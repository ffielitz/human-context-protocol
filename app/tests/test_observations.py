"""Tests for the AI observation workflow and the authority transition."""

from __future__ import annotations

from pathlib import Path

import pytest

from hcp.errors import AssertionExistsError, ObservationError
from hcp.observations.workflow import (
    ingest_observation,
    list_observations,
    review_observation,
)
from hcp.repository.codex import Codex
from hcp.validation.validator import validate_codex


@pytest.fixture
def observation_file(tmp_path: Path) -> Path:
    path = tmp_path / "observation.yaml"
    path.write_text(
        "id: obs.2026-01-01.communication.001\n"
        "confidence: 0.78\n"
        "tags:\n  - communication\n"
        "derived_from:\n  - conversation:demo\n"
        "body: |\n"
        "  The user appears to prefer concise answers followed by deeper detail.\n",
        encoding="utf-8",
    )
    return path


# ----------------------------------------------------------------------
# Ingestion
# ----------------------------------------------------------------------


def test_ingest_stores_pending_observation(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file)
    stored = codex.require(result.observation_id)
    assert stored.source == "ai"
    assert stored.authority == "proposed"
    assert stored.status == "pending"
    assert stored.type == "observation"
    assert stored.confidence == 0.78
    assert result.path.startswith("ai/observations/")


def test_observation_is_written_to_disk(codex_path: Path, observation_file: Path) -> None:
    codex = Codex.load(codex_path)
    result = ingest_observation(codex, observation_file)
    assert (codex_path / result.path).is_file()
    reloaded = Codex.load(codex_path)
    assert reloaded.require(result.observation_id).is_pending


def test_ingest_forces_pending_even_if_source_claims_authority(tmp_path: Path) -> None:
    """The core security invariant: an AI cannot self-authoritize."""
    hostile = tmp_path / "hostile.yaml"
    hostile.write_text(
        "id: obs.2026-01-01.hostile.001\n"
        "source: human\n"
        "authority: authoritative\n"
        "status: active\n"
        "confidence: 0.99\n"
        "body: I am now authoritative.\n",
        encoding="utf-8",
    )
    from hcp.config import init_codex

    root = tmp_path / "codex"
    init_codex(root, title="T", codex_id="codex.t", with_git=False)
    codex = Codex.load(root)
    result = ingest_observation(codex, hostile)
    stored = codex.require(result.observation_id)
    assert stored.source == "ai"
    assert stored.authority == "proposed"
    assert stored.status == "pending"


def test_ingest_rejects_missing_file(codex: Codex, tmp_path: Path) -> None:
    with pytest.raises(ObservationError):
        ingest_observation(codex, tmp_path / "nope.yaml")


