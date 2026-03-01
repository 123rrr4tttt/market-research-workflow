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

## Test Execution Result
- Command:
  - `main/backend/.venv311/bin/python -m unittest discover -s main/backend/tests -p '*_unittest.py'`
- Result:
  - `Ran 29 tests ... OK`
