# Graph Editing and Reporting Plan (2026-03-07)

> 日期：2026-03-07
> 范围：图谱编辑、关系同步、结构化任务优化、图谱到报告/写作的结果消费
> 状态：主题主计划文档，用于冻结具体需求、阶段计划与实现边界

## 1. 背景

当前平台已经有图谱页面、图谱草稿编辑能力和图谱结果导出能力，但这套能力仍然更接近“可视化分析页 + 模板式编辑器”，还不是稳定的业务图谱工作流。

抽象规划总纲对本主题提出了更具体的要求：

- 必须定义节点/关系创建、修改、删除的最小合同。
- 必须定义草稿、提交、同步、失败反馈、冲突处理的基本机制。
- 必须定义最小审计/回滚需求。
- 必须定义图谱结果进入写作/报告前的中间表示。
- 必须说明图谱编辑对象与图模板/自动生成图之间的边界。

因此，本主题不是“增强图谱页面交互”这么简单，而是要把图谱从结果展示层升级为：

- 可编辑的结构化对象；
- 可同步的业务对象；
- 可被写作/报告链路消费的中间产物。

## 2. 当前基线

### 2.1 前端基线

图谱前端的核心入口已经存在：

- `main/frontend-modern/src/pages/GraphPage.tsx`
- `main/frontend-modern/src/pages/graph/hooks/useGraphDraft.ts`

当前能确认的能力包括：

- `GraphPage.tsx` 已经包含 `editMode`、`graphEditStatus`、模板/版本列表、草稿节点与边的编辑 UI。
- `useGraphDraft.ts` 已经具备：
  - 克隆当前 nodes / edges 进入 draft
  - `createNode`
  - `updateNodeByKey`
  - `removeNodesByKeys`
  - `createEdgeByNodeKeys`
  - `removeEdgeAt`
  - `resetDraft`
  - `markSaved`
- `GraphPage.tsx` 还存在模板与版本相关操作：
  - 创建模板
  - 重命名模板
  - 删除模板
  - 保存版本
  - 加载版本
  - 激活版本

结论：

- 前端并不是完全没有编辑能力。
- 但当前能力更像“图模板 / 图 DSL 编辑器”。
- 是否已经适合承接“真实业务图谱编辑合同”，目前仍未冻结。

### 2.2 后端基线

当前后端已有图谱构建、投影、导出和持久化基础：

- 图谱构建与投影：
  - `main/backend/app/services/graph/builder.py`
  - `main/backend/app/services/graph/projection.py`
  - `main/backend/app/services/graph/doc_types.py`
- 图谱导出与校验：
  - `main/backend/app/services/graph/exporter.py`
- 图谱持久化：
  - `main/backend/app/services/graph/persistence/graph_node_reader.py`
  - `main/backend/app/services/graph/persistence/graph_node_writer.py`
  - `main/backend/app/services/graph/persistence/graph_node_alias_resolver.py`
- 图谱 API 主路径：
  - `main/backend/app/api/admin.py`

当前后端现实说明两点：

- 平台已经能稳定读取、投影、导出和持久化图谱节点。
- 但用户级图谱编辑 API 合同并没有以清晰方式暴露出来，至少在现有主路径里还不是显式一等能力。

### 2.3 报告与写作链路基线

当前图谱到报告/写作之间已有若干可复用锚点：

- 报告生成 API：
  - `main/backend/app/api/llm_report.py`
- 报告结构与 gate：
  - `main/backend/app/services/llm_report_generator.py`
- 报告来源补全：
  - `main/backend/app/services/llm_report_source_enrichment.py`
- writing schema 已支持 `source_type = "graph"`：
  - `main/backend/app/contracts/schemas/writing.py`
  - `main/backend/app/services/writing/keyword_card_service.py`

这说明“图谱作为来源”已经有基础，但还没有形成“编辑后的图谱对象 -> 标准 evidence pack -> 写作/报告消费”的稳定路径。

## 3. 核心问题定义

本主题需要解决的核心问题不是“能否编辑图谱”，而是以下四个结构性问题：

### 3.1 编辑能力存在，但业务合同缺位

前端已经有 draft 能力，后端也有 graph persistence 能力，但两者之间缺少明确的业务合同。当前仍不清楚：

- 允许用户编辑的图谱对象到底是什么。
- 哪些字段是业务可编辑字段，哪些字段是系统派生字段。
- 前后端同步的请求/响应语义是什么。

### 3.2 图模板编辑与业务图谱编辑边界不清

当前 `GraphPage.tsx` 的模板和版本操作更像图模板构建能力。若不显式区分，很容易把：

- 模板图谱编辑
- 自动生成图审校
- 真实业务图谱维护

混成一套逻辑，最终导致权限、版本、冲突、回滚都无法设计清楚。

### 3.3 图谱结果缺少统一消费形态

报告或写作链路消费图谱时，不能直接依赖完整前端图对象。当前仍缺少稳定的中间表示，例如：

