# Wave17 Projects Page I18N Slice Evidence - Dual Frontend Workbench Topology

Date: 2026-05-22

Worker: Wave17 worker #7 / `codex/devdocs-wave17-frontend-page-i18n-slice`

Scope: localized business-string movement for the management-layer Projects page in `main/frontend-modern`, staying inside the existing frontend topology and avoiding shared supervisor index edits.

## Topology Relevance

- The slice keeps `ProjectsPage` mounted through the existing module topology; no routes, module manifest entries, legacy hashes, or layer assignments changed.
- The page now consumes the shared app locale through the same platform i18n entrypoint used by shell and Agent Chat migration slices.
- The dedicated Projects page checker is dependency-light and can be run independently from browser/e2e gates.

## Evidence

Commands observed green:

```bash
npm --prefix main/frontend-modern run -s check:projects-i18n-slice
npm --prefix main/frontend-modern run -s check:business-string-audit
python3 scripts/check_frontend_migration_boundary.py
npm --prefix main/frontend-modern run -s lint
```

Observed migration-boundary summary:

```text
OK frontend_migration_boundary=passed routes=31/31 renderers=31/31 surfaces=31/31 i18n=74/74 theme=48/48 business_gaps=1836 page_refactor_complete=false
```

## Remaining Boundary

This does not close the dual-frontend or topology lanes. It only proves that one management page can move visible business strings into the shared catalog while preserving route/surface contracts.
