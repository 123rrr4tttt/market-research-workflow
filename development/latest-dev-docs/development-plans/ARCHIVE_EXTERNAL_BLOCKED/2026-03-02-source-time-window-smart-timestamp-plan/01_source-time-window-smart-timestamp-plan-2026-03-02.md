# Source Time-Window Plotting and Smart Timestamp Plan (2026-03-02)

## 1. 目标

为每个信息源（搜索站点）建立统一时间语义与时间窗分析能力，确保：

- 可按源做时间窗绘图（趋势可视化）。
- 文档具备智能时间戳（优先源时间，无则回退采集时间）。
- 查询、排序、统计统一使用同一时间口径，避免前后端不一致。

## 1.1 当前状态声明（2026-03-02）

- 本文档为方案设计文档，当前能力尚未在生产链路完整落地。
- 当前系统仍以既有 ingest 主流程为骨架。
- 新能力采用“新增参数嵌入原流程”的过渡接入方式，不代表已完成模块级彻底解耦。

---

## 2. 概念定义（统一口径）

1. `Source（信息源）`
- 指内容来源站点或域名（例如 `arxiv.org`、`techcrunch.com`）。
- 统计、绘图、质量评估都以 Source 作为主分组维度。

2. `Source Time（源时间）`
- 内容本身的发布时间或更新时间。
- 候选来源包括：`meta` 标签、`json-ld`、RSS/Atom 时间字段、正文日期表达、页面内结构化时间字段。

3. `Ingested At（采集时间）`
- 系统实际抓取并入库该文档的时间。
- 由系统写入，始终可得，作为兜底时间。

4. `Effective Time（智能时间戳）`
- 文档最终用于排序、过滤、聚合的统一时间字段。
- 决策规则：优先 `source_time`；若缺失或不可信则回退 `ingested_at`。

5. `Time Confidence（时间可信度）`
- 标识时间解析可信程度：`high` / `medium` / `low` / `none`。
- 用于排障、解释和后续策略优化。

6. `Time Provenance（时间来源）`
- 记录 `effective_time` 的具体来源，例如：
  - `meta_published_time`
  - `jsonld_datePublished`
  - `feed_pubDate`
  - `body_regex_date`
  - `fallback_ingested_at`

7. `Time Window（时间窗）`
- 查询与分析使用的时间范围，如 `7d`、`30d`、`90d`、自定义起止时间。

8. `Per-Source Time Plot（每源时间窗绘图）`
- 在给定时间窗内，按日/周聚合 Source 数据，展示文档量、源时间命中率、回退比例等。

9. `Noun Vector Group（名词向量组）`
- 将文档中的名词短语（实体/术语/产品名/机构名）编码为向量后聚类形成的语义组。
- 作用：把“同义不同写法”映射到同一语义簇，减少关键词表面差异带来的统计偏差。

10. `Noun Space（名词空间）`
- 由全部名词向量组构成的语义空间。
- 一个文档可命中多个名词向量组；一个名词向量组也可跨多个 Source 出现。

11. `Noun-Space × Domain Collection Density（名词空间×域名采集密度）`
- 在时间窗 `W` 内，针对某个 `domain d` 与某个名词向量组 `g` 的单位时间有效采集量：
- `density(d,g,W) = effective_new_docs(d,g,W) / window_days(W)`
- `effective_new_docs` 仅统计去重且通过质量门禁的新增文档。

12. `Normalized Density（规范化密度）`
- 用于跨域名、跨主题横向比较：
- `norm_density(d,g,W) = density(d,g,W) / baseline_density(g,W_ref)`
- 建议 `baseline_density` 取该名词组在参考窗 `W_ref`（如近90天）全域日均值。

---

## 3. 范围（本次仅计划，不改实现）

包含：

- 时间字段标准化设计（数据模型与决策规则）。
- 时间窗查询与聚合接口契约。
- 前端时间窗滑条与每源绘图的产品定义。
- 历史数据回填与验收标准。

不包含：

- 代码实现与数据库迁移执行。
- 采集策略改写（例如自动绕过重复区策略的上线实现）。

---

## 4. 目标架构

1. 采集写入层
- 每条文档写入时执行 `Timestamp Resolver`：
  - 解析候选源时间；
  - 判定可信度；
  - 生成 `effective_time`。

2. 存储层
- 文档表持久化时间语义字段。
- 聚合层提供按 Source + 时间桶统计能力（可查询时实时聚合，或物化视图/离线表）。

3. API 层
- 所有时间过滤统一按 `effective_time`。
- 输出原始时间语义用于可解释性（`source_time`、`ingested_at`、`time_provenance`）。

4. 前端层
- 统一时间窗滑条（预设 + 自定义）。
- 每源绘图组件消费同一统计 API，避免多口径图表。

## 4.1 解耦实施策略（分阶段）

1. `Phase A（过渡态）`
- 通过新增参数和字段把能力嵌入现有流程，优先保证兼容和可用。

2. `Phase B（半解耦）`
- 抽离 `Timestamp Resolver` 与 `Noun Density Aggregator` 为独立模块。
- 主流程只负责编排与参数透传。

3. `Phase C（完全解耦）`
- 形成标准化服务边界（时间语义服务/密度聚合服务）。
- 旧流程仅保留 adapter，不承载核心计算逻辑。

---

## 5. 数据模型建议

### 5.1 文档级字段（新增/规范化）

