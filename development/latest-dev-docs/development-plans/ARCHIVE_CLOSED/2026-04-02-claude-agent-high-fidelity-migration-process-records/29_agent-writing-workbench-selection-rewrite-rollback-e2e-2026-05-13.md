# Agent Writing Workbench Selection Rewrite Rollback E2E

Date: 2026-05-13
Status: active gap reduction, no closure claim

## Scope

This note covers the next gap from `21_agent-goal-gap-and-optimization-direction-2026-05-13.md` around writing workbench collaboration:

- selection/cursor context must reach AgentCore;
- AgentCore must edit through writing tools, not the legacy writing AI module;
- range replacement must be reviewable and reversible from the workbench UI;
- browser validation must prove the user-facing chain, not just backend unit behavior.

## Implementation

- Agent writing updates now store `replaced_text` and `replaced_text_truncated` for replacement operations.
- `writing.document.insert_paragraph(operation=replace_range)` records the original selected range before mutation.
- The writing workbench reject path now restores original text for `replace_range` / `replace_text` updates instead of deleting the Agent-written span.
- The diff panel now exposes the original selected text as rollback source.
- The workbench quick action copy now asks AgentCore to prefer `replace_range` / `insert_at_offset` over anchor-only fallback operations.
- The deterministic real-backend E2E provider can read the workbench context JSON and execute:
  - `writing.document.read`
  - `writing.document.insert_paragraph(operation=replace_range)`

## Validation

- Backend focused range tests:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py -q -k "writing_insert_can_replace_selected_range or writing_insert_requires_version_lock"` -> `2 passed, 3 warnings`
- Backend Agent matrix:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `104 passed, 11 warnings`
- Frontend lint:
  - `npm run lint -- tests/e2e/writing-workbench.spec.ts src/pages/WritingWorkbenchPage.tsx` -> passed
- Real-backend writing workbench E2E:
  - backend: `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8021`
  - frontend: `AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/writing-workbench.spec.ts --reporter=line` -> `5 passed`
- Real-backend AgentChat regression:
  - `AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line` -> `2 passed`

## Result

The workbench row is materially stronger:

| Row | Before | After |
| --- | --- | --- |
| Workbench edit | Range tools and review UI existed, but reject semantics for replacement were delete-like. | Selection -> AgentCore -> `replace_range` -> diff/provenance -> locate -> reject restores original text in real browser E2E. |
| User-visible review | Diff showed inserted text and provenance. | Diff also shows the rollback source for replaced selections. |

## Remaining Gap

This does not claim the whole Agent goal is complete. Remaining gaps from the active 21 document still include:

- candidate-to-ingest review UX for live external search results;
- broader live provider quality validation beyond deterministic scripted E2E;
- richer writing canvas operations beyond Markdown range replacement, such as citation insertion and multi-block structured edits.
