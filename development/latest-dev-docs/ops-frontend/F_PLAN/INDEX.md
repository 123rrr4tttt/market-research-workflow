# Ops Frontend F_PLAN Closure Index

> Updated: 2026-05-22 (US/Pacific)
> Scope: `development/latest-dev-docs/ops-frontend/F_PLAN/` current closure status for graph, API, Storybook, and launcher tracks.
> Write boundary for this pass: docs only under `development/latest-dev-docs/ops-frontend/**`; `main/frontend-modern` and launcher scripts were read only as evidence.

## Status Legend

- `已封口`: current code shape exists and a current acceptance gate can prove the track.
- `需更新`: implementation evidence exists, but the closure record or fresh gate evidence is not current enough.
- `未封口`: the track still lacks either a complete implementation record or a passing acceptance gate.
- `过时`: the ops-frontend document is behind the current project surface and can mislead the next implementer.

## Current Closure Matrix

| Track | Current status | Evidence checked | Unsealed blocker | Next acceptance gate |
| --- | --- | --- | --- | --- |
| Graph rendering and interaction | `需更新` | Historical F_PLAN records cover renderer split, 2D/3D control work, interaction hook extraction, and graph E2E. Current frontend files still include `GraphPage.tsx`, `src/pages/graph/hooks/useGraphVisualState.ts`, `src/pages/graph/domain/topology.ts`, renderer modules, and `tests/e2e/graphpage.spec.ts`. | This lane could not refresh the frontend gate because `main/frontend-modern/node_modules` is absent in this worktree. The old records are directionally valid but not a current closure proof. | From `main/frontend-modern`: run targeted lint for graph files, then `npm run test:e2e -- tests/e2e/graphpage.spec.ts`. If graph visuals changed, also capture one 2D and one 3D screenshot. |
| Frontend API facade and graph query keys | `需更新` | Current `src/lib/api.ts` re-exports domain modules; `src/lib/api/domains/graph-workflow.ts` contains graph API normalization; `src/lib/queryKeys.ts` contains `buildGraphDataQueryKey`. | The implementation shape exists, but the F_PLAN evidence stops at 2026-03-05 and no fresh lint/build result is attached in this lane. | From `main/frontend-modern`: run targeted lint for `src/lib/api.ts`, `src/lib/api/domains/graph-workflow.ts`, and `src/lib/queryKeys.ts`; then run `npm run build` when dependencies are installed. |
| Storybook and Storybook MCP | `未封口` | Current `package.json` defines `storybook` and `storybook:build`; `.storybook/main.ts` enables `@storybook/addon-docs` and `@storybook/addon-mcp`; current source tree contains page/component stories including `GraphPage.stories.tsx`, `OpsPage.stories.tsx`, and writing/workflow stories. | There is no ops-frontend F_PLAN closure record for Storybook, and no current `storybook:build` or MCP endpoint reachability proof in this worktree. | From `main/frontend-modern`: run `npm run storybook:build`; then run `npm run storybook` and verify `curl -I http://127.0.0.1:6006/mcp` returns a live endpoint such as `405 Method Not Allowed` with allowed methods. |
| Launcher-first ops flow | `过时` | Current repo scripts include `scripts/platform-macos.sh`, `scripts/docker-launcher-ui.sh`, `scripts/build-macos-launcher.sh`, and `tools/macos/Launcher.swift`. `platform-macos.sh docker-start` routes to the Docker launcher UI; `docker-full-start` routes to full modern-ui compose startup. | `ops-frontend/main/MERGED_OPS_FRONTEND.md` and `E_OPS/QUICKSTART.md` still lead with the older `main/ops/start-all.sh` path, so the docs do not reflect launcher-first startup. This lane records the blocker but does not rewrite E_OPS. | Run `bash scripts/platform-macos.sh docker-start` for launcher-first smoke, or `bash scripts/platform-macos.sh docker-full-start` for direct full-stack smoke. For the macOS app path, run `bash scripts/build-macos-launcher.sh` and verify the copied app starts without compile/runtime errors. |

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
3. Add a dedicated Storybook closure record after `storybook:build` and `/mcp` endpoint verification.
4. Update `E_OPS/QUICKSTART.md` and the main merged doc so launcher-first startup is the primary documented path, while preserving `docker-full-start` as the direct full-stack alternative.
5. Only after those gates pass, change graph/API rows from `需更新` to `已封口`; keep Storybook as `未封口` until both build and MCP evidence are attached.
