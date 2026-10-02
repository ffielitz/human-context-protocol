"""Error types for the HCP reference implementation.

Every error that is expected during normal operation is expressed as either an
exception deriving from :class:`HCPError` or as a structured :class:`Issue`
produced by the validator. The CLI turns both into calm, actionable messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HCPError(Exception):
    """Base class for all expected HCP errors."""


class CodexError(HCPError):
    """Base class for errors that concern a Codex repository."""


class CodexNotFoundError(CodexError):
    """The given path is not an HCP Codex."""


class ManifestMissingError(CodexError):
    """A Codex must contain a readable ``manifest.yaml``."""


class UnsafePathError(CodexError):
    """A path escapes the Codex, traverses upwards, or is a symlink."""


class AssertionExistsError(CodexError):
    """An assertion ID or target path is already in use."""


class AssertionNotFoundError(CodexError):
    """No assertion with the requested ID exists in the Codex."""


class ObservationError(HCPError):
    """An observation could not be ingested or reviewed."""


class ScopeConfigError(HCPError):
    """A scope configuration file is malformed."""


class GitUnavailableError(HCPError):
    """The ``git`` binary is not available or the directory is not a repo."""


class Severity(StrEnum):
    """How serious a validation finding is."""

    ERROR = "error"
    WARNING = "warning"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass(frozen=True)
class Issue:
    """A single validation finding.

    Attributes:
        code: Stable machine-readable identifier, e.g. ``invalid_confidence``.
        message: Human-readable, single-sentence description.
        path: Repository-relative path of the offending file, if known.
        field: Dotted metadata field name the issue relates to, if known.
        severity: ``error`` or ``warning``.
    """

    code: str
    message: str
    path: str | None = None
    field: str | None = None
    severity: Severity = Severity.ERROR

    def format(self) -> str:
        """Render the issue as one ``severity: file: field: message`` line."""
        location = self.path or "<codex>"
        if self.field:
            location = f"{location}:{self.field}"
        return f"{self.severity.value}: {location}: {self.message}"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.format()


class DocumentError(CodexError):
    """A document could not be parsed into the internal model."""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = list(issues)
        summary = "; ".join(issue.format() for issue in self.issues) or "invalid document"
        super().__init__(summary)


__all__ = [
    "AssertionExistsError",
    "AssertionNotFoundError",
    "CodexError",
    "CodexNotFoundError",
    "DocumentError",
    "GitUnavailableError",
    "HCPError",
    "Issue",
    "ManifestMissingError",
    "ObservationError",
    "ScopeConfigError",
    "Severity",
    "UnsafePathError",
]
