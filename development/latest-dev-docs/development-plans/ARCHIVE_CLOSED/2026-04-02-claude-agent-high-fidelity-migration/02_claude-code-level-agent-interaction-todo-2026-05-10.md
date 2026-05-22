# Claude Code 等级 Agent 交互水准待办总表

更新时间：2026-05-11（PDT）

状态：代码范围已完成收口审计，作为 `2026-04-02-claude-agent-high-fidelity-migration` 专题的历史推进主表。

2026-05-14 收口审计：本文 P0-P6 与 S-01-S-10 的实现状态已经由归档过程记录 [`41_agent-high-fidelity-migration-closure-audit-2026-05-14.md`](../2026-04-02-claude-agent-high-fidelity-migration-process-records/41_agent-high-fidelity-migration-closure-audit-2026-05-14.md) 重新核对。旧文中的“未封口”与后续章节的 `Remaining Gap` 只作为历史推进记录；随后追加的本地资料综合缺口已在 [`46_agent-context-manifest-and-demand-read-synthesis-2026-05-14.md`](./46_agent-context-manifest-and-demand-read-synthesis-2026-05-14.md) 落地并记录回归证据。

2026-05-11 主线重置：用户端实测证明当前实现仍然被机械分类构架限制，`enable_model_tool_loop` 也只是局部入口决策，不是 Claude Code 式模型拥有工具循环。本文中已勾选的 P0/P1/P4/P5/P6 项只代表 Agent Runtime V2 补丁层曾实现过相应能力，不再代表最终封口。新的代码级复原规范以 [`17_claude-code-core-reconstruction-spec-2026-05-11.md`](./17_claude-code-core-reconstruction-spec-2026-05-11.md) 为准：先建立可替换 `AgentCore`，再把项目能力投影为 tool/skill/MCP，最后以用户端自由对话和项目能力调用实测为验收。

2026-05-11 纠偏：此前把“关键词只能作为 hint，最终由模型 tool call 和工具策略决定”标为完成过早。`你好` 被路由到 `agent_batch.nl_command.submit` 的回归说明当前仍存在规则分类器主导入口的问题。P0-05 已重开为 P0-05R，目标改为 model-first routing：大部分意图判断、工具选择和是否需要追问交给模型/planner；规则层只保留安全、权限、预算、审批和 hard no-go guardrail。

2026-05-11 审批冻结：审批不再作为主线交互成熟度目标。`AgentCore` 默认不因 `ask` / `explicit_user_request` 工具生成审批暂停；前端不再默认发送 `require_high_risk_approval=true`。审批协议、历史 pending approval 继续/拒绝、approval card 作为兼容层保留。当前安全边界改为工具显式选择、schema 校验、project isolation、版本锁、预算、来源信任门禁和硬性 deny。

## 目标

把本项目 agent 从“交互入口 + 静态能力选择 + agent_batch 提交器”升级为接近 Claude Code 交互水准的智能 agent：

- 用户可以自由对话，询问能力、项目数据、当前状态、历史产物、来源库、workflow、采集链路和执行边界。
- 模型可以在一轮对话中自主选择工具、执行工具、接收工具结果、继续推理，并给出最终回答。
- 工具执行过程必须实时可见，包含 token、tool_start、tool_progress、tool_result、artifact、approval、error、retry、cancel。
- read-only 工具默认快速并发，写入/外部网络/高风险工具必须通过 schema、版本锁、预算、来源信任门禁和硬性 deny 治理；审批暂停暂时冻结为兼容能力。
- 旧 `agent_batch`、`source_library`、`ingest`、`workflow_graph` 能力保留，但要成为 agent runtime 可调用的工具适配器，而不是唯一执行主路径。
- 前端首屏就是可用 agent 工作台，不是批处理管理面板。

## 代码基线与参考基线

当前项目基线：

- `main/backend/app/api/agent_chat.py`：`POST /agent-chat/turn` 仍是同步单次 turn 入口，并固定注入 `run_agent_batch_nl_command_loop`。
- `main/backend/app/services/agent_runtime/interactive_agent.py`：当前流程是 plan -> execute -> final，执行型请求主要转给 `agent_batch`。
- `main/backend/app/services/agent_runtime/capability_registry.py`：能力选择依赖静态 capability 表与关键词启发式。
- `main/frontend-modern/src/pages/AgentChatPage.tsx`：前端通过一次 mutation 提交 turn，再以 3 秒轮询 session/task/event/artifact。

