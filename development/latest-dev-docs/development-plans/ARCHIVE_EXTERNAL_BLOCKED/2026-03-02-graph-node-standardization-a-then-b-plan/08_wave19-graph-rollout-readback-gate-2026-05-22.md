# Wave19 Graph Rollout Readback Gate (2026-05-22)

Status: `pre-live rollout/readback gate landed; real tenant DB rollout remains open`.

Worker branch:

- `codex/devdocs-wave19-graph-rollout-readback`

Target topic:

- `2026-03-02-graph-node-standardization-a-then-b-plan`

## Result

This slice adds a deterministic Wave19 graph rollout/readback checker that composes the prior Graph Node rollout gates without opening a tenant DB:

1. Manifest shape readback over the Wave7/Wave10/Wave14 Graph Node manifest.
2. Projection contract readback over the no-DB canonical node/edge fixture and pre-live readiness checks.
3. Rollback-ready trace for B-write rollback, B-read fallback, and backfill apply rollback.
4. Force3D visual boundary readback, kept as non-closing because no live WebGL smoke is run.

Implemented files:

- `main/backend/scripts/check_graph_rollout_readback_gate.py`
- `main/backend/tests/unit/test_graph_rollout_readback_gate_unittest.py`

## Machine Gate

Default local command:

```bash
cd /Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave19-graph-rollout-readback
/Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_rollout_readback_gate.py --format text
```

Observed default status:

```text
status=passed
readiness_state=pre_live_rollout_readback_ready
closure_claim=False
live_tenant_db_validated=False
webgl_live_visual_validated=False
manifest_shape_readback=passed validated=True
projection_contract_readback=passed validated=True
rollback_ready_trace=passed validated=True
force3d_visual_boundary_readback=passed validated=True
```

Focused test:

```bash
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_graph_rollout_readback_gate_unittest.py
```

Observed test result:

```text
3 passed
```

## Boundary

This is a deterministic pre-live readback gate only. It does not:

- open a tenant DB connection;
- run Alembic against a configured tenant schema;
- run `scripts/backfill_graph_nodes.py --dry-run` against live tenant data;
- compare `b_canary` or `b_primary` read parity against seeded projection rows;
- move this topic out of CURRENT_DEV.

The checker keeps `closure_claim=false`, `live_tenant_db_validated=false`, and `webgl_live_visual_validated=false`.

Shared navigation indexes remain untouched for the Wave19 integration lane.
