# Graph Modern3D Parallel Atomic Wave2 (2026-03-05)

## Scope

- Frontend only, limited to modern 3D graph related modules.
- Goal: improve slider smoothness, tighten graph API/query-key normalization, and add minimum e2e regression for graph interactions.

## Parallel Atomic Sequence

1. Task A (Agent Hooke)
- 目标: 优化滑动条实时渲染平滑性。
- 输入: `src/pages/graph/hooks/useGraphVisualState.ts`, `src/pages/GraphPage.tsx`
- 输出: `visualDraft`/`visualApplied` 分离，range 默认延迟应用，checkbox 立即应用。
- 验收: build 通过（Agent 分支验证）。

2. Task B (Agent Lorentz)
- 目标: 统一图谱 API 参数规范化与 query key 构造。
- 输入: `src/lib/api/domains/graph-workflow.ts`, `src/lib/queryKeys.ts`, `src/lib/api.ts`
- 输出: `normalizeGraphQueryParams` 与 `buildGraphDataQueryKey`，兼容原调用。
- 验收: build 通过（Agent 分支验证）。

3. Task C (Agent Einstein)
- 目标: 增加图谱关键交互最小回归。
- 输入: `tests/e2e/graphpage.spec.ts`
- 输出: 覆盖 2D/3D 切换与关键 slider 可交互断言。
- 验收: `npm run test:e2e -- tests/e2e/graphpage.spec.ts` 通过。

## Merged Result

- Slider interaction now applies expensive visual recalculation in coalesced delayed updates while preserving immediate UI feedback.
- Graph API/query-key path now uses normalized date/filter/limit semantics (`YYYY-MM-DD`, trimmed filters, `1..2000` limit clamp).
- Graph e2e now includes mode-switch and slider interaction coverage.

## Verification In Main Workspace

- `npm run test:e2e -- tests/e2e/graphpage.spec.ts`: passed (2 tests).
- `npm run build`: blocked by unrelated existing TypeScript unused-variable errors in `src/pages/LlmDesignerPage.tsx` (not introduced by this graph wave).

## Risk Notes

- Default delayed apply (`120ms`) introduces minor visual lag by design to reduce stutter.
- e2e selectors depend on current Chinese UI labels/title attributes; text changes require test updates.

