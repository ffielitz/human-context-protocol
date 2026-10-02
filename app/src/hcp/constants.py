"""Constants and version information for the HCP implementation."""

from __future__ import annotations

from typing import Final

#: The HCP specification version implemented by this package.
HCP_VERSION: Final[str] = "0.1"

#: The application version.
APP_VERSION: Final[str] = "0.1.0"

#: The trust covenant implemented by the bundle generator.
TRUST_COVENANT: Final[str] = "HCP-0002"

#: Filename of the Codex manifest inside a Codex repository.
MANIFEST_FILENAME: Final[str] = "manifest.yaml"

#: Optional per-Codex scope configuration written by ``hcp scopes``.
SCOPES_FILENAME: Final[str] = "scopes.yaml"

#: Directory holding AI-generated observations awaiting human review.
OBSERVATIONS_DIR: Final[str] = "ai/observations"

#: Human-authored free-form documents that are not assertions. These carry
#: prose only and are never expected to have frontmatter.
PROSE_DOCUMENTS: Final[tuple[str, ...]] = (
    "constitution.md",
    "soul.md",
    "README.md",
    "readme.md",
    "ai/observations.md",
    "ai/questions.md",
    "ai/rejected.md",
    "CHANGELOG.md",
    "LICENSE",
)

#: Top-level files and directories that never contain assertions.
RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".hcp",
        ".github",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".DS_Store",
    }
)

#: Maximum size of a single Markdown file that will be parsed (1 MiB).
MAX_FILE_BYTES: Final[int] = 1024 * 1024

__all__ = [
    "APP_VERSION",
    "HCP_VERSION",
    "MANIFEST_FILENAME",
    "MAX_FILE_BYTES",
    "OBSERVATIONS_DIR",
    "PROSE_DOCUMENTS",
    "RESERVED_NAMES",
    "SCOPES_FILENAME",
    "TRUST_COVENANT",
]
