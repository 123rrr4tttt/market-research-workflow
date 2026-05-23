# Backend Interface Change Checklist：Density Cloud + Overlap + Shift（2026-03-14）

## 0. 用途与范围

本清单用于把 01-03 的方案要求，映射到当前后端“已实现/待补强”接口事实，供 05/06 直接引用。

范围仅覆盖：
1. `main/backend/app/api/stats.py`
2. `main/backend/app/services/stats/prompt_time_density.py`
3. `main/backend/app/services/tasks.py`
4. `main/backend/app/models/entities.py`

## 1. 代码现状基线（已落地）

### 1.1 已有路由

1. `GET /api/v1/stats/prompt-time-density`
2. `GET /api/v1/stats/prompt-time-density/cloud`
3. `GET /api/v1/stats/prompt-time-density/priority`
4. `GET /api/v1/stats/prompt-time-density/select-windows`

### 1.2 已有核心字段

`noun_group_id`、`vector_overlap`、`shift_signal`、`p_base`、`p_new`、`kl_to_base` 已在 priority 结果中生成并回传。

### 1.3 已有日志落库

已存在 `prompt_time_policy_decision_logs`（模型：`PromptTimePolicyDecisionLog`），且在线优先级查询会写入决策日志。

## 2. 条目级“参考 + 实现”映射

| 条目 | 参考（01-03 术语/要求） | 当前实现（代码） | 状态 | 下一步 |
|---|---|---|---|---|
| noun_group 统一命名 | `noun_group_id` 作为主键，兼容 `prompt_group_id` | `stats.py::_coalesce_noun_group_ids`；服务层同时返回 `noun_group_id/prompt_group_id` | 已实现 | 保持兼容窗口，后续仅前端主用 `noun_group_id` |
| cloud 接口 | 需提供 density cloud、峰值、不确定性 | `GET /prompt-time-density/cloud` + `query_prompt_time_density_cloud(...)` 输出 `cloud_points/cloud_summary/uncertainty_band/cold_start_proxy` | 已实现 | 补充契约测试覆盖新字段 |
| overlap 门控 | `vector_overlap >= min_overlap` 才可参与 | `estimate_window_overlap(...)` + `query_prompt_time_density_priority(...)` 中 `if overlap < min_overlap: continue` | 已实现（V1启发式） | 升级为 embedding O1 真实余弦实现 |
| shift 信号 | `shift_signal` 参与轻避峰分布改写 | `shift_signal = a*peak + b*(1-latent)+c*(1-overlap)+d*freshness` | 已实现 | 对权重做版本化配置外置 |
| 有界重分布 | `p_base -> p_new`，受 `delta_max/tau` 约束 | `redistribute_window_probabilities(...)` 包含 bounded simplex + KL 回投影 | 已实现 | 增加极值参数单测 |
| KL 可观测 | 必须输出 `kl_to_base` | 每行返回 `kl_to_base`，并写入日志表 | 已实现 | 增加 P95 监控看板 |
| avoid_peak 退化 | `avoid_peak=false` 时回退基线分布 | `if not avoid_peak: return base, 0.0` | 已实现 | 增加 API 回归测试 |
| Celery 参数贯通 | 任务侧需支持新参数 | `task_select_prompt_time_windows(...)` 已接收 `min_overlap/target_overlap/eta/delta_max/tau/avoid_peak` | 已实现 | 在任务契约测试中断言字段完整 |
| 策略 trace | 需要可回放 `shift_signal/p_base/p_new/kl_to_base` | `build_policy_decision_trace(...)` + `_persist_policy_decision_logs(...)` | 已实现 | 增加 request 级审计查询接口 |
| target_overlap 语义 | 目标 overlap 需参与策略控制 | 当前仅回传 `target_overlap`，未进入评分/约束计算 | 待补强 | 将其纳入目标偏差罚项 |
| 离线 OPE | Replay + IPS/SNIPS + DR 系列门禁 | 代码中尚无 OPE 执行链路 | 待补强 | 新建离线评估脚本与 Go/No-Go 接入 |
| 规划中实体 | `window_density_stats/window_collection_feedback/...` | 目前落地为 `prompt_time_policy_decision_logs` 与 `prompt_time_window_feedback` | 部分实现 | 明确“映射关系”或按规划补新表 |

## 3. 接口参数与字段核对清单

### 3.1 `/prompt-time-density/cloud`

请求参数：
1. `keyword`（必填）
2. `start/end` 或 `time_window`
3. `bucket`
4. `source_domains`
5. `noun_group_ids`（兼容 `prompt_group_ids`）
6. `smoothing`
7. `peak_percentile`
8. `uncertainty`

响应字段：
1. `cloud_points[]`
2. `cloud_summary`
3. `uncertainty_band`
4. `cold_start_proxy`

### 3.2 `/prompt-time-density/priority`

请求参数：
1. `min_overlap`
2. `target_overlap`
3. `eta`
4. `delta_max`
5. `tau`
6. `avoid_peak`

响应字段（关键）：
1. `noun_group_id`
2. `vector_overlap`
3. `shift_signal`
4. `p_base`
5. `p_new`
6. `kl_to_base`
7. `policy_decision_trace`
8. `request_id/chosen_window/is_chosen`

## 4. 最小门禁建议（接口改造相关）

1. `cd main/backend && python3.11 -m pytest -q tests/core_business/test_api_group_b_core_contract.py`
2. `cd main/backend && python3.11 -m pytest -q tests/core_business/test_process_consistency_core_contract.py`
3. 对 `prompt_time_density.py` 新增/补齐单测，覆盖：
- `delta_max` 边界
- `tau` 边界
- `avoid_peak=false` 退化
- `target_overlap` 新逻辑（补强后）

## 5. 结论

接口主链路已具备开发可用基线，不属于“从 0 到 1”。下一阶段重点不是补路由，而是把 `target_overlap`、OPE 门禁和测试覆盖补齐，避免“字段存在但策略未闭环”。
