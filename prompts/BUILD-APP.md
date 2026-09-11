# HCP Reference Application — Build Prompt

You are the lead engineer building the first reference implementation of the
**Human Context Protocol (HCP)**.

Your task is to turn the specification and repository structure in this
repository into a working, tested, local-first application.

Do not treat this as a generic CRUD app. The central product requirement is:

> **The human owns the context. AI systems consume it.**

The implementation must preserve that principle in its architecture, data model,
CLI/API semantics, permissions, and user interface.

---

## 1. Read first

Before writing code, inspect:

- `README.md`
- `hcp-spec/HCP-0001.md`
- `codex-schema/`
- `templates/`
- `examples/minimal-codex/`
- `docs/architecture.md`
- `docs/security-model.md`

Treat HCP-0001 as the current conceptual authority.

Where the specification is intentionally incomplete, make the smallest reasonable
implementation decision and document it. Do not silently invent protocol
semantics that would belong in a future RFC.

---

## 2. Primary objective

Build a local-first reference application that can:

1. initialize a new Codex
2. validate an existing Codex
3. parse Markdown + YAML frontmatter
4. normalize assertions into a typed internal model
5. inspect Codex status
6. create and edit assertions
7. export machine-readable JSON
8. create selective Context Bundles
9. ingest AI observations
10. review observations
11. accept, edit, reject, or archive observations
12. preserve provenance
13. understand temporal validity
14. work naturally with Git
15. provide a clean path toward future AI/MCP adapters

The application should work completely offline for all core Codex operations.

---

## 3. Recommended technology

Choose a pragmatic, well-supported stack.

Preferred starting point:

- Python 3.12+
- Typer for CLI
- Pydantic for internal data validation
- PyYAML for YAML
- Markdown parsing with a mature library or a small deterministic frontmatter
  parser
- pytest for tests
- JSON Schema for interchange validation

Alternative stacks are acceptable if there is a strong reason, but keep the
architecture language-independent enough that the protocol is not coupled to
the implementation language.

Do not add a database for the first version unless it is genuinely necessary.
The filesystem + Markdown + YAML + Git should be sufficient.

---

## 4. Proposed project layout

Create an implementation under:

```text
src/hcp/
├── __init__.py
├── cli.py
├── config.py
├── errors.py
├── models/
│   ├── __init__.py
│   ├── assertion.py
│   ├── manifest.py
│   └── bundle.py
├── parser/
│   ├── __init__.py
│   ├── frontmatter.py
│   └── markdown.py
├── repository/
│   ├── __init__.py
│   ├── codex.py
│   ├── files.py
│   └── git.py
├── validation/
│   ├── __init__.py
│   └── validator.py
├── bundles/
│   ├── __init__.py
│   └── generator.py
├── observations/
│   ├── __init__.py
│   └── workflow.py
└── output/
    └── json.py

tests/
├── fixtures/
├── test_parser.py
├── test_validation.py
├── test_repository.py
├── test_bundles.py
├── test_observations.py
└── test_cli.py
```

Keep modules small.

---

## 5. CLI

Implement a command such as:

```bash
hcp init ./my-codex
hcp validate ./my-codex
hcp status ./my-codex
hcp add ./my-codex --type belief
hcp show ./my-codex <assertion-id>
hcp export ./my-codex --format json
hcp bundle ./my-codex --scope assistant
hcp observe ./my-codex observation.yaml
hcp review ./my-codex <observation-id> --accept
hcp review ./my-codex <observation-id> --reject
hcp history ./my-codex
```

Also provide:

```bash
hcp --help
hcp version
```

The CLI should have useful error messages and non-zero exit codes on failure.

Do not make Git mandatory for parsing or validation, although a Codex initialized
by `hcp init` should be Git-friendly and may initialize a repository.

---

## 6. Data model

Implement the core objects:

### Manifest

At minimum:

- hcp
- codex_id
- title
- version
- created
- updated
- language
- timezone
- schema versions
- privacy defaults

### Assertion

At minimum:

- hcp
- id
- type
- source
- authority
- status
- confidence
- created
- updated
- valid_from
- valid_until
- visibility
- tags
- derived_from
- supersedes

The body of the Markdown file is the assertion's human-readable content.

