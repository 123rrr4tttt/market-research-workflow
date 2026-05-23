# Wave19 Graph Rollout Readback Gate (2026-05-22)

Status: `pre-live rollout/readback gate landed; live backend-data WebGL visual closure remains open`.

Worker branch:

- `codex/devdocs-wave19-graph-rollout-readback`

Target topic:

- `2026-03-02-graph-3d-force-engine-parallel-migration`

## Result

This slice links the Graph 3D force engine topic to the Graph Node rollout readback gate without claiming live visual closure. The checker reads the Force3D side as a rollback and boundary contract:

1. Force3D load/render failure falls back to `legacy-projection`.
2. The manual engine selector still exposes both `legacy` and `force3d`.
3. Mocked e2e readback still covers rapid engine switching.
4. The Wave17 runtime pixel/shape gate remains repo-local and records `tenantDbRequired=false` / `externalGpuRequired=false`.
5. The visual data smoke gate still reports live UI as not run unless separate live evidence exists.

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

This gate proves the repo-local readback and rollback/fallback contract only. It does not:

- query a real tenant DB graph endpoint;
- run GraphPage against live backend graph data;
- prove a live WebGL canvas is nonblank;
- replace the Wave17 runtime pixel/shape gate;
- claim this CURRENT_DEV topic is closed.

The checker keeps `closure_claim=false`, `live_tenant_db_validated=false`, and `webgl_live_visual_validated=false`.

Shared navigation indexes remain untouched for the Wave19 integration lane.
