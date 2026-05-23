# 01 合并修复与 Smart Timestamp 计划（2026-03-14）

## 文档元信息
- 文档 ID: `A01-merged-remediation-smart-timestamp-2026-03-14`
- 所属目录: `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-time-semantics-density-merged-plan/ARCHIVE_01_04/`
- 版本: `v2026.03.14`
- 状态: `current-baseline`
- 术语主键: `noun_group_id`
- 对齐代码范围:
- `main/backend/app/api/stats.py`
- `main/backend/app/services/stats/prompt_time_density.py`
- `main/backend/app/models/entities.py`
- `main/backend/migrations/versions/20260312_000008_add_prompt_time_policy_decision_logs.py`

## 定位
- 本文是 2026-03-14 口径下的执行基线，目标是把“时间语义 + 密度统计 + 轻避峰策略 + 决策日志”收敛为一份可验收计划。
- 约束: 以代码现状为准，历史计划仅作为差异对照。

## 最新实现事实
1. 时间语义已落地为统一 effective 时间表达式，顺序为 `policy.effective_date -> publish_date -> created_at::date`。
2. API 已提供四个端点: `/prompt-time-density`、`/cloud`、`/priority`、`/select-windows`。
3. 语义组参数已兼容 `noun_group_ids` 与 `prompt_group_ids`，内部优先 `noun_group_ids`。
4. `priority` 已实现轻避峰分布改写: `eta + delta_max + tau + KL` 预算约束。
5. `priority` 输出包含 `p_base/p_new/kl_to_base/policy_decision_trace`，并写入 `prompt_time_policy_decision_logs`。
6. 数据层已落地两张表: `prompt_time_policy_decision_logs` 与 `prompt_time_window_feedback`。

## 历史差异
1. 2026-03-12 方案中的 `max_peak_percentile` 未在 `priority` API 落地；当前仅通过 `shift_signal` 与 `avoid_peak` 控制。
2. 2026-03-12 方案中的 `O1/O2/O3` 向量重合度定义尚未落地；当前 `vector_overlap` 为启发式 lexical+recency。
3. 2026-03-12 提到的 `window_density_stats/window_embedding_profile/noun_group_overlap_cache/shift_experiment_log` 尚未建表。
4. `cloud` 当前输出为 `smoothed_density + uncertainty_lower/upper`，未输出 `is_valley`/`zscore`。

## 接口与数据契约
1. `GET /api/v1/stats/prompt-time-density`
- 入参: `time_window | start+end`、`bucket`、`source_domains[]`、`noun_group_ids[]|prompt_group_ids[]`、`normalize`
- 出参核心项: `source_domain`、`noun_group_id`、`bucket_time`、`effective_new_docs`、`density`、`baseline_density`、`norm_density`、`dup_ratio`

2. `GET /api/v1/stats/prompt-time-density/cloud`
- 入参: 额外 `keyword`、`smoothing`、`peak_percentile`、`uncertainty`
- 出参核心项: `cloud_points[]`、`cloud_summary`、`uncertainty_band`、`cold_start_proxy`

3. `GET /api/v1/stats/prompt-time-density/priority`
- 入参: `candidate_windows[]`、`prefer_low_density`、`exclude_high_dup`、`min_overlap`、`target_overlap`、`eta`、`delta_max`、`tau`、`avoid_peak`
- 出参核心项: `window`、`vector_overlap`、`shift_signal`、`offpeak_confidence`、`p_base`、`p_new`、`kl_to_base`、`policy_decision_trace`、`rank`

4. `GET /api/v1/stats/prompt-time-density/select-windows`
- 行为: 基于 `priority` 结果按 `window` 去重，返回最多 `max_windows` 个窗口。

5. 落库契约
- `prompt_time_policy_decision_logs`: 决策行为日志、分布改写证据、策略版本。
- `prompt_time_window_feedback`: 观察回报与质量反馈。

