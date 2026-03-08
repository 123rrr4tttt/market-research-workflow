# Crawler Source Expansion Plan (2026-03-07)

> 日期：2026-03-07
> 范围：现代 crawler 接入、定向信息源扩展、来源分层、质量治理
> 状态：主题主计划文档，用于冻结来源扩张层的问题定义、边界和第一阶段建议

## 1. 背景

抽象规划对来源层提出了三个清晰要求：

- 扩展更多现代基于 LLM 的 crawler 项目。
- 系统性补齐学术、商业研报、商业信息、新闻平台等定向来源。
- 解决当前来源固定、离散、质量参差不齐的问题。

这说明来源扩张不能再被理解为“多加几个 adapter”，而需要被提升为来源生态建设主题。

## 2. 当前基线

### 2.1 crawler 与来源管理基线

当前仓库已存在较完整的 crawler/source library 基础：

- 前端管理入口：
  - `main/frontend-modern/src/pages/CrawlerManagePage.tsx`
- crawler API：
  - `main/backend/app/api/crawler.py`
- source library API：
  - `main/backend/app/api/source_library.py`
- 来源执行与同步：
  - `main/backend/app/services/source_library/*`
- crawler provider / registry / bridge：
  - `main/backend/app/services/crawlers/*`
  - `main/backend/app/services/crawlers/providers/*`
  - `main/backend/app/services/crawlers_mgmt/*`

这说明来源层已经不是空白，而是已经有运行骨架、provider 机制和管理面板。

### 2.2 collect runtime 与 discovery 基线

当前还存在另外两条与来源相关的重要链路：

- `main/backend/app/services/collect_runtime/*`
- `main/backend/app/services/discovery/*`

它们说明平台已经具备：

- 运行时 collect adapter
- search/deep-search 能力
- 来源发现与结果存储

但这些能力目前分散在 discovery、collect、source library、crawler 几条线上，容易碎片化。

### 2.3 来源质量治理基线

当前仓库已经有若干质量治理锚点：

