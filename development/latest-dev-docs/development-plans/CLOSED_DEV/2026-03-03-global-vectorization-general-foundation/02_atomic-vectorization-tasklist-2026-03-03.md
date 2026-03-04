# Atomic Vectorization Tasklist (2026-03-03)

## 0. Execution Rules

- Each task is atomic and idempotent.
- Each task keeps fixed fields: `Goal / Input / Output / Acceptance / Minimal Gate / Failure Isolation`.
- One task only changes one concern; do not silently expand scope.
- Any API/schema/contract change must include tests in the same task.
- Tenant isolation is mandatory: all read/write paths must enforce `project_key`.

## 1. Taskboard

### T1 - Gate-0 frozen-field contract check

Goal:
- Freeze upstream vectorization fields before M1.

Input:
- `main/backend/tests/core_business/test_ingest_core_contract.py`
- frozen fields list from global vectorization plan.

Output:
- Contract assertions for frozen fields are explicit and stable.

Acceptance:
- Missing/renamed frozen field fails contract tests.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest tests/core_business/test_ingest_core_contract.py -q`

Failure Isolation:
- Revert only frozen-field assertions; do not touch ingest write workflow.

### T2 - Object identity and idempotency key enforcement

Goal:
- Enforce `uk_vector_object=(project_key, object_type, object_id, vector_version)`.

Input:
- vector object identity design.

Output:
- Identity rule enforced in model/policy path.

Acceptance:
- Duplicate write for same identity does not create new vector row.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest -m "contract and not external" -q`

Failure Isolation:
- Roll back identity policy only; keep existing search behavior unchanged.

### T3 - `vector_objects` schema migration

Goal:
- Add/align `vector_objects` minimal schema with unique constraint.

Input:
- `main/backend/app/models/entities.py`
- migration files.

Output:
- Migration contains required columns + unique key + baseline indexes.

Acceptance:
- Migration apply/rollback works; unique key prevents duplicates.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest -m "integration and not external" -q`

Failure Isolation:
- Roll back this migration only.

### T4 - Vector metadata/link/job schema baseline

Goal:
- Add/align `vector_metadata`, `vector_links`, `vector_jobs` baseline tables/structures.

Input:
- vector data model section in plan.

Output:
- Migration + model entries for metadata/link/job tracking.

Acceptance:
- Job status and provenance fields can be stored and queried.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest -m "integration and not external" -q`

Failure Isolation:
- Revert metadata/link/job additions only.

### T5 - Embedding input contract normalization

Goal:
- Normalize pipeline input fields (`raw_text/clean_text/language/source_domain/effective_time/keep_for_vectorization`).

Input:
- `main/backend/app/services/indexer/policy.py`

Output:
- Unified validation for embedding write entry.

Acceptance:
- Invalid payload fails fast with stable error code.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest tests/unit/test_policy_indexer_vector_contract_unittest.py -q`

Failure Isolation:
- Roll back input validator only.

### T6 - Chunking config by object type

Goal:
- Make `chunk_size/chunk_overlap` configurable with per-object-type overrides.

Input:
- indexer policy/config modules.

Output:
- Config map for `document/chunk/entity/relation/report_fact` chunk strategy.

Acceptance:
- Different object types can load distinct chunk parameters.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest -m "unit and not external" -q`

Failure Isolation:
- Revert chunk config mapping only.

### T7 - Retry, backoff, and DLQ semantics

Goal:
- Implement bounded retries and DLQ with `quality_flags=embedding_failed`.

Input:
- task/worker pipeline modules.

Output:
- Retry policy + failure state transitions + DLQ markers.

Acceptance:
- Exceeded retries move task to DLQ and keep task traceability.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest -m "integration and not external" -q`

Failure Isolation:
- Revert retry/DLQ behavior only.

### T8 - M1 document/chunk embedding write path

Goal:
- Enable first M1 object types (`document`, `chunk`) through full embedding write path.

Input:
- model + policy + storage baseline.

Output:
- End-to-end write path for document/chunk embeddings.

Acceptance:
- Idempotent writes pass; multi-version rows are readable.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest tests/contract/test_vectorization_contract_unittest.py -q`

Failure Isolation:
- Revert document/chunk write integration only.

### T9 - Unified vector search API skeleton

Goal:
- Implement `POST /api/v1/vector/search` with envelope response.

Input:
- `main/backend/app/api/*`
- search service modules.

Output:
- API returns `status/data/error/meta` and `matches[]` structure.

Acceptance:
- Core response shape and errors are contract-stable.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest tests/integration/test_search_api_unittest.py -q`
- `cd main/backend && .venv311/bin/python -m pytest tests/core_business/test_search_core_contract.py -q`

Failure Isolation:
- Revert vector API handler only.

### T10 - Tenant isolation and auth binding for vector search

Goal:
- Enforce server-side `project_key` isolation and authorization binding.

Input:
- auth middleware / search API path.

Output:
- Unauthorized tenant returns `403`; missing required tenant field returns `400`.

Acceptance:
- No cross-tenant results can be returned from vector search.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest tests/integration/test_project_key_policy_unittest.py -q`
- `cd main/backend && .venv311/bin/python -m pytest -m "contract and not external" -q`

