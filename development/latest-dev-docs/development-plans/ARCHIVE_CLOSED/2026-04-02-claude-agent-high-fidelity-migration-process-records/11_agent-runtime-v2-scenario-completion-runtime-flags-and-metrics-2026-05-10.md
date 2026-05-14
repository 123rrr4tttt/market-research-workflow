# Agent Runtime V2 Scenario Completion, Runtime Flags, And Metrics

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass closes the remaining fixed user-scenario replay gap from the source TODO and adds the first production rollout/observability surface.

Implemented:

- S-03 source-library collection replay: source-library execution now lists candidates, snapshots scope and execution payload, requests approval, and continues through the approved high-risk executor.
- S-04 ingest chain replay: ingest/source-library execution payload now carries `item_key`, `time_window`, `max_items`, budget, and `resume_context`.
- S-07 cancel/continue replay: `task.cancel` no longer breaks final-answer emission, and `task.continue` can restore a canceled worker task into a recoverable pending/blocked state.
- S-09 artifact replay: fixed read-only replay covers `agent_artifact.search` and `agent_artifact.read` against an existing session artifact.
- S-10 low-latency idle chat replay: fixed replay asserts idle status chat stays under the in-memory 1 second gate and does not dispatch `agent_batch`.
- P0 final-answer path: model planner `final_answer` is now preserved by `AgentRunLoop` and used by `InteractiveAgentRuntime` when available.
- P5 rollout flags: backend settings and `/agent-chat` responses expose `agent_runtime_v2_enabled`, `agent_stream_enabled`, and `agent_batch_as_tool_enabled`.
- P6 metrics: run loop now returns first-event latency, first-tool-start latency, elapsed seconds, tool count, retry/approval/cancel/error counters.

## Main Files

- `main/backend/app/services/agent_runtime/interactive_agent.py`
- `main/backend/app/services/agent_runtime/run_loop.py`
- `main/backend/app/services/agent_runtime/control_tools.py`
- `main/backend/app/services/agent_runtime/capability_registry.py`
- `main/backend/app/services/agent_runtime/read_only_tools.py`
- `main/backend/app/api/agent_chat.py`
- `main/backend/app/settings/config.py`
- `main/backend/tests/integration/test_agent_runtime_scenario_replay_unittest.py`
- `main/backend/tests/integration/test_agent_runtime_artifact_idle_replay_unittest.py`
- `main/backend/tests/unit/test_agent_run_loop_unittest.py`
- `main/backend/tests/unit/test_interactive_agent_runtime_unittest.py`
- `main/backend/tests/integration/test_agent_chat_api_unittest.py`

## Scenario Coverage

| Scenario | Status | Evidence |
|---|---|---|
| S-01 能力问答 | green | capability question stays in conversation/read-only path and does not submit `agent_batch` |
| S-02 项目事实问答 | green | source-library fact question uses project/source-library read-only tools |
| S-03 来源库采集 | green | candidate preview, scope snapshot, approval wait, approved continuation |
| S-04 ingest 链路 | green | scoped ingest/source-library execution payload with resume context |
| S-05 workflow 执行 | green | graph inspect, approval edit, approved continuation |
| S-06 失败恢复 | green | failed workflow inspect returns as tool result and final answer cites failure |
| S-07 中断继续 | green | cancel preserves recoverable session state; continue restores canceled worker task |
| S-08 追问上下文 | green | follow-up reads recent failed tool result from session context |
| S-09 产物查看 | green | artifact search/read replay locates and summarizes seeded JSON artifact |
| S-10 低延迟闲聊 | green | idle status chat remains read-only and below 1 second in deterministic replay |

## Validation

Commands run:

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/integration/test_agent_runtime_scenario_replay_unittest.py
```

Result: `7 passed`.

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/integration/test_agent_runtime_artifact_idle_replay_unittest.py
```

Result: `2 passed`.

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/integration/test_agent_chat_api_unittest.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py tests/integration/test_agent_runtime_scenario_replay_unittest.py tests/integration/test_agent_runtime_artifact_idle_replay_unittest.py tests/unit/test_agent_control_tools_unittest.py
```

Result: `35 passed, 11 warnings`.

```bash
cd main/backend
./.venv311/bin/python -m py_compile app/api/agent_chat.py app/settings/config.py app/services/agent_runtime/interactive_agent.py app/services/agent_runtime/run_loop.py app/services/agent_runtime/control_tools.py app/services/agent_runtime/capability_registry.py app/services/agent_runtime/read_only_tools.py
```

Result: passed.

## Mainline Satisfaction Update

- All S-01 through S-10 fixed replay scenarios are now green at the backend deterministic gate.
- P0 is materially stronger: model-provided final answers have a runtime path instead of being dropped behind the deterministic template.
- P2 is materially stronger for source-library/ingest approval previews and cancel/continue recovery.
- P5 now has explicit runtime feature flags for rollout and fallback control.
- P6 now has scenario replay coverage plus first-run-loop latency and tool-count metrics.

## Remaining Non-Scenario Gaps

This pass does not claim full closure of every P0-P6 checkbox:

- P1 dynamic project-aware tool assembly and delayed tool search are still partial.
- P2 cooperative abort signal inside long-running external collectors is still partial.
- P3 durable long-session memory and compression are still partial beyond recent tool-result summaries.
- P4 frontend artifact preview drawer, capability panel, and mobile tab switching still need another UI pass.
- P5 full `agent_batch` demotion still needs caller-by-caller migration beyond flags and approval-gated high-risk tools.
