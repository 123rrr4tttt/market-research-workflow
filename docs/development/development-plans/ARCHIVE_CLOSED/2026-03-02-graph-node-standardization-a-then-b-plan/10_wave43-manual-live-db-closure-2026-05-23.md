# Wave43 Manual Live DB Closure (2026-05-23)

Status: `closed`.

## Closure Decision

The remaining external blocker for this target was live tenant DB validation. It is now resolved for the Graph Node standardization gate.

This closure is limited to `2026-03-02-graph-node-standardization-a-then-b-plan`; it does not close GraphPage visual, Graph 3D, or graph editing audit/rollback targets.

## Evidence

- Evidence pack: [wave43-manual-graph-live-db-closure/2026-05-23](../../../../../automation-runs/wave43-manual-graph-live-db-closure/2026-05-23/README.md)
- Live DB evidence JSON: [live_db_evidence.json](../../../../../automation-runs/wave43-manual-graph-live-db-closure/2026-05-23/live_db_evidence.json)
- Migration repair: `main/backend/migrations/versions/20260402_000002_repair_graph_projection_constraints.py`

## Gate Results

```text
check_graph_node_live_db_rollout_gate.py:
status=ok
closure_state=live_db_validated_ready_for_closure_review
live_db_validated=True
live_db_closure_ready=True
closure_claim=False
```

```text
check_graph_live_smoke_readiness.py:
status=ok
live_db_validated=True
frontend_backend_data_smoke_validated=False
live_db_backend_data_smoke=validated
frontend_backend_data_visual_smoke=ready_not_run
```

## Manual DB Work

- Alembic upgraded to `20260402_000002 (head)`.
- Existing tenant graph projection tables were deduped where needed and repaired with:
  - `uq_graph_nodes_type_canonical`
  - `uq_graph_node_aliases_norm_type`
  - `uq_graph_edges_type_from_to`
- `demo_proj` tenant counts after repair/projection:
  - `documents=218`
  - `graph_nodes=2946`
  - `graph_edges=6254`
  - `graph_node_aliases=4741`

## Live Readback

- `scripts/backfill_graph_nodes.py --dry-run --limit 10`:
  - `scanned_docs=10`
  - `written_nodes=154`
  - `skipped_docs=0`
- Backend graph endpoint smoke:
  - content graph: `nodes=123`, `edges=338`
  - market graph: `nodes=62`, `edges=57`
  - policy graph: `nodes=70`, `edges=84`
- B-read parity after projection write:
  - content: `missing_nodes=0`, `missing_edges=0`
  - market: `missing_nodes=0`, `missing_edges=0`
  - policy: `missing_nodes=0`, `missing_edges=0`

## Remaining Non-Claims

The following remain external-blocked unless separately validated:

- live backend-data GraphPage/WebGL visual smoke
- GraphPage audit/rollback UI readback
- live tenant audit durability for graph editing/reporting