Do not discard unknown metadata. Preserve forward-compatible fields where
possible.

---

## 7. ID rules

Implement deterministic validation for assertion IDs.

Initial recommendation:

```text
<namespace>.<name>
```

Examples:

```text
belief.ai.human-agency
preference.communication.direct
goal.project.hcp
obs.2026-09-11.communication.001
```

Do not make IDs depend on filenames alone.

IDs must be unique within a Codex.

Document the exact implemented rule so it can later become HCP-0003.

---

## 8. Authority rules

Enforce these invariants:

### Human-authored

```yaml
source: human
authority: authoritative
```

is valid.

### AI observation

Normally:

```yaml
source: ai
authority: proposed
status: pending
```

is required.

An AI-generated file must not automatically become authoritative merely because
it has a high confidence score.

The review command is the authority transition.

---

## 9. Observation workflow

Implement:

```text
AI observation
      │
      ▼
pending
      │
 ┌────┼─────────────┐
 ▼    ▼             ▼
accept edit         reject
 │    │               │
 ▼    ▼               ▼
auth  auth           rejected
```

When accepting an observation, preserve provenance.

When editing an observation into an authoritative assertion, retain a reference
to the original observation.

Do not erase the original observation by default.

---

## 10. Temporal semantics

Implement:

- `valid_from`
- `valid_until`
- `supersedes`

Validation should reject impossible date relationships such as a `valid_until`
before `valid_from`.

When generating a current-context bundle, include assertions that are active
for the requested time.

Do not delete historical assertions merely because they are no longer current.

---

## 11. Visibility and selective disclosure

Implement:

```text
public
private
sensitive
restricted
```

as explicit metadata.

Implement named scopes, initially through a simple local configuration.

Example conceptual configuration:

```yaml
scopes:
  assistant:
    include:
      - identity
      - preferences
      - values
  career:
    include:
      - identity
      - life.work
      - life.goals
      - preferences.communication
```

The implementation should never treat the entire Codex as an implicit bundle.

A future permission system can become more sophisticated without changing the
core model.

---

## 12. Context Bundle

Generate a machine-readable bundle containing:

- bundle ID
- Codex ID
- HCP version
- purpose
- creation timestamp
- optional expiration
- requested scopes
- included assertions
- integrity metadata placeholder

The bundle should be deterministic for identical input and configuration,
apart from timestamps explicitly defined as dynamic.

Do not include restricted assertions unless the scope explicitly authorizes them.

---

## 13. JSON export

Implement a stable normalized JSON representation.

Requirements:

- UTF-8
- deterministic key ordering where practical
- no accidental secrets
- preserve metadata
- preserve assertion body
- preserve provenance
- represent dates consistently

Write tests for round-trip behavior:

```text
Markdown → model → JSON
```

---

## 14. Validation

Validation should detect:

- missing manifest
- malformed YAML
- malformed frontmatter
- invalid assertion type
- invalid source
- invalid authority
- invalid status
- invalid visibility
- confidence outside 0..1
- invalid dates
- duplicate IDs
- missing required metadata
- invalid AI observation state
- broken `supersedes` references
- broken `derived_from` references
- unsafe or malformed paths

Validation output should identify the file and field whenever possible.

---

## 15. Security requirements

Treat Codex files as sensitive by default.

Never:

- execute Markdown
- execute YAML
- evaluate embedded code
- follow arbitrary shell commands
- import credentials as normal assertions
- send context to a network service during local validation
- silently upload the repository

Be defensive about:

- path traversal
- symlinks
- malformed YAML
- oversized files
- unexpected binary files
- malicious metadata
- prompt-injection content inside imported AI observations

A malicious assertion body is data, not an instruction to the application.

---

## 16. Git integration

Provide read-only Git status/history functionality first.

Useful operations:

```bash
hcp status
hcp history
hcp diff
```

Do not automatically create commits after every edit in the first version.

If the app offers optional commit helpers later, make them explicit.

Never rewrite Git history automatically.

---

## 17. No cloud dependency

Core operations must work with:

```bash
network disabled
```

The application should be able to:

- initialize
- parse
- validate
- edit
- export
- bundle
- review observations

without internet access.