Claude Code 本地参考基线：

- `/Users/wangyiliang/Desktop/Claude/Claude-Code-main/src/query.ts`：async generator 主循环，模型输出、工具调用和后续消息都可流式产出。
- `/Users/wangyiliang/Desktop/Claude/Claude-Code-main/src/services/tools/StreamingToolExecutor.ts`：工具可边流式生成边执行，支持并发、独占、中断和错误合成。
- `/Users/wangyiliang/Desktop/Claude/Claude-Code-main/src/services/tools/toolOrchestration.ts`：read-only 工具并发，非并发安全工具串行。
- `/Users/wangyiliang/Desktop/Claude/Claude-Code-main/src/Tool.ts`：统一 `ToolUseContext` 承载工具池、权限、MCP、abort、UI 状态、文件状态、技能发现和上下文更新。
- `/Users/wangyiliang/Desktop/Claude/Claude-Code-main/src/tools.ts`：工具池是动态组装的，不是固定少数 capability。
- `/Users/wangyiliang/Desktop/Claude/Claude-Code-main/src/services/SessionMemory/sessionMemory.ts`：长会话依靠记忆提取和压缩维持可持续对话。

本地开源参考基线：

- OpenAI Agents JS：`reference-pool/oss/agent-cases/openai-agents-js/packages/agents-core/src/run.ts` 是 runner 主循环，支持 session、stream、guardrails、handoff、tool call。
- LangGraph：`reference-pool/oss/agent-cases/langgraph/libs/prebuilt/langgraph/prebuilt/tool_node.py` 把工具执行、状态注入、store 注入、错误处理和 graph 条件路由显式化。
- Dify：`reference-pool/oss/dify/api/core/agent/fc_agent_runner.py` 和 `reference-pool/oss/dify/api/core/tools/tool_engine.py` 有模型工具循环和统一工具执行引擎。

## 完成定义

达到“同等交互水准”必须同时满足以下标准：

- 自由对话：用户问基本事实、能力、项目状态、项目数据时，不进入重批处理路径，首 token 或首事件在 1 秒左右出现。
- 自主工具：模型不是被关键词路由固定工具，而是在可见工具 schema 中按需选择工具。
- 工具循环：一轮对话可多次执行工具，工具结果回灌模型后继续推理。
- 实时可见：前端实时显示模型输出、工具开始、工具进度、工具结果、产物、审批和失败恢复。
- 可恢复：中断、审批等待、失败重试、继续执行都能回到同一个 session/task 上下文。
- 可治理：read-only 自动执行；write_shared 做写集冲突控制；write_external/privileged 走审批；所有工具都有 timeout、budget、result_budget。
- 可验证：有固定用户场景回放、工具契约测试、流式事件测试、前端交互 E2E 和性能指标。

## 总体迁移顺序

1. 先做低延迟自由对话与只读工具层，解决“问什么都慢”和“不能自由问”的问题。
2. 再做模型原生工具循环，替代静态 capability 选择。
3. 再把 `source_library`、`ingest`、`workflow_graph`、项目数据查询逐步适配为工具。
4. 再重做前端交互，把实时事件、工具轨迹、产物、审批、取消、重试放到一个自然工作台里。
5. 最后迁移旧 `agent_batch` 调用方，让它降级为兼容适配器，而不是 agent 主干。

## P0 待办：交互主循环与快速对话

- [x] P0-01 定义 `AgentRunLoop`：输入 message + session_context + tool_pool，输出流式 `AgentEvent`。
- [x] P0-02 把 agent turn 拆成 `model_delta`、`assistant_message`、`tool_call_requested`、`tool_call_started`、`tool_call_result`、`final_answer`、`error`。
- [x] P0-03 建立自由对话 fast path：能力、状态、项目概览、来源库概览、已有数据、历史产物查询不进入 `agent_batch`。
- [x] P0-04 把 `_build_final_answer` 模板回答替换为模型基于上下文和工具结果生成的自然回答。
- [x] P0-05R 去掉规则分类器主导入口：`classify_goal` / 静态关键词只能作为低优先级 hint 和安全兜底，默认 turn 由模型/planner 基于上下文、工具 schema、风险策略判断是直接回答、调用只读工具、追问澄清，还是请求审批执行。
- [x] P0-06 增加 turn 级最大循环次数、最大工具次数、最大耗时和最大 token budget。
- [x] P0-07 定义停止条件：无工具调用、达到 final output、审批等待、用户中断、预算耗尽、不可恢复错误。
- [x] P0-08 保留当前 session ledger，但把它作为 context source 和 event sink，不再让每个轻问答都强制 plan/execute/final 三任务。

