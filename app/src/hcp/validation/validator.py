"""Codex validation.

The validator is the human's safety net. It reports every problem it can find in
one pass, naming the file and, where possible, the exact metadata field. It never
mutates anything.

Checks implemented (BUILD-APP section 14)
-----------------------------------------
missing manifest, malformed YAML, malformed frontmatter, invalid assertion type,
invalid source, invalid authority, invalid status, invalid visibility, confidence
outside 0..1, invalid dates, duplicate IDs, missing required metadata, invalid AI
observation state, broken ``supersedes`` references, broken ``derived_from``
references, and unsafe or malformed paths.

Authority invariants (BUILD-APP section 8)
-----------------------------------------
* ``source: human`` + ``authority: authoritative`` is valid.
* ``source: ai`` must be ``authority: proposed`` + ``status: pending`` until a
  human reviews it. Confidence never changes this: a high-confidence AI
  observation that claims to be authoritative is an **error**, not a warning,
  because that is precisely the silent identity mutation HCP-0001 forbids.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ..constants import MANIFEST_FILENAME
from ..errors import Issue, Severity
from ..ids import id_problem, namespace_of
from ..models.assertion import (
    ASSERTION_TYPES,
    AUTHORITIES,
    SOURCES,
    STATUSES,
    VISIBILITIES,
    Assertion,
)
from ..models.manifest import Manifest
from ..repository.codex import Codex

#: Metadata fields every assertion must declare.
REQUIRED_FIELDS: tuple[str, ...] = ("id", "type", "source", "authority", "status", "visibility")

#: Fields that must be parseable as ISO-8601 dates.
DATE_FIELDS: tuple[str, ...] = ("created", "updated", "valid_from", "valid_until")

#: Authority values that may coexist with ``status: active``.
ACTIVE_AUTHORITIES: frozenset[str] = frozenset({"authoritative"})


@dataclass
class ValidationReport:
    """The outcome of validating a Codex."""

    issues: list[Issue]

    @property
    def errors(self) -> list[Issue]:
        """Return only the error-severity issues."""
        return [issue for issue in self.issues if issue.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        """Return only the warning-severity issues."""
        return [issue for issue in self.issues if issue.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        """Return ``True`` when the Codex has no errors."""
        return not self.errors

    def __bool__(self) -> bool:
        return self.ok

    def summary(self) -> str:
        """Return a one-line human summary."""
        if self.ok and not self.warnings:
            return "valid: no problems found"
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return ", ".join(parts)


def validate_codex(codex: Codex, *, today: date | None = None) -> ValidationReport:
    """Validate a loaded Codex.

    Args:
        codex: The loaded Codex.
        today: Reference date for temporal warnings; defaults to today (UTC).

    Returns:
        A :class:`ValidationReport` listing every issue found.
    """
    issues: list[Issue] = []
    issues.extend(_validate_manifest(codex.manifest))
    issues.extend(codex.issues)
    issues.extend(_validate_dates_and_confidence(codex, today))
    issues.extend(_validate_duplicate_ids(codex))
    issues.extend(_validate_references(codex))
    for assertion in codex.assertions:
        issues.extend(_validate_assertion(assertion))
    issues.extend(_validate_observation_state(codex))
    issues.sort(key=lambda issue: (issue.severity.value, issue.path or "", issue.field or ""))
    return ValidationReport(issues=issues)


# ----------------------------------------------------------------------
# Manifest
# ----------------------------------------------------------------------


def _validate_manifest(manifest: Manifest) -> list[Issue]:
    issues: list[Issue] = []
    if not manifest.title.strip():
        issues.append(
            Issue("manifest_invalid_title", "title must not be empty", MANIFEST_FILENAME, "title")
        )
    problem = id_problem(manifest.codex_id)
    if problem:
        issues.append(
            Issue(
                "invalid_codex_id",
                f"codex_id is invalid: {problem}",
                MANIFEST_FILENAME,
                "codex_id",
            )
        )
    for name, value in (("created", manifest.created), ("updated", manifest.updated)):
        if manifest.unknown_fields().get(name) is not None and value is None:
            issues.append(
                Issue(
                    "invalid_date",
                    f"{name} is not a valid ISO-8601 date (YYYY-MM-DD)",
                    MANIFEST_FILENAME,
                    name,
                )
            )
    if manifest.privacy is not None:
        visibility = manifest.privacy.default_visibility
        if visibility not in VISIBILITIES:
            issues.append(
                Issue(
                    "invalid_visibility",
                    f"privacy.default_visibility must be one of {list(VISIBILITIES)}",
                    MANIFEST_FILENAME,
                    "privacy.default_visibility",
                )
            )
    return issues


# ----------------------------------------------------------------------
# Per-assertion checks
# ----------------------------------------------------------------------


def _validate_assertion(assertion: Assertion) -> list[Issue]:
    issues: list[Issue] = []
    path = assertion.path
    add = issues.append

    for field in REQUIRED_FIELDS:
        value = getattr(assertion, field, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            add(
                Issue(
                    "missing_required_field",
                    f"required metadata field {field!r} is missing or empty",
                    path,
                    field,
                )
            )

    if assertion.id:
        problem = id_problem(assertion.id)
        if problem:
            add(Issue("invalid_id", f"invalid assertion id: {problem}", path, "id"))

    if assertion.type and assertion.type not in ASSERTION_TYPES:
        add(
            Issue(
                "invalid_type",
                f"unknown assertion type {assertion.type!r}; expected one of {list(ASSERTION_TYPES)}",
                path,
                "type",
            )
        )

    if assertion.source not in SOURCES:
        add(
            Issue(
                "invalid_source",
                f"unknown source {assertion.source!r}; expected one of {list(SOURCES)}",
                path,
                "source",
            )
        )

    if assertion.authority not in AUTHORITIES:
        add(
            Issue(
                "invalid_authority",
                f"unknown authority {assertion.authority!r}; expected one of {list(AUTHORITIES)}",
                path,
                "authority",
            )
        )

    if assertion.status not in STATUSES:
        add(
            Issue(
                "invalid_status",
                f"unknown status {assertion.status!r}; expected one of {list(STATUSES)}",
                path,
                "status",
            )
        )

    if assertion.visibility not in VISIBILITIES:
        add(
            Issue(
                "invalid_visibility",
                f"unknown visibility {assertion.visibility!r}; expected one of {list(VISIBILITIES)}",
                path,
                "visibility",
            )
        )

    issues.extend(_check_authority_invariants(assertion))

    if assertion.id and assertion.type:
        try:
            namespace = namespace_of(assertion.id)
        except ValueError:
            namespace = ""
        if namespace and namespace != assertion.type and assertion.source != "ai":
            add(
                Issue(
                    "namespace_type_mismatch",
                    f"id namespace {namespace!r} differs from type {assertion.type!r}; "
                    "this is allowed but unconventional",
                    path,
                    "id",
                    Severity.WARNING,
                )
            )

    if not assertion.body.strip():
        add(
            Issue(
                "empty_body",
                "assertion has no body text; it carries no human-readable content",
                path,
                "body",
                Severity.WARNING,
            )
        )

    if assertion.visibility == "restricted":
        add(
            Issue(
                "restricted_assertion",
                "restricted assertions are excluded from bundles unless the scope "
                "explicitly authorizes them",
                path,
                "visibility",
                Severity.WARNING,
            )
        )

    return issues


def _check_authority_invariants(assertion: Assertion) -> list[Issue]:
    """Enforce that AI material never becomes authoritative by itself."""
    issues: list[Issue] = []
    path = assertion.path

    if assertion.source == "ai" and assertion.authority == "authoritative":
        decision = _decision_of(assertion)
        if decision is None:
            issues.append(
                Issue(
                    "ai_observation_self_authoritative",
                    "AI-sourced assertions cannot be authoritative without a recorded "
                    "human review decision in provenance (use 'hcp review')",
                    path,
                    "authority",
                )
            )
        elif decision not in {"accepted", "edited"}:
            issues.append(
                Issue(
                    "ai_observation_not_accepted",
                    f"AI-sourced assertion has authority 'authoritative' but its recorded "
                    f"decision is {decision!r}; only 'accepted' or 'edited' grants authority",
                    path,
                    "authority",
                )
            )

    if (
        assertion.source == "ai"
        and assertion.status == "active"
        and assertion.authority == "proposed"
    ):
        issues.append(
            Issue(
                "ai_observation_state_conflict",
                "an AI observation awaiting review must use status 'pending', not 'active'",
                path,
                "status",
            )
        )

    if assertion.status == "active" and assertion.authority not in ACTIVE_AUTHORITIES:
        issues.append(
            Issue(
                "status_authority_conflict",
                f"status 'active' requires authority 'authoritative', found "
                f"{assertion.authority!r}",
                path,
                "status",
            )
        )

    if assertion.authority == "rejected" and assertion.status != "rejected":
        issues.append(
            Issue(
                "status_authority_conflict",
                "authority 'rejected' requires status 'rejected'",
                path,
                "status",
            )
        )

    if assertion.authority == "archived" and assertion.status != "archived":
        issues.append(
            Issue(
                "status_authority_conflict",
                "authority 'archived' requires status 'archived'",
                path,
                "status",
            )
        )

    if assertion.type == "observation" and assertion.source == "human":
        issues.append(
            Issue(
                "observation_source_mismatch",
                "type 'observation' describes AI inference and should use source 'ai'; "
                "a human-authored statement is normally a fact, belief, or value",
                path,
                "source",
                Severity.WARNING,
            )
        )

    return issues


def _decision_of(assertion: Assertion) -> str | None:
    """Return the recorded human review decision for an assertion, if any."""
    if assertion.provenance is not None:
        return assertion.provenance.decision
    raw = assertion.unknown_fields().get("provenance")
    if isinstance(raw, dict):
        decision = raw.get("decision")
        return str(decision) if decision is not None else None
    return None


def _validate_dates_and_confidence(codex: Codex, today: date | None) -> list[Issue]:
    """Check date ranges and the confidence bound for every assertion."""
    issues: list[Issue] = []
    for assertion in codex.assertions:
        path = assertion.path

        for name in DATE_FIELDS:
            raw = assertion.unknown_fields().get(name)
            if raw is not None and getattr(assertion, name, None) is None:
                issues.append(
                    Issue(
                        "invalid_date",
                        f"{name} must be an ISO-8601 date (YYYY-MM-DD), got {raw!r}",
                        path,
                        name,
                    )
                )

        if assertion.confidence is not None and not 0.0 <= assertion.confidence <= 1.0:
            issues.append(
                Issue(
                    "invalid_confidence",
                    f"confidence must be between 0.0 and 1.0, got {assertion.confidence}",
                    path,
                    "confidence",
                )
            )

        if (
            isinstance(assertion.confidence, (int, float))
            and not isinstance(assertion.confidence, bool)
            and assertion.confidence > 1.0
            and assertion.source == "ai"
        ):
            issues.append(
                Issue(
                    "invalid_confidence",
                    "an AI observation with confidence above 1.0 is malformed; note that "
                    "confidence never confers authority regardless of its value",
                    path,
                    "confidence",
                )
            )

        if (
            assertion.valid_from
            and assertion.valid_until
            and assertion.valid_until < assertion.valid_from
        ):
            issues.append(
                Issue(
                    "invalid_date_range",
                    f"valid_until ({assertion.valid_until}) is before valid_from "
                    f"({assertion.valid_from})",
                    path,
                    "valid_until",
                )
            )

        if assertion.created and assertion.updated and assertion.updated < assertion.created:
            issues.append(
                Issue(
                    "invalid_date_range",
                    f"updated ({assertion.updated}) is before created ({assertion.created})",
                    path,
                    "updated",
                )
            )

        if today is not None and assertion.valid_from and assertion.valid_from > today:
            issues.append(
                Issue(
                    "future_assertion",
                    f"valid_from is in the future ({assertion.valid_from.isoformat()})",
                    path,
                    "valid_from",
                    Severity.WARNING,
                )
            )

    return issues


def _validate_duplicate_ids(codex: Codex) -> list[Issue]:
    """Report IDs that appear in more than one file."""
    issues: list[Issue] = []
    seen: dict[str, list[str]] = {}
    for assertion in codex.assertions:
        seen.setdefault(assertion.id, []).append(assertion.path or "<unknown>")
    for assertion_id, paths in sorted(seen.items()):
        if len(paths) > 1:
            joined = ", ".join(sorted(paths))
            issues.append(
                Issue(
                    "duplicate_id",
                    f"id {assertion_id!r} is used by {len(paths)} files: {joined}",
                    sorted(paths)[0],
                    "id",
                )
            )
    return issues


def _validate_references(codex: Codex) -> list[Issue]:
    """Check ``supersedes`` and ``derived_from`` resolve to real assertions."""
    issues: list[Issue] = []
    known = {assertion.id for assertion in codex.assertions}
    for assertion in codex.assertions:
        if assertion.supersedes and assertion.supersedes not in known:
            issues.append(
                Issue(
                    "broken_supersedes",
                    f"supersedes references unknown assertion {assertion.supersedes!r}",
                    assertion.path,
                    "supersedes",
                )
            )
        for reference in assertion.derived_from:
            # derived_from may legitimately cite external material such as
            # 'conversation:example'; only bare HCP IDs are resolved.
            if ":" in reference:
                continue
            if reference not in known:
                issues.append(
                    Issue(
                        "broken_derived_from",
                        f"derived_from references unknown assertion {reference!r}",
                        assertion.path,
                        "derived_from",
                    )
                )
        if assertion.supersedes == assertion.id:
            issues.append(
                Issue(
                    "self_supersedes",
                    "an assertion cannot supersede itself",
                    assertion.path,
                    "supersedes",
                )
            )
    return issues


def _validate_observation_state(codex: Codex) -> list[Issue]:
    """Check that the set of pending observations is internally consistent."""
    issues: list[Issue] = []
    for assertion in codex.pending_observations():
        if assertion.authority != "proposed":
            issues.append(
                Issue(
                    "invalid_observation_state",
                    "pending observations must have authority 'proposed'",
                    assertion.path,
                    "authority",
                )
            )
        if assertion.source == "ai" and assertion.type != "observation":
            issues.append(
                Issue(
                    "invalid_observation_state",
                    "AI-sourced pending material should use type 'observation'",
                    assertion.path,
                    "type",
                    Severity.WARNING,
                )
            )
    return issues


def parse_iso_date(value: str) -> date | None:
    """Parse an ISO-8601 date, returning ``None`` when invalid."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_iso_datetime(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp, returning ``None`` when invalid."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


__all__ = [
    "ACTIVE_AUTHORITIES",
    "DATE_FIELDS",
    "REQUIRED_FIELDS",
    "ValidationReport",
    "parse_iso_date",
    "parse_iso_datetime",
    "validate_codex",
]
