# Wave20 Graph Editing Audit Conflict Readback (2026-05-22)

Status: `repo-local deterministic conflict/rollback readback gate added / live tenant DB remains open`.

This Wave20 worker extends the graph editing audit durability checker with a deterministic stale-conflict and rollback readback fixture. No shared navigation indexes were edited in this lane. `main/backend/scripts/workflow_graph_smoke_local.py` was not touched.

## Code Updated

- `main/backend/scripts/check_graph_editing_audit_durability.py`
  - adds `conflict_rollback_readback_fixture`;
  - writes two curated graph submit audit events, attempts a stale rollback, then performs an accepted rollback;
  - verifies the stale rollback conflict marker: `category=version_conflict`, `expected_revision=1`, `actual_revision=2`;
  - verifies the rejected conflict does not append an audit event;
  - verifies accepted rollback intent through `workflow_graph.rollback.v1`;
  - verifies fresh readback summary restores the baseline node and removes the candidate node.
- `main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py`
  - asserts the new fixture is validated by default;
  - asserts conflict marker, rollback intent, raw audit order, readback audit order, and restored node summary.

## Evidence

- [wave20-graph-editing-audit-conflict/2026-05-22](../../../automation-runs/wave20-graph-editing-audit-conflict/2026-05-22/README.md)
- `graph_editing_audit_conflict_readback.json`

## Checker Snapshot

Command:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_editing_audit_durability.py --format text
```

Observed result:

```text
status=passed
readiness_state=repo_local_validated_live_gaps_open
closure_claim=False
repo_local_audit_readback_validated=True
tenant_like_fixture_audit_trace_validated=True
conflict_rollback_readback_validated=True
graphpage_audit_controls_validated=False
live_db_audit_durability_validated=False
live_tenant_db_audit_open=True
conflict_rollback_readback_fixture=validated passed=True validated=True
```

## Boundary

This evidence validates only a repo-local deterministic fixture:

- audit event integrity for accepted submit/rollback;
- stale conflict marker preservation;
- rollback intent preservation;
- readback summary after rollback.

This evidence does not close:

- live tenant DB audit durability;
- production tenant/project scoping under persistent storage;
- live GraphPage audit visibility after submit/rollback;
- GraphPage-visible handoff replay proof.

`live_tenant_db_audit_open=True` is intentionally preserved. Do not archive this topic from this worker lane.

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave20-graph-editing-audit-conflict`:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_editing_audit_durability.py --format text
```

Observed result:

```text
pytest: 7 passed
checker: status=passed, conflict_rollback_readback_validated=True, live_tenant_db_audit_open=True
```
