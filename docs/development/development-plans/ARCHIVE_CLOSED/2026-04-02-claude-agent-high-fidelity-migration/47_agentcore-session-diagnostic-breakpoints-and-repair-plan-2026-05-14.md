<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration/47_agentcore-session-diagnostic-breakpoints-and-repair-plan-2026-05-14.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration/47_agentcore-session-diagnostic-breakpoints-and-repair-plan-2026-05-14.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# AgentCore Session 诊断断点与修复计划

Date: 2026-05-14
Status: convergence repair landed + closure audit green
Mainline: Claude Code level AgentCore reconstruction
Scope: session diagnostics, AgentCore final-answer substance, keyword follow-up search, E2E/fake session isolation, writing workbench intent/tool stability.

2026-05-22 archive split: this D47 diagnostic is retained here as closed diagnostic evidence. It is no longer an active `CURRENT_DEV` entry; any reopened AgentCore diagnostic should start as a new D48-or-later topic under `CURRENT_DEV`.

## 背景

`45` 和 `46` 已经把 AgentCore 的高保真迁移、manifest-first context、demand-read synthesis 收口到可回归状态。但最新实测暴露的风险不再只是“工具是否能被调用”，而是 session、stream、工具回接、项目上下文和长任务状态之间的边界是否足够硬。

本文件记录下一轮诊断断点和修复计划，目标是把以下问题从“现象修补”推进为可复现、可观测、可回归的工程项：

- 流式输出边界不清导致前端等待态、最终态或后台 session 状态混在一起；
- fake/e2e session 污染真实 session 或复用错误状态；
- 关键词检索命中后没有进入深读，最终回答停留在标题/摘要层；
- 长任务缺少形式化完成条件，`thinking`、`continue`、`done` 与 stage 状态无法互证；
- 写作工具重复占位，导致 workbench 中出现多份空段落或重复待应用块；
- 写作工作台“新建/写入/贴进去”意图被当成普通聊天输出或只读项目检索，未触发 `writing.document.create` / `writing.document.insert_paragraph`；
- source-library async 回接完成后没有稳定写回 session/tool result；
- `project_key` fallback 继续把真实项目流量导向 `default` / `project_default`。

## 总原则

- Session 是主边界：每个 run、stream placeholder、tool result、long-task stage、writing writeback 都必须绑定到明确 `session_id`、`run_id`、`message_id` 和 `project_key`。
- Tool observation 不是 UI 临时态：后端事件流和 session history 必须能独立重放同一条工具结果，前端只负责展示，不负责补事实。
- 自动 fallback 只能显式、可标记、可审计：任何从 `demo_proj` 退到 `default`、从真实 provider 退到 fake provider、从深读退到摘要的行为都必须留下诊断字段。
- 完成态必须可机器判定：长任务不能只靠自然语言说“完成”，必须有 stage ledger、artifact/writeback/verification gate。

## 诊断断点矩阵

