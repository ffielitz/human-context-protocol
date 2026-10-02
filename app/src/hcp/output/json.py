"""Stable JSON serialisation for a Codex.

The JSON representation is *derived* data (HCP-0001 section 21). It must never
replace the canonical Markdown, and it must be stable enough for adapters to
diff. Guarantees:

* UTF-8 output, ``ensure_ascii=False`` so human content stays readable
* deterministic key ordering (metadata order, then unknown keys sorted)
* dates as ISO-8601 strings, never Python objects
* the assertion body and provenance are always preserved
* no secrets are injected and nothing is fetched from the network
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from ..constants import HCP_VERSION
from ..repository.codex import Codex

#: Number of spaces used for indentation in the default JSON output.
INDENT = 2


def to_jsonable(value: Any) -> Any:
    """Recursively convert a value into JSON-serialisable primitives.

    ``date`` and ``datetime`` become ISO-8601 strings. Unknown objects fall back
    to their string representation rather than raising, so a single odd metadata
    value cannot break an export.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump())
    return str(value)


def dumps(data: Any, *, indent: int | None = INDENT, sort_keys: bool = False) -> str:
    """Serialise ``data`` to a deterministic JSON string."""
    return json.dumps(
        to_jsonable(data),
        indent=indent,
        ensure_ascii=False,
        sort_keys=sort_keys,
        separators=(",", ": ") if indent is not None else (",", ":"),
    )


def codex_to_dict(
    codex: Codex,
    *,
    include_prose: bool = True,
    include_pending: bool = True,
) -> dict[str, Any]:
    """Build the normalized JSON representation of a whole Codex.

    Args:
        codex: The loaded Codex.
        include_prose: Include ``constitution.md`` and ``soul.md`` content.
        include_pending: Include observations that are still pending review.
            Pending material is included with its ``status`` intact so a
            consumer can see what was proposed; the validator and the bundle
            generator are what enforce authority.

    Returns:
        An ordered, JSON-ready mapping.
    """
    assertions = list(codex.assertions)
    if not include_pending:
        assertions = [a for a in assertions if not a.is_pending]

    payload: dict[str, Any] = {
        "hcp": HCP_VERSION,
        "kind": "codex",
        "codex_id": codex.manifest.codex_id,
        "title": codex.manifest.title,
        "version": codex.manifest.version,
        "manifest": codex.manifest.to_json_dict(),
        "assertion_count": len(assertions),
        "assertions": [a.to_json_dict() for a in assertions],
    }

    if include_prose:
        payload["documents"] = {
            name: {"path": name, "content": content}
            for name, content in sorted(codex.prose.items())
        }

    return payload


def export_codex(
    codex: Codex,
    *,
    include_prose: bool = True,
    include_pending: bool = True,
    indent: int | None = INDENT,
) -> str:
    """Return the JSON export of a Codex as a string.

    The result is byte-identical for identical repository contents, which makes
    it usable in tests and for reproducible adapter handshakes.
    """
    return dumps(
        codex_to_dict(codex, include_prose=include_prose, include_pending=include_pending),
        indent=indent,
    )


def write_export(codex: Codex, destination, **kwargs: Any) -> str:
    """Write the JSON export to ``destination`` and return the text written."""
    from pathlib import Path

    path = Path(destination)
    text = export_codex(codex, **kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return text


__all__ = [
    "INDENT",
    "codex_to_dict",
    "dumps",
    "export_codex",
    "to_jsonable",
    "write_export",
]
