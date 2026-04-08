# Backend Interface Change Checklist：Density Cloud + Overlap + Shift（2026-03-12）

## 0. 目的

把研究与设计中的接口要求转换为后端可执行清单，覆盖：
- HTTP API 变更
- 服务层函数变更
- 任务接口变更
- 数据契约与日志
- 测试与发布门禁

## 1. 现状基线（已实现）

代码位置：
- `main/backend/app/api/stats.py`
- `main/backend/app/services/stats/prompt_time_density.py`
- `main/backend/app/services/tasks.py`

已实现路由：
1. `GET /api/v1/stats/prompt-time-density`
2. `GET /api/v1/stats/prompt-time-density/priority`
3. `GET /api/v1/stats/prompt-time-density/select-windows`

## 2. 目标接口（本次变更）

### 2.1 新增路由

1. `GET /api/v1/stats/prompt-time-density/cloud`

请求参数：
1. `keyword`（required）
2. `time_window | start+end`
3. `bucket`
4. `source_domains[]`
5. `noun_group_ids[]`（兼容 `prompt_group_ids[]`）
6. `smoothing=ema|gaussian|none`
7. `peak_percentile`
8. `uncertainty`

响应字段：
1. `cloud_points[]`
2. `cloud_summary`
3. `uncertainty_band`
4. `cold_start_proxy`（可选）

### 2.2 扩展现有 priority 路由

路由：`GET /api/v1/stats/prompt-time-density/priority`

新增请求参数：
1. `min_overlap`
2. `target_overlap`
3. `eta`
4. `delta_max`
5. `tau`
6. `avoid_peak`

新增响应字段：
1. `noun_group_id`（兼容返回 `prompt_group_id`）
2. `vector_overlap`
3. `shift_signal`
4. `p_base`
5. `p_new`
6. `kl_to_base`
7. `offpeak_confidence`

规则：
1. `avoid_peak=false` 时应返回 `p_new == p_base`（探索噪声除外）。
2. `vector_overlap < min_overlap` 不进入可行窗口集。

## 3. 服务层改造清单

文件：`main/backend/app/services/stats/prompt_time_density.py`

新增函数：
1. `query_prompt_time_density_cloud(...)`
2. `estimate_window_overlap(...)`
3. `redistribute_window_probabilities(...)`
4. `build_policy_decision_trace(...)`

改造函数：
1. `query_prompt_time_density_priority(...)`
: 从当前 `collection_priority_score` 排序，升级为 `shift_signal + bounded redistribution`。
2. `select_priority_windows(...)`
: 支持基于 `p_new` 的选择逻辑。

输入校验：
1. `eta >= 0`
2. `0 <= delta_max <= 1`
3. `tau >= 0`
4. `0 <= min_overlap <= 1`

## 4. 任务接口改造清单（Celery）

文件：`main/backend/app/services/tasks.py`

任务：`task_select_prompt_time_windows(...)`

新增入参：
1. `eta`
2. `delta_max`
3. `tau`
4. `min_overlap`
5. `target_overlap`
6. `avoid_peak`

新增回传字段：
1. `p_base`
2. `p_new`
3. `kl_to_base`
4. `offpeak_confidence`

## 5. 数据契约与日志

建议新增表/实体：
1. `window_density_stats`
2. `window_collection_feedback`
3. `window_embedding_profile`
4. `noun_group_overlap_cache`
5. `shift_experiment_log`
6. `policy_decision_log`

`policy_decision_log` 最低字段：
1. `shift_signal_breakdown`
2. `p_base`
3. `p_new`
4. `kl_to_base`
5. `policy_version`

## 6. 向后兼容

1. 入参兼容 `prompt_group_ids[]`，内部归一到 `noun_group_ids[]`。
2. 出参同时保留 `prompt_group_id`（过渡期），新增 `noun_group_id`。
3. 保留原有路由路径，不做破坏性改名。

## 7. 测试清单

### 7.1 单元测试

1. `query_prompt_time_density_cloud` 峰谷识别
2. `redistribute_window_probabilities` 的 `delta_max`/`tau` 约束
3. `avoid_peak=false` 的退化一致性
4. `min_overlap` 门控正确性

### 7.2 API 合约测试

1. `/stats/prompt-time-density/cloud` 响应结构
2. `/stats/prompt-time-density/priority` 新参数/新字段
3. 错误参数（`eta/delta_max/tau`）返回 `422`

### 7.3 集成测试

1. Celery 任务接口参数贯通
2. `policy_decision_log` 写入完整性

## 8. 发布门禁（Go/No-Go）

1. `KL(p_new||p_base)` P95 `<= tau`
2. `max |p_new-p_base| <= delta_max`
3. `overlap_pass_rate` 不低于基线
4. `effective_new_docs_rate` 不劣化
5. 连续 48h 恶化触发回滚到上个 `policy_version`

## 9. 执行顺序（建议）

1. API schema 先行（参数与字段）
2. 服务层 bounded redistribution
3. overlap 估计与 cloud 查询
4. Celery 任务扩展
5. 测试与灰度

## 10. 参考文档

1. `03_unified-research-and-design-report-density-cloud-overlap-shift-2026-03-12.md`
2. `02_research-report-density-cloud-overlap-avoid-peak-2026-03-12.md`
3. `01_merged-remediation-and-smart-timestamp-plan-2026-03-12.md`