## 风险边界
1. `vector_overlap` 非 embedding 语义重合度，存在误判边界。
2. `query_prompt_time_density` 同时返回 `noun_group_id` 和 `prompt_group_id`，前端若混用可能产生契约漂移。
3. 写日志失败被吞并仅打印异常，不会阻断在线排序，存在观测缺口风险。
4. `chosen_window` 取 `p_base` 最大窗口用于行为日志，不代表实际 `p_new` 最优窗口。

## 验收标准
1. API 契约验收
- `priority` 返回字段包含 `p_base/p_new/kl_to_base/policy_decision_trace/request_id`。
- `cloud` 返回 `uncertainty_band` 与可空 `cold_start_proxy`。

2. 数据契约验收
- migration `20260312_000008` 可创建两张表及索引。
- ORM 实体字段与 migration 列名一致。

3. 语义统一验收
- 文档与接口主术语统一为 `noun_group_id`。
- `prompt_group_ids` 仅作为兼容入参，不作为主口径字段名。

## Reference Registry
| Ref ID | 类型 | 条目 | 用途 |
|---|---|---|---|
| R-01 | 历史计划 | `2026-03-12 .../01_merged-remediation-and-smart-timestamp-plan-2026-03-12.md` | 作为 2026-03-12 基线对照 |
| R-02 | 历史研究 | `2026-03-12 .../02_research-report-density-cloud-overlap-avoid-peak-2026-03-12.md` | 对照已实现与未实现研究项 |
| R-03 | 历史统一报告 | `2026-03-12 .../03_unified-research-and-design-report-density-cloud-overlap-shift-2026-03-12.md` | 对照统一契约与分布改写定义 |
| R-04 | 代码 | `main/backend/app/api/stats.py` | API 契约事实来源 |
| R-05 | 代码 | `main/backend/app/services/stats/prompt_time_density.py` | 算法与日志事实来源 |
| R-06 | 代码 | `main/backend/app/models/entities.py` | ORM 契约事实来源 |
| R-07 | 代码 | `main/backend/migrations/versions/20260312_000008_add_prompt_time_policy_decision_logs.py` | DDL 契约事实来源 |

## Implementation Registry
| Impl ID | 实现位置 | 事实条目 | 对应 Ref |
|---|---|---|---|
| I-API-001 | `main/backend/app/api/stats.py:69` | 暴露 `/prompt-time-density` |
| I-API-002 | `main/backend/app/api/stats.py:107` | 暴露 `/prompt-time-density/cloud` |
| I-API-003 | `main/backend/app/api/stats.py:151` | 暴露 `/prompt-time-density/priority` |
| I-API-004 | `main/backend/app/api/stats.py:198` | 暴露 `/prompt-time-density/select-windows` |
| I-SEM-001 | `main/backend/app/api/stats.py:61` | `noun_group_ids` 优先并兼容 `prompt_group_ids` |
| I-TIME-001 | `main/backend/app/services/stats/prompt_time_density.py:31` | effective 时间回退链 |
| I-CLOUD-001 | `main/backend/app/services/stats/prompt_time_density.py:427` | density cloud 构建函数 |
| I-PRI-001 | `main/backend/app/services/stats/prompt_time_density.py:653` | `p_base -> p_new` 分布改写 |
| I-PRI-002 | `main/backend/app/services/stats/prompt_time_density.py:669` | `policy_decision_trace` 生成 |
| I-LOG-001 | `main/backend/app/services/stats/prompt_time_density.py:705` | priority 决策日志持久化 |
| I-DB-001 | `main/backend/app/models/entities.py:689` | `PromptTimePolicyDecisionLog` ORM |
| I-DB-002 | `main/backend/app/models/entities.py:716` | `PromptTimeWindowFeedback` ORM |
| I-MIG-001 | `main/backend/migrations/versions/20260312_000008_add_prompt_time_policy_decision_logs.py:21` | 创建 `prompt_time_policy_decision_logs` |
| I-MIG-002 | `main/backend/migrations/versions/20260312_000008_add_prompt_time_policy_decision_logs.py:64` | 创建 `prompt_time_window_feedback` |