AI integrations are adapters outside the core.

---

## 18. Future MCP architecture

Do not implement a full MCP server unless the core is stable.

However, structure the code so a future adapter can expose concepts such as:

```text
get_identity(scope)
get_preferences(scope)
request_context(request)
propose_observation(observation)
list_observations()
review_observation(id, decision)
```

There must be no unrestricted:

```text
dump_everything()
```

The permission layer should remain between an external agent and the Codex.

---

## 19. Testing

Aim for a serious test suite from the beginning.

At minimum test:

### Parsing

- valid frontmatter
- missing frontmatter
- malformed YAML
- Unicode
- multiline Markdown
- empty body

### Validation

- valid assertion
- invalid type
- invalid confidence
- duplicate IDs
- invalid dates
- invalid authority combinations
- invalid observation state

### Temporal model

- currently valid assertion
- expired assertion
- future assertion
- superseded assertion

### Bundles

- correct scope filtering
- restricted data exclusion
- deterministic content
- expiration handling

### Observations

- ingest
- accept
- edit
- reject
- archive
- provenance preservation

### Security

- path traversal
- unsafe paths
- symlink handling
- unexpected files

### CLI

Every command should have at least one success and one failure test.

---

## 20. Developer experience

Include:

```text
pyproject.toml
README for developers
Makefile or task runner
pytest configuration
lint/format configuration
```

Use a clean formatter and linter.

CI should run:

```text
format check
lint
tests
schema validation
```

Do not add unnecessary dependencies.

---

## 21. Documentation

Update the repository documentation with:

- installation
- quick start
- Codex creation
- assertion creation
- validation
- JSON export
- bundle creation
- observation review
- Git workflow
- security notes
- architecture

Provide one complete example from:

```text
hcp init
      ↓
write assertion
      ↓
hcp validate
      ↓
hcp bundle
      ↓
AI returns observation
      ↓
hcp observe
      ↓
hcp review
      ↓
Git diff
```

---

## 22. UX principles

The application should feel:

- calm
- precise
- trustworthy
- local
- transparent
- technically serious

Avoid:

- gamification
- anthropomorphic claims
- "digital soul" marketing inside the application
- hidden AI behavior
- automatic profiling
- manipulative onboarding
- unnecessary dashboards

The product should communicate that the Codex belongs to the user.

---

## 23. Implementation sequence

Work in this order:

### Step 1
Scaffold the package and test infrastructure.

### Step 2
Implement models.

### Step 3
Implement Markdown/frontmatter parsing.

### Step 4
Implement repository discovery.

### Step 5
Implement validation.

### Step 6
Implement JSON export.

### Step 7
Implement selective bundles.

### Step 8
Implement AI observation workflow.

### Step 9
Add Git read-only integration.

### Step 10
Build CLI commands around stable application services.

### Step 11
Add comprehensive tests.

### Step 12
Document everything.

Do not start with a GUI.

---

## 24. Definition of done for v0.1

The implementation is ready for a first alpha when this workflow works:

```bash
hcp init ~/my-codex

hcp add ~/my-codex --type value
hcp add ~/my-codex --type preference

hcp validate ~/my-codex

hcp export ~/my-codex --format json > codex.json

hcp bundle ~/my-codex --scope assistant > context.json

hcp observe ~/my-codex observation.yaml

hcp review ~/my-codex obs.example --accept

hcp status ~/my-codex
hcp history ~/my-codex
```

with tests covering the complete flow.

---

## 25. Important architectural constraint

Do not confuse HCP with generic AI memory.

The implementation must preserve this distinction:

```text
AI memory:
"What does the AI remember about me?"

HCP:
"What do I choose to tell AI systems about myself?"
```

AI observations are useful because they let the system propose new context.

They are not authoritative merely because an AI produced them.

---

## 26. Final instruction

Build the smallest serious implementation that makes the protocol real.

Do not overengineer.

Do not build a SaaS product.

Do not add a database because it feels conventional.

Do not add blockchain.

Do not add proprietary cloud infrastructure.

Do not invent cryptography.

Make the local Codex excellent first.

Every architectural decision should answer one question:

> **Does this make human-owned context more portable, understandable,
> controllable, and useful across AI systems?**
