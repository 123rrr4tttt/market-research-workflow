# Frontend Topology / I18N / Theme Contract Evidence

> Date: 2026-05-22 (US/Pacific)
> Lane: Wave3 I, `frontend topology/i18n/theme closure`
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/frontend-topology-theme`
> Branch: `codex/devdocs-wave3-frontend-topology-theme`

## Scope

This evidence package verifies the current `main/frontend-modern` topology, shell i18n, theme token, and module manifest contracts without doing a broad UI rewrite.

The lane targeted three outdated CURRENT_DEV topics:

- `2026-03-07-dual-frontend-workbench-topology`
- `2026-03-07-frontend-i18n-theme-modularization`
- `2026-03-15-frontend-three-layer-rewrite`

## Added Gate

The package adds a repeatable static gate:

```bash
npm --prefix main/frontend-modern run check:topology-platform
```

The gate reads TypeScript source with the TypeScript compiler API and checks:

- `KernelModuleKey` covers the same 31 modes as `moduleManifest`;
- every mode is present once in the topology placement baseline and baseline inventory;
- baseline inventory surfaces match the topology placement matrix;
- every module title, nav label, and nav group has non-empty `zh-CN` and `en-US` catalog values;
- `light`, `dark`, and `brand` themes all expose the shared token groups;
- `AppShell` consumes locale/theme contracts and applies theme tokens;
- `FigmaSideNav` consumes module registry, filters by interaction surface, and resolves labels through i18n keys.

## Evidence

- Contract result: [topology_platform_contract.json](./topology_platform_contract.json)

Key result:

```json
{
  "status": "ok",
  "modules": 31,
  "manifest_entries": 31,
  "placement_records": 15,
  "baseline_inventory_records": 15,
  "topology_surfaces": {
    "management": 20,
    "workbench": 11
  },
  "i18n_locales": ["zh-CN", "en-US"],
  "themes": ["light", "dark", "brand"],
  "failures": []
}
```

## Current Closure Status

- `dual-frontend topology`: no longer stale as a planning-only topic. It now maps to `src/app/topology/*`, `FigmaSideNav` surface switching, and the static contract gate.
- `frontend i18n/theme modularization`: shell-level i18n, locale persistence, theme persistence, settings controls, module registry labels, and theme tokens are present. Full business-content localization remains out of scope.
- `frontend three-layer rewrite`: single module manifest, legacy hash adapter, A/B/C layer shells, B-layer `VisualizationLayerShell`, and route contracts are present. Residual work remains around reducing `AppShell` to compatibility-only duties and splitting heavy pages.

## Validation Results

Executed during this lane:

```bash
npm --prefix main/frontend-modern run check:topology-platform
npm --prefix main/frontend-modern run lint
python3 changed-doc link check
git diff --check
```

All four checks passed in the assigned worktree.
