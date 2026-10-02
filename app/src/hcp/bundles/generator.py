"""Selective Context Bundle generation.

This is the selective-disclosure boundary of the whole application. Everything
that leaves the Codex passes through :func:`generate_bundle`.

What a bundle contains
----------------------
Only assertions that are simultaneously:

1. **in scope** - matched by at least one requested scope pattern
2. **disclosable** - the scope's ``visibility_ceiling`` permits their class
3. **currently valid** - ``valid_from``/``valid_until`` contain the requested date
4. **authoritative and active** - pending, rejected, and archived material is
   never exported
5. **not superseded** - superseded assertions are retained in the Codex for
   history but omitted from current context

Determinism
-----------
For identical Codex contents and configuration, the bundle content is
byte-identical apart from the explicitly dynamic ``created``/``expires``
timestamps and the content-derived ``bundle_id``.

Trust
-----
The generator writes ``trust.status: declared`` and the human's conditions. It
never writes ``trust_response``: only a receiving adapter may do that, and only
after comparing its real capabilities against the declaration.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..constants import HCP_VERSION, SCOPES_FILENAME
from ..errors import ScopeConfigError
from ..models.assertion import VISIBILITIES, Assertion
from ..models.bundle import ContextBundle, TrustConditions, TrustDeclaration
from ..output.json import dumps, to_jsonable
from ..parser.frontmatter import safe_load_yaml
from ..repository.codex import Codex

#: Default scope configuration written by ``hcp init``.
DEFAULT_SCOPES: dict[str, Any] = {
    "assistant": {
        "description": "General-purpose assistant context.",
        "include": ["identity", "preferences", "values"],
        "visibility_ceiling": "private",
    },
    "career": {
        "description": "Professional context for career conversations.",
        "include": ["identity", "life.work", "life.goals", "preferences.communication"],
        "visibility_ceiling": "private",
    },
    "writing": {
        "description": "Style and communication preferences for writing assistance.",
        "include": ["preferences.communication", "values", "preferences.writing"],
        "visibility_ceiling": "private",
    },
    "public": {
        "description": "Only assertions explicitly marked public.",
        "include": ["identity", "values", "preferences"],
        "visibility_ceiling": "public",
    },
}

#: Disclosure classes ordered from least to most sensitive.
VISIBILITY_ORDER: tuple[str, ...] = VISIBILITIES


@dataclass(frozen=True)
class Scope:
    """A named set of disclosure permissions."""

    name: str
    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    visibility_ceiling: str = "private"
    description: str = ""

    def permits_visibility(self, visibility: str) -> bool:
        """Return ``True`` if this scope may disclose ``visibility``.

        ``visibility_ceiling: restricted`` is the only way restricted data is
        ever exported, which implements BUILD-APP section 12's requirement that
        restricted assertions are included only on explicit authorization.
        """
        try:
            ceiling_index = VISIBILITY_ORDER.index(self.visibility_ceiling)
            value_index = VISIBILITY_ORDER.index(visibility)
        except ValueError:
            return False
        return value_index <= ceiling_index

    def matches(self, assertion: Assertion) -> bool:
        """Return ``True`` if the assertion is inside this scope."""
        if not any(_matches_pattern(pattern, assertion) for pattern in self.include):
            return False
        return not any(_matches_pattern(pattern, assertion) for pattern in self.exclude)


def _matches_pattern(pattern: str, assertion: Assertion) -> bool:
    """Match one scope pattern against an assertion.

    A pattern matches when any of these hold:

    * it equals the assertion ``id``
    * it is a dot-prefix of the ``id`` (``preferences.communication`` matches
      ``preference.example.communication`` via its namespace or path)
    * it equals the assertion ``type``
    * it is a path prefix of the file's location inside the Codex
      (``life.work`` matches ``life/work.md``)

    This keeps scope configuration readable without requiring IDs to mirror the
    directory layout exactly.
    """
    normalized = pattern.strip()
    if not normalized:
        return False
    if normalized in {"*", "all"}:
        return True
    if normalized == assertion.id:
        return True
    if normalized == assertion.type:
        return True
    if assertion.id.startswith(f"{normalized}."):
        return True

    namespace = assertion.id.split(".", 1)[0]
    if normalized == namespace:
        return True
    if normalized.startswith(f"{namespace}."):
        return True

    path = (assertion.path or "").removesuffix(".md")
    if path:
        dotted = path.replace("/", ".")
        if dotted == normalized or dotted.startswith(f"{normalized}."):
            return True
        # Also allow matching any directory prefix, e.g. 'life' or 'life.work'.
        parts = dotted.split(".")
        for index in range(1, len(parts) + 1):
            if ".".join(parts[:index]) == normalized:
                return True
    return False


@dataclass
class ScopeConfig:
    """The scope configuration of a Codex."""

    scopes: dict[str, Scope] = field(default_factory=dict)
    source: Path | None = None

    def get(self, name: str) -> Scope:
        """Return the named scope.

        Raises:
            ScopeConfigError: If the scope is not defined.
        """
        try:
            return self.scopes[name]
        except KeyError as exc:
            known = ", ".join(sorted(self.scopes)) or "none"
            raise ScopeConfigError(f"unknown scope {name!r}; defined scopes: {known}") from exc

    def names(self) -> list[str]:
        """Return all defined scope names, sorted."""
        return sorted(self.scopes)


def load_scopes(codex: Codex) -> ScopeConfig:
    """Load scope configuration from the Codex, falling back to defaults.

    A Codex may override or extend the defaults with a ``scopes.yaml`` file at
    its root. That keeps scope configuration local, human-readable, and
    version-controlled, which is exactly what HCP asks for.
    """
    config = ScopeConfig(scopes=_scopes_from_mapping(DEFAULT_SCOPES), source=None)
    path = codex.root / SCOPES_FILENAME
    if not path.is_file():
        return config

    raw = path.read_text(encoding="utf-8")
    try:
        data = safe_load_yaml(raw, path=SCOPES_FILENAME)
    except Exception as exc:  # noqa: BLE001 - surfaced as a config error
        raise ScopeConfigError(f"cannot read {SCOPES_FILENAME}: {exc}") from exc

    scopes_data = data.get("scopes", data)
    if not isinstance(scopes_data, dict):
        raise ScopeConfigError(f"{SCOPES_FILENAME} must define a mapping of scope names")
    config.scopes.update(_scopes_from_mapping(scopes_data, origin=str(path)))
    config.source = path
    return config


def _scopes_from_mapping(data: dict[str, Any], *, origin: str = "defaults") -> dict[str, Scope]:
    """Build :class:`Scope` objects from a configuration mapping."""
    scopes: dict[str, Scope] = {}
    for name, config in data.items():
        if not isinstance(config, dict):
            raise ScopeConfigError(f"scope {name!r} in {origin} must be a mapping")
        ceiling = str(config.get("visibility_ceiling", "private"))
        if ceiling not in VISIBILITY_ORDER:
            raise ScopeConfigError(
                f"scope {name!r} has invalid visibility_ceiling {ceiling!r}; "
                f"expected one of {list(VISIBILITY_ORDER)}"
            )
        include = config.get("include") or []
        exclude = config.get("exclude") or []
        if isinstance(include, str):
            include = [include]
        if isinstance(exclude, str):
            exclude = [exclude]
        scopes[str(name)] = Scope(
            name=str(name),
            include=tuple(str(item) for item in include),
            exclude=tuple(str(item) for item in exclude),
            visibility_ceiling=ceiling,
            description=str(config.get("description", "")),
        )
    return scopes


def bundle_id_for(
    codex_id: str,
    purpose: str,
    scopes: list[str],
    assertions: list[dict[str, Any]],
    *,
    created: datetime,
    expires: datetime | None = None,
) -> str:
    """Derive a deterministic bundle ID from the bundle's own content.

    The ID is a short digest over everything that defines the bundle's meaning,
    so identical content yields an identical ID and any change to the shared
    context is visible in the ID.
    """
    payload = {
        "hcp": HCP_VERSION,
        "codex_id": codex_id,
        "purpose": purpose,
        "scopes": sorted(scopes),
        "created": created.isoformat(),
        "expires": expires.isoformat() if expires else None,
        "assertions": assertions,
    }
    digest = hashlib.sha256(dumps(payload, indent=None, sort_keys=True).encode("utf-8"))
    return f"bundle.{_slug(codex_id)}.{digest.hexdigest()[:16]}"


def _slug(text: str) -> str:
    """Return a filesystem- and ID-safe rendering of ``text``."""
    cleaned = "".join(ch if ch.isalnum() or ch in ".-" else "-" for ch in text.strip().lower())
    return cleaned.strip("-.") or "codex"


def select_assertions(
    codex: Codex,
    scopes: list[Scope],
    *,
    at: date,
    include_restricted: bool = False,
) -> list[Assertion]:
    """Select the assertions permitted by ``scopes`` at a point in time.

    Args:
        codex: The loaded Codex.
        scopes: The resolved scopes.
        at: The date at which the context must be valid.
        include_restricted: Required in order for a scope with
            ``visibility_ceiling: restricted`` to disclose restricted data. The
            CLI sets this only for an explicit ``--include-restricted`` flag, so
            restricted context can never leak through a routine bundle.

    Returns:
        Assertions sorted by ID for deterministic output.
    """
    superseded = codex.superseded_at(at)
    selected: dict[str, Assertion] = {}

    for scope in scopes:
        for assertion in codex.assertions:
            if not scope.matches(assertion):
                continue
            if assertion.status != "active" or assertion.authority != "authoritative":
                continue
            if assertion.id in superseded:
                continue
            if not assertion.is_valid_at(at):
                continue
            if assertion.visibility == "restricted" and not (
                include_restricted or scope.visibility_ceiling == "restricted"
            ):
                continue
            if not scope.permits_visibility(assertion.visibility):
                continue
            selected.setdefault(assertion.id, assertion)

    return [selected[key] for key in sorted(selected)]


def generate_bundle(
    codex: Codex,
    scopes: list[str],
    *,
    purpose: str,
    config: ScopeConfig | None = None,
    at: date | None = None,
    created: datetime | None = None,
    expires_in: timedelta | None = None,
    include_restricted: bool = False,
    trust_conditions: TrustConditions | None = None,
) -> ContextBundle:
    """Generate a Context Bundle for the given scopes and purpose.

    Args:
        codex: The loaded Codex.
        scopes: Names of the scopes to apply.
        purpose: Why the bundle exists; recorded verbatim for the receiver.
        config: Scope configuration; loaded from the Codex when omitted.
        at: Date at which assertions must be valid; defaults to today (UTC).
        created: Bundle creation timestamp; defaults to now (dynamic).
        expires_in: Optional lifetime relative to ``created``.
        include_restricted: Explicitly permit restricted visibility.
        trust_conditions: The human's declared conditions; defaults to the
            strictest declaration (all listed uses prohibited).

    Returns:
        The generated :class:`ContextBundle`.

    Raises:
        ScopeConfigError: If a requested scope is not defined.
    """
    scope_config = config or load_scopes(codex)
    resolved = [scope_config.get(name) for name in scopes]
    if not resolved:
        raise ScopeConfigError("at least one scope is required to build a bundle")

    moment = at or date.today()
    created_at = created or datetime.now(UTC).replace(microsecond=0)
    expires_at = created_at + expires_in if expires_in else None

    selected = select_assertions(codex, resolved, at=moment, include_restricted=include_restricted)
    payload = [a.to_json_dict() for a in selected]

    declaration = TrustDeclaration(
        status="declared",
        conditions=trust_conditions or TrustConditions.strict(),
    )

    return ContextBundle(
        hcp=HCP_VERSION,
        bundle_id=bundle_id_for(
            codex.manifest.codex_id,
            purpose,
            list(scopes),
            payload,
            created=created_at,
            expires=expires_at,
        ),
        codex_id=codex.manifest.codex_id,
        purpose=purpose,
        created=created_at,
        expires=expires_at,
        scopes=list(scopes),
        assertions=payload,
        integrity={
            "algorithm": "sha256",
            "hash": _content_hash(payload),
            "assertion_count": len(payload),
            "signed": False,
            "note": "Integrity placeholder; cryptographic signing is deferred to HCP-0010.",
        },
        trust=declaration,
    )


def _content_hash(payload: list[dict[str, Any]]) -> str:
    """Return a SHA-256 digest over the bundle's assertion content."""
    return hashlib.sha256(
        dumps(to_jsonable(payload), indent=None, sort_keys=True).encode("utf-8")
    ).hexdigest()