- `main/backend/app/services/ingest/meaningful_gate.py`
- `main/backend/app/services/resource_pool/llm_validator.py`
- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/discovery/store.py`

说明“质量门禁”并不是零基础，但它目前没有被提炼成来源层统一治理规则。

## 3. 核心问题定义

### 3.1 来源体系缺少统一分层

当前来源能力已存在，但平台还没有统一回答：

- 什么是通用来源
- 什么是定向高价值来源
- 什么是实验性 crawler 能力

没有分层，就无法决定优先级和治理标准。

### 3.2 crawler 接入能力分散

source library、collect runtime、crawler provider、discovery 都能“带来源进平台”，但主入口不统一。结果是：

- 接入边界不清
- 输出格式不稳定
- 后续 ingest 和知识组织难以对齐

### 3.3 来源质量问题仍在下游暴露

抽象规划明确要求解决质量参差不齐的问题。当前平台虽然有门禁，但仍更多在：

- ingest 阶段
- resource pool 校验阶段

暴露问题，而不是在来源层就进行分层治理。

### 3.4 LLM crawler 容易变成“新技术愿望词”

如果不先定义它在平台中的职责，LLM crawler 很容易被写成概念口号，而不是：

- 新型接入器
- 新型抓取策略
- 新型筛选/摘要/结构化增强器

中的哪一种。

## 4. 目标

本主题第一阶段要达成的目标是：

1. 定义平台来源体系的统一分层。
2. 定义新型 crawler / adapter 进入平台的统一边界。
3. 定义来源质量、去重、稳定性评价的最小规则。
4. 定义来源层与 ingest、知识组织、报告之间的交接方式。

## 5. 明确需求清单

根据母文档“各主题需求清单与阶段计划”，本主题在后续细化时必须显式保留以下需求，不能只抽象成能力标题：

1. 必须明确来源类型分层和优先级。
具体要求：
- 至少区分通用来源、定向高价值来源、实验性/增强型来源三层。
- 必须说明学术、商业研报、商业信息、新闻平台分别优先落在哪一层。
- 必须给出优先级判断依据，而不是只列来源名单。

2. 必须定义新型 crawler / adapter 的统一接入边界。
具体要求：
- 必须说明 `source_library`、`collect_runtime`、`crawler provider` 三层各自负责什么。
- 必须给出新增来源进入平台时的最小输入/输出合同。
- 必须说明 LLM crawler 在平台中是新型 provider、adapter，还是增强型抓取策略。

3. 必须定义来源质量、去重、稳定性评估的最小规则。
具体要求：
- 至少覆盖可靠性、可重复抓取性、内容意义密度、去重和来源元数据完整性。
- 必须说明哪些规则在来源层执行，哪些允许下游补充。
- 必须说明质量差的来源是阻断、降级还是打标后放行。

4. 必须定义学术、商业研报、商业信息、新闻等定向来源的引入策略。
具体要求：
- 不能只写“后续补齐”，必须说明哪类来源先引、为什么先引。
- 必须说明高价值高成本来源和高频低信噪来源的不同处理方式。
- 必须说明定向来源是按主题域、项目域，还是全局来源库维护。

5. 必须说明来源扩张与下游 ingest / 知识组织的接口。
具体要求：
- 必须给出来源层输出到 ingest 的最小交接字段或对象语义。
- 必须说明来源元数据如何被后续知识组织和质量分级消费。
- 必须避免把下游消化逻辑重新写进本主题。

## 6. 范围

本主题当前纳入范围：

- 来源类型分层
- crawler/provider/adapter 的主接入边界
- 定向来源优先级
- 来源质量、去重、稳定性治理
- 来源层到 ingest 的最小交接合同

### 5.1 第一阶段优先范围

第一阶段建议只冻结以下五项：

1. 来源分层模型
2. 新型 crawler 接入边界
3. 定向来源优先级
4. 来源质量最小门禁
5. 来源到 ingest 的输出合同

## 7. 非目标

本主题当前不纳入：

- 下游 ingest 消化详细设计
- 知识组织层完整方案
- 多模型平台整体设计
- 具体外部 crawler 项目选型清单定稿
- 全量来源目录一次性列全

## 8. 关键能力拆解

### 7.1 Source Tiering

来源至少应分为三层：

- 通用来源：高覆盖、低定制度
- 定向来源：高价值、主题聚焦
- 实验/增强来源：LLM crawler、探索性入口

计划文档必须说明：

- 每层为什么存在
- 每层如何进入平台
- 每层质量标准是否一致

### 7.2 Adapter and Provider Boundary

当前平台已有多层接入能力，第一阶段必须回答：

- source library adapter 负责什么
- collect runtime adapter 负责什么
- crawler provider 负责什么

否则后续新增来源仍会继续堆在任意层。

### 7.3 Quality Governance

来源质量治理至少应覆盖：

- 可靠性
- 可重复抓取性
- 内容意义密度
- 去重
- 来源元数据完整性

第一阶段不要求最终评分体系，但必须先定义最小门禁。

### 7.4 Directed Source Strategy

学术、商业研报、商业信息、新闻平台并不只是来源类别差异，而是：

- 抓取成本不同
- 更新节奏不同
- 内容密度不同
- 结构化难度不同

主题计划必须写出优先级而不是平铺。

## 9. 阶段计划

### Phase 1：冻结来源分层、统一接入边界、质量口径

本阶段必须完成：

- 冻结来源层分层模型。
- 冻结 `source_library / collect_runtime / crawler provider` 的边界。
- 冻结新增来源接入的最小合同。
- 冻结最小质量门禁与去重口径。

本阶段不追求：

- 一次性接入大量新来源。
- 提前做复杂自动筛选或来源评分系统。

### Phase 2：补高价值定向来源和新型 crawler 接入

本阶段重点：

- 按优先级接入高价值定向来源。
- 补齐一批最值得投入的新型 crawler / adapter。
- 验证不同来源层级下的接入成本和质量差异。

本阶段要避免：

- 没有统一合同就并行接大量来源。
- 把“实验性 crawler”直接提升为默认主链。

### Phase 3：补自动评估、自动筛选和来源策略优化

本阶段重点：

- 引入更强的来源质量自动评估。
- 引入基于策略的筛选、降级或优先级调整。
- 让来源层对下游 ingest / 知识组织提供更稳定的策略化输出。

本阶段前提：

- Phase 1 的分层、合同、门禁已经稳定。
- Phase 2 已验证至少一批高价值来源的接入效果。

## 10. 依赖与边界

### 8.1 与 `ingest-digestion-and-long-cycle-automation` 的边界

- 本主题定义内容如何进入平台
- ingest 主题定义内容进入平台后如何被消化和再分发

### 8.2 与 `llm-service-and-agent-platformization` 的边界

- 本主题定义来源层对模型增强的需求
- 模型平台主题定义 provider、route、agent orchestration

### 8.3 与 `typed-knowledge-organization` 的边界

- 本主题输出来源内容
- 知识组织主题决定这些内容如何被组织和分册

## 11. 第一阶段建议

第一阶段不建议一开始就追求“接入更多来源”，而应先做三件事：

1. 冻结来源分层
2. 冻结接入边界
3. 冻结质量门禁

只有这三件事清楚，后续新增来源才不会继续污染结构。

这一判断与阶段计划一致：Phase 1 的价值不在于来源数量增长，而在于先把来源层做成稳定平台边界。

## 12. 风险与待确认问题

### 10.1 风险

- 如果先接来源、后补治理，会继续积累低质量历史包袱。
- 如果把 LLM crawler 写成主线而不是增强能力，可能偏离当前仓库现实。
- 如果 provider / adapter / runtime 分层不清，后续每加一个来源都会复制逻辑。

### 10.2 待确认问题

- 新型 crawler 应落在 source library 还是 collect runtime 之上。
- 来源质量门禁是否分层执行。
- 定向来源是否按项目域维护独立目录。
- 来源元数据最小集合应包含哪些字段。

## 13. 最小验证

- 至少定义一个新增来源类别的接入样例。
- 至少定义一个来源质量或去重检查点。
- 至少定义一个“来源层 -> ingest 层”的最小交接路径。
