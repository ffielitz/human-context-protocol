"""Tests for Context Bundle generation: scoping, privacy, determinism, trust."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from hcp.bundles.generator import (
    DEFAULT_SCOPES,
    Scope,
    ScopeConfig,
    generate_bundle,
    load_scopes,
    select_assertions,
)
from hcp.errors import ScopeConfigError
from hcp.models.bundle import TrustConditions, TrustResponse
from hcp.repository.codex import Codex


def _write(codex_path: Path, relative: str, text: str) -> None:
    target = codex_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _full_codex(codex_path: Path) -> Codex:
    _write(
        codex_path,
        "identity/core.md",
        '---\nid: "identity.core"\ntype: "identity"\nvisibility: "private"\n'
        'valid_from: "2020-01-01"\n---\n\nI am a software professional.\n',
    )
    _write(
        codex_path,
        "preferences/communication.md",
        '---\nid: "preference.communication"\ntype: "preference"\n'
        'visibility: "private"\nvalid_from: "2020-01-01"\n---\n\nPrefer direct answers.\n',
    )
    _write(
        codex_path,
        "values/honesty.md",
        '---\nid: "value.honesty"\ntype: "value"\nvisibility: "private"\n'
        'valid_from: "2020-01-01"\n---\n\nHonesty matters.\n',
    )
    _write(
        codex_path,
        "life/secret.md",
        '---\nid: "fact.address"\ntype: "fact"\nvisibility: "restricted"\n'
        'valid_from: "2020-01-01"\n---\n\nI live at 12 Example Street.\n',
    )
    _write(
        codex_path,
        "life/sensitive.md",
        '---\nid: "fact.health"\ntype: "fact"\nvisibility: "sensitive"\n'
        'valid_from: "2020-01-01"\n---\n\nSensitive detail.\n',
    )
    _write(
        codex_path,
        "life/expired.md",
        '---\nid: "fact.old"\ntype: "fact"\nvisibility: "private"\n'
        'valid_from: "2019-01-01"\nvalid_until: "2020-01-01"\n---\n\nOld fact.\n',
    )
    return Codex.load(codex_path)


def _ids(bundle) -> set[str]:
    return {a["id"] for a in bundle.assertions}


# ----------------------------------------------------------------------
# Scope filtering
# ----------------------------------------------------------------------


def test_assistant_scope_includes_expected_areas(codex_path: Path) -> None:
    bundle = generate_bundle(
        _full_codex(codex_path), ["assistant"], purpose="test", at=date(2025, 1, 1)
    )
    assert _ids(bundle) == {"identity.core", "preference.communication", "value.honesty"}


def test_public_scope_excludes_private_areas(codex_path: Path) -> None:
    bundle = generate_bundle(
        _full_codex(codex_path), ["public"], purpose="test", at=date(2025, 1, 1)
    )
    # public scope has visibility_ceiling public, so private assertions drop out.
    assert _ids(bundle) == set()


def test_restricted_data_is_excluded_by_default(codex_path: Path) -> None:
    codex = _full_codex(codex_path)
    config = ScopeConfig(
        scopes={
            "everything": Scope(name="everything", include=("*",), visibility_ceiling="private"),
            "open": Scope(name="open", include=("*",), visibility_ceiling="restricted"),
        }
    )
    default_bundle = generate_bundle(
        codex, ["everything"], purpose="t", at=date(2025, 1, 1), config=config
    )
    assert "fact.address" not in _ids(default_bundle)

    restricted_bundle = generate_bundle(
        codex, ["open"], purpose="t", at=date(2025, 1, 1), config=config
    )
    assert "fact.address" in _ids(restricted_bundle)


def test_sensitive_requires_explicit_ceiling(codex_path: Path) -> None:
    codex = _full_codex(codex_path)
    config = ScopeConfig(
        scopes={
            "all_private": Scope(name="all_private", include=("*",), visibility_ceiling="private")
        }
    )
    bundle = generate_bundle(
        codex, ["all_private"], purpose="t", at=date(2025, 1, 1), config=config
    )
    assert "fact.health" not in _ids(bundle)


def test_expired_assertion_is_excluded(codex_path: Path) -> None:
    bundle = generate_bundle(
        _full_codex(codex_path), ["assistant"], purpose="t", at=date(2025, 1, 1)
    )
    assert "fact.old" not in _ids(bundle)


def test_pending_observation_never_reaches_a_bundle(codex_path: Path) -> None:
    _write(
        codex_path,
        "ai/observations/o.md",
        '---\nid: "obs.2026-01-01.a.001"\ntype: "observation"\nsource: "ai"\n'
        'authority: "proposed"\nstatus: "pending"\nvisibility: "private"\n'
        'valid_from: "2020-01-01"\n---\n\nGuess about the user.\n',
    )
    bundle = generate_bundle(
        _full_codex(codex_path), ["assistant"], purpose="t", at=date(2025, 1, 1)
    )
    assert "obs.2026-01-01.a.001" not in _ids(bundle)


def test_unknown_scope_is_rejected(codex_path: Path) -> None:
    with pytest.raises(ScopeConfigError):
        generate_bundle(_full_codex(codex_path), ["nope"], purpose="t")


def test_empty_scope_list_is_rejected(codex_path: Path) -> None:
    with pytest.raises(ScopeConfigError):
        generate_bundle(_full_codex(codex_path), [], purpose="t")


def test_excluded_reason_explains_omissions(codex_path: Path) -> None:
    from hcp.bundles.generator import excluded_reason

    codex = _full_codex(codex_path)
    config = load_scopes(codex)
    scopes = [config.get("assistant")]
    selected = select_assertions(codex, scopes, at=date(2025, 1, 1))
    reasons = excluded_reason(codex, scopes, selected, at=date(2025, 1, 1))
    assert "out of scope" in " ".join(reasons["fact.address"])
    assert reasons


# ----------------------------------------------------------------------
# Determinism
# ----------------------------------------------------------------------


def test_bundle_is_deterministic_for_same_input(codex_path: Path) -> None:
    fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    first = generate_bundle(
        _full_codex(codex_path),
        ["assistant"],
        purpose="t",
        at=date(2025, 1, 1),
        created=fixed,
    )
    second = generate_bundle(
        _full_codex(codex_path),
        ["assistant"],
        purpose="t",
        at=date(2025, 1, 1),
        created=fixed,
    )
    assert first.to_json_dict() == second.to_json_dict()
    assert first.bundle_id == second.bundle_id


def test_bundle_id_changes_when_content_changes(codex_path: Path) -> None:
    fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    before = generate_bundle(_full_codex(codex_path), ["assistant"], purpose="t", created=fixed)
    _write(
        codex_path,
        "values/extra.md",
        '---\nid: "value.extra"\ntype: "value"\nvisibility: "private"\n'
        'valid_from: "2020-01-01"\n---\n\nNew value.\n',
    )
    after = generate_bundle(_full_codex(codex_path), ["assistant"], purpose="t", created=fixed)
    assert before.bundle_id != after.bundle_id


def test_expiration_is_recorded(codex_path: Path) -> None:
    bundle = generate_bundle(
        _full_codex(codex_path),
        ["assistant"],
        purpose="t",
        expires_in=timedelta(hours=1),
    )
    assert bundle.expires is not None
    assert bundle.expires - bundle.created == timedelta(hours=1)


def test_scope_order_does_not_change_bundle_id(codex_path: Path) -> None:
    fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    one = generate_bundle(_full_codex(codex_path), ["assistant"], purpose="t", created=fixed)
    two = generate_bundle(_full_codex(codex_path), ["assistant"], purpose="t", created=fixed)
    assert one.bundle_id == two.bundle_id


# ----------------------------------------------------------------------
# Trust (HCP-0002)
# ----------------------------------------------------------------------


def test_bundle_declares_trust(codex_path: Path) -> None:
    bundle = generate_bundle(_full_codex(codex_path), ["assistant"], purpose="t")
    assert bundle.trust.status == "declared"
    assert bundle.trust.covenant == "HCP-0002"
    assert bundle.trust.conditions.training is False


def test_generator_never_fabricates_a_response(codex_path: Path) -> None:
    payload = generate_bundle(_full_codex(codex_path), ["assistant"], purpose="t").to_json_dict()
    assert "trust_response" not in payload


def test_trust_response_requires_acknowledged_when_compatible() -> None:
    with pytest.raises(ValueError):
        TrustResponse(acknowledged=False, compatible=True).validate_compatibility()


def test_compatible_with_limitations_is_rejected() -> None:
    response = TrustResponse(acknowledged=True, compatible=True, limitations=["retention applies"])
    with pytest.raises(ValueError):
        response.validate_compatibility()


def test_incompatible_response_is_valid() -> None:
    response = TrustResponse(
        acknowledged=True, compatible=False, limitations=["provider retains data"]
    )
    response.validate_compatibility()


def test_trust_conditions_detect_violations() -> None:
    """A receiver guarantee must not contradict the human's declaration."""
    # strict() is the all-false declaration, which forbids every listed use, so
    # a receiver that trains contradicts it.
    assert "training" in TrustConditions.strict().violations({"training": True})
    assert TrustConditions.strict().violations({"training": False}) == []

    # If the human permits training, a receiver that trains is compliant.
    permitted = TrustConditions(training=True)
    assert permitted.violations({"training": True}) == []

    # If the human forbids it, a receiver that trains is a violation.
    forbidden = TrustConditions(training=False)
    assert "training" in forbidden.violations({"training": True})
    assert forbidden.violations({"training": False}) == []


