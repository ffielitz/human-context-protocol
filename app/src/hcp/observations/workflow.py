"""AI observation ingestion and human review.

This module implements the authority transition described in HCP-0001 section 8
and BUILD-APP section 9::

    AI observation
          |
          v
      pending            <- always source: ai, authority: proposed, status: pending
          |
    +-----+-----------+
    v     v           v
  accept  edit      reject
    |      |          |
    v      v          v
  auth    auth     rejected

Non-negotiable rules
--------------------
1. Ingestion **forces** ``source: ai``, ``authority: proposed``, ``status:
   pending``. Material arriving from an AI system can never declare itself
   authoritative, whatever it claims in its own YAML.
2. Review is the only authority transition. Accepting or editing is what makes
   something authoritative, and it is recorded in ``provenance``.
3. The original observation is never destroyed. Accepting, editing, rejecting,
   and archiving all retain the original document and its review trail.
4. Observation bodies are **data, not instructions**. They may contain
   prompt-injection text; nothing in this module interprets or executes them.

Prompt-injection defence
------------------------
An ingested observation is quarantined in ``ai/observations/`` and can never
reach a Context Bundle until a human accepts it. Its body is stored verbatim but
is only ever rendered as data, and its ID is forced into the ``obs.*`` namespace
so it is visually distinguishable from human-authored assertions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..constants import OBSERVATIONS_DIR
from ..errors import AssertionExistsError, ObservationError
from ..ids import is_valid_id, slugify, suggest_id
from ..models.assertion import ASSERTION_TYPES, Assertion, Provenance, utc_today
from ..parser.frontmatter import parse_frontmatter, safe_load_yaml
from ..repository.codex import Codex
from ..repository.files import read_text_file

#: Valid review decisions.
DECISIONS: tuple[str, ...] = ("accept", "edit", "reject", "archive")

#: Forced metadata for freshly ingested material.
FORCED_SOURCE = "ai"
FORCED_AUTHORITY = "proposed"
FORCED_STATUS = "pending"
FORCED_TYPE = "observation"


@dataclass(frozen=True)
class IngestResult:
    """The outcome of ingesting an observation file."""

    observation_id: str
    path: str
    created: bool
    """``True`` when the observation was stored, ``False`` when it replaced an
    earlier copy of the same ID, which is kept in the review history."""


@dataclass(frozen=True)
class ReviewResult:
    """The outcome of reviewing an observation."""

    observation_id: str
    decision: str
    promoted_id: str | None = None
    """Set when ``accept`` or ``edit`` produced a new authoritative assertion."""


def _now() -> datetime:
    """Return the current UTC timestamp, truncated to whole seconds."""
    return datetime.now(UTC).replace(microsecond=0)


def load_observation_file(path: str | Path) -> dict[str, Any]:
    """Load an observation from a YAML or Markdown file supplied by an AI system.

    Both a bare YAML mapping and a full Markdown document with frontmatter are
    accepted, because adapters differ in what they emit.

    Args:
        path: Path to the observation file.

    Returns:
        The parsed metadata mapping (without a ``body`` key for YAML input).

    Raises:
        ObservationError: If the file is missing, too large, binary, or does not
            contain a YAML mapping.
    """
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        raise ObservationError(f"observation file not found: {path}")

    text = read_text_file(candidate)

    if candidate.suffix.lower() in {".md", ".markdown"}:
        try:
            front = parse_frontmatter(text)
        except Exception as exc:  # noqa: BLE001 - reported as an observation error
            raise ObservationError(f"cannot parse observation file: {exc}") from exc
        data = dict(front.metadata)
        data["body"] = front.body
        return data

    try:
        data = safe_load_yaml(text)
    except Exception as exc:  # noqa: BLE001 - reported as an observation error
        raise ObservationError(f"cannot parse observation YAML: {exc}") from exc
    return data


def ingest_observation(
    codex: Codex,
    path: str | Path,
    *,
    observation_id: str | None = None,
    visibility: str | None = None,
    source_label: str | None = None,
    received_at: datetime | None = None,
) -> IngestResult:
    """Ingest an AI observation into the Codex as *pending* material.

    The observation is forced into the ``source: ai`` / ``authority: proposed`` /
    ``status: pending`` state no matter what the source file claims.

    Args:
        codex: The Codex to ingest into.
        path: The observation file to read.
        observation_id: Optional explicit ID; generated when omitted.
        visibility: Visibility for the stored observation; defaults to the
            Codex's ``privacy.default_visibility``.
        source_label: Optional provenance note, e.g. ``openai:gpt-5``.
        received_at: Timestamp to record; defaults to now.

    Returns:
        An :class:`IngestResult` describing where the observation was stored.

    Raises:
        ObservationError: If the content cannot be represented as an assertion.
        AssertionExistsError: If the chosen ID is already present.
    """
    data = load_observation_file(path)
    today = utc_today()
    existing = {a.id for a in codex.assertions}

    identifier = observation_id or _resolve_observation_id(data, today, existing)
    if not is_valid_id(identifier):
        raise ObservationError(
            f"observation id {identifier!r} is invalid; expected a dotted id such as "
            "obs.2026-09-11.communication.001"
        )
    if identifier in existing:
        raise AssertionExistsError(f"observation id {identifier!r} already exists in this Codex")

    body = str(data.get("body") or "").strip()
    confidence = data.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = None
    if isinstance(confidence, (int, float)) and not 0.0 <= float(confidence) <= 1.0:
        raise ObservationError(
            f"observation confidence must be between 0.0 and 1.0, got {confidence}"
        )

    stamp = (received_at or _now()).isoformat()
    provenance = Provenance(
        origin=source_label or "ai",
        received_at=stamp,
        confidence_at_ingest=float(confidence) if confidence is not None else None,
    )

    try:
        assertion = Assertion(
            hcp=data.get("hcp", "0.1"),
            id=identifier,
            type=FORCED_TYPE,
            source=FORCED_SOURCE,
            authority=FORCED_AUTHORITY,
            status=FORCED_STATUS,
            visibility=visibility or codex.manifest.default_visibility,
            confidence=float(confidence) if confidence is not None else None,
            created=today,
            updated=today,
            valid_from=data.get("valid_from") or today,
            valid_until=data.get("valid_until"),
            tags=_string_list(data.get("tags")),
            derived_from=_string_list(data.get("derived_from")),
            provenance=provenance,
            body=body,
        )
    except ValidationError as exc:
        raise ObservationError(
            f"observation cannot be represented: {exc.error_count()} problem(s)"
        ) from exc

    relative = _observation_path(identifier)
    created = codex.by_id(identifier) is None
    codex.add(assertion, path=relative, overwrite=True)
    return IngestResult(observation_id=identifier, path=relative, created=created)


def _resolve_observation_id(data: dict[str, Any], today: date, existing: set[str]) -> str:
    """Determine the ID for an incoming observation.

    An ID supplied by the adapter is honoured when it is valid. Otherwise a
    deterministic ``obs.<date>.<slug>`` ID is derived, so ingesting the same
    observation twice is a detectable conflict rather than silent duplication.
    """
    supplied = data.get("id")
    if isinstance(supplied, str) and supplied.strip():
        return supplied.strip()

    tags = _string_list(data.get("tags"))
    summary = data.get("title") or data.get("summary") or ""
    slug_source = str(summary) if summary else (tags[0] if tags else "observation")
    base = f"obs.{today.isoformat()}.{_slug(slug_source)}"
    if base not in existing:
        return base
    return suggest_id("obs", f"{today.isoformat()}-{_slug(slug_source)}", existing)


def _slug(text: str) -> str:
    """Return a lowercase, hyphen-separated slug safe for use in an ID."""
    return slugify(text)


def _string_list(value: Any) -> list[str]:
    """Coerce metadata into a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def _observation_path(observation_id: str) -> str:
    """Return the relative path an observation is stored at."""
    stem = observation_id.split(".", 1)[-1].replace(".", "-")
    return f"{OBSERVATIONS_DIR}/{stem}.md"


