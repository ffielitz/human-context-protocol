"""Tests for the read-only Git integration."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from hcp.errors import GitUnavailableError
from hcp.repository.git import (
    diff,
    history,
    is_git_repository,
    status,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def git_codex(codex_path: Path) -> Path:
    _git(codex_path, "init", "--quiet")
    _git(codex_path, "config", "user.email", "test@example.invalid")
    _git(codex_path, "config", "user.name", "HCP Test")
    return codex_path


def test_detects_repository(git_codex: Path) -> None:
    assert is_git_repository(git_codex)


def test_non_repository_is_handled(codex_path: Path) -> None:
    assert not is_git_repository(codex_path)
    state = status(codex_path)
    assert state.is_repository is False
    assert state.error


def test_status_of_empty_repository(git_codex: Path) -> None:
    state = status(git_codex)
    assert state.is_repository is True
    assert not state.clean


def test_history_on_empty_repository(git_codex: Path) -> None:
    assert history(git_codex) == []


def test_history_after_commit(git_codex: Path) -> None:
    _git(git_codex, "add", "-A")
    _git(git_codex, "commit", "-m", "Initial commit")
    commits = history(git_codex)
    assert len(commits) == 1
    assert commits[0].subject == "Initial commit"
    assert commits[0].short_hash


def test_status_reports_changes(git_codex: Path) -> None:
    _git(git_codex, "add", "-A")
    _git(git_codex, "commit", "-m", "Initial commit")
    target = git_codex / "values" / "new.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("---\nid: value.new\n---\n\nX\n", encoding="utf-8")
    # Git collapses an untracked directory into a single '?? dir/' entry, so add
    # the file first to observe the file itself being reported as modified.
    _git(git_codex, "add", str(target))
    target.write_text("---\nid: value.new\n---\n\nChanged\n", encoding="utf-8")

    state = status(git_codex)
    assert not state.clean
    assert any("new.md" in entry.path for entry in state.entries)


def test_status_reports_untracked_files(git_codex: Path) -> None:
    _git(git_codex, "add", "-A")
    _git(git_codex, "commit", "-m", "Initial commit")
    (git_codex / "values" / "fresh.md").write_text("---\nid: value.f\n---\n\nX\n", encoding="utf-8")
    state = status(git_codex)
    assert not state.clean
    assert any("values/" in entry.path for entry in state.entries)


def test_diff_shows_changes(git_codex: Path) -> None:
    _git(git_codex, "add", "-A")
    _git(git_codex, "commit", "-m", "Initial commit")
    target = git_codex / "values" / "new.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("---\nid: value.new\n---\n\nX\n", encoding="utf-8")
    _git(git_codex, "add", str(target))
    target.write_text("---\nid: value.new\n---\n\nChanged\n", encoding="utf-8")
    text = diff(git_codex)
    assert "new.md" in text
    assert "Changed" in text


def test_diff_includes_untracked_files(git_codex: Path) -> None:
    """A brand-new assertion is untracked; `hcp diff` must still show it."""
    _git(git_codex, "add", "-A")
    _git(git_codex, "commit", "-m", "Initial commit")
    (git_codex / "values" / "fresh.md").write_text(
        "---\nid: value.fresh\n---\n\nBrand new assertion.\n", encoding="utf-8"
    )
    text = diff(git_codex)
    assert "fresh.md" in text
    assert "Brand new assertion." in text
    assert "untracked" in text


def test_diff_of_clean_tree_is_empty(git_codex: Path) -> None:
    _git(git_codex, "add", "-A")
    _git(git_codex, "commit", "-m", "Initial commit")
    assert diff(git_codex).strip() == ""


def test_history_limit(git_codex: Path) -> None:
    _git(git_codex, "add", "-A")
    _git(git_codex, "commit", "-m", "First")
    (git_codex / "second.txt").write_text("x", encoding="utf-8")
    _git(git_codex, "add", "-A")
    _git(git_codex, "commit", "-m", "Second")
    assert len(history(git_codex, limit=1)) == 1


def test_git_integration_is_read_only(git_codex: Path) -> None:
    """Reading status/history/diff must never modify the repository."""
    _git(git_codex, "add", "-A")
    _git(git_codex, "commit", "-m", "Initial commit")
    before = status(git_codex)
    head_before = subprocess.run(
        ["git", "-C", str(git_codex), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    history(git_codex)
    diff(git_codex)
    status(git_codex)

    head_after = subprocess.run(
        ["git", "-C", str(git_codex), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head_before == head_after
    assert before.branch == status(git_codex).branch


def test_history_without_git_raises(monkeypatch: pytest.MonkeyPatch, git_codex: Path) -> None:
    monkeypatch.setattr("hcp.repository.git._git_available", lambda: False)
    with pytest.raises(GitUnavailableError):
        history(git_codex)


def test_status_without_git_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, git_codex: Path
) -> None:
    monkeypatch.setattr("hcp.repository.git._git_available", lambda: False)
    state = status(git_codex)
    assert state.is_repository is False
    assert "not installed" in (state.error or "")
