"""Shared pytest fixtures.

Tests build throwaway Codex directories under ``tmp_path``; nothing ever touches
a user's real Codex, and every test runs fully offline.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from hcp.config import init_codex
from hcp.models.assertion import Assertion
from hcp.models.manifest import Manifest
from hcp.parser.markdown import assertion_from_markdown
from hcp.repository.codex import Codex

VALID_ASSERTION = """---
hcp: "0.1"
id: "value.honesty"
type: "value"
source: "human"
authority: "authoritative"
status: "active"
confidence: 1.0
created: "2024-01-01"
updated: "2024-01-01"
valid_from: "2024-01-01"
valid_until: null
visibility: "private"
tags:
  - core
---

I value honest assessment over comfortable agreement.
"""


@pytest.fixture
def codex_path(tmp_path: Path) -> Path:
    """Return an initialised, empty Codex directory."""
    root = tmp_path / "codex"
    init_codex(root, title="Test Codex", codex_id="codex.test", with_git=False)
    return root


@pytest.fixture
def codex(codex_path: Path) -> Codex:
    """Return a loaded, empty Codex."""
    return Codex.load(codex_path)


@pytest.fixture
def write_assertion(codex_path: Path):
    """Return a helper that writes raw Markdown into the Codex."""

    def _write(relative: str, content: str) -> Path:
        destination = codex_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return destination

    return _write


@pytest.fixture
def populated(codex_path: Path) -> Codex:
    """Return a Codex containing one valid human assertion."""
    target = codex_path / "values" / "honesty.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(VALID_ASSERTION, encoding="utf-8")
    return Codex.load(codex_path)


@pytest.fixture
def isolated_git_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Force Git commands to fail as if git were unavailable."""
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.delenv("GIT_DIR", raising=False)
    os.environ.pop("GIT_DIR", None)


def make_assertion(**overrides: object) -> Assertion:
    """Build an in-memory assertion with sensible defaults."""
    data: dict[str, object] = {
        "id": "value.honesty",
        "type": "value",
        "source": "human",
        "authority": "authoritative",
        "status": "active",
        "visibility": "private",
        "body": "Some text.",
    }
    data.update(overrides)
    return Assertion(**data)  # type: ignore[arg-type]


def parse(text: str, path: str = "values/honesty.md") -> Assertion:
    """Parse Markdown into an assertion."""
    return assertion_from_markdown(text, path=path)


__all__ = ["VALID_ASSERTION", "Manifest", "make_assertion", "parse"]
