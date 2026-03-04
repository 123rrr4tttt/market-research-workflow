# Decoupled Implementation Plan: Linear Independent Ingest Chain Params (2026-03-02)

## 0. 当前落地快照（2026-03-02）

本计划已按“最小优化优先”推进到第一阶段可用形态，当前状态：

1. 已落地（可用）
- Single URL 作为统一入口链路，URL 采集从入口到落地走同一标准化流程。
- 轻度过滤（Light Filter）已前置并参数化，结果字段写入流程结果用于后续决策与可观测。
- 新增关键词记忆双库：
  - `keyword_history`（关键词历史库）
  - `keyword_priors`（关键词先验库）
- 新增关键词 API（统计、历史、先验 upsert、向量化候选输出）。
- 关键词历史已接入 single-url 收尾阶段，且对 `search_expand` 子调用做去重计数保护（避免放大）。

2. 待落地（本计划后续阶段）
- 时间窗滑条与每源时间窗绘图（前端）
- 智能时间戳主流程（优先源时间，缺失回退采集时间）
- `source_domain × noun_group × time_bucket` 密度聚合层与查询端低密度优先调度

## 1. 目标

本计划按“线性独立采集链路参数加入采集中”定义解耦，实现以下目标：

1. 时间语义参数独立：`source_time -> effective_time` 规则作为独立参数段注入链路。
2. 名词空间密度参数独立：`noun_group` 与 `domain × noun_group × time` 统计参数独立维护并注入。
3. 主流程线性化：ingest 按固定阶段顺序执行，每阶段只消费并产出标准参数块。
4. 查询统一口径：所有时间过滤与统计统一使用 `effective_time`。
5. 查询端采集优先级：默认按“低密度窗口优先采集”调度，避免高重复窗口占用预算。
6. 轻度过滤前置：先做低成本高收益过滤，并保留向量化适配字段，后续可直接升级到全局向量化。
7. 关键词记忆解耦：关键词历史与先验作为独立参数源，不反向耦合主 ingest 业务逻辑。

---

## 2. 解耦目标架构（线性参数链路）

### 2.1 线性链路阶段

1. `Stage F: Light Filter Params`
- 输入：`url, title, snippet, source_domain, fetch_meta`。
- 输出参数块：`filter_decision, filter_reason_code, filter_score, keep_for_vectorization`。
- 职责：执行轻量规则过滤（空壳页/中间跳转页/明显低价值页/重复URL壳），并显式标注是否进入后续向量化通道。

2. `Stage A: Time Semantics Params`
- 输入：页面元信息、正文候选时间、`ingested_at`。
- 输出参数块：`source_time/effective_time/time_confidence/time_provenance`。
- 职责：候选抽取、打分、异常过滤、时区归一。

3. `Stage B: Noun Space Params`
- 输入：文档正文与标题。
- 输出参数块：`noun_vector_group_ids`、`noun_extraction_version`。
- 职责：名词抽取、向量编码、语义聚类映射、版本管理。

4. `Stage C: Density Params`
- 输入：文档主表 + noun 关系 + 时间窗口参数。
- 输出参数块：`density/norm_density/dup_ratio/collection_priority_score/recommended_window_rank`。
- 职责：按 `source_domain × noun_group_id × bucket` 统计与规范化，并计算查询端采集优先级。

5. `Stage D: Persist + Query`
- 写入文档字段与 noun 关系，查询时统一读取参数块结果。
- 不在主流程中散落规则分支，避免耦合回流。

6. `Stage K: Keyword Memory Params`（已落地）
- 输入：`query_terms + ingest_result + source_domain + filter_decision`。
- 输出参数块：`keyword_history_delta`、`keyword_prior_signal`、`vector_priority_score`（候选）。
- 职责：维护关键词历史统计、先验权重与向量化候选评分；作为查询端与向量化准备层的独立参数源。

### 2.2 数据流（固定线性顺序）

1. 文档入库时：
- `Stage F -> Stage A -> Stage B -> Stage D -> Stage K`。
- 阶段间仅传参数块，不共享隐式状态。

2. 统计查询时：
- `Stage C -> Query API` 返回每源趋势与名词空间密度。

