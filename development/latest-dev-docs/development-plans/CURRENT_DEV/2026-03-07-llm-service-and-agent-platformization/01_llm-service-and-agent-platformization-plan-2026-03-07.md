# LLM Service and Agent Platformization Plan (2026-03-07)

> 日期：2026-03-07
> 范围：多 LLM 服务接入、统一模型服务层、agent 能力、长期智能框架接入策略
> 状态：主题主计划文档，用于冻结模型平台层的问题定义、边界和第一阶段建议

## 1. 背景

抽象规划对模型层提出的要求已经超过“多接几个模型”的水平：

- 接入更多 LLM 服务以支撑更多自主化功能。
- 让 agent 成为平台能力增强的一部分。
- 评估类似 openclaw 的长期智能框架接入。

这说明模型能力在平台中的角色正在变化：

- 不是单个业务页面内的辅助按钮
- 而是逐步成为跨写作、图谱、采集、工作流的底层能力层

因此，本主题不是“LLM 接入清单”，而是模型平台层的主计划。

## 2. 当前基线

### 2.1 writing / report 模型能力基线

当前仓库已经存在多条与模型能力直接相关的业务链：

- writing 动作与 trace：
  - `main/backend/app/services/writing/llm_action_service.py`
- 模板与写作 action 配套：
  - `main/backend/app/services/writing/template_service.py`
  - `main/backend/app/services/writing/search_suggest_service.py`
