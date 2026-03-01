# Ingest Chain Evidence Matrix (2026-03-01)

## Request Context & Fallback Observability
- File: `main/backend/app/main.py`
- Change:
  - Added `_resolve_request_project_context()`
  - Added response headers:
    - `X-Request-Id`
    - `X-Project-Key-Resolved`
    - `X-Project-Key-Source`
    - `X-Project-Key-Warning` (when fallback used)
  - Added warning log on fallback usage
- Acceptance:
  - Request with `X-Project-Key` returns `x-project-key-source=header`
  - Request without project key returns fallback warning header

## Ingest Write Path Project Key Policy
- File: `main/backend/app/api/ingest.py`
- Change:
  - `_require_project_key()` now supports stage mode:
    - `warn`: fallback to context + warning
    - `require`: reject missing explicit project key
  - Missing key error uses `PROJECT_KEY_REQUIRED`
- Acceptance:
  - Missing key in `require` mode returns structured error
  - Missing key in `warn` mode logs fallback warning

## Source Library Write Path Project Key Policy
- File: `main/backend/app/api/source_library.py`
- Change:
  - Added `_require_project_key()` with same stage policy as ingest
  - Applied to `/items/{item_key}/run` and `/sync_shared_from_files`
  - Preserved `HTTPException` without re-wrapping
- Acceptance:
  - `run_item` supports fallback in warn mode, rejects in require mode
  - sync endpoint reports resolved project key in response

## Contract Error Code
- File: `main/backend/app/contracts/errors.py`
- Change:
  - Added `PROJECT_KEY_REQUIRED`
- Acceptance:
  - New code is available for envelope-based error response

## Runtime Config Switch
- File: `main/backend/app/settings/config.py`
- Change:
  - Added `project_key_enforcement_mode` (`warn|require`), default `warn`
- Acceptance:
  - Behavior switches with settings patch/environment override

## Automated Tests
- File: `main/backend/tests/test_project_key_policy_unittest.py`
- Added:
  - Error code existence test
  - Ingest explicit and fallback behavior tests
  - Ingest strict mode rejection test
  - Source-library fallback warning test
  - Middleware project-context header test
  - API contract-like route tests:
    - `/api/v1/ingest/graph/structured-search` explicit key success + strict mode failure
    - `/api/v1/source_library/items/{item_key}/run` explicit key success + strict mode failure

## Ingest Baseline Matrix Tests (core modes)
- File: `main/backend/tests/test_ingest_baseline_matrix_unittest.py`
- Coverage:
  - Route inventory assertions (OpenAPI contains core ingest paths)
  - Strict mode (`project_key_enforcement_mode=require`) missing-key failures for:
    - `policy`, `market`, `source-library/run`, `social/sentiment`, `graph/structured-search`,
      `policy/regulation`, `commodity/metrics`, `ecom/prices`
  - Explicit key success cases for the same set, with async mode and task dispatch mocks
- Outcome:
  - All matrix cases pass; confirms baseline completeness of core ingest entrypoints.

## Frontend-Modern Heterogeneous Entry Baseline
- File: `main/backend/tests/test_frontend_modern_entry_baseline_unittest.py`
- Source of truth:
  - `main/frontend-modern/src/pages/IngestPage.tsx`
  - `main/frontend-modern/src/pages/GraphPage.tsx`
  - `main/frontend-modern/src/lib/api.ts`
- Covered heterogeneous entries:
  - suggest keywords (`/api/v1/discovery/generate-keywords`)
  - source-library sync/run
  - policy / policy-regulation / market / social / commodity / ecom
  - graph structured-search (`collect` + `source_collect`)
- Assertions:
  - explicit `project_key` path succeeds for each entry
  - strict mode missing-key rejection for ingest entries
  - OpenAPI route inventory includes all expected modern entry routes

## Test Execution Result
- Command:
  - `main/backend/.venv311/bin/python -m unittest discover -s main/backend/tests -p '*_unittest.py'`
- Result:
  - `Ran 39 tests ... OK`

## Live DB Isolation Verification (demo_proj vs iso_proj)
- Purpose:
  - Verify per-project write isolation with real HTTP requests and DB checks.
- Steps:
  - Create project `iso_proj` via `POST /api/v1/projects`.
  - Call `POST /api/v1/source_library/items?project_key=<key>` for:
    - `demo_proj` with `item_key=iso_check_demo_proj_1772358317`
    - `iso_proj` with `item_key=iso_check_iso_proj_1772358317`
  - Query DB:
    - `project_demo_proj.source_library_items`
    - `project_iso_proj.source_library_items`
- Observed results:
  - Count delta:
    - `demo_proj`: `+1`
    - `iso_proj`: `+1`
  - Cross-check:
    - `project_demo_proj` contains only `iso_check_demo_proj_1772358317`
    - `project_iso_proj` contains only `iso_check_iso_proj_1772358317`
  - Conclusion:
    - No cross-project pollution observed on this write path.

## Live Ingest Market Attempt (diagnostic note)
- Endpoint:
  - `POST /api/v1/ingest/market`
- Result:
  - `iso_proj`: request succeeded (`200`) but returned zero links, no document insert.
  - `demo_proj`: request failed (`500`) due existing DB sequence/state issue:
    - `etl_job_runs` primary key conflict (`duplicate key value violates unique constraint etl_job_runs_pkey`).
- Implication:
  - Ingest path request/route context is reachable and project headers resolve correctly.
  - `demo_proj` needs DB sequence repair before using it as stable ingest-write evidence.

## Project Initialization Fix (tenant completeness + sequence binding)
- File:
  - `main/backend/app/api/projects.py`
- Changes:
  - `_create_tenant_tables_best_effort()` now always executes `_ensure_tenant_id_sequences(schema_name)`.
  - Added `_ensure_tenant_id_sequences(schema_name)`:
    - creates per-table local sequences (`<schema>.<table>_id_seq`) if missing
    - sets `id` default to local sequence via `nextval('<schema>.<table>_id_seq'::regclass)`
    - aligns sequence value with `MAX(id)+1`
  - `inject_initial_project()` now invokes `_create_tenant_tables_best_effort(target_schema)` after copy to ensure full tenant tables (including `etl_job_runs`) and correct defaults.

## New Project Create + Raw Import Validation (post-fix)
- Method:
  - Direct invocation: `create_project(CreateProjectPayload(...))`
  - Created project: `init_fix_0301095525` (schema: `project_init_fix_0301095525`)
  - Verified:
    - `etl_job_runs` table exists
    - `id` default expression is schema-local:
      - `nextval('project_init_fix_0301095525.etl_job_runs_id_seq'::regclass)`
  - Executed raw import under `bind_project(project_key)`:
    - `run_raw_import_documents(...)` returned `inserted=1`, `error_count=0`
  - DB checks:
    - `project_init_fix_0301095525.documents` count = 1
    - `project_init_fix_0301095525.etl_job_runs` (`job_type='raw_import'`) count = 1
- Conclusion:
  - Initialization fix is effective for newly created projects and raw import no longer fails due missing/incorrect job table sequence wiring.
