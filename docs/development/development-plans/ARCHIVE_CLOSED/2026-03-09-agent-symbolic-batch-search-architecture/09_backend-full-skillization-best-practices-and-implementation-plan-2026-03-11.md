# 后端全量技能化最佳实践与实施方案（2026-03-11）

Date: 2026-03-11 (US/Pacific)  
Scope: `main/backend`（目标：Agent 可通过技能层直接调用全部后端能力）  
Status: CURRENT_DEV / 执行方案

---

## 1. 目标与结论

目标定义（Full Skillization）：

1. Agent 侧只通过 `invoke_skill` 调用后端能力，不直接依赖 `api/*` 或 `services/*` 具体实现。
2. 每个业务能力都有可发现技能定义（name/description/input schema/permission boundary/owner/contract_version）。
3. 所有技能调用可审计（trace_id、tool lifecycle、error taxonomy、policy decision）。

结论：

1. 当前项目已具备技能 runtime 与部分能力样板（workflow_graph + agent_batch planner skill-first）。
2. 距离“全量技能化”主要差在执行链路和 API 能力的系统性封装，仍需分波次迁移。

---

## 2. 外部最佳实践（可追溯）

### 2.1 工具定义要“重描述 + 强 schema”

实践：

1. 工具描述必须足够详细，明确“何时用/何时不用/参数语义/限制”。
2. 输入参数必须使用 JSON Schema，避免模型猜测参数结构。

来源：

- Anthropic Tool Use（Best practices for tool definitions）  
  https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use

### 2.2 让工具目录成为模型可见的“系统上下文”

实践：

1. 运行时将工具定义注入模型上下文（而不是依赖模型记忆代码）。
2. 约束模型“不可发明未声明工具/字段”。

来源：

- Anthropic Tool Use（tool definitions in JSON Schema 注入系统提示）  
  https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use

### 2.3 把 handoff 当作可治理工具，而非隐式跳转

实践：

1. 多 Agent 交接应显式建模为 handoff tool。
2. 为 handoff 补充描述与输入过滤器，避免上下文污染。

来源：

- OpenAI Agents SDK Handoffs  
  https://openai.github.io/openai-agents-python/handoffs/

### 2.4 在工具调用前后加 guardrails

实践：

1. 对高风险工具启用输入/输出 guardrails。
2. 对拒绝策略统一行为（allow/reject/exception），保证策略可测试。

来源：

- OpenAI Agents SDK Guardrails  
  https://openai.github.io/openai-agents-js/guides/guardrails/

### 2.5 全链路 tracing 默认开启

实践：

1. 追踪至少覆盖：LLM generation、tool call、handoff、guardrail。
2. 支持敏感数据脱敏开关与 run 级 trace metadata。

来源：

- OpenAI Agents SDK Tracing / Running agents  
  https://openai.github.io/openai-agents-js/guides/tracing/  
  https://openai.github.io/openai-agents-js/guides/running-agents

### 2.6 用标准元数据表达工具副作用与幂等性

实践：

1. 对工具标注只读/破坏性/幂等/open-world 属性。
2. 客户端策略可基于标注做风险分级与审批绑定。

来源：

- MCP Tools（readOnlyHint / destructiveHint / idempotentHint / openWorldHint）  
  https://modelcontextprotocol.io/legacy/concepts/tools

### 2.7 权限与授权要最小化，禁止 token passthrough

实践：

1. OAuth 2.1 + PKCE + token audience 校验。
2. 明确禁止 token passthrough 反模式。

来源：

- MCP Authorization (2025-11-25)  
  https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization  
- MCP Security Best Practices  
  https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices

---

## 3. 本项目现状基线（2026-03-11）

已具备：

1. `skill_runtime` 具备 registry + actor_role/permissions boundary。
2. `workflow_graph` API 已大范围走 `invoke_skill`。
3. `agent_batch` planner 已是 skill-first，并引入 task manifest。

未完成：

1. 执行层仍大量直连 Celery task/service（如 ingest/source_library/process）。
2. 多数 API 能力尚未抽象成独立技能契约。
3. “技能目录 -> agent 可发现能力”还未形成全域统一索引。

---

## 4. 目标架构（全量技能化）

调用原则：

1. Agent -> `skills gateway` -> `skill_runtime` -> domain adapters -> existing services/tasks。
2. API 继续对人类/系统提供 HTTP 接口，但 agent 路径只走技能层。

分层：

