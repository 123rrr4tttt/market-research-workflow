<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/23_agent-writing-selection-range-tools-2026-05-13.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/23_agent-writing-selection-range-tools-2026-05-13.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Writing Selection Range Tools - 2026-05-13

## Scope

This note closes the next `21_agent-goal-gap-and-optimization-direction-2026-05-13.md` gap around writing workbench selection/cursor integration. The previous state only put the selected text into the Agent prompt and relied on `anchor_text`; it did not expose the actual editor range as a stable write contract.

## Implemented

- `writing.document.insert_paragraph` now accepts explicit location fields:
  - `operation=replace_range` with `range_start` and `range_end`
  - `operation=insert_at_offset` with `cursor_offset`
  - `selection_snapshot` for selected text, offsets, line, active heading, and nearby context
- Agent writeback metadata now records these fields in `agent_update.locator` and folds the selection snapshot into provenance.
- The writing workbench Agent command now passes `selection_start`, `selection_end`, and `cursor_offset` from the Markdown editor selection state.
- The workbench prompt now prefers range/cursor operations first and only falls back to text-anchor operations when offsets are unavailable.
- Material ontology was tightened for writing research:
  - generic `帮我补充资料` remains collection/discovery oriented
  - writing-context material requests prefer internal project context first
  - explicit external writing material requests map to external discovery/search
  - only explicit import/ingest/source-library execution wording upgrades to external write/ingest risk

## Behavior Matrix

| User intent | Expected contract |
|---|---|
| Rewrite highlighted paragraph in the workbench | `writing.document.read` then `writing.document.insert_paragraph(operation=replace_range, range_start, range_end, selection_snapshot)` |
| Continue at the current cursor | `writing.document.insert_paragraph(operation=insert_at_offset, cursor_offset)` |
| Selected text exists but offsets are unavailable | fallback to `replace_text` / `insert_after_text` / `insert_before_text` with `anchor_text` |
| Writing asks to supplement materials without saying external | inspect `project.context.bundle` and internal project data first |
| Writing asks for external materials | use external discovery/search path; do not run source-library ingest unless user asks to import/execute |

## Verification

- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py -q -k "writing"` -> `7 passed, 33 deselected`
- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_agent_core_unittest.py -q -k "material_ontology or writing or tool_window_selects_project_material_context or generic_material_collection"` -> `10 passed, 33 deselected`
- `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `99 passed, 11 warnings`
- `npm run lint -- src/pages/WritingWorkbenchPage.tsx src/pages/AgentChatPage.tsx src/pages/agent-chat.css src/lib/types.ts` -> `0 errors, 1 existing CSS ignored warning`
- `npm run build` -> passed
- `npm run lint -- src/pages/WritingWorkbenchPage.tsx tests/e2e/writing-workbench.spec.ts` -> passed
- `npm run test:e2e -- tests/e2e/writing-workbench.spec.ts` -> `4 passed`

## Remaining Gaps From 21

- Cross-page long-task acceptance still needs broader browser matrix coverage beyond writing workbench.
- Durable long-task stage machines still need stronger refresh/reconnect evidence.
- The repeated model-owned tool loop needs more scenario coverage for investigation and source-search chains.
