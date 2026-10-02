"""Application configuration and Codex scaffolding.

Two responsibilities:

* :class:`AppConfig` resolves user-level defaults (default Codex location,
  timezone, output preferences) with environment overrides, keeping everything
  local and inspectable.
* :func:`init_codex` writes a new, valid, Git-friendly Codex from templates.

Nothing here touches the network. ``hcp init`` produces a directory that is
useful immediately and that a user can read, edit by hand, and commit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .constants import HCP_VERSION, MANIFEST_FILENAME, SCOPES_FILENAME
from .errors import UnsafePathError
from .ids import slugify
from .models.assertion import utc_today
from .repository.codex import DEFAULT_AREAS, PROSE_FILES, Codex
from .repository.files import safe_relative_path, write_text_file

#: Environment variable that overrides the default Codex path.
ENV_CODEX = "HCP_CODEX"

#: Environment variable that overrides the output format (``json`` or ``text``).
ENV_FORMAT = "HCP_FORMAT"

#: Conventional default Codex location relative to the home directory.
DEFAULT_CODEX_DIRNAME = "my-codex"


@dataclass
class AppConfig:
    """Resolved application-level configuration."""

    default_codex: Path
    output_format: str = "text"
    color: bool = True

    @classmethod
    def load(cls, env: dict[str, str] | None = None) -> AppConfig:
        """Build configuration from the environment, falling back to defaults.

        Args:
            env: Environment mapping; defaults to :data:`os.environ`.
        """
        environ = os.environ if env is None else env
        raw_codex = environ.get(ENV_CODEX) or str(Path.home() / DEFAULT_CODEX_DIRNAME)
        fmt = environ.get(ENV_FORMAT, "text").lower()
        return cls(
            default_codex=Path(raw_codex).expanduser(),
            output_format=fmt if fmt in {"text", "json"} else "text",
            color=environ.get("NO_COLOR") is None,
        )


# ----------------------------------------------------------------------
# Scaffolding
# ----------------------------------------------------------------------

_CONSTITUTION = """# Constitution

This document defines how my Codex should be interpreted.

## Authority

- Human-authored assertions are authoritative unless explicitly marked otherwise.
- AI observations are hypotheses until I accept or edit them.
- No AI observation may silently become an authoritative assertion.

## Uncertainty

- Do not represent uncertainty as certainty.
- Surface meaningful conflicts instead of silently resolving them.

## Privacy

- Restricted information must not be disclosed without explicit authorization.
- Credentials and secrets do not belong in the Codex.

## Time

- Prefer the newest assertion that is valid for the requested time.
- Preserve historical assertions when they explain how my views evolved.

## Interaction

- Use the Codex to improve assistance, not to stereotype or constrain me.
"""

_SOUL = """# Soul

This is intentionally unstructured.

Write here in your own words about the things that are difficult to reduce to
metadata: what matters, recurring themes, contradictions, aspirations, fears,
philosophy, aesthetics, or the way you want to live.

The schema describes the Codex. It does not define the whole person.
"""

_README = """# {title}

This Codex is yours. It is a local folder of Markdown files that you can read,
edit, back up, and share with any AI system you choose.

## Layout

```text
manifest.yaml     Codex identity and privacy defaults
constitution.md   how your Codex should be interpreted
soul.md           unstructured context, in your own words
scopes.yaml       which context each recipient may receive
identity/         who you are
values/           what you value
worldview/        what you believe
preferences/      how you like to be treated
relationships/    who matters
life/             work, goals, experience
ai/observations/  AI proposals awaiting your review
```

## Everyday use

```bash
hcp add . --type value --title "Intellectual honesty"
hcp validate .
hcp bundle . --scope assistant --purpose "Help me plan my week"
hcp review . obs.2026-01-01.example.001 --accept
hcp history .
```

Nothing leaves this folder unless you explicitly create a bundle and pass it
somewhere. The Codex belongs to you.
"""

_OBSERVATIONS_README = """# AI Observations

AI observations should normally be represented as individual assertion files so
that each observation has its own provenance, status, and review history.

Nothing in this folder is authoritative until you review it:

