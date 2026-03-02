# Test Automation Standardization

Last updated: 2026-03-01

## 1. Standardized Test Boundary

Backend tests use marker layering from `main/backend/pytest.ini`:

- `unit`: isolated logic tests.
- `integration`: module wiring and app-assembly checks.
- `contract`: API envelope/OpenAPI contract checks.
- `e2e`: backend smoke request-path checks.
- `slow`, `external`: execution tags.

Standardized entrypoint is `scripts/test-standardize.sh` with profiles:

- `unit|integration|schema-guard|contract|e2e|core-business|external-smoke|frontend-e2e|coverage|all|ci-pr|ci-main|docker`.
- `core-business` runs `tests/core_business` with marker union `(unit or integration or contract or e2e) and not external`.
- `schema-guard` runs `tests/integration/test_project_schema_guard_unittest.py` and validates `/api/v1/dashboard/stats` for every project from `/api/v1/projects`; failure output includes exact `project_key`.
- `coverage` runs `(unit or integration) and not external`, then enforces split thresholds via `main/backend/scripts/check_coverage_thresholds.py`.
- `external-smoke` runs two external chain smoke checks in docker compose:
  - `python -m scripts.test_resource_library_e2e`
  - `python -m scripts.test_search_to_document_chain`
- `frontend-e2e` runs Playwright suite in `main/frontend-modern` via `npm run test:e2e`.

## 2. CI Gate Alignment

Source of truth: `.github/workflows/backend-tests.yml`.

- `pull_request` lane:
  - `standards-check`
  - `unit-check`
  - `integration-check`
  - `schema-guard-check` (`continue-on-error: true`, non-blocking)
  - `coverage-check` (`continue-on-error: true`, non-blocking)
  - `docker-check`
- `push(main)` / `schedule` / `workflow_dispatch` lane:
  - `standards-check`
  - `unit-check`
  - `integration-check`
  - `schema-guard-check` (blocking)
  - `coverage-check` (blocking)
  - `contract-check`
  - `e2e-check`
  - `docker-check`

Note: `core-business` is currently a standardized local engineering profile, not a dedicated CI job.

## 3. Coverage Gate Policy

Split coverage gate is enforced by `scripts/check_coverage_thresholds.py`:

- Core threshold: `100%`.
- Other threshold: `20%`.
- Default core paths: `app/api/search.py,app/contracts/api.py,app/contracts/responses.py,app/contracts/tasks.py,app/contracts/errors.py`.
- Core path set can be overridden by `CORE_COVERAGE_PATHS`.

This policy is executed both:

- In CI `coverage-check` job.
- In local standardized `coverage` profile.

## 4. Parallel Execution Guidance

- CI uses job-level parallelism: after `standards-check`, eligible jobs are scheduled concurrently.
- Local acceleration can use pytest xdist by passing extra args through standardized entrypoint (example: `./scripts/test-standardize.sh unit -n auto`).
- For CI reproduction and gate parity, use default serial execution (do not pass `-n auto`).

## 5. Current Limitations

1. Frontend E2E is available via standardized profile (`frontend-e2e`) but is not a default blocking CI gate.
2. Backend `e2e` currently focuses on smoke paths, not full scenario matrix.
3. External dependency determinism is still incomplete for some third-party integrations.

## 6. Manual Checks (Archived but Retained)

The following scripts are retained as manual checks and are intentionally excluded from blocking CI gates:

- `main/backend/scripts/test_azure_search_index.py`
- `main/backend/scripts/test_serper_demo.py`
- `main/backend/scripts/test_scraper_html.py`
- `main/backend/scripts/test_scraper_info.py`
- `main/backend/scripts/test_history_adapters.py`
- `main/backend/scripts/test_nitter.py`
- `main/backend/scripts/test_nitter_standalone.py`
- `main/backend/scripts/test_twitter_api.py`
- `main/backend/scripts/test_twitter_api_standalone.py`
