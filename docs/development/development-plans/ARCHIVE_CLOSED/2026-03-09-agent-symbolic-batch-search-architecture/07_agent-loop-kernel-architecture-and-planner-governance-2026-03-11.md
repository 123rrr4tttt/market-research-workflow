# Agent Loop 内核架构与 Planner 治理（P2 架构基线，含对标实现）

Date: 2026-03-11 (PST)  
Scope: `agent-batch nl-command` 到全链路 agent 化执行  
Status: CURRENT_DEV / 作为 P2 架构约束基线（替换旧版“仅 planner 设计”）

---

## 1. 背景与问题重述

当前系统已有 batch API、handoff/replay、workflow.llm_call skill 化调用路径，但旧版设计存在两个核心问题：

1. 对“Agent 内核”陈述过于抽象，缺少可落地模块边界。  
2. 过度聚焦 planner，未覆盖 execution runtime / tool runtime / safety / queue / observability。

本文件将 `planner` 下沉为内核中的一个可替换子模块，并冻结完整内核契约。

---

## 2. 核心结论（执行约束）

1. Planner 必须工程化治理（版本、schema、失败语义、fallback），不能以自由文本直下任务。  
2. Agent Kernel 必须至少包含 8 个层面：
- `Session/Thread Runtime`
- `Plan`
- `Execute`
- `Tool Runtime`
- `Safety/Approval`
- `Context/Memory`
- `Queue/Concurrency`
- `Observability/Recovery`

3. 生产路径必须 `skill-first`，规则解析器仅作为 fail-closed fallback。  
4. 每轮 loop 必须输出统一元数据：`loop_id/stages/degradation_flags/strategy_adjustments/reason_code`。  
5. 每个任务下发必须带 `workflow_run_id + trace_id + task_id`，保证回放和归责。

---

## 3. 标准 Agent Kernel（五阶段 + 三条横切能力）

### 3.1 五阶段主流程（纵向）

1. `plan`：结构化任务图生成（非自由文本）  
2. `dispatch`：任务入队、lane 选择、并发上限约束  
3. `execute`：模型推理 + 工具调用 + 中间状态更新  
4. `observe_adjust`：状态观测、失败分类、策略调整（重试/降级/换模型）  
5. `report`：对外输出兼容视图 + 审计元数据

### 3.2 三条横切能力（必须全程生效）

1. `safety/approval`：执行前、执行中、执行后的安全与审批约束。  
2. `context/memory`：上下文构建、压缩、持久化、恢复。  
3. `observability/recovery`：事件流、指标、重放、恢复、终止条件。

---

## 4. 对标实现（文件级定位，不是概念图）

以下为 2026-03-11 实际仓库位点抽样，作为“完整工程实现”证据链。

### 4.1 Codex（OpenAI / Rust）

仓库：`openai/codex`

1. Session/Thread Runtime
- `codex-rs/core/src/thread_manager.rs`：`ThreadManager` 负责线程创建、模型管理、MCP 管理、skills/plugins 装配。
- `codex-rs/core/src/codex_thread.rs`：`CodexThread.submit()` / `next_event()` / `config_snapshot()`。

2. 统一事件总线（loop 的真实输出面）
- `codex-rs/protocol/src/protocol.rs`：`EventMsg`（`TurnStarted/TurnComplete/PlanUpdate/ExecCommand* / RequestPermissions / McpToolCall*`）。

3. Planner 与执行解耦
- `codex-rs/core/src/tools/handlers/plan.rs`：`PlanUpdate` 事件发射。
- `codex-rs/app-server/src/bespoke_event_handling.rs`：把 `PlanUpdate / ExecCommand / RequestPermissions` 映射到前端/客户端协议。

4. Safety/Approval
- `codex-rs/protocol/src/request_permissions.rs`：权限请求/响应契约。
- `codex-rs/app-server/src/bespoke_event_handling.rs`：审批请求与回传处理（`ExecCommandApproval*`）。

5. Tool Runtime / Subagents
- `codex-rs/core/src/tools/handlers/multi_agents.rs`：子 agent 继承审批策略、sandbox、cwd，并提供事件通知。

结论：Codex 的 planner 只是 `EventMsg::PlanUpdate` 的一个来源，真正内核是 `thread runtime + event protocol + execution/approval bridge`。

