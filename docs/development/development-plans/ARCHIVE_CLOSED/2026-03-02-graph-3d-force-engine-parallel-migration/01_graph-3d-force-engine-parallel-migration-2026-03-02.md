# Graph 3D Force Engine Parallel Migration (2026-03-02)

## 2026-05-22 Closure Refresh

Status: `需更新 / 封口待验证`.

The implementation is no longer plan-only. Current repo evidence shows the force 3D path is present and still wired:

- `main/frontend-modern/package.json` includes `react-force-graph-3d`.
- `main/frontend-modern/src/pages/graph/hooks/useGraphModeSwitch.ts` defaults the projection engine to `force3d` and keeps a switch guard.
- `main/frontend-modern/src/pages/graph/hooks/useForceGraph3DLoader.ts` dynamically imports `react-force-graph-3d`, retries load failures, and exposes a manual retry hook.
- `main/frontend-modern/src/pages/GraphPage.tsx` still renders the force 3D canvas path, engine selector, fallback notice, and 2D/3D mode toggle.
- `main/frontend-modern/tests/e2e/graphpage.spec.ts` covers the mocked graph page load plus 2D/3D switch and slider interaction.

Closure blocker:

1. The current branch still needs fresh graph-specific validation before this topic can move to `ARCHIVE_CLOSED`.
2. The existing e2e proves UI reachability with mocked graph APIs, but it does not by itself prove nonblank WebGL canvas output, rapid engine-switch stress, or fallback recovery on a real data set.
3. Treat `react-force-graph-3d` upstream/runtime warnings as a retained risk until a visual/canvas smoke or browser debug check confirms that `window.__graph3dDebug` reports expected scene stats in 3D mode.

Minimal validation steps for closure:

```bash
cd /Users/wangyiliang/market-research-workflow.worktrees/graph-plan-refresh/main/frontend-modern
npm run test:e2e -- tests/e2e/graphpage.spec.ts
npm run build

rg -n "initialProjectionEngine = 'force3d'|requestProjectionEngineChange|DEFAULT_ENGINE_SWITCH_GUARD_MS" src/pages/graph/hooks/useGraphModeSwitch.ts
rg -n "import\\('react-force-graph-3d'\\)|MAX_RETRY|retry" src/pages/graph/hooks/useForceGraph3DLoader.ts
rg -n "__graph3dDebug|ForceGraph3DComp|gv2-chart--force3d|react-force-graph-3d" src/pages/GraphPage.tsx
```

Worker lane 5 validation result:

- Passed structural smoke: `rg -n "initialProjectionEngine = 'force3d'|requestProjectionEngineChange|DEFAULT_ENGINE_SWITCH_GUARD_MS" main/frontend-modern/src/pages/graph/hooks/useGraphModeSwitch.ts`.
- Blocked frontend e2e in this worktree: local `node_modules` is absent, and the borrowed Playwright CLI from the main workspace cannot resolve `@playwright/test` from this worktree's `playwright.config.ts`.
- No dependency install was performed in this parallel worktree.

Closure decision: keep this topic in `CURRENT_DEV` as `需更新` until the validation above is run on the current graph branch and the visual/canvas blocker is either passed or explicitly waived.

## Background

This task migrated graph 3D rendering from a single legacy projection path to a parallel dual-engine setup:

- `legacy-projection` (kept for fallback and compatibility)
- `react-force-graph-3d` (new default 3D engine)

At the same time, 2D behavior was restored/optimized to avoid unintended regressions.

## Delivered Changes

1. 3D dual-engine architecture
- Added `projectionEngine` switch in `GraphPage`.
- Kept legacy 3D path intact.
- Added force-graph path and made it the default for 3D mode.

2. Dynamic loading and chunk split
- `react-force-graph-3d` is loaded only when needed.
- Vite manual chunking added `force-graph-vendor` to isolate heavy 3D deps from default path.

3. Legend and symbol consistency
- Restored 2D legend visual format (dot style).
- Kept 3D legend/symbol mapping with shape-aware rendering.
- Added type normalization + symbol mapping debug to improve diagnosis.

4. Force simulation controls
- Added `3D node repulsion` and `3D global mutual attraction`.
- Extended value ranges (2x) and mapped ranges to effective force parameters.
- Updated force logic so disconnected components are also pulled back globally.

5. Performance and interaction fixes
- Removed 2D animation slowdown (`animation=false`, duration `0`).
- Removed click delay timer strategy (single-click immediate; double-click handled without timer wait).
- Isolated 3D computations to 3D mode to avoid 2D overhead.

6. Stability fixes for engine switching
- Solved black-screen / DOM conflict by separating ECharts and ForceGraph containers.
- Reduced engine-switch crashes by reusing force instance in 3D mode and pause/resume control.
- Added viewport sync (ResizeObserver + runtime size sync) to fix canvas/interaction region mismatch.

## Key Files

- `main/frontend-modern/src/pages/GraphPage.tsx`
- `main/frontend-modern/src/pages/graph/renderers/renderer2dEcharts.ts`
- `main/frontend-modern/src/index.css`
- `main/frontend-modern/vite.config.ts`
- `main/frontend-modern/src/types/three.d.ts`

## Risks / Follow-ups

1. `react-force-graph-3d` upstream warning and internal tick robustness
- Observed `THREE.Clock` deprecation warnings from dependency internals.
- Further hardening may require explicit lifecycle guards or engine-level debounce during extreme rapid toggling.

2. Bundle size
- `force-graph-vendor` remains large by nature of WebGL/three stack.
- Current split ensures non-3D default path avoids immediate load cost.

3. Optional next optimization
- Add strict engine-switch debounce and explicit context disposal guard for stress toggling scenarios.

## 功能日志同步（不含 bug 修复）

日期：2026-03-02

- 2D 选择模式右键能力统一为“一跳邻域切换”（以中心节点为锚点，切换中心+邻居的选中集合）。
- 右键节点解析链路增强为多源参数兼容（支持 `data/id/value/name/dataIndex` 组合解析），提升不同输入设备与事件形态下的命中稳定性。
- 保持“右键邻域切换 + 去重窗口”并行策略，避免同一次右键触发重复切换。

影响文件：

- `main/frontend-modern/src/pages/GraphPage.tsx`
