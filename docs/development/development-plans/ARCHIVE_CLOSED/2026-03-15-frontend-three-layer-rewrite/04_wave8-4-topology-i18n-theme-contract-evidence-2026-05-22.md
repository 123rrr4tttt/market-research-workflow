# Wave8-4 three-layer contract evidence

Date: 2026-05-22

Scope: frontend three-layer rewrite closure evidence for `main/frontend-modern`.

## Result

Wave8-4 strengthens the platform contract that the three-layer rewrite depends on.

The gate now checks that:

- A-layer modules remain `workbench` surface modules.
- B-layer modules remain `visualization` surface modules.
- C-layer modules remain `management` surface modules.
- The module registry and navigation hash adapter are still generated from `moduleManifest`.
- Shell title, side navigation labels, locale controls, theme controls, and token groups still use the shared platform contracts.

This moves the platform-contract part of T1/T2 evidence beyond existence checks and toward drift prevention. Remaining three-layer work is still page-boundary depth, especially heavy page split depth, not missing platform topology/i18n/theme primitives.

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
  "nav_groups": 5,
  "themes": ["light", "dark", "brand"]
}
```

The stronger gate is implemented in `main/frontend-modern/scripts/check_topology_platform_contract.mjs`.

## Boundary

No shared index was edited. No visual rewrite or page-container restructuring was performed in this slice.
