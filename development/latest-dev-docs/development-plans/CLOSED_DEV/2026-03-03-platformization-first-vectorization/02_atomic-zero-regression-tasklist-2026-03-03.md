# Atomic Zero-Regression Tasklist (2026-03-03)

## 0. Execution Rules

- Each task is atomic and idempotent.
- Each task has fixed fields: `Goal / Input / Output / Acceptance / Minimal Gate / Failure Isolation`.
- No task may silently broaden scope.
- Any contract field change must include tests in the same task.

## 1. Taskboard

### T1 - Router startup hardening

Goal:
- Remove silent API router loading fallback and fail fast on router import errors.

Input:
- `main/backend/app/main.py`

Output:
- Router mounting code does not swallow exceptions.
- Startup failure is explicit and observable.

Acceptance:
- Application fails on invalid router import.
- Existing successful startup path unchanged.

Minimal Gate:
- `pytest -m "unit and not external" -q`
- `pytest tests/core_business/test_main_core_contract.py -q`

Failure Isolation:
- Revert only router-loading block changes in `app/main.py`.

### T2 - GateService reason-code normalization

Goal:
- Unify reject reasons for URL/content/provenance gates under one stable code set.

Input:
- `main/backend/app/services/ingest/meaningful_gate.py`
- `main/backend/app/services/ingest/single_url.py`

Output:
- Shared reason-code map and deterministic output fields.

Acceptance:
- Rejection outputs include stable reason codes.
- Existing accepted cases still pass.

Minimal Gate:
- `pytest tests/unit/test_meaningful_gate_unittest.py -q`
- `pytest tests/unit/test_single_url_ingest_unittest.py -q`

Failure Isolation:
- Roll back reason-code mapping only; keep gate logic unchanged.

### T3 - `single_url` pipeline extraction

Goal:
- Split `single_url` flow into staged functions without changing business contract.

Input:
- `main/backend/app/services/ingest/single_url.py`

Output:
- Explicit stages: classify/fetch/parse/gate/persist orchestration.

Acceptance:
- Response fields remain backward-compatible.
- Existing ingest core contract tests pass.

Minimal Gate:
- `pytest tests/unit/test_single_url_ingest_unittest.py -q`
- `pytest tests/core_business/test_ingest_core_contract.py -q`

Failure Isolation:
- Revert stage extraction only, keep original gate behavior.

### T4 - Enforce single write workflow in `url_pool`

Goal:
- Ensure `url_pool` does candidate orchestration only and routes final write to `single_url`.

Input:
- `main/backend/app/services/ingest/url_pool.py`

Output:
- No bypass direct write branch remains.

Acceptance:
- Mixed candidate batch returns consistent `inserted_valid/rejected_count` aggregation.

Minimal Gate:
- `pytest tests/integration/test_ingest_baseline_matrix_unittest.py -q`
- `pytest tests/core_business/test_ingest_core_contract.py -q`

Failure Isolation:
- Revert only `url_pool` integration path.

### T5 - Enforce single write workflow in `source_library` auto-ingest

Goal:
- Ensure source-library auto-ingest routes writes through `single_url` only.

Input:
- `main/backend/app/services/collect_runtime/adapters/source_library.py`

Output:
- Auto-ingest branch uses single unified write path.

Acceptance:
- Handler-cluster execution has no direct write bypass.

Minimal Gate:
- `pytest tests/integration/test_t22_source_library_scrapy_collect_runtime_integration_unittest.py -q`
- `pytest tests/core_business/test_source_library_core_contract.py -q`

Failure Isolation:
- Revert only source-library adapter changes.

### T6 - Task orchestration normalization

Goal:
- Remove synchronous `.run(...)` orchestration where broker path is expected.

Input:
- `main/backend/app/services/tasks.py`

Output:
- Async orchestration semantics are explicit and traceable.

Acceptance:
- Task status transitions remain consistent in process history.

Minimal Gate:
- `pytest tests/core_business/test_process_consistency_core_contract.py -q`
- `pytest -m "integration and not external" -q`

Failure Isolation:
- Revert only orchestration calls, preserve task payload shape.

### T7 - Ingest contract freeze test

Goal:
- Freeze ingest response business fields for platformized workflows.

Input:
- `main/backend/tests/contract/`

Output:
- New/updated contract test asserting stable fields:
  - `status`
  - `inserted_valid`
  - `rejected_count`
  - `rejection_breakdown`
  - `degradation_flags`

Acceptance:
- Contract tests fail on accidental field drift.

Minimal Gate:
- `pytest -m "contract and not external" -q`

Failure Isolation:
- Revert only new contract assertions.

### T8 - Process observability baseline fields

Goal:
- Standardize process-level quality/error fields for operations.

Input:
- `main/backend/app/services/job_logger.py`
- `main/backend/app/api/process.py`

Output:
- Process output includes stable observability dimensions (`error_code`, quality fields).

Acceptance:
- Process history/detail endpoints expose fields consistently.

Minimal Gate:
- `pytest tests/core_business/test_process_consistency_core_contract.py -q`
- `pytest tests/integration/test_api_exception_envelope_unittest.py -q`

Failure Isolation:
- Revert process-output field additions only.

### T9 - Vectorization contract baseline test (start of M1)

Goal:
- Add vectorization non-regression contract before M1 implementation expansion.

Input:
- `main/backend/tests/contract/`
- existing vector-related modules

Output:
- New test file: `test_vectorization_contract_unittest.py`
- Baseline assertions for `Embedding` compatibility and search output shape.

Acceptance:
- Contract catches object identity/model/dim drift.

Minimal Gate:
- `pytest -m "contract and not external" -q`
- `pytest tests/core_business/test_search_core_contract.py -q`

Failure Isolation:
- Revert vector contract file only.

### T10 - M1 embedding pipeline guard

Goal:
- Enforce upstream-field freeze before embedding write.

Input:
- `main/backend/app/services/indexer/policy.py`
- related vectorization pipeline entrypoints

Output:
- Pre-write validation for frozen fields:
  - `project_key/object_type/object_id/vector_version/clean_text/language/source_domain/effective_time/keep_for_vectorization`

Acceptance:
- Missing critical fields fail fast with explicit reason.
- Existing valid indexing path passes.

Minimal Gate:
- `pytest tests/core_business/test_search_core_contract.py -q`
- `pytest -m "integration and not external" -q`

Failure Isolation:
- Revert only pre-write validation guard.

## 2. Suggested Execution Sequence

1. T1
2. T2
3. T3
4. T4
5. T5
6. T6
7. T7
8. T8
9. T9
10. T10

Rule:
- T1-T8 are platformization critical path.
- T9-T10 must start only after T7 sign-off.

## 3. Merge Policy

- One task = one PR.
- Mandatory PR section:
  - task id
  - changed files
  - minimal gate outputs
  - rollback scope

## 4. Done Definition

Platformization done when:
- T1-T8 all merged and green.
- No direct write bypass outside `single_url` workflow.

Vectorization foundation entry allowed when:
- T9 merged.
- T10 passes and does not regress platform contracts.
