# Claude Code Level Agent M1 Implementation Status

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass implements M1 only: fast conversational/read-only interaction for the current agent runtime while preserving the existing `/agent-chat/turn` signature and the `agent_batch` execution path.

Implemented:

- Added a read-only capability/tool contract for M1 calls and stream descriptors.
- Added read-only adapters for capability catalogue, session context, project summary, source-library list/search/inspect, and session artifact search/read.
- Added goal classification so capability/status/project/source-library fact questions use `conversation` or `read_only` mode instead of dispatching `agent_batch`.
- Kept execution requests, including source-library collection requests such as “继续补充来源库证据”, on the governed `agent_batch` path.
- Added stream-friendly `interactive_agent.tool_call_started` events and returned a session stream descriptor in `/agent-chat/turn`.
- Changed agent source-library listing inside `/agent-chat` to omit execution-plan expansion for faster fact reads.
- Updated the Agent Chat frontend to consume session SSE events, merge streamed events with polling results, show stream status, and surface read-only tool calls in the chat and inspector.
- Increased the Agent Chat thread workspace height so the page behaves more like a working agent console instead of a small preview panel.

## Main Files

- Backend:
  - `main/backend/app/services/agent_runtime/tool_contract.py`
  - `main/backend/app/services/agent_runtime/read_only_tools.py`
  - `main/backend/app/services/agent_runtime/capability_registry.py`
  - `main/backend/app/services/agent_runtime/interactive_agent.py`
  - `main/backend/app/api/agent_chat.py`
- Frontend:
  - `main/frontend-modern/src/lib/api.ts`
  - `main/frontend-modern/src/lib/types.ts`
  - `main/frontend-modern/src/pages/AgentChatPage.tsx`
  - `main/frontend-modern/src/pages/agent-chat.css`
- Tests:
  - `main/backend/tests/unit/test_interactive_agent_runtime_unittest.py`

## Validation

Commands run:

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/unit/test_agent_sessions_service_unittest.py tests/integration/test_agent_sessions_api_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py tests/integration/test_agent_chat_api_unittest.py
```

Result: `28 passed`.

```bash
cd main/frontend-modern
npm run build
```

Result: TypeScript build and Vite production build passed.

## Remaining Gaps

M1 does not yet make the runtime equal to Claude Code. It removes the worst interaction bottleneck for basic fact questions and makes read-only tools visible, but the next gaps remain:

- Replace deterministic keyword classification with a model-native tool loop.
- Add approval-gated write/external tools that can be freely selected by the model while still respecting project policy.
- Add richer cancellation/retry/continue semantics with resumable turn tokens.
- Add session memory and context compaction so long conversations do not degrade.
- Promote `agent_batch` from the default natural-language execution path to one governed tool among many.
- Continue the Agent Chat UI redesign into a full workbench with clearer transcript, tool trace, task tree, and artifact panes.
