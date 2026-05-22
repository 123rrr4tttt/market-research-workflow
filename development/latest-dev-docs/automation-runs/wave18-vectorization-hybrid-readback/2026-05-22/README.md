# Wave18 Vectorization Hybrid Readback

- status: `passed`
- contract_version: `wave18-vectorization-hybrid-readback.v1`
- scope: `deterministic_repo_local_fixture_no_network_no_container_no_live_provider_closure`
- closure_claim_allowed: `false`

## Inputs

| input | status | contract_version | state | closure_claim_allowed |
|---|---|---|---|---|
| wave8 | passed | wave8-search-vectorization-runtime-contract.v1 |  | None |
| wave10 | passed | wave10-vectorization-quality-gate.v1 |  | None |
| wave12 | passed | wave12-provider-readiness-gate.v1 | partial | None |
| wave14 | passed | wave14-vectorization-provider-capability.v1 | partial | False |

## Mode Identity Readback

| mode | case | chunk_order | scores | failures |
|---|---|---|---|---:|
| keyword | keyword_identity_readback | kw-primary, kw-secondary | 2.5, 1.5 | 0 |
| vector | vector_identity_readback | vec-primary, vec-secondary | 1.0, 0.911119 | 0 |
| hybrid | hybrid_identity_readback | hybrid-primary, hybrid-secondary | 1.825, 1.272835 | 0 |

## Gate Semantics

- status passed means: repo-local keyword/vector/hybrid identity, quality trace, and result readback contract are deterministic and machine-checkable
- status passed does not mean: live embedding providers, SearXNG/YaCy live quality, provider=auto promotion, semantic relevance quality, or OSS node SLA are sealed

## Remaining Gaps

- `live_provider_quality_not_closed`: This checker does not call external embedding providers or local open-search services.
- `semantic_embedding_quality_not_proven`: Deterministic vectors prove wiring and trace readback, not production semantic relevance.
- `oss_node_platform_io_sla_not_closed`: OSS node IO can consume the readback fields but still needs node-level live SLA evidence.

## Rerun

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py --out-dir development/latest-dev-docs/automation-runs/wave18-vectorization-hybrid-readback/2026-05-22
```

Full deterministic output is in `hybrid_readback_contract.json`.