| ID | 断点 | 现象 | 需要采集的证据 | 最小修复方向 |
| --- | --- | --- | --- | --- |
| D47-B01 | Stream boundary | 页面切换、session 切换或后台 run 结束后，当前页仍显示 `thinking` 或吞掉 final answer。 | SSE 原始事件、`session_id/run_id/message_id`、前端 active session、stream placeholder id。 | 后端事件带完整 run identity；前端只更新匹配 session 的 placeholder；final/done/error 必须关闭对应 run。 |
| D47-B02 | Fake/e2e session pollution | E2E/fake provider 生成的 session、project 或 message 被真实 workbench 读取。 | provider kind、test marker、session namespace、storage key、created_by。 | fake/e2e session 使用独立 namespace 与 TTL；真实 UI 默认过滤测试 marker；测试显式清理。 |
| D47-B03 | Keyword hit without deep-read | 关键词检索返回命中项，但最终回答只复述标题、计数或短摘要。 | search manifest、read handles、是否调用 `*.read`、final answer evidence ids。 | 命中高相关材料后强制至少一次 demand-read 或显式说明无法深读；final answer 绑定 evidence ids。 |
| D47-B04 | Long-task formal completion | 长任务说已完成但 stage 仍 open，或 stage done 但没有 artifact/writeback。 | stage ledger、tool calls、artifact ids、writeback ids、verification events。 | 引入 `planned -> running -> blocked/done/failed` stage state；完成条件必须同时满足 stage、artifact/writeback、verification。 |
| D47-B05 | Writing duplicate placeholders | 写作工具连续调用时生成多个空白占位、重复 `Agent 段落` 或重复待应用块。 | placeholder key、document id、selection anchor、tool call id、idempotency key。 | 写作工具以 `(session_id, tool_call_id, document_id, anchor)` 幂等；重复调用更新同一 pending block。 |
| D47-B06 | Source-library async callback | URL-pool/source-library 后台任务完成，但 AgentChat session 没有收到完成事件或最终回答不能继续。 | task id、callback target session/run、event store、tool result append 状态。 | async callback 写入 session event ledger；前端从 session replay 看到完成事件；continue 能读取回接结果。 |
| D47-B07 | `project_key` fallback | 当前项目是 `demo_proj`，但请求或工具读取 `default` / `project_default`。 | frontend active project、API payload、backend resolved project、fallback reason。 | 禁止静默 fallback；缺失 project_key 时返回可诊断错误或要求前端补齐；仅 demo/dev seed 流程允许带 reason 的 fallback。 |
| D47-B08 | Writing create intent not executed | 用户明确要求“写入写作工作台 / 新建稿件并把内容贴进去”，Agent 仍只输出 Markdown，甚至回复“不能直接新建或写入”。 | compare 真实 session、turn tools、visible tool window、`writing.document.create` 是否可见、final answer。 | 写作新建意图必须优先进入 `writing.document.create`；若工具不可见必须返回缺口诊断，不能伪装成能力限制。 |
| D47-B09 | Writing intent over-routed to project search | “写作工作台稿件/写入文档”被 guardrail 解释成项目资料问题，连续调用 `project.context.bundle` / `project.graph.search` / `project.structured_data.search`，消耗轮次后仍不写入。 | guardrail reason、tool sequence、用户原话、最终 stop_reason。 | 意图路由按 action-first：写作 mutation > 写作 read/list > 项目材料检索；只有正文需要资料时才补项目读工具。 |
| D47-B10 | Empty workbench treated as blocker | `writing.document.list` 返回 0 篇文档后，Agent 得出“没有现成文档可直接写入”，没有把空工作台视为“应创建新文档”。 | `writing.document.list` result、是否调用 create、是否产生 document_id/artifact/writeback。 | 空文档列表 + 新建/写入/稿件意图 => `writing.document.create`；已有文档 + 指定位置/划词/修改意图 => read + insert/update。 |

## 修复任务拆解

| Task | 目标 | 主要检查点 | 验收 |
| --- | --- | --- | --- |
| D47-T01 | 统一 AgentCore run identity。 | 所有 SSE event、session history、tool observation、writing writeback 都带 `session_id/run_id/message_id/project_key`。 | 切页、切 session、刷新后不会串改其他 session 的 running/final 状态。 |
| D47-T02 | 隔离 fake/e2e session。 | provider/test marker、namespace、TTL、清理脚本、真实 UI 过滤策略。 | E2E 后真实 workbench session 列表不出现 fake/e2e 数据；回放测试仍可读取自己的夹具。 |
| D47-T03 | 关键词检索后深读门禁。 | search -> manifest -> read handle -> demand-read -> final synthesis。 | 命中项目材料时 final answer 至少引用一个已深读 record/section；无法深读时有明确原因。 |
| D47-T04 | 长任务 completion ledger。 | stage state、artifact/writeback linkage、verification status、resume bundle。 | `done` 只能在 ledger 满足完成条件时出现；刷新/continue 可解释当前 stage。 |
| D47-T05 | 写作工具幂等占位。 | pending block key、selection anchor、tool call id、duplicate suppression。 | 相同写作请求重试不会生成重复空占位；不同 selection 能并列保留。 |
| D47-T06 | source-library async 回接到 session。 | URL-pool/source callback target、event append、continue read path。 | 后台任务完成后 session replay 包含结果；用户继续提问能使用该结果。 |
| D47-T07 | `project_key` fallback 收紧。 | active project propagation、backend resolve trace、fallback reason。 | 真实请求缺 project_key 不再静默读 `project_default`；诊断日志能指出丢失位置。 |
| D47-T08 | 写作新建工具链强制可用。 | tool window、provider prompt、tool registry、`writing.document.create` schema、create preview/apply 语义。 | “新建稿件并把内容贴进去”在空 workbench 下产生新文档或明确 pending writeback，不再只返回正文。 |
| D47-T09 | 写作意图路由前置。 | guardrail 分类、follow-up context、action verbs、current workbench context、model-owned tool selection。 | “输出新的写作工作台稿件 / 写入写作工作台”不会先把整句当检索 query；项目检索只服务内容证据。 |
| D47-T10 | compare 真实会话回归夹具。 | session `as-2aafc5094a6d42a3` 的消息链、工具序列、final answer、project_key `demo_proj_compare_0303_121137`。 | 固定回放：数据库查找 -> 写作展开 -> 新建稿件；最终至少一次 `writing.document.create`，并保留引用框。 |