Failure Isolation:
- Fail-closed behavior; revert only auth-binding layer if needed.

### T11 - Vector version activation and rollback switch

Goal:
- Support read by active version and explicit version override.

Input:
- vector model/service read path.

Output:
- Version toggle path (`is_active`, `vector_version`) with rollback procedure.

Acceptance:
- One gray release and one rollback rehearsal can be completed.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest tests/contract/test_vectorization_contract_unittest.py -q`

Failure Isolation:
- Roll back version toggling logic only, preserve data rows.

### T12 - Graph dedup adapter integration

Goal:
- Integrate vector retrieval for graph node/relation candidate recall.

Input:
- graph standardization modules.

Output:
- Adapter consumes vector matches for dedup decision pipeline.

Acceptance:
- Candidate recall can flow to merge gate (`semantic + type/time rule`).

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest tests/integration/test_admin_graph_standardization_unittest.py -q`
- `cd main/backend && .venv311/bin/python -m pytest tests/unit/test_graph_projection_unittest.py tests/unit/test_relation_ontology_unittest.py -q`

Failure Isolation:
- Revert graph adapter only; core vector API remains untouched.

### T13 - Document hybrid retrieval adapter integration

Goal:
- Integrate semantic + keyword hybrid retrieval with dedup folding.

Input:
- search modules and vector API.

Output:
- Adapter with filtering by `effective_time/source_domain/project_key`.

Acceptance:
- Hybrid path works with stable query contract.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest tests/integration/test_search_api_unittest.py -q`
- `cd main/backend && .venv311/bin/python -m pytest tests/core_business/test_search_core_contract.py tests/contract/test_vectorization_contract_unittest.py -q`

Failure Isolation:
- Revert hybrid adapter only; semantic-only path remains available.

### T14 - Report evidence retrieval adapter integration

Goal:
- Build `conclusion -> report_fact -> source_doc` evidence chain path.

Input:
- discovery/report modules + vector retrieval.

Output:
- Evidence retrieval adapter and provenance output.

Acceptance:
- Evidence-chain query is traceable and measurable.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest tests/core_business/test_discovery_core_contract.py tests/contract/test_vectorization_contract_unittest.py -q`

Failure Isolation:
- Revert report adapter only; other adapters unaffected.

### T15 - Scheduler signal integration (density + novelty)

Goal:
- Feed vector novelty/density signals into ingest scheduling.

Input:
- source library runtime path and scheduler logic.

Output:
- Scheduling score path with low-density priority and coverage floor hooks.

Acceptance:
- Signal can affect ranking without breaking existing ingest flow.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest tests/integration/test_t22_source_library_scrapy_collect_runtime_integration_unittest.py tests/core_business/test_resource_pool_core_contract.py -q`

Failure Isolation:
- Disable new scoring weights and fall back to legacy scheduler weights.

### T16 - Quality baseline and release gate solidification

Goal:
- Freeze vector release gate: coverage, retrieval quality, rollback evidence.

Input:
- evaluation scripts + release checklist.

Output:
- Reproducible evaluation entry and release checklist for M1-M4.

Acceptance:
- Team can run one-click evaluation and attach evidence to release PR.

Minimal Gate:
- `cd main/backend && .venv311/bin/python -m pytest -m "unit and not external" -q`
- `cd main/backend && .venv311/bin/python -m pytest -m "integration and not external" -q`
- `cd main/backend && .venv311/bin/python -m pytest tests/e2e/test_health_smoke_e2e.py -q`

Failure Isolation:
- Evaluation failure blocks release only; does not block development branch work.

## 2. Parallel Execution Sequence

Batch 1 (serial precondition):
- T1
- T2

Batch 2 (parallel):
- T3
- T4
- T5
- T6

Batch 3 (serial):
- T7
- T8

Batch 4 (parallel, then dependency):
- T9
- T11
- T10 (run after T9)

Batch 5 (parallel):
- T12
- T13
- T14

Batch 6 (serial closeout):
- T15
- T16

Rule:
- Run tasks in parallel inside each batch.
- Move to next batch only after current batch gates are green.
- `T16` is the final release gate and must pass before production rollout.

## 3. Merge Policy

- One task = one PR.
- Mandatory PR sections:
  - task id
  - changed files
  - minimal gate outputs
  - rollback scope

## 4. Done Definition

Vectorization atomic execution is considered done when:
- T1-T16 merged in order with gates green.
- No cross-tenant retrieval leakage.
- At least one version gray-release + rollback rehearsal evidence is attached.

## 5. Status Snapshot (2026-03-03, factual run state)

T1-T16 status:
- `T1`: done
- `T2`: done
- `T3`: done
- `T4`: done
- `T5`: done
- `T6`: done
- `T7`: done
- `T8`: done
- `T9`: done
- `T10`: done
- `T11`: done
- `T12`: done
- `T13`: done
- `T14`: done
- `T15`: done
- `T16`: done

Post-task operational add-ons (already executed):
- merge candidate filtering upgraded to `merge-eligible only` (exclude data-point + content-like nodes).
- supplemental grouping algorithm enabled for small groups.
- compare project full-run + DB apply completed with exported evidence.

Residual operational gap (outside T1-T16 hard gate):
- deterministic same-name fallback merge (optional strict mode) is not yet enabled by default.
