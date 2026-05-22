# Frontend Runtime Visual Evidence

> Date: 2026-05-22 (US/Pacific)
> Lane: Wave4 H, `frontend runtime and visual evidence`
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/frontend-runtime-visual`
> Branch: `codex/devdocs-wave4-frontend-runtime-visual`

## Scope

This evidence package complements the Wave3 static topology/i18n/theme contract with a browser runtime check. It does not change `GraphPage.tsx` and does not depend on backend services.

## Added Gate

```bash
npm --prefix main/frontend-modern run check:runtime-visual
```

The gate runs Playwright against Vite and mocks `/api/v1/**` responses in the browser test. It verifies:

- runtime theme token application on `document.documentElement`;
- Settings page language/theme controls update shell labels and theme state;
- Layer C Admin, Layer A Workbench, and Layer B Visualization shells render through real routes;
- cross-layer navigation uses the runtime `LayerSwitch`;
- shell nav and stage regions have stable non-overlapping layout boxes at desktop viewport.

## Evidence

- Runtime contract JSON: [runtime_visual_contract.json](./runtime_visual_contract.json)
- Admin/settings screenshot: [admin-settings-brand-en.png](./admin-settings-brand-en.png)
- Workbench/writing screenshot: [workbench-writing-brand-en.png](./workbench-writing-brand-en.png)
- Visualization/dashboard screenshot: [visual-dashboard-brand-en.png](./visual-dashboard-brand-en.png)

## Validation Results

Executed during this lane:

```bash
npm --prefix main/frontend-modern run lint
npm --prefix main/frontend-modern run check:runtime-visual
python3 changed-doc link check
git diff --check
```

All checks passed in the assigned worktree.
