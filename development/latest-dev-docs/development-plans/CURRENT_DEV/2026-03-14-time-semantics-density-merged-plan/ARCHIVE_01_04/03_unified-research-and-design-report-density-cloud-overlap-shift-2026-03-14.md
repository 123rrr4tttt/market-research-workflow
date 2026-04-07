# 03 统一研究与设计报告：Density Cloud、Overlap 与 Shift（2026-03-14）

## 文档元信息
- 文档 ID: `A03-unified-research-design-density-cloud-overlap-shift-2026-03-14`
- 版本: `v2026.03.14`
- 状态: `single-source-of-truth`
- 术语主键: `noun_group_id`
- 基线来源: A01 执行计划 + A02 调查核对 + 当前代码

## 定位
- 本文是“研究结论、设计约束、实现事实”的统一口径文档。
- 用于评审与实施时的一页式判定: 什么已实现、什么可依赖、什么仍是下一阶段任务。

## 最新实现事实
1. 统一时间语义已工程化，统计窗口基于 effective 时间过滤。
2. 密度云已支持 `ema/gaussian/none` 平滑与分位峰值识别。
3. 轻避峰分布改写已实现边界控制:
- `|p_new-p_base|` 受 `delta_max` 约束。
- `KL(p_new || p_base)` 受 `tau` 约束。
4. `priority -> select-windows` 已形成完整链路，可直接用于窗口选择。
5. 决策日志链路已闭环: API 计算结果 -> trace 组装 -> ORM 持久化。

## 历史差异
1. 历史报告把 `vector_overlap` 作为向量语义指标；当前实现是启发式替代。
2. 历史报告建议“在线策略 + OPE 评估”双闭环；当前仅具备在线决策与日志，不含 OPE 计算。
3. 历史报告定义了更多实体表；当前只有 `policy_decision_logs` 与 `window_feedback` 两表落地。
4. 历史报告强调 `max_peak_percentile` 进入 `priority`；当前没有该参数。

## 接口与数据契约
1. 统一接口面
- 统计: `/prompt-time-density`
- 密度云: `/prompt-time-density/cloud`
- 排序: `/prompt-time-density/priority`
- 选窗: `/prompt-time-density/select-windows`

2. 参数统一原则
- 主术语: `noun_group_ids`
- 兼容术语: `prompt_group_ids`
- 所有新增参数需满足确定性校验并返回 `INVALID_INPUT`。

3. 统一输出最小集合
- 统计层: `density/norm_density/dup_ratio/effective_new_docs`
- 云层: `smoothed_density/is_peak/uncertainty_*`
- 策略层: `vector_overlap/shift_signal/offpeak_confidence/p_base/p_new/kl_to_base`
- 审计层: `request_id/chosen_window/is_chosen/policy_decision_trace`

## 风险边界
1. 由于未引入真实向量 overlap，`target_overlap` 目前是流程参数而非严格语义目标。
2. `avoid_peak=false` 会直接退化为 `p_new == p_base`，若调用方误解会高估策略有效性。
3. 当前 `cloud` 聚合按 `bucket_time` 汇总，未提供跨域归一化策略，跨项目比较要谨慎。
4. 日志落库失败不会影响在线响应，必须依赖外部监控补齐失败感知。

## 验收标准
1. 统一口径验收
- 三层输出字段命名一致并以 `noun_group_id` 为主键语义。

2. 策略约束验收
- 当 `avoid_peak=true`，返回结果必须体现 `p_base/p_new/kl_to_base`。
- 当 `avoid_peak=false`，`redistribute_window_probabilities` 返回 base 分布。

3. 数据契约验收
- ORM 与 migration 在字段与索引上保持同名同义。
- `request_id` 可用于串联同次请求的所有窗口记录。

## Reference Registry
| Ref ID | 类型 | 条目 | 用途 |
|---|---|---|---|
| R3-01 | 当前计划 | `01_merged-remediation-and-smart-timestamp-plan-2026-03-14.md` | 执行边界与验收继承 |
| R3-02 | 当前调查 | `02_research-report-density-cloud-overlap-avoid-peak-2026-03-14.md` | 研究实现一致性继承 |
| R3-03 | API 代码 | `main/backend/app/api/stats.py` | 统一接口事实 |
| R3-04 | 服务代码 | `main/backend/app/services/stats/prompt_time_density.py` | 统一算法事实 |
| R3-05 | ORM 代码 | `main/backend/app/models/entities.py` | 数据契约事实 |
| R3-06 | migration 代码 | `main/backend/migrations/versions/20260312_000008_add_prompt_time_policy_decision_logs.py` | DDL 与索引事实 |
| R3-07 | 历史统一文档 | `2026-03-12 .../03_unified-research-and-design-report-density-cloud-overlap-shift-2026-03-12.md` | 历史差异对照 |

## Implementation Registry
| Impl ID | 实现位置 | 事实条目 | 对应 Ref |
|---|---|---|---|
| I3-API-001 | `main/backend/app/api/stats.py:42` | 时间范围统一解析 `start+end` 或 `time_window` |
| I3-API-002 | `main/backend/app/api/stats.py:61` | `noun_group_ids` 与 `prompt_group_ids` 兼容归并 |
| I3-API-003 | `main/backend/app/api/stats.py:168` | `priority` 默认窗口 `7d/30d/90d` |
| I3-SVC-001 | `main/backend/app/services/stats/prompt_time_density.py:22` | 提取 `policy.effective_date` 作为优先时间 |
| I3-SVC-002 | `main/backend/app/services/stats/prompt_time_density.py:322` | 基础密度统计主函数 |
| I3-SVC-003 | `main/backend/app/services/stats/prompt_time_density.py:542` | 轻避峰排序主函数 |
| I3-SVC-004 | `main/backend/app/services/stats/prompt_time_density.py:254` | 分布重写函数支持 `avoid_peak` 退化行为 |
| I3-SVC-005 | `main/backend/app/services/stats/prompt_time_density.py:717` | `select_priority_windows` 去重选窗 |
| I3-DB-001 | `main/backend/app/models/entities.py:697` | 策略日志主键字段集与索引字段 |
| I3-DB-002 | `main/backend/app/models/entities.py:724` | 反馈表字段集 |
| I3-MIG-001 | `main/backend/migrations/versions/20260312_000008_add_prompt_time_policy_decision_logs.py:44` | 策略日志索引创建 |
| I3-MIG-002 | `main/backend/migrations/versions/20260312_000008_add_prompt_time_policy_decision_logs.py:79` | 反馈表索引创建 |
