"""Tests for Codex validation, including the authority invariants."""

from __future__ import annotations

from pathlib import Path

import pytest

from hcp.errors import Severity
from hcp.repository.codex import Codex
from hcp.validation.validator import validate_codex


def _codes(codex: Codex) -> set[str]:
    return {issue.code for issue in validate_codex(codex).issues}


def _errors(codex: Codex) -> set[str]:
    return {i.code for i in validate_codex(codex).errors}


def test_valid_assertion_passes(populated: Codex) -> None:
    report = validate_codex(populated)
    assert report.ok, report.issues
    assert report.summary() == "valid: no problems found"


def test_invalid_type_is_reported(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/bad.md",
        '---\nid: "value.bad"\ntype: "nonsense"\n---\n\nBody\n',
    )
    assert "invalid_type" in _errors(Codex.load(codex_path))


def test_invalid_source_is_reported(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/bad.md",
        '---\nid: "value.bad"\ntype: "value"\nsource: "robot"\n---\n\nBody\n',
    )
    assert "invalid_source" in _errors(Codex.load(codex_path))


def test_invalid_authority_is_reported(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/bad.md",
        '---\nid: "value.bad"\ntype: "value"\nauthority: "supreme"\n---\n\nBody\n',
    )
    assert "invalid_authority" in _errors(Codex.load(codex_path))


def test_invalid_status_is_reported(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/bad.md",
        '---\nid: "value.bad"\ntype: "value"\nstatus: "maybe"\n---\n\nBody\n',
    )
    assert "invalid_status" in _errors(Codex.load(codex_path))


def test_invalid_visibility_is_reported(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/bad.md",
        '---\nid: "value.bad"\ntype: "value"\nvisibility: "secret"\n---\n\nBody\n',
    )
    assert "invalid_visibility" in _errors(Codex.load(codex_path))


@pytest.mark.parametrize("value", ["-0.5", "1.5", "2"])
def test_confidence_outside_range_is_reported(
    codex_path: Path, write_assertion, value: str
) -> None:
    write_assertion(
        "values/bad.md",
        f'---\nid: "value.bad"\ntype: "value"\nconfidence: {value}\n---\n\nBody\n',
    )
    assert "invalid_confidence" in _errors(Codex.load(codex_path))


def test_invalid_date_is_reported(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/bad.md",
        '---\nid: "value.bad"\ntype: "value"\ncreated: "not-a-date"\n---\n\nBody\n',
    )
    assert "invalid_date" in _errors(Codex.load(codex_path))


def test_valid_until_before_valid_from_is_reported(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/bad.md",
        '---\nid: "value.bad"\ntype: "value"\nvalid_from: "2024-01-01"\n'
        'valid_until: "2023-01-01"\n---\n\nBody\n',
    )
    assert "invalid_date_range" in _errors(Codex.load(codex_path))


def test_duplicate_ids_are_reported(codex_path: Path, write_assertion) -> None:
    write_assertion("values/a.md", '---\nid: "value.same"\ntype: "value"\n---\n\nA\n')
    write_assertion("values/b.md", '---\nid: "value.same"\ntype: "value"\n---\n\nB\n')
    assert "duplicate_id" in _errors(Codex.load(codex_path))


def test_broken_supersedes_is_reported(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/a.md",
        '---\nid: "value.a"\ntype: "value"\nsupersedes: "value.ghost"\n---\n\nA\n',
    )
    assert "broken_supersedes" in _errors(Codex.load(codex_path))


def test_broken_derived_from_is_reported(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/a.md",
        '---\nid: "value.a"\ntype: "value"\nderived_from:\n  - "value.ghost"\n---\n\nA\n',
    )
    assert "broken_derived_from" in _errors(Codex.load(codex_path))


def test_external_derived_from_reference_is_allowed(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/a.md",
        '---\nid: "value.a"\ntype: "value"\nderived_from:\n  - "conversation:x"\n---\n\nA\n',
    )
    assert "broken_derived_from" not in _errors(Codex.load(codex_path))


