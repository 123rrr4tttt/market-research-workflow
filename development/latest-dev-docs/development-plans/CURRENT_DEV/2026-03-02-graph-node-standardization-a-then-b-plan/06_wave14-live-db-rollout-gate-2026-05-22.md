# Wave14 Graph Node Live DB Rollout Gate (2026-05-22)

Status: `rollout gate landed / live DB closure remains evidence-bound`.

Worker branch:

- `codex/devdocs-wave14-graph-node-live-db-readiness`

Target topic:

- `2026-03-02-graph-node-standardization-a-then-b-plan`

## Result

This slice adds a dedicated Graph Node live DB rollout gate that separates three states that were easy to blur in the stale plan text:

- deterministic no-DB projection fixture evidence;
- pre-live read-mode and bounded backfill dry-run readiness;
- actual live DB closure evidence.

Implemented files:

- `main/backend/app/services/graph/persistence/graph_node_live_db_rollout_gate.py`
- `main/backend/scripts/check_graph_node_live_db_rollout_gate.py`
- `main/backend/tests/unit/test_graph_node_live_db_rollout_gate_unittest.py`

The checker passes in the default dry-run-ready state while keeping:

- `dry_run_ready=true`
- `live_db_validated=false`
- `live_db_closure_ready=false`
- `closure_claim=false`

If an evidence JSON is supplied, the checker only marks `live_db_validated=true` when all required live DB evidence fields are present:

- `live_db_validated`
- `alembic_current_or_upgrade_run`
- `backfill_graph_nodes_dry_run`
- `backend_data_graph_endpoint_smoke`
- `b_read_parity_checked`

Incomplete evidence is a failed gate, not partial closure.

## Boundary

This branch does not edit shared navigation indexes.

This branch does not modify:

- `main/backend/scripts/workflow_graph_smoke_local.py`

The new gate can validate live DB evidence if that evidence is provided, but it does not itself open a tenant DB connection or run Alembic/backfill. That distinction is intentional:

- dry-run readiness means the code path is ready to schedule a bounded tenant DB smoke;
- live DB validation means a separate run has supplied migration/current, live dry-run backfill, backend graph endpoint smoke, and B-read parity evidence;
- document closure remains a review decision after validated live evidence is attached.

## Verification Commands

Expected local dry-run gate:

```bash
cd /Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave14-graph-node-live-db-readiness/main/backend
/Users/wangyiliang/.local/bin/python3.11 scripts/check_graph_node_live_db_rollout_gate.py --format text
```

Expected status:

```text
status=ok
closure_state=dry_run_ready_live_db_not_validated
dry_run_ready=True
live_db_validated=False
live_db_closure_ready=False
closure_claim=False
```

Focused tests:

```bash
cd /Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave14-graph-node-live-db-readiness/main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/unit/test_graph_node_live_db_rollout_gate_unittest.py \
  tests/unit/test_graph_live_smoke_readiness_unittest.py \
  tests/unit/test_graph_persistence_writer_unittest.py \
  tests/unit/test_graph_backfill_readiness_unittest.py
```

Required Wave14 worker guard:

```bash
cd /Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave14-graph-node-live-db-readiness
/Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_wave14_plan.py
```

## Remaining Topic Gap

- Run Alembic `current` or `upgrade head` against the configured tenant schema.
- Run `scripts/backfill_graph_nodes.py --dry-run --limit 10` against live tenant data.
- Smoke backend graph endpoints against nonempty live tenant graph data.
- Compare `b_canary` or `b_primary` read-mode parity against seeded projection data.
- Let the integration lane update shared indexes after worker branches merge.
