<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/08_agent-runtime-v2-scenario-replay-gate-2026-05-10.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/08_agent-runtime-v2-scenario-replay-gate-2026-05-10.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Runtime V2 Scenario Replay Gate

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass turns the mainline P6 replay requirement into a repo-owned regression gate.

Implemented:

- Added fixed scenario replay tests for the current agent runtime:
  - S-01 capability question
  - S-02 project/source-library fact question
  - S-03 source-library collection candidate preview, approval wait, and approved continuation
  - S-04 ingest/source-library scoped execution payload and resume context
  - S-05 workflow execution with inspect, approval wait, edited approval payload, and continuation
  - S-06 missing workflow graph failure returned as a tool result
  - S-07 cancel then continue recovery
  - S-08 follow-up question over the prior failed tool result
  - S-09 artifact search/read replay lives in `test_agent_runtime_artifact_idle_replay_unittest.py`
  - S-10 idle status chat latency/no-`agent_batch` replay lives in `test_agent_runtime_artifact_idle_replay_unittest.py`
- Added readable final-answer fact summaries for:
  - `workflow_graph.list`
  - `workflow_graph.inspect`
  - `ingest.status.read`
- Kept the replay gate in-memory and deterministic; it does not depend on external services or live `agent_batch`.

## Main Files

- `main/backend/app/services/agent_runtime/interactive_agent.py`
- `main/backend/tests/integration/test_agent_runtime_scenario_replay_unittest.py`

## Scenario Coverage

| Scenario | Replay assertion | Status |
|---|---|---|
| S-01 能力问答 | `你能做什么工具？` stays in conversation mode, calls capability catalog/session read, and does not dispatch `agent_batch` | green |
| S-02 项目事实问答 | `当前项目有哪些来源库 item？` uses project/source-library read-only tools and reports source-library count | green |
| S-03 来源库采集 | `用来源库 demo.news 补一轮证据` lists candidates, snapshots scope, waits for approval, and continues after approval | green |
| S-04 ingest 链路 | `ingest demo.ingest time_window=... max_items=5` produces scoped execution payload and resume context | green |
| S-05 workflow 执行 | `运行 workflow graph demo_graph_agent_scenario` inspects graph, requests approval, accepts edited `inputs`, and completes continuation | green |
| S-06 失败恢复 | missing workflow graph inspect returns a failed tool result and the final answer cites the failed graph | green |
| S-07 中断继续 | cancel keeps the session recoverable; continue restores a canceled worker task and waits on the original approval | green |
| S-08 追问上下文 | after S-06, `刚才那个结果里第二项为什么失败？` reads session context and cites the previous `workflow_graph.inspect` failure | green |
| S-09 产物查看 | seeded JSON artifact is found by `agent_artifact.search` and read by `agent_artifact.read` | green |
| S-10 低延迟闲聊 | idle status chat completes below the deterministic 1 second gate without dispatching `agent_batch` | green |

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
./.venv311/bin/python -m py_compile app/services/agent_runtime/interactive_agent.py tests/integration/test_agent_runtime_scenario_replay_unittest.py
```

Result: passed.

## Mainline Satisfaction Update

- P6-03 is now covered by deterministic repo-owned replay gates for S-01 through S-10.
- P6-07 is stronger for two important regressions:
  - capability/fact questions must not dispatch `agent_batch`
  - failed workflow inspect must return as a tool result instead of breaking the turn
- P6-08 now has saved scenario replay reports in the development topic.
- P0/P1 fact-answer quality improves because workflow and ingest read-only tools now contribute readable answer lines, not only raw tool traces.

## Remaining Gap

Still open before full P6 closure:

- Frontend E2E still needs explicit artifact drawer, mobile tab, and per-tool retry/cancel coverage.
- Performance metrics now exist in the run-loop payload, but threshold reporting beyond S-10's deterministic idle gate still needs a broader perf gate.

## Next Mainline Slice

Proceed to the remaining non-scenario gaps:

1. Broaden P3 session memory and context compaction beyond recent tool-result summaries.
2. Finish P4 artifact preview drawer/capability panel/mobile switching.
3. Continue P5 caller migration so `agent_batch` is only a governed compatibility tool/fallback.