1. L0 `platform skills`：`workflow.llm_call`、trace、policy、approval。
2. L1 `domain atomic skills`：ingest、source_library、search、report、project admin 等原子动作。
3. L2 `composite skills`：多步骤编排（可回放、可降级）。
4. L3 `agent handoff skills`：跨 agent 专业能力转交。

---

## 5. 技能契约标准（项目内强制）

每个 skill 必须具备：

1. `skill_id`（命名空间化，如 `ingest.market.search`）。
2. `description`（至少 3-4 句，包含适用边界与反例）。
3. `input_schema`（JSON Schema）。
4. `required_permissions` + `allowed_actor_roles`。
5. `contract_version`（显式版本）。
6. 返回 envelope：`status/data/error/meta`（与现有 API 一致）。
7. 可观测字段：`trace_id`、`consumer`、`owner`、`latency_ms`、`reason_code`。

---

## 6. 迁移路线（分波次）

### Phase 0：目录与治理先行（1-2 天）

1. 建立 `Skill Capability Catalog`（机器可读 + 文档可读双份）。
2. 冻结命名规范、权限规范、error taxonomy。
3. 建立“新增后端能力必须先注册 skill”的门禁脚本。

验收：

1. 新增能力 PR 若无 skill 注册与 schema，CI 失败。

### Phase 1：执行链路技能化（3-5 天）

范围：

1. `agent_batch` dispatch path。
2. `ingest`（market/source item run）。
3. `source_library` run/refresh。
4. `process` retry/cancel/inspect。

策略：

1. 先加 adapter（skill -> 旧 service/task），不改业务逻辑。
2. 保持 API 向后兼容，切换 agent 调用入口到 skill。

验收：

1. agent 端不再直接引用 task function。
2. 与旧路径结果一致（契约测试 + 回归样例）。

### Phase 2：API 能力全覆盖技能化（5-10 天）

范围：

1. 按业务域建立 skill 包：`projects`、`resource_pool`、`crawler`、`writing`、`llm_report` 等。
2. 为高风险能力补 guardrails（写操作、外部网络、批量操作）。

验收：

1. 关键业务域覆盖率 >= 95%（按 route capability 计）。
2. 技能调用 trace 覆盖率 >= 99%。

### Phase 3：收敛与强制（2-3 天）

1. 关闭 agent 直连 service/task 的后门路径。
2. 启用审批绑定（按 destructive/open-world/idempotent 分级）。
3. 进行故障演练（权限拒绝、超时、重试、回滚）。

---

## 7. 最小验证步骤

1. 单测：skill contract validation、permission boundary、error mapping。
2. 集成：agent -> skill -> adapter -> task/service 闭环。
3. 回归：选 20 条真实命令，比较迁移前后输出一致性。
4. 观测：验证 trace 包含 tool/handoff/guardrail 关键 span。

建议命令（按当前项目形态）：

```bash
cd main/backend
python3 -m pytest -q tests/unit/test_skill_runtime_unittest.py
python3 -m pytest -q tests/unit/test_agent_batch_loop_unittest.py
python3 -m pytest -q tests/integration/test_agent_batch_workflow_closure_unittest.py
```

---

## 8. 风险与缓解

1. 风险：技能壳过薄，仍有隐式直连。  
缓解：CI 检查 `app/api` 与 `agent runtime` 的禁用直连清单。

2. 风险：schema 漂移导致模型误调用。  
缓解：manifest version + contract tests + golden examples。

3. 风险：权限配置分散。  
缓解：集中式权限注册与审计报表。

4. 风险：迁移期双路径行为不一致。  
缓解：shadow run + 差异阈值告警 + 可回滚开关。

---

## 9. 本文与当前专题关系

本文件作为 `2026-03-09-agent-symbolic-batch-search-architecture` 的延伸方案，重点回答：

1. 如何把“agent 可调用能力”从局部改造提升为后端全域能力层。
2. 如何用外部成熟实践反推项目内可执行门禁与迁移波次。

---

## 10. Implementation Status（2026-03-11）

已落地（Phase 1 首批）：

1. 新增 dispatch skills：
   - `agent_batch.dispatch.market_collect`
   - `agent_batch.dispatch.source_library_item`
2. `agent_batch` 提交/重试链路已通过 `invoke_skill` 调度，不再直接调用 task function。
3. `ingest`、`source_library`、`process.retry` 的异步路径已切换为技能调度。
4. `skill_runtime` 启动时注册上述 dispatch skills，并纳入 agent_batch task manifest 同步机制。
