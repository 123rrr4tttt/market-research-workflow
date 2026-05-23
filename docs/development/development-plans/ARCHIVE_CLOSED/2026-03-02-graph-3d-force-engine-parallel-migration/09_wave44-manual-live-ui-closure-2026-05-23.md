# Wave44 Manual Live UI Closure (2026-05-23)

Status: `closed`.

## Closure Decision

The remaining external blocker for this target was live backend-data GraphPage/WebGL evidence. It is now resolved for the Graph 3D Force Engine Parallel Migration target.

This closure is limited to `2026-03-02-graph-3d-force-engine-parallel-migration`; it does not close Graph editing audit durability, audit/rollback UI, or persistent handoff replay targets.

## Evidence

- Evidence pack: [wave44-manual-graph3d-live-ui-closure/2026-05-23](../../../../../automation-runs/wave44-manual-graph3d-live-ui-closure/2026-05-23/README.md)
- Backend data evidence JSON: [backend_data_evidence.json](../../../../../automation-runs/wave44-manual-graph3d-live-ui-closure/2026-05-23/backend_data_evidence.json)
- Live UI evidence JSON: [live_ui_evidence.json](../../../../../automation-runs/wave44-manual-graph3d-live-ui-closure/2026-05-23/live_ui_evidence.json)
- Canvas screenshot: [graphpage-force3d-live-ui-canvas.png](../../../../../automation-runs/wave44-manual-graph3d-live-ui-closure/2026-05-23/graphpage-force3d-live-ui-canvas.png)

## Gate Results

```text
check_graph_visual_data_smoke_gate.py:
status=passed
readiness_state=live_ui_validated_non_closing
backend-data visual smoke=validated
live UI smoke=validated
```

```text
check_graph_live_smoke_readiness.py:
status=ok
live_db_validated=True
frontend_backend_data_smoke_validated=True
live_db_backend_data_smoke=validated
frontend_backend_data_visual_smoke=validated
```

## Manual Frontend Fix

- `useForceGraph3DLoader` now stores the dynamic import component with `setComponent(() => mod.default)`, so React does not execute the component function as a state updater.
- `window.__graph3dDebug.getVisibilityStats()` now reports current visible force3d data nodes, matching `nodeVisibility` and the live scene object count.

## Live Readback

- GraphPage loaded a live backend market graph endpoint through Vite proxy.
- Backend graph endpoint response: `nodes=413`, `edges=445`, `graph_schema_version=v1`.
- Force3D debug stats: `dataNodes=264`, `sceneNodeObjects=264`, `emptyDataNodes=0`, `emptySceneNodeObjects=0`.
- Canvas screenshot pixel stats: `uniqueSampledColors=993`, `nonWhite=10047/10050`.
- Validated run browser console errors: `0`.

## Remaining Non-Claims

The following remain external-blocked unless separately validated:

- Graph editing audit durability
- GraphPage audit/rollback UI readback
- persistent graph handoff replay readback