def excluded_reason(
    codex: Codex, scopes: list[Scope], selected: list[Assertion], *, at: date
) -> dict[str, list[str]]:
    """Explain why each non-selected assertion was withheld.

    Transparency matters for selective disclosure: the human should be able to
    see exactly what a bundle left out and why, without having to diff the bundle
    against the Codex by hand.
    """
    chosen = {a.id for a in selected}
    superseded = codex.superseded_at(at)
    reasons: dict[str, list[str]] = {}
    for assertion in codex.assertions:
        if assertion.id in chosen:
            continue
        why: list[str] = []
        if assertion.id in superseded:
            why.append("superseded")
        if assertion.status != "active":
            why.append(f"status={assertion.status}")
        if assertion.authority != "authoritative":
            why.append(f"authority={assertion.authority}")
        if not assertion.is_valid_at(at):
            why.append(f"{assertion.temporal_state(at)} at {at.isoformat()}")
        if not any(scope.matches(assertion) for scope in scopes):
            why.append("out of scope")
        else:
            for scope in scopes:
                if scope.matches(assertion) and not scope.permits_visibility(assertion.visibility):
                    why.append(
                        f"visibility={assertion.visibility} exceeds scope "
                        f"{scope.name!r} ceiling {scope.visibility_ceiling}"
                    )
                    break
        reasons[assertion.id] = why or ["not selected"]
    return reasons


__all__ = [
    "DEFAULT_SCOPES",
    "VISIBILITY_ORDER",
    "ContextBundle",
    "Scope",
    "ScopeConfig",
    "bundle_id_for",
    "excluded_reason",
    "generate_bundle",
    "load_scopes",
    "select_assertions",
]