验收场景：

- [x] 用户问“你能做什么工具？”时，直接回答能力并展示工具目录，不提交 job。
- [x] 用户问“你好”“你是谁”“这个系统现在能干什么”这类普通对话时，默认返回自然对话，不显示 `agent_batch`、审批、`parsed: empty`、工具 chips 或内部路由 metadata。
- [x] 用户问“当前项目有哪些来源库 item？”时，只调用只读来源库查询工具。
- [x] 用户问“刚才执行到哪里了？”时，只读 session/task/event/artifact 并自然总结。
- [x] 用户追问“那继续上一步”时，能复用同一 session 上下文。

### P0-05R 纠偏拆分：Model-first Routing

- [x] P0-05R-01 建立模型主导的 turn decision schema：`answer_direct`、`call_tools`、`ask_clarification`、`request_approval`、`decline_or_safe_complete`，并记录置信度和理由。
- [x] P0-05R-02 把 `classify_goal` 从主路由降级为 `RoutingHints`：只能提供候选工具、风险提示、历史兼容 hint，不能直接触发 `agent_batch` 或审批。
- [x] P0-05R-03 默认策略改为“先普通对话/澄清”：低置信度、短输入、事实问答、能力问答不得默认落到 `execute`。
- [x] P0-05R-04 `agent_batch.nl_command.submit` 只能由模型明确选择或用户明确要求执行时进入候选，并且仍受审批/预算/写集 guardrail 控制。
- [x] P0-05R-05 模型选择工具前必须看到 project-aware tool pool、工具风险、read-only/write/external 分类和最近上下文摘要。
- [x] P0-05R-06 安全规则层只负责 veto / approval / budget / timeout / concurrency，不负责常规语义理解。
- [x] P0-05R-07 增加回归门禁：`你好`、`hello`、`你是谁`、`为什么这么慢`、`当前有什么能力`、`这个项目有什么数据` 都不得进入 `agent_batch`；明确“采集/生成/执行/写入/跑 workflow”才允许进入执行候选。
- [x] P0-05R-08 前端普通对话消息默认只显示 assistant 文本；工具、审批、metadata 只在实际发生时进入右侧 workbench 或折叠详情。
- [x] P0-05R-09 自由事实问答必须由模型自然回答，而不是 canned answer 或“请补充任务类型”模板；`enable_model_tool_loop` 打开时只让入口决策使用 guarded planner，read-only/approval 工具执行仍走快速启发式，避免每个工具场景都阻塞在模型 JSON planner 上。

## P1 待办：工具协议与动态工具池

- [x] P1-01 定义统一 `ToolDefinition` 文档契约：`name`、`description`、`input_schema`、`output_schema`、`risk_level`、`concurrency_class`、`approval_level`、`timeout`、`result_budget`。
- [x] P1-02 定义统一 `ToolExecutionContext`：session、task、project_key、user、abort signal、budget、权限、事件写入器、artifact 写入器。
- [x] P1-03 建立动态工具池装配：按 project_key、用户权限、运行模式、feature flag、MCP/source/workflow 状态组合工具。
- [x] P1-04 建立工具搜索/延迟加载：默认只暴露核心工具，大工具集通过 `tool_search` 或目录工具按需加载。
- [x] P1-05 工具输出统一为面向模型的短结果 + 面向 UI 的结构化详情 + 可落盘 artifact。
- [x] P1-06 工具错误必须返回可恢复信息：参数错误、权限错误、上游错误、超时、取消、需要审批。
- [x] P1-07 工具调用必须支持 `dry_run`、`explain_only`、`approval_required`、`resume_token`。
- [x] P1-08 为每个工具定义最小验证样例，避免工具目录存在但不可执行。

首批工具适配清单：