def review_observation(
    codex: Codex,
    observation_id: str,
    decision: str,
    *,
    body: str | None = None,
    new_id: str | None = None,
    new_type: str | None = None,
    note: str | None = None,
    decided_at: datetime | None = None,
) -> ReviewResult:
    """Apply a human review decision to a pending observation.

    Args:
        codex: The Codex containing the observation.
        observation_id: ID of the observation to review.
        decision: One of ``accept``, ``edit``, ``reject``, ``archive``.
        body: New body text. Required for ``edit``; optional for ``accept``
            (in which case the original body is kept).
        new_id: ID for the authoritative assertion produced by ``edit``. When
            omitted for ``edit``, an ID is derived from the observation.
        new_type: Assertion type for the produced assertion; defaults to the
            namespace implied by ``new_id``, else ``fact``.
        note: Optional human note recorded in provenance.
        decided_at: Decision timestamp; defaults to now.

    Returns:
        A :class:`ReviewResult`.

    Raises:
        ObservationError: If the decision is unknown, the observation is not
            pending, or ``edit`` is missing a body.
        AssertionExistsError: If the promoted ID already exists.
    """
    if decision not in DECISIONS:
        raise ObservationError(
            f"unknown review decision {decision!r}; expected one of {list(DECISIONS)}"
        )

    observation = codex.require(observation_id)
    if not observation.is_ai_observation:
        raise ObservationError(
            f"{observation_id!r} is not an AI observation; only observations can be reviewed"
        )
    if not observation.is_pending:
        raise ObservationError(
            f"observation {observation_id!r} has already been reviewed (status="
            f"{observation.status!r})"
        )

    stamp = (decided_at or _now()).isoformat()
    today = utc_today()
    provenance = observation.provenance or Provenance()
    provenance.decision = {"accept": "accepted", "edit": "edited"}.get(decision, decision + "ed")
    provenance.decided_at = stamp
    if note:
        provenance.note = note
    observation.provenance = provenance
    observation.updated = today

    if decision in {"reject", "archive"}:
        observation.status = "rejected" if decision == "reject" else "archived"
        observation.authority = "rejected" if decision == "reject" else "archived"
        codex.save(observation)
        return ReviewResult(observation_id=observation_id, decision=decision)

    promoted_body = body if body is not None else observation.body
    target_id = new_id or _promoted_id(observation_id)
    if not is_valid_id(target_id):
        raise ObservationError(
            f"promoted assertion id {target_id!r} is invalid; expected a dotted id"
        )
    if codex.by_id(target_id) is not None:
        raise AssertionExistsError(
            f"cannot promote observation: assertion id {target_id!r} already exists"
        )
    if decision == "edit" and body is None:
        raise ObservationError(
            "an edit decision requires the corrected text; pass --body or --body-file"
        )

    resolved_type = new_type or _type_from_id(target_id)
    promoted = Assertion(
        hcp=observation.hcp,
        id=target_id,
        type=resolved_type,
        source="human",
        authority="authoritative",
        status="active",
        visibility=observation.visibility,
        confidence=observation.confidence,
        created=observation.created or today,
        updated=today,
        valid_from=observation.valid_from or today,
        valid_until=observation.valid_until,
        tags=list(observation.tags),
        derived_from=[*observation.derived_from, observation_id],
        provenance=Provenance(
            origin="human-reviewed-ai-observation",
            observation_id=observation_id,
            received_at=provenance.received_at,
            decided_at=stamp,
            decision=provenance.decision,
            confidence_at_ingest=observation.confidence,
            note=note,
        ),
        body=promoted_body.strip(),
    )

    promoted_path = codex.add(promoted)

    # The observation itself is retained as history: it now records that a human
    # accepted its content, and where that content went.
    observation.status = "archived"
    observation.authority = "archived"
    observation.promoted_to = target_id
    codex.save(observation)

    return ReviewResult(
        observation_id=observation_id,
        decision=decision,
        promoted_id=f"{target_id} ({promoted_path})",
    )