### 4.2 OpenClaw（TypeScript）

仓库：`openclaw/openclaw`

1. 运行内核入口
- `src/agents/pi-embedded-runner/run.ts`：`runEmbeddedPiAgent()` 主入口，含重试上限、fallback、上下文窗口守卫、lane 入队。

2. Queue/Concurrency
- `src/process/command-queue.ts`：多 lane 队列、并发控制、draining、lane clear、reset。
- `src/process/lanes.ts`：`CommandLane`（`main/cron/subagent/nested`）。
- `src/agents/pi-embedded-runner/lanes.ts`：session lane + global lane 解析。

3. Streaming/状态机/恢复
- `src/agents/pi-embedded-subscribe.ts`：流式订阅、reasoning 模式、block reply、compaction 重试与收敛。
- `src/agents/pi-embedded-runner/runs.ts`：active run 注册、abort、wait-for-end。

4. Tool Runtime + Planner 执行桥
- `src/agents/tools/agent-step.ts`：`runAgentStep()`（agent -> wait -> 取最新回复）。
- `src/agents/tool-policy.ts` + `src/agents/tool-policy-pipeline.ts`：工具策略管线、allow/deny、plugin-only allowlist 保护。
- `src/agents/tool-loop-detection.ts`：重复调用/轮询无进展/ping-pong 检测。

5. Safety/Approval
- `src/infra/exec-approvals.ts`：审批协议、默认策略、allowlist、timeout。
- `src/infra/system-run-approval-binding.ts`：审批绑定校验（argv/cwd/agentId/session/envHash）。
- `src/infra/exec-approval-forwarder.ts`：审批转发到消息通道（Telegram/Discord 等）。

结论：OpenClaw 不是“planner 驱动”，而是“lane queue + run loop + approval binding + tool-policy pipeline”联合驱动。

### 4.3 OpenHands SDK（Python）

仓库：`OpenHands/software-agent-sdk`

1. Agent Step Loop
- `openhands-sdk/openhands/sdk/agent/agent.py`：`Agent.step()`，执行 `pending_actions -> LLM -> tool calls -> action events -> execute`。
- `openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py`：`run()` 主循环（状态机、max iterations、stuck detection、错误事件化）。

2. 状态机与持久化
- `openhands-sdk/openhands/sdk/conversation/state.py`：`ConversationExecutionStatus`、`ConversationState`（confirmation/security/stats/secret_registry）。
- `openhands-sdk/openhands/sdk/conversation/event_store.py`：`EventLog`（append-only、加锁、索引恢复）。

3. 反死循环与安全
- `openhands-sdk/openhands/sdk/conversation/stuck_detector.py`：action-observation/error/monologue/alternating/context-window loop 检测。
- `openhands-sdk/openhands/sdk/security/confirmation_policy.py`：`AlwaysConfirm/NeverConfirm/ConfirmRisky`。

4. Tool 抽象与远程执行
- `openhands-sdk/openhands/sdk/tool/tool.py`：`ToolExecutor`、ToolDefinition 契约。
- `openhands-sdk/openhands/sdk/mcp/tool.py`：`MCPToolExecutor` 与 schema 动态绑定。
- `openhands-agent-server/openhands/agent_server/event_service.py`：服务端会话执行与事件发布。
- `openhands-sdk/openhands/sdk/conversation/impl/remote_conversation.py`：远程会话订阅与状态同步。

结论：OpenHands 明确把 planner 放在 `Agent.step()` 的一环，真正可运营能力在 `conversation loop + event store + stuck detector + confirmation policy`。

---

## 5. 本项目目标内核分层（冻结）

### 5.1 模块边界

1. `kernel/session_runtime`
- 管理 `workflow_run_id/trace_id/task_id`。
- 持有线程级上下文、配置快照、回放锚点。

2. `kernel/planner`
- 仅负责结构化计划：`intent/constraints/tasks/strategy`。
- 必须 schema 校验，失败输出统一 `reason_code`。

3. `kernel/executor`
- 消费 plan 形成可执行项；负责重试、退避、provider fallback。

4. `kernel/tool_runtime`
- skill/tool 调度、策略过滤、环路检测、工具结果归一化。

