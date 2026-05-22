# Wave20 Graph Editing Audit Conflict Readback Evidence (2026-05-22)

Status: `passed / deterministic_fixture_gate_only`.

This run extends the graph editing audit durability checker with a repo-local deterministic fixture for stale revision conflict handling and accepted rollback readback. It does not claim live tenant DB audit durability or GraphPage live UI closure.

## Artifact

- `graph_editing_audit_conflict_readback.json`

## Deterministic Assertions

- `conflict_rollback_readback_validated=True`
- stale rollback with `base_revision=1` returns conflict marker:
  - `category=version_conflict`
  - `expected_revision=1`
  - `actual_revision=2`
- rejected conflict does not append a new audit event before accepted rollback.
- accepted rollback records a `workflow_graph.rollback.v1` intent with:
  - `target_version_id=cver-wave20-baseline`
  - `rollback_scope=snapshot_restore`
  - `requires_base_revision_match=True`
  - `base_revision=2`
- rollback audit readback returns actions in reverse chronological order: `rollback`, `submit`, `submit`.
- fresh readback summary restores `node-wave20-baseline` and removes `node-wave20-candidate`.

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

## Boundary

This evidence remains repo-local and deterministic. It keeps `closure_claim=False` and `live_tenant_db_audit_open=True`; production tenant storage, live GraphPage audit/rollback visibility, and handoff replay UI proof remain separate blockers.