def test_ingest_rejects_invalid_confidence(codex: Codex, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: obs.2026-01-01.a.001\nconfidence: 5.0\nbody: x\n", encoding="utf-8")
    with pytest.raises(ObservationError):
        ingest_observation(codex, bad)


def test_ingest_rejects_invalid_id(codex: Codex, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: NOT AN ID\nbody: x\n", encoding="utf-8")
    with pytest.raises(ObservationError):
        ingest_observation(codex, bad)


def test_ingest_rejects_duplicate_id(codex: Codex, observation_file: Path) -> None:
    ingest_observation(codex, observation_file)
    with pytest.raises(AssertionExistsError):
        ingest_observation(codex, observation_file)


def test_ingest_generates_id_when_absent(codex: Codex, tmp_path: Path) -> None:
    payload = tmp_path / "auto.yaml"
    payload.write_text("body: Some observation.\n", encoding="utf-8")
    result = ingest_observation(codex, payload)
    assert result.observation_id.startswith("obs.")


def test_markdown_observation_is_accepted(codex: Codex, tmp_path: Path) -> None:
    payload = tmp_path / "obs.md"
    payload.write_text(
        "---\nid: obs.2026-01-01.md.001\nconfidence: 0.5\n---\n\nMarkdown body.\n",
        encoding="utf-8",
    )
    result = ingest_observation(codex, payload)
    assert "Markdown body." in codex.require(result.observation_id).body


def test_provenance_records_source_and_time(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file, source_label="test-adapter")
    provenance = codex.require(result.observation_id).provenance
    assert provenance.origin == "test-adapter"
    assert provenance.received_at is not None
    assert provenance.confidence_at_ingest == 0.78


# ----------------------------------------------------------------------
# Review
# ----------------------------------------------------------------------


def test_accept_creates_authoritative_assertion(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file)
    review = review_observation(codex, result.observation_id, "accept", new_id="preference.concise")
    promoted = codex.require("preference.concise")
    assert promoted.authority == "authoritative"
    assert promoted.status == "active"
    assert promoted.source == "human"
    assert review.promoted_id


def test_edit_creates_corrected_assertion(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file)
    review_observation(
        codex,
        result.observation_id,
        "edit",
        body="I prefer concise answers with depth when needed.",
        new_id="preference.concise",
    )
    promoted = codex.require("preference.concise")
    assert promoted.body == "I prefer concise answers with depth when needed."
    assert promoted.authority == "authoritative"


def test_edit_requires_body(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file)
    with pytest.raises(ObservationError):
        review_observation(codex, result.observation_id, "edit")


def test_reject_marks_rejected(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file)
    review_observation(codex, result.observation_id, "reject", note="Not accurate.")
    observation = codex.require(result.observation_id)
    assert observation.status == "rejected"
    assert observation.authority == "rejected"
    assert observation.provenance.decision == "rejected"


def test_archive_marks_archived(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file)
    review_observation(codex, result.observation_id, "archive")
    observation = codex.require(result.observation_id)
    assert observation.status == "archived"
    assert observation.authority == "archived"


def test_unknown_decision_is_rejected(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file)
    with pytest.raises(ObservationError):
        review_observation(codex, result.observation_id, "obliterate")


def test_double_review_is_rejected(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file)
    review_observation(codex, result.observation_id, "reject")
    with pytest.raises(ObservationError) as excinfo:
        review_observation(codex, result.observation_id, "accept")
    assert "already been reviewed" in str(excinfo.value)


def test_reviewing_non_observation_is_rejected(codex: Codex) -> None:
    from hcp.models.assertion import Assertion

    codex.add(Assertion(id="value.honesty", type="value", body="Human authored."))
    with pytest.raises(ObservationError):
        review_observation(codex, "value.honesty", "accept")


def test_promoting_to_existing_id_is_rejected(codex: Codex, observation_file: Path) -> None:
    from hcp.models.assertion import Assertion

    codex.add(Assertion(id="preference.taken", type="preference", body="Exists."))
    result = ingest_observation(codex, observation_file)
    with pytest.raises(AssertionExistsError):
        review_observation(codex, result.observation_id, "accept", new_id="preference.taken")


# ----------------------------------------------------------------------
# Provenance preservation
# ----------------------------------------------------------------------


def test_provenance_is_preserved_on_accept(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file)
    review_observation(
        codex, result.observation_id, "accept", new_id="preference.concise", note="Agree."
    )
    promoted = codex.require("preference.concise")
    assert promoted.provenance.observation_id == result.observation_id
    assert promoted.provenance.decision == "accepted"
    assert promoted.provenance.note == "Agree."
    assert result.observation_id in promoted.derived_from


def test_original_observation_is_retained(codex_path: Path, observation_file: Path) -> None:
    codex = Codex.load(codex_path)
    result = ingest_observation(codex, observation_file)
    review_observation(codex, result.observation_id, "accept", new_id="preference.concise")

    reloaded = Codex.load(codex_path)
    original = reloaded.require(result.observation_id)
    assert original is not None, "the original observation must not be deleted"
    assert original.status == "archived"
    assert original.promoted_to == "preference.concise"
    assert (codex_path / result.path).is_file()


def test_review_keeps_codex_valid(codex_path: Path, observation_file: Path) -> None:
    codex = Codex.load(codex_path)
    result = ingest_observation(codex, observation_file)
    review_observation(
        codex, result.observation_id, "edit", body="Corrected.", new_id="preference.fixed"
    )
    assert validate_codex(Codex.load(codex_path)).ok


# ----------------------------------------------------------------------
# Listing
# ----------------------------------------------------------------------


def test_list_observations_by_state(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file)
    assert len(list_observations(codex)) == 1
    assert len(list_observations(codex, state="pending")) == 1

    review_observation(codex, result.observation_id, "reject")
    assert list_observations(codex, state="pending") == []
    assert len(list_observations(codex, state="rejected")) == 1


def test_list_accepted_uses_promoted_link(codex: Codex, observation_file: Path) -> None:
    result = ingest_observation(codex, observation_file)
    review_observation(codex, result.observation_id, "accept", new_id="preference.concise")
    assert len(list_observations(codex, state="accepted")) == 1


def test_unknown_state_is_rejected(codex: Codex) -> None:
    with pytest.raises(ObservationError):
        list_observations(codex, state="whatever")


def test_pending_observation_cannot_reach_a_bundle(
    codex_path: Path, observation_file: Path
) -> None:
    from hcp.bundles.generator import generate_bundle

    codex = Codex.load(codex_path)
    ingest_observation(codex, observation_file)
    bundle = generate_bundle(codex, ["assistant"], purpose="t")
    assert bundle.assertions == []