3. 采集调度时（查询端）
- `Query Planner` 读取 `recommended_window_rank`。
- 在同等预算下优先选择 `norm_density` 较低且 `dup_ratio` 较低的窗口执行采集。

---

## 3. 数据模型与存储拆分

### 3.1 文档主表（documents）

- `id`
- `source_domain`
- `source_time` (nullable)
- `ingested_at`
- `effective_time` (not null)
- `time_confidence`
- `time_provenance`
- `time_parse_version`
- `filter_decision`
- `filter_reason_code`
- `filter_score`
- `keep_for_vectorization`

### 3.2 名词关系表（document_noun_groups）

- `document_id`
- `noun_group_id`
- `noun_extraction_version`
- `score`（可选）

### 3.3 聚合结果层（建议物化视图或聚合表）

- `source_domain`
- `noun_group_id`
- `bucket_time`
- `effective_new_docs`
- `density`
- `baseline_density`
- `norm_density`
- `dup_ratio`

### 3.4 关键词历史库（keyword_history，已落地）

- `keyword`（unique）
- `normalized_keyword`
- `search_count`
- `hit_count`
- `inserted_count`
- `rejected_count`
- `last_status`
- `last_source`
- `last_source_domain`
- `last_filter_decision`
- `first_seen_at`
- `last_seen_at`
- `extra`

### 3.5 关键词先验库（keyword_priors，已落地）

- `keyword`（unique）
- `normalized_keyword`
- `prior_score`
- `confidence`
- `source`
- `enabled`
- `tags`
- `notes`
- `extra`
- `created_at`
- `updated_at`

---

## 4. 接口契约（线性参数化解耦后）

1. `Time Semantics Params`（内部能力接口）
- `POST /internal/time/resolve`
- Request: `source_domain, metadata, content_excerpt, ingested_at`
- Response: `source_time, effective_time, time_confidence, time_provenance, time_parse_version`

2. `Noun Space Params`（内部能力接口）
- `POST /internal/noun/extract-groups`
- Request: `title, content, language`
- Response: `noun_vector_group_ids, noun_extraction_version`

3. `Density Params`（内部/公开统计接口）
- `GET /stats/source-noun-density`
- Params: `time_window, start_time, end_time, bucket, source_domains[], noun_group_ids[], normalize`
- Response: `[{source_domain, noun_group_id, bucket_time, effective_new_docs, density, norm_density, dup_ratio, collection_priority_score, recommended_window_rank}]`

4. `Light Filter Params`（内部能力接口）
- `POST /internal/filter/light`
- Request: `url, title, snippet, source_domain, fetch_meta`
- Response: `filter_decision, filter_reason_code, filter_score, keep_for_vectorization`
- 规则：默认“轻过滤不过度拒绝”，优先拦截高噪音样本，保留后续向量化可用样本。

5. 查询端优先级接口（新增）
- `GET /stats/collection-window-priority`
- Params: `source_domains[], noun_group_ids[], candidate_windows[], prefer_low_density=true, exclude_high_dup=true`
- Response: `[{source_domain, noun_group_id, window, density, norm_density, dup_ratio, collection_priority_score, rank}]`
- 规则：默认 `prefer_low_density=true`，按 `collection_priority_score` 升序（低密度优先）返回。

6. 文档查询接口（公开）
- 必返：`source_time, ingested_at, effective_time, time_confidence, time_provenance, noun_vector_group_ids`

7. `Keyword Memory Params`（已落地接口）
- `GET /keywords/stats`
- `GET /keywords/history`
- `GET /keywords/priors`
- `POST /keywords/priors/upsert`
- `GET /keywords/vectorization/candidates`
- 作用：为后续全局向量化、去重、研究报告提供“关键词历史信号 + 先验信号”的统一入口。

---

## 5. 实施计划（纯解耦路径）

### Phase 1: 线性参数段与契约冻结（D1-D2）

1. 建立四段参数能力目录与接口契约文件（含 Stage F 轻过滤）。
2. 增加契约测试（请求/响应字段、错误码）。
3. 冻结版本号：`time_parse_version`、`noun_extraction_version`。

验收：
- 四段参数能力可独立调用并返回标准结构。
- 当前状态：`Stage F` 与 `Stage K` 已先行落地；`Stage A/B/C` 仍按本计划推进。

