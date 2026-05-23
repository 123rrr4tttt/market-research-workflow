# Wave21 Frontend I18N Closure Priority - Three-Layer Rewrite

Date: 2026-05-22

Worker: Wave21 frontend i18n closer / `codex/devdocs-wave21-frontend-i18n-closer`

Scope: closure-priority readback for `2026-03-15-frontend-three-layer-rewrite` and the related frontend i18n evidence stream. This wave intentionally avoids another average page-slice migration unless the remaining business-string backlog is small enough to close the lane.

## Decision

decision: `retained_partial`

The frontend i18n work is materially advanced but not close enough to seal. Wave16-Wave20 slice gates are green for Agent Chat, Projects, Catalog, Dashboard, and Process, but the static inventory still reports a broad remaining business-string backlog across kernel shells and many renderer-bound pages.

Can move from `CURRENT_DEV`: no.

Reason: the three-layer rewrite still has `full_business_string_migration_complete=false`, `page_refactor_complete=false`, and more than one thousand remaining text gaps. This is not a final small slice; moving it would hide an active implementation backlog.

## Evidence

Commands observed green:

```bash
npm --prefix main/frontend-modern run -s check:agent-chat-i18n-slice
npm --prefix main/frontend-modern run -s check:projects-i18n-slice
npm --prefix main/frontend-modern run -s check:catalog-page-i18n-slice
npm --prefix main/frontend-modern run -s check:dashboard-page-i18n-slice
npm --prefix main/frontend-modern run -s check:process-page-i18n-slice
npm --prefix main/frontend-modern run -s check:business-string-audit
python3 scripts/check_frontend_migration_boundary.py
```

Slice gates:

```json
{
  "agent_chat_i18n_slice": { "status": "ok", "required_keys": 31, "retired_page_snippets": 14 },
  "projects_i18n_slice": { "status": "ok", "required_keys": 26, "retired_page_snippets": 18 },
  "catalog_page_i18n_slice": { "status": "ok", "required_keys": 21, "retired_page_snippets": 15 },
  "dashboard_page_i18n_slice": { "status": "ok", "required_keys": 29, "retired_page_snippets": 24 },
  "process_page_i18n_slice": { "status": "ok", "required_keys": 68, "retired_page_snippets": 35 }
}
```

Business-string audit readback:

```json
{
  "status": "ok",
  "full_business_string_migration_complete": false,
  "remaining_migration_gaps_total": 1936,
  "by_layer": {
    "A": 735,
    "B": 613,
    "C": 537,
    "shared": 51
  }
}
```

Migration-boundary readback:

```text
OK frontend_migration_boundary=passed routes=31/31 renderers=31/31 surfaces=31/31 i18n=74/74 theme=48/48 business_gaps=1864 page_refactor_complete=false
```

## Remaining Blockers

The remaining blockers are internal backlog, not an external environment block:

- `src/pages/GraphPage.tsx`: 526 audit gaps.
- `src/pages/LlmDesignerPage.tsx`: 230 audit gaps.
- `src/pages/AgentChatPage.tsx`: 220 audit gaps after the Wave16 slice.
- `src/pages/OpsPage.tsx`: 179 audit gaps.
- `src/pages/WritingWorkbenchPage.tsx`: 171 audit gaps.
- `src/pages/ProcessPage.tsx`: 115 audit gaps after the Wave20 slice.
- Additional gaps remain in `IngestPage`, `ResourcePage`, `SettingsPage`, `CrawlerManagePage`, `PolicyPage`, kernel shells, and renderer glue.

The closure blocker is therefore not a missing checker. The checker stack is already useful and green; the open work is real migration breadth plus page-refactor acceptance.

## Closure Guidance

Do not continue adding single-page evidence waves unless the wave is explicitly tied to a closure threshold. The next useful work should be one of:

- a concentrated migration batch for the top backlog pages, starting with `GraphPage`, `LlmDesignerPage`, `OpsPage`, and `WritingWorkbenchPage`;
- a scoped closure redefinition that marks selected namespaces/pages as closed while retaining the full three-layer rewrite as partial;
- a strict business-string gate only after the remaining total is small enough for a final slice.

No frontend source files were changed in Wave21, so dependency-backed lint was not required for this closure-priority decision.

No shared `CURRENT_DEV`, `README`, or `MERGED_OVERVIEW` index was edited.
