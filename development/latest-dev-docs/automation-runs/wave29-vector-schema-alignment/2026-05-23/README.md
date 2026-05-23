# Wave29 Vector Schema Alignment Gate

- status: `passed`
- contract_version: `wave29-vector-schema-alignment-gate.v1`
- scope: `deterministic_repo_local_global_vector_object_and_search_evidence_hit_schema_alignment`
- archive_recommendation: `retain_current_dev_until_persistence_payload_provenance_and_agent_join_are_closed`

## Decision

| item | value |
|---|---|
| closed repo-local blockers | `unified_vector_object_contract_not_frozen`, `main_search_evidence_hit_contract_not_aligned` |
| remaining repo-local blockers | `retrieval_runs_branches_hits_persistence_not_implemented`, `embedding_qdrant_pgvector_payload_provenance_not_unified`, `agent_matrix_and_main_search_schema_not_joined` |
| external conditions still open | `external_embedding_provider_live_not_verified`, `semantic_embedding_quality_not_proven`, `production_vector_quality_not_proven` |

## Rerun

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave29_vector_schema_alignment_gate.py --out-dir development/latest-dev-docs/automation-runs/wave29-vector-schema-alignment/2026-05-23
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_search_vector_contracts_unittest.py main/backend/tests/unit/test_wave29_vector_schema_alignment_gate_unittest.py main/backend/tests/contract/test_vectorization_contract_unittest.py main/backend/tests/core_business/test_search_core_contract.py
```

Full deterministic output is in `vector_schema_alignment_gate.json`.
