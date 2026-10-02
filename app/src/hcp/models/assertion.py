"""Typed assertion metadata model.

Design notes
------------
The internal model is intentionally *tolerant* at load time: a hand-written
Codex must still be loadable so that the validator can report precise, useful
errors instead of the parser crashing with a stack trace. Enum membership and
range checks therefore live in :mod:`hcp.validation.validator`, not in field
validators. This module only normalises representation (dates, lists, numbers)
and guarantees that unknown metadata survives a load/save round trip.

Forward compatibility
---------------------
``model_config`` sets ``extra="allow"``, and :meth:`Assertion.metadata`
re-emits unknown keys in sorted order after the known ones. Nothing a future HCP
revision adds to the frontmatter is discarded by this implementation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Assertion types defined by HCP-0001 section 7 and assertion.schema.json.
ASSERTION_TYPES: tuple[str, ...] = (
    "fact",
    "belief",
    "value",
    "principle",
    "preference",
    "boundary",
    "goal",
    "aspiration",
    "identity",
    "relationship",
    "experience",
    "observation",
)

#: Sources defined by assertion.schema.json.
SOURCES: tuple[str, ...] = ("human", "ai", "import", "derived")

#: Authority levels defined by assertion.schema.json.
AUTHORITIES: tuple[str, ...] = ("authoritative", "proposed", "rejected", "archived")

#: Lifecycle states defined by assertion.schema.json.
STATUSES: tuple[str, ...] = ("active", "pending", "rejected", "archived")

#: Disclosure classes defined by assertion.schema.json.
VISIBILITIES: tuple[str, ...] = ("public", "private", "sensitive", "restricted")

#: Ordered metadata keys used when writing an assertion back to Markdown.
METADATA_ORDER: tuple[str, ...] = (
    "hcp",
    "id",
    "type",
    "source",
    "authority",
    "status",
    "confidence",
    "created",
    "updated",
    "valid_from",
    "valid_until",
    "visibility",
    "tags",
    "derived_from",
    "supersedes",
)


def utc_today() -> date:
    """Return today's UTC date.

    UTC keeps behaviour deterministic in tests and avoids depending on a
    machine-local timezone that the Codex has not declared yet.
    """
    return datetime.now(UTC).date()


class Provenance(BaseModel):
    """Structured record of how an assertion came to exist.

    The specification names provenance but does not fix a schema, so this is the
    smallest useful set of fields. Unknown keys are preserved via ``extra``.
    """

    model_config = ConfigDict(extra="allow")

    origin: str | None = None
    """``human``, ``ai``, ``import``, ``derived``, or a free-form label."""

    observation_id: str | None = None
    """ID of the AI observation this assertion came from, if any."""

    received_at: str | None = None
    """ISO-8601 timestamp at which the material entered the Codex."""

    decided_at: str | None = None
    """ISO-8601 timestamp of the human review decision."""

    decision: str | None = None
    """One of ``accepted``, ``edited``, ``rejected`` or ``archived``."""

    confidence_at_ingest: float | None = None
    """Confidence as claimed by the AI at ingestion time."""

    note: str | None = None
    """Optional human-written explanation of the decision."""

    def unknown_fields(self) -> dict[str, Any]:
        """Return unknown provenance keys that must be preserved."""
        return dict(self.__pydantic_extra__ or {})


class Assertion(BaseModel):
    """A single HCP assertion: typed metadata plus its Markdown body."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    hcp: str = "0.1"
    id: str
    type: str
    source: str = "human"
    authority: str = "authoritative"
    status: str = "active"
    visibility: str = "private"
    confidence: float | None = None
    created: date | None = None
    updated: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    supersedes: str | None = None
    tags: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)
    provenance: Provenance | None = None
    body: str = ""

    path: str | None = None
    """Repository-relative path of the backing Markdown file, when loaded."""

    promoted_to: str | None = None
    """For observations: the ID of the authoritative assertion a review created.

    Recorded on the retained original so the link survives in both directions:
    the promoted assertion cites the observation via ``derived_from``, and the
    observation records where its accepted content ended up."""

    def unknown_fields(self) -> dict[str, Any]:
        """Return unknown top-level metadata keys that must be preserved.

        Anything a future HCP revision adds to the frontmatter lands here and
        is re-emitted by :meth:`metadata`, so loading and saving never silently
        discards a field this implementation does not understand.
        """
        return dict(self.__pydantic_extra__ or {})

    # ------------------------------------------------------------------
    # Representation normalisation. These validators never reject a value;
    # they only make it predictable so the validator can report semantic
    # problems with a helpful message.
    # ------------------------------------------------------------------

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                return value  # left as-is so the validator can report it
        return value

    @field_validator("tags", "derived_from", mode="before")
    @classmethod
    def _coerce_str_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        return value

    @field_validator("created", "updated", "valid_from", "valid_until", mode="before")
    @classmethod
    def _coerce_dates(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (date, datetime)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() in {"null", "none", "~"}:
                return None
            return text
        return value

    @field_validator("supersedes", mode="before")
    @classmethod
    def _coerce_supersedes(cls, value: Any) -> Any:
        # The schema declares a single string or null, but tolerate a list
        # rather than crashing; the validator reports the mismatch.
        if isinstance(value, (list, tuple)) and value:
            return str(value[0])
        return value

    # ------------------------------------------------------------------
    # Temporal semantics (HCP-0001 section 10)
    # ------------------------------------------------------------------

    def is_valid_at(self, moment: date) -> bool:
        """Return ``True`` if the assertion is temporally valid at ``moment``."""
        if self.valid_from is not None and moment < self.valid_from:
            return False
        return not (self.valid_until is not None and moment > self.valid_until)

    def is_expired(self, moment: date) -> bool:
        """Return ``True`` if the assertion is no longer valid at ``moment``."""
        return self.valid_until is not None and moment > self.valid_until

    def is_future(self, moment: date) -> bool:
        """Return ``True`` if the assertion is not yet valid at ``moment``."""
        return self.valid_from is not None and moment < self.valid_from

    def temporal_state(self, moment: date) -> str:
        """Return ``current``, ``expired``, ``future`` or ``undated``."""
        if self.is_expired(moment):
            return "expired"
        if self.is_future(moment):
            return "future"
        if self.valid_from is None and self.valid_until is None:
            return "undated"
        return "current"

    @property
    def is_ai_observation(self) -> bool:
        """Return ``True`` for AI-proposed material awaiting human review."""
        return self.source == "ai" or self.type == "observation"

    @property
    def is_pending(self) -> bool:
        """Return ``True`` if the assertion still requires a human decision."""
        return self.status == "pending"

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def metadata(self) -> dict[str, Any]:
        """Return the ordered frontmatter mapping for this assertion.

        Known keys come first in a fixed order; unknown keys from the original
        document follow in sorted order so nothing is discarded and output stays
        deterministic.
        """
        data: dict[str, Any] = {}
        for key in METADATA_ORDER:
            value = getattr(self, key, None)
            if key in {"confidence", "created", "updated", "valid_from", "valid_until"}:
                data[key] = value.isoformat() if isinstance(value, date) else value
            elif key in {"tags", "derived_from"}:
                data[key] = list(value or [])
            else:
                data[key] = value
        if self.provenance is not None:
            data["provenance"] = self.provenance.model_dump(
                exclude_none=True, exclude_defaults=True
            )
        if self.promoted_to is not None:
            data["promoted_to"] = self.promoted_to
        unknown = self.unknown_fields()
        for key in sorted(unknown):
            if key not in data:
                data[key] = unknown[key]
        return data

    def to_json_dict(self, *, include_body: bool = True) -> dict[str, Any]:
        """Return the machine-readable representation of this assertion."""
        data = self.metadata()
        if include_body:
            data["body"] = self.body
        if self.path:
            data["path"] = self.path
        return data


__all__ = [
    "ASSERTION_TYPES",
    "AUTHORITIES",
    "METADATA_ORDER",
    "SOURCES",
    "STATUSES",
    "VISIBILITIES",
    "Assertion",
    "Provenance",
    "utc_today",
]
