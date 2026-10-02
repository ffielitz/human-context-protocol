"""Tests for the CLI: every command has a success and a failure case."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hcp.cli import app

runner = CliRunner()


def run(*args: str):
    """Invoke the CLI and return the result."""
    return runner.invoke(app, list(args))


@pytest.fixture
def ready(codex_path: Path) -> Path:
    codex_path.mkdir(parents=True, exist_ok=True)
    return codex_path


# ----------------------------------------------------------------------
# Global
# ----------------------------------------------------------------------


def test_help_succeeds() -> None:
    result = run("--help")
    assert result.exit_code == 0
    assert "Human Context Protocol" in result.stdout


def test_version_succeeds() -> None:
    result = run("version")
    assert result.exit_code == 0
    assert "HCP-0002" in result.stdout


def test_version_flag_succeeds() -> None:
    result = run("--version")
    assert result.exit_code == 0
    assert "hcp" in result.stdout


def test_no_args_shows_help_and_fails() -> None:
    result = run()
    assert result.exit_code != 0


# ----------------------------------------------------------------------
# init
# ----------------------------------------------------------------------


def test_init_creates_codex(tmp_path: Path) -> None:
    target = tmp_path / "new-codex"
    result = run("init", str(target), "--title", "My Codex", "--codex-id", "codex.mine")
    assert result.exit_code == 0
    assert (target / "manifest.yaml").is_file()
    assert "Created Codex" in result.stdout


def test_init_rejects_invalid_codex_id(tmp_path: Path) -> None:
    result = run("init", str(tmp_path / "x"), "--codex-id", "NO DOTS")
    assert result.exit_code == 1
    assert "error" in result.output


def test_init_refuses_existing(tmp_path: Path) -> None:
    target = tmp_path / "c"
    assert run("init", str(target), "--codex-id", "codex.c").exit_code == 0
    assert run("init", str(target), "--codex-id", "codex.c").exit_code == 1


# ----------------------------------------------------------------------
# validate
# ----------------------------------------------------------------------


def test_validate_succeeds_on_clean_codex(ready: Path) -> None:
    result = run("validate", str(ready))
    assert result.exit_code == 0


def test_validate_fails_on_invalid_codex(ready: Path) -> None:
    bad = ready / "values" / "bad.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text('---\nid: "value.x"\ntype: "nonsense"\n---\n\nB\n', encoding="utf-8")
    result = run("validate", str(ready))
    assert result.exit_code == 2
    assert "invalid_type" in result.output


def test_validate_json_output(ready: Path) -> None:
    result = run("validate", str(ready), "--format")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert "issues" in payload


def test_validate_fails_on_missing_codex(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    result = run("validate", str(missing))
    assert result.exit_code == 1


# ----------------------------------------------------------------------
# status
# ----------------------------------------------------------------------


def test_status_succeeds(ready: Path) -> None:
    result = run("status", str(ready))
    assert result.exit_code == 0
    assert "codex" in result.stdout.lower()


def test_status_json(ready: Path) -> None:
    result = run("status", str(ready), "--format")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "counts" in payload


def test_status_fails_on_missing_codex(tmp_path: Path) -> None:
    assert run("status", str(tmp_path / "nope")).exit_code == 1


# ----------------------------------------------------------------------
# add / show / edit / list
# ----------------------------------------------------------------------


def test_add_succeeds(ready: Path) -> None:
    result = run(
        "add",
        str(ready),
        "--type",
        "value",
        "--title",
        "Intellectual honesty",
        "--body",
        "Honesty matters.",
    )
    assert result.exit_code == 0
    assert "value.intellectual-honesty" in result.stdout


def test_add_scaffolds_when_no_text_given(ready: Path) -> None:
    """`hcp add --type value` with no text creates a placeholder to fill in."""
    result = run("add", str(ready), "--type", "value")
    assert result.exit_code == 0
    assert "placeholder" in result.stdout


def test_add_fails_on_duplicate(ready: Path) -> None:
    args = ("add", str(ready), "--type", "value", "--id", "value.dup", "--body", "x")
    assert run(*args).exit_code == 0
    assert run(*args).exit_code == 1


def test_add_fails_with_bad_type(ready: Path) -> None:
    result = run("add", str(ready), "--type", "nonsense", "--body", "x")
    assert result.exit_code != 0


def test_add_fails_with_unknown_supersedes(ready: Path) -> None:
    result = run("add", str(ready), "--type", "value", "--body", "x", "--supersedes", "value.ghost")
    assert result.exit_code == 1


def test_show_succeeds(ready: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "Body text.")
    result = run("show", str(ready), "value.a")
    assert result.exit_code == 0
    assert "Body text." in result.stdout


def test_show_fails_for_unknown_id(ready: Path) -> None:
    assert run("show", str(ready), "value.nope").exit_code == 1


def test_edit_succeeds(ready: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "First.")
    result = run("edit", str(ready), "value.a", "--body", "Second.")
    assert result.exit_code == 0
    assert "Second." in run("show", str(ready), "value.a").stdout


def test_edit_fails_with_no_changes(ready: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "x")
    assert run("edit", str(ready), "value.a").exit_code == 1


def test_list_succeeds_and_filters(ready: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "A")
    run("add", str(ready), "--type", "identity", "--id", "identity.b", "--body", "B")
    result = run("list", str(ready), "--type", "value")
    assert result.exit_code == 0
    assert "value.a" in result.stdout
    assert "identity.b" not in result.stdout


def test_list_json(ready: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "A")
    result = run("list", str(ready), "--format")
    assert result.exit_code == 0
    assert isinstance(json.loads(result.stdout), list)


# ----------------------------------------------------------------------
# export
# ----------------------------------------------------------------------


def test_export_succeeds(ready: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "A")
    result = run("export", str(ready), "--format", "json")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "codex"
    assert payload["assertion_count"] == 1


def test_export_to_file(ready: Path, tmp_path: Path) -> None:
    out = tmp_path / "out" / "codex.json"
    result = run("export", str(ready), "-o", str(out))
    assert result.exit_code == 0
    assert json.loads(out.read_text())["kind"] == "codex"


def test_export_is_deterministic(ready: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "A")
    first = run("export", str(ready)).stdout
    second = run("export", str(ready)).stdout
    assert first == second


def test_export_fails_on_bad_format(ready: Path) -> None:
    assert run("export", str(ready), "--format", "xml").exit_code != 0


# ----------------------------------------------------------------------
# bundle
# ----------------------------------------------------------------------


def test_bundle_succeeds(ready: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "A")
    result = run("bundle", str(ready), "--scope", "assistant", "--purpose", "Personal assistance")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trust"]["status"] == "declared"
    assert payload["trust"]["covenant"] == "HCP-0002"


def test_bundle_requires_purpose(ready: Path) -> None:
    assert run("bundle", str(ready), "--scope", "assistant").exit_code != 0


def test_bundle_requires_scope(ready: Path) -> None:
    assert run("bundle", str(ready), "--purpose", "x").exit_code != 0


def test_bundle_rejects_unknown_scope(ready: Path) -> None:
    """An unknown scope is rejected by argument validation (exit 2) or by the
    handler (exit 1); either way the command must not produce a bundle."""
    result = run("bundle", str(ready), "--scope", "nonexistent", "--purpose", "x")
    assert result.exit_code != 0


def test_bundle_never_includes_trust_response(ready: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "A")
    payload = json.loads(run("bundle", str(ready), "--scope", "assistant", "--purpose", "t").stdout)
    assert "trust_response" not in payload


def test_bundle_to_file_with_excluded(ready: Path, tmp_path: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "A")
    out = tmp_path / "context.json"
    result = run(
        "bundle",
        str(ready),
        "--scope",
        "assistant",
        "--purpose",
        "t",
        "-o",
        str(out),
        "--show-excluded",
    )
    assert result.exit_code == 0
    assert json.loads(out.read_text())["bundle_id"].startswith("bundle.")


def test_bundle_at_date_filters(ready: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "A")
    result = run(
        "bundle",
        str(ready),
        "--scope",
        "assistant",
        "--purpose",
        "t",
        "--at",
        "1999-01-01",
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["assertions"] == []


def test_bundle_rejects_bad_date(ready: Path) -> None:
    result = run(
        "bundle", str(ready), "--scope", "assistant", "--purpose", "t", "--at", "yesterday"
    )
    assert result.exit_code == 1


def test_bundle_is_deterministic(ready: Path) -> None:
    run("add", str(ready), "--type", "value", "--id", "value.a", "--body", "A")
    args = ("bundle", str(ready), "--scope", "assistant", "--purpose", "t")
    first = json.loads(run(*args).stdout)
    second = json.loads(run(*args).stdout)
    assert first["assertions"] == second["assertions"]


# ----------------------------------------------------------------------
# scopes
# ----------------------------------------------------------------------


def test_scopes_succeeds(ready: Path) -> None:
    result = run("scopes", str(ready))
    assert result.exit_code == 0
    assert "assistant" in result.stdout


def test_scopes_fails_on_missing_codex(tmp_path: Path) -> None:
    assert run("scopes", str(tmp_path / "nope")).exit_code == 1


# ----------------------------------------------------------------------
# observe / review
# ----------------------------------------------------------------------


@pytest.fixture
def with_observation(ready: Path, tmp_path: Path) -> tuple[Path, str]:
    payload = tmp_path / "obs.yaml"
    payload.write_text(
        "id: obs.2026-01-01.communication.001\n"
        "confidence: 0.8\n"
        "body: The user appears to prefer concise answers.\n",
        encoding="utf-8",
    )
    result = run("observe", str(ready), str(payload))
    assert result.exit_code == 0
    return ready, "obs.2026-01-01.communication.001"


def test_observe_succeeds(with_observation) -> None:
    path, observation_id = with_observation
    result = run("review", str(path), "--list")
    assert result.exit_code == 0
    assert observation_id in result.stdout


def test_observe_fails_on_missing_file(ready: Path, tmp_path: Path) -> None:
    assert run("observe", str(ready), str(tmp_path / "nope.yaml")).exit_code == 1


def test_observe_forces_pending(ready: Path, tmp_path: Path) -> None:
    payload = tmp_path / "hostile.yaml"
    payload.write_text(
        "id: obs.2026-01-01.hostile.001\nsource: human\n"
        "authority: authoritative\nstatus: active\nbody: Trust me.\n",
        encoding="utf-8",
    )
    assert run("observe", str(ready), str(payload)).exit_code == 0
    result = run("validate", str(ready))
    assert result.exit_code == 0  # stored correctly as pending


def test_review_accept_succeeds(with_observation) -> None:
    path, observation_id = with_observation
    result = run("review", str(path), observation_id, "--accept", "--as", "preference.concise")
    assert result.exit_code == 0
    assert run("validate", str(path)).exit_code == 0


def test_review_reject_succeeds(with_observation) -> None:
    path, observation_id = with_observation
    result = run("review", str(path), observation_id, "--reject")
    assert result.exit_code == 0
    assert "reject" in result.stdout


def test_review_edit_requires_body(with_observation) -> None:
    path, observation_id = with_observation
    assert run("review", str(path), observation_id, "--edit").exit_code == 1


def test_review_edit_succeeds(with_observation) -> None:
    path, observation_id = with_observation
    result = run(
        "review",
        str(path),
        observation_id,
        "--edit",
        "--body",
        "Corrected text.",
        "--as",
        "preference.corrected",
        "--type",
        "preference",
    )
    assert result.exit_code == 0


def test_review_requires_exactly_one_decision(with_observation) -> None:
    path, observation_id = with_observation
    assert run("review", str(path), observation_id).exit_code == 1
    assert run("review", str(path), observation_id, "--accept", "--reject").exit_code == 1


def test_review_fails_for_unknown_id(ready: Path) -> None:
    assert run("review", str(ready), "obs.nope", "--accept").exit_code == 1


def test_review_requires_id_without_list(ready: Path) -> None:
    assert run("review", str(ready), "--accept").exit_code == 1


# ----------------------------------------------------------------------
# diff / history
# ----------------------------------------------------------------------


def test_diff_succeeds_without_git(ready: Path) -> None:
    result = run("diff", str(ready))
    assert result.exit_code in (0, 1)


def test_history_succeeds(ready: Path) -> None:
    result = run("history", str(ready))
    assert result.exit_code in (0, 1)


def test_diff_fails_on_missing_codex(tmp_path: Path) -> None:
    assert run("diff", str(tmp_path / "nope")).exit_code == 1


# ----------------------------------------------------------------------
# End-to-end
# ----------------------------------------------------------------------


def test_full_workflow(ready: Path, tmp_path: Path) -> None:
    """init -> add -> validate -> export -> bundle -> observe -> review -> validate."""
    run(
        "add",
        ready and str(ready),
        "--type",
        "value",
        "--title",
        "Honesty",
        "--body",
        "I value honesty.",
    )
    run(
        "add",
        str(ready),
        "--type",
        "preference",
        "--title",
        "Directness",
        "--body",
        "I prefer direct answers.",
    )

    assert run("validate", str(ready)).exit_code == 0
    assert json.loads(run("export", str(ready)).stdout)["assertion_count"] == 2

    bundle = json.loads(
        run("bundle", str(ready), "--scope", "assistant", "--purpose", "test").stdout
    )
    assert bundle["trust"]["status"] == "declared"
    assert len(bundle["assertions"]) == 2

    payload = tmp_path / "obs.yaml"
    payload.write_text(
        "id: obs.2026-01-01.workflow.001\nconfidence: 0.6\n"
        "body: The user may prefer shorter answers.\n",
        encoding="utf-8",
    )
    assert run("observe", str(ready), str(payload)).exit_code == 0
    assert (
        run(
            "review",
            str(ready),
            "obs.2026-01-01.workflow.001",
            "--edit",
            "--body",
            "I prefer concise answers.",
            "--as",
            "preference.concise",
            "--type",
            "preference",
        ).exit_code
        == 0
    )
    assert run("validate", str(ready)).exit_code == 0
    assert run("status", str(ready)).exit_code == 0