5. `kernel/safety_approval`
- 危险动作审批、参数绑定校验（命令+cwd+env 指纹）。

6. `kernel/context_memory`
- 历史压缩、窗口守卫、事件持久化、恢复加载。

7. `kernel/queue_concurrency`
- lane 模型（至少 `main/subagent/system`），支持 drain/reset/隔离重试。

8. `kernel/observability`
- 统一事件流 + 指标 + reason taxonomy + replay。

### 5.2 Planner 治理（保留并强化）

每个 planner 版本必须有：
- `prompt_id`
- `contract_version`
- 输入约束
- 输出 schema
- 失败语义
- fallback 策略与 reason_code

禁止项：
- LLM 自由文本直接下发任务。
- 无 schema 的猜测解析进入 dispatch。
- fallback 静默发生。

---

## 6. 最小验证集（从“只测 planner”升级为“测内核”）

1. unit
- planner schema 成功/失败。
- executor 重试与 fallback。
- tool policy 与 loop detection。
- approval binding 校验（argv/cwd/envHash）。

2. integration
- `nl-command -> plan -> dispatch(lane) -> execute(tool) -> observe_adjust -> report`。
- `workflow-handoffs -> replay` 一致性。

3. gate
- rollback drill（dry-run）必须通过。
- reason taxonomy 与 metrics schema 校验通过。
- 至少 1 条真实指令具备完整 trace（plan + tool + approval + outcome）。

---

## 7. 实施顺序（P2）

1. 先落地 `session_runtime + event schema + reason_code taxonomy`。  
2. 再落地 `planner schema + executor + lane queue`。  
3. 最后补 `approval binding + loop detection + replay gate`。

---

## 8. Done Criteria（架构级）

1. `nl-command` 默认走 skill planner，fallback 可观测。  
2. 五阶段主流程稳定输出，且事件链可回放。  
3. 任务级 `run/trace/task` 在查询链路闭环。  
4. tool runtime 具备策略过滤 + loop 防护 + 审批绑定。  
5. pre-release gate 覆盖 rollback drill + schema + taxonomy。

---

## 9. 本仓库内核映射（目录与入口函数）

### 9.1 Session / Thread Runtime

- `main/backend/app/services/agent_batch/agent_loop.py`
  - `run_agent_batch_nl_command_loop(...)`：主循环入口（plan -> dispatch -> observe -> adjust -> report）。
- `main/backend/app/api/agent_batch.py`
  - `_submit_jobs_from_loop_tasks(...)`：loop 任务下发入口。
  - `_BATCH_JOB_REGISTRY / _IDEMPOTENCY_INDEX`：当前运行态与幂等索引（内存态）。

### 9.2 Planner

- `main/backend/app/services/agent_batch/planner.py`
  - `plan_batch_search_command(...)`：规则解析 planner（deterministic fallback）。
- `main/backend/app/services/agent_batch/agent_loop.py`
  - `_plan_skill_first(...)`：skill-first 规划 + fallback 聚合。
  - `_extract_plan_from_llm_text(...)`、`_normalize_plan(...)`：结构化输出收敛。

### 9.3 Executor

- `main/backend/app/services/tasks.py`
  - `task_ingest_market(...)`：主要执行任务（market collect）。
  - 其他 celery task：单 URL、索引、资源采集等。
- `main/backend/app/services/agent_batch/executor_health.py`
  - `inspect_executor_health(...)`：执行器健康快照。

### 9.4 Tool Runtime / Safety

- `main/backend/app/services/skill_runtime.py`
  - `SkillRuntime.invoke(...)`：skill 调度、actor_role + permissions 校验。
  - `_bootstrap(...)`：workflow_graph/llm_call 技能注册。
- `main/backend/app/api/skills.py`
  - `/skills/invoke`：技能调用 API 封装层。

### 9.5 Context / Memory / Replay

- `main/backend/app/services/workflow_graph/handoff_store.py`
  - `persist(...)` / `list_handoffs(...)` / `replay_handoff(...)`：handoff 持久化与回放。

### 9.6 Queue / Concurrency / Lane Routing

- `main/backend/app/api/agent_batch.py`
  - `_resolve_lane(...)`：按 channel/priority 决定 lane（`main/subagent/system`）。
  - `_resolve_queue_for_lane(...)`：lane 到 queue 的映射。
  - `_apply_async_or_delay(...)`：统一 `apply_async`（queue + routing_key）下发。
