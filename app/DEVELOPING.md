# Developing the HCP reference implementation

## Setup

```bash
cd app
make install          # creates .venv and installs the package with dev extras
.venv/bin/hcp version
```

`make install` uses `uv` when it is available; the resulting environment is
identical either way. Python 3.12 or newer is required.

## Everyday commands

```bash
make test           # pytest
make lint           # ruff check (same as format-check)
make format         # ruff format + autofix
make format-check   # exactly what CI runs
make schema         # validate output against codex-schema/*.json
make ci             # format-check + test + schema
make demo           # run the whole workflow in a temp Codex
```

## Layout

```text
src/hcp/
├── cli.py             Typer CLI; thin, contains no business logic
├── config.py          AppConfig + Codex scaffolding (hcp init)
├── constants.py       Protocol constants and reserved names
├── errors.py          HCPError hierarchy and the Issue record
├── ids.py             Assertion ID grammar (see below)
├── models/            Assertion, Manifest, ContextBundle, Provenance
├── parser/            frontmatter.py, markdown.py — safe parsing
├── repository/        codex.py, files.py, git.py — discovery and safe IO
├── validation/        validator.py — all structural/authority checks
├── bundles/           generator.py — scopes and bundle creation
├── observations/      workflow.py — ingest and human review
└── output/            json.py — deterministic machine representation
```

Layering rule: `cli` may call anything; lower layers may not import `cli`. No
module performs network I/O.

## Test layout

| File | Covers |
|---|---|
| `test_parser.py` | frontmatter, Unicode, multiline, empty body, round trip |
| `test_validation.py` | every §14 check and the authority invariants |
| `test_temporal.py` | validity windows, supersession, history retention |
| `test_repository.py` | discovery, indexing, mutation, prose vs assertions |
| `test_bundles.py` | scope filtering, restricted data, determinism, trust |
| `test_observations.py` | ingest, accept, edit, reject, archive, provenance |
| `test_export.py` | deterministic JSON and Markdown→model→JSON round trip |
| `test_security.py` | path traversal, symlinks, YAML execution, injection |
| `test_git.py` | read-only status/history/diff |
| `test_cli.py` | every command, success and failure |
| `test_schemas.py` | conformance with `codex-schema/*.json` |

Shared fixtures live in `tests/conftest.py`. Every test builds its Codex under
`tmp_path`; the suite never touches a real Codex and never uses the network.

## Conventions

- **Docstrings on everything public.** Google style, with Args/Returns/Raises.
- **Comments explain *why*, not *what*.** If a line needs a comment to say what
  it does, the line should be rewritten instead.
- **Errors carry a machine-readable code.** `Issue.code` is stable and greppable;
  the CLI prints it in brackets.
- **Tolerant parsing, strict validation.** The model normalises representation
  and never raises on semantics; `validator.py` reports them. This is what lets
  `hcp validate` list every problem in one pass.
- **Never lose unknown metadata.** `extra="allow"` plus `unknown_fields()`.
- **No new dependency without a reason.** The runtime needs only typer, pydantic,
  and pyyaml.

## ID grammar

Defined in `src/hcp/ids.py`, provisional until HCP-0003:

```text
<segment> ("." <segment>+      segment := [a-z0-9]+(-[a-z0-9]+)*
```

At least one dot, so every ID is namespaced. IDs are unique per Codex and are
never derived from filenames.

## Security rules to preserve

Any change to these areas must keep the corresponding tests passing:

1. YAML is parsed with `yaml.SafeLoader` only. Never introduce an unsafe loader.
2. Every path goes through `repository/files.py`; never open a path directly.
3. Symlinks are not followed outside the Codex root.
4. Observation bodies are data. Never execute, render, or obey them.
5. `ingest_observation` must always force `source: ai`, `authority: proposed`,
   `status: pending`.
6. The bundle generator must always emit `trust.status: "declared"` and must
   never emit `trust_response`.
7. The Git layer stays read-only.

## Trust condition polarity

HCP-0002 does not define whether `training: false` means "training forbidden" or
"no training restriction". This implementation treats a condition as a
**restriction**: `false` means the use is prohibited. That matches the spec's
description of its own example as "a non-negotiable set". The decision is
documented at `TRUST_CONDITION_POLARITY` in `models/bundle.py`, which is the
single place to change if HCP-0008 fixes the opposite meaning.

## Design decisions worth knowing

- **No database.** Markdown + YAML + Git is sufficient and stays human-readable.
- **Prose files are not assertions.** `constitution.md`, `soul.md`, `README.md`,
  and the `ai/*.md` notes are read but never parsed as assertions.
- **Supersession is temporal.** An assertion superseded in 2021 is still the
  current view in 2020, so `Codex.superseded_at(moment)` is used rather than a
  blanket "superseded" set.
- **`hcp diff` includes untracked files.** A just-created assertion is untracked,
  and plain `git diff` would report nothing right after an edit.
- **Restricting is opt-in twice.** A scope needs `visibility_ceiling: restricted`
  *and* the `--include-restricted` flag before restricted data can be exported.
