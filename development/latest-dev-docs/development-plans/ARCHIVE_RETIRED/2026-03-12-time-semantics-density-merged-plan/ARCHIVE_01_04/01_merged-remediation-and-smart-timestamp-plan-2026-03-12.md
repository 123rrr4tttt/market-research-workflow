# 时间语义与密度能力合并改造主计划（2026-03-12）

## 0. 文档定位与合并原则

- 本文档用于合并以下两组计划，不删除原文档，仅形成单一执行入口：
  - `2026-03-02-source-time-window-smart-timestamp-plan`
  - `2026-03-05-time-statistics-remediation-plan`
- 合并策略：
  - 执行主线以 `2026-03-05` 为准（任务可执行、已有落地映射与实测口径）。
  - 架构演进以 `2026-03-02` 为准（`source_time/effective_time/time_confidence` 与解耦阶段）。
- 术语统一：本主计划默认使用 `noun_group_id` 作为语义分组标识。

## 1. 当前状态调查结论（截至 2026-03-12）

1. 已有能力（可作为当前基线）
- 时间统计修复、密度查询与优先级调度在文档与代码层已有明确映射。
- 已有 realcase 测试脚本与 Go/No-Go 相关脚本。
- 执行记录显示 `T01~T10` 完成，`T11/T12` 部分阻塞。

2. 主要问题（需要合并改造）
- 两套文档存在“计划态 vs 已落地态”并存，状态叙述冲突。
- 术语存在并行使用（`prompt_group_id` 与 `noun_group_id`），影响契约与前后端一致性。
- 任务编号体系并存（`A1-A8` 与 `T01-T12`），不利于跟踪与验收。

## 2. 合并后统一目标

1. 统一时间语义
- 所有查询/统计/排序统一基于 `effective_time`。
- `source_time`、`ingested_at`、`time_confidence`、`time_provenance` 作为可解释字段保留。

2. 统一密度维度
- 以 `source_domain × noun_group_id × time_bucket` 作为标准聚合维度。
- 指标统一：`effective_new_docs`、`density`、`baseline_density`、`norm_density`、`dup_ratio`。
- 在单值指标之上增加“时间名词密度云（Density Cloud）”能力，用于检索时避峰采集。

3. 统一执行编排
- 仅保留一套执行任务编号（本文件使用 `T01-T12`）。
- 将 `A1-A8` 作为映射附录，不再作为主追踪 ID。

## 3. 统一术语与字段字典

### 3.1 核心术语

- `source_domain`：来源域名。
- `source_time`：内容源时间（可空）。
- `ingested_at`：采集入库时间（必有）。
- `effective_time`：统一过滤与聚合时间（`source_time` 不可用时回退 `ingested_at`）。
- `noun_group_id`：名词语义组主键（统一命名，不再以 `prompt_group_id` 作为主名）。
- `time_window`：时间窗（`7d/30d/90d/custom`）。
- `time_bucket`：分桶粒度（`day/week/month`）。
- `density_cloud`：同一 `source_domain × noun_group_id` 在时间轴上的密度分布云，包含峰值区、平稳区、低压区与不确定性带。
- `keyword_history_rag`：关键词历史检索增强上下文（历史命中、去重后有效文档、历史窗口表现）。
- `vector_overlap`：候选采集窗口与目标语义向量（noun/rank 向量）的重合度，范围 `[0,1]`。

### 3.2 命名兼容策略

- API 对外层：
  - 新增/主字段统一输出 `noun_group_id`。
  - 兼容期允许接收历史别名参数（如 `prompt_group_ids`），内部归一为 `noun_group_id`。
- 前端层：
  - query key、请求参数、图表维度统一改写为 `noun_group_id`。

## 4. 统一 API 契约（主口径）

### 4.1 密度查询

- `GET /api/v1/stats/prompt-time-density`
- Query：`time_window | start+end`、`bucket`、`source_domains[]`、`noun_group_ids[]`、`normalize`
- Response `data.items[]`：
  - `source_domain`
  - `noun_group_id`
  - `bucket_time`
  - `effective_new_docs`
  - `density`
  - `baseline_density`
  - `norm_density`
  - `dup_ratio`

