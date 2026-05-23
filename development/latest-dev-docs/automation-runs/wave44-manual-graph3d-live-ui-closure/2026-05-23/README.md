# Wave44 Manual Graph3D Live UI Closure Evidence (2026-05-23)

Scope: manually resolve the live backend-data GraphPage/WebGL blocker for `2026-03-02-graph-3d-force-engine-parallel-migration`.

## Result

- `check_graph_visual_data_smoke_gate.py`: `status=passed`, `backend-data visual smoke=validated`, `live UI smoke=validated`.
- `check_graph_live_smoke_readiness.py`: `status=ok`, `live_db_validated=True`, `frontend_backend_data_smoke_validated=True`.
- The closure is limited to Graph 3D live UI/WebGL evidence. It does not close graph editing audit durability.

## Manual Work Performed

1. Opened GraphPage through a live Vite proxy against the backend on `127.0.0.1:8000`.
2. Confirmed the old force3d failure was not a documentation gap:
   - stale Vite optimized deps could bind `react-force-graph-3d` to a different React chunk;
   - `setComponent(mod.default)` also treated the imported component function as a React state updater.
3. Fixed `useForceGraph3DLoader` to store the component with `setComponent(() => mod.default)`.
4. Fixed `window.__graph3dDebug.getVisibilityStats()` to report current visible force3d data nodes, matching `nodeVisibility`.
5. Rebuilt the temporary Vite dev surface on `127.0.0.1:4173 --force`.
6. Captured live backend endpoint evidence and live force3d canvas evidence with Chromium WebGL enabled through SwiftShader flags.

## Evidence

- Backend data evidence: `backend_data_evidence.json`
- Live UI evidence: `live_ui_evidence.json`
- Canvas screenshot: `graphpage-force3d-live-ui-canvas.png`
- Diagnostic root-cause capture: `diagnostic.json`, `graphpage-force3d-diagnostic-fullpage.png`

Important metrics:

- backend graph endpoint: `nodes=413`, `edges=445`, `graph_schema_version=v1`
- GraphPage force3d debug stats: `dataNodes=264`, `sceneNodeObjects=264`, `emptyDataNodes=0`, `emptySceneNodeObjects=0`
- canvas pixel stats: `width=1156`, `height=652`, `uniqueSampledColors=993`, `nonWhite=10047/10050`
- console errors during validated run: `0`

## Boundary

Do not reuse this evidence to close:

- `2026-03-07-graph-editing-and-reporting`

That target still needs live tenant DB audit durability, persistent handoff replay readback, tenant/project scoping, and audit/rollback UI evidence.
