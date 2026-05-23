# Wave17 Projects Page I18N Slice Evidence - Frontend Three-Layer Rewrite

Date: 2026-05-22

Worker: Wave17 worker #7 / `codex/devdocs-wave17-frontend-page-i18n-slice`

Scope: one management-layer page slice after the Wave16 Agent Chat workbench slice. The selected page is `ProjectsPage`, a non-AgentChat component with obvious hardcoded create/list/action strings.

## Layer Relevance

- `ProjectsPage` remains a layer C management page; this worker did not edit layer routing, shell structure, or shared indexes.
- The slice reduces page-local business copy by moving create/list/action copy into `MESSAGE_CATALOGS`.
- The page-level gate verifies catalog shape/readback coverage for zh-CN and en-US and checks that retired hardcoded snippets do not reappear.

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

## Remaining Boundary

The three-layer rewrite remains partially open: this slice is not a full layer C localization pass, and other management pages still contain business-string gaps.
