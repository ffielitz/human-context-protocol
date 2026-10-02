"""Tests for the temporal model: validity windows and supersession."""

from __future__ import annotations

from datetime import date

from hcp.models.assertion import Assertion


def _assertion(**kwargs) -> Assertion:
    data = {
        "id": "belief.ai.test",
        "type": "belief",
        "source": "human",
        "authority": "authoritative",
        "status": "active",
        "body": "Body.",
    }
    data.update(kwargs)
    return Assertion(**data)


def test_current_assertion_is_valid() -> None:
    assertion = _assertion(valid_from=date(2020, 1, 1), valid_until=date(2030, 1, 1))
    assert assertion.is_valid_at(date(2025, 6, 1))
    assert assertion.temporal_state(date(2025, 6, 1)) == "current"


def test_expired_assertion_is_invalid_after_valid_until() -> None:
    assertion = _assertion(valid_from=date(2019, 1, 1), valid_until=date(2021, 1, 1))
    assert assertion.is_expired(date(2022, 1, 1))
    assert not assertion.is_valid_at(date(2022, 1, 1))
    assert assertion.temporal_state(date(2022, 1, 1)) == "expired"


def test_validity_is_inclusive_on_both_bounds() -> None:
    assertion = _assertion(valid_from=date(2020, 1, 1), valid_until=date(2020, 12, 31))
    assert assertion.is_valid_at(date(2020, 1, 1))
    assert assertion.is_valid_at(date(2020, 12, 31))


def test_future_assertion_is_invalid_before_valid_from() -> None:
    assertion = _assertion(valid_from=date(2030, 1, 1))
    assert assertion.is_future(date(2025, 1, 1))
    assert not assertion.is_valid_at(date(2025, 1, 1))
    assert assertion.temporal_state(date(2025, 1, 1)) == "future"


def test_undated_assertion_is_always_valid() -> None:
    assertion = _assertion()
    assert assertion.is_valid_at(date(1999, 1, 1))
    assert assertion.is_valid_at(date(2099, 1, 1))
    assert assertion.temporal_state(date(2025, 1, 1)) == "undated"


def test_open_ended_assertion_is_always_valid() -> None:
    assertion = _assertion(valid_from=date(2020, 1, 1))
    assert assertion.is_valid_at(date(2099, 1, 1))


def test_historical_assertions_are_retained_not_deleted(codex_path, write_assertion) -> None:
    """A belief from 2019 stays in the Codex when it stops being current."""
    from hcp.repository.codex import Codex

    write_assertion(
        "worldview/old.md",
        '---\nid: "belief.ai.old"\ntype: "belief"\nvalid_from: "2019-01-01"\n'
        'valid_until: "2021-01-01"\n---\n\nI believed this once.\n',
    )
    write_assertion(
        "worldview/new.md",
        '---\nid: "belief.ai.new"\ntype: "belief"\nvalid_from: "2021-01-01"\n'
        'supersedes: "belief.ai.old"\n---\n\nI believe this now.\n',
    )
    codex = Codex.load(codex_path)
    assert len(codex.assertions) == 2
    assert codex.require("belief.ai.old") is not None
    assert codex.superseded_ids() == {"belief.ai.old"}


def test_active_at_excludes_expired_and_superseded(codex_path, write_assertion) -> None:
    from hcp.repository.codex import Codex

    write_assertion(
        "worldview/old.md",
        '---\nid: "belief.ai.old"\ntype: "belief"\nvalid_from: "2019-01-01"\n'
        'valid_until: "2021-01-01"\n---\n\nOld.\n',
    )
    write_assertion(
        "worldview/new.md",
        '---\nid: "belief.ai.new"\ntype: "belief"\nvalid_from: "2021-01-01"\n'
        'supersedes: "belief.ai.old"\n---\n\nNew.\n',
    )
    codex = Codex.load(codex_path)
    current = {a.id for a in codex.active_at(date(2025, 1, 1))}
    assert current == {"belief.ai.new"}

    historical = {a.id for a in codex.active_at(date(2020, 1, 1))}
    assert historical == {"belief.ai.old"}


def test_active_at_excludes_pending_observations(codex_path, write_assertion) -> None:
    from hcp.repository.codex import Codex

    write_assertion(
        "ai/observations/o.md",
        '---\nid: "obs.2026-01-01.a.001"\ntype: "observation"\nsource: "ai"\n'
        'authority: "proposed"\nstatus: "pending"\n---\n\nGuess.\n',
    )
    codex = Codex.load(codex_path)
    assert codex.active_at(date(2026, 6, 1)) == []
