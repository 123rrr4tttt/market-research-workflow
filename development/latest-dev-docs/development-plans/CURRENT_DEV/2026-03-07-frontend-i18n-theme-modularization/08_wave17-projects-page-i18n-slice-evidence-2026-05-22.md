# Wave17 Projects Page I18N Slice Evidence - I18N Theme Modularization

Date: 2026-05-22

Worker: Wave17 worker #7 / `codex/devdocs-wave17-frontend-page-i18n-slice`

Scope: one bounded non-AgentChat page-level business-string migration slice for `ProjectsPage`. This extends the Wave16 Agent Chat slice without claiming full frontend business-copy localization.

## Code Slice

- Added a `projects` i18n catalog namespace with zh-CN and en-US strings for the Projects page create form, template create controls, list header, action buttons, empty state, current marker, and missing-key error.
- Wired `src/pages/ProjectsPage.tsx` to `useAppLocale()` and `translate()`.
- Added `check:projects-i18n-slice` to prevent the migrated Projects page literals from returning as hardcoded page text.
- Extended the business-string audit and migration-boundary scanners so `projects.*` catalog keys are treated as i18n catalog references.

## Evidence

Commands observed green:

```bash
npm --prefix main/frontend-modern run -s check:projects-i18n-slice
npm --prefix main/frontend-modern run -s check:business-string-audit
python3 scripts/check_frontend_migration_boundary.py
npm --prefix main/frontend-modern run -s lint
```

Observed slice gate:

```json
{"status":"ok","gate_type":"projects_i18n_slice","required_keys":26,"retired_page_snippets":18}
```

Observed business-string scan:

```json
{
  "check_business_string_audit": {
    "status": "ok",
    "remaining_total": 1908,
    "projects_page": 4,
    "i18n_catalog_key_allowed": 104
  },
  "frontend_migration_boundary": {
    "status": "ok",
    "business_gaps": 1836,
    "full_page_refactor_complete": false
  }
}
```

## Remaining Boundary

This is a page-level migration slice only. `ProjectsPage` still has a small number of non-migrated scanner gaps around technical/service tokens, and other frontend pages remain open for future business-string migration. Shared CURRENT_DEV indexes were intentionally not edited in this worker branch.