- 报告生成与来源补齐：
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/services/llm_report_generator.py`
  - `main/backend/app/services/llm_report_source_enrichment.py`
- 模型配置 API：
  - `main/backend/app/api/llm_config.py`
  - `main/backend/app/services/llm/config_service.py`
  - `main/backend/app/services/llm/config_loader.py`

这说明当前平台已经不是“没有模型层”，而是有多个业务已直接使用模型能力。

### 2.2 更底层的模型与工作流基线

当前后端还存在一套更底层的模型和工作流能力：

- `main/backend/app/services/llm/*`
- `main/backend/app/services/workflow_graph/*`
- `main/frontend-modern/src/pages/LlmDesignerPage.tsx`

从这些路径可以看出，平台已经在尝试：

- provider / model / prompt 模型化
- LLM 调用节点化
- workflow graph 编译与执行

这意味着模型平台化不是空想，而是已有零散基础但缺少统一产品边界。

### 2.3 外部参考基线

本地 OSS 参考池已经包含：

- `reference-pool/oss/silverbullet-ai/*`
- `reference-pool/oss/dify/*`
- `reference-pool/oss/langflow/*`

这些不是让平台整仓迁移，而是说明：

- 右侧 AI 助手
- provider / capability 抽象
- typed flow / agentic workflow

这些能力在外部已有成熟参考，不应在本主题里闭门造车。

## 3. 核心问题定义

### 3.1 当前模型能力是“已接入”，不是“已平台化”

现在的模型能力更多是嵌在具体业务里：

- writing action 用模型
- llm_report 用模型
- LlmDesignerPage 可组装 LLM 节点

但平台仍缺少统一回答：

- provider 如何治理
- capability 如何表达
- route 如何决策
- trace 如何贯穿

### 3.2 agent 的位置不清

“agent 平台化”可能至少指三种不同东西：

- 任务编排层
- UI 助手层
- 业务能力包装层

如果不先冻结 agent 在平台中的位置，这个主题很容易无限膨胀。

### 3.3 长期框架接入容易脱离仓库现实

openclaw 类长期框架是合理方向，但如果在当前阶段把它写成主线，很容易偏离仓库已有：

- writing action
- llm report
- workflow graph

这些现实基础。

### 3.4 模型层与业务层边界不足

当前多个业务都直接消费模型能力，如果没有一个统一平台层，后续风险会集中在：

- provider 配置分散
- prompt 语义漂移
- trace 与审计不一致
- 业务自己复制模型调用逻辑

## 4. 目标

本主题第一阶段要达成的目标是：

1. 定义统一模型服务层的最小抽象。
2. 定义 agent 在平台中的职责位置。
3. 定义模型平台与 writing、graph、crawler 等业务主题的边界。
4. 给长期智能框架接入一个阶段性策略，而不是空泛远景。

## 5. 范围

本主题当前纳入范围：

- provider / model / capability / route / trace 抽象
- 模型服务配置与调用边界
- 业务 action 与 agent 能力的关系
- workflow graph 与模型平台的关系
- 长期框架的阶段性接入策略

### 5.1 第一阶段优先范围

第一阶段建议只冻结以下五项：

1. 模型服务层统一抽象
2. provider 配置与路由边界
3. trace 与审计口径
4. agent 角色分层
5. 长期框架接入阶段策略

## 6. 具体需求清单

本主题本轮必须明确以下具体需求，后续子 agent 不能把这些要求再弱化成抽象口号。

### 6.1 统一模型服务抽象

必须给出一套可落到当前仓库的统一抽象，至少覆盖：

- `provider`
  - 供应商标识、接入配置、可用状态
- `model`
  - 模型名称、上下文能力、默认用途
- `capability`
  - 写作改写、结构摘要、提取、检索增强、agent step 等能力类型
- `route`
  - 某个业务动作如何选到 provider/model
- `trace`
  - 请求链路、调用来源、业务上下文、失败原因、结果引用

这套抽象必须能够同时承接：

- writing action
- llm report
- workflow graph 中的 llm_call

而不是只适配其中一个业务点。

### 6.2 统一配置与调用边界

必须明确：

- 模型配置由哪一层统一提供
- 业务方能传哪些参数，不能传哪些参数
- provider/model 的默认值、覆盖规则、项目级配置边界
- 新业务接入模型层时的最小调用合同

当前仓库已有：

- `main/backend/app/api/llm_config.py`
- `main/backend/app/services/llm/config_service.py`
- `main/backend/app/services/llm/config_loader.py`

所以本主题不能再把“配置层”写成未来想象，必须基于现有配置入口继续抽象。

### 6.3 统一审计、失败反馈与 trace 要求

必须明确：

- 哪些业务调用必须带 `trace_id`
- 错误如何标准化返回
- 审计记录写到什么层
- 业务方能看到哪些执行元信息

当前 `main/backend/app/services/writing/llm_action_service.py` 已经使用 `trace_id`，说明 trace 不是可选增强项，而是平台级基本要求。

### 6.4 业务能力接入点要求

必须说明模型平台首先服务哪些平台环节，不能只写“给全平台赋能”。

第一批必须明确的接入点至少应包括：

- 写作工作台：
  - 改写、续写、提纲生成、证据压缩
- 图谱到报告：
  - 图谱摘要、结构化 handoff
- crawler / ingest 增强：
  - 抓取后筛选、结构化、摘要增强
- workflow graph：
  - `llm_call` 节点的统一 provider/capability/trace 机制

### 6.5 agent 能力边界

必须先定义 agent 先服务哪些环节，至少要回答：

- agent 是优先做用户可见助手，还是优先做后台编排器
- agent 是否允许直接执行跨业务动作，还是只负责调用平台能力
- agent 的上下文来源、权限边界、审计要求是什么

本轮禁止把 agent 写成“全面智能化平台”这种无法执行的表述。

### 6.6 长期框架接入策略

必须明确 openclaw 类长期框架的阶段策略：

- 当前阶段先不作为平台主路径
- 先观察哪些已有平台动作足够稳定，值得抽成长期 agent runtime
- 何时才进入深度集成评估

也就是说，本轮需要的是“接入策略”，不是“直接承诺落地”。

### 6.7 最低平台化要求

本轮至少要把以下基础要求写清：

- 统一配置入口
- 统一调用入口或 facade
- 统一 trace / audit 规则
- 统一失败反馈口径
- 新业务接入的最小准入规范

## 7. 非目标

本主题当前不纳入：

- 所有业务工作流的具体实现方案
- 完整 autonomous agent 平台承诺
- 固定全部供应商矩阵
- 替代 writing、graph、crawler 主题去定义业务 action
- 一次性重写现有 llm report 或 workflow graph 全部实现

## 8. 关键能力拆解

### 7.1 Model Service Layer

第一阶段必须至少统一以下概念：

- provider
- model
- capability
- route
- trace

当前仓库的 `llm_action_service.py` 已经说明 trace 是真实需求，而不是后补字段。

### 7.2 Business Action Layer

不同业务主题需要的模型能力并不相同：

- writing 需要改写、续写、证据压缩
- graph 需要结构摘要、报告 handoff
- crawler / ingest 可能需要筛选、摘要、结构化增强

本主题必须定义：

- 哪些是平台级 action 类型
- 哪些是业务特有 action

### 7.3 Agent Layer

agent 不应被泛化成“更聪明的模型调用”。平台至少要区分：

- 对用户可见的助手
- 对系统可见的编排器
- 对业务可见的能力包装器

第一阶段不必三者都做重，但必须写清主次。

### 7.4 Long-Horizon Framework Strategy

openclaw 类框架应被视为：

- 中长期能力方向
- 不是当前第一阶段交付目标

计划文档需要写清：

- 先接什么
- 何时评估
- 什么条件下才值得深度接入

## 9. 分阶段计划

### Phase 1: Freeze Service Abstraction and Trace Contract

本阶段目标是先把“模型平台最小可用骨架”冻住。

必须完成：

- 冻结 `provider/model/capability/route/trace` 五元抽象
- 明确 `llm_config`、`llm service`、业务调用之间的边界
- 明确写作、报告、workflow graph 三条已有调用路径如何归入统一模型服务层
- 定义统一错误反馈与审计口径

本阶段不做：

- 不追求多业务全量接入
- 不推动重型 agent runtime
- 不承诺长期框架深度集成

阶段验收：

- 至少能用同一套抽象解释 writing action 和 llm report 两条链
- 至少能定义一条统一 trace 链路
- 至少能给出一条新业务接入模型层的最小合同

### Phase 2: Add Agent Capability Packaging and Business Entry Points

本阶段目标是把“模型服务层”提升为“可被业务稳定消费的能力层”，并引入第一批 agent 能力封装。

必须完成：

- 明确 agent 首个落点：
  - 用户可见助手
  - 后台编排器
  - 业务能力包装器
  其中至少选择一个主路径
- 定义 writing / graph / ingest 三类业务的接入点差异
- 定义 agent 如何消费平台能力，而不是绕开平台直接堆逻辑

本阶段不做：

- 不把所有业务都接成 agent-first
- 不在没有权限/审计前提下允许 agent 任意跨域执行

阶段验收：

- 至少定义一个 agent 参与的真实业务样例
- 至少定义一个平台级 action 如何被业务和 agent 共同消费
- 至少定义一条 agent 调用的审计和失败反馈要求

### Phase 3: Evaluate Long-Horizon Framework Integration and Complex Orchestration

本阶段目标是建立长期框架接入和复杂 orchestration 的评估条件，而不是为了概念先进性强行落地。

必须完成：

- 给出 openclaw 类长期框架的适配条件
- 明确哪些已有平台动作已经稳定到可进入长期编排
- 评估是否需要独立 runtime / scheduler / memory / tool registry 体系

本阶段不做：

- 不在基础抽象未稳定前硬上复杂框架
- 不让长期框架直接取代现有业务模型调用链

阶段验收：

- 至少形成一个长期框架接入评估清单
- 至少说明一条复杂 orchestration 与现有 workflow graph 的关系

## 10. 依赖与边界

### 10.1 与 `writing-workbench-evolution` 的边界

- writing 主题定义写作动作和主工作流
- 本主题定义这些动作如何由统一模型平台承载

### 10.2 与 `graph-editing-and-reporting` 的边界

- graph 主题定义图谱到报告的业务需求
- 本主题定义模型层如何接这些需求

### 10.3 与 `crawler-source-expansion` / `ingest-digestion-and-long-cycle-automation` 的边界

- 业务主题定义何处需要模型增强
- 本主题定义模型服务层如何统一提供能力

## 11. 第一阶段建议

第一阶段不建议直接冲“agent 平台化”大词，而应先按以下顺序推进：

1. 统一模型服务抽象
2. 统一 trace 与审计口径
3. 统一业务 action 接入边界
4. 再讨论 agent 分层

如果第一步都不清楚，agent 只会成为新一层耦合。

## 12. 风险与待确认问题

### 12.1 风险

- 如果不先统一抽象，业务主题会继续各自封装模型调用。
- 如果 agent 定义不清，UI 助手、workflow graph、自动任务三者会混在一起。
- 如果过早推动长期框架接入，会偏离当前仓库现实能力。

### 12.2 待确认问题

- provider 选择是配置驱动还是策略驱动。
- trace 是否统一进入现有 responses/meta 体系。
- workflow graph 是否视为模型平台的一部分，还是上层消费者。
- agent 首个落点是用户可见助手还是后台编排。

## 13. 最小验证

- 至少定义两个不同业务场景的统一模型能力抽象。
- 至少定义一个带 trace 的 action 链路样例。
- 至少定义一个 agent 参与平台流程但不越权替代业务主题的最小样例。
