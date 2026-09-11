# HCP — Human Context Protocol

```
                 H U M A N   C O N T E X T   P R O T O C O L
                         YOUR CONTEXT. YOUR AUTHORITY.
```

> **One personal context. Every AI.**

HCP is a proposed open protocol for a simple idea:

**The human owns the context. AI systems consume it.**

Today, every AI assistant builds its own partial model of a person. It lives behind a provider's account, memory system, chat history, or proprietary database. Switching models can mean starting over.

HCP explores a different architecture: a **portable, human-owned context layer** that can move between ChatGPT, Claude, Gemini, local models, agents, and future AI systems.

The first implementation is deliberately boring where it should be boring:

- **Markdown** for human readability
- **YAML metadata** for structure
- **Git** for history, diffs, branches, and rollback
- **JSON** for machine interchange
- **Local-first** storage
- **Explicit authority** for human-authored facts and beliefs
- **Separate AI observations** that require human review
- **Selective disclosure** instead of "send everything"

HCP is not intended to become another proprietary memory silo. The protocol should remain useful even if the company or project behind it disappears.

## The problem

An AI can be extremely capable and still know almost nothing about the person it is helping.

A new assistant may not know:

- how you prefer to communicate
- what you believe
- which principles matter to you
- what your boundaries are
- what your long-term goals are
- who matters in your life
- how you want decisions framed
- which assumptions about you are wrong
- how your views have changed over time

Existing AI memory systems address part of this problem, but usually from the perspective of the AI:

> **What should the AI remember about this user?**

HCP starts from the opposite question:

> **What does this human choose to make available to AI systems?**

That distinction is the foundation of the project.

## The core model

```text
                         ┌─────────────────────┐
                         │     HUMAN / LIFE    │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    PERSONAL CODEX   │
                         │                     │
                         │ Markdown + YAML     │
                         │ Git + history       │
                         │ Human authority     │
                         └──────────┬──────────┘
                                    │
                         selective disclosure
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
       ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
       │  ChatGPT    │       │ Claude / AI │       │ Local Agent │
       └──────┬──────┘       └──────┬──────┘       └──────┬──────┘
              │                     │                     │
              └─────────────────────┼─────────────────────┘
                                    │
                         AI observations / proposals
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  HUMAN REVIEW       │
                         │ accept / edit /     │
                         │ reject / archive    │
                         └──────────┬──────────┘
                                    │
                                    ▼
                              Git revision
```

## A Codex is more than "memory"

A Codex can contain different kinds of assertions:

| Type | Example |
|---|---|
| `fact` | "I work primarily from Berlin." |
| `belief` | "AI systems should preserve human agency." |
| `value` | "I value intellectual honesty." |
| `principle` | "Prefer reversible decisions when uncertainty is high." |
| `preference` | "I prefer direct, structured communication." |
| `boundary` | "Do not expose restricted contact information without explicit permission." |
| `goal` | "Build a portable human-context system." |
| `aspiration` | "Become better at balancing ambition and family life." |
| `identity` | "I am a software/knowledge-work professional." |
| `relationship` | "Jessica is my wife." |
| `experience` | "I have worked with knowledge bases and technical documentation." |
| `observation` | "An AI inferred that I prefer X." |

These categories matter because **"what is true", "what I believe", "what I prefer", and "what an AI inferred" are not the same thing.**

## Human authority vs. AI inference

The most important rule in HCP is:

> **An AI may propose an observation about a person. It may not silently redefine the person.**

For example:

```yaml
type: observation
source: ai
authority: proposed
status: pending
confidence: 0.72
```

The human can then:

```text
accept → authoritative
edit   → authoritative (modified)
reject → rejected
ignore → remains proposed
```

This makes the system auditable and reversible.

## Temporal identity

People change.

HCP therefore treats time as a first-class property. A belief from 2019 does not necessarily become "false" because the person changed their mind in 2026.

Instead, the Codex can express:

```text
old assertion
      │
      └── superseded by ──► current assertion
```

Git preserves the history.

This makes the Codex not merely a profile, but a **versioned record of an evolving human point of view**.

## Selective disclosure

A personal context repository may contain highly sensitive information. It should never be necessary to expose the entire Codex to every AI system.

A restaurant assistant might receive:

```text
preferences.food
preferences.communication
preferences.accessibility
```

A career assistant might receive:

```text
identity.professional
work
goals
preferences.communication
```

A family-planning assistant might receive a different scope.

Restricted contact details should remain behind explicit authorization.

The long-term protocol concept is therefore:

```text
Codex
  │
  ├── public
  ├── private
  ├── sensitive
  └── restricted
          │
          ▼
    Context Bundle
          │
          ▼
      AI system
```

## Repository structure

The first repository is intentionally split into protocol, schema, implementation, examples, and documentation:

