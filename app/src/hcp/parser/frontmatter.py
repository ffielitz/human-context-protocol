"""Deterministic YAML frontmatter parsing.

Security properties
-------------------
This module never evaluates YAML. It uses :class:`yaml.SafeLoader`, which
constructs only plain Python scalars, sequences, and mappings. Constructs such as
``!!python/object/apply`` therefore raise a :class:`yaml.YAMLError` instead of
executing code. That is the single most important guarantee in the parser: a
Codex is untrusted local input, possibly supplied by an AI adapter or imported
from someone else's machine.

The splitter is intentionally small and deterministic rather than a full
CommonMark implementation, because HCP frontmatter has a fixed shape:

1. optional UTF-8 BOM
2. a line containing exactly ``---``
3. the YAML mapping
4. a line containing exactly ``---``
5. the Markdown body
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from ..errors import DocumentError, Issue

#: The exact delimiter lines that bound frontmatter.
DELIMITER = "---"


@dataclass(frozen=True)
class Frontmatter:
    """A parsed frontmatter block and the Markdown body that follows it."""

    metadata: dict[str, Any]
    body: str
    raw: str
    """The original YAML text, kept so callers can re-serialise or diagnose."""


def _strip_bom(text: str) -> str:
    """Remove a leading UTF-8 byte-order mark if present."""
    return text[1:] if text.startswith("\ufeff") else text


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split ``text`` into ``(yaml_text, body)``.

    ``yaml_text`` is ``None`` when the document has no frontmatter block at all.
    An *unterminated* block (an opening ``---`` with no closing ``---``) is
    reported as an error by raising :class:`DocumentError`, because silently
    treating it as body text would hide a malformed assertion.

    Args:
        text: Full document text.

    Returns:
        A tuple of the frontmatter YAML source (``None`` when absent) and the
        remaining Markdown body.

    Raises:
        DocumentError: If the block is opened but never closed.
    """
    cleaned = _strip_bom(text)
    lines = cleaned.splitlines()

    if not lines or lines[0].strip() != DELIMITER:
        return None, cleaned

    for index in range(1, len(lines)):
        if lines[index].strip() == DELIMITER:
            raw = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :])
            return raw, body.lstrip("\n")

    raise DocumentError(
        [
            Issue(
                code="unterminated_frontmatter",
                message=(
                    "frontmatter starts with '---' but is never closed; add a closing '---' line"
                ),
            )
        ]
    )


def safe_load_yaml(raw: str, *, path: str | None = None) -> Any:
    """Parse YAML text with a safe loader.

    Args:
        raw: YAML source text.
        path: Repository-relative path used in error messages.

    Returns:
        The parsed object, normally a ``dict``.

    Raises:
        DocumentError: If the YAML is malformed, uses an unsafe construct, or
            does not describe a mapping.
    """
    try:
        data = yaml.load(raw, Loader=yaml.SafeLoader)
    except yaml.YAMLError as exc:
        detail = _clean_yaml_error(exc)
        raise DocumentError(
            [
                Issue(
                    code="malformed_yaml",
                    message=f"could not parse YAML frontmatter: {detail}",
                    path=path,
                )
            ]
        ) from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise DocumentError(
            [
                Issue(
                    code="frontmatter_not_mapping",
                    message=(
                        "frontmatter must be a YAML mapping of metadata keys, "
                        f"got {type(data).__name__}"
                    ),
                    path=path,
                )
            ]
        )
    return data


def _clean_yaml_error(exc: yaml.YAMLError) -> str:
    """Reduce a PyYAML exception to a single readable line."""
    message = str(exc).replace("\n", " ").strip()
    for marker in ("could not determine a constructor", "found undefined tag"):
        if marker in message:
            return (
                "frontmatter uses an unsupported or unsafe YAML tag; "
                "only plain scalars, lists, and mappings are allowed"
            )
    if "expected <block end>" in message or "mapping values are not allowed" in message:
        return "indentation or quoting error in frontmatter"
    return message[:300]


def parse_frontmatter(text: str, *, path: str | None = None) -> Frontmatter:
    """Parse a document that is expected to contain frontmatter.

    Args:
        text: Full document text.
        path: Repository-relative path used in error messages.

    Returns:
        The parsed :class:`Frontmatter`.

    Raises:
        DocumentError: If frontmatter is absent, unterminated, malformed, or
            not a mapping.
    """
    raw, body = split_frontmatter(text)
    if raw is None:
        raise DocumentError(
            [
                Issue(
                    code="missing_frontmatter",
                    message=(
                        "document has no YAML frontmatter; assertions must start "
                        "with a '---' line followed by metadata"
                    ),
                    path=path,
                )
            ]
        )
    metadata = safe_load_yaml(raw, path=path)
    return Frontmatter(metadata=metadata, body=body, raw=raw)


def dump_frontmatter(metadata: dict[str, Any], body: str) -> str:
    """Serialise metadata and body back into canonical HCP Markdown.

    The output is deterministic: keys keep their insertion order, indentation is
    two spaces, block style is used, and the body is separated by exactly one
    blank line. Values are dumped with ``allow_unicode`` so human content stays
    readable rather than being escaped.

    Args:
        metadata: Ordered metadata mapping.
        body: Markdown body.

    Returns:
        The full document text.
    """
    dumped = yaml.dump(
        metadata,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=1000,
    )
    stripped = body.strip("\n")
    if stripped:
        return f"{DELIMITER}\n{dumped}{DELIMITER}\n\n{stripped}\n"
    return f"{DELIMITER}\n{dumped}{DELIMITER}\n"


__all__ = [
    "DELIMITER",
    "Frontmatter",
    "dump_frontmatter",
    "parse_frontmatter",
    "safe_load_yaml",
    "split_frontmatter",
]
