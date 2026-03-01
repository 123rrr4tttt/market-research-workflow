# Ingest Chain Taskboard (2026-03-01)

## Scope
- frontend-modern -> backend ingest/source_library -> database write path
- Subproject compatibility and `project_key` isolation
- Legacy frontend excluded in this round

## Work Items
1. Add stage-1 `project_key` policy for ingest/source_library write paths
status: done
evidence: `app/api/ingest.py`, `app/api/source_library.py`

2. Add middleware observability for resolved/fallback project context
status: done
evidence: `app/main.py` adds `X-Request-Id`, `X-Project-Key-Resolved`, `X-Project-Key-Source`, `X-Project-Key-Warning`

3. Add phase switch for stage-2 enforcement
status: done
evidence: `settings.project_key_enforcement_mode` (`warn|require`)

4. Add backend automated tests for project key policy and middleware headers
status: done
evidence: `tests/test_project_key_policy_unittest.py`

5. Add API-level tests for structured-search and source-library run
status: done
evidence: `tests/test_project_key_policy_unittest.py` includes:
- `/api/v1/ingest/graph/structured-search` explicit key success + require-mode missing key failure
- `/api/v1/source_library/items/{item_key}/run` explicit key success + require-mode missing key failure

6. Run backend test suite
status: done
evidence: `python -m unittest discover -s main/backend/tests -p '*_unittest.py'`

7. Add ingest baseline matrix tests for all core ingest modes
status: done
evidence: `tests/test_ingest_baseline_matrix_unittest.py`

8. Add frontend-modern heterogeneous entry baseline tests
status: done
evidence: `tests/test_frontend_modern_entry_baseline_unittest.py`

9. Fix project initialization for tenant table completeness and schema-local id sequences
status: done
evidence: `app/api/projects.py` (`_create_tenant_tables_best_effort`, `_ensure_tenant_id_sequences`, inject path follow-up ensure)

10. Create new project and validate raw import end-to-end on initialized schema
status: done
evidence: project `init_fix_0301095525` created; `etl_job_runs` default sequence bound to project schema; raw import inserted document and job record

## Follow-ups
1. Enable `project_key_enforcement_mode=require` after client rollout.
2. Repair `project_demo_proj.etl_job_runs` sequence/PK state (current market ingest may fail with duplicate PK).
3. Add DB-backed integration checks for document/source ingest writes after sequence repair.