### 4.1.1 密度云查询（新增主能力）

- `GET /api/v1/stats/prompt-time-density/cloud`
- Query：
  - `keyword`（必填）
  - `time_window | start+end`
  - `bucket`
  - `source_domains[]`
  - `noun_group_ids[]`
  - `smoothing=ema|gaussian|none`（默认 `ema`）
  - `peak_percentile`（默认 `0.85`）
  - `uncertainty=true|false`（默认 `true`）
- Response `data.items[]`：
  - `source_domain`
  - `noun_group_id`
  - `cloud_points[]`: `{bucket_time, density, norm_density, zscore, is_peak, is_valley}`
  - `cloud_summary`: `{p50, p75, p90, peak_ratio, valley_ratio, volatility, recommended_offpeak_windows[]}`
  - `uncertainty_band`（可选）: `{lower, upper, method}`

说明：
- `recommended_offpeak_windows` 为“新检索关键词”默认避峰入口输出。
- 若目标 `noun_group_id` 数据不足，返回 `cold_start_proxy`（近邻组或域基线）与置信度。
- `density_cloud` 生成机制：`keyword_history_rag × time_window`（历史 RAG 命中在时间窗内聚合后建云）。
- `density` 区分两层：
  - `observed_density`：当前窗口“实际有效新增/天”的观测值；
  - `latent_density`：结合失败率/重复率/覆盖率反推得到的潜在信息密度（未知量估计）。

### 4.2 优先级调度

- `GET /api/v1/stats/prompt-time-density/priority`
- Query：`candidate_windows[]`、`prefer_low_density`、`exclude_high_dup`、`source_domains[]`、`noun_group_ids[]`、`avoid_peak=true|false`（默认 `true`）、
  `max_peak_percentile`（默认 `0.85`）、`min_overlap`（默认 `0.35`）、`target_overlap`（默认 `0.55`）、
  `eta`（默认 `0.08`）、`delta_max`（默认 `0.12`）、`tau`（默认 `0.03`）
- Response `data.items[]`：
  - `source_domain`
  - `noun_group_id`
  - `window`
  - `norm_density`
  - `dup_ratio`
  - `peak_pressure_score`
  - `vector_overlap`
  - `offpeak_confidence`
  - `shift_signal`
  - `p_base`
  - `p_new`
  - `kl_to_base`
  - `rank`

调度原则：
- 非“彻底错峰”，而是“可接受重合度约束下避峰”。
- 先满足 `vector_overlap >= min_overlap`，再在可行集合中优先低峰值压力窗口。
- 当 `vector_overlap` 低于 `min_overlap` 时，不进入推荐窗口，即使该窗口是低峰值区。

评分建议（可实现为配置化权重）：
- `latent_density_score = observed_density * (1-dup_ratio)^u * (1-fail_rate)^v * coverage^w`
- `shift_signal = a*peak_pressure_score + b*(1-latent_density_score) + c*(1-vector_overlap) + d*freshness_cost`
- 分布改写（轻避峰，不做硬最小化）：
  - `p_base(window)` 为原始采样分布；
  - `p_new(window) ∝ p_base(window) * exp(-eta * shift_signal(window))`；
  - `|p_new(window)-p_base(window)| <= delta_max`（单窗口偏移上限）；
  - `KL(p_new || p_base) <= tau`（全局改动预算）。
- 其中：
  - `fail_rate` 包含搜索失败、抓取失败、解析失败；
  - `coverage` 表示窗口内可检索样本覆盖度；
  - `vector_overlap` 采用软约束，防止为避峰而牺牲语义相关性。
  - 避峰目标是“分布微调”，不是“去重”；`dup_ratio` 只作为潜在密度估计信号，不等于避峰动作。

默认参数（按论文与库实现先验）：
- `eta=0.08`：轻度改分布起点，避免新策略抖动。
- `delta_max=0.12`：单窗口概率改写上限 12%。
- `tau=0.03`：全局 KL 预算上限，超限则回退到 `p_base`。
- `explore_rate=0.08`：与轻避峰并行的小流量探索。

