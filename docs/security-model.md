# Security Model

## Security goals

1. Prevent unauthorized context disclosure.
2. Prevent AI observations from escalating authority.
3. Preserve integrity and provenance.
4. Minimize sensitive data exposure.
5. Keep the local repository usable offline.
6. Prevent false claims that a receiving system can honor declared trust
   conditions.

## Trust boundaries

```text
Human/device → Codex → bundle generator → external AI
```

Every boundary should be treated as untrusted unless explicitly authorized.

## Trust declarations

HCP-0002 trust conditions express the human's requirements for a Context
Bundle; they do not override a provider's contracts, infrastructure, or law.
An adapter must disclose known incompatibilities before representing a Covenant
as acknowledged or compatible.

A Context Bundle carries only the human's `status: declared` conditions. Any
receiving-system statement is separately recorded as `trust_response`, so a
provider acknowledgement cannot be mistaken for human authorization or alter
the original declaration.

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
