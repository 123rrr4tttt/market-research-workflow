# Wave16 Agent Chat I18N Slice Evidence - I18N Theme Modularization

Date: 2026-05-22

Worker: Wave16 worker #8 / `codex/devdocs-wave16-frontend-business-string-migration`

Scope: one low-risk business-string migration slice for the workbench Agent Chat page. This advances the Frontend I18N Theme Modularization lane beyond audit-only evidence, without claiming full business-copy localization.

## Code Slice

- Added an `agentChat` i18n catalog namespace with zh-CN and en-US strings for the Agent Chat session rail, stage labels, run signal labels, idle hint, quick commands, and composer controls.
- Wired `src/pages/AgentChatPage.tsx` to `useAppLocale()` and `translate()` for that page slice.
- Added `check:agent-chat-i18n-slice` to prevent the migrated rail/composer literals from returning as hardcoded page text.
- Extended existing business-string scanners to recognize `agentChat.*` as catalog keys.

## Evidence

Commands observed green:

```bash
npm --prefix main/frontend-modern run -s check:agent-chat-i18n-slice
npm --prefix main/frontend-modern run -s check:business-string-audit
python3 scripts/check_frontend_migration_boundary.py
npm --prefix main/frontend-modern run -s check:topology-platform
npm --prefix main/frontend-modern run -s check:layer-shell-contract
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest tests/checkers/test_check_frontend_migration_boundary_unittest.py
npm --prefix main/frontend-modern run lint
npm --prefix main/frontend-modern run build
```

Observed slice gate:

```json
{"status":"ok","gate_type":"agent_chat_i18n_slice","required_keys":31,"retired_page_snippets":14}
```

Observed business-string movement:

```json
{
  "check_business_string_audit": {
    "status": "ok",
    "remaining_total": 1896,
    "agent_chat_page": 220,
    "workbench_surface": 735,
    "i18n_catalog_key_allowed": 77
  },
  "frontend_migration_boundary": {
    "status": "ok",
    "business_gaps": 1824,
    "agent_chat_page": 203,
    "full_page_refactor_complete": false
  }
}
```

## Remaining Boundary

This is an actual migration slice, not a closure claim. The shell/module i18n and theme token boundaries remain green, but full business-copy localization is still open across Agent Chat and other high-count pages. Shared CURRENT_DEV indexes were intentionally not edited in this worker branch.