## 回归场景

1. Stream/session isolation:
   - 在 session A 发起长任务；
   - 切到 session B 并发起普通问答；
   - 等 A 完成；
   - 验证 B 不显示 A 的 streaming placeholder，A replay 能看到 final answer。

2. Fake/e2e isolation:
   - 运行 AgentChat E2E fake provider 场景；
   - 打开真实 workbench session 列表；
   - 验证 fake/e2e session 不进入真实列表，或只在测试命名空间可见。

3. Keyword deep-read:
   - 对真实项目问“帮我根据关键词总结机器人资料”；
   - 验证先返回 manifest，再调用 item/section read；
   - final answer 包含具体证据，而不是只列 dataset/count。

4. Long-task completion:
   - 发起需要多阶段 source-library / writing 的任务；
   - 中途刷新并 continue；
   - 验证 stage ledger、artifact/writeback 和 final status 一致。

5. Writing placeholder idempotency:
   - 对同一 selection 连续点击两次写作工具；
   - 验证只有一个 pending block，被第二次结果更新；
   - 对不同 selection 验证 pending block 分开。

6. Source-library async callback:
   - Agent 发起 source candidate / URL-pool 后台任务；
   - 等待 worker 完成；
   - 验证 session replay 有 callback event 和 tool result，continue 能接上。

7. Project key fallback:
   - 在 `demo_proj` 下发起项目数据查询；
   - 抓 API payload 和 backend resolve trace；
   - 验证所有工具读取同一个 `project_key`，没有静默 fallback 到 `default`。

8. Writing workbench create intent:
   - 使用真实 compare 项目 `demo_proj_compare_0303_121137`；
   - 连续发送：“从数据库里找” -> “详细展开并写一篇文档” -> “写一篇文档就是写入写作工作台” -> “新建稿件并把内容贴进去”；
   - 验证 Agent 不把写作动作降级为普通 Markdown 输出；
   - 验证空写作工作台触发 `writing.document.create`，已有文档触发 `writing.document.read` + `writing.document.insert_paragraph`；
   - 验证最终回答包含 document id / pending writeback / 引用框证据，而不是“你可以复制到工作台”。

## 文档与索引影响

本文件是 `45` / `46` 之后的下一轮诊断计划，不推翻已完成结论；它把剩余风险限定为 session 边界、异步回接、项目上下文传播和长任务完成态。代码修复完成后，需要在本目录追加 closure 文档，并把本文件从 `diagnostic plan` 更新为 `superseded by closure evidence` 或迁入 `ARCHIVE_CLOSED`。

## 当前验证状态

- 已建档并挂入 `development/latest-dev-docs` 索引。
- 已落第一轮代码修复：
  - E2E scripted provider 新建 session 标记为 `source=e2e-scripted`，避免继续以 `source=user` 污染真实会话列表。
  - JSON provider guardrail 对“关键词检索/试试看/下一步/继续”这类上下文跟进语，会从最近 transcript 提取项目查询语境，并优先调用 `project.context.bundle` / `project.structured_data.search` 等项目读工具。
  - AgentCore 在工具调用后若模型最终回答只是“已完成/已读取/已提交/已写入”这类形式化短句，会用实际 tool result 生成可读摘要，并标记 `fallback_reason=insubstantial_model_final_answer_after_tools`。
  - source-library、long-task、investigation trace、writing writeback 等工具结果进入 fallback 摘要，不再只输出完成状态。
