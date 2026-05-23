# 02 调查报告：Density Cloud、重合约束与轻避峰（2026-03-14）

## 文档元信息
- 文档 ID: `A02-research-density-cloud-overlap-avoid-peak-2026-03-14`
- 版本: `v2026.03.14`
- 状态: `code-aligned`
- 术语主键: `noun_group_id`
- 调查口径: 代码现状优先，历史研究结论作为对照与待补项

## 定位
- 本文给出“研究结论 vs 当前代码实现”的逐项核对，明确哪些能力已落地、哪些仍停留在研究设想。
- 目标不是新增设想，而是为后续实现提供准确边界。

## 最新实现事实
1. `density_cloud` 已实现时间桶聚合、平滑、分位阈值判峰、不确定区间、稀疏冷启动代理。
2. `priority` 已实现 overlap 下限过滤、轻避峰分布改写、KL 预算约束与排序。
3. `latent_density_score` 已按 `norm_density * (1-dup_ratio)^0.4` 的简化公式实现。
4. `vector_overlap` 当前为启发式估计，不依赖向量库。
5. 决策 trace 与行为日志已可落库，并包含 `policy_version`、`shift_signal_breakdown`、`p_base/p_new/kl_to_base`。

## 历史差异
1. 历史调研建议的 `Rocchio/OPRF/HyDE` 等 query-shift 机制尚未接入线上路径。
2. 历史建议的 OPE 评估链路（IPS/SNIPS/DR/Switch-DR）未在本模块内实现。
3. 历史文档提出的 `max_peak_percentile` 作为 `priority` 入参未落地。
4. 历史文档把 `uncertainty` 设为布尔开关；当前实现为 `[0,1]` 带宽参数。

## 接口与数据契约
1. `cloud` 契约
- 输入: `keyword`、时间范围、`bucket`、`noun_group_ids`、`smoothing`、`peak_percentile`、`uncertainty`
- 输出: `cloud_points[]` 包含 `smoothed_density/is_peak/uncertainty_lower/uncertainty_upper`
- 退化: 样本小于 3 个点时输出 `cold_start_proxy`

2. `priority` 契约
- 输入: `candidate_windows[]`、`min_overlap/target_overlap`、`eta/delta_max/tau`、`avoid_peak`
- 处理: 先筛 `overlap >= min_overlap`，再做有界重分布
- 输出: `collection_priority_score`、`offpeak_confidence`、`p_base/p_new/kl_to_base`、`rank`

3. 行为日志契约
- `request_id` 为同次请求统一 ID。
- `chosen_window` 当前定义为 `p_base` 最大窗口，`is_chosen` 基于此计算。

## 风险边界
1. overlap 启发式可能导致“相关性看起来合格但语义不够精确”。
2. `exclude_high_dup` 阈值固定为 `0.95`，在不同数据域可能过宽或过窄。
3. `policy_decision_logs` 写入失败不会失败请求，可能出现“在线有效但不可审计”。
4. `query_prompt_time_density` 对文档类型固定为 `policy/policy_regulation/news/social`，域外文档不参与统计。

## 验收标准
1. 研究到实现一致性
- 研究中的“轻避峰 + 约束重分布”必须在服务层有可追踪实现与参数校验。

2. 契约完整性
- `cloud` 与 `priority` API 必须均支持 `noun_group_ids` 主口径。
- `priority` 返回值必须可直接用于回放和审计。

3. 可审计性
- 每次 `priority` 调用产生日志条目，且 `request_id` 贯穿同批结果。

## Reference Registry
| Ref ID | 类型 | 条目 | 用途 |
|---|---|---|---|
| R2-01 | 历史研究文档 | `2026-03-12 .../02_research-report-density-cloud-overlap-avoid-peak-2026-03-12.md` | 研究假设基线 |
| R2-02 | 历史统一文档 | `2026-03-12 .../03_unified-research-and-design-report-density-cloud-overlap-shift-2026-03-12.md` | 统一定义对照 |
| R2-03 | 服务实现 | `main/backend/app/services/stats/prompt_time_density.py` | 当前算法事实 |
| R2-04 | API 实现 | `main/backend/app/api/stats.py` | 参数与响应契约 |
| R2-05 | ORM 实现 | `main/backend/app/models/entities.py` | 落库字段契约 |
| R2-06 | Migration 实现 | `main/backend/migrations/versions/20260312_000008_add_prompt_time_policy_decision_logs.py` | DDL 与索引事实 |

## Implementation Registry
| Impl ID | 实现位置 | 事实条目 | 对应 Ref |
|---|---|---|---|
| I2-CLOUD-001 | `main/backend/app/services/stats/prompt_time_density.py:487` | `cloud` 对桶序列进行平滑与峰值阈值计算 | R2-03 |
| I2-CLOUD-002 | `main/backend/app/services/stats/prompt_time_density.py:500` | 输出 `smoothed_density/is_peak/uncertainty_*` | R2-03 |
| I2-CLOUD-003 | `main/backend/app/services/stats/prompt_time_density.py:515` | 小样本返回 `cold_start_proxy` | R2-03 |
| I2-PRI-001 | `main/backend/app/services/stats/prompt_time_density.py:620` | `overlap < min_overlap` 直接过滤 | R2-03 |
| I2-PRI-002 | `main/backend/app/services/stats/prompt_time_density.py:623` | `shift_signal` 固定加权公式 | R2-03 |
| I2-PRI-003 | `main/backend/app/services/stats/prompt_time_density.py:653` | `redistribute_window_probabilities` 应用 KL/偏移约束 | R2-03 |
| I2-PRI-004 | `main/backend/app/services/stats/prompt_time_density.py:665` | 输出 `target_overlap/p_base/p_new/kl_to_base` | R2-03 |
| I2-LOG-001 | `main/backend/app/services/stats/prompt_time_density.py:699` | 为每批结果生成统一 `request_id` | R2-03 |
| I2-LOG-002 | `main/backend/app/services/stats/prompt_time_density.py:705` | 写入 `PromptTimePolicyDecisionLog` | R2-03 |
| I2-API-001 | `main/backend/app/api/stats.py:117` | `cloud` 支持 `smoothing` 参数 | R2-04 |
| I2-API-002 | `main/backend/app/api/stats.py:118` | `cloud` 支持 `peak_percentile` 参数 | R2-04 |
| I2-API-003 | `main/backend/app/api/stats.py:162` | `priority` 支持 `eta/delta_max/tau` | R2-04 |
| I2-DB-001 | `main/backend/app/models/entities.py:700` | 日志表以 `noun_group_id` 建索引 | R2-05 |
| I2-MIG-001 | `main/backend/migrations/versions/20260312_000008_add_prompt_time_policy_decision_logs.py:52` | migration 建 `noun_group_id` 索引 | R2-06 |