- `source_domain` (string, not null)
- `source_time` (datetime, nullable)
- `ingested_at` (datetime, not null, existing)
- `effective_time` (datetime, not null)
- `time_confidence` (enum: high/medium/low/none)
- `time_provenance` (string)
- `time_parse_version` (string, optional)
- `noun_vector_group_ids` (array<string>, optional)
- `noun_extraction_version` (string, optional)

### 5.2 聚合视图字段（建议）

- `source_domain`
- `bucket_date`（按天/周）
- `total_docs`
- `with_source_time_docs`
- `fallback_ingested_docs`
- `source_time_coverage = with_source_time_docs / total_docs`

### 5.3 名词空间密度视图字段（新增建议）

- `source_domain`
- `noun_group_id`
- `bucket_date`
- `effective_new_docs`
- `window_days`
- `density = effective_new_docs / window_days`
- `baseline_density`
- `norm_density = density / baseline_density`
- `dup_ratio`（可选，用于解释高重复区）

---

## 6. 时间决策规则（Timestamp Resolver）

1. 候选抽取
- 从 `meta/json-ld/feed/body/http header` 抽取时间候选集合。

2. 标准化
- 统一转为 UTC 存储；展示层按用户时区转换。

3. 候选打分
- 依据来源类型、格式完整性、是否未来时间、是否明显异常进行打分。

4. 选择
- 取最高分候选作为 `source_time`。
- 若无有效候选，则 `source_time = null`。

5. 回退
- `effective_time = source_time ?? ingested_at`。

6. 记录
- 写入 `time_confidence` 与 `time_provenance` 供审计与排障。

---

## 7. API 契约建议

1. 列表接口（文档查询）
- 入参新增：
  - `time_window`（如 `7d/30d/90d/custom`）
  - `start_time/end_time`（custom 时必填）
  - `source_domains[]`（可选）
- 返回新增：
  - `source_time`
  - `ingested_at`
  - `effective_time`
  - `time_confidence`
  - `time_provenance`

2. 统计接口（每源绘图）
- 入参：
  - `time_window`
  - `bucket=day|week`
  - `metrics=total_docs,source_time_coverage,fallback_ratio`
- 返回：
  - `[{source_domain, bucket_time, total_docs, with_source_time_docs, fallback_ingested_docs, source_time_coverage}]`

3. 名词空间密度接口（新增）
- 入参：
  - `time_window`
  - `bucket=day|week`
  - `source_domains[]`
  - `noun_group_ids[]`（可选，不传则返回 Top-N）
  - `normalize=true|false`
- 返回：
  - `[{source_domain, noun_group_id, bucket_time, effective_new_docs, density, norm_density, dup_ratio}]`

---

## 8. 前端产品定义

1. 时间窗控件
- 预设：`7天 / 30天 / 90天 / 180天`。
- 自定义：起止时间选择器。
- UI 组件形式：滑条 + 日期输入双通道。

2. 每源绘图
- 维度：Source（域名）。
- 指标：
  - 文档总量趋势（主线）。
  - 源时间命中率（次轴或叠层）。
  - 回退占比（可切换）。

2.1 名词空间×域名绘图（新增）
- 维度：`source_domain × noun_group_id`。
- 图形建议：热力图（domain 在 Y 轴、noun group 在 X 轴）+ 时间切片。
- 核心指标：
  - `density`
  - `norm_density`
  - `dup_ratio`（辅助判断是否高重复低信息增益）。

3. 可解释信息
- 悬浮提示显示：`source_time_coverage`、`fallback_count`、样本数。
- 图表与文档列表联动，点击某天桶可下钻文档。
- 名词空间视图悬浮提示补充：`noun_group_label`、`density`、`norm_density`、`effective_new_docs`。

---

## 9. 历史数据回填计划

1. 回填任务
- 扫描历史文档，尝试解析 `source_time`。
- 计算并补齐 `effective_time/time_confidence/time_provenance`。

2. 回填策略
- 分批执行（按时间段或 source_domain 分片）。
- 幂等更新，避免重复污染。

3. 回填产物
- 覆盖率报表：
  - `source_time 命中率`
  - `fallback 率`
  - `按源分布`

---

## 10. 里程碑与验收

### Milestone

1. `M1`：字段与决策规则冻结（Schema + Resolver 设计评审通过）。
2. `M2`：查询/API 契约冻结（前后端联调口径一致）。
3. `M3`：前端时间窗绘图原型验收（每源趋势正确）。
4. `M4`：历史回填与质量报表验收。

### 验收标准

1. 任意文档都具备 `effective_time`。
2. 缺失源时间时可自动回退并可追溯来源。
3. 每源在任意时间窗可绘图，图表与列表数据一致。
4. 能输出按源 `source_time_coverage` 质量看板。
5. 能输出 `source_domain × noun_group_id` 的 `density/norm_density` 看板，并支持时间窗切换。

---

## 11. 风险与控制

1. 风险：源时间解析噪音导致误判。
- 控制：引入可信度分级和异常时间过滤（未来时间、极端历史时间）。

2. 风险：时间口径变更影响既有报表。
- 控制：提供过渡期对照指标（旧口径 vs `effective_time` 口径）。

3. 风险：历史回填性能压力。
- 控制：分片 + 限流 + 可中断续跑。

---

## 12. 后续实施任务（下一文档承接）

后续可基于本计划拆出执行任务单：

1. DDL 与索引迁移清单。
2. Resolver 实现与单元测试矩阵。
3. 统计 API 与前端图表联调清单。
4. 历史回填脚本与验收报表模板。
