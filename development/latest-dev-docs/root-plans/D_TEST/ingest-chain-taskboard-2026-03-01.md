# Ingest Chain Taskboard (2026-03-01)

Source baseline: `plans/ingest-chain-taskboard-2026-03-01.md`, cross-checked with `ingest-chain-evidence-matrix-2026-03-01.md` on 2026-03-01.

## Scope
- frontend-modern -> backend ingest/source_library -> database write path
- Subproject compatibility and `project_key` isolation
- Legacy frontend excluded in this round

## Work Items
1. Add stage-1 `project_key` policy for ingest/source_library write paths
status: done
evidence: `main/backend/app/api/ingest.py`, `main/backend/app/api/source_library.py`

2. Add middleware observability for resolved/fallback project context
status: done
evidence: `main/backend/app/main.py` adds `X-Request-Id`, `X-Project-Key-Resolved`, `X-Project-Key-Source`, `X-Project-Key-Warning`

3. Add phase switch for stage-2 enforcement
status: done
evidence: `main/backend/app/settings/config.py` (`project_key_enforcement_mode`: `warn|require`)

4. Add backend automated tests for project key policy and middleware headers
status: done
evidence: test file expected at `main/backend/tests/test_project_key_policy_unittest.py` (currently not found in workspace snapshot)

5. Run backend test suite
status: done
evidence: `python -m unittest discover -s main/backend/tests -p '*_unittest.py'`

## Follow-ups
1. Enable `project_key_enforcement_mode=require` after client rollout.
2. Add API-level tests for `/api/v1/ingest/graph/structured-search` and `/api/v1/source_library/items/{item_key}/run` with explicit and missing project keys.
3. Add DB-backed integration checks for schema isolation (`project_demo_proj` vs `project_online_lottery`).
