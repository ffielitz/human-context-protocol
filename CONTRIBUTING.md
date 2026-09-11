# Contributing to HCP

HCP is intentionally experimental. Contributions should prioritize clarity,
interoperability, security, and human control over feature volume.

## Before proposing a protocol change

Ask:

1. Does this preserve human authority?
2. Is it understandable without specialized software?
3. Does it introduce unnecessary vendor coupling?
4. Can the change be represented in Markdown and machine-readable form?
5. Does it preserve provenance and history?
6. Does it create new privacy or security risks?

Protocol changes should be documented as RFCs or amendments rather than
silently changing existing semantics.

## Development philosophy

Prefer:

- small composable components
- deterministic parsing
- explicit schemas
- strong validation
- test fixtures
- backwards compatibility
- secure defaults

Avoid:

- opaque proprietary formats
- implicit inference becoming identity
- unrestricted data export APIs
- unnecessary cloud dependencies
- custom cryptography
