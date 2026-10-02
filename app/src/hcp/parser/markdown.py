"""Markdown + frontmatter to :class:`~hcp.models.assertion.Assertion`.

This module connects the parser to the data model. It deliberately does *not*
render or execute Markdown: the body is opaque human text that may contain
prompt-injection content, so it is only ever treated as data.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..errors import DocumentError, Issue
from ..models.assertion import Assertion
from .frontmatter import dump_frontmatter, parse_frontmatter


def assertion_from_markdown(text: str, *, path: str | None = None) -> Assertion:
    """Parse Markdown into an :class:`Assertion`.

    Args:
        text: Full Markdown document, frontmatter included.
        path: Repository-relative path, used for error reporting.

    Returns:
        The parsed assertion, including its body and any unknown metadata.

    Raises:
        DocumentError: If frontmatter is missing/malformed, or the metadata
            cannot be represented by the model (e.g. ``id`` is absent or of the
            wrong type).
    """
    front = parse_frontmatter(text, path=path)
    metadata: dict[str, Any] = dict(front.metadata)
    metadata["body"] = front.body
    if path is not None:
        metadata["path"] = path
    try:
        return Assertion(**metadata)
    except ValidationError as exc:
        raise DocumentError(_issues_from_validation_error(exc, path)) from exc


def _issues_from_validation_error(exc: ValidationError, path: str | None) -> list[Issue]:
    """Translate a Pydantic error into HCP issues that name the offending field.

    Mapping Pydantic's error types back to HCP issue codes keeps the codes
    stable and specific, so ``created: "not-a-date"`` is reported as
    ``invalid_date`` rather than a generic ``invalid_metadata``.
    """
    issues: list[Issue] = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", ()) if part != "body"]
        field = ".".join(location) if location else "frontmatter"
        kind = error.get("type", "invalid")
        detail = str(error.get("msg", "invalid value"))

        if kind in {"missing", "value_error.missing"}:
            code = "missing_required_field"
            message = "required metadata field is missing"
        elif kind in {"date_parsing", "date_from_datetime_parsing", "date_type"}:
            code = "invalid_date"
            message = f"{field} must be an ISO-8601 date (YYYY-MM-DD)"
        elif kind in {"float_parsing", "int_parsing", "float_type", "finite_number"}:
            code = "invalid_confidence"
            message = f"{field} must be a number between 0.0 and 1.0"
        elif kind in {"string_type", "model_type", "list_type"}:
            code = "invalid_metadata"
            message = f"{field} has the wrong type: {detail}"
        else:
            code = "invalid_metadata"
            message = f"{field}: {detail}"

        issues.append(Issue(code=code, message=message, path=path, field=field))
    return issues or [Issue(code="invalid_metadata", message="invalid frontmatter", path=path)]


def assertion_to_markdown(assertion: Assertion) -> str:
    """Render an assertion back to canonical HCP Markdown.

    Round-tripping is lossless for everything the model knows about, and unknown
    metadata keys are preserved, so ``parse(render(a))`` yields an equivalent
    assertion.
    """
    metadata = assertion.metadata()
    metadata.pop("path", None)
    return dump_frontmatter(metadata, assertion.body)


def looks_like_assertion(text: str) -> bool:
    """Return ``True`` if ``text`` starts with a frontmatter delimiter.

    Used to distinguish assertion files from prose documents such as
    ``constitution.md`` and ``soul.md`` without hard-coding every filename.
    """
    cleaned = text[1:] if text.startswith("\ufeff") else text
    first = cleaned.splitlines()[0].strip() if cleaned.splitlines() else ""
    return first == "---"


__all__ = [
    "assertion_from_markdown",
    "assertion_to_markdown",
    "looks_like_assertion",
]