```text
human-context/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
│
├── hcp-spec/
│   └── HCP-0001.md
│
├── codex-schema/
│   ├── manifest.schema.json
│   ├── assertion.schema.json
│   └── context-bundle.schema.json
│
├── templates/
│   ├── manifest.yaml
│   ├── constitution.md
│   ├── soul.md
│   └── assertions/
│       ├── fact.md
│       ├── belief.md
│       ├── value.md
│       ├── preference.md
│       ├── boundary.md
│       ├── goal.md
│       └── observation.md
│
├── examples/
│   └── minimal-codex/
│       ├── manifest.yaml
│       ├── constitution.md
│       ├── soul.md
│       ├── identity/
│       ├── values/
│       ├── worldview/
│       ├── preferences/
│       └── ai/
│
├── docs/
│   ├── architecture.md
│   ├── security-model.md
│   ├── roadmap.md
│   └── terminology.md
│
└── prompts/
    └── BUILD-APP.md
```

## Current status

**Experimental / pre-alpha.**

HCP is a proposed protocol, not an established standards-body specification. The goal of this repository is to make the idea concrete enough to implement, test, challenge, and improve.

The initial implementation target is a local-first CLI and library capable of:

1. creating a Codex
2. validating its structure
3. reading Markdown assertions
4. tracking changes with Git
5. producing machine-readable JSON
6. generating selective context bundles
7. importing AI observations
8. reviewing and accepting/rejecting observations
9. preserving provenance and temporal history
10. eventually connecting to AI systems through adapters/MCP

## Design principles

1. **Human ownership**
2. **Human readability**
3. **Machine interoperability**
4. **Explicit authority**
5. **Temporal awareness**
6. **Selective disclosure**
7. **Privacy by architecture**
8. **Provider independence**
9. **Auditability**
10. **Reversibility**
11. **Extensibility**
12. **No silent identity mutation**

## What HCP is not

HCP is not:

- an AI model
- a chatbot
- a proprietary memory database
- a personality test
- a psychological diagnosis
- a digital clone
- a social network
- a blockchain requirement
- a replacement for a password manager
- a place to store private keys, passwords, seed phrases, or API secrets

## Why Markdown?

The canonical representation should be understandable without HCP software.

A person should be able to open the repository in:

- a text editor
- VS Code
- Vim/Neovim
- Obsidian
- GitHub
- a future HCP application

and understand what is written there.

Machine-readable formats are derived from the canonical human representation.

## Why Git?

Git is unusually well suited to identity/context data:

- complete history
- meaningful diffs
- rollback
- branches for hypothetical futures
- merge workflows
- provenance
- offline operation
- interoperability
- mature tooling

A person's evolving worldview can be treated as a versioned knowledge base without pretending that identity is static.

## Security

A real Codex may contain extremely sensitive information.

The reference implementation should follow:

- local-first defaults
- encryption at rest
- encrypted transport
- least privilege
- explicit authorization
- selective disclosure
- no unrestricted `dump_everything` API
- no secret storage
- auditable access
- cryptographic integrity where appropriate

**Never put passwords, recovery phrases, private keys, API keys, or other credentials into a normal Codex.**

Hosted synchronization, if introduced later, should be designed so the service can operate without being able to read the user's plaintext Codex.

## Project vision

The long-term vision is a **human context layer for the AI ecosystem**.

AI providers will continue to compete on models, agents, tools, latency, multimodality, and products.

The person's context should not have to compete with them.

```text
             AI PROVIDERS / MODELS / AGENTS
        ┌────────┬────────┬────────┬────────┐
        │ ChatGPT│ Claude │ Gemini │ Local  │
        └────┬───┴────┬───┴────┬───┴───┬────┘
             │        │        │        │
             └────────┴────────┼────────┘
                               │
                    HUMAN CONTEXT PROTOCOL
                               │
                         PERSONAL CODEX
                               │
                            HUMAN
```

**Your context should belong to you.**

## Roadmap

### Phase 0 — Foundation

- [x] Foundational RFC
- [x] Initial repository structure
- [ ] Formal schemas
- [ ] Validation rules
- [ ] Example Codex

### Phase 1 — Reference implementation

- [ ] CLI
- [ ] parser
- [ ] validator
- [ ] JSON export
- [ ] context bundles
- [ ] observation workflow

### Phase 2 — AI integration

- [ ] provider adapters
- [ ] MCP integration
- [ ] local model support
- [ ] context request protocol
- [ ] observation proposal protocol

### Phase 3 — Security and interoperability

- [ ] cryptographic signatures
- [ ] encrypted sync
- [ ] permission model
- [ ] interoperability test suite
- [ ] formal threat model

### Phase 4 — Ecosystem

- [ ] reference web UI
- [ ] desktop/mobile clients
- [ ] import/export tools
- [ ] third-party integrations
- [ ] enterprise/self-hosted deployment

## A possible future

Imagine creating an AI account tomorrow.

Instead of spending months teaching it who you are, you authorize:

```text
hcp bundle --scope assistant
```

The assistant receives a signed, purpose-specific context bundle.

It knows enough to work with you.

It does not own that knowledge.

You do.

---

**HCP — Human Context Protocol**

*Experimental today. Designed to outlive any particular AI provider.*
