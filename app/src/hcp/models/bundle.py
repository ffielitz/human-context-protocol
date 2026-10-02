"""Context Bundle model.

A Context Bundle is the only thing an AI system should receive. It is a
purpose-specific, scope-filtered, time-filtered, visibility-filtered projection
of a Codex, plus a mandatory human trust declaration defined by HCP-0002.

Trust rules enforced here (HCP-0002, docs/security-model.md)
-----------------------------------------------------------
* ``trust.status`` is always ``declared`` in a generated bundle. The generator is
  the human's side of the boundary and cannot speak for a receiver.
* ``trust_response`` is a *separate*, optional object. It may only be produced by
  a receiving adapter after comparing real capabilities against the declaration.
  ``compatible: true`` requires ``acknowledged: true``; reporting incompatibility
  honestly (``compatible: false`` with limitations) is explicitly valid.
* Neither the generator nor the CLI ever fabricates a receiver response.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..constants import HCP_VERSION, TRUST_COVENANT

#: The trust conditions defined by HCP-0002 section 5.
TRUST_CONDITION_NAMES: tuple[str, ...] = (
    "training",
    "derived_models",
    "human_review",
    "third_party_processing",
    "resale",
    "unauthorized_disclosure",
    "profiling",
    "manipulation",
)

#: Conservative default declaration, matching the example in HCP-0002 section 5.
DEFAULT_TRUST_CONDITIONS: dict[str, bool] = dict.fromkeys(TRUST_CONDITION_NAMES, False)

#: Polarity of the trust conditions, stated explicitly because HCP-0002 does not
#: define it normatively and the two readings are opposites.
#:
#: Implemented semantics: **a condition is a restriction the human imposes.**
#: ``training: false`` therefore reads "this context must not be used for
#: training". The safest value for every condition is ``false``, which is why
#: :meth:`TrustConditions.strict` returns the all-false declaration: it requests
#: the least invasive use of the shared context.
#:
#: The alternative reading (``false`` = "no restriction imposed") would make the
#: spec's own example a blanket permission, which contradicts the section's
#: description of it as "a non-negotiable set". If HCP-0008 later fixes the
#: opposite polarity, this is the single place to change it.
TRUST_CONDITION_POLARITY = "restriction"


class TrustConditions(BaseModel):
    """The human's declared conditions for use of this bundle."""

    model_config = ConfigDict(extra="forbid")

    training: bool = False
    derived_models: bool = False
    human_review: bool = False
    third_party_processing: bool = False
    resale: bool = False
    unauthorized_disclosure: bool = False
    profiling: bool = False
    manipulation: bool = False

    @classmethod
    def strict(cls) -> TrustConditions:
        """Return the default declaration prohibiting all listed conditions."""
        return cls(**DEFAULT_TRUST_CONDITIONS)

    def violations(self, guarantees: dict[str, bool]) -> list[str]:
        """Return declared restrictions that the receiver's guarantees break.

        Under the documented ``restriction`` polarity a condition is ``False``
        when the human forbids that use, and ``True`` when it is permitted. A
        receiver's guarantee says what the receiver will actually do. The two
        conflict when the human forbids a use that the receiver reports as
        happening, which is exactly what HCP-0002 requires to be disclosed
        rather than hidden behind an ``acknowledged: true``.
        """
        conflicts = []
        for name, prohibited in self.model_dump().items():
            permitted_by_human = not prohibited
            if permitted_by_human and guarantees.get(name, False):
                conflicts.append(name)
        return sorted(conflicts)


class TrustDeclaration(BaseModel):
    """The human's HCP-0002 declaration carried by every bundle."""

    model_config = ConfigDict(extra="forbid")

    covenant: str = TRUST_COVENANT
    status: str = "declared"
    conditions: TrustConditions = Field(default_factory=TrustConditions.strict)

    def to_json_dict(self) -> dict[str, Any]:
        """Return the declaration in wire form."""
        return {
            "covenant": self.covenant,
            "status": self.status,
            "conditions": self.conditions.model_dump(),
        }


class TrustResponse(BaseModel):
    """A receiving system's separate compatibility report.

    This object is never produced by the bundle generator. It exists so a future
    adapter (MCP server, provider integration) has a typed, schema-matching place
    to record what it can and cannot guarantee.
    """

    model_config = ConfigDict(extra="forbid")

    acknowledged: bool
    compatible: bool
    guarantees: TrustConditions = Field(default_factory=TrustConditions)
    limitations: list[str] = Field(default_factory=list)
    responded_at: datetime | None = None

    def validate_compatibility(self) -> None:
        """Raise :class:`ValueError` if the response contradicts HCP-0002."""
        if self.compatible and not self.acknowledged:
            raise ValueError("compatible: true requires acknowledged: true")
        if self.compatible and self.limitations:
            raise ValueError("compatible: true must not report limitations")


class ContextBundle(BaseModel):
    """A selective, purpose-specific export of a Codex."""

    model_config = ConfigDict(extra="allow")

    hcp: str = HCP_VERSION
    bundle_id: str
    codex_id: str
    purpose: str
    created: datetime
    expires: datetime | None = None
    scopes: list[str] = Field(default_factory=list)
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    integrity: dict[str, Any] = Field(default_factory=dict)
    trust: TrustDeclaration = Field(default_factory=TrustDeclaration)
    trust_response: TrustResponse | None = None

    def to_json_dict(self) -> dict[str, Any]:
        """Return the bundle in wire form with deterministic key ordering."""
        data: dict[str, Any] = {
            "hcp": self.hcp,
            "bundle_id": self.bundle_id,
            "codex_id": self.codex_id,
            "purpose": self.purpose,
            "created": _iso(self.created),
            "expires": _iso(self.expires),
            "scopes": list(self.scopes),
            "assertions": [dict(item) for item in self.assertions],
            "integrity": dict(self.integrity),
            "trust": self.trust.to_json_dict(),
        }
        if self.trust_response is not None:
            response = self.trust_response
            data["trust_response"] = {
                "acknowledged": response.acknowledged,
                "compatible": response.compatible,
                "guarantees": response.guarantees.model_dump(),
                "limitations": list(response.limitations),
                "responded_at": _iso(response.responded_at),
            }
        return data


def _iso(value: datetime | None) -> str | None:
    """Return a UTC ISO-8601 string for ``value``."""
    if value is None:
        return None
    return value.isoformat()


__all__ = [
    "DEFAULT_TRUST_CONDITIONS",
    "TRUST_CONDITION_NAMES",
    "ContextBundle",
    "TrustConditions",
    "TrustDeclaration",
    "TrustResponse",
]
