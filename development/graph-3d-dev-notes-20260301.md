# Graph 3D Dev Notes (2026-03-01)

## Scope
- Refactor graph rendering into separated 2D/3D renderer modules.
- Keep `GraphPage` as orchestration layer with render mode switching.
- Restore to quaternion-enabled 3D interaction baseline (without view-offset/pan movement).

## Key Changes
1. Renderer split
- Added `main/frontend-modern/src/pages/graph/renderers/types.ts`.
- Added `main/frontend-modern/src/pages/graph/renderers/renderer2dEcharts.ts`.
- Added `main/frontend-modern/src/pages/graph/renderers/renderer3dProjection.ts`.
- `GraphPage.tsx` now switches by `renderMode` and renderer capabilities.

2. 3D force/physics path
- 3D physics state is persisted via `projectionPhysicsRef`.
- Solver runs in projection mode only; loop is driven by frame tick.
- Initial and final centroid recentering is retained in 3D solver.

3. Quaternion interaction baseline (current)
- Quaternion utilities live in `GraphPage.tsx`.
- Drag rotation + inertial damping is enabled in 3D mode.
- Slider angles (X/Y/Z) are used as basis orientation and synchronized into quaternion view state.
- `renderer3dProjection` accepts `interactionQuat` and applies quaternion rotation after Euler base transform.

4. Reverted out-of-scope movement variants
- Removed view-offset based pan from renderer call path.
- Removed WASD movement/pan from current final state.
- Final state = quaternion rotate only (no 2D view translation).

## Current UX/Controls
- Mode toggle: `2D` / `3D`.
- 3D keeps center lock via graph series center + no roam pan.
- 3D panel currently includes:
  - model rotate X
  - model rotate Y
  - model rotate Z
  - 3D repulsion

## Validation
- Lint run: `npm run lint -- src/pages/GraphPage.tsx src/pages/graph/renderers/renderer3dProjection.ts`
- Result: no errors; one existing warning on hook deps in `GraphPage.tsx`.

## Notes / Known Risk
- Existing `react-hooks/exhaustive-deps` warning remains from historical code path.
- Current commit intentionally avoids broader dependency-array refactor to keep behavior stable.
