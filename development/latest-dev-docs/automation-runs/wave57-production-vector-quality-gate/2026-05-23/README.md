# Wave57 Production Vector Quality Gate

- status: `passed`
- contract_version: `wave57-production-vector-quality-gate.v1`
- scope: `production_like_devdocs_corpus_lancedb_vector_store_replay`
- vector_store_backend: `lancedb`
- production_like_vector_quality_claim_allowed: `true`
- production_traffic_claim_allowed: `false`
- target_topic_migration_ready: `true`
- global_manifest_update_performed: `false`

## Corpus

- rows: `27`
- distinct_documents: `27`
- source_groups: `automation_run_artifact, existing_lancedb_jsonl_artifact, target_blocker_docs`
- target_topic_rows: `13`
- existing_lancedb_jsonl_rows: `10`
- automation_artifact_rows: `4`

## Provider And Vector Store

- provider_id: `repo_local_token_hashing`
- model: `repo-local-token-hashing-v1`
- model_version: `2026-05-23.wave56`
- embedding_dim: `512`
- vector_version: `repo-local-live-v2`
- lancedb: `0.24.2`
- pyarrow: `24.0.0`

## Quality Metrics

- cases: `6`
- top1_accuracy: `1.0`
- recall_at_3: `1.0`
- mrr: `1.0`
- min_top2_margin: `0.025746`
- min_hard_negative_margin: `0.025746`

## Decision

- closed condition: `production_vector_quality_not_proven`
- remaining condition: `none`
- global manifest/index update: `not performed`

## Rerun

```bash
PYTHONPATH=main/backend main/backend/.venv311/bin/python ops/search-lab/scripts/wave57_production_vector_quality_gate.py --require-vector-store --out-dir development/latest-dev-docs/automation-runs/wave57-production-vector-quality-gate/2026-05-23
PYTHONPATH=main/backend main/backend/.venv311/bin/python -m pytest -q main/backend/tests/unit/test_wave57_production_vector_quality_gate_unittest.py
```

Full deterministic output is in `production_vector_quality_gate.json`.
