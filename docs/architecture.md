# Architecture

The reference implementation should be layered:

```text
CLI / UI
   │
   ▼
Application services
   │
   ├── Codex parser
   ├── validator
   ├── repository/index
   ├── observation engine
   ├── bundle generator
   ├── trust handshake evaluator
   └── policy/permission engine
             │
             ▼
        HCP data model
             │
             ├── Markdown + YAML
             └── JSON
```

Adapters sit outside the core:

```text
                 HCP Core
              /      |      \
          ChatGPT  MCP     Local AI
           adapter adapter  adapter
```

The core must remain usable without any provider integration.

An adapter that receives a Context Bundle with declared trust conditions must
report whether its provider and infrastructure can honor those conditions. It
must not report incompatible conditions as guaranteed.

The bundle's `trust` object is a human declaration and remains
`status: declared`. An adapter records its own result separately as
`trust_response`; it must not mutate the declaration to make an
acknowledgement or compatibility result appear human-authorized.
