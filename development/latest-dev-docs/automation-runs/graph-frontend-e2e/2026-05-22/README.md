# GraphPage Frontend E2E Evidence (2026-05-22)

## Scope

- Branch: `codex/devdocs-graph-frontend-e2e`
- Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/graph-frontend-e2e`
- Target docs: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-graph-editing-and-reporting/01_graph-editing-and-reporting-plan-2026-03-07.md`
- Target frontend: `main/frontend-modern/src/pages/GraphPage.tsx`
- Target e2e: `main/frontend-modern/tests/e2e/graphpage.spec.ts`

## Result

The existing GraphPage e2e only proved the page loaded, the 3D toggle existed, and the 3D slider stayed interactive. This lane added a focused GraphPage e2e path for the 3D engine boundary:

- if headless Chromium can create a WebGL context, the test requires the `react-force-graph-3d` canvas host to render and `window.__graph3dDebug.getVisibilityStats()` to report the two mocked graph data nodes plus at least two scene node objects;
- if the local browser cannot create WebGL, the test requires a visible automatic fallback to `legacy-projection` while keeping the GraphPage heading and controls visible.

During local replay, headless Chromium could not create a WebGL context with SwiftShader:

```text
THREE.WebGLRenderer: Error creating WebGL context.
```

This exposed a real frontend reliability gap: before this lane, the `ForceGraph3D` render error could blank the page after the 3D toggle. `GraphPage.tsx` now wraps the force3d component in a small render boundary and falls back to `legacy-projection` with a visible retry affordance.

## Changed Files

- `main/frontend-modern/src/pages/GraphPage.tsx`
  - added a `ForceGraphRenderBoundary` around `ForceGraph3DComp`;
  - added visible fallback text for force3d render errors;
  - added `data-testid="graph-force3d-canvas-host"` for stable e2e canvas detection.
- `main/frontend-modern/tests/e2e/graphpage.spec.ts`
  - added `graph page renders force3d canvas backed by graph scene nodes`;
  - the test accepts either verified force3d canvas/scene-node evidence or the verified no-WebGL fallback path.

## Validation

```bash
npm --prefix main/frontend-modern run test:e2e -- tests/e2e/graphpage.spec.ts
```

Result:

```text
3 passed (15.2s)
```

```bash
npm --prefix main/frontend-modern run lint
```

Result: passed.

## Closure Impact

This lane improves the GraphPage frontend evidence for the graph 3D surface and closes the false-green e2e gap around force3d render failures. It does not close the full graph editing/reporting CURRENT_DEV topic, because the documented GraphPage-to-curated workflow graph bridge and writing/reporting handoff flow remain unimplemented or unproven in the frontend.

Next closure blocker for that topic remains: prove a branch-local user flow from local graph edit to curated draft/submit, evidence pack, and writing or reporting handoff.
