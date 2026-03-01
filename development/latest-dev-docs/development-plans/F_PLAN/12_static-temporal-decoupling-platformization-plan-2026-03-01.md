# 静态数据与时间数据解耦：来源平台化与分析增强实施计划

- 最后更新：2026-03-01（US/Pacific）
- 适用范围：`main/backend`（source library / collect runtime / resource pool / search / dashboard）
- 目标：在不推翻现有链路的前提下，完成“静态维度”和“时间事实”解耦，提升来源扩展能力与时间分析强度。

## 1. 设计原则（本次重排的硬约束）

1. 静态数据与时间数据分层存储，禁止在同一实体中混放多种语义时间字段。
2. 静态层可频繁复用，时间层可高频写入；二者通过稳定外键或业务键关联。
3. 采集接入优先走 `source_library + collect_runtime`，减少新增爬虫对主业务代码侵入。
4. 先做可观测与质量评分，再扩大来源数量；禁止“只加来源不加治理”。
5. API 层按“静态视图 / 时间视图”拆分返回，避免字段语义混乱。

## 2. 当前问题（针对代码基线）

1. 来源平台化能力不完整：有配置加载、路由、执行，但缺评分、状态机、调度消费。
2. 时间语义不足：当前主要是 `publish_date/created_at/last_search_time`，缺 `event_time/timezone/time_confidence`。
3. 分析能力偏统计：趋势展示有，但归因和时间驱动解释弱。
4. 测试覆盖偏“路由可达”，对来源评分、时间透传、新 adapter 行为覆盖不足。

## 3. 目标架构（解耦后）

### 3.1 静态层（Static Core）
- 载体：`Source`、`SourceLibraryItem`、`ResourcePoolSiteEntry`（静态属性）
- 语义：来源身份、接入配置、能力标签、状态、信誉评分
- 典型字段：
  - `source_key`, `provider`, `kind`, `domain`, `capabilities`
  - `status`（`active/degraded/paused/retired`）
  - `health_score`（0-100）
  - `config_version`, `owner`, `updated_at`

### 3.2 时间层（Temporal Facts）
- 新增事实层（建议）：
  - `source_observation`：来源在某时间窗口的运行/质量快照
  - `document_event_time`：文档事件时间抽取结果（含置信度与时区）
  - `metric_fact_time_series`：按时间窗的指标事实（可与 NumericFact 对齐）
- 典型字段：
  - `event_time`, `captured_at`, `timezone`, `time_confidence`, `time_source`
  - `window_start`, `window_end`, `latency_ms`, `success_rate`, `dup_rate`

### 3.3 API 语义分层
- 静态 API：来源定义、配置、状态管理（不返回高频时间序列）
- 时间 API：趋势、归因、事件演化（只读时间事实）
- 聚合 API：按主题整合静态与时间层，返回统一分析视图

## 4. 重排后的任务计划

## T0（第 1 周，2026-03-01 到 2026-03-07）
目标：先打通“来源扩展平台化”最小闭环（不引入新时间事实表）。

1. 明确静态层边界与来源平台字段（文档 + schema 草案）。
2. 增加最小状态机字段：`status`, `health_score` 到来源核心实体（或扩展表）。
3. 补齐 provider 配置治理清单（去除“有配置未生效”的键项歧义）。
4. 建立来源接入准入规则（能力标签、失败阈值、降级规则）。

验收：
- 来源平台字段与状态机落库可用。
- 不改时间模型也能完成来源接入闭环验证。

## T1（第 2 周，2026-03-08 到 2026-03-14）
目标：完成来源扩展链路标准化与可运营化（继续不做时间事实扩展）。

1. 统一 adapter contract（collect_runtime 为主，ingest adapters 对齐）。
2. 收敛 HTTP 客户端实现（减少双栈差异）。
3. 将 `schedule` 从“存储字段”推进到“可消费调度”（可先最小轮询任务）。
4. 为来源执行链路增加统一观测字段（耗时、错误码、重试次数）。
5. 建立来源评分流水线（`health_score` 更新任务 + 降级/恢复规则）。

验收：
- 新增一个爬虫只需“配置 + adapter 实现”即可接入。
- 同一任务可输出统一运行观测结构。
- 来源可按评分自动降级/恢复。

## T2（第 3-4 周，2026-03-15 到 2026-03-28）
目标：在来源平台稳定后，落地时间维度（与静态层保持解耦）。

1. 定义时间事实标准字段：`event_time/timezone/time_confidence/time_source`。
2. 在 extraction 链路增加时间归一化（相对时间、时区、置信度）。
3. 落地时间事实表写入（文档事件时间 + 来源观测时间）。
4. SearchHistory 从 topic 级升级为 query 级历史（含 provider、延迟、结果数）。
5. 保持旧字段双轨兼容，避免前端与报表回归。

验收：
- `event_time` 覆盖率可统计。
- 时间事实可独立查询，不依赖静态实体字段拼装。

## T3（第 5-6 周，2026-03-29 到 2026-04-11）
目标：分析增强（时间趋势 + 归因）。

1. Dashboard 输出统一结构：`series + contributors + top_drivers + notes`。
2. 增加来源质量指标：`source_diversity/freshness/duplication_loss`。
3. 图谱侧引入时间衰减与影响传播分（先规则版）。
4. 报表增加趋势摘要和归因段，且强制附 `source_ref`。

验收：
- 至少 2 个核心分析页面可解释“何时变化、由谁驱动、证据在哪”。

## 5. 文件级实施建议（第一批）

### 模型与迁移
- `main/backend/app/models/entities.py`
- `main/backend/migrations/versions/*`（新增静态扩展字段与时间事实表）

### 采集与来源平台
- `main/backend/app/services/source_library/*`
- `main/backend/app/services/collect_runtime/*`
- `main/backend/app/services/ingest/adapters/*`
- `main/backend/app/services/http/client.py`

### 时间抽取与检索历史
- `main/backend/app/services/extraction/models.py`
- `main/backend/app/services/extraction/extract.py`
- `main/backend/app/services/search/history.py`
- `main/backend/app/services/search/web.py`

### 分析与展示
- `main/backend/app/api/dashboard.py`
- `main/backend/app/services/graph/builder.py`
- `main/backend/app/services/report.py`

### 测试
- `main/backend/tests/integration/test_ingest_baseline_matrix_unittest.py`
- `main/backend/tests/integration/test_frontend_modern_entry_baseline_unittest.py`
- `main/backend/tests/core_business/test_source_library_core_contract.py`
- 新增：来源评分/时间透传/new adapter 行为测试

## 6. 风险与控制

1. 风险：迁移影响现有链路写入稳定性。  
控制：双轨字段、灰度启用、回滚 SQL 预案。

2. 风险：来源扩展过快导致质量下降。  
控制：先上评分与状态机，再扩来源数量。

3. 风险：时间字段语义不一致造成分析误导。  
控制：统一 `event_time/timezone/time_confidence` 口径与校验。

4. 风险：测试只覆盖 happy path。  
控制：补齐来源评分、时间透传、adapter 异常场景自动化测试。

## 7. 本计划的完成定义（Definition of Done）

1. 静态层与时间层可独立演进，API 字段语义清晰。
2. 新来源接入成本显著下降（配置化 + 统一 contract）。
3. 时间趋势与归因可在 dashboard/report 稳定输出。
4. 关键链路具备可观测、可回归、可回滚能力。
