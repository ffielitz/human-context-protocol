"""Codex manifest model (``manifest.yaml``).

The manifest is the entry point of a Codex: it declares the Codex identity,
version, locale, schema versions, and privacy defaults. Every other operation in
the CLI resolves a Codex by finding and reading this file first.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SchemaVersions(BaseModel):
    """Schema versions a Codex declares support for."""

    model_config = ConfigDict(extra="forbid")

    assertion: str = "0.1"
    bundle: str = "0.1"


class PrivacyDefaults(BaseModel):
    """Codex-wide privacy defaults."""

    model_config = ConfigDict(extra="allow")

    default_visibility: str = "private"
    """Visibility applied to new assertions when none is specified."""

    def unknown_fields(self) -> dict[str, Any]:
        """Return unknown privacy keys that must be preserved."""
        return dict(self.__pydantic_extra__ or {})


class Manifest(BaseModel):
    """A Codex manifest."""

    hcp: str = "0.1"
    codex_id: str
    title: str
    version: str = "0.1.0"
    created: date | None = None
    updated: date | None = None
    language: str | None = None
    timezone: str | None = None

    # 'schema' is the protocol field name, but BaseModel already defines
    # .schema(), so the attribute is renamed internally and aliased to the
    # wire name. Serialisation still emits 'schema'.
    schema_versions: SchemaVersions = Field(
        default_factory=SchemaVersions,
        alias="schema",
        serialization_alias="schema",
    )
    privacy: PrivacyDefaults | None = None
    features: dict[str, Any] | None = None

    path: str | None = None
    """Repository-relative path of the manifest, for diagnostics."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @field_validator("created", "updated", mode="before")
    @classmethod
    def _coerce_dates(cls, value: Any) -> Any:
        if value is None or isinstance(value, (date, datetime)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() in {"null", "none", "~", "yyyy-mm-dd"}:
                return None
            return text
        return value

    def unknown_fields(self) -> dict[str, Any]:
        """Return unknown manifest keys that must be preserved."""
        return dict(self.__pydantic_extra__ or {})

    @property
    def default_visibility(self) -> str:
        """Return the Codex-wide default visibility for new assertions."""
        return self.privacy.default_visibility if self.privacy else "private"

    def to_json_dict(self) -> dict[str, Any]:
        """Return the machine-readable representation of this manifest."""
        data: dict[str, Any] = {
            "hcp": self.hcp,
            "codex_id": self.codex_id,
            "title": self.title,
            "version": self.version,
        }
        for key in ("created", "updated"):
            value = getattr(self, key)
            data[key] = value.isoformat() if isinstance(value, date) else value
        for key in ("language", "timezone"):
            data[key] = getattr(self, key)
        data["schema"] = self.schema_versions.model_dump()
        if self.privacy is not None:
            data["privacy"] = self.privacy.model_dump(exclude_none=True)
        if self.features:
            data["features"] = dict(self.features)
        for key in sorted(self.unknown_fields()):
            if key not in data:
                data[key] = self.unknown_fields()[key]
        return data

    def to_yaml_dict(self) -> dict[str, Any]:
        """Return the mapping written back to ``manifest.yaml``."""
        data = self.to_json_dict()
        data.pop("hcp", None)
        return data


__all__ = ["Manifest", "PrivacyDefaults", "SchemaVersions"]
