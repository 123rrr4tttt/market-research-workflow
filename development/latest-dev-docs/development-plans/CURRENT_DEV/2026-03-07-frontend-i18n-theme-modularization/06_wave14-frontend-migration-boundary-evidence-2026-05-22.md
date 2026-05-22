# Wave14 frontend migration boundary evidence

Date: 2026-05-22

Scope: static i18n/theme migration-boundary gate for `main/frontend-modern`. This evidence advances the frontend i18n/theme modularization lane without claiming full business-content localization or full theme restyling.

## Result

Wave14 adds `scripts/check_frontend_migration_boundary.py`, a dependency-light checker that:

- confirms every `moduleManifest` title, nav label, and nav group key exists in `MESSAGE_KEY_SHAPE`;
- confirms the required catalog keys are non-empty in both `zh-CN` and `en-US`;
- confirms app locale/theme settings controls remain statically wired;
- confirms all `light`, `dark`, and `brand` theme token leaves are present and applied;
- keeps remaining page business strings as an explicit migration backlog rather than a hard failure.

## Evidence

Command:

```bash
python3 scripts/check_frontend_migration_boundary.py
```

Observed summary:

```text
OK frontend_migration_boundary=passed routes=31/31 renderers=31/31 surfaces=31/31 i18n=74/74 theme=48/48 business_gaps=1863 page_refactor_complete=false
```

i18n/theme snapshot:

```json
{
  "i18n_coverage": {
    "expected_catalog_keys": 74,
    "present_catalog_keys_in_shape_and_locales": 74,
    "locales": [
      "zh-CN",
      "en-US"
    ]
  },
  "theme_coverage": {
    "themes": [
      "light",
      "dark",
      "brand"
    ],
    "expected_token_leaves": 48,
    "present_token_leaves": 48,
    "settings_control_static_markers_present": true
  }
}
```

Implemented by:

- `scripts/check_frontend_migration_boundary.py`
- `tests/checkers/test_check_frontend_migration_boundary_unittest.py`

## Remaining migration map

The structural i18n/theme boundary is locally sealed for shell/module navigation and theme token coverage. Full business-string migration remains open:

```json
{
  "checked_files_total": 23,
  "gap_free_files": 1,
  "remaining_migration_gaps_total": 1863,
  "remaining_gaps_by_surface": {
    "kernel": 64,
    "management": 479,
    "visualization": 570,
    "workbench": 750
  },
  "remaining_gaps_by_category": {
    "human_text_literal": 978,
    "visible_aria-label": 16,
    "visible_jsx_text": 724,
    "visible_label": 78,
    "visible_placeholder": 45,
    "visible_title": 22
  }
}
```

No shared navigation index was edited.
