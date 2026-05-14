# Agent Runtime V2 Tool Loop And Approval Status

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass moves the M1 read-only fast path into a bounded agent run loop and adds the first governance path for high-risk capabilities. It is still not a full Claude Code equivalent runtime, but the runtime now has a real tool-loop contract rather than only static capability dispatch.

Implemented:

- Added `AgentRunLoop` with explicit iteration, tool-call, elapsed-time, and result-size budgets.
- Added tool-definition contracts for read-only tools so planners can see name, description, input schema, risk level, concurrency class, approval level, timeout, and result budget.
- Added deterministic `HeuristicAgentRunLoopPlanner` for compatibility and `JsonModelAgentRunLoopPlanner` for feature-flagged model-native tool selection.
- Added stream events for `interactive_agent.model_delta`, `interactive_agent.tool_call_requested`, `interactive_agent.tool_call_started`, and `interactive_agent.tool_call_result`.
- Wired `/agent-chat/turn` to accept `enable_model_tool_loop` and `require_high_risk_approval` without changing the existing response envelope.
- Kept legacy behavior as default: without `enable_model_tool_loop`, read-only questions still use the deterministic planner and execution requests can still fall through to `agent_batch`.
- Added an approval-gated path for selected high-risk capabilities including `workflow_graph.run` and `ingest.source_library.run`.
- When high-risk approval is required, the runtime creates a pending approval, records `approval.waiting` / `approval.requested`, blocks the execute/final tasks, and returns `approval_requests` to the caller instead of dispatching `agent_batch`.
- Updated the Agent Chat frontend type/event whitelist so model-delta, tool-request, and tool-result events can appear in the conversation stream.
- Added `/agent-chat/approvals/{approval_id}/continue` so an approved high-risk capability can resume in the same session instead of staying as a permanent blocker.
- Approval resume restores `turn_id`, `session_id`, `task_id`, `capability_id`, command, and project scope from the approval binding, emits tool start/result events, writes capability artifacts, and emits a continuation final answer.
- The default resume executor now attempts approved `workflow_graph.run` through the existing workflow graph runtime and approved `ingest.source_library.run` through the source-library compat executor when required inputs are explicit.
- The Agent Chat frontend now defaults interactive turns to high-risk approval gating, shows approval cards in the inspector, and supports a `批准并继续` action for pending approvals.

## Main Files

- Backend:
  - `main/backend/app/services/agent_runtime/tool_contract.py`
  - `main/backend/app/services/agent_runtime/read_only_tools.py`
  - `main/backend/app/services/agent_runtime/run_loop.py`
  - `main/backend/app/services/agent_runtime/interactive_agent.py`
  - `main/backend/app/api/agent_chat.py`
- Frontend:
  - `main/frontend-modern/src/lib/api.ts`
  - `main/frontend-modern/src/lib/types.ts`
  - `main/frontend-modern/src/pages/AgentChatPage.tsx`
- Tests:
  - `main/backend/tests/unit/test_agent_run_loop_unittest.py`
  - `main/backend/tests/unit/test_interactive_agent_runtime_unittest.py`

## Validation

Commands run:

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/unit/test_agent_sessions_service_unittest.py tests/integration/test_agent_sessions_api_unittest.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py tests/integration/test_agent_chat_api_unittest.py
```

Result: `32 passed`.

After approval resume implementation:

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/unit/test_agent_sessions_service_unittest.py tests/integration/test_agent_sessions_api_unittest.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py tests/integration/test_agent_chat_api_unittest.py
```

Result: `34 passed`.

```bash
cd main/backend
./.venv311/bin/python -m py_compile app/services/agent_runtime/tool_contract.py app/services/agent_runtime/read_only_tools.py app/services/agent_runtime/run_loop.py app/services/agent_runtime/interactive_agent.py app/api/agent_chat.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py
```

Result: passed.

```bash
cd main/frontend-modern
npm run build
```

Result: TypeScript build and Vite production build passed.

HTTP smoke against local backend:

- `POST /api/v1/agent-chat/turn` with `当前项目有哪些来源库 item？` returned `session.status=completed`, `agent_mode=read_only`, and read-only tool calls for `agent_session.context.read`, `project.summary.read`, and `source_library.item.list`.
- `POST /api/v1/agent-chat/turn` with `运行 workflow graph demo_graph` plus `require_high_risk_approval=true` returned `session.status=blocked`, one pending approval, and `workflow_graph.run` with `status=needs_approval`.
- Compiled a minimal `demo_graph_agent_smoke` workflow graph, then `POST /api/v1/agent-chat/approvals/{approval_id}/continue` returned `session.status=completed`, `approval.status=approved`, `capability_call.status=completed`, and a workflow `run_id`.

Frontend smoke against local Vite:

- `http://127.0.0.1:5173/#agent-chat.html` rendered `.agent-chat-page`.
- No page errors or console errors were observed.
- No horizontal overflow was observed at `1440x960`.
- A Playwright UI smoke submitted `运行 workflow graph demo_graph_agent_smoke`, waited for the approval card, clicked `批准并继续`, and confirmed `审批已处理` appeared with no console/page errors and no horizontal overflow.

## Remaining Gaps

The runtime is closer to Claude Code's architecture but still incomplete:

- Model-native tool loop is feature-flagged and JSON-planner based; final natural-language synthesis still mostly uses the existing template.
- Write/external tools now have approval request and approved resume for the first high-risk slice, but parameter editing, rejection UX, and policy-level approval scopes are still missing.
- `source_library.run`, `ingest.run`, and `workflow_graph.run` still need dry-run impact summaries, richer progress events, artifact previews, cancel, retry, and user-editable continue semantics.
- The frontend now has a minimal approval card, but it still lacks reject/edit-before-approve controls, a full tool timeline, artifact drawer, and per-tool retry affordances.
- `agent_batch` is still the default compatibility path for many execution requests; it has not yet been fully demoted to one governed tool among many.
- Session memory, context compaction, and project-aware dynamic tool search remain pending.

## Next Stage

Proceed to M3/M4 work:

- Add user-editable approval parameters and rejection paths.
- Add concrete governed tool adapters for workflow inspection and richer source-library execution.
- Redesign the Agent Chat workbench around conversation, tool timeline, approval, and artifacts.
- Add fixed scenario replay for ability Q&A, project fact Q&A, approval wait, and continue-after-approval.
