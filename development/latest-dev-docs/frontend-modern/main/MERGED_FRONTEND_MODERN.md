# Frontend Modern Merged Current-State Document

> Updated: 2026-05-22 (US/Pacific)
> Scope: `main/frontend-modern` README, package scripts, Storybook configuration, and Playwright E2E layout.
> Write boundary: documentation index only; no frontend source files were changed in this lane.

## 1. Canonical App Surface

`main/frontend-modern` is the active React + Vite frontend. The current package metadata identifies it as `frontend-modern` version `0.1.8-rc1`, with:

- React `^19.2.0`
- Vite `^7.3.1`
- TypeScript `~5.9.3`
- Storybook `^10.3.4`
- Playwright `^1.58.2`

The local development path remains:

```bash
cd main/frontend-modern
VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
```

`vite.config.ts` proxies `/api` to `VITE_API_PROXY_TARGET`, defaulting to `http://localhost:8000`, and uses port `5173` unless `PORT` is supplied.

## 2. Package Scripts

Current scripts from `main/frontend-modern/package.json`:

| Script | Command | Current role |
|---|---|---|
| `dev` | `vite` | local development server |
| `build` | `tsc -b && vite build` | production build gate |
| `lint` | `eslint .` | static lint gate |
| `preview` | `vite preview` | local production preview |
| `storybook` | `storybook dev -p 6006 --host 0.0.0.0` | Storybook dev server |
| `storybook:build` | `storybook build` | static Storybook build |
| `test:e2e` | `playwright test` | full Playwright E2E suite |
| `test:e2e:runtime` | `playwright test tests/e2e/runtime-smoke.spec.ts` | runtime smoke E2E lane |
| `test:e2e:headed` | `playwright test --headed` | headed Playwright run |
| `test:ingest-smoke` | `../backend/scripts/run_ingest_flow_smoke.sh` | backend-assisted ingest smoke |

There is no generic `npm test` script in this package. The current frontend validation surface is therefore lint/build, Storybook, and Playwright E2E.

## 3. Storybook And MCP Status

Storybook is configured in `main/frontend-modern/.storybook/main.ts` with:

- framework: `@storybook/react-vite`
- story glob: `../src/**/*.stories.@(ts|tsx)`
- addons: `@storybook/addon-docs` and `@storybook/addon-mcp`
- MCP toolsets: `dev=true`, `docs=true`, `test=false`

Current source inventory contains 39 `*.stories.tsx` files. The README describes three intended Storybook groupings:

- `Component Stories`
- `Container Stories`
- `Shell Stories`

The current README also names high-value page surfaces for Storybook/MCP consumption, including `IngestPage`, `WritingWorkbenchPage`, `GraphPage`, `SettingsPage`, `ProcessPage`, and `LlmDesignerPage`.

Current gate evidence was refreshed on 2026-05-22:

- `npm --prefix main/frontend-modern run storybook:build` completed successfully.
- `@storybook/addon-mcp` is declared in `package.json` and enabled in `.storybook/main.ts` with `dev=true`, `docs=true`, and `test=false`.
- `curl -I http://127.0.0.1:6006/mcp` returned `405 Method Not Allowed` with `allow: GET, POST, DELETE, OPTIONS`, proving the MCP endpoint is mounted.
- Evidence package: [../../automation-runs/storybook-launcher-gates/2026-05-22/README.md](../../automation-runs/storybook-launcher-gates/2026-05-22/README.md).

## 4. E2E Status

Playwright is configured by `main/frontend-modern/playwright.config.ts`:

- test directory: `tests/e2e`
- base URL: `http://127.0.0.1:4173`
- web server: `npm run dev -- --host 127.0.0.1 --port 4173`
- project: Chromium desktop
- CI behavior: `forbidOnly`, 2 retries, 1 worker

Current source inventory contains 8 E2E specs:

- `agent-chat-real-backend-long-task.spec.ts`
- `agent-chat-writing-crossflow.spec.ts`
- `agent-chat.spec.ts`
- `graphpage.spec.ts`
- `homepage.spec.ts`
- `ingest-single-url.spec.ts`
- `runtime-smoke.spec.ts`
- `writing-workbench.spec.ts`

## 5. Documentation Accuracy Notes

- The previous `frontend-modern/main/LLM_DESIGNER_UI_REPLICA_BRIEF.md` file was moved to `frontend-modern/F_PLAN/LLM_DESIGNER_UI_REPLICA_BRIEF.md` so `main/` keeps the standard entry shape.
- `main/frontend-modern/README.md` remains the source-facing operational README. It includes the current Storybook, E2E, Docker, and API alignment notes, but its docker-compose example section appears to keep explanatory prose inside a fenced `yaml` block. This lane did not edit that source README because the write boundary is the latest-dev-docs index surface.
- This document records current source state and navigation status. Storybook/MCP gates were executed in the 2026-05-22 `storybook-launcher-gates` lane; broader frontend build and Playwright runtime gates remain separate.

## 6. Recommended Merge Check

Before merging this branch into a shared integration branch, run:

```bash
git diff --check
```

and a Markdown link check over:

- `development/latest-dev-docs/frontend-modern/INDEX.md`
- `development/latest-dev-docs/frontend-modern/main/index.md`
- `development/latest-dev-docs/frontend-modern/main/MERGED_FRONTEND_MODERN.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`
