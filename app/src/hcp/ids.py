"""Assertion ID rules.

The specification deliberately leaves the exact ID grammar to a future RFC
(HCP-0003/HCP-0004). This module implements the smallest rule that satisfies the
examples in ``prompts/BUILD-APP.md`` and documents it precisely so it can be
promoted to a normative spec later.

Implemented rule (HCP-0001 ``v0.1``)
----------------------------------
An assertion ID is a dot-separated path of at least two segments::

    <segment> ("." <segment>)+

where each segment matches ``[a-z0-9]+(-[a-z0-9]+)*``:

* lowercase ASCII letters, digits and inner hyphens only
* no leading/trailing hyphen, no double hyphen, no underscores, no spaces
* at least one dot, so every ID carries a namespace (``belief``, ``value``, ``obs``)

This accepts all documented examples::

    belief.ai.human-agency
    preference.communication.direct
    goal.project.hcp
    obs.2026-09-11.communication.001

and rejects unsafe or ambiguous identifiers such as ``No Spaces``, ``../escape``,
``UPPER.case`` and ``nodots``.

A Codex ID uses the same grammar, which is why ``codex.example.minimal`` is a
valid manifest identifier.

The first segment acts as the assertion's *namespace* and is expected to match
the assertion ``type`` for human-authored assertions. The validator reports a
warning rather than an error when it does not, because the specification does not
mandate it and imported material may legitimately differ.
"""

from __future__ import annotations

import re

_SEGMENT = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_ID_RE = re.compile(rf"^{_SEGMENT}(?:\.{_SEGMENT})+$")
_SEGMENT_ONLY_RE = re.compile(rf"^{_SEGMENT}$")
_MAX_ID_LENGTH = 200


def is_valid_id(value: str) -> bool:
    """Return ``True`` if ``value`` is a syntactically valid HCP ID."""
    if not isinstance(value, str):
        return False
    if not value or len(value) > _MAX_ID_LENGTH:
        return False
    return bool(_ID_RE.match(value))


def is_valid_segment(value: str) -> bool:
    """Return ``True`` if ``value`` is a single valid ID segment."""
    if not isinstance(value, str):
        return False
    return bool(_SEGMENT_ONLY_RE.match(value))


def namespace_of(value: str) -> str:
    """Return the first segment of an ID, i.e. its namespace."""
    if not is_valid_id(value):
        raise ValueError(f"not a valid HCP ID: {value!r}")
    return value.split(".", 1)[0]


def id_problem(value: str) -> str | None:
    """Return a human-readable reason why ``value`` is not a valid ID, if any."""
    if not isinstance(value, str):
        return "id must be a string"
    if not value:
        return "id must not be empty"
    if len(value) > _MAX_ID_LENGTH:
        return f"id must be at most {_MAX_ID_LENGTH} characters"
    if ".." in value:
        return "id must not contain empty segments"
    if value.strip() != value:
        return "id must not have leading or trailing whitespace"
    if "." not in value:
        return "id must contain at least one dot separating namespace and name"
    if any(ch.isspace() for ch in value):
        return "id must not contain whitespace"
    if "/" in value or "\\" in value:
        return "id must not contain path separators"
    if value.startswith("-"):
        return "id segments must not start with a hyphen"
    invalid = [seg for seg in value.split(".") if not is_valid_segment(seg)]
    if invalid:
        return f"id segments must match [a-z0-9]+(-[a-z0-9]+)* (offending segment: {invalid[0]!r})"
    return None


def slugify(text: str) -> str:
    """Convert free text into a valid ID segment.

    Used by ``hcp add`` to build a suggestion from ``--title`` when the user
    does not supply an explicit ID.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "untitled"


def suggest_id(type_: str, title: str | None = None, taken: set[str] | None = None) -> str:
    """Build a deterministic, unique ID suggestion for a new assertion.

    The namespace is the assertion type and the name is the slugified title. When
    no title is available, the name falls back to ``example`` so the result is
    still a valid namespaced ID; a numeric suffix is appended when the
    suggestion is already taken.

    Args:
        type_: The assertion type, used as the namespace.
        title: Optional human title to slugify into the name.
        taken: IDs already in use; used to keep the suggestion unique.

    Returns:
        A syntactically valid, unused assertion ID.
    """
    taken = taken or set()
    namespace = type_ if is_valid_segment(type_) else "fact"
    name = slugify(title) if title and title.strip() else "example"
    base = f"{namespace}.{name}"
    candidate = base
    counter = 2
    while candidate in taken:
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


__all__ = [
    "id_problem",
    "is_valid_id",
    "is_valid_segment",
    "namespace_of",
    "slugify",
    "suggest_id",
]
