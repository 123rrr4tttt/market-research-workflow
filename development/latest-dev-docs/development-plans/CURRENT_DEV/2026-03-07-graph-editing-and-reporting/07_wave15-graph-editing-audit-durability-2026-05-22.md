# Wave15 Graph Editing Audit Durability Gate (2026-05-22)

Status: `repo-local audit/readback gate added / UI and live DB durability remain open`.

This Wave15 worker adds a deterministic checker for the audit durability/readback boundary in Graph Editing and Reporting. It intentionally separates repo-local contract evidence from product UI and live tenant audit-log durability evidence.

No shared navigation indexes were edited in this lane. `main/backend/scripts/workflow_graph_smoke_local.py` was not touched.

## Evidence Added

- `main/backend/scripts/check_graph_editing_audit_durability.py`
  - runs a deterministic curated graph fixture through draft submit, second submit, rollback, audit listing, and fresh service readback;
  - verifies rollback restores the target version snapshot and preserves `workflow_graph.rollback.v1` inside the audit context;
  - verifies handoff persist, list, replay, and governance audit records through the run-store boundary;
  - statically checks backend audit/rollback/readback routes and handoff replay anchors;
  - classifies GraphPage audit/rollback controls and live DB audit durability as separate, unsealed stages.
- `main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py`
  - covers the default partial state;
  - verifies incomplete live DB evidence fails closed;
  - verifies live DB evidence can be recorded without claiming topic closure;
  - verifies UI evidence cannot validate when static GraphPage audit/rollback controls are absent.

## Checker Snapshot

Command:

```bash
/Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_editing_audit_durability.py --format text
```

Observed result:

```text
status=passed
readiness_state=repo_local_validated_live_gaps_open
closure_claim=False
repo_local_audit_readback_validated=True
graphpage_audit_controls_validated=False
live_db_audit_durability_validated=False
repo_local_audit_readback_contract=validated passed=True validated=True
graphpage_audit_rollback_readback_ui=not_exposed passed=True validated=False
live_db_audit_durability=not_run passed=True validated=False
```

## Boundary

This evidence validates the repo-local audit/readback contract only:

- curated submit audit records remain readable after a fresh service instance;
- rollback audit records retain target version, revision, and rollback contract context;
- handoff persisted/replayed events carry governance audit records and can be replayed from the run-store boundary.

This evidence does not close:

- GraphPage audit readback controls;
- GraphPage rollback controls;
- GraphPage-visible handoff replay proof;
- live tenant DB audit-log durability;
- production graph edit operations or tenant/project scoping under real persistence.

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave15-graph-editing-audit-durability`:

```bash
/Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_editing_audit_durability.py --format text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py
```

Observed result:

```text
checker: status=passed, closure_claim=False, repo_local_audit_readback_validated=True
pytest: 4 passed
```

## Closure Decision

Do not archive this topic from this lane. The backend now has a repeatable gate that prevents repo-local audit/readback evidence from being mistaken for live product closure. The GraphPage audit/rollback UI and live DB audit durability gaps remain explicit blockers for final Graph Editing and Reporting closure.
