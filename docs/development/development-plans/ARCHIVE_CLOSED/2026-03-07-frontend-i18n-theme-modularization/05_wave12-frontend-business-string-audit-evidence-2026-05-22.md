<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-07-frontend-i18n-theme-modularization/05_wave12-frontend-business-string-audit-evidence-2026-05-22.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-frontend-i18n-theme-modularization/05_wave12-frontend-business-string-audit-evidence-2026-05-22.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Wave12 frontend business-string audit evidence

Date: 2026-05-22

Scope: bounded audit/readiness gate for `main/frontend-modern` business strings. This is evidence for the frontend i18n/theme modularization lane; it does not claim full business-content localization or full theme restyling.

## Result

Wave12 adds a dependency-light checker that turns the open business-string migration gap into a repeatable audit:

- confirms every manifest module still has `shell.title.*`, `navigation.item.*`, and `navigation.group.*` catalog anchoring;
- scans selected kernel files plus renderer-bound page components;
- classifies allowed literals such as imports, routes, class names, module keys, enum tokens, catalog keys, and localized catalog entries;
- reports visible strings, labels, placeholders, titles, aria labels, and templates as remaining migration gaps.

The checker deliberately exits green when remaining migration gaps are present. Its purpose is to make the i18n backlog measurable and regression-readable, not to pretend page-level migration is done.

## Evidence

Command:

```bash
npm --prefix main/frontend-modern run -s check:business-string-audit
```

Observed summary:

```json
{
  "status": "ok",
  "gate_type": "audit_readiness",
  "full_business_string_migration_complete": false,
  "modules": 31,
  "checked_files": 25,
  "known_allowed_literals_total": 4890,
  "remaining_migration_gaps_total": 1935,
  "remaining_gaps_by_category": {
    "visible_label": 78,
    "visible_string": 121,
    "human_text_literal": 843,
    "visible_template": 84,
    "visible_aria-label": 16,
    "visible_jsx_text": 725,
    "visible_placeholder": 46,
    "visible_title": 22
  }
}
```

Implemented by:

- `main/frontend-modern/scripts/check_frontend_business_string_audit.mjs`
- `main/frontend-modern/package.json`

Related shell/platform gate remains green:

```bash
npm --prefix main/frontend-modern run -s check:layer-shell-contract
```

## Remaining migration map

The current readiness inventory is:

```json
{
  "workbench": 774,
  "visualization": 583,
  "management": 527,
  "kernel": 51
}
```

Recommended next refactor order:

1. Move shared kernel labels/status text into the existing catalog namespaces or a small new shared namespace.
2. Migrate high-count page clusters by surface, starting with `GraphPage`, `AgentChatPage`, `LlmDesignerPage`, `OpsPage`, and `WritingWorkbenchPage`.
3. Keep this checker as the audit gate while separate page-level visual/regression checks prove behavior.

No shared navigation index was edited.
