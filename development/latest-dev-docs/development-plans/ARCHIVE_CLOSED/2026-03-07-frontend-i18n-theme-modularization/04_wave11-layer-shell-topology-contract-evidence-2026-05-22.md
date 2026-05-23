# Wave11 layer-shell i18n/theme contract evidence

Date: 2026-05-22

Scope: bounded shell i18n/theme contract for `main/frontend-modern`, with no browser server requirement.

## Result

Wave11 adds a no-dependency static gate that keeps the layered frontend shells tied to shared platform i18n/theme primitives.

The gate now checks that:

- `FrontendKernelApp` still reads the shared app theme and applies shared theme tokens;
- all three layer shells read the shared locale with `useAppLocale()`;
- all three layer shells resolve navigation labels through `translate(...)`;
- all three layer shells pass their layer-specific `shellMode` into `ModuleRenderer`;
- layer shell navigation coverage is derived from the same module contract shape as the route manifest.

This strengthens the shell/platform contract without claiming full page-level business-content localization or a full theme restyling.

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

The existing catalog/token checker was inspected and attempted:

```bash
npm --prefix main/frontend-modern run -s check:topology-platform
```

Current blocker in this worktree:

```text
Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'typescript' imported from .../main/frontend-modern/scripts/check_topology_platform_contract.mjs
```

The no-dependency checker above does not replace the TypeScript AST checker. It covers the layer-shell contract while dependencies are unavailable.

## Remaining gaps

- Full business-content localization remains outside this slice.
- This does not prove every CSS selector consumes shared theme tokens.
- This does not retire old compatibility styling.
- No shared index was edited.
