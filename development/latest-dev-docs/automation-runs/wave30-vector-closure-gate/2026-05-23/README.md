# Wave30 Vector Closure Gate

- status: `passed`
- contract_version: `wave30-vector-closure-gate.v1`
- archive_recommendation: `archive_external_blocked_after_shared_index_sync`

## Decision

| item | value |
|---|---|
| closed repo-local blockers | `retrieval_runs_branches_hits_persistence_not_implemented`, `embedding_qdrant_pgvector_payload_provenance_not_unified`, `agent_matrix_and_main_search_schema_not_joined` |
| remaining repo-local blockers | none |
| external conditions still open | `external_embedding_provider_live_not_verified`, `semantic_embedding_quality_not_proven`, `production_vector_quality_not_proven` |

## Rerun

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave30_vector_closure_gate.py --out-dir development/latest-dev-docs/automation-runs/wave30-vector-closure-gate/2026-05-23
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_search_vector_contracts_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/contract/test_vectorization_contract_unittest.py main/backend/tests/core_business/test_search_core_contract.py
```

Full deterministic output is in `vector_closure_gate.json`.
