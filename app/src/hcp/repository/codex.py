"""Codex discovery, loading, and indexing.

A Codex is a directory containing ``manifest.yaml`` plus Markdown documents. This
module turns that directory into a typed, queryable object graph and is the only
place that knows how files map to assertions.

Loading is deliberately forgiving: a malformed assertion is recorded as an
:class:`~hcp.errors.Issue` on the :class:`Codex` instead of aborting the whole
load, so ``hcp validate`` can report every problem in the repository in one pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..constants import HCP_VERSION, MANIFEST_FILENAME, OBSERVATIONS_DIR, PROSE_DOCUMENTS
from ..errors import (
    AssertionExistsError,
    AssertionNotFoundError,
    DocumentError,
    Issue,
    ManifestMissingError,
    Severity,
    UnsafePathError,
)
from ..ids import slugify
from ..models.assertion import Assertion, utc_today
from ..models.manifest import Manifest
from ..parser.frontmatter import parse_frontmatter, safe_load_yaml
from ..parser.markdown import assertion_from_markdown, assertion_to_markdown
from .files import (
    iter_markdown_files,
    read_text_file,
    relative_to_root,
    resolve_codex_root,
    safe_relative_path,
    write_text_file,
)

#: Semantic areas created by ``hcp init``, per HCP-0001 section 5.
DEFAULT_AREAS: tuple[str, ...] = (
    "identity",
    "values",
    "worldview",
    "preferences",
    "relationships",
    "life",
    "ai",
)

#: Human-authored prose documents created by ``hcp init``.
PROSE_FILES: tuple[str, ...] = PROSE_DOCUMENTS

#: Mapping from assertion type to the default directory new assertions land in.
TYPE_DIRECTORIES: dict[str, str] = {
    "identity": "identity",
    "fact": "life",
    "experience": "life",
    "value": "values",
    "principle": "values",
    "boundary": "values",
    "belief": "worldview",
    "preference": "preferences",
    "relationship": "relationships",
    "goal": "life",
    "aspiration": "life",
    "observation": OBSERVATIONS_DIR,
}


@dataclass
class LoadedDocument:
    """A Markdown file that could not be parsed into an assertion."""

    path: str
    issues: list[Issue] = field(default_factory=list)


@dataclass
class Codex:
    """An in-memory view of a Codex repository."""

    root: Path
    manifest: Manifest
    assertions: list[Assertion] = field(default_factory=list)
    documents: list[LoadedDocument] = field(default_factory=list)
    prose: dict[str, str] = field(default_factory=dict)
    extra_files: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> Codex:
        """Load a Codex from a directory.

        Args:
            path: Directory containing ``manifest.yaml``.

        Returns:
            The loaded :class:`Codex`.

        Raises:
            CodexNotFoundError: If the directory does not exist.
            ManifestMissingError: If ``manifest.yaml`` is absent or invalid.
        """
        root = resolve_codex_root(path)
        return cls._load_root(root)

    @classmethod
    def _load_root(cls, root: Path) -> Codex:
        manifest_path = root / MANIFEST_FILENAME
        if not manifest_path.is_file():
            raise ManifestMissingError(f"{root} is not an HCP Codex: {MANIFEST_FILENAME} not found")

        raw = read_text_file(manifest_path)
        try:
            data = safe_load_yaml(raw, path=MANIFEST_FILENAME)
        except DocumentError as exc:
            raise ManifestMissingError(f"cannot read {MANIFEST_FILENAME}: {exc}") from exc

        try:
            manifest = Manifest(**{**data, "path": MANIFEST_FILENAME})
        except ValidationError as exc:
            raise ManifestMissingError(
                f"{MANIFEST_FILENAME} is invalid: {exc.error_count()} problem(s)"
            ) from exc

        codex = cls(root=root, manifest=manifest)
        codex._scan()
        return codex

    def _scan(self) -> None:
        """Walk the Codex and populate assertions, prose, and documents."""
        for path in iter_markdown_files(self.root):
            relative = relative_to_root(self.root, path)
            try:
                text = read_text_file(path)
            except UnsafePathError as exc:
                self.documents.append(
                    LoadedDocument(relative, [Issue("unreadable_file", str(exc), relative)])
                )
                continue

            if relative in PROSE_FILES:
                self.prose[relative] = text
                continue

            try:
                front = parse_frontmatter(text, path=relative)
            except DocumentError as exc:
                # Prose without frontmatter is legitimate in non-reserved files
                # (for example ai/observations.md), so record it as a document
                # rather than failing the load.
                self.documents.append(LoadedDocument(relative, exc.issues))
                continue

            if "id" not in front.metadata:
                self.documents.append(
                    LoadedDocument(
                        relative,
                        [
                            Issue(
                                "missing_assertion_id",
                                "Markdown file has frontmatter but no 'id' field; "
                                "it is not an assertion",
                                relative,
                                "id",
                            )
                        ],
                    )
                )
                continue

            try:
                assertion = assertion_from_markdown(text, path=relative)
            except DocumentError as exc:
                self.documents.append(LoadedDocument(relative, exc.issues))
                continue

            self.assertions.append(assertion)

        self.assertions.sort(key=lambda item: item.id)

    # ------------------------------------------------------------------
    # Indexing and querying
    # ------------------------------------------------------------------

    @property
    def issues(self) -> list[Issue]:
        """Return every issue found while loading the Codex."""
        collected: list[Issue] = []
        for document in self.documents:
            collected.extend(document.issues)
        return collected

    @property
    def has_errors(self) -> bool:
        """Return ``True`` if any load issue is an error."""
        return any(issue.severity is Severity.ERROR for issue in self.issues)

    def by_id(self, assertion_id: str) -> Assertion | None:
        """Return the assertion with ``assertion_id``, if present."""
        for assertion in self.assertions:
            if assertion.id == assertion_id:
                return assertion
        return None

    def require(self, assertion_id: str) -> Assertion:
        """Return the assertion with ``assertion_id``.

        Raises:
            AssertionNotFoundError: If no such assertion exists.
        """
        found = self.by_id(assertion_id)
        if found is None:
            known = ", ".join(sorted(a.id for a in self.assertions)[:5]) or "none"
            raise AssertionNotFoundError(
                f"no assertion with id {assertion_id!r} in this Codex (existing: {known})"
            )
        return found

    def in_area(self, area: str) -> list[Assertion]:
        """Return assertions stored under the given top-level area."""
        prefix = f"{area}/"
        return [a for a in self.assertions if a.path and a.path.startswith(prefix)]

    def observations(self) -> list[Assertion]:
        """Return all AI observations, whatever their review state."""
        return [a for a in self.assertions if a.is_ai_observation]

    def pending_observations(self) -> list[Assertion]:
        """Return observations still awaiting a human decision."""
        return [a for a in self.assertions if a.is_ai_observation and a.is_pending]

    def human_assertions(self) -> list[Assertion]:
        """Return human-authored assertions."""
        return [a for a in self.assertions if not a.is_ai_observation]

    def superseded_ids(self) -> set[str]:
        """Return IDs that some other assertion explicitly supersedes."""
        return {a.supersedes for a in self.assertions if a.supersedes}

    def superseded_at(self, moment: date) -> set[str]:
        """Return IDs that were superseded *as of* ``moment``.

        Supersession is itself temporal: an assertion that was replaced in 2021
        was still the current view in 2020. Only superseding assertions that are
        themselves valid at ``moment`` remove their predecessor from current
        context. This is what lets a Codex answer "what did I believe then?"
        without deleting history.
        """
        replaced: set[str] = set()
        for assertion in self.assertions:
            if assertion.supersedes and assertion.is_valid_at(moment):
                replaced.add(assertion.supersedes)
        return replaced

    def active_at(self, moment: date) -> list[Assertion]:
        """Return assertions that are current, approved, and not superseded."""
        superseded = self.superseded_at(moment)
        return [
            a
            for a in self.assertions
            if a.is_valid_at(moment)
            and a.status == "active"
            and a.authority == "authoritative"
            and a.id not in superseded
        ]

    def counts(self) -> dict[str, dict[str, int]]:
        """Return counts by type, status, source, authority, and visibility."""
        summary: dict[str, dict[str, int]] = {
            "type": {},
            "status": {},
            "source": {},
            "authority": {},
            "visibility": {},
        }
        for assertion in self.assertions:
            summary["type"][assertion.type] = summary["type"].get(assertion.type, 0) + 1
            summary["status"][assertion.status] = summary["status"].get(assertion.status, 0) + 1
            summary["source"][assertion.source] = summary["source"].get(assertion.source, 0) + 1
            summary["authority"][assertion.authority] = (
                summary["authority"].get(assertion.authority, 0) + 1
            )
            summary["visibility"][assertion.visibility] = (
                summary["visibility"].get(assertion.visibility, 0) + 1
            )
        return summary

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def path_for(self, assertion: Assertion) -> Path:
        """Return the on-disk path for ``assertion``.

        Raises:
            UnsafePathError: If the recorded path is unsafe.
        """
        if not assertion.path:
            raise UnsafePathError(f"assertion {assertion.id!r} has no recorded path")
        return safe_relative_path(self.root, assertion.path)

    def default_path_for(self, type_: str, assertion_id: str) -> str:
        """Return the conventional relative path for a new assertion.

        The filename is derived from the ID's namespace and name, not from the
        ID alone, so IDs never depend on filenames (see ``hcp/ids.py``).
        """
        area = TYPE_DIRECTORIES.get(type_, "life")
        parts = assertion_id.split(".")
        stem = slugify(parts[-1]) if len(parts) > 1 else slugify(parts[0])
        return f"{area}/{stem}.md"

    def add(self, assertion: Assertion, *, path: str | None = None, overwrite: bool = False) -> str:
        """Write a new assertion into the Codex and index it.

        Args:
            assertion: The assertion to persist.
            path: Optional repository-relative path override.
            overwrite: Allow replacing an existing file.

        Returns:
            The repository-relative path that was written.

        Raises:
            AssertionExistsError: If the ID or target path is already in use.
            UnsafePathError: If the path escapes the Codex.
        """
        if self.by_id(assertion.id) is not None:
            raise AssertionExistsError(f"assertion id {assertion.id!r} already exists")
        relative = path or assertion.path or self.default_path_for(assertion.type, assertion.id)
        destination = safe_relative_path(self.root, relative)
        if destination.exists() and not overwrite:
            raise AssertionExistsError(f"{relative} already exists")
        assertion.path = relative
        write_text_file(destination, assertion_to_markdown(assertion))
        self.assertions.append(assertion)
        self.assertions.sort(key=lambda item: item.id)
        self.touch()
        return relative

    def save(self, assertion: Assertion) -> str:
        """Persist changes to an existing assertion and index it."""
        relative = assertion.path or self.default_path_for(assertion.type, assertion.id)
        destination = safe_relative_path(self.root, relative)
        assertion.path = relative
        write_text_file(destination, assertion_to_markdown(assertion))
        self.touch()
        return relative

    def touch(self) -> None:
        """Update the manifest's ``updated`` field to today."""
        self.manifest.updated = utc_today()
        data = self.manifest.to_yaml_dict()
        write_text_file(
            self.root / MANIFEST_FILENAME,
            _dump_yaml(data),
        )

    def path_of(self, assertion_id: str) -> Path:
        """Return the absolute path of an assertion, verifying it exists.

        Raises:
            AssertionNotFoundError: If the assertion is unknown.
            UnsafePathError: If the recorded path is unsafe.
        """
        assertion = self.require(assertion_id)
        path = self.path_for(assertion)
        if not path.is_file():
            raise AssertionNotFoundError(
                f"assertion {assertion_id!r} is indexed but {assertion.path} is missing"
            )
        return path


def _dump_yaml(data: dict[str, Any]) -> str:
    """Serialise a mapping to deterministic YAML for on-disk metadata files."""
    import yaml

    return yaml.dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=1000,
    )


def utc_timestamp() -> datetime:
    """Return the current UTC timestamp, used for bundle IDs and provenance."""
    return datetime.now(UTC).replace(microsecond=0)


__all__ = [
    "DEFAULT_AREAS",
    "HCP_VERSION",
    "TYPE_DIRECTORIES",
    "Codex",
    "LoadedDocument",
    "utc_timestamp",
]
