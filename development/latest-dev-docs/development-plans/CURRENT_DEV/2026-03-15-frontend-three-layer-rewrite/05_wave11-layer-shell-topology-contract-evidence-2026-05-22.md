# Wave11 layer-shell three-layer contract evidence

Date: 2026-05-22

Scope: bounded three-layer rewrite contract for `main/frontend-modern`, with no browser server requirement.

## Result

Wave11 moves one more three-layer invariant into code: layered route prefixes, layer-specific shell dispatch, layer shell navigation coverage, shared locale/theme anchors, and renderer shell mode are now checked by a no-dependency static gate.

The gate verifies:

- A/B/C manifest entries keep their expected route families: `/workbench/`, `/visual/`, and `/admin/`;
- A/B/C manifest entries keep their expected surface kinds: `workbench`, `visualization`, and `management`;
- `FrontendKernelApp` dispatches A, B, and C routes to `WorkbenchLayerShell`, `VisualizationLayerShell`, and `AdminLayerShell`;
- each layer shell navigation list covers exactly the manifest entries for that layer;
- each layer shell passes its own renderer mode: `workbench`, `visualization`, or `admin`;
- runtime module navigation uses layered route hashes.

The code change is intentionally small: `AdminLayerShell` now passes `shellMode="admin"` to `ModuleRenderer`, matching the already-present workbench and visualization shell modes.

## Evidence

Command:

```bash
npm --prefix main/frontend-modern run -s check:layer-shell-contract
```

Observed summary:

```json
{
  "status": "ok",
  "modules": 31,
  "layer_counts": { "A": 6, "B": 15, "C": 10 },
  "shell_coverage_counts": { "A": 6, "B": 15, "C": 10 },
  "route_prefixes": { "A": "/workbench/", "B": "/visual/", "C": "/admin/" },
  "surface_by_layer": { "A": "workbench", "B": "visualization", "C": "management" }
}
```

Implemented by:

- `main/frontend-modern/scripts/check_layer_shell_contract.mjs`
- `main/frontend-modern/package.json`
- `main/frontend-modern/src/app/kernel/AdminLayerShell.tsx`

## Existing checker blocker

The existing topology platform checker was inspected and attempted:

```bash
npm --prefix main/frontend-modern run -s check:topology-platform
```

Current blocker in this worktree:

```text
Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'typescript' imported from .../main/frontend-modern/scripts/check_topology_platform_contract.mjs
```

The new checker is intentionally dependency-free so this lane still has a runnable frontend contract gate.

## Remaining gaps

- This does not claim the full three-layer rewrite is complete.
- `AppShell` retirement remains open.
- Heavy page container/view splitting remains open.
- Page-level object/view contracts remain concentrated in large pages, especially visualization and workbench pages.
- No shared index was edited.
