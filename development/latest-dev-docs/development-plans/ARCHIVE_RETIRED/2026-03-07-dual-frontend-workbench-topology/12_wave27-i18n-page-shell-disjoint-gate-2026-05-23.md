# Wave27 I18N / Page-Shell Disjoint Gate - Dual Frontend Workbench Topology

Date: 2026-05-23

Worker: Wave27 frontend i18n worker B

Original scope before Wave28 retirement: `2026-03-07-dual-frontend-workbench-topology`, with readback against `2026-03-07-frontend-i18n-theme-modularization` and `2026-03-15-frontend-three-layer-rewrite`.

## Decision

decision: `can_transfer_to_three_layer`

The dual-frontend topology topic no longer has a separate repo-local implementation blocker. Its modern-only topology, layer-shell routing, i18n/theme platform anchors, and page placement contracts are covered by source gates.

This is not a claim that the whole frontend rewrite is closed. The remaining internal blockers belong to the three-layer rewrite lane:

- page-shell retirement is still open;
- `AppShell` is still an active compatibility/runtime path;
- full business-string migration remains broad;
- full page refactor acceptance remains false.

Recommended integration action: merge/retire the dual-frontend topic into the three-layer rewrite topic during the shared index/archive pass. Do not keep dual-frontend open only because three-layer page-shell work remains.

This Wave27 worker did not edit shared `CURRENT_DEV/INDEX.md`, `development-plans/INDEX.md`, `README.md`, or `MERGED_OVERVIEW.md` files.

## Disjoint Gate

Added a read-only frontend gate:

```bash
npm --prefix main/frontend-modern run -s check:i18n-page-shell-disjoint
```

Core readback:

```json
{
  "status": "ok",
  "gate_type": "i18n_page_shell_disjoint",
  "decision": {
    "dual_frontend_unique_blocker": false,
    "dual_frontend_can_transfer_to_three_layer": true,
    "frontend_i18n_platform_closed": true,
    "page_shell_retirement_complete": false,
    "three_layer_retains_page_shell_blocker": true
  },
  "i18n_platform": {
    "locales": ["zh-CN", "en-US"],
    "required_catalog_anchors": 6,
    "missing_catalog_anchors": [],
    "platform_leaks": []
  },
  "page_shell_boundary": {
    "blocker_markers_present": 5,
    "blocker_markers_total": 5
  }
}
```

The gate proves the useful closure split:

- i18n platform ownership is closed enough for the shared frontend contract: locale types, catalog anchors, exported entrypoints, and shell consumers are present;
- i18n platform files do not import or own shell/kernel runtime responsibilities;
- page-shell retirement remains explicit and separate, so a green i18n gate cannot accidentally close `AppShell` compatibility work.

## Closure Evidence

Topology/platform gate:

```bash
npm --prefix main/frontend-modern run -s check:topology-platform
```

Core readback:

```json
{
  "status": "ok",
  "modules": 31,
  "manifest_entries": 31,
  "placement_records": 15,
  "baseline_inventory_records": 15,
  "i18n_locales": ["zh-CN", "en-US"],
  "themes": ["light", "dark", "brand"],
  "failures": []
}
```

Layer-shell contract gate:

```bash
npm --prefix main/frontend-modern run -s check:layer-shell-contract
```

Core readback:

```json
{
  "status": "ok",
  "modules": 31,
  "layer_counts": { "A": 6, "B": 15, "C": 10 },
  "shell_coverage_counts": { "A": 6, "B": 15, "C": 10 },
  "failures": []
}
```

Business-string audit remains a retained three-layer blocker, not a dual-frontend blocker:

```bash
npm --prefix main/frontend-modern run -s check:business-string-audit
```

Core readback:

```json
{
  "status": "ok",
  "full_business_string_migration_complete": false,
  "remaining_migration_gaps": {
    "total": 1941,
    "by_layer": { "A": 735, "B": 618, "C": 537, "shared": 51 }
  }
}
```

Migration-boundary readback also keeps the page-refactor blocker explicit:

```bash
python3 scripts/check_frontend_migration_boundary.py
```

Output:

```text
OK frontend_migration_boundary=passed routes=31/31 renderers=31/31 surfaces=31/31 i18n=74/74 theme=48/48 business_gaps=1869 page_refactor_complete=false
```

## Remaining Blocker Owner

The remaining blocker owner was `ARCHIVE_CLOSED/2026-03-15-frontend-three-layer-rewrite`, not this dual-frontend topology topic. Wave32 later closed that successor blocker with the final frontend i18n gate.

The disjoint gate records these page-shell blockers as still present:

- `FrontendKernelApp` falls back to `<AppShell />` for unknown routes;
- `AppShell` still reads `window.location.hash` through `resolveShellModeFromHash`;
- `AppShell` still renders modules with `shellMode: 'legacy-shell'`;
- `AppShell` still mounts `FigmaSideNav` directly;
- kernel route resolution still classifies `legacy` and `unknown` route sources.

Closure implication: dual-frontend can be migrated or retired into the three-layer topic once the integration pass updates indexes. Wave32 completed the successor business-string closure, so this note is historical evidence rather than an active blocker statement.
