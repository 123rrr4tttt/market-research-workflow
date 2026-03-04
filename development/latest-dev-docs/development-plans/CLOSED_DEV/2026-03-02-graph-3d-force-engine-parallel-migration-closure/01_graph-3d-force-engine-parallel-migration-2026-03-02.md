# Graph 3D Force Engine Parallel Migration (2026-03-02)

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
- `main/frontend-modern/src/pages/graph/hooks/useForceGraph3DLoader.ts`
- `main/frontend-modern/src/index.css`
- `main/frontend-modern/vite.config.ts`

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
