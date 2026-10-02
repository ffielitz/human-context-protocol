# hcp — Human Context Protocol reference implementation

> **The human owns the context. AI systems consume it.**

A local-first implementation of [HCP](../README.md): your personal context as a
folder of Markdown you can read, edit, version with Git, and share with any AI
system — selectively, on your terms.

There is no database, no account, and no network call in the core. Your Codex is
a directory on your disk. This package reads it, validates it, and produces
Context Bundles you choose to share.

---

## Install

Requires Python 3.12 or newer.

```bash
cd app
uv venv --python 3.12 .venv        # or: python3 -m venv .venv
uv pip install -e ".[dev]"         # or: .venv/bin/pip install -e ".[dev]"
```

Or with plain pip inside an activated virtualenv:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify:

```bash
hcp version
```

---

## Quick start

```bash
hcp init ~/my-codex
hcp add ~/my-codex --type value --title "Intellectual honesty"
hcp add ~/my-codex --type preference --title "Direct communication"
hcp validate ~/my-codex
hcp export ~/my-codex --format json > codex.json
hcp bundle ~/my-codex --scope assistant --purpose "Personal assistance" > context.json
hcp status ~/my-codex
```

`hcp init` creates:

```text
my-codex/
├── manifest.yaml        Codex identity and privacy defaults
├── scopes.yaml          which context each recipient may receive
├── constitution.md      how your Codex should be interpreted
├── soul.md              unstructured context, in your own words
├── README.md
├── identity/            who you are
├── values/              what you value
├── worldview/           what you believe
├── preferences/         how you like to be treated
├── relationships/       who matters
├── life/                work, goals, experience
└── ai/observations/     AI proposals awaiting your review
```

---

## Commands

| Command | Purpose |
|---|---|
| `hcp init <path>` | Create a new Codex |
| `hcp validate <path>` | Report structural, temporal, and authority problems |
| `hcp status <path>` | Overview: counts, validation, pending reviews, Git state |
| `hcp list <path>` | List assertions with filters |
| `hcp add <path> --type T` | Create a human-authored assertion |
| `hcp show <path> <id>` | Show one assertion in full |
| `hcp edit <path> <id>` | Edit metadata or body text |
| `hcp export <path> --format json` | Export the whole Codex as JSON |
| `hcp bundle <path> --scope S --purpose P` | Create a selective Context Bundle |
| `hcp scopes <path>` | Show configured disclosure scopes |
| `hcp observe <path> <file>` | Ingest an AI observation as pending |
| `hcp review <path> <id> --accept` | Accept, edit, reject, or archive an observation |
| `hcp diff <path>` | Show uncommitted changes (read-only) |
| `hcp history <path>` | Show Git history (read-only) |

Exit codes: `0` success, `1` error, `2` validation failed.

---

## The core model

### Authority

What is true, what you believe, what you prefer, and what an AI inferred are not
the same thing. Every assertion declares where it came from and how much weight
it carries:

```yaml
source: human        # human | ai | import | derived
authority: authoritative   # authoritative | proposed | rejected | archived
status: active             # active | pending | rejected | archived
visibility: private        # public | private | sensitive | restricted
confidence: 0.8            # optional, 0.0 .. 1.0
```

AI observations are **always** ingested as `source: ai`, `authority: proposed`,
`status: pending` — whatever the incoming file claims. Only `hcp review` can
promote them. A high confidence score confers no authority.

### Selective disclosure

A Context Bundle is never "the whole Codex". You name the scope and the purpose:

```bash
hcp bundle . --scope assistant --purpose "Drafting my newsletter"
```

Scopes come from `scopes.yaml`:

```yaml
scopes:
  assistant:
    description: General-purpose assistant context.
    include: [identity, preferences, values]
    visibility_ceiling: private
```

`visibility_ceiling` is a hard limit: a scope capped at `private` can never
export `sensitive` or `restricted` assertions. Restricted context requires a
scope that explicitly sets `visibility_ceiling: restricted` **and** the
`--include-restricted` flag.

Inspect what a bundle withheld and why:

```bash
hcp bundle . --scope assistant --purpose "..." -o context.json --show-excluded
```

### Temporal validity

```yaml
valid_from: "2024-01-01"
valid_until: "2025-06-01"
supersedes: belief.ai.human-agency
```

