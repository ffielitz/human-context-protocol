"""Validate generated output against the repository's JSON Schemas.

These tests assert that this implementation actually conforms to
``codex-schema/*.json`` from the protocol repository, not merely to its own
internal model. They are skipped when ``jsonschema`` or the schema directory is
unavailable so the core suite still runs in a bare environment.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from hcp.bundles.generator import generate_bundle
from hcp.repository.codex import Codex

jsonschema = pytest.importorskip("jsonschema", reason="jsonschema is a dev dependency")

#: The protocol repository's schema directory, one level above ``app/``.
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "codex-schema"

pytestmark = pytest.mark.skipif(
    not SCHEMA_DIR.is_dir(), reason="codex-schema/ not available next to the app"
)


def _load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def assertion_schema() -> dict:
    return _load("assertion.schema.json")


@pytest.fixture(scope="module")
def bundle_schema() -> dict:
    return _load("context-bundle.schema.json")


@pytest.fixture(scope="module")
def manifest_schema() -> dict:
    return _load("manifest.schema.json")


def test_manifest_conforms(codex: Codex, manifest_schema: dict) -> None:
    jsonschema.validate(codex.manifest.to_json_dict(), manifest_schema)


def test_assertion_conforms(populated: Codex, assertion_schema: dict) -> None:
    for assertion in populated.assertions:
        jsonschema.validate(assertion.to_json_dict(), assertion_schema)


def test_bundle_conforms(codex_path: Path, bundle_schema: dict, write_assertion) -> None:
    write_assertion(
        "values/honesty.md",
        '---\nid: "value.honesty"\ntype: "value"\nvisibility: "private"\n'
        'valid_from: "2020-01-01"\n---\n\nHonesty matters.\n',
    )
    codex = Codex.load(codex_path)
    bundle = generate_bundle(
        codex,
        ["assistant"],
        purpose="schema conformance",
        at=date(2025, 1, 1),
        created=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        expires_in=timedelta(hours=1),
    )
    payload = bundle.to_json_dict()
    jsonschema.validate(payload, bundle_schema)
    assert payload["trust"]["status"] == "declared"


def test_observation_conforms(codex_path: Path, assertion_schema: dict, tmp_path: Path) -> None:
    from hcp.observations.workflow import ingest_observation

    payload = tmp_path / "obs.yaml"
    payload.write_text(
        "id: obs.2026-01-01.schema.001\nconfidence: 0.7\nbody: An observation.\n",
        encoding="utf-8",
    )
    codex = Codex.load(codex_path)
    result = ingest_observation(codex, payload)
    jsonschema.validate(codex.require(result.observation_id).to_json_dict(), assertion_schema)


def test_bundle_schema_requires_trust(bundle_schema: dict) -> None:
    assert "trust" in bundle_schema["required"]
    assert bundle_schema["properties"]["trust"]["properties"]["status"]["const"] == "declared"


def test_bundle_schema_forbids_mutating_declaration(bundle_schema: dict) -> None:
    """The human declaration must not gain extra fields such as a status change."""
    assert bundle_schema["properties"]["trust"]["additionalProperties"] is False


def test_example_codex_validates(codex_path: Path, write_assertion, tmp_path: Path) -> None:
    """A hand-written Codex using only documented fields validates cleanly."""
    write_assertion(
        "worldview/beliefs.md",
        '---\nhcp: "0.1"\nid: "belief.ai.human-agency"\ntype: "belief"\n'
        'source: "human"\nauthority: "authoritative"\nstatus: "active"\n'
        "confidence: 0.8\n"
        'created: "2026-09-11"\nupdated: "2026-09-11"\nvalid_from: "2026-09-11"\n'
        "valid_until: null\n"
        'visibility: "private"\n'
        "tags:\n  - ai\n"
        "---\n\n"
        "AI systems should strengthen human agency.\n",
    )
    write_assertion(
        "ai/observations/o.md",
        '---\nhcp: "0.1"\nid: "obs.2026-09-11.communication.001"\ntype: "observation"\n'
        'source: "ai"\nauthority: "proposed"\nstatus: "pending"\nconfidence: 0.78\n'
        'created: "2026-09-11"\nupdated: "2026-09-11"\nvalid_from: "2026-09-11"\n'
        "valid_until: null\n"
        'visibility: "private"\n'
        'derived_from:\n  - "conversation:example"\n'
        "---\n\n"
        "The user appears to prefer concise answers.\n",
    )
    codex = Codex.load(codex_path)
    schema = _load("assertion.schema.json")
    for assertion in codex.assertions:
        jsonschema.validate(assertion.to_json_dict(), schema)

    from hcp.validation.validator import validate_codex

    assert validate_codex(codex).ok


def test_repository_example_codex_is_usable(manifest_schema: dict, assertion_schema: dict) -> None:
    """The example Codex shipped in the repository must load, validate, and bundle."""
    example = Path(__file__).resolve().parents[2] / "examples" / "minimal-codex"
    if not example.is_dir():
        pytest.skip("examples/minimal-codex not available")

    from hcp.bundles.generator import generate_bundle
    from hcp.repository.codex import Codex
    from hcp.validation.validator import validate_codex

    codex = Codex.load(example)
    assert codex.manifest.codex_id == "codex.example.minimal"
    assert codex.assertions, "the example Codex should contain assertions"

    jsonschema.validate(codex.manifest.to_json_dict(), manifest_schema)
    for assertion in codex.assertions:
        jsonschema.validate(assertion.to_json_dict(), assertion_schema)

    report = validate_codex(codex)
    assert report.ok, [i.format() for i in report.errors]

    bundle = generate_bundle(codex, ["assistant"], purpose="example", at=date(2025, 1, 1))
    assert bundle.trust.status == "declared"
    jsonschema.validate(bundle.to_json_dict(), _load("context-bundle.schema.json"))