- 已补回归：
  - `tests/unit/test_agent_core_unittest.py` 覆盖关键词跟进检索和工具后非实质回答替换。
  - `tests/integration/test_agent_chat_api_unittest.py` 验收从形式化完成语改为工具结果摘要。
- 已落 compare 真实会话写作修复：
  - `tool_window.py` 将 `新建稿件`、`稿件`、`写入`、`贴进去` 纳入 writing-workbench profile，避免“新建稿件并把内容贴进去”这种短 follow-up 看不到写作工具。
  - `json_provider.py` 在模型试图用 final answer 回避“新建/写入写作工作台”时，强制转为 `writing.document.create`，并从当前或上一轮 Markdown 稿件提取 `title/body_md/source_refs`。
  - `json_provider.py` 在模型主动返回 project search tool_calls 但当前是 workbench create/write 意图时，action-first 覆盖为 `writing.document.create`；create 成功后立即封口为自然语言 final answer，避免继续跑 project search。
  - 写作 prompt/tool rules 明确：空 `writing.document.list` 是 create 触发条件，不是“无法写入”的理由。
  - AgentChat 新建 session 的 `default/public/empty project_key` 已按 D47-B07 改为 400 诊断错误，旧的 active project 静默 fallback 测试已更新。
- 验证通过：
  - `cd main/backend && PYTHONPATH=. .venv311/bin/python -m py_compile app/services/agent_core/json_provider.py app/services/agent_core/tool_window.py app/services/agent_core/core.py app/services/agent_core/project_tools.py app/api/agent_chat.py` -> passed。
  - `cd main/backend && PYTHONPATH=. .venv311/bin/pytest tests/unit/test_agent_core_unittest.py tests/integration/test_agent_chat_api_unittest.py -q` -> 98 passed。
  - `cd main/frontend-modern && npm run test:e2e -- tests/e2e/agent-chat.spec.ts --reporter=line` -> 10 passed。
  - `cd main/frontend-modern && npm run lint -- src/pages/AgentChatPage.tsx src/lib/api.ts` -> passed after Playwright run completed。
  - `git diff --check` scoped to本轮文件 -> passed。

## 最新 compare 真实会话诊断

Source session:

- `session_id`: `as-2aafc5094a6d42a3`
- `project_key`: `demo_proj_compare_0303_121137`
- `source`: `user`
- `goal`: `你帮我找一点关于机器人有意义的信息`
- `updated_at`: `2026-05-13 21:43:43.894150-07:00`
- session counters: 14 messages, 1733 events, 2 artifacts.

Observed conversation chain:

| Turn | User intent | Actual tools | Final behavior | Breakpoint |
| --- | --- | --- | --- | --- |
| `turn-0036e97677dd476c` | `从数据库里找` | `project.structured_data.search(query="机器人")` | 返回记录摘要，但没有 deep-read 具体 item。 | D47-B03 |
| `turn-f97ddee9b39e472e` | `详细的展开...写一篇文档...加入引用框` | `project.summary.read` only | 生成正文，但不是写作工作台文档，也未深读引用记录。 | D47-B03 / D47-B08 |
| `turn-9c0efcdce6a84531` | `写一篇文档就是写入写作工作台` | `agent_session.resume_bundle`、`project.context.bundle`、`project.structured_graph.query`、`project.graph.search`、`project.structured_data.search`、`writing.document.list` | 把写作动作误判为项目检索；`writing.document.list` 返回 0 后回复“没有现成文档可直接写入”。 | D47-B09 / D47-B10 |
| `turn-8e4dc8aef7b14072` | `输出完整稿件` | none | 只输出 Markdown 正文。 | D47-B08 |
| `turn-53776b15d4bf4c52` | `你直接输出新的写作工作台稿件` | 再次执行 project context/graph/structured search + `writing.document.list` | 仍只输出 Markdown 正文，没有 create。 | D47-B08 / D47-B09 |
| `turn-27647b09afb249b0` | `新建稿件并把内容贴进去` | none | 明确回复“不能直接新建或写入工作台内容”，但当前 registry 已存在 `writing.document.create`。 | D47-B08 / D47-B10 |