### Phase 2: 采集链路线性化切换（D3-D4）

1. Ingest 写入改为“按 Stage F->A->B->D 固定顺序执行参数注入”。
2. 文档写入增加事务一致性（主文档 + noun 关系）。
3. 统计 API 改走 Stage C 参数计算。
4. 查询端调度器接入 `collection-window-priority`，默认开启低密度窗口优先。

验收：
- 主流程代码中不再散落时间/名词规则分支，全部集中在参数段实现。
- 同预算下，采集任务优先落在低密度窗口（非高重复窗口）。
- 轻过滤层对明显噪音样本拦截有效，且不过度伤害后续有效样本。
- 当前状态：single-url 主链路线性化已完成基础版，关键词参数已并入收尾阶段；时间窗密度调度尚未切换为默认策略。

### Phase 3: 回填与一致性校验（D5）

1. 批量回填历史文档的 `effective_time` 与 noun 关系。
2. 生成一致性报告：
- 空 `effective_time` 数量
- 空 noun 关系文档比例
- 新旧统计偏差

验收：
- `effective_time` 覆盖率 100%。
- 关键源的密度曲线与抽样文档一致。

### Phase 4: 灰度发布与切主（D6）

1. 在 `demo_proj` 灰度 24 小时。
2. 观察指标：
- 统计接口 P95
- 解析失败率
- norm_density 波动异常率
3. 通过后切主，保留回滚开关 72 小时。

验收：
- 无阻断级错误，关键指标稳定。

---

## 6. 迁移与回滚策略

1. 迁移顺序
- 先上 Stage F 轻过滤接口 -> 再切线性写入链路 -> 最后切统计读取。

2. 回滚原则
- 任一参数段异常可按阶段回滚，不回滚整个 ingest。
- 回滚优先级：
  - Stage C 回滚（不影响写入）
  - Stage B 回滚（时间语义保留）
  - Stage A 回滚（最终回退 `effective_time=ingested_at`）
  - Stage F 回滚（关闭轻过滤，直接放行到 Stage A）

3. 数据安全
- 所有回填任务幂等，按批次记录 checkpoint，可断点续跑。

---

## 7. 验收门禁

1. 架构门禁
- 主流程只保留线性阶段调度，不含散落规则分支。

2. 功能门禁
- 文档查询均返回完整时间语义与 noun 组字段。
- 查询端在默认配置下启用“低密度窗口优先采集”。

3. 统计门禁
- 每源时间窗图、名词空间密度图可稳定出图。
- 优先级接口可返回窗口排序与打分明细。

4. 质量门禁
- `effective_time` 覆盖率 = 100%。
- `norm_density` 计算成功率 >= 99.5%。
- 低密度窗口采集占比 >= 70%（同批次任务，默认策略）。
- 轻过滤误杀率 <= 3%（抽样人工复核）。
- 轻过滤后有效样本保留率 >= 90%（对照集）。

5. 性能门禁
- 统计接口 P95 <= 1.5s（常用时间窗）。

---

## 8. 任务分配建议（并行）

1. Backend Core
- Stage F/Stage A/Stage B 参数段 + Orchestrator 线性调度切换。

2. Backend Data
- noun 关系表、聚合层、Stage C 参数计算 API。

3. Frontend
- 时间窗滑条、每源趋势图、名词空间热力图。

4. Data/Ops
- 历史回填、质量报表、灰度观测与告警。
- 新增监控：`low_density_window_selection_rate`、`high_dup_window_bypass_rate`。
- 新增监控：`light_filter_reject_rate`、`light_filter_false_positive_rate`。

---

## 9. 完成定义（DoD）

1. 时间语义、名词空间、密度聚合均实现线性参数段解耦。
2. ingest 主流程只保留线性调度与持久化职责。
3. 对外查询与图表统一使用解耦后服务结果。
4. 查询端默认实现低密度窗口优先采集并可解释排序依据。
5. 轻度过滤层已前置并可平滑适配后续全局向量化。
6. 回填完成、门禁通过、灰度完成并可回滚。
7. 关键词历史库+先验库可稳定产出向量化候选，并可作为后续图谱去重与报告系统的统一上游信号源。