- 关键节点集
- 关键关系链
- 子图摘要
- 可追溯的 graph evidence pack

### 3.4 图谱主题与知识组织主题天然耦合但职责不同

`typed-knowledge-organization` 负责定义对象层和分类层。
本主题负责定义这些对象如何被编辑、同步、消费。

如果本主题越界去定义完整知识模型，会让两个主题失去独立性。

## 4. 目标

本主题的目标不是一次性实现完整图谱平台，而是先把以下几件事写清楚：

1. 图谱编辑的最小业务合同。
2. 图谱草稿、提交、同步、失败、冲突的基本机制。
3. 图谱结果进入写作/报告前的中间表示。
4. 审计、回滚、版本语义的最低要求。
5. 图模板、自动生成图、业务图谱三类对象之间的边界。

## 5. 具体需求清单

这一节对应总纲中的“各主题需求清单与阶段计划”，必须作为后续实现和子任务拆解的硬输入。

### 5.1 节点/关系编辑合同

- 必须定义节点创建的最小字段集合。
  - 至少明确 `id`、`type`、`name` 是否必填。
  - 至少明确前端临时节点 id 与后端持久化节点 id 的关系。
- 必须定义关系创建的最小字段集合。
  - 至少明确 `from`、`to`、`relation/predicate` 的输入合同。
  - 至少明确重复边、非法节点引用、空关系的处理方式。
- 必须定义节点修改范围。
  - 哪些字段允许用户直接改。
  - 哪些字段是系统归一化、抽取或映射结果，不允许直接覆盖。
- 必须定义删除语义。
  - 删除节点时关联边如何联动处理。
  - 删除是否立即写后端，还是先停留在 draft 中。

### 5.2 草稿、提交、同步、失败反馈、冲突处理

- 必须定义草稿对象的生命周期。
  - 何时创建 draft。
  - 何时 reset。
  - 何时 mark saved。
- 必须定义提交与同步反馈。
  - 成功时返回什么。
  - 校验失败时返回什么。
  - 冲突时返回什么。
- 必须定义最小冲突处理机制。
  - 是否使用 revision / version token。
  - 是否允许覆盖写。
  - 是否需要用户重新拉取最新状态。
- 必须定义失败反馈最小要求。
  - 前端不能只显示通用失败 toast。
  - 至少要区分参数错误、对象缺失、版本冲突、权限拒绝。

### 5.3 审计、回滚、版本需求

- 必须定义最小审计记录。
  - 谁修改了什么。
  - 修改对象是什么。
  - 修改时间与项目归属是什么。
- 必须定义最小回滚需求。
  - 回滚整个提交，还是回滚单节点/单关系。
  - 是否支持恢复到某个版本快照。
- 必须定义版本语义。
  - 当前模板/版本操作是否沿用为业务图谱版本体系。
  - 若不沿用，必须明确两套版本体系的关系。

### 5.4 图谱结果进入写作/报告的中间表示

- 必须定义 graph evidence pack 或同等中间表示。
  - 不能只写“把图谱送给 LLM”。
  - 至少要明确由哪些字段构成。
- 必须定义最小消费对象。
  - 是节点集合。
  - 是关系链。
  - 是子图摘要。
  - 还是经过主题化整理的证据包。
- 必须定义图谱结果进入消费链路的入口。
  - 由图谱页显式触发。
  - 由写作页拉取选中的图谱结果。
  - 或由报告生成器自动补图谱证据。

### 5.5 图模板 / 自动生成图 / 业务图谱边界

- 必须说明图谱编辑对象与图模板的边界。
- 必须说明图谱编辑对象与自动抽取生成图的边界。
- 必须说明人工编辑后的图谱是否回流原始抽取层。
- 必须说明哪些对象允许直接写后端，哪些对象只能作为草稿或模板存在。

## 6. 范围

本主题当前纳入范围：

- 节点/关系创建、删除、修改的业务语义。
- 前端 graph draft 与后端同步之间的合同。
- 审计、回滚、版本语义的最低要求。
- 图谱结果进入写作/报告链路的中间表示。
- 图谱结构化任务优化与人工编辑之间的衔接方式。

## 7. 非目标

本主题当前不纳入：

- 重写图布局、渲染引擎、2D/3D renderer。
- 在本主题中定义完整类型节点主模型。
- 直接重写整套写作工作台方案。
- 直接承载完整模型平台方案。
- 将 workflow graph DSL 体系等同于业务知识图谱。

## 8. 关键能力拆解

### 8.1 Graph Draft Layer

职责：

- 承接前端节点/关系的局部修改。
- 保持未提交状态和已发布状态分离。
- 为 reset、compare、submit 提供最小状态基础。

现实锚点：

- `main/frontend-modern/src/pages/graph/hooks/useGraphDraft.ts`

### 8.2 Graph Sync Contract

职责：

- 把前端 draft 映射为后端可接受的业务编辑请求。
- 提供成功、失败、冲突、版本不一致等反馈。

