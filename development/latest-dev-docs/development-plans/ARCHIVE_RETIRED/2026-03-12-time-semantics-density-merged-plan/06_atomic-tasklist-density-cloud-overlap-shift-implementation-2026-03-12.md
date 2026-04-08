# 原子任务单：Density Cloud + Overlap + Shift（2026-03-12）

来源主文档：`05_merged-unified-report-from-two-reports-density-cloud-overlap-shift-2026-03-12.md`

## AT-01 API 参数扩展（priority）

- 目标：为 `GET /api/v1/stats/prompt-time-density/priority` 增加 `min_overlap/target_overlap/eta/delta_max/tau/avoid_peak`。
- 输入：`main/backend/app/api/stats.py` 现有 query 参数。
- 输出：路由支持新增参数与范围校验。
- 验收：非法参数返回 `422 + INVALID_INPUT`；无新增参数时向后兼容。
- 最小检查：`cd main/backend && python3.11 -m pytest -q tests/core_business/test_api_group_b_core_contract.py`

## AT-02 Priority 返回字段扩展

- 目标：返回 `noun_group_id/vector_overlap/shift_signal/p_base/p_new/kl_to_base/offpeak_confidence`。
- 输入：`query_prompt_time_density_priority` 当前返回结构。
- 输出：API `items[]` 包含新字段。
- 验收：保留 `prompt_group_id` 兼容字段；新字段存在且类型稳定。
- 最小检查：`cd main/backend && python3.11 -m pytest -q tests/core_business/test_process_consistency_core_contract.py`

## AT-03 新增 cloud API

- 目标：新增 `GET /api/v1/stats/prompt-time-density/cloud`。
- 输入：`api/stats.py` 与 `services/stats/prompt_time_density.py`。
- 输出：支持 `cloud_points/cloud_summary/uncertainty_band/cold_start_proxy`。
- 验收：`keyword` 必填；无历史时返回 `cold_start_proxy`。
- 最小检查：`cd main/backend && python3.11 -m pytest -q tests/core_business/test_api_group_b_core_contract.py`

## AT-04 DensityCloudBuilder 实现

- 目标：实现 `query_prompt_time_density_cloud(...)`（平滑、峰谷、统计摘要）。
- 输入：现有 `query_prompt_time_density` 聚合能力。
- 输出：可复用的云构建函数。
- 验收：`is_peak/is_valley` 与 `peak_percentile` 一致。
- 最小检查：新增单测 `cloud builder` 通过。

## AT-05 OverlapEstimator 实现

- 目标：实现 V1 `O1` overlap（`cos(e(query), e(window_centroid))`）。
- 输入：窗口向量与 query 向量。
- 输出：`vector_overlap` 标量及版本标识。
- 验收：`vector_overlap < min_overlap` 不进入可行集。
- 最小检查：新增单测 `overlap gate` 通过。

## AT-06 Bounded Redistribution 实现

- 目标：实现 `redistribute_window_probabilities(...)`。
- 输入：`p_base`, `shift_signal`, `eta`, `delta_max`, `tau`。
- 输出：`p_new`, `kl_to_base`。
- 验收：始终满足 `|p_new-p_base| <= delta_max` 与 `KL<=tau`。
- 最小检查：新增单测 `redistribution constraints` 通过。

## AT-07 avoid_peak 退化逻辑

- 目标：实现 `avoid_peak=false` 的退化路径。
- 输入：priority 调度流程。
- 输出：`p_new == p_base`（探索噪声除外）。
- 验收：开启/关闭结果差异符合预期。
- 最小检查：新增单测 `avoid_peak fallback` 通过。

## AT-08 命名兼容层

- 目标：实现 `prompt_group_ids -> noun_group_ids` 入参归一与双字段出参兼容。
- 输入：API/服务层参数。
- 输出：兼容不破坏旧调用。
- 验收：旧参数仍可用；新字段主输出稳定。
- 最小检查：契约测试通过。

## AT-09 决策日志落库

- 目标：新增/接入 `policy_decision_log` 写入。
- 输入：priority 计算过程。
- 输出：记录 `shift_signal_breakdown/p_base/p_new/kl_to_base/policy_version/chosen_window`。
- 验收：每次调度均可追踪决策 trace。
- 最小检查：集成测试校验日志字段完整。

## AT-10 Celery 任务扩展

- 目标：扩展 `task_select_prompt_time_windows` 参数与返回结构。
- 输入：`main/backend/app/services/tasks.py`。
- 输出：支持 `eta/delta_max/tau/min_overlap/target_overlap/avoid_peak`。
- 验收：任务返回含 `p_base/p_new/kl_to_base/offpeak_confidence`。
- 最小检查：任务链路集成测试通过。

## AT-11 离线 OPE 流水线

- 目标：建立最小 OPE 评估（Replay + IPS/SNIPS + DR/Switch-DR/DRos）。
- 输入：历史调度日志与反馈。
- 输出：离线评估报告（可入 Go/No-Go）。
- 验收：评估脚本稳定产出指标与置信区间。
- 最小检查：离线脚本跑通并生成报告文件。

## AT-12 发布门禁与回滚

- 目标：将 KL/偏移/收益指标纳入 Go/No-Go。
- 输入：realcase 报告、perf 指标、OPE 报告。
- 输出：自动判定与回滚建议。
- 验收：连续 48h 恶化可触发回滚到上个 `policy_version`。
- 最小检查：`generate_prompt_time_density_gonogo.py` 扩展检查通过。

## 串并行建议

- 可并行：`AT-01/02/08`, `AT-04/05/06/07`, `AT-09/10`
- 串行依赖：`AT-11` 依赖 `AT-09/10` 日志；`AT-12` 依赖 `AT-11`

## 总体验收

1. 新 API 与旧调用兼容。
2. 分布改写约束可证明满足。
3. 离线 + 在线门禁可闭环。
4. 文档、索引、实现三者一致。