def test_self_supersession_is_reported(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/a.md",
        '---\nid: "value.a"\ntype: "value"\nsupersedes: "value.a"\n---\n\nA\n',
    )
    assert "self_supersedes" in _errors(Codex.load(codex_path))


def test_missing_manifest_is_reported(tmp_path: Path) -> None:
    from hcp.errors import ManifestMissingError

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ManifestMissingError):
        Codex.load(empty)


# ----------------------------------------------------------------------
# Authority invariants
# ----------------------------------------------------------------------


def test_human_authoritative_is_valid(populated: Codex) -> None:
    assertion = populated.require("value.honesty")
    assert assertion.source == "human"
    assert assertion.authority == "authoritative"
    assert validate_codex(populated).ok


def test_ai_observation_must_be_proposed_and_pending(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "ai/observations/o.md",
        '---\nid: "obs.2026-01-01.a.001"\ntype: "observation"\nsource: "ai"\n'
        'authority: "proposed"\nstatus: "pending"\n---\n\nB\n',
    )
    assert validate_codex(Codex.load(codex_path)).ok


def test_ai_cannot_self_authoritative_high_confidence(codex_path: Path, write_assertion) -> None:
    """The central invariant: confidence never confers authority."""
    write_assertion(
        "ai/observations/o.md",
        '---\nid: "obs.2026-01-01.a.001"\ntype: "observation"\nsource: "ai"\n'
        'authority: "authoritative"\nstatus: "active"\nconfidence: 0.99\n---\n\nB\n',
    )
    assert "ai_observation_self_authoritative" in _errors(Codex.load(codex_path))


def test_ai_authoritative_requires_recorded_decision(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "ai/observations/o.md",
        '---\nid: "obs.2026-01-01.a.001"\ntype: "observation"\nsource: "ai"\n'
        'authority: "authoritative"\nstatus: "active"\nprovenance:\n'
        '  decision: "accepted"\n  decided_at: "2026-01-01T00:00:00+00:00"\n---\n\nB\n',
    )
    assert "ai_observation_self_authoritative" not in _errors(Codex.load(codex_path))


def test_active_status_requires_authoritative(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/a.md",
        '---\nid: "value.a"\ntype: "value"\nstatus: "active"\nauthority: "proposed"\n---\n\nA\n',
    )
    assert "status_authority_conflict" in _errors(Codex.load(codex_path))


def test_rejected_authority_requires_rejected_status(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/a.md",
        '---\nid: "value.a"\ntype: "value"\nauthority: "rejected"\nstatus: "active"\n---\n\nA\n',
    )
    assert "status_authority_conflict" in _errors(Codex.load(codex_path))


def test_pending_observation_must_be_proposed(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "ai/observations/o.md",
        '---\nid: "obs.2026-01-01.a.001"\ntype: "observation"\nsource: "ai"\n'
        'authority: "authoritative"\nstatus: "pending"\n---\n\nB\n',
    )
    assert "ai_observation_self_authoritative" in _errors(Codex.load(codex_path))


def test_invalid_id_is_reported(codex_path: Path, write_assertion) -> None:
    write_assertion("values/bad.md", '---\nid: "No Spaces"\ntype: "value"\n---\n\nB\n')
    assert "invalid_id" in _errors(Codex.load(codex_path))


def test_warnings_do_not_fail_validation(codex_path: Path, write_assertion) -> None:
    write_assertion("values/empty.md", '---\nid: "value.empty"\ntype: "value"\n---\n')
    report = validate_codex(Codex.load(codex_path))
    assert report.ok
    assert any(i.severity is Severity.WARNING for i in report.warnings)


def test_issue_names_file_and_field(codex_path: Path, write_assertion) -> None:
    write_assertion("values/bad.md", '---\nid: "value.bad"\ntype: "nope"\n---\n\nB\n')
    issues = [i for i in validate_codex(Codex.load(codex_path)).errors if i.code == "invalid_type"]
    assert issues[0].path == "values/bad.md"
    assert issues[0].field == "type"
    assert "values/bad.md:type" in issues[0].format()