Concrete diagnosis:

- `writing.document.create` 已注册在 `project_tools.py`，并进入 `tool_window.py` 的写作 profile，但模型/guardrail 在真实会话中没有调用它。
- 当前 guardrail 对“写作工作台稿件”这类语句过度套用“项目上下文只读检索”，把用户动作动词当成搜索 query，导致工具序列从写作 mutation 偏到 project search。
- 空 workbench 不应被解释为无法写入；它是创建文档的触发条件。
- “不能直接新建或写入”属于能力暴露错误：如果工具可见，这是 tool selection failure；如果工具不可见，应暴露为 tool window/config failure。

Repair state:

- D47-B08: implemented guardrail fallback to `writing.document.create` when a workbench-create/write intent is about to be answered as plain final text.
- D47-B09: implemented action-first protection for writing create even when the model itself returns project search tool_calls; API replay test verifies only `writing.document.create` executes.
- D47-B10: implemented empty-workbench create semantics in prompt/rules and fallback; API replay verifies create result and final answer include document id.

## 封口审计矩阵

| ID | Closure evidence | Status |
| --- | --- | --- |
| D47-B01 / T01 | `test_agent_core_stream_emits_live_core_events`、`test_agent_core_stream_preserves_tool_metadata_for_project_answers`、frontend `agent-chat.spec.ts` stream cases verify SSE open/start/delta/final/tool events and UI stream consumption. | Closed |
| D47-B02 / T02 | `_prepare_agent_core_session` writes `source=e2e-scripted` under explicit E2E flag; `test_agent_core_e2e_scripted_provider_uses_isolated_session_source` verifies session source isolation. | Closed |
| D47-B03 / T03 | `test_json_provider_guardrail_demands_read_from_manifest_before_final_answer` and `test_agent_core_robot_material_summary_can_demand_read_local_record` verify search manifest -> concrete read -> synthesis path. | Closed |
| D47-B04 / T04 | `test_long_task_stage_state_survives_resume_bundle_and_replay` verifies stage ledger persistence/replay; `test_long_task_final_answer_cannot_claim_completion_without_done_ledger` verifies natural-language completion is downgraded without done ledger. | Closed |
| D47-B05 / T05 | `test_writing_insert_is_idempotent_for_same_selection_and_content` verifies repeated writing writeback replays by idempotency key instead of duplicating pending/inserted blocks. | Closed |
| D47-B06 / T06 | source-library dispatch handler writes `ingest.source_library_dispatches.json` and `ingest.source_library.dispatch_recorded`; unit coverage in `test_legacy_capability_registry_uses_real_handlers_and_hides_unwired_capabilities` verifies dispatch artifact/event/readback hints. | Closed |
| D47-B07 / T07 | `_agent_chat_requires_explicit_project_key` rejects new sessions with `default/public/empty`; `test_agent_chat_default_project_key_is_rejected_for_new_session` and stream error path verify no silent fallback. | Closed |
| D47-B08 / T08 | `test_json_provider_guardrail_creates_workbench_document_from_prior_draft`, `test_writing_document_create_registers_formal_workbench_document`, and API replay verify workbench create intent calls `writing.document.create`. | Closed |
| D47-B09 / T09 | `test_json_provider_guardrail_prioritizes_writing_create_over_project_search_calls` and `test_agent_core_compare_replay_creates_writing_document_instead_of_project_search` verify action-first writing mutation wins over model-returned project search tool calls. | Closed |
| D47-B10 / T10 | `test_agent_core_compare_replay_creates_writing_document_instead_of_project_search` replays the compare session shape: previous draft -> `新建稿件并把内容贴进去` -> only `writing.document.create`, with document id in final answer. | Closed |

Conclusion: D47 convergence items are closed at backend unit, backend API, and frontend AgentChat E2E levels. Any future work should be tracked in a new D48 document rather than reopening this file.