在线策略伪代码（V1）：
```text
input: candidate_windows, p_base, overlap, peak_pressure, latent_density
feasible = {w | overlap(w) >= min_overlap}
if feasible is empty: return cold_start_proxy
for w in feasible:
  shift_signal(w) = a*peak_pressure + b*(1-latent_density) + c*(1-overlap) + d*freshness_cost
  raw(w) = p_base(w) * exp(-eta*shift_signal(w))
p_new = normalize(raw)
p_new = clip_per_window(p_new, p_base, delta_max)
if KL(p_new || p_base) > tau: p_new = project_to_kl_budget(p_new, p_base, tau)
return sample_or_rank_by(p_new)
```

论文到设计映射（本轮定稿）：
- TRPO/CPO：提供“策略更新受 KL/约束限制”的设计依据，避免一次改分布过猛。
- OBP/DRos/Switch-DR：提供离线反事实评估协议，验证“轻避峰”是否真实提升收益而非噪声。
- ULTRA/DualIPW/MULTR：提供偏置与长尾稳健训练侧参考，减少冷启动与尾部词抖动。

`vector_overlap` 的工程定义（必须固定一版）：
- `O1`（单向量）：`cos(e(query), e(window_centroid))`
- `O2`（多向量 late interaction）：`maxsim(E_query, E_window_docs)`
- `O3`（任务条件化）：`cos(e(noun_group_id), e(window_repr_task))`
- 首版建议：在线服务用 `O1`，离线评估同时记录 `O2`，待一致性稳定后再升级线上定义。

`window` 语义表示首版口径：
- `window_centroid`：窗口内去重后有效文档 embedding 的均值；
- `window_repr_task`：窗口内命中 `noun_group_id` 的代表文档集合向量聚合；
- 明确版本字段：`window_repr_version`，避免特征漂移不可追溯。

### 4.3 错误契约

- 非法日期、非法 bucket、非法窗口参数统一返回确定性 `4xx`，禁止 silent fallback。
- 错误码集合：`INVALID_INPUT`、`CONTRACT_VIOLATION`、`UPSTREAM_ERROR`（兼容已有 `INVALID_DATE_PARAM` 时保留映射）。

## 5. 执行路线（主线 + 演进）

### 5.1 Phase R（Remediation，短期）

- 目标：巩固当前已落地能力并补齐 `T11/T12`。
- 任务：
  - T11 前后端快照对账流水线化。
  - T12 Go/No-Go 模板接入真实 perf 指标。
- 验收：
  - 核心 realcase 持续通过。
  - API/UI 抽样对账零差异（允许显示层四舍五入）。

### 5.2 Phase S（Semantics，过渡）

- 目标：完成 `noun_group_id` 命名归一与参数兼容层。
- 任务：
  - API 入参兼容别名，响应主字段统一。
  - 前端 modern 与 legacy 查询参数统一。
- 验收：
  - 新旧参数均可用，日志可观测别名使用率。

### 5.3 Phase C（Cloud，避峰能力）

- 目标：从“单值密度”升级为“可决策密度云”，服务新关键词避峰采集。
- 任务：
  - 增加 `prompt-time-density/cloud` 查询与峰谷识别。
  - 调度器接入 `avoid_peak`、`max_peak_percentile`、`min_overlap/target_overlap` 策略。
  - 增加 `latent_density` 反推模块，接入 `fail_rate/dup_ratio/coverage`。
  - 新增数据契约实体：`window_density_stats`、`window_collection_feedback`、`window_embedding_profile`、`noun_group_overlap_cache`、`shift_experiment_log`、`policy_decision_log`。
  - 新增离线反事实评估：`IPS/DR/Switch-DR/SNIPS` 基线与回归报告。
  - 新关键词冷启动时输出 `cold_start_proxy` + 置信度，避免盲目高峰采集。
- 验收：
  - 随机新关键词样本下，避峰策略命中率达到预设阈值。
  - `vector_overlap` 达标前提下，峰值窗口占比下降（而非强制清零）。
  - `latent_density` 与后续窗口真实增益（新增有效文档）呈稳定正相关。
  - 同预算下，重复率与无效采集占比下降。
  - 新增分布门禁：`KL(p_new||p_base)` P95 不超过 `tau`，单窗口偏移不超过 `delta_max`。

