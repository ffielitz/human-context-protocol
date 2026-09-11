# Human–AI Trust Covenant

This Codex uses the Human–AI Trust Covenant defined by
[HCP-0002](../hcp-spec/HCP-0002.md).

## My declaration

When I share a Context Bundle, I retain ownership of my personal context. I
share it only for the stated purpose and expect it to be treated with respect,
restraint, confidentiality, and honesty.

I expect a receiving system to distinguish my assertions from its inferences,
preserve my autonomy, and disclose any condition that it cannot honor. Sharing
my context does not grant ownership of my identity or a separate commercial
right to use it.

## Default conditions

These are the conditions I normally declare in a Context Bundle. Replace them
with your own requirements before using this template.

```yaml
trust:
  covenant: "HCP-0002"
  status: "declared"
  conditions:
    training: false
    derived_models: false
    human_review: false
    third_party_processing: false
    resale: false
    unauthorized_disclosure: false
    profiling: false
    manipulation: false
```

`false` means that the use is not permitted for this bundle. A condition not
included in a bundle is not a condition the bundle declares.

## Compatibility

This Covenant expresses my requirements; it does not override a provider's
Terms of Service, infrastructure, technical limits, or applicable law. A
system that cannot guarantee a declared condition must report that limitation
and mark the interaction incompatible rather than claim compliance.

For a compact, machine-readable example, see
[`examples/context-bundle.yaml`](../examples/context-bundle.yaml).