- [x] T-01 `agent.capabilities.list`：读取可用工具、风险、输入要求。
- [x] T-02 `agent.session.read`：读取当前 session 的消息、任务、事件、产物、审批。
- [x] T-03 `project.summary.read`：读取项目基本信息、配置、数据规模、最近活动。
- [x] T-04 `source_library.items.list`：列出有效来源库 item，默认不展开重执行计划。
- [x] T-05 `source_library.items.search`：按 query/project_key/time_window/source_type 搜索 item。
- [x] T-06 `source_library.item.inspect`：解释单个 item 的参数、默认来源、handler、风险。
- [x] T-07 `source_library.run`：执行来源库采集，高风险，需审批或明确执行边界。
- [x] T-08 `ingest.status.read`：读取 ingest 最近运行、失败原因、产物位置。
- [x] T-09 `ingest.run`：执行 ingest 链路，高风险，必须有审批与预算。
- [x] T-10 `workflow_graph.list`：读取可用 workflow graph。
- [x] T-11 `workflow_graph.inspect`：解释 graph 节点、输入、输出、风险。
- [x] T-12 `workflow_graph.run`：运行 workflow，高风险，走审批和可恢复 task。
- [x] T-13 `artifact.search`：查询已有报告、表格、采集结果、日志。
- [x] T-14 `artifact.read`：读取指定 artifact 摘要或结构化内容。
- [x] T-15 `report.generate`：基于已有数据生成报告草稿，写入型，需声明输出路径。
- [x] T-16 `task.cancel`：取消当前 session 或指定 task。
- [x] T-17 `task.retry`：按失败 task 的 resume token 重试。
- [x] T-18 `task.continue`：从审批、中断或等待状态恢复。

## P2 待办：并发、权限、审批与中断

- [x] P2-01 按 Claude Code 语义实现并发策略：`read_only` 可并发；`write_shared` 按 write_set 串行或互斥；`write_external` 与 `privileged` 必须审批。
- [x] P2-02 每个工具在执行前发 `tool_call_started`，执行中发 progress，完成后发 `tool_call_result`。
- [x] P2-03 工具运行必须接入 abort signal，用户取消后要向模型返回中断结果，而不是让请求悬挂。
- [x] P2-04 审批等待必须成为 session 内可恢复状态，前端可批准/拒绝/修改参数。
- [x] P2-05 写入型工具执行前生成简短 diff/影响范围说明。
- [x] P2-06 外部网络和成本型工具必须有预算、时间窗、来源范围和最大结果数。
- [x] P2-07 工具失败后把错误作为 tool result 回灌模型，允许模型修正参数后重试。
- [x] P2-08 建立 hook 点：pre_tool、post_tool、on_error、on_approval、on_cancel。

## P3 待办：记忆、上下文与压缩

- [x] P3-01 建立 session memory：把长期对话压缩成稳定摘要，不把全量消息每轮塞进模型。
- [x] P3-02 建立 project context builder：项目配置、source_library 摘要、最近运行、产物索引按需注入。
- [x] P3-03 建立 tool-use summary：把长工具轨迹压缩为可读进度摘要和模型可消费摘要。
- [x] P3-04 建立 context budget 策略：优先级为用户最新指令、审批状态、当前任务、工具结果摘要、项目摘要、历史摘要。
- [x] P3-05 建立 memory update 触发：token 阈值、工具次数阈值、任务完成、用户显式总结。
- [x] P3-06 建立记忆纠错机制：用户指出错误时更新 session memory 或标记旧摘要失效。

## P4 待办：前端交互重做

- [x] P4-01 首屏改为对话优先：左侧 session 列表，中央对话流，右侧工具/产物/审批抽屉。
- [x] P4-02 消息气泡支持实时 token 流、正在思考状态、工具调用卡片和最终答案。
- [x] P4-03 工具轨迹以 timeline 呈现：请求参数摘要、状态、耗时、结果摘要、展开详情。
- [x] P4-04 approval card 支持批准、拒绝、修改参数后批准。
- [x] P4-05 artifact drawer 支持报告、JSON、表格、日志、采集结果的预览和定位。
- [x] P4-06 session task 面板保留，但作为辅助，不再压过对话主流程。
- [x] P4-07 取消、继续、重试必须直接贴近当前消息或当前工具，而不是全局按钮堆叠。
- [x] P4-08 增加工具目录/能力面板，用户可查看当前 agent 能做什么、哪些需要审批。
- [x] P4-09 增加空状态和错误状态：无项目、无来源库、后端离线、工具超时、审批等待。
- [x] P4-10 移动端和窄屏必须保持对话、工具轨迹、产物三者可切换，不互相遮挡。

视觉目标：

- [x] 信息密度接近专业工作台，而不是营销页或卡片堆。
- [x] 状态颜色克制：运行中、成功、失败、等待审批、中断要有明确但不刺眼的区分。
- [x] 工具调用细节默认折叠，重要状态默认可见。
- [x] 不用大段说明文字解释怎么用，交互本身要能被理解。

