# Security Model

## Security goals

1. Prevent unauthorized context disclosure.
2. Prevent AI observations from escalating authority.
3. Preserve integrity and provenance.
4. Minimize sensitive data exposure.
5. Keep the local repository usable offline.

## Trust boundaries

```text
Human/device → Codex → bundle generator → external AI
```

Every boundary should be treated as untrusted unless explicitly authorized.

## Sensitive information

Restricted data should be isolated and require explicit scope authorization.

Credentials are never Codex data.

## Future work

- encrypted repository support
- signed assertions
- signed bundles
- capability-based access
- audit log
- secure synchronization
