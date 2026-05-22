# Ops Frontend F_PLAN Closure Index

> Updated: 2026-05-22 (US/Pacific)
> Scope: `development/latest-dev-docs/ops-frontend/F_PLAN/` current closure status for graph, API, Storybook, and launcher tracks.
> Write boundary for this pass: `development/latest-dev-docs/ops-frontend/**`, the evidence package under `development/latest-dev-docs/automation-runs/storybook-launcher-gates/2026-05-22/`, and the read-only launcher dry-run gate in `scripts/gates/run_launcher_first_dry_run_gate.sh`.

## Status Legend

- `已封口`: current code shape exists and a current acceptance gate can prove the track.
- `需更新`: implementation evidence exists, but the closure record or fresh gate evidence is not current enough.
- `未封口`: the track still lacks either a complete implementation record or a passing acceptance gate.
- `过时`: the ops-frontend document is behind the current project surface and can mislead the next implementer.

## Current Closure Matrix

| Track | Current status | Evidence checked | Unsealed blocker | Next acceptance gate |
| --- | --- | --- | --- | --- |
| Graph rendering and interaction | `需更新` | Historical F_PLAN records cover renderer split, 2D/3D control work, interaction hook extraction, and graph E2E. Current frontend files still include `GraphPage.tsx`, `src/pages/graph/hooks/useGraphVisualState.ts`, `src/pages/graph/domain/topology.ts`, renderer modules, and `tests/e2e/graphpage.spec.ts`. | This lane did not refresh the graph-specific Playwright gate; that work remains assigned to the graph/frontend E2E lane. The old records are directionally valid but not a current closure proof. | From `main/frontend-modern`: run targeted lint for graph files, then `npm run test:e2e -- tests/e2e/graphpage.spec.ts`. If graph visuals changed, also capture one 2D and one 3D screenshot. |
| Frontend API facade and graph query keys | `需更新` | Current `src/lib/api.ts` re-exports domain modules; `src/lib/api/domains/graph-workflow.ts` contains graph API normalization; `src/lib/queryKeys.ts` contains `buildGraphDataQueryKey`. | The implementation shape exists, but the F_PLAN evidence stops at 2026-03-05 and no fresh API/query-key lint/build result is attached in this lane. | From `main/frontend-modern`: run targeted lint for `src/lib/api.ts`, `src/lib/api/domains/graph-workflow.ts`, and `src/lib/queryKeys.ts`; then run `npm run build` in the API/graph validation lane. |
| Storybook and Storybook MCP | `已封口` | `npm --prefix main/frontend-modern run storybook:build` passed on 2026-05-22; `.storybook/main.ts` enables `@storybook/addon-docs` and `@storybook/addon-mcp`; `curl -I http://127.0.0.1:6006/mcp` returned `405 Method Not Allowed` with `allow: GET, POST, DELETE, OPTIONS`. Evidence: [automation-runs/storybook-launcher-gates/2026-05-22/README.md](../../automation-runs/storybook-launcher-gates/2026-05-22/README.md). | None for the current Storybook/MCP gate. The Vite chunk-size warning is non-blocking and should be handled separately only if bundle budgets are introduced. | Re-run `npm --prefix main/frontend-modern run storybook:build` and the `/mcp` HEAD probe whenever Storybook dependencies, `.storybook/*`, or stories change. |
| Launcher-first ops flow | `已封口` | `scripts/platform-macos.sh docker-start` routes to `scripts/docker-launcher-ui.sh`; `docker-full-start` remains the direct full-stack alternative; `docker-status` is read-only and passed on 2026-05-22; the dry-run gate validated launcher routing, compose launcher services, and the macOS Swift build entry. Evidence: [automation-runs/storybook-launcher-gates/2026-05-22/README.md](../../automation-runs/storybook-launcher-gates/2026-05-22/README.md). | None for the non-destructive launcher-first gate. `scripts/build-macos-launcher.sh` still mutates `$HOME/Desktop/Market Research Workflow.app`, so full app-bundle smoke should be run only in a user-approved packaging lane. | Re-run `scripts/gates/run_launcher_first_dry_run_gate.sh "$PWD"` plus `bash scripts/platform-macos.sh docker-status` after launcher script changes; run `docker-start` or app-bundle build only when the lane explicitly allows startup/desktop mutation. |

## Existing Plan Records

- [frontend-modern-api-graph-atomic-execution-2026-03-05.md](./frontend-modern-api-graph-atomic-execution-2026-03-05.md): API domain split, query keys, graph topology layering.
- [multi-agent-parallel-execution-graph-interaction-hook-graphpage-e2e-2026-03-05.md](./multi-agent-parallel-execution-graph-interaction-hook-graphpage-e2e-2026-03-05.md): graph interaction hook extraction and GraphPage E2E record.
- [graph-modern3d-parallel-atomic-wave2-2026-03-05.md](./graph-modern3d-parallel-atomic-wave2-2026-03-05.md): graph slider smoothness, API/query-key normalization, GraphPage E2E wave.
- [graph-3d-controls-left-and-2d-gravity-2026-03-02.md](./graph-3d-controls-left-and-2d-gravity-2026-03-02.md): 3D control placement and 2D gravity slider.
- [graph-3d-dev-notes-20260301.md](./graph-3d-dev-notes-20260301.md): 2D/3D renderer split and 3D interaction baseline.
- [frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md](./frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md): Figma component pull status; still separately blocked by Figma MCP quota.
- [LEGACY_A_INDEX.md](./LEGACY_A_INDEX.md): legacy imported index.

## Next Round Work Queue

1. Install or reuse frontend dependencies in the worker worktree without changing tracked files.
2. Run the graph/API lint and GraphPage E2E gates listed above.
3. Keep Storybook/MCP and launcher-first rows closed by re-running the linked gates after dependency or launcher script changes.
4. Only after graph/API gates pass, change graph/API rows from `需更新` to `已封口`.
