# Wave17 Runtime Pixel / Shape Gate Evidence (2026-05-22)

Status: `repo-local runtime gate landed / live tenant DB visual smoke remains open`.

This Wave17 worker adds a deterministic GraphPage runtime gate for the Graph 3D force engine migration. The gate uses mocked repo-local graph API payloads, so it does not require tenant DB access, production data, or an external GPU.

## Evidence Added

- `main/frontend-modern/tests/e2e/graph-runtime-pixel-gate.spec.ts`
  - mocks graph config and admin market graph responses with 3 nodes and 2 resolved edges;
  - opens `/#graph.html?type=market`, enters 3D mode, and waits for the force3d canvas host;
  - validates `window.__graph3dDebug` shape framing: expected data nodes, scene node objects, no empty data nodes, no empty scene node objects;
  - screenshots the force3d host and inspects PNG pixel diversity when WebGL pixels are available;
  - records `nonblank-pixels` when pixel diversity is sufficient, otherwise accepts `shape-framing` from force3d scene/debug evidence;
  - when WebGL context creation is unavailable, accepts `fallback-data-framing` only after the legacy visual frame, node/edge summary, and typed legend prove the same graph payload was framed without tenant DB access.
- `main/frontend-modern/package.json`
  - adds `check:graph-runtime-pixel-gate` for a single-worker Playwright run.
- `main/frontend-modern/scripts/check_graph_force3d_frontend_contract.mjs`
  - now asserts that the Wave17 runtime pixel/shape gate and npm script remain present.

## Current Gate Output

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave17-graph-visual-runtime-pixel-gate`:

```bash
npm --prefix main/frontend-modern run check:graph-force3d-frontend-contract
npm --prefix main/frontend-modern run check:graph-runtime-pixel-gate
```

Observed status:

```text
Graph force3d frontend contract check passed
1 passed
```

Observed local proof route: `fallback-data-framing`, because Chromium reported `Error creating WebGL context.` The gate still passed only after confirming the legacy graph visual frame, `节点总数=3`, `边总数=2`, and typed legend labels for the deterministic graph payload.

The Playwright test attaches `wave17-graph-runtime-pixel-gate.json` with:

- `tenantDbRequired=false`
- `externalGpuRequired=false`
- `proof=nonblank-pixels` when software/headless WebGL produces inspectable pixels;
- `proof=shape-framing` when canvas pixels are not diverse but force3d scene/debug framing proves the graph data reached rendered node objects;
- `proof=fallback-data-framing` when WebGL context creation is unavailable and the legacy graph visual frame still proves node/edge and typed legend framing for the deterministic graph payload.

## Boundary

This gate proves repo-local GraphPage runtime rendering/framing for deterministic mocked backend graph data. It does not close the remaining production/live smoke gap:

- no tenant DB graph endpoint was queried;
- no production GraphPage screenshot was captured;
- no supervisor closure claim is made for the overall Graph 3D force engine migration topic.
