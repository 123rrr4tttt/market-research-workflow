# Wave18 Graph Editing Audit Readback (2026-05-22)

Status: `tenant-like fixture audit/readback trace added / live tenant DB audit remains open`.

This Wave18 worker extends the graph editing audit durability gate with a tenant-like fixture. It proves the write/readback path for curated audit events and verifies rollback trace integrity without opening or claiming a live tenant database audit lane.

No shared navigation indexes were edited in this lane. `main/backend/scripts/workflow_graph_smoke_local.py` was not touched.

## Code Added

- `main/backend/scripts/check_graph_editing_audit_durability.py`
  - adds `tenant_like_fixture_audit_trace` as a separate gate stage;
  - writes two curated graph submit audit events and one rollback audit event under `tenant_like_graph_audit_fixture`;
  - reads the same graph back through a fresh `WorkflowGraphCuratedService` instance;
  - verifies raw write order `submit -> submit -> rollback` and readback order `rollback -> submit -> submit`;
  - verifies audit ids, `project_key`, `graph_id`, `actor_id`, audit contract version, rollback target, base revision, and rollback reason survive readback;
  - keeps top-level `live_tenant_db_audit_open=True`.
- `main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py`
  - asserts the tenant-like fixture stage is validated;
  - asserts rollback restores the baseline node and removes the experimental node;
  - asserts `live_tenant_db_audit_open` remains true even when repo-local evidence passes.

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
graphpage_audit_controls_validated=False
live_db_audit_durability_validated=False
live_tenant_db_audit_open=True
repo_local_audit_readback_contract=validated passed=True validated=True
tenant_like_fixture_audit_trace=validated passed=True validated=True
graphpage_audit_rollback_readback_ui=ready_not_run passed=True validated=False
live_db_audit_durability=not_run passed=True validated=False
```

## Boundary

This evidence validates:

- deterministic repo-local curated submit audit readback;
- tenant-like fixture audit event write/readback order and metadata integrity;
- rollback trace integrity for target version, current/base revision, project key, actor, reason, and restored graph snapshot.

This evidence does not close:

- live tenant DB audit durability;
- production tenant/project scoping under persistent storage;
- live GraphPage audit visibility after submit/rollback;
- GraphPage-visible handoff replay proof.

`live_tenant_db_audit_open=True` is intentionally preserved. Do not archive this topic from this worker lane.

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave18-graph-editing-audit-readback`:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_graph_editing_audit_durability_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_editing_audit_durability.py --format text
```

Observed result:

```text
pytest: 6 passed
checker: status=passed, tenant_like_fixture_audit_trace_validated=True, live_tenant_db_audit_open=True
```
