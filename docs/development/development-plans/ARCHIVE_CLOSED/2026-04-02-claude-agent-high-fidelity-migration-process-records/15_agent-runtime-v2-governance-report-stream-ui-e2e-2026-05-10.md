<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/15_agent-runtime-v2-governance-report-stream-ui-e2e-2026-05-10.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/15_agent-runtime-v2-governance-report-stream-ui-e2e-2026-05-10.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Runtime V2 Governance Report Stream UI E2E

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass closes the next set of mainline TODO gaps after dynamic tool pool and session memory.

Implemented:

- Added `ToolExecutionPolicy`, `ToolExecutionHooks`, and abort detection for run-loop tool execution.
- Read-only tools can now execute through a parallel-safe path; non-read-only/high-risk classes are routed to serial/approval-required handling.
- Added hook points: `pre_tool`, `post_tool`, `on_error`, `on_approval`, and `on_cancel`.
- Abort signals now return a recoverable canceled tool result instead of hanging.
- Added governed `report.generate` capability. It requires approval and an output path, then writes a markdown report artifact through the existing report generator.
- Added `/agent-chat/turn/stream` SSE-compatible endpoint.
- Added `runtime_variant` support so the same user/request can explicitly use `agent_runtime_v2` or fall back to `legacy_batch`.
- Frontend workbench now includes near-message continue/retry/cancel controls, a thinking state, empty/error banners, and segmented workbench tabs for tools, approvals, and artifacts.
- Desktop/mobile Playwright smoke verifies tabs, inline controls, state banners, no horizontal overflow, and no page/console errors.

## Main Files

- `main/backend/app/services/agent_runtime/tool_execution.py`
- `main/backend/app/services/agent_runtime/run_loop.py`
- `main/backend/app/services/agent_runtime/capability_registry.py`
- `main/backend/app/services/agent_runtime/interactive_agent.py`
- `main/backend/app/api/agent_chat.py`
- `main/backend/tests/unit/test_agent_run_loop_unittest.py`
- `main/backend/tests/unit/test_interactive_agent_runtime_unittest.py`
- `main/backend/tests/integration/test_agent_chat_api_unittest.py`
- `main/frontend-modern/src/pages/AgentChatPage.tsx`
- `main/frontend-modern/src/pages/agent-chat.css`
- `main/frontend-modern/src/lib/api.ts`
- `main/frontend-modern/src/lib/api/endpoints.ts`
- `main/frontend-modern/src/lib/types.ts`

## Validation

Backend:

```bash
cd main/backend
./.venv311/bin/python -m py_compile app/api/agent_chat.py app/services/agent_runtime/tool_execution.py app/services/agent_runtime/tool_pool.py app/services/agent_runtime/read_only_tools.py app/services/agent_runtime/capability_registry.py app/services/agent_runtime/interactive_agent.py app/services/agent_runtime/run_loop.py app/services/agent_runtime/session_memory.py
./.venv311/bin/python -m pytest -q tests/integration/test_agent_chat_api_unittest.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py tests/unit/test_agent_session_memory_unittest.py tests/integration/test_agent_runtime_scenario_replay_unittest.py tests/integration/test_agent_runtime_artifact_idle_replay_unittest.py tests/unit/test_agent_control_tools_unittest.py
```

Result: `47 passed, 11 warnings`.

Frontend:

```bash
cd main/frontend-modern
npm run build
```

Result: passed.

Headless Playwright smoke against `http://127.0.0.1:5173/#agent-chat.html`:

```json
{
  "desktop": {
    "hasWorkbench": true,
    "hasTabs": true,
    "hasInlineControls": true,
    "inlineControlsNearThread": true,
    "hasStateBanner": true,
    "bodyOverflowX": false,
    "overflowing": [],
    "errors": []
  },
  "mobile": {
    "hasWorkbench": true,
    "hasTabs": true,
    "hasInlineControls": true,
    "inlineControlsNearThread": true,
    "hasStateBanner": true,
    "bodyOverflowX": false,
    "overflowing": [],
    "errors": []
  },
  "tabs": ["tools", "approvals", "artifacts"]
}
```

## Mainline Satisfaction Update

- T-15 is satisfied by approval-gated `report.generate` and markdown artifact writing.
- P2-01, P2-03, and P2-08 are materially satisfied by execution policy, abort handling, and hook coverage.
- P4-02, P4-07, P4-09, and P4-10 are materially satisfied by the frontend workbench update and smoke checks.
- P5-02 is satisfied by the new stream endpoint and existing session SSE descriptor.
- P5-08 is satisfied by `runtime_variant` and `legacy_batch` fallback.
- P6-04 is satisfied by the Playwright workbench smoke plus API stream/legacy tests.

Remaining open items after this pass are P0-04, P0-05, and P5-03. They require making model-native tool choice/final synthesis the default path and moving `agent_batch.nl_command.submit` from default execution path to approval-governed fallback.