## P5 待办：兼容迁移与旧链路降级

- [x] P5-01 保留 `/agent-chat/turn` 兼容入口，但内部转到新 `AgentRunLoop`。
- [x] P5-02 新增流式入口作为主入口，旧 mutation 只作为 fallback。
- [x] P5-03 `agent_batch.nl_command.submit` 降级为一个可审批工具，而不是默认所有执行型请求的主路径。
- [x] P5-04 `source_library`、`ingest`、`workflow_graph` 调用方逐步迁移到工具适配层。
- [x] P5-05 旧 session/task/artifact API 保留读取兼容，写入统一由新 runtime 产生。
- [x] P5-06 对旧前端状态模型做兼容桥，避免迁移期间丢失历史 session。
- [x] P5-07 加 feature flag：`agent_runtime_v2_enabled`、`agent_stream_enabled`、`agent_batch_as_tool_enabled`。
- [x] P5-08 支持 A/B 或灰度：同一用户可回退旧路径，便于定位回归。

## P6 待办：测试、指标与验收门禁

- [x] P6-01 单元测试：工具 schema、工具权限、并发策略、错误转换、context builder。
- [x] P6-02 集成测试：自由对话、只读工具、多工具循环、审批等待、取消、重试、继续。
- [x] P6-03 回放测试：用固定用户场景验证 agent 是否能自主调用项目各环节完成任务。
- [x] P6-04 前端 E2E：流式消息、工具 timeline、approval card、artifact drawer、cancel/retry/continue。
- [x] P6-05 性能指标：首事件延迟、首 token 延迟、工具启动延迟、轮询/流式连接稳定性、工具耗时分布。
- [x] P6-06 观测指标：每轮 tool_count、retry_count、approval_count、cancel_count、error_kind、budget_used。
- [x] P6-07 回归门禁：自由问答不得提交 agent_batch job；只读查询不得触发外部采集；取消后不得继续写入。
- [x] P6-08 用户场景验收报告：每轮变更后保存 scenario replay 结果到开发文档。

## 必须通过的用户场景

- [x] S-01 能力问答：用户问“你能做什么”，agent 返回可用能力、风险等级和可执行入口。
- [x] S-02 项目事实问答：用户问“当前项目有哪些数据源/来源库/最近产物”，agent 只读查询并回答。
- [x] S-03 来源库采集：用户要求“用来源库补一轮证据”，agent 直接选择来源库执行工具；候选扩展和外部来源发现仍先走信任/范围工具，审批暂停冻结。
- [x] S-04 ingest 链路：用户指定对象和时间窗，agent 自动选择 ingest/source_library 工具并展示过程。
- [x] S-05 workflow 执行：用户要求跑某个 workflow，agent 能检查 graph 输入、发起审批、执行并回填结果。
- [x] S-06 失败恢复：工具失败后，agent 能解释原因、修正参数或建议重试。
- [x] S-07 中断继续：用户取消运行后，session 保留可恢复状态；用户说“继续”时能恢复。
- [x] S-08 追问上下文：用户追问“刚才那个结果里第二项为什么失败”，agent 能引用对应工具结果。
- [x] S-09 产物查看：用户要求查看生成的报告/日志/JSON，agent 能定位并摘要 artifact。
- [x] S-10 低延迟闲聊：用户问基本能力和状态，不应出现长时间无响应或进入批处理路径。

## 里程碑

### M1：自由对话与只读工具可用

- 完成 P0、P1 中只读工具、P6 中基础测试。
- `agent_batch` 不再处理能力问答、状态问答、项目事实问答。
- 前端能实时展示 assistant 文本和只读工具调用轨迹。

### M2：模型工具循环可用

- 完成多轮 tool call -> tool result -> model follow-up。
- source_library 只读和 inspect 工具稳定。
- 工具错误可回灌模型并修正。
- 主路由进入 model-first：规则分类只做 hint，模型/planner 决定直接回答、工具调用、澄清或审批。

### M3：高风险工具可治理执行

- source_library.run、ingest.run、workflow_graph.run 作为审批工具可执行。
- 支持 cancel/retry/continue。
- 工具产物统一进入 artifacts。

### M4：前端达到可用工作台水准

- 对话、工具 timeline、approval、artifact drawer、session task 全链路可用。
- 完成移动端/窄屏基本适配。
- 用户不需要知道 agent_batch 或内部接口即可完成任务。