def test_custom_trust_conditions_are_used(codex_path: Path) -> None:
    conditions = TrustConditions(training=False, human_review=True)
    bundle = generate_bundle(
        _full_codex(codex_path), ["assistant"], purpose="t", trust_conditions=conditions
    )
    assert bundle.trust.conditions.human_review is True


# ----------------------------------------------------------------------
# Scope configuration
# ----------------------------------------------------------------------


def test_default_scopes_are_available(codex: Codex) -> None:
    config = load_scopes(codex)
    assert "assistant" in config.names()
    assert config.source == codex.root / "scopes.yaml"


def test_codex_scopes_file_overrides_defaults(codex_path: Path) -> None:
    (codex_path / "scopes.yaml").write_text(
        "scopes:\n  only-work:\n    include:\n      - life\n    visibility_ceiling: private\n",
        encoding="utf-8",
    )
    codex = Codex.load(codex_path)
    config = load_scopes(codex)
    assert "only-work" in config.names()
    assert "assistant" in config.names()  # defaults remain available


def test_invalid_visibility_ceiling_is_rejected(codex_path: Path) -> None:
    (codex_path / "scopes.yaml").write_text(
        "scopes:\n  bad:\n    include: ['*']\n    visibility_ceiling: top-secret\n",
        encoding="utf-8",
    )
    codex = Codex.load(codex_path)
    with pytest.raises(ScopeConfigError):
        load_scopes(codex)


def test_default_scope_definitions_are_sane() -> None:
    for _name, spec in DEFAULT_SCOPES.items():
        assert spec["include"]
        assert spec["visibility_ceiling"] in {"public", "private", "sensitive", "restricted"}
