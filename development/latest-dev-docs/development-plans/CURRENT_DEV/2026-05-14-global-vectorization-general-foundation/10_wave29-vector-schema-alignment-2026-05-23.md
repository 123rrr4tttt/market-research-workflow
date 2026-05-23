# Wave29 Global Vector Object / Evidence-Hit Schema Alignment

- Status: repo-local schema alignment gate passed; global topic remains partial
- Decision date: 2026-05-23
- Evidence: [wave29-vector-schema-alignment/2026-05-23](../../../automation-runs/wave29-vector-schema-alignment/2026-05-23/README.md)
- Checker: `ops/search-lab/scripts/wave29_vector_schema_alignment_gate.py`
- Unit gates:
  - `main/backend/tests/unit/test_search_vector_contracts_unittest.py`
  - `main/backend/tests/unit/test_wave29_vector_schema_alignment_gate_unittest.py`
  - `main/backend/tests/contract/test_vectorization_contract_unittest.py`
  - `main/backend/tests/core_business/test_search_core_contract.py`
- Shared index changes: none

## Result

Wave29 closes the narrow repo-local blocker chain for `global vector object / evidence-hit schema alignment`.

The main search response now exposes a deterministic parallel `evidence_hits` contract without changing the legacy `results` list. Each evidence hit carries:

- `contract_version=search_evidence_hit.v1`
- `query_group_id`
- `matrix_branch_id`
- `retrieval_mode`
- `retrieval_family=main_search`
- `backend`
- `evidence_class`
- `verification_state`
- `rank_features`
- `provenance`
- nested `global_vector_object` with `contract_version=global_vector_object.v1`

The global vector object builder freezes the shared fields for `project_key`, `object_type`, `object_id`, `chunk_id`, `source_id`, `document_id`, `vector_version`, `embedding_model`, `embedding_dim`, `matrix_branch_id`, and provenance. The gate covers deterministic BM25/OpenSearch, Qdrant, and pgvector-shaped rows.

## Closed Repo-Local Blockers

- `unified_vector_object_contract_not_frozen`
- `main_search_evidence_hit_contract_not_aligned`

## Remaining Repo-Local Blockers

- `retrieval_runs_branches_hits_persistence_not_implemented`
- `embedding_qdrant_pgvector_payload_provenance_not_unified`
- `agent_matrix_and_main_search_schema_not_joined`

## External Conditions Still Open

- `external_embedding_provider_live_not_verified`
- `semantic_embedding_quality_not_proven`
- `production_vector_quality_not_proven`

## Archive Recommendation

Retain this topic in `CURRENT_DEV`.

Wave29 materially reduces the repo-local blocker set, but the topic should not move to `ARCHIVE_CLOSED` or `ARCHIVE_EXTERNAL_BLOCKED` until retrieval persistence, stored payload provenance, and Agent matrix/main-search schema joining are closed. Those remaining blockers are still repository work, not external provider conditions.

## Verification

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave29_vector_schema_alignment_gate.py --out-dir development/latest-dev-docs/automation-runs/wave29-vector-schema-alignment/2026-05-23
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_search_vector_contracts_unittest.py main/backend/tests/unit/test_wave29_vector_schema_alignment_gate_unittest.py main/backend/tests/contract/test_vectorization_contract_unittest.py main/backend/tests/core_business/test_search_core_contract.py
```
