"""HCP — Human Context Protocol reference implementation.

The human owns the context. AI systems consume it.

This package provides a local-first implementation of HCP: a typed data model,
a safe Markdown + YAML frontmatter parser, a Codex repository layer, validation,
selective Context Bundle generation, and an AI observation workflow with an
explicit human authority transition.

Everything in the core works offline. AI integrations are adapters that live
outside this package and consume Context Bundles; there is intentionally no
unrestricted ``dump_everything`` entry point.
"""

from __future__ import annotations

from .bundles.generator import Scope, ScopeConfig, generate_bundle, load_scopes
from .config import AppConfig, init_codex
from .constants import APP_VERSION, HCP_VERSION, TRUST_COVENANT
from .errors import (
    AssertionExistsError,
    AssertionNotFoundError,
    CodexNotFoundError,
    HCPError,
    Issue,
    ManifestMissingError,
    ObservationError,
    ScopeConfigError,
    Severity,
    UnsafePathError,
)
from .ids import id_problem, is_valid_id, suggest_id
from .models.assertion import Assertion, Provenance, utc_today
from .models.bundle import ContextBundle, TrustConditions, TrustDeclaration, TrustResponse
from .models.manifest import Manifest
from .observations.workflow import ingest_observation, list_observations, review_observation
from .output.json import codex_to_dict, export_codex
from .parser.markdown import assertion_from_markdown, assertion_to_markdown
from .repository.codex import Codex
from .validation.validator import ValidationReport, validate_codex

__version__ = APP_VERSION

__all__ = [
    "APP_VERSION",
    "HCP_VERSION",
    "TRUST_COVENANT",
    "AppConfig",
    "Assertion",
    "AssertionExistsError",
    "AssertionNotFoundError",
    "Codex",
    "CodexNotFoundError",
    "ContextBundle",
    "HCPError",
    "Issue",
    "Manifest",
    "ManifestMissingError",
    "ObservationError",
    "Provenance",
    "Scope",
    "ScopeConfig",
    "ScopeConfigError",
    "Severity",
    "TrustConditions",
    "TrustDeclaration",
    "TrustResponse",
    "UnsafePathError",
    "ValidationReport",
    "__version__",
    "assertion_from_markdown",
    "assertion_to_markdown",
    "codex_to_dict",
    "export_codex",
    "generate_bundle",
    "id_problem",
    "ingest_observation",
    "init_codex",
    "is_valid_id",
    "list_observations",
    "load_scopes",
    "review_observation",
    "suggest_id",
    "utc_today",
    "validate_codex",
]
