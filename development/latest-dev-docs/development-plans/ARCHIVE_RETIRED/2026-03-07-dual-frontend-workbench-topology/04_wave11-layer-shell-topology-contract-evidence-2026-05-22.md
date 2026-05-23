# Wave11 layer-shell topology contract evidence

Date: 2026-05-22

Scope: bounded topology contract for `main/frontend-modern`, with no browser server requirement.

## Result

Wave11 adds a no-dependency static gate for the frontend layer shell topology.

The new gate proves that the current manifest, layered routes, and layer shell navigation cannot drift independently:

- every manifest module keeps the expected layer-to-surface mapping: A -> `workbench`, B -> `visualization`, C -> `management`;
- every manifest route keeps the expected layer route prefix: A -> `/workbench/`, B -> `/visual/`, C -> `/admin/`;
- `WorkbenchLayerShell`, `VisualizationLayerShell`, and `AdminLayerShell` each expose exactly the manifest modules for their layer, with no missing, extra, or duplicated modules;
- `FrontendKernelApp` dispatches layered routes to the matching shell;
- each layer shell consumes shared locale translation and passes a layer-specific `shellMode` into `ModuleRenderer`;
- shared theme token application remains anchored in `FrontendKernelApp`.

This is a topology contract slice. It does not claim that all page-level UI has been rewritten.

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

The broader existing checker was inspected and attempted:

```bash
npm --prefix main/frontend-modern run -s check:topology-platform
```

Current blocker in this worktree:

```text
Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'typescript' imported from .../main/frontend-modern/scripts/check_topology_platform_contract.mjs
```

The no-dependency checker above was added and run because frontend dependencies are not installed in this worktree.

## Remaining gaps

- No shared index was edited.
- This does not retire the old `AppShell`.
- This does not split heavy pages into final container/view boundaries.
- This does not claim completion of a full visual or interaction rewrite.
