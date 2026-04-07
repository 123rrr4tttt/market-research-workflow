# Backend AI Agent Runtime Architecture（Current State）

Date: 2026-03-11 (US/Pacific)  
Scope: `main/backend` 当前可运行的 `agent-batch` 后端架构  
Status: CURRENT_DEV / 架构说明（面向研发理解）

---

## 1. 系统定位

当前后端不是“纯聊天代理”，而是一个 **可治理的任务编排内核**：

1. 接收自然语言目标（`nl-command`）。
2. 生成结构化任务（plan）。
3. 按 lane 入队（dispatch）。
4. 由 Celery 执行真实采集任务（execute）。
5. 回传作业状态、事件与结果（observe/report）。

---

## 2. 分层与代码入口

### 2.1 API Orchestration

文件：`main/backend/app/api/agent_batch.py`

关键职责：

1. 暴露对外接口：`/nl-command`、`/jobs`、`/items`、`/events`、`/retry`。
2. 将 loop 的 tasks 转换为 job 提交 payload（`_submit_jobs_from_loop_tasks`）。
3. 管理 job 运行态（内存态 registry + idempotency 索引）。
4. 审批绑定与 fail-closed 拦截。

关键入口：

- `run_agent_batch_nl_command(...)`
- `submit_agent_batch_job(...)`
- `get_agent_batch_job(...)`
- `list_agent_batch_items(...)`

### 2.2 Agent Loop Kernel

文件：`main/backend/app/services/agent_batch/agent_loop.py`

关键职责：

1. `skill-first` 规划，失败时 fallback 到规则 planner。
2. 统一任务 schema 归一化。
3. 执行“检索模式驱动”的任务混编。
4. 输出阶段化运行元数据（stages / degradation flags）。

关键入口：

- `run_agent_batch_nl_command_loop(...)`

### 2.3 Planner

文件：`main/backend/app/services/agent_batch/planner.py`

关键职责：

1. 规则解析 fallback（deterministic）。
2. planner 输出 contract 校验（channel/query_terms/item_key 必填约束）。
3. 稳定 reason code（invalid json/schema/empty tasks）。
4. 提供可调用任务清单（task manifest），作为 planner prompt 的权威能力来源。

### 2.4 Skill Runtime Governance

文件：`main/backend/app/services/skill_runtime.py`

关键职责：

1. skill registry / bootstrap。
2. `actor_role + permissions` 校验。
3. invoke 安全边界控制（拒绝越权调用）。

### 2.5 Execution Layer

文件：`main/backend/app/services/tasks.py`

关键执行任务：

1. `task_ingest_market(...)`：非固定来源搜索采集。
2. `task_run_source_library_item(...)`：固定来源（来源库）条目执行。

---

## 2.6 Task Capability Manifest（新增）

文件：`main/backend/app/services/agent_batch/planner.py`  
注入点：`main/backend/app/services/agent_batch/agent_loop.py::_build_planner_prompt`

目标：

1. 解决“LLM 不能仅靠 agent 文件稳定理解可调用任务”的问题。
2. 将可调用任务从“隐式代码约定”升级为“显式 machine-readable manifest”。

当前机制：

1. 定义 `AGENT_BATCH_TASK_MANIFEST_VERSION = agent_batch.task_manifest.v1`。
2. `build_agent_batch_task_manifest()` 暴露：
   - 可调用 channel（`search.market` / `source_library`）
   - 每个 channel 的 required/optional keys
   - `constraints.retrieval_mode` 可选值
   - 最小示例任务
3. `_build_planner_prompt(...)` 将 manifest JSON 直接拼入 `TASK_MANIFEST` 段，并要求：
   - 不得发明未声明 channel/schema keys
   - `search.market` 必须给 `query_terms`
   - `source_library` 必须给 `item_key`
4. `skill_runtime.register(...)` 新增 `agent_batch_task_manifest` 可选参数：
   - 注册技能时即可声明该技能对应的 task manifest 片段
   - `build_agent_batch_task_manifest()` 会自动合并这些注册项（按 channel 覆盖）
   - 即“注册技能 -> manifest 自动更新 -> planner prompt 自动感知”

收益：

1. 降低 planner 输出 schema 漂移概率，减少 fallback。
2. 提升 LLM 规划可解释性与可审计性（manifest version 可追踪）。
3. 为后续开放新 channel 提供统一入口（先改 manifest，再改 validator/runtime）。

---

## 3. 运行时流程（实际）

用户命令 -> `POST /agent-batch/nl-command`

1. `agent_loop` 先 plan（skill-first）。
2. 根据检索模式（mode）组装最终 tasks。
3. API 批量 submit 到 Celery。
4. 通过 `GET /jobs/{id}` + `/items` + `/events` 回读状态。
5. 输出 `phase/progress/run_id/trace_id` 形成可追踪链路。

---

## 4. “来源库/搜索”在当前系统中的定义

这是 **检索模式（fixed vs non-fixed source）**，不是语义分类：

1. `source_library`：固定来源模式（来源库 item_key）。
2. `search.market`：非固定来源模式（web/provider 搜索）。

当前 loop 支持三种 retrieval mode：

1. `hybrid`（默认）：固定来源 + 非固定来源同时执行。
2. `source_only`：仅固定来源。
3. `web_only`：仅非固定来源。

说明：当前 mode 推断来源于 command/constraints，后续可上升为 API 显式字段。

---

## 5. 现在“自治”到什么程度

当前是 **有边界自治**：

1. LLM 可参与计划生成（skill planner）。
2. 内核会按模式自动补充/裁剪任务集。
3. 但执行仍受治理约束（权限、审批、contract、lane、job schema）。

这不是“完全自由 agent”，而是可上线的工程化自治。

---

## 6. 可观测与稳定性

可观测数据面：

1. loop stages：`plan / autonomous_mix / dispatch / observe_snapshot / strategy_adjustment / report`
2. job progress：`total/succeeded/failed/running/queued`
3. item output/error：任务级结果回读
4. executor health：worker/broker 健康探测

稳定性基线：

1. planner 有 fail-closed fallback。
2. task 失败可被结构化回读并参与 retry。
3. 失败对象已做可序列化归一化，避免接口序列化崩溃。

---

## 7. 当前边界与后续建议

当前边界：

1. 二次 replan（根据执行结果自动再规划）仍较轻量。
2. retrieval mode 还未成为前后端统一显式参数。
3. provider 可用性（配置/限流）会直接影响检索质量。

建议下一步：

1. 把 `retrieval_mode` 放入 API request schema（强类型）。
2. 实现执行后自动 replan（如 search 0 命中 -> 增强 fixed source 路径）。
3. 引入 source item 质量评分（命中率/时效/稳定）替代静态优先级。
