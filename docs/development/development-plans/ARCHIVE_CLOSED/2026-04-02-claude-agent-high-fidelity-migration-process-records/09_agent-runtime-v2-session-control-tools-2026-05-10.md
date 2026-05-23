<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/09_agent-runtime-v2-session-control-tools-2026-05-10.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/09_agent-runtime-v2-session-control-tools-2026-05-10.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Runtime V2 Session Control Tools

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass promotes cancel/retry/continue from frontend-only session actions into runtime tool contracts that the interactive agent can select from natural language.

Implemented:

- Added `AgentControlToolRuntime` for state-changing session control tools.
- Added tool definitions and executors for:
  - `task.cancel`
  - `task.retry`
  - `task.continue`
- Added capability-registry entries for the three control tools with:
  - `concurrency_class=write_shared`
  - `approval_level=explicit_user_request`
  - `risks=["session_state_mutation"]`
- Added control-goal classification so:
  - `取消当前会话` selects `task.cancel`
  - `重试失败任务` selects `task.retry`
  - `继续上一步` selects `task.continue`
- Integrated control tools into `InteractiveAgentRuntime.run_turn`.
- Control tools now emit `interactive_agent.tool_call_started` and `interactive_agent.tool_call_result` events with `protocol=session_control`.
- `task.retry` can infer the latest failed/canceled/expired task when no explicit `task_id` is supplied.
- `task.cancel` preserves final returned session status as `canceled`.

## Main Files

- `main/backend/app/services/agent_runtime/control_tools.py`
- `main/backend/app/services/agent_runtime/capability_registry.py`
- `main/backend/app/services/agent_runtime/interactive_agent.py`
- `main/backend/tests/unit/test_agent_control_tools_unittest.py`

## Validation

Commands run:

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/unit/test_agent_control_tools_unittest.py
```

Result: `5 passed`.

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/unit/test_agent_sessions_service_unittest.py tests/integration/test_agent_sessions_api_unittest.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py tests/integration/test_agent_chat_api_unittest.py tests/integration/test_agent_runtime_scenario_replay_unittest.py tests/unit/test_agent_control_tools_unittest.py
```

Result: `46 passed, 11 warnings`.

```bash
cd main/backend
./.venv311/bin/python -m py_compile app/services/agent_runtime/control_tools.py app/services/agent_runtime/capability_registry.py app/services/agent_runtime/interactive_agent.py tests/unit/test_agent_control_tools_unittest.py tests/integration/test_agent_runtime_scenario_replay_unittest.py
```

Result: passed.

## Mainline Satisfaction Update

- T-16 `task.cancel` is now represented as a runtime tool and executable from natural language.
- T-17 `task.retry` is now represented as a runtime tool and can infer a retryable task.
- T-18 `task.continue` is now represented as a runtime tool and calls the coordinator pass.
- P2-02 is stronger for control tools because start/result events are emitted into the session ledger.
- P2-03 is still partial: `task.cancel` cancels the ledger, but long-running tool abort signals are not yet cooperative across every executor.
- S-07 is partially enabled: users can say continue/retry/cancel, but fixed cancel/continue browser replay is still pending.

## Remaining Gap

Still open before full control parity:

- Long-running tools need cooperative abort signals, not only session-level cancellation.
- `task.continue` should route approval-continuation resumes when the waiting state is an approval, not only coordinator pass.
- Retry should eventually consume structured resume tokens for failed tools.
- Frontend should surface control-tool calls as message-local actions, not only global session buttons.
- Fixed replay must cover cancel/continue/retry in one end-to-end session.

## Next Mainline Slice

Proceed to P3/P6:

1. Add session memory/context-summary fields that compact prior tool results for follow-up questions.
2. Add fixed replay for S-08 follow-up over prior failed tool result.
3. Add browser replay for S-07 cancel/continue once cooperative abort semantics are in place.
