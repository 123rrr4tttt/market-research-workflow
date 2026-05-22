# Wave19 Vectorization Provider Manifest Readback

- status: `passed`
- manifest_state: `partial`
- contract_version: `wave19-vectorization-provider-manifest.v1`
- scope: `deterministic_repo_manifest_no_network_no_container_no_live_provider_closure`
- closure_claim_allowed: `false`

## Manifest Rows

| mode | keyword | vector | hybrid | fallback_mode | fallback_reason | trace_quality | live_provider_verified |
|---|---:|---:|---:|---|---|---|---:|
| keyword | true | false | false | none |  | passed | false |
| vector | false | true | false | keyword | RuntimeError | passed | false |
| hybrid | true | true | true | keyword | RuntimeError | passed | false |

## External Provider Boundary

- external_provider_sealed: `false`
- provider_auto_promotion_allowed: `false`

## Gap Codes

- `external_embedding_provider_live_not_verified`
- `local_open_search_live_quality_not_sealed`
- `oss_node_platform_io_sla_not_closed`
- `provider_auto_promotion_not_allowed`
- `semantic_embedding_quality_not_proven`

## Gate Semantics

- status passed means: keyword/vector/hybrid capability, fallback, and trace-quality manifest fields can be read back deterministically from repo-controlled artifacts
- status passed does not mean: live embedding providers, local open-search quality, provider=auto promotion, semantic relevance quality, or OSS node SLA are closed

## Rerun

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py --out-dir development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22
```

Full deterministic output is in `provider_manifest_readback.json`.
