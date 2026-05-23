<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/13_agent-runtime-v2-tool-context-pool-search-2026-05-10.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/13_agent-runtime-v2-tool-context-pool-search-2026-05-10.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Runtime V2 Tool Context Pool And Search

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass closes the P1 tool-protocol gaps that remained after the capability panel and scenario replay work.

Implemented:

- Added a first-class `ToolExecutionContext` with session, task, turn, project, user, abort, budget, permissions, feature flags, event writer, artifact writer, and tool-call options.
- Added `ToolCallOptions` for `dry_run`, `explain_only`, `approval_required`, and `resume_token`.
- Added `AgentToolPoolAssembler` to build a project-aware runtime tool pool from capability metadata and feature flags.
- Split the runtime tool pool into `core`, `deferred`, and `disabled` groups, with approval-required counts.
- Added read-only tools:
  - `agent_runtime.tool_pool.list`
  - `agent_runtime.tool.search`
- Updated capability selection so tool/capability questions can inspect the dynamic tool pool and search deferred tools without entering `agent_batch`.
- Updated `/agent-chat/capabilities` to return `tool_pool` alongside legacy `items` and `feature_flags`.
- Updated the frontend capability panel to prefer dynamic `tool_pool.groups` over the legacy static list.

## Main Files

- `main/backend/app/services/agent_runtime/tool_contract.py`
- `main/backend/app/services/agent_runtime/tool_pool.py`
- `main/backend/app/services/agent_runtime/read_only_tools.py`
- `main/backend/app/services/agent_runtime/capability_registry.py`
- `main/backend/app/services/agent_runtime/run_loop.py`
- `main/backend/app/services/agent_runtime/interactive_agent.py`
- `main/backend/app/api/agent_chat.py`
- `main/frontend-modern/src/pages/AgentChatPage.tsx`
- `main/frontend-modern/src/lib/api.ts`
- `main/frontend-modern/src/lib/types.ts`

## Validation

Backend:

```bash
cd main/backend
./.venv311/bin/python -m py_compile app/api/agent_chat.py app/services/agent_runtime/tool_pool.py app/services/agent_runtime/read_only_tools.py app/services/agent_runtime/capability_registry.py app/services/agent_runtime/interactive_agent.py app/services/agent_runtime/run_loop.py
./.venv311/bin/python -m pytest -q tests/integration/test_agent_chat_api_unittest.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py tests/integration/test_agent_runtime_scenario_replay_unittest.py tests/integration/test_agent_runtime_artifact_idle_replay_unittest.py
```

Result: `32 passed, 11 warnings`.

Frontend:

```bash
cd main/frontend-modern
npm run build
```

Result: passed.

## Mainline Satisfaction Update

- P1-02 is materially satisfied by `ToolExecutionContext` and serialization tests.
- P1-03 is materially satisfied by `AgentToolPoolAssembler` plus `/agent-chat/capabilities` returning dynamic `tool_pool`.
- P1-04 is materially satisfied by `agent_runtime.tool.search` and deferred-tool grouping.
- P1-07 is materially satisfied by `ToolCallOptions` and approval resume binding payloads.

Remaining major gaps are now concentrated in P0-04/P0-05, P2 concurrent execution and cooperative abort hooks, P3 memory compaction, P4 streaming-message/mobile-control polish, P5 stream-primary migration and batch fallback controls, and P6 frontend E2E.
