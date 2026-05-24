# Wave55 OSS Node Search Quality Gate

- status: `passed`
- contract_version: `wave55-oss-node-search-quality-gate.v1`
- scope: `repo_local_controlled_open_search_and_semantic_quality_no_network`
- local_open_search_quality_claim_allowed: `true`
- repo_local_semantic_quality_claim_allowed: `true`
- production_quality_claim_allowed: `false`

## Quality Readback

- open-search top1_accuracy: `1.0`
- open-search min_top_margin: `14.5`
- semantic top1_accuracy: `1.0`
- semantic min_top_margin: `0.07752`

## Decision

- closed condition: `local_open_search_live_quality_not_sealed`
- reduced condition: `semantic_embedding_quality_not_proven`
- still open for production/live-container scope: `local_open_search_live_container_quality_not_replayed`, `production_semantic_embedding_quality_not_proven`

## Rerun

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py --out-dir development/latest-dev-docs/automation-runs/wave55-oss-node-search-quality-gate/2026-05-23
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave55_oss_node_search_quality_gate_unittest.py
```

Full deterministic output is in `oss_node_search_quality_gate.json`.