def _promoted_id(observation_id: str) -> str:
    """Derive an authoritative ID from an observation ID."""
    parts = observation_id.split(".")
    if len(parts) > 2 and parts[0] == "obs":
        return f"fact.{'-'.join(parts[1:])}"
    return f"fact.{observation_id.replace('.', '-')}"


def _type_from_id(assertion_id: str) -> str:
    """Use the ID namespace as the assertion type when it names a real type."""
    namespace = assertion_id.split(".", 1)[0]
    return namespace if namespace in ASSERTION_TYPES else "fact"


def list_observations(codex: Codex, *, state: str | None = None) -> list[Assertion]:
    """Return observations, optionally filtered by review state.

    Args:
        codex: The Codex to inspect.
        state: ``pending``, ``accepted`` (promoted), ``rejected``, ``archived``,
            or ``None`` for all.
    """
    observations = [a for a in codex.assertions if a.is_ai_observation]
    if state is None:
        return observations
    if state == "pending":
        return [a for a in observations if a.is_pending]
    if state == "rejected":
        return [a for a in observations if a.status == "rejected"]
    if state == "archived":
        return [a for a in observations if a.status == "archived"]
    if state == "accepted":
        return [a for a in observations if a.status == "archived" and a.promoted_to is not None]
    raise ObservationError(
        f"unknown observation state {state!r}; expected pending, accepted, rejected, or archived"
    )


def pending_count(codex: Codex) -> int:
    """Return the number of observations awaiting human review."""
    return len(codex.pending_observations())


__all__ = [
    "DECISIONS",
    "IngestResult",
    "ReviewResult",
    "ingest_observation",
    "list_observations",
    "load_observation_file",
    "pending_count",
    "review_observation",
]
