# Wave14 frontend migration boundary evidence

Date: 2026-05-22

Scope: static migration-boundary gate for the frontend three-layer rewrite. This evidence covers route/surface/i18n/theme/business-string measurement only; it does not change UI behavior or claim the full page rewrite is complete.

## Result

Wave14 adds a root-level Python checker that reads the frontend source directly:

- parses `moduleManifest` and `KernelModuleKey` to validate all A/B/C modules;
- parses `renderKernelModuleContent` to confirm every module has a renderer-bound page;
- verifies A/workbench, B/visualization, and C/management route-surface coverage;
- verifies page placement and baseline inventory coverage for every module;
- verifies catalog and theme token coverage;
- classifies renderer-bound pages as locally structural-sealed but still open at the full page refactor layer when business strings remain.

## Evidence

Command:

```bash
python3 scripts/check_frontend_migration_boundary.py
```

Observed summary:

```text
OK frontend_migration_boundary=passed routes=31/31 renderers=31/31 surfaces=31/31 i18n=74/74 theme=48/48 business_gaps=1863 page_refactor_complete=false
```

Three-layer snapshot:

```json
{
  "module_counts_by_layer": {
    "A": 6,
    "B": 15,
    "C": 10
  },
  "module_counts_by_route_surface": {
    "management": 10,
    "visualization": 15,
    "workbench": 6
  },
  "full_page_refactor_boundary": {
    "pages_total": 15,
    "state_counts": {
      "structural_sealed_text_open": 15
    },
    "full_page_refactor_complete": false
  }
}
```

Implemented by:

- `scripts/check_frontend_migration_boundary.py`
- `tests/checkers/test_check_frontend_migration_boundary_unittest.py`

## Rewrite boundary

This slice locally seals the static migration boundary for routes, renderer bindings, surfaces, i18n shell keys, and theme tokens. The full page rewrite remains open: all 15 renderer-bound pages still have remaining business-string gaps and are therefore classified as `structural_sealed_text_open`, not `locally_sealed`.

Highest remaining full-page refactor targets:

```json
{
  "src/pages/GraphPage.tsx": 497,
  "src/pages/AgentChatPage.tsx": 242,
  "src/pages/LlmDesignerPage.tsx": 230,
  "src/pages/OpsPage.tsx": 171,
  "src/pages/WritingWorkbenchPage.tsx": 171
}
```

No shared navigation index was edited.
