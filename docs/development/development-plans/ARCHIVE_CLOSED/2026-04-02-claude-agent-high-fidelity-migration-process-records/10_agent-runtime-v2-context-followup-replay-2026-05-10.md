<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/10_agent-runtime-v2-context-followup-replay-2026-05-10.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/10_agent-runtime-v2-context-followup-replay-2026-05-10.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Runtime V2 Context Follow-up Replay

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass advances P3 context compression and S-08 follow-up behavior without introducing a separate memory subsystem.

Implemented:

- `agent_session.context.read` now returns `recent_tool_results` summarized from `interactive_agent.tool_call_result` events.
- Recent tool result summaries include:
  - event id and sequence
  - capability/tool name
  - status
  - summary
  - error payload
- Final answer synthesis now turns failed recent tool results into readable fact lines.
- Added follow-up replay to the scenario gate:
  1. trigger a missing workflow graph inspect failure
  2. ask `刚才那个结果里第二项为什么失败？` in the same session
  3. assert the answer cites the prior `workflow_graph.inspect` failure and graph id

## Main Files

- `main/backend/app/services/agent_runtime/read_only_tools.py`
- `main/backend/app/services/agent_runtime/capability_registry.py`
- `main/backend/app/services/agent_runtime/interactive_agent.py`
- `main/backend/tests/integration/test_agent_runtime_scenario_replay_unittest.py`

## Validation

Commands run:

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/integration/test_agent_runtime_scenario_replay_unittest.py
```

Result: `4 passed`; this file now covers S-01, S-02, S-05, S-06, and S-08.

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/unit/test_agent_sessions_service_unittest.py tests/integration/test_agent_sessions_api_unittest.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py tests/integration/test_agent_chat_api_unittest.py tests/integration/test_agent_runtime_scenario_replay_unittest.py tests/unit/test_agent_control_tools_unittest.py
```

Result: `46 passed, 11 warnings`.

```bash
cd main/backend
./.venv311/bin/python -m py_compile app/services/agent_runtime/read_only_tools.py app/services/agent_runtime/capability_registry.py app/services/agent_runtime/interactive_agent.py tests/integration/test_agent_runtime_scenario_replay_unittest.py
```

Result: passed.

## Mainline Satisfaction Update

- P3-03 is partially covered: tool-use summaries are now exposed through session context for recent tool results.
- P3-04 is stronger: follow-up turns can prioritize current user instruction plus prior failed tool result without replaying external tools.
- S-08 is now green in the deterministic replay gate.
- P6-03/P6-08 now include a saved follow-up-context replay record.

## Remaining Gap

Still open before full P3 closure:

- No durable long-session compression beyond `memory.md` and `scratchpad.md`.
- No token-budgeted context builder that ranks user instruction, approvals, task state, project summary, tool summaries, and historical summary.
- No user-correction invalidation mechanism for stale memory.
- Follow-up answers still use deterministic synthesis, not model-native answer generation over compacted context.

## Next Mainline Slice

Proceed to deeper P3:

1. Build a project/session context builder with explicit budget priorities.
2. Add memory update triggers for completed tasks and tool-count thresholds with structured metadata.
3. Add correction handling so a user can invalidate or update stale session memory.
