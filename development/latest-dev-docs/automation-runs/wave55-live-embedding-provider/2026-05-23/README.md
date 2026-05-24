# Wave55 Live Embedding Provider Gate

- status: `passed`
- contract_version: `wave55-live-embedding-provider-gate.v1`
- scope: `repo_local_live_embedding_provider_no_network_no_external_api`
- local_provider_closure_claim_allowed: `true`
- production_quality_claim_allowed: `false`

## Provider

- provider_id: `repo_local_token_hashing`
- model: `repo-local-token-hashing-v1`
- model_version: `2026-05-23.wave56`
- embedding_dim: `512`
- network_required: `false`
- live_provider_verified: `true`

## Quality Readback

- query_count: `3`
- top1_accuracy: `1.0`
- min_top_margin: `0.625351`

## Decision

- closed for repo-local provider scope: `external_embedding_provider_live_not_verified`
- still open for production: `semantic_embedding_quality_not_proven`, `production_vector_quality_not_proven`

## Rerun

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave55_live_embedding_provider_gate.py --out-dir development/latest-dev-docs/automation-runs/wave55-live-embedding-provider/2026-05-23
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_local_index_service_unittest.py main/backend/tests/unit/test_wave55_live_embedding_provider_gate_unittest.py
```

Full deterministic output is in `live_embedding_provider_gate.json`.