Old beliefs are not deleted when you change your mind. They are retained with a
validity window and an explicit `supersedes` link, so the evolution of your
point of view stays legible. Bundles include only what is valid at the requested
date (`--at YYYY-MM-DD`).

### Trust (HCP-0002)

Every bundle carries your declaration:

```json
"trust": {
  "covenant": "HCP-0002",
  "status": "declared",
  "conditions": { "training": false, "resale": false, "profiling": false, "...": false }
}
```

`status` is always `declared`. This tool is the human's side of the boundary and
cannot speak for a receiver. A receiving system records its own answer
separately in `trust_response`, and reporting `compatible: false` with
limitations is a valid, important outcome — never present incompatibility as
compliance.

---

## The AI observation workflow

```text
AI observation
      │
      ▼
   pending                 source: ai, authority: proposed
      │
 ┌────┼─────────────┐
 ▼    ▼             ▼
accept edit        reject
 │    │              │
 ▼    ▼              ▼
auth  auth         rejected
```

```bash
hcp observe . observation.yaml          # stored as pending
hcp review . --list                     # see what is waiting
hcp review . obs.2026-09-11.communication.001 --accept
hcp review . obs.2026-09-11.communication.001 --edit --body "Prefer concise summaries."
hcp review . obs.2026-09-11.communication.001 --reject
```

Provenance is preserved on every path. The promoted assertion records the
observation it came from in `derived_from` and `provenance`, and the original
observation is **never deleted** — it is retained as your record of what the AI
claimed and what you decided.

Observations cannot reach a bundle until you accept them. Their bodies are
treated strictly as data: prompt-injection text inside an observation is stored
and displayed, never interpreted or executed.

---

## Git

Git is a first-class part of the data model, not an afterthought. `hcp init`
runs `git init` when Git is available, and the Codex is designed to be committed
as-is.

The Git integration is **read-only**. It never commits, stages, checks out,
resets, or rewrites history. Review your changes, then commit them yourself:

```bash
hcp diff .
git add -A && git commit -m "Add values about intellectual honesty"
hcp history .
```

---

## Security notes

- **YAML is never executed.** Parsing uses `yaml.SafeLoader`; constructs such as
  `!!python/object/apply` are rejected, not run.
- **Markdown is never executed.** Assertion bodies are opaque data.
- **No network access** in any core command. Nothing is uploaded, ever.
- **Path safety.** Every read and write is confined to the Codex. Absolute paths,
  `..` traversal, and symlinks that escape the directory are rejected.
- **Oversized and binary files** are refused rather than parsed.
- **Credentials do not belong in a Codex.** Keep secrets in a password manager.
- Observation bodies are untrusted input and are never treated as instructions.

---

## ID rules

Implemented grammar, documented in `src/hcp/ids.py`:

```text
<segment> ("." <segment>)+      where segment matches [a-z0-9]+(-[a-z0-9]+)*
```

At least one dot is required, so every ID carries a namespace:

```text
belief.ai.human-agency
preference.communication.direct
obs.2026-09-11.communication.001
```

IDs are unique within a Codex and are **not** derived from filenames. This rule
is provisional and intended to become normative in HCP-0003/HCP-0004.

---

## Architecture

```text
CLI  (hcp/cli.py)
 │
 ▼
Application services
 ├── repository/   Codex discovery, safe file access, read-only Git
 ├── parser/       frontmatter + Markdown -> typed assertions
 ├── validation/   structural, temporal, and authority checks
 ├── bundles/      scope filtering and Context Bundle generation
 ├── observations/ ingest and human review workflow
 └── output/       deterministic JSON
        │
        ▼
   HCP data model  (models/)
        │
        ▼
   Markdown + YAML  (canonical)  ⇄  JSON  (derived)
```

AI adapters sit outside this core and consume bundles. There is deliberately no
unrestricted `dump_everything()` entry point; every read goes through a scope.

---

## Development

```bash
make install        # create the venv and install dev dependencies
make test           # run the test suite
make format         # format and auto-fix
make format-check   # what CI runs
make lint           # alias for format-check
make schema         # validate against the JSON Schemas
make ci             # format-check + test + schema
make demo           # run the full workflow end to end in a temp Codex
```

See [DEVELOPING.md](DEVELOPING.md) for the test layout and conventions.

## License

MIT
