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
