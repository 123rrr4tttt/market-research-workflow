# Wave11 Graph Editing Audit and Rollback Evidence (2026-05-22)

## Scope

This Wave11 worker lane adds a deterministic backend slice for graph governance contracts. It does not claim that GraphPage audit/rollback controls, writing handoff UI ownership, live tenant audit storage, or production audit operations are fully sealed.

No shared navigation indexes were edited in this lane.

## Result

Status: `backend deterministic contract evidence added / product workflow gaps retained`.

Implemented in this worktree:

- Added `main/backend/app/services/workflow_graph/governance_contract.py` as a pure service-layer contract module for bounded graph edit audit records, rollback requests, and handoff audit records.
- Curated graph submit audit records now carry `workflow_graph.governance_audit.v1`, bounded action/object-scope vocabulary, actor, project, graph id, revisions, version id, status, and version-semantics fields.
- Curated graph rollback now builds and persists a `workflow_graph.rollback.v1` contract with `snapshot_restore` scope, target version id, current/base revision, actor/project context, and explicit separation from template-version semantics.
- Handoff persistence and replay events now include bounded governance audit records for `handoff.persisted` and `handoff.replayed`, without changing the existing run-store list/replay contract shape.
- Focused unit tests cover pure contract validation, curated rollback audit/contract persistence, and handoff audit event emission.

## Boundary

This is not closure evidence for:

- real GraphPage audit or rollback controls;
- a GraphPage writing handoff button or writing-page pull proof;
- clue-chain graph output mapped into curated graph governance;
- live DB or production audit-log durability;
- a full UI conflict-resolution workflow.

The slice is intentionally no-DB and deterministic: the service tests use patched config repositories or in-memory run stores.

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave11-graph-editing-audit` unless noted:

```bash
python3 scripts/check_current_dev_wave11_plan.py
```

Observed result:

```text
OK wave11_current_dev_plan=passed mode=codex/devdocs-wave11-graph-editing-audit branches=9 changed_files=7 worker_boundary_enforced=true
```

Command run from `main/backend`:

```bash
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/unit/test_workflow_graph_governance_contract_unittest.py tests/unit/test_workflow_graph_curated_service_unittest.py tests/unit/test_workflow_graph_handoff_store_unittest.py
```

Observed result:

```text
11 passed in 10.64s
```

Final branch gate:

```bash
git diff --check
```

Observed result: passed with no output.

## Closure Decision

Do not archive this topic. The backend now has a bounded deterministic audit/rollback contract slice for graph edits and handoff actions, but the topic remains open for the product workflow gaps listed above.