- `main/backend/app/settings/config.py`
  - `agent_batch_lane_main_queue` / `agent_batch_lane_subagent_queue` / `agent_batch_lane_system_queue`。

### 9.7 Safety / Approval Binding

- `main/backend/app/services/agent_batch/approval_binding.py`
  - `request_approval(...)` / `verify_approval_token(...)` / `approve_approval(...)` / `cleanup_expired(...)`。
- `main/backend/app/api/agent_batch.py`
  - `_enforce_approval_if_needed(...)`：提交前审批拦截。
  - `/approvals` / `/approvals/{token}`：审批创建与决议 API。

### 9.8 Observability / Failure Taxonomy / Health

- `main/backend/app/api/agent_batch.py`
  - `get_agent_batch_job(...)`：阶段汇总、progress 与 phase 输出。
  - `list_agent_batch_items(...)`：item 级 output/error 归一化。
  - `get_agent_batch_events(...)`：事件流输出。
  - `get_agent_batch_failure_reasons(...)`：失败 reason 聚合。
- `main/backend/app/services/agent_batch/executor_health.py`
  - `inspect_executor_health(...)`：broker/worker 在线状态探测。
- `main/backend/scripts/check_agent_symbolic_metrics_schema.py`
  - 指标 schema 门禁校验脚本。

---

## 10. 当前实现状态（2026-03-11 快照）

### 10.1 已落地能力

1. `nl-command` 已走 `skill-first` planner，并提供 deterministic fallback。  
2. loop 输出 `stages + loop_id + degradation_flags + strategy_adjustment`。  
3. `search.market` 与 `source_library` 均可纳入同一批次任务。  
4. 执行结果可通过 `jobs/items/events` 闭环回读。  
5. approval binding 与 executor health 已接入 API。

### 10.2 已知边界

1. planner prompt 仍偏“search 优先”，对 mode 显式表达不足。  
2. 二次 replan（根据首轮执行结果自动再规划）能力仍有限。  
3. provider 配置与限流会直接影响检索命中，不属于 loop 本体 bug。  
4. `_BATCH_JOB_REGISTRY` 仍为内存态，不具备跨实例持久化能力。

---

## 11. 风险与约束（上线前必须确认）

1. 任务风暴风险  
- 约束 `max_items`、批次任务数、lane 并发上限，防止失控入队。

2. 外部依赖风险  
- provider 不可用/限流时要有稳定降级与可观测 reason code。

3. 审批与执行偏差风险  
- 所有高风险命令必须绑定 argv/cwd/env 指纹，不允许裸 token 复用。

4. 回放一致性风险  
- `workflow_run_id + trace_id + task_id` 必须在 submit 与查询链路完全一致。

---

## 12. Release Gate（建议纳入 pre-release）

1. 合同门禁  
- planner contract 校验通过；reason taxonomy 与 metrics schema 校验通过。

2. 链路门禁  
- `nl-command -> jobs -> items -> events` 全链路冒烟通过（含 1 条失败样本）。

3. 安全门禁  
- approval required 场景必须拦截成功；approval token 过期与绑定不匹配可复现。

4. 回滚门禁  
- rollback drill（dry-run）通过，且失败可回放定位。

---

## 13. 最小操作手册（研发本地）

1. 健康探测  
- `GET /api/v1/agent-batch/executor/health`

2. 命令执行  
- `POST /api/v1/agent-batch/nl-command`

3. 作业查询  
- `GET /api/v1/agent-batch/jobs/{job_id}`
- `GET /api/v1/agent-batch/jobs/{job_id}/items`
- `GET /api/v1/agent-batch/jobs/{job_id}/events`

4. 指标与契约检查  
- `python scripts/check_agent_symbolic_metrics_schema.py`

---

## 14. 文档使用说明

本文件是 **P2 架构基线**，用于冻结：

1. 内核边界（不是仅 planner）。  
2. 执行约束（可治理、可审计、可回放）。  
3. 上线门禁（contract + safety + replay + observability）。

若实现发生变更，必须同步更新第 9~13 节，确保“架构描述 == 真实运行系统”。
