# Changelog

All notable changes to the HCP project will be documented here.

## [Unreleased]

### Added

- Initial repository structure
- HCP-0001 founding specification
- HCP-0002 Human–AI Trust Covenant
- Context Bundle trust declaration schema
- Trust Covenant template
- Codex templates
- Initial JSON schemas
- Minimal example Codex
- Application build prompt
- Reference CLI implementation in `app/` (init, validate, status, list, add,
  show, edit, export, bundle, scopes, observe, review, diff, history)
- Selective disclosure via named scopes with a per-scope visibility ceiling
- Deterministic JSON export with Markdown → model → JSON round-trip tests
- AI observation workflow with forced pending state and provenance-preserving
  accept/edit/reject/archive
- Read-only Git integration (status, history, diff including untracked files)
- 247 tests covering parsing, validation, temporal semantics, bundles,
  observations, security, Git, CLI, and JSON Schema conformance
