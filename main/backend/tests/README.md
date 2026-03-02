# Backend Test Strategy

This directory follows a layered test strategy:

- `unit/`: isolated logic tests, no external dependency required.
- `integration/`: application wiring and module interaction tests.
- `contract/`: API/envelope/OpenAPI contract stability tests.
- `e2e/`: smoke tests for request path behavior.

## Markers

Configured in `main/backend/pytest.ini`:

- `unit`
- `integration`
- `contract`
- `e2e`
- `slow`
- `external`

## Local Commands

Run from `main/backend`:

```bash
.venv311/bin/python -m pytest -m unit -q
.venv311/bin/python -m pytest -m integration -q
.venv311/bin/python -m pytest -m contract -q
.venv311/bin/python -m pytest -m e2e -q
.venv311/bin/python -m pytest -m "(unit or integration or contract or e2e) and not external" tests/core_business -q
.venv311/bin/python -m pytest -m "integration and not external" tests/integration/test_project_schema_guard_unittest.py -q
.venv311/bin/python -m pytest -m "(unit or integration) and not external" --cov=app --cov-report=term-missing --cov-report=xml:coverage.xml -q
CORE_COVERAGE_PATHS="app/api/search.py,app/contracts/api.py,app/contracts/responses.py,app/contracts/tasks.py,app/contracts/errors.py" .venv311/bin/python scripts/check_coverage_thresholds.py --coverage-file coverage.xml --core-paths "$CORE_COVERAGE_PATHS" --core-threshold 100 --other-threshold 20
.venv311/bin/python -m pytest -q
```

## CI Gate Policy

- `pull_request`:
  - `standards-check`
  - `unit-check`
  - `integration-check`
  - `schema-guard-check` (non-blocking, `continue-on-error: true`)
  - `coverage-check` (non-blocking, `continue-on-error: true`)
  - `docker-check`
- `push` to `main`, `schedule`, `workflow_dispatch`:
  - `standards-check`
  - `unit-check`
  - `integration-check`
  - `schema-guard-check` (blocking)
  - `coverage-check` (blocking, `core=100%` and `other=20%`)
  - `contract-check`
  - `e2e-check`
  - `docker-check`

This keeps PR feedback fast while preserving full layered validation on mainline.

## 自动化测试标准化执行

Use the standardized test entrypoint from repo root:

```bash
./scripts/test-standardize.sh unit
./scripts/test-standardize.sh integration
./scripts/test-standardize.sh schema-guard
./scripts/test-standardize.sh contract
./scripts/test-standardize.sh e2e
./scripts/test-standardize.sh core-business
./scripts/test-standardize.sh external-smoke
./scripts/test-standardize.sh frontend-e2e
./scripts/test-standardize.sh coverage
./scripts/test-standardize.sh ci-pr
TEST_PROFILE=test ./scripts/test-standardize.sh docker
```

Profile policy:

- Supported profiles: `unit|integration|schema-guard|contract|e2e|core-business|external-smoke|frontend-e2e|coverage|all|ci-pr|ci-main|docker`.
- Local pytest profiles exclude `external` by default.
- Core business profile command:
  - `pytest -m "(unit or integration or contract or e2e) and not external" tests/core_business -q`
  - Purpose: fast regression checks for core business endpoints/flows collected in `tests/core_business`.
- Schema guard profile command:
  - `pytest -m "integration and not external" tests/integration/test_project_schema_guard_unittest.py -q`
  - Purpose: verify `/api/v1/dashboard/stats` is available for each project returned by `/api/v1/projects`; failure output includes exact `project_key`.
- Coverage profile command:
  - `pytest -m "(unit or integration) and not external" --cov=app --cov-report=term-missing --cov-report=xml:coverage.xml`
  - `CORE_COVERAGE_PATHS="app/api/search.py,app/contracts/api.py,app/contracts/responses.py,app/contracts/tasks.py,app/contracts/errors.py" python scripts/check_coverage_thresholds.py --coverage-file coverage.xml --core-paths "$CORE_COVERAGE_PATHS" --core-threshold 100 --other-threshold 20`
- Local prerequisite for coverage profile: install plugin in active env (`python -m pip install pytest-cov`).
- Coverage threshold location:
  - CI gate: `.github/workflows/backend-tests.yml` -> `jobs.coverage-check` -> `scripts/check_coverage_thresholds.py`.
  - Local standardized entry: `scripts/test-standardize.sh` -> `coverage` profile -> `check_coverage_thresholds.py`.
  - Default thresholds: `core=100%`, `other=20%`.
  - Core path list can be customized via `CORE_COVERAGE_PATHS`.
- For docker profile, `TEST_PROFILE` defaults to `test` (maps to `backend-test` service).
- In CI `workflow_dispatch`, `test_profile` can override the profile; fallback remains `test`.
- `core-business` is currently a standardized local/engineering entrypoint and is not a standalone CI job in `.github/workflows/backend-tests.yml`.
- `external-smoke` runs two backend external-chain checks in docker compose:
  - `python -m scripts.test_resource_library_e2e`
  - `python -m scripts.test_search_to_document_chain`
- `frontend-e2e` runs Playwright suite in `main/frontend-modern` via `npm run test:e2e`.

Tier policy:

- `PR` tier (fast feedback): `standards-check + unit-check + integration-check + schema-guard-check(non-blocking) + coverage-check(non-blocking) + docker-check`.
- `main` tier (full gate): `standards-check + unit-check + integration-check + schema-guard-check + coverage-check + contract-check + e2e-check + docker-check`.

## Manual Checks Archive (Not CI Gates)

The following scripts are kept as manual checks and are not part of default CI gate jobs:

- `main/backend/scripts/test_azure_search_index.py`
- `main/backend/scripts/test_serper_demo.py`
- `main/backend/scripts/test_scraper_html.py`
- `main/backend/scripts/test_scraper_info.py`
- `main/backend/scripts/test_history_adapters.py`
- `main/backend/scripts/test_nitter.py`
- `main/backend/scripts/test_nitter_standalone.py`
- `main/backend/scripts/test_twitter_api.py`
- `main/backend/scripts/test_twitter_api_standalone.py`

Reason: these scripts rely on unstable third-party dependencies, credentials, or exploratory debugging scenarios, so they are intentionally excluded from blocking gates.

## Parallel Execution Guidance

- CI parallelism is at the job layer: after `standards-check`, remaining jobs are scheduled in parallel according to event conditions.
- For local acceleration, pass through pytest xdist args via standardized script (install `pytest-xdist` first):
  - `./scripts/test-standardize.sh unit -n auto`
  - `./scripts/test-standardize.sh integration -n auto`
  - `./scripts/test-standardize.sh core-business -n auto`
- For CI reproduction and gate parity, run profiles without `-n auto` (default serialized pytest execution).