现实锚点：

- `main/backend/app/services/graph/persistence/*`
- `main/backend/app/api/admin.py`

### 8.3 Graph Audit / Rollback Layer

职责：

- 将图谱编辑从“可改”提升为“可治理”。
- 保证提交后的修改可追踪、可恢复。

现实问题：

- 当前模板版本能力不自动等于业务图谱审计能力。

### 8.4 Graph Evidence Pack and Handoff

职责：

- 将图谱结果转成写作/报告能消费的标准对象。

现实锚点：

- `main/backend/app/api/llm_report.py`
- `main/backend/app/services/llm_report_source_enrichment.py`
- `main/backend/app/contracts/schemas/writing.py`

## 9. 分阶段计划

### Phase 1: Freeze Edit Contract and Consumption Shape

目标：

- 冻结编辑合同。
- 冻结 graph draft 与服务端同步边界。
- 冻结 graph evidence pack 的最小形态。

本阶段必须回答：

- 节点/关系最小输入输出合同是什么。
- 业务图谱、模板图谱、自动生成图三者的边界是什么。
- draft -> submit -> feedback 的最小链路是什么。
- 图谱结果进入写作/报告的最小 payload 是什么。

本阶段产出应包括：

- 编辑合同说明
- 同步状态流
- 最小 evidence pack 定义
- 第一条 graph-to-report 消费路径

### Phase 2: Add Audit, Rollback, and Version Semantics

目标：

- 在编辑合同稳定后，补上图谱治理能力。

本阶段必须回答：

- revision / version token 是否存在。
- 审计记录需要覆盖哪些维度。
- 回滚粒度是提交级还是对象级。
- 模板版本与业务图版本是否复用同一语义。

本阶段产出应包括：

- 最小审计模型
- 最小回滚策略
- 冲突反馈策略
- 版本语义说明

### Phase 3: Optimize Graph Tasks and Strengthen Report Linkage

目标：

- 在前两阶段合同稳定后，再补图谱结构化任务优化和更强的报告联动。

本阶段必须回答：

- 自动生成图如何与人工编辑结果协同。
- 图谱结构化任务优化后如何回流。
- 图谱证据如何更稳定地进入报告 gate 和写作复用链路。

本阶段产出应包括：

- 图谱任务优化与人工编辑协同策略
- 更强的 graph-to-report 链路
- 图谱结果在写作/报告/知识组织中的复用策略

## 10. 依赖与边界

### 10.1 与 `typed-knowledge-organization` 的边界

- 该主题定义“对象结构是什么”。
- 本主题定义“这些对象如何在图谱中被编辑、同步、消费”。

本主题不得替代知识组织主题去定义完整类型体系。

### 10.2 与 `writing-workbench-evolution` 的边界

- 写作主题负责写作主链。
- 本主题只负责定义图谱如何成为写作链路的结构化输入。

### 10.3 与 `llm-service-and-agent-platformization` 的边界

- 模型平台主题负责 provider、route、trace、agent orchestration。
- 本主题只负责 graph evidence 的形态与交接边界。

## 11. 第一阶段建议

第一阶段不要把目标定成“完整业务协作图谱平台”，而应先建立一条受控闭环：

1. 先限定一种图谱对象进入编辑合同。
2. 先打通 graph draft -> submit -> feedback。
3. 先定义 graph evidence pack。
4. 先打通一条 graph-to-report 或 graph-to-writing 的最小消费链路。

第一阶段不建议直接尝试：

- 多人协作图谱编辑；
- 全量线上业务图谱开放编辑；
- 复杂审批流；
- 全自动图谱任务优化闭环。

## 12. 风险与待确认问题

### 12.1 风险

- 当前前端编辑能力可能领先于后端业务合同，形成“看起来能改，实际不可持久化”的错位。
- 图模板编辑能力如果与业务图谱编辑混用，会导致版本和权限语义失真。
- 如果没有稳定 evidence pack，图谱结果进入写作/报告仍会退化成 ad-hoc prompt 拼接。
- 图谱主题与知识组织主题交叉很深，边界不清会导致两个主题互相吞并。

### 12.2 待确认问题

- 第一阶段支持的编辑对象到底是哪一类图谱。
- 是否需要显式 revision / version token。
- 图谱编辑是否需要项目级权限隔离。
- 图谱结果传给报告时，是快照、子图、关系链还是任务化摘要对象。

## 13. 最小验证

后续进入实现前，至少要能支撑以下验证：

1. 编辑闭环验证
   - 能描述一条 `edit node/edge -> submit -> feedback` 的完整业务链路。

2. 同步合同验证
   - 能区分成功、校验失败、版本冲突三种返回语义。

3. 消费链路验证
   - 能定义一条 `graph selection -> evidence pack -> writing/report input` 的最小传递路径。

4. 边界验证
   - 能明确指出图模板、自动生成图、业务图谱三类对象的边界。
