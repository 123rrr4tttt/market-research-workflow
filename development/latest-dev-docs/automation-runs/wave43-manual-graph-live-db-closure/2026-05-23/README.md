# Wave43 Manual Graph Live DB Closure Evidence (2026-05-23)

Scope: manually resolve the live DB blocker for `2026-03-02-graph-node-standardization-a-then-b-plan`.

## Result

- `check_graph_node_live_db_rollout_gate.py`: `status=ok`, `closure_state=live_db_validated_ready_for_closure_review`, `live_db_validated=True`, `live_db_closure_ready=True`.
- `check_graph_live_smoke_readiness.py`: live DB stage validated; frontend/backend-data visual smoke still `ready_not_run`, so this evidence only closes the Graph Node live DB blocker, not the parent 3D/GraphPage visual blocker.

## Manual Work Performed

1. Ran Alembic current/upgrade against the configured local PostgreSQL tenant DB.
2. Found the tenant graph projection tables lacked the unique constraints required by `GraphNodeWriter` `ON CONFLICT`.
3. Added and ran `20260402_000002_repair_graph_projection_constraints.py`.
4. Confirmed 21 graph projection unique-constraint rows across tenant schemas.
5. Ran `scripts/backfill_graph_nodes.py --dry-run --limit 10` against live tenant data.
6. Smoked backend graph endpoints on `127.0.0.1:8000` for `demo_proj`.
7. Wrote content/market/policy graph projections into `demo_proj` through `GraphNodeWriter`.
8. Rechecked B-read parity: missing nodes and missing edges are zero for all three graph families.

## Evidence

- `live_db_evidence.json`

Important metrics:

- backfill dry-run: `scanned_docs=10`, `written_nodes=154`, `skipped_docs=0`, `next_resume_token=33`
- endpoint smoke:
  - content graph: `nodes=123`, `edges=338`
  - market graph: `nodes=62`, `edges=57`
  - policy graph: `nodes=70`, `edges=84`
- B-read parity:
  - content: `missing_nodes=0`, `missing_edges=0`
  - market: `missing_nodes=0`, `missing_edges=0`
  - policy: `missing_nodes=0`, `missing_edges=0`

## Boundary

Do not reuse this evidence to close:

- `2026-03-02-graph-3d-force-engine-parallel-migration`
- `2026-03-07-graph-editing-and-reporting`

Those still need GraphPage/backend-data visual evidence, audit/rollback UI evidence, or live audit durability evidence beyond this Graph Node live DB gate.
