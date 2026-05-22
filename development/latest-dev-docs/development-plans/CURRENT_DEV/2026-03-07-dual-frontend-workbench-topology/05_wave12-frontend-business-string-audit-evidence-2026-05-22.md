# Wave12 frontend business-string audit evidence

Date: 2026-05-22

Scope: bounded audit gate for `main/frontend-modern` kernel/module surfaces. This is evidence for the dual frontend workbench topology lane; it does not claim full UI migration.

## Result

Wave12 adds a dependency-light static checker for frontend business-string readiness:

- validates that the 31 registered `moduleManifest` entries still resolve to renderer component surfaces;
- reports A/B/C layer and surface coverage for workbench, visualization, and management modules;
- separates known allowed technical literals from human-facing strings that still need catalog/i18n migration;
- keeps remaining raw business strings as an audit inventory rather than failing the current partial state.

Observed layer/surface coverage:

```json
{
  "A": { "surface": "workbench", "modules": 6, "component_files": 5 },
  "B": { "surface": "visualization", "modules": 15, "component_files": 4 },
  "C": { "surface": "management", "modules": 10, "component_files": 6 }
}
```

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
  "remaining_gaps_by_surface": {
    "workbench": 774,
    "visualization": 583,
    "management": 527,
    "kernel": 51
  }
}
```

Implemented by:

- `main/frontend-modern/scripts/check_frontend_business_string_audit.mjs`
- `main/frontend-modern/package.json`

Relevant existing checker also remains green:

```bash
npm --prefix main/frontend-modern run -s check:layer-shell-contract
```

## Readiness boundary

This advances the dual-frontend topology from shell contract coverage to business-string audit coverage. The raw-string inventory confirms the topology is still partial: the workbench, visualization, management, and shared kernel surfaces all retain user-facing literals outside the i18n catalog.

The highest remaining page-level migration clusters are:

- `src/pages/GraphPage.tsx`: 497 gaps
- `src/pages/AgentChatPage.tsx`: 259 gaps
- `src/pages/LlmDesignerPage.tsx`: 230 gaps
- `src/pages/OpsPage.tsx`: 179 gaps
- `src/pages/WritingWorkbenchPage.tsx`: 171 gaps

No shared navigation index was edited.
