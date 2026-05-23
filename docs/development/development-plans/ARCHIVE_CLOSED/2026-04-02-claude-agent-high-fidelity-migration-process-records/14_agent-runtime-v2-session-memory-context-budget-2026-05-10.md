<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/14_agent-runtime-v2-session-memory-context-budget-2026-05-10.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/14_agent-runtime-v2-session-memory-context-budget-2026-05-10.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Runtime V2 Session Memory / Context Budget 首版记录

日期：2026-05-10

范围：仅补齐后端 Agent Runtime V2 的 P3 session memory、project context builder、tool-use summary、context budget 与 memory update trigger 首版实现；不改前端，不更新 `02` 主表与顶层索引。

## 实现内容

- P3-01 session memory：新增 `app/services/agent_runtime/session_memory.py`，从 `AgentSessionService.get_session_bundle(...)` 的 `session/messages/tasks/events/artifacts/approvals` 生成 `stable_summary`。
- P3-02 project context builder：从 session project、artifact index、最近 capability/tool 结果中提取 `project_context`，覆盖 source_library、ingest status、workflow graph、recent runs 的压缩视图。
- P3-03 tool-use summary：从 `interactive_agent.tool_call_result`、`interactive_agent.capability_executed`、`interactive_agent.approval_continued` 事件生成 `tool_use_summary`，包含工具次数、状态次数、协议次数、最近结果与失败摘要。
- P3-04 context budget：新增 `budgeted_context`，按固定优先级裁剪：
  1. latest user instruction
  2. approval state
  3. current task
  4. tool result summary
  5. project summary
  6. history summary
- P3-05 memory update trigger：新增 `should_update_memory(...)`，支持 token、事件、工具次数阈值，并补充 task completion 与用户显式 summary/memory 请求触发。

## 接入方式

- `interactive_agent.py` 仅做窄接入：在最终回答 metadata 与 turn 返回体中挂载 `context_summary`。
- 不重写 run loop，不改变工具选择、审批、任务流转或前端 payload 主结构。
- 旧 `agent_runtime/memory.py` 保持不动，继续服务现有 `memory.md` / `scratchpad.md` artifact 刷新。

## 验证

已执行：

```bash
cd main/backend
python3.11 -m pytest -q tests/unit/test_agent_session_memory_unittest.py
python3.11 -m pytest -q tests/unit/test_interactive_agent_runtime_unittest.py
python3.11 -m py_compile app/services/agent_runtime/session_memory.py app/services/agent_runtime/interactive_agent.py tests/unit/test_agent_session_memory_unittest.py
```

结果：

- `tests/unit/test_agent_session_memory_unittest.py`：5 passed
- `tests/unit/test_interactive_agent_runtime_unittest.py`：12 passed
- `py_compile`：passed

## 风险与后续

- 当前预算使用字符数近似，不接具体 tokenizer；后续接真实模型上下文窗口时可替换估算器。
- `project_context` 依赖当前 session 内已有工具结果，不主动读取外部项目状态；后续可由 read-only tool 主动刷新后再压缩。
- P3-06 已由主线补齐首版：`build_memory_correction_marker(...)` 能识别用户指出旧记忆/旧摘要错误的消息，并在 `should_update_memory(...)` 返回 `user_corrected_memory`，同时把 `stable_summary.memory_correction.handling` 标记为 `mark_previous_summary_stale_and_rebuild`。