```bash
hcp review . <observation-id> --accept
hcp review . <observation-id> --edit --body "Corrected text"
hcp review . <observation-id> --reject
```
"""


def _manifest_yaml(
    *,
    codex_id: str,
    title: str,
    version: str,
    language: str,
    timezone_name: str,
    today: date,
    default_visibility: str,
) -> str:
    """Render a fresh ``manifest.yaml``."""
    import yaml

    data: dict[str, Any] = {
        "hcp": HCP_VERSION,
        "codex_id": codex_id,
        "title": title,
        "version": version,
        "created": today.isoformat(),
        "updated": today.isoformat(),
        "language": language,
        "timezone": timezone_name,
        "schema": {"assertion": HCP_VERSION, "bundle": HCP_VERSION},
        "privacy": {"default_visibility": default_visibility},
        "features": {
            "temporal_assertions": True,
            "ai_observations": True,
            "selective_disclosure": True,
        },
    }
    return yaml.dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=1000,
    )


def _scopes_yaml() -> str:
    """Render the default ``scopes.yaml``."""
    import yaml

    from .bundles.generator import DEFAULT_SCOPES

    data: dict[str, Any] = {"scopes": DEFAULT_SCOPES}
    return yaml.dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=1000,
    )


def init_codex(
    path: str | Path,
    *,
    title: str | None = None,
    codex_id: str | None = None,
    language: str = "en",
    timezone_name: str | None = None,
    default_visibility: str = "private",
    version: str = "0.1.0",
    force: bool = False,
    with_git: bool | None = None,
) -> tuple[Codex, list[str]]:
    """Create a new Codex directory and return it.

    Args:
        path: Directory to create. Must not already contain a manifest unless
            ``force`` is set.
        title: Human-readable Codex title.
        codex_id: Stable Codex identifier; derived from ``title`` when omitted.
        language: BCP-47 language tag.
        timezone_name: IANA timezone name.
        default_visibility: Default visibility for new assertions.
        version: Codex version string.
        force: Allow initialising in a non-empty directory.
        with_git: Initialise a Git repository. Defaults to True only when Git is
            available and the directory is not already inside a repository.

    Returns:
        The loaded :class:`Codex` and the list of created paths.

    Raises:
        UnsafePathError: If the target is occupied and ``force`` is not set.
    """
    root = Path(path).expanduser()

    # Accept the CLI's StrEnum option for --default-visibility, but persist a
    # plain string. Serialising the enum itself would emit a Python object tag,
    # which the safe loader correctly refuses to read back.
    visibility_value = str(default_visibility)

    if root.exists() and not root.is_dir():
        raise UnsafePathError(f"{root} exists and is not a directory")
    if (root / MANIFEST_FILENAME).exists() and not force:
        raise UnsafePathError(
            f"{root} already contains a Codex ({MANIFEST_FILENAME}); pass --force to reinitialise"
        )
    if root.exists() and any(root.iterdir()) and not force:
        raise UnsafePathError(f"{root} is not empty; pass --force to initialise anyway")

    root.mkdir(parents=True, exist_ok=True)
    resolved_title = title or root.resolve().name.replace("-", " ").replace("_", " ").title()
    resolved_id = codex_id or _default_codex_id(resolved_title)

    today = utc_today()
    created: list[str] = []

    manifest_text = _manifest_yaml(
        codex_id=resolved_id,
        title=resolved_title,
        version=version,
        language=language,
        timezone_name=timezone_name or _local_timezone(),
        today=today,
        default_visibility=visibility_value,
    )
    write_text_file(root / MANIFEST_FILENAME, manifest_text)
    created.append(MANIFEST_FILENAME)

    write_text_file(root / SCOPES_FILENAME, _scopes_yaml())
    created.append(SCOPES_FILENAME)

    write_text_file(root / "constitution.md", _CONSTITUTION)
    created.append("constitution.md")
    write_text_file(root / "soul.md", _SOUL)
    created.append("soul.md")
    write_text_file(root / "README.md", _README.format(title=resolved_title))
    created.append("README.md")

    for area in DEFAULT_AREAS:
        safe_relative_path(root, area).mkdir(parents=True, exist_ok=True)
        created.append(f"{area}/")
        if area == "ai":
            write_text_file(root / "ai" / "observations.md", _OBSERVATIONS_README)
            write_text_file(root / "ai" / "observations" / ".gitkeep", "")
            created.append("ai/observations/")

    write_text_file(root / ".gitignore", ".hcp-cache/\n*.tmp\n")

    _maybe_init_git(root, enabled=with_git)

    return Codex.load(root), created


def _default_codex_id(title: str) -> str:
    """Derive a Codex ID from a title, e.g. ``codex.my-codex``."""
    return f"codex.{slugify(title)}"


def _local_timezone() -> str:
    """Return the local IANA timezone name, or ``UTC`` when unavailable.

    Timezone detection is best effort only: a Codex may declare any valid zone,
    and a missing ``tzdata`` install must never break ``hcp init``.
    """
    try:
        local = datetime.now().astimezone().tzinfo
        name = getattr(local, "key", None)
        if isinstance(name, str) and name:
            return name
        return str(local) if local else "UTC"
    except Exception:  # noqa: BLE001 - never block initialisation
        return "UTC"


def _maybe_init_git(root: Path, *, enabled: bool | None) -> bool:
    """Optionally initialise a Git repository in a new Codex.

    Only ``git init`` is ever used. No file is staged, no commit is created, and
    no remote is configured: committing a Codex is an explicit human act.
    """
    import shutil
    import subprocess

    if enabled is False:
        return False
    if enabled is None and shutil.which("git") is None:
        return False
    if enabled is None and (root.parent / ".git").exists():
        return False
    if shutil.which("git") is None:
        return False

    try:
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "init", "--quiet", str(root)],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return True


__all__ = [
    "DEFAULT_CODEX_DIRNAME",
    "ENV_CODEX",
    "ENV_FORMAT",
    "PROSE_FILES",
    "AppConfig",
    "init_codex",
]
