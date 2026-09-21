# Contract 13 binding-impact receipt v2

Status: `BINDING_DRIFT_FOUND_ADDITIVE_REBIND_REVIEW_REQUIRED`.

This is a read-only byte-binding audit. It does not modify declarations, registries, candidate/history bytes, runtime code, or production state.

## Coverage

- Changed-path entries: 105/105.
- Code/contract/checker subset: 91/91 audited.
- Bound paths: 2; NOT_BOUND paths: 103.
- Drifted bound paths: 2; intact bound paths: 0.
- Task attribution: only 5 recorded task-start hashes are accepted as before evidence; 100 remain inherited or unattributable. HEAD was not used as before evidence.

## Current-declaration alignment

Stage 2 intake and I1 test support declare B23 current, while the Stage 0 v4 generator/record declares B19 for C2-C9 and B22 for I1; family test support defaults to B19. The JSON reports every declaration set separately and does not silently pick one authority.

## Eight import-time DB boundary paths

| Path | Binding | Drift | Required disposition |
|---|---:|---:|---|
| `main/backend/app/models/base.py` | BOUND (6) | YES | `AUTHORIZED_CREATE_ONLY_SUCCESSOR_STAGE_REBIND; DO_NOT_OVERWRITE_B23; VERSIONED_STAGE0_DECLARATION_ALIGNMENT_AND_ADDITIVE_REBIND` |
| `main/backend/app/startup_hooks.py` | NOT_BOUND (0) | NO | `NONE_NOT_BOUND_WITHIN_DETERMINISTIC_SEARCH_SCOPE` |
| `main/backend/app/services/workflow_graph/__init__.py` | NOT_BOUND (0) | NO | `NONE_NOT_BOUND_WITHIN_DETERMINISTIC_SEARCH_SCOPE` |
| `main/backend/app/services/workflow_graph/runtime.py` | BOUND (1) | YES | `VERSIONED_SUCCESSOR_ALL_LINES_BYTE_CLOSURE_RECORD` |
| `main/backend/app/services/workflow_graph/executors/__init__.py` | NOT_BOUND (0) | NO | `NONE_NOT_BOUND_WITHIN_DETERMINISTIC_SEARCH_SCOPE` |
| `main/backend/app/services/workflow_graph/handoff_store.py` | NOT_BOUND (0) | NO | `NONE_NOT_BOUND_WITHIN_DETERMINISTIC_SEARCH_SCOPE` |
| `main/backend/tests/unit/test_schema_startup_boundary_unittest.py` | NOT_BOUND (0) | NO | `NONE_NOT_BOUND_WITHIN_DETERMINISTIC_SEARCH_SCOPE` |
| `main/backend/tests/unit/test_workflow_graph_import_boundary_unittest.py` | NOT_BOUND (0) | NO | `NONE_NOT_BOUND_WITHIN_DETERMINISTIC_SEARCH_SCOPE` |

## Bound changed paths

| Path | Current SHA-256 | References | Drift |
|---|---|---:|---:|
| `main/backend/app/models/base.py` | `173d95722cef7411f4b1e4606f8dbdbf850d74fbae9847b942b13be1e56c8308` | 6 | YES |
| `main/backend/app/services/workflow_graph/runtime.py` | `15c22d898b1c90205c43585aae4e3d83a425782e57676926507b92e6b8fb68ca` | 1 | YES |

Every reference, old bound hash, current hash, JSON pointer, drift result, task-start attribution, and additive-rebind requirement is recorded in `binding-impact-audit.v2.json`. `NOT_BOUND` is limited to the exact enumerated search universe; it is not a repository-global absence claim.

Authority ceiling: `PRODUCTION_RELEASE_NOT_AUTHORIZED`.
