"""Tests for Codex discovery, loading, indexing, and mutation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from hcp.config import init_codex
from hcp.errors import (
    AssertionExistsError,
    AssertionNotFoundError,
    ManifestMissingError,
    UnsafePathError,
)
from hcp.models.assertion import Assertion
from hcp.repository.codex import Codex


def test_init_creates_a_valid_codex(codex_path: Path) -> None:
    codex = Codex.load(codex_path)
    assert codex.manifest.codex_id == "codex.test"
    assert (codex_path / "manifest.yaml").is_file()
    assert (codex_path / "constitution.md").is_file()
    assert (codex_path / "soul.md").is_file()
    assert (codex_path / "scopes.yaml").is_file()
    for area in ("identity", "values", "preferences", "ai"):
        assert (codex_path / area).is_dir()


def test_fresh_codex_is_valid(codex: Codex) -> None:
    from hcp.validation.validator import validate_codex

    assert validate_codex(codex).ok


def test_init_refuses_to_overwrite(codex_path: Path) -> None:
    with pytest.raises(UnsafePathError):
        init_codex(codex_path, title="Again", with_git=False)


def test_load_requires_manifest(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ManifestMissingError):
        Codex.load(empty)


def test_load_rejects_file_path(tmp_path: Path) -> None:
    target = tmp_path / "file.md"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(UnsafePathError):
        Codex.load(target)


def test_prose_documents_are_not_assertions(codex: Codex) -> None:
    assert "constitution.md" in codex.prose
    assert "soul.md" in codex.prose
    assert codex.assertions == []


def test_frontmatter_file_without_id_is_a_document(codex_path: Path, write_assertion) -> None:
    write_assertion("values/notes.md", "---\ntype: value\n---\n\nNotes.\n")
    codex = Codex.load(codex_path)
    assert codex.assertions == []
    assert any(d.issues for d in codex.documents)


def test_malformed_assertion_is_recorded_not_raised(codex_path: Path, write_assertion) -> None:
    write_assertion("values/broken.md", "---\nid: [unclosed\n---\n\nBody\n")
    codex = Codex.load(codex_path)
    assert codex.assertions == []
    assert codex.has_errors


def test_require_raises_for_unknown_id(populated: Codex) -> None:
    with pytest.raises(AssertionNotFoundError):
        populated.require("value.nonexistent")


def test_add_persists_and_indexes(codex: Codex) -> None:
    today = date.today()
    assertion = Assertion(
        id="value.honesty",
        type="value",
        body="Honesty matters.",
        created=today,
        updated=today,
        valid_from=today,
    )
    relative = codex.add(assertion)
    assert relative.endswith(".md")
    assert (codex.root / relative).is_file()
    assert codex.by_id("value.honesty") is not None

    reloaded = Codex.load(codex.root)
    assert reloaded.require("value.honesty").body == "Honesty matters."


def test_add_rejects_duplicate_id(populated: Codex) -> None:
    duplicate = Assertion(id="value.honesty", type="value", body="Again.")
    with pytest.raises(AssertionExistsError):
        populated.add(duplicate, path="values/other.md")


def test_add_rejects_escaping_path(codex: Codex) -> None:
    with pytest.raises(UnsafePathError):
        codex.add(Assertion(id="value.x", type="value", body="x"), path="../escape.md")


def test_save_updates_file(codex: Codex) -> None:
    today = date.today()
    codex.add(
        Assertion(
            id="value.tmp",
            type="value",
            body="First.",
            created=today,
            updated=today,
            valid_from=today,
        )
    )
    codex.require("value.tmp").body = "Second."
    codex.save(codex.require("value.tmp"))
    assert Codex.load(codex.root).require("value.tmp").body == "Second."


def test_touch_updates_manifest_date(codex: Codex) -> None:
    codex.manifest.updated = date(2000, 1, 1)
    codex.touch()
    assert Codex.load(codex.root).manifest.updated == date.today()


def test_default_path_for_uses_type_directory(codex: Codex) -> None:
    assert codex.default_path_for("value", "value.honesty") == "values/honesty.md"
    assert codex.default_path_for("preference", "preference.direct") == "preferences/direct.md"


def test_default_path_ignores_filename_for_id(codex: Codex) -> None:
    """IDs do not depend on filenames; the path is derived from the ID."""
    path = codex.default_path_for("belief", "belief.ai.human-agency")
    assert path == "worldview/human-agency.md"


def test_counts_and_queries(populated: Codex) -> None:
    counts = populated.counts()
    assert counts["type"]["value"] == 1
    assert counts["source"]["human"] == 1
    assert populated.human_assertions()
    assert populated.pending_observations() == []
    assert populated.in_area("values")


def test_superseded_ids(populated: Codex) -> None:
    populated.require("value.honesty").supersedes = "value.old"
    assert "value.old" in populated.superseded_ids()
