"""Read-only Git integration.

Git is a first-class part of the HCP data model (HCP-0001 section 11): it provides
history, diffs, rollback, and provenance. This module therefore only ever *reads*.
It never commits, stages, checks out, resets, rebases, or rewrites history, and
it never contacts a remote. A user reviewing their own context should be able to
trust that running ``hcp status`` cannot change anything.

All commands are invoked with an explicit ``-C <codex>`` and with the pager and
optional locks disabled so the output is deterministic and side-effect free.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import GitUnavailableError

#: Timeout for any single git invocation, in seconds.
GIT_TIMEOUT = 30


@dataclass(frozen=True)
class GitCommit:
    """A single commit in the Codex history."""

    hash: str
    short_hash: str
    author: str
    date: str
    subject: str


@dataclass(frozen=True)
class GitStatusEntry:
    """One changed path in the working tree."""

    status: str
    path: str


@dataclass(frozen=True)
class GitStatus:
    """A read-only snapshot of the Codex working tree."""

    is_repository: bool
    branch: str | None = None
    entries: list[GitStatusEntry] = field(default_factory=list)
    error: str | None = None

    @property
    def clean(self) -> bool:
        """Return ``True`` when there are no local modifications."""
        return not self.entries


def _git_available() -> bool:
    """Return ``True`` if a ``git`` binary is on PATH."""
    return shutil.which("git") is not None


def _run_git(codex_root, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a read-only git command inside ``codex_root``."""
    if not _git_available():
        raise GitUnavailableError("the 'git' binary is not available on PATH")
    command = [
        "git",
        "-C",
        str(codex_root),
        "--no-pager",
        "-c",
        "core.pager=cat",
        "-c",
        "color.ui=never",
        *args,
    ]
    try:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitUnavailableError(f"git command timed out: {' '.join(args)}") from exc
    except OSError as exc:  # pragma: no cover - defensive
        raise GitUnavailableError(f"could not run git: {exc}") from exc


def is_git_repository(codex_root) -> bool:
    """Return ``True`` if ``codex_root`` is inside a Git working tree."""
    if not _git_available():
        return False
    result = _run_git(codex_root, ["rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0 and result.stdout.strip() == "true"


def current_branch(codex_root) -> str | None:
    """Return the checked-out branch name, or ``None`` when detached."""
    result = _run_git(codex_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return None if branch in {"", "HEAD"} else branch


def status(codex_root) -> GitStatus:
    """Return a read-only status of the Codex working tree.

    Args:
        codex_root: Path to the Codex directory.

    Returns:
        A :class:`GitStatus`. If the directory is not a repository, or git is
        unavailable, ``is_repository`` is ``False`` and ``error`` explains why.
        This never raises, so ``hcp status`` still works without Git.
    """
    if not _git_available():
        return GitStatus(is_repository=False, error="git is not installed")
    if not is_git_repository(codex_root):
        return GitStatus(is_repository=False, error="not a git repository")

    result = _run_git(codex_root, ["status", "--porcelain", "--untracked-files=normal"])
    if result.returncode != 0:
        return GitStatus(
            is_repository=True,
            error=result.stderr.strip() or "git status failed",
        )

    entries = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        status_code = line[:2].strip() or "?"
        path = line[3:].strip()
        entries.append(GitStatusEntry(status=status_code, path=path))

    return GitStatus(is_repository=True, branch=current_branch(codex_root), entries=entries)


def history(codex_root, *, limit: int = 20, path: str | None = None) -> list[GitCommit]:
    """Return recent commits, newest first.

    Args:
        codex_root: Path to the Codex directory.
        limit: Maximum number of commits to return.
        path: Optional repository-relative path to filter the history.

    Returns:
        A list of :class:`GitCommit`. Empty when the Codex has no commits yet.

    Raises:
        GitUnavailableError: If git is missing or the command fails.
    """
    if not _git_available():
        raise GitUnavailableError("the 'git' binary is not available on PATH")
    if not is_git_repository(codex_root):
        return []

    separator = "\x1f"
    format_string = separator.join(["%H", "%h", "%an", "%aI", "%s"])
    args = ["log", f"-{max(1, int(limit))}", f"--pretty=format:{format_string}"]
    if path:
        args.extend(["--", path])

    result = _run_git(codex_root, args)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        # An empty repository has no commits; that is not an error.
        if "does not have any commits yet" in stderr or "bad default revision" in stderr:
            return []
        raise GitUnavailableError(stderr or "git log failed")

    commits = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(separator)
        if len(parts) != 5:
            continue
        commits.append(
            GitCommit(
                hash=parts[0],
                short_hash=parts[1],
                author=parts[2],
                date=parts[3],
                subject=parts[4],
            )
        )
    return commits


def diff(codex_root, *, path: str | None = None, staged: bool = False) -> str:
    """Return the textual diff of uncommitted changes.

    Args:
        codex_root: Path to the Codex directory.
        path: Optional repository-relative path to limit the diff.
        staged: Show staged changes instead of the working tree.

    Returns:
        The diff text, or an empty string when there are no changes.

    Raises:
        GitUnavailableError: If git is missing or the command fails.
    """
    if not _git_available():
        raise GitUnavailableError("the 'git' binary is not available on PATH")
    if not is_git_repository(codex_root):
        return ""

    args = ["diff", "--no-color"]
    if staged:
        args.append("--staged")
    if path:
        args.extend(["--", path])

    result = _run_git(codex_root, args)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "does not have any commits yet" in stderr or "bad default revision" in stderr:
            return ""
        raise GitUnavailableError(stderr or "git diff failed")
    return result.stdout + _untracked_diff(codex_root, path=path, staged=staged)


def _untracked_diff(codex_root, *, path: str | None, staged: bool) -> str:
    """Render untracked files as diffs so new assertions are visible.

    Plain ``git diff`` omits untracked files, which is exactly what a Codex
    author most wants to review: an assertion they just created is untracked, so
    ``hcp diff`` would otherwise report "no changes" right after an edit. This
    is still read-only, and only prints file names, never uploads anything.
    """
    listing = _run_git(
        codex_root,
        ["ls-files", "--others", "--exclude-standard"],
    )
    if listing.returncode != 0:
        return ""

    chunks: list[str] = []
    for entry in listing.stdout.splitlines():
        name = entry.strip()
        if not name:
            continue
        if path and name != path:
            continue
        if staged:
            continue
        chunks.append(
            f"\ndiff --git a/{name} b/{name}\nnew file (untracked)\n--- /dev/null\n+++ b/{name}\n"
        )
        candidate = Path(codex_root) / name
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                text = "<binary or unreadable file>\n"
            for line in text.splitlines():
                chunks.append(f"+{line}\n")
    return "".join(chunks)


__all__ = [
    "GitCommit",
    "GitStatus",
    "GitStatusEntry",
    "current_branch",
    "diff",
    "history",
    "is_git_repository",
    "status",
]
