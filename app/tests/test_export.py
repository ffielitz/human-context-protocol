"""Tests for deterministic JSON export and round-trip behaviour."""

from __future__ import annotations

import json
from pathlib import Path

from hcp.models.assertion import Assertion
from hcp.output.json import codex_to_dict, dumps, export_codex, to_jsonable
from hcp.parser.markdown import assertion_from_markdown, assertion_to_markdown
from hcp.repository.codex import Codex


def test_export_contains_everything(populated: Codex) -> None:
    payload = codex_to_dict(populated)
    assert payload["kind"] == "codex"
    assert payload["codex_id"] == "codex.test"
    assert payload["assertion_count"] == 1
    entry = payload["assertions"][0]
    assert entry["id"] == "value.honesty"
    assert entry["body"].startswith("I value honest")


def test_export_includes_prose(populated: Codex) -> None:
    payload = codex_to_dict(populated)
    assert "constitution.md" in payload["documents"]


def test_export_can_omit_prose(populated: Codex) -> None:
    payload = codex_to_dict(populated, include_prose=False)
    assert "documents" not in payload


def test_export_is_deterministic(populated: Codex) -> None:
    assert export_codex(populated) == export_codex(populated)


def test_export_is_valid_json(populated: Codex) -> None:
    json.loads(export_codex(populated))


def test_dates_are_iso_strings(populated: Codex) -> None:
    text = export_codex(populated)
    assert '"2024-01-01"' in text


def test_unicode_is_not_escaped(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "values/uni.md",
        '---\nid: "value.uni"\ntype: "value"\n---\n\nWertschätzung: ehrlich. 日本語\n',
    )
    assert "日本語" in export_codex(Codex.load(codex_path))


def test_markdown_to_model_to_json_round_trip(codex_path: Path, write_assertion) -> None:
    """The canonical round trip required by BUILD-APP section 13."""
    source = (
        "---\n"
        'hcp: "0.1"\n'
        'id: "belief.ai.human-agency"\n'
        'type: "belief"\n'
        'source: "human"\n'
        'authority: "authoritative"\n'
        'status: "active"\n'
        "confidence: 0.8\n"
        'created: "2026-09-11"\n'
        'updated: "2026-09-11"\n'
        'valid_from: "2026-09-11"\n'
        "valid_until: null\n"
        'visibility: "private"\n'
        "tags:\n  - ai\n  - human-agency\n"
        "---\n\n"
        "AI systems should strengthen human agency rather than quietly replace it.\n"
    )
    write_assertion("worldview/agency.md", source)

    codex = Codex.load(codex_path)
    assertion = codex.require("belief.ai.human-agency")
    assert assertion.confidence == 0.8
    assert assertion.tags == ["ai", "human-agency"]
    assert assertion.valid_until is None
    assert "human agency" in assertion.body

    payload = codex_to_dict(codex)
    entry = payload["assertions"][0]
    assert entry["id"] == "belief.ai.human-agency"
    assert entry["created"] == "2026-09-11"
    assert entry["tags"] == ["ai", "human-agency"]

    # And back to Markdown, unchanged in meaning.
    again = assertion_from_markdown(assertion_to_markdown(assertion))
    assert again.id == assertion.id
    assert again.body == assertion.body
    assert again.tags == assertion.tags


def test_provenance_survives_export(codex_path: Path) -> None:
    from hcp.models.assertion import Provenance

    codex = Codex.load(codex_path)
    codex.add(
        Assertion(
            id="preference.from-obs",
            type="preference",
            body="Derived.",
            provenance=Provenance(
                origin="human-reviewed-ai-observation",
                observation_id="obs.2026-01-01.a.001",
                decision="edited",
            ),
        )
    )
    entry = codex_to_dict(codex)["assertions"][0]
    assert entry["provenance"]["observation_id"] == "obs.2026-01-01.a.001"


def test_exclude_pending_omits_observations(codex_path: Path, write_assertion) -> None:
    write_assertion(
        "ai/observations/o.md",
        '---\nid: "obs.2026-01-01.a.001"\ntype: "observation"\nsource: "ai"\n'
        'authority: "proposed"\nstatus: "pending"\n---\n\nGuess.\n',
    )
    codex = Codex.load(codex_path)
    with_pending = codex_to_dict(codex, include_pending=True)
    without = codex_to_dict(codex, include_pending=False)
    assert len(with_pending["assertions"]) == 1
    assert without["assertions"] == []


def test_to_jsonable_handles_types() -> None:
    from datetime import date, datetime

    assert to_jsonable(date(2024, 1, 1)) == "2024-01-01"
    assert to_jsonable(datetime(2024, 1, 1, 12, 0)) == "2024-01-01T12:00:00"
    assert to_jsonable({"a": [1, date(2024, 1, 1)]}) == {"a": [1, "2024-01-01"]}
    assert to_jsonable(None) is None


def test_compact_output_is_single_line(populated: Codex) -> None:
    assert "\n" not in dumps(codex_to_dict(populated), indent=None)
