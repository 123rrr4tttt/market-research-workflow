# Wave8-4 topology/i18n/theme contract evidence

Date: 2026-05-22

Scope: frontend topology closure evidence for `main/frontend-modern`.

## Result

Wave8-4 strengthens the existing `check:topology-platform` gate without changing frontend visual design.

The gate now proves that the topology entry points do not drift independently:

- `KernelModuleKey`, `moduleManifest`, `PAGE_PLACEMENT_BASELINE`, and `BASELINE_PAGE_INVENTORY` still cover the same 31 modes.
- `moduleManifest` remains the source for the module registry and hash adapter.
- `src/app/navigation/index.ts` still re-exports the kernel hash adapter instead of introducing a second route table.
- A/B/C layer IDs still map to `workbench`, `visualization`, and `management` surface kinds.
- Surface switching keeps `projectKey`, theme, locale, and deep-link-compatible route identity in the shared retain rule.

## Evidence

Command:

```bash
npm --prefix main/frontend-modern run -s check:topology-platform
```

Observed summary:

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
  }
}
```

The stronger gate is implemented in `main/frontend-modern/scripts/check_topology_platform_contract.mjs`.

## Boundary

No shared index was edited. No page visuals, CSS, or shell layout behavior were changed.