### M5：旧路径降级为兼容层

- 新 runtime 成为 agent 主路径。
- 旧 `agent_batch` 只作为工具或 fallback。
- 固定用户场景全部 green。

## 风险与控制

- 风险：一次性替换 `agent_batch` 会破坏既有执行链路。控制：先把 `agent_batch` 包成工具，保留旧入口，逐步迁移调用方。
- 风险：模型自由选工具可能误触发昂贵或写入操作。控制：read-only 自动，写入/外部/高权限审批，预算与超时强制。
- 风险：流式前端和旧轮询状态并存导致 UI 状态错乱。控制：新 runtime 以 event log 为唯一事实源，轮询只作为 fallback。
- 风险：上下文过大导致速度继续慢。控制：session memory、tool summary、项目摘要和按需工具搜索。
- 风险：工具目录过大导致模型选择变差。控制：默认核心工具 + 延迟工具搜索 + project-aware tool pool。

## 不做事项

- 不复制 Claude Code 的 CLI/Ink UI。
- 不复制 Claude 私有 feature gate、远程 bridge 或 Anthropic SDK 绑定。
- 不把所有现有后端 API 直接暴露给模型；必须经过工具契约、权限和结果预算。
- 不把 `agent_batch` 删除；先降级为兼容工具，待场景全部迁移后再收口。

## 当前实现记录

主线推进时必须同步检查本表 P0-P6 与 S-01-S-10，不只处理当前阶段标题。当前已落地记录：

下列实现记录已经归档到 [`ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records`](../2026-04-02-claude-agent-high-fidelity-migration-process-records/INDEX.md)。

- `03_claude-code-level-agent-m1-implementation-status-2026-05-10.md`：M1 自由对话与只读工具首批实现。
- `04_agent-runtime-v2-tool-loop-and-approval-status-2026-05-10.md`：M2/M3 工具循环、审批等待与批准继续。
- `05_agent-workbench-ui-and-mainline-satisfaction-2026-05-10.md`：M4 工作台与 P0-P6/S 场景满足度矩阵。
- `06_agent-runtime-v2-project-tool-adapters-2026-05-10.md`：workflow graph 与 ingest/source-library 只读适配。
- `07_agent-runtime-v2-approval-edit-reject-ui-replay-2026-05-10.md`：审批参数编辑、拒绝与 UI 回放。
- `08_agent-runtime-v2-scenario-replay-gate-2026-05-10.md`：S-01/S-02/S-05/S-06 固定场景回放门禁。
- `09_agent-runtime-v2-session-control-tools-2026-05-10.md`：`task.cancel`、`task.retry`、`task.continue` 控制工具。
- `10_agent-runtime-v2-context-followup-replay-2026-05-10.md`：最近工具结果摘要与 S-08 追问上下文回放。
- `11_agent-runtime-v2-scenario-completion-runtime-flags-and-metrics-2026-05-10.md`：S-03/S-04/S-07/S-09/S-10 回放补齐、模型最终回答出口、运行时 feature flags 与 run-loop 指标。
- `12_agent-workbench-capability-panel-artifact-preview-2026-05-10.md`：前端能力面板、读/写治理分组、artifact 选择预览与桌面/移动无溢出验证。
- `13_agent-runtime-v2-tool-context-pool-search-2026-05-10.md`：`ToolExecutionContext`、调用选项、动态工具池、工具搜索、API tool_pool 与前端能力面板动态分组。
- `14_agent-runtime-v2-session-memory-context-budget-2026-05-10.md`：session memory、project context builder、tool-use summary、context budget、memory update trigger 与记忆纠错失效标记。
- `15_agent-runtime-v2-governance-report-stream-ui-e2e-2026-05-10.md`：P2 执行治理 hook/abort/并发、`report.generate`、前端近场控制/工作台切换、stream 入口、legacy_batch 回退与 E2E smoke。

## 下一步执行入口

原推荐拆分如下，后续执行记录已按实际推进扩展为 `03` 到 `08`：

- `03_agent-runtime-v2-fast-chat-and-readonly-tools-2026-05-10.md`
- `04_agent-runtime-v2-tool-loop-and-streaming-events-2026-05-10.md`
- `05_agent-workbench-ui-redesign-and-acceptance-scenarios-2026-05-10.md`

这三份分别对应 M1、M2-M3、M4，可独立推进和验收。