### 5.4 Phase D（Decoupled，后续）

- 目标：按 2026-03-02 路线完成解耦化能力边界。
- 范围：
  - `Timestamp Resolver` 独立化。
  - `Noun Density Aggregator` 独立化。
  - 主 ingest 链路仅保留编排。
- 验收：
  - 阶段能力可独立测试与发布，旧链路仅作为 adapter。

## 6. 最小验证集合（统一门禁）

1. 后端契约与回归
- `cd main/backend && python3.11 -m pytest -q tests/core_business/test_api_group_b_core_contract.py tests/core_business/test_admin_dashboard_process_core_contract.py tests/core_business/test_process_consistency_core_contract.py`

2. 实际案例
- `cd main/backend && python3.11 scripts/run_realcase_prompt_time_density.py --project demo_proj --case-set all --fail-fast`

2.1 密度云与避峰验证
- 新增 case：
  - 峰值窗口识别正确（`is_peak=true` 命中）
  - `recommended_offpeak_windows` 为空时必须返回 `cold_start_proxy`
  - `avoid_peak=true` 时调度结果中峰值窗口占比显著下降
  - `vector_overlap < min_overlap` 的窗口不得入选
  - 在 `vector_overlap >= min_overlap` 子集中，排序优先低 `peak_pressure_score`
  - `fail_rate` 上升时，`latent_density_score` 同步下降
  - `dup_ratio` 上升时，`latent_density_score` 同步下降
  - `KL(p_new||p_base) <= tau` 持续满足
  - `|p_new-p_base| <= delta_max` 对所有窗口满足
  - 关闭 `avoid_peak` 时输出应退化为 `p_new == p_base`（或仅探索项差异）

3. 前端 modern
- `cd main/frontend-modern && npm run -s lint && npm run -s test -- GraphPage`

4. 发布门禁（T12）
- `cd main/backend && python3.11 scripts/generate_prompt_time_density_gonogo.py --realcase .artifacts/realcase_prompt_time_density_report.json --perf .artifacts/perf_metrics.json --output .artifacts/prompt_time_density_gonogo.md`

## 7. 风险与处置

1. 命名切换风险
- 风险：`prompt_group_id` 与 `noun_group_id` 双轨期间造成缓存碎片或字段混读。
- 处置：统一参数归一层 + query key 标准化 + 兼容期埋点统计。

2. 时间边界风险
- 风险：时区/边界日导致统计偏差。
- 处置：统一 UTC 存储与边界测试样例，禁止 naive/aware 混用。

3. 性能风险
- 风险：密度聚合 P95 波动。
- 处置：保留聚合优化开关（物化视图或桶粒度降级）。

4. 云模型误判风险
- 风险：平滑参数不当导致“假低谷”。
- 处置：输出 `offpeak_confidence` 与 `uncertainty_band`，低置信度时降级为保守策略。

5. overlap 门槛过严风险
- 风险：`min_overlap` 过高导致可行窗口塌缩，反向集中到少数峰值窗口。
- 处置：设置 `feasible_window_count` 下限与自动降门槛策略，触发时写入 `policy_decision_log`。

6. 反馈污染风险
- 风险：抓取/解析基础设施故障污染 `fail_rate`，误伤 `latent_density`。
- 处置：反馈打标拆分 `infra_fail` 与 `retrieval_fail`，仅后者进入主模型。

## 8. 与原文档关系说明

- 原文档继续保留，作为历史上下文与审计依据。
- 本文档作为“唯一执行入口”，后续更新优先写入本文件。
- 若原文档后续追加内容，应在本文件维护“变更映射”并同步索引。

## 9. 原任务映射（简版）

- `A1-A8`（2026-03-05）映射到 `T01-T12` 的关系保持不变，后续仅维护 `T*` 口径。
- `2026-03-02` 的 `Phase A/B/C` 与本文件 `Phase R/S/D` 对齐关系：
  - `Phase A` -> `Phase R + Phase S`
  - `Phase B/C` -> `Phase D`
