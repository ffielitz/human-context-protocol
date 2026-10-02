"""Safe filesystem access for a Codex repository.

Everything the application reads or writes goes through this module. Its job is
to make path traversal, symlink escapes, oversized files, and binary blobs
impossible to reach silently.

Threat model
------------
A Codex is untrusted local input. It may have been created by the user, synced
from another device, cloned from a repository, or produced by importing an AI
adapter's output. A malicious or careless repository must not be able to make
the CLI read ``/etc/passwd``, follow a symlink outside the Codex, exhaust memory
with a huge file, or treat binary content as an assertion.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from ..constants import MAX_FILE_BYTES, RESERVED_NAMES
from ..errors import UnsafePathError

#: Byte sequences that mark a file as binary rather than text.
_BINARY_SNIFF_BYTES = 8192


def resolve_codex_root(path: str | os.PathLike[str]) -> Path:
    """Resolve a user-supplied Codex path to an absolute directory.

    Args:
        path: Path to the Codex directory.

    Returns:
        The absolute, symlink-resolved directory path.

    Raises:
        UnsafePathError: If the path does not exist or is not a directory.
    """
    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise UnsafePathError(f"cannot resolve Codex path {path!r}: {exc}") from exc
    if not resolved.is_dir():
        raise UnsafePathError(f"{path!r} is not a directory")
    return resolved


def is_within(root: Path, candidate: Path) -> bool:
    """Return ``True`` if ``candidate`` is inside ``root`` after resolution.

    Both paths are resolved first, so ``a/../../etc/passwd`` and symlinks that
    point outside the Codex are both rejected.
    """
    try:
        root_resolved = root.resolve()
        candidate_resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return False
    if root_resolved == candidate_resolved:
        return True
    return root_resolved in candidate_resolved.parents


def safe_relative_path(root: Path, relative: str) -> Path:
    """Join a repository-relative path onto ``root`` safely.

    Rejects absolute paths, drive-like prefixes, ``..`` traversal, and any
    result that escapes ``root``.

    Args:
        root: The Codex root.
        relative: A repository-relative path such as ``identity/core.md``.

    Returns:
        The absolute path inside the Codex.

    Raises:
        UnsafePathError: If the path is unsafe.
    """
    if not relative or not relative.strip():
        raise UnsafePathError("path must not be empty")
    text = relative.strip().replace("\\", "/")
    pure = PurePosixPath(text)
    if pure.is_absolute():
        raise UnsafePathError(f"path must be relative to the Codex: {relative!r}")
    if any(part == ".." for part in pure.parts):
        raise UnsafePathError(f"path must not traverse upwards: {relative!r}")
    if any(part == "~" for part in pure.parts):
        raise UnsafePathError(f"path must not contain '~': {relative!r}")
    candidate = root / Path(*pure.parts)
    if not is_within(root, candidate):
        raise UnsafePathError(f"path escapes the Codex: {relative!r}")
    return candidate


def is_symlink(path: Path) -> bool:
    """Return ``True`` if ``path`` is a symbolic link."""
    return path.is_symlink()


def read_text_file(path: Path, *, max_bytes: int = MAX_FILE_BYTES) -> str:
    """Read a UTF-8 text file with size and binary guards.

    Args:
        path: File to read.
        max_bytes: Maximum permitted size.

    Returns:
        The decoded text with any BOM removed.

    Raises:
        UnsafePathError: If the file is too large, unreadable, or binary.
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise UnsafePathError(f"cannot stat {path}: {exc}") from exc
    if size > max_bytes:
        raise UnsafePathError(
            f"file is too large to parse ({size} bytes > {max_bytes} bytes): {path.name}"
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise UnsafePathError(f"cannot read {path}: {exc}") from exc

    if b"\x00" in raw[:_BINARY_SNIFF_BYTES]:
        raise UnsafePathError(f"file appears to be binary, not Markdown: {path.name}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsafePathError(f"file is not valid UTF-8 text: {path.name}") from exc
    return text[1:] if text.startswith("\ufeff") else text


def write_text_file(path: Path, content: str) -> None:
    """Write UTF-8 text, creating parent directories as needed.

    Args:
        path: Destination file.
        content: Text content.

    Raises:
        UnsafePathError: If the content is not encodable or the write fails.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except (OSError, UnicodeEncodeError) as exc:
        raise UnsafePathError(f"cannot write {path}: {exc}") from exc


def is_reserved(name: str) -> bool:
    """Return ``True`` if a directory or file name must never be scanned."""
    return name in RESERVED_NAMES


def iter_markdown_files(root: Path, *, follow_symlinks: bool = False) -> Iterator[Path]:
    """Yield Markdown files inside a Codex, skipping reserved directories.

    Args:
        root: Codex root directory.
        follow_symlinks: When ``False`` (default) symlinked files are skipped so
            a Codex cannot reach content outside itself.

    Yields:
        Absolute paths to ``.md`` files in deterministic sorted order.
    """
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirnames[:] = sorted(name for name in dirnames if not is_reserved(name))
        current = Path(dirpath)
        for filename in sorted(filenames):
            if not filename.lower().endswith((".md", ".markdown")):
                continue
            candidate = current / filename
            if not follow_symlinks and candidate.is_symlink():
                continue
            yield candidate


def relative_to_root(root: Path, path: Path) -> str:
    """Return ``path`` as a POSIX-style string relative to ``root``."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError) as exc:
        raise UnsafePathError(f"{path} is not inside {root}") from exc


def copy_tree(source: Path, destination: Path) -> None:
    """Copy a template directory into place.

    Raises:
        UnsafePathError: If the copy fails.
    """
    try:
        shutil.copytree(source, destination, dirs_exist_ok=True)
    except OSError as exc:
        raise UnsafePathError(f"cannot copy template to {destination}: {exc}") from exc


__all__ = [
    "copy_tree",
    "is_reserved",
    "is_symlink",
    "is_within",
    "iter_markdown_files",
    "read_text_file",
    "relative_to_root",
    "resolve_codex_root",
    "safe_relative_path",
    "write_text_file",
]
