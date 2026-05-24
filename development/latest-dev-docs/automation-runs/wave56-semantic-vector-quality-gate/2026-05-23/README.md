# Wave56 Semantic Vector Quality Gate

- status: `passed`
- contract_version: `wave56-semantic-vector-quality-gate.v1`
- scope: `repo_local_production_like_semantic_vector_quality_no_network_no_live_traffic`
- semantic_quality_claim_allowed: `true`
- production_quality_claim_allowed: `false`

## Provider

- provider_id: `repo_local_token_hashing`
- model: `repo-local-token-hashing-v1`
- model_version: `2026-05-23.wave56`
- embedding_dim: `512`
- vector_version: `repo-local-live-v2`
- network_required: `false`

## Quality Metrics

- domains: `5`
- cases: `8`
- top1_accuracy: `1.0`
- recall_at_3: `1.0`
- mrr: `1.0`
- min_top2_margin: `0.170647`
- min_hard_negative_margin: `0.170647`

## Decision

- closed for repo-local semantic provider scope: `semantic_embedding_quality_not_proven`
- reduced but still not globally closed: `production_vector_quality_not_proven`
- still requires live production replay before target migration: `production_vector_quality_not_proven`

## Rerun

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave56_semantic_vector_quality_gate.py --out-dir development/latest-dev-docs/automation-runs/wave56-semantic-vector-quality-gate/2026-05-23
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_local_index_service_unittest.py main/backend/tests/unit/test_wave55_live_embedding_provider_gate_unittest.py main/backend/tests/unit/test_wave56_semantic_vector_quality_gate_unittest.py
```

Full deterministic output is in `semantic_vector_quality_gate.json`.
