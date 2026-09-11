# Security Policy

## Scope

Security issues include:

- unauthorized disclosure of Codex content
- bypassing context-scope restrictions
- authority escalation from AI observation to authoritative assertion
- malicious or ambiguous parsing
- signature verification failures
- unsafe import/export
- credential leakage
- insecure synchronization

## Sensitive information

Never use the Codex as a credential store. Passwords, API keys, private keys,
recovery phrases, and similar secrets are explicitly out of scope.

## Reporting

Until a dedicated security process exists, report suspected vulnerabilities
privately to the project maintainers rather than publishing exploit details
immediately.

Security-sensitive changes should include regression tests.
