<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/26_agent-real-backend-source-intake-browser-e2e-2026-05-13.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/26_agent-real-backend-source-intake-browser-e2e-2026-05-13.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Real Backend Source Intake Browser E2E

Date: 2026-05-13
Status: active gap slice, not final closure
Mainline: `21_agent-goal-gap-and-optimization-direction-2026-05-13.md`

## Purpose

This pass closes the browser-evidence gap left by `25_agent-model-owned-internal-external-tool-loop-2026-05-13.md`: source intake and writing output now have a real backend browser scenario rather than only mocked AgentChat streams or backend unit coverage.

This is still not a full Claude Code level closure claim. It covers the long-task/source-intake browser row and keeps the full acceptance matrix open for a later audit.

## Implementation

- `AgentCore` long-task and writing tool windows now expose `ingest.source_library.run`, so a model-owned loop can proceed from external discovery into governed source intake without falling back to `agent_batch`.
- AgentCore turn budgets are now profile-aware:
  - normal conversation/project reads keep the existing small loop budget;
  - long-task, writing-workbench, and material-collection profiles get enough iterations/tool calls for internal evidence, external discovery, source intake, leads, writing, and stage updates.
- Added a default-off E2E scripted provider gate:
  - setting: `agent_core_e2e_scripted_provider_enabled`;
  - env: `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true`;
  - it is only for deterministic real-backend browser testing and is disabled by default.
- Added deterministic E2E source dispatch for `e2e.*` source-library item keys while the scripted provider gate is enabled. This proves the real `ingest.source_library.run` tool boundary is exercised without launching external collection.
- AgentChat long-task stage cards now render object-shaped `next_actions` as readable text instead of `[object Object]`, and prefer the latest next action.

## Browser Scenario

New test: `main/frontend-modern/tests/e2e/agent-chat-real-backend-long-task.spec.ts`

The test starts from the browser and calls the real backend `/api/v1/agent-chat/turn/stream` endpoint. It does not route/mock the AgentChat stream in Playwright.

Covered chain:

1. User asks for a long writing investigation with internal-first and external supplementation.
2. Real backend AgentCore stream emits:
   - `project.context.bundle`
   - `agent_long_task.stage.update`
   - `source.discovery.plan`
   - `ingest.source_library.run`
   - `agent_investigation.leads.append`
   - `writing.document.insert_paragraph`
3. AgentChat displays source intake counters and writing diff cards.
4. Browser hard refresh preserves the same stage state from backend session artifacts/events.
5. Writing workbench opens the backend-created draft in the same temporary E2E project.

## Verification

- Backend focused:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q -k "tool_window_keeps_general_chat_empty or long_task_chat_api_has_enough_iterations or model_owned_loop_internal_first"` -> `3 passed, 61 deselected, 11 warnings`
- Backend Agent matrix:
  - `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_interactive_agent_runtime_unittest.py main/backend/tests/unit/test_agent_run_loop_unittest.py main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/integration/test_agent_chat_api_unittest.py -q` -> `103 passed, 11 warnings`
- Frontend lint:
  - `npm run lint -- src/pages/AgentChatPage.tsx tests/e2e/agent-chat-real-backend-long-task.spec.ts` -> passed
- Existing AgentChat browser matrix:
  - `npm run test:e2e -- tests/e2e/agent-chat.spec.ts --reporter=line` -> `10 passed`
- Real-backend browser source-intake scenario:
  - backend command: `AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED=true PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m uvicorn app.main:app --host 127.0.0.1 --port 8021`
  - test command: `AGENT_CORE_REAL_BACKEND_E2E=1 VITE_API_PROXY_TARGET=http://127.0.0.1:8021 npm run test:e2e -- tests/e2e/agent-chat-real-backend-long-task.spec.ts --reporter=line` -> `1 passed`
- Frontend build:
  - `npm run build` -> passed

## Remaining Gaps From 21

- This pass proves one real-backend long-task/source-intake browser scenario, but the full acceptance matrix still needs a row-by-row audit.
- External web/MCP search is still not broadly enabled; this test uses deterministic source intake dispatch, not live external fetch.
- Workbench accept/reject/provenance is covered by existing writing E2E, but a single browser test that combines live AgentCore edit proposal review plus accept/reject remains useful.
