# 时间语义与密度能力统一主报告（开发主读本，2026-03-14）

## 0. 文档定位

本文档是该主题唯一主读本，目标是“只看这一份即可开发、联调、验收”。

输入来源：
1. 01-03 的术语与目标约束
2. 04 接口核对清单（代码现状）
3. 当前后端实现（API/Service/Task/Model）

## 1. 当前代码事实（Code-First Baseline）

### 1.1 现有 API

1. `GET /api/v1/stats/prompt-time-density`
2. `GET /api/v1/stats/prompt-time-density/cloud`
3. `GET /api/v1/stats/prompt-time-density/priority`
4. `GET /api/v1/stats/prompt-time-density/select-windows`

### 1.2 现有策略链路

1. `query_prompt_time_density(...)`：按时间桶聚合 `density/norm_density/dup_ratio`。
2. `query_prompt_time_density_cloud(...)`：构建 `cloud_points/cloud_summary/uncertainty_band/cold_start_proxy`。
3. `query_prompt_time_density_priority(...)`：
- 计算 `vector_overlap`
- 生成 `shift_signal`
- 对窗口分布做 `p_base -> p_new`
- 计算 `kl_to_base`
- 落库决策 trace
4. `task_select_prompt_time_windows(...)`：Celery 任务透传策略参数。

### 1.3 现有数据落地

1. `prompt_time_policy_decision_logs`：记录 `noun_group_id/vector_overlap/shift_signal/p_base/p_new/kl_to_base` 等。
2. `prompt_time_window_feedback`：记录观测反馈（reward/duplicate/fail）。

## 2. 统一术语（与 01-03 对齐）

1. `noun_group_id`：语义组主键。
2. `vector_overlap`：窗口语义重合度（V1 当前为启发式，目标为 O1 embedding 余弦）。
3. `shift_signal`：轻避峰策略信号。
4. `p_base`：基线窗口分布。
5. `p_new`：重分布后的窗口分布。
6. `kl_to_base`：`KL(p_new || p_base)`。

## 3. 参考 + 实现映射（条目级）

| 主题 | 参考（01-03） | 当前实现（代码） | 结论 |
|---|---|---|---|
| 命名统一 | `noun_group_id` 主导，兼容 `prompt_group_id` | API 参数合并、返回双字段 | 已达成 |
| overlap 门控 | 低 overlap 不参与候选 | priority 中 `overlap < min_overlap` 直接过滤 | 已达成（V1） |
| shift 信号 | 由峰压/潜在密度/overlap/新鲜度组成 | 固定权重公式已实现 | 已达成 |
| 分布改写 | `p_base -> p_new` + `delta_max/tau` 约束 | `redistribute_window_probabilities` 已实现 | 已达成 |
| 退化路径 | `avoid_peak=false` 回退 | 已返回 base 分布 | 已达成 |
| 决策可解释 | 记录 trace 与概率字段 | `policy_decision_trace` + DB log 已实现 | 已达成 |
| target_overlap | 作为目标控制项 | 当前仅回传，不参与损失/约束 | 缺口 |
| OPE 门禁 | Replay + IPS/SNIPS + DR | 尚无离线执行链路 | 缺口 |
| 测试覆盖 | 新字段/新约束需契约化 | core contract 仅部分覆盖旧字段 | 缺口 |

## 4. 目标架构（本轮实现口径）

### 4.1 在线路径

1. 请求进入 `/priority`。
2. 生成候选窗口统计特征。
3. 计算 `vector_overlap` 并做 `min_overlap` 过滤。
4. 计算 `shift_signal`。
5. 由 `p_base` 生成 `p_new`，并约束 `delta_max/tau`。
6. 输出排序与概率字段，持久化决策日志。

### 4.2 离线路径

1. 读取 `prompt_time_policy_decision_logs` 与 `prompt_time_window_feedback`。
2. 构造 bandit 样本（action=window，reward=observed signal）。
3. 运行 Replay / IPS / SNIPS / DR / Switch-DR。
4. 产出策略版本报告，写入 Go/No-Go 输入。

## 5. 详细接口契约（开发直接可用）

### 5.1 `GET /stats/prompt-time-density/cloud`

关键请求参数：
1. `keyword`
2. `time_window` 或 `start+end`
3. `bucket`
4. `noun_group_ids`（兼容 `prompt_group_ids`）
5. `smoothing`
6. `peak_percentile`
7. `uncertainty`

关键响应字段：
1. `cloud_points[]`
2. `cloud_summary`
3. `uncertainty_band`
4. `cold_start_proxy`

### 5.2 `GET /stats/prompt-time-density/priority`

关键请求参数：
1. `min_overlap`
2. `target_overlap`
3. `eta`
4. `delta_max`
5. `tau`
6. `avoid_peak`

关键响应字段：
1. `noun_group_id`
2. `vector_overlap`
3. `shift_signal`
4. `p_base`
5. `p_new`
6. `kl_to_base`
7. `policy_decision_trace`

### 5.3 `GET /stats/prompt-time-density/select-windows`

调用 priority 后去重窗口，返回前 `max_windows`。

## 6. 本轮补强点（以可交付为顺序）

1. `target_overlap` 入策略：
- 将 `|vector_overlap - target_overlap|` 纳入 `shift_signal` 或独立约束项。

2. OPE 评估链路：
- 新增离线脚本，按 `policy_version` 评估并产出报告。

3. 测试补强：
- API 契约增加新字段断言。
- 服务层单测增加 `delta_max/tau/avoid_peak/target_overlap` 组合场景。

4. 门禁并线：
- 将离线 OPE 指标并入 Go/No-Go。

## 7. 开发执行清单（可直接按序实施）

1. 修改 `query_prompt_time_density_priority(...)`：引入 `target_overlap` 实际约束。
2. 新增 OPE 脚本（读取决策日志与反馈表）。
3. 扩展 core contract 测试，补新字段与边界参数。
4. 增加策略版本化配置（权重、阈值）与默认值声明。
5. 在发布脚本中接入 OPE 结果阈值判定。

## 8. 最小验证步骤

1. `cd main/backend && python3.11 -m pytest -q tests/core_business/test_api_group_b_core_contract.py`
2. `cd main/backend && python3.11 -m pytest -q tests/core_business/test_process_consistency_core_contract.py`
3. `cd main/backend && python3.11 -m pytest -q`（若时长允许）
4. 离线 OPE 脚本执行并产出报告文件（补强后作为强制步骤）

## 9. 风险与控制

1. 风险：`target_overlap` 未入策略会造成“参数存在但无效”。
- 控制：新增单测断言参数影响排序结果。

2. 风险：V1 overlap 启发式与真实语义偏差。
- 控制：并行引入 embedding O1 实现并做 A/B 对照。

3. 风险：缺少 OPE 门禁导致上线收益不可证伪。
- 控制：发布前强制输出 Replay/IPS/SNIPS/DR 报告。

4. 风险：日志写入失败导致可观测断层。
- 控制：增加日志失败告警与采样回查任务。

## 10. 结论

当前系统已具备 `density_cloud + overlap gate + shift redistribution + trace logging` 的可运行主链路。下一阶段不是重做接口，而是补齐 `target_overlap` 的真实策略作用、OPE 离线评估与测试门禁，使其从“可用”进入“可验证可持续迭代”。
## 接口契约硬化（草稿，可直接粘贴）

### 1. 统一响应 Envelope 与错误码

#### 1.1 统一响应结构

所有接口统一返回如下 envelope：

| 字段 | 必填 | 类型 | 说明 | 约束 |
|---|---|---|---|---|
| status | 是 | string | 响应状态 | `ok` \| `error` |
| data | 否 | object \| array \| null | 业务数据 | `status=ok` 时必须非 `null`；`status=error` 时必须为 `null` |
| error | 否 | object \| null | 错误信息 | `status=error` 时必须非 `null`；`status=ok` 时必须为 `null` |
| meta | 是 | object | 元信息 | 必须包含 `request_id`、`timestamp`、`version` |

`meta` 子字段约定：

| 字段 | 必填 | 类型 | 默认 | 说明 | 约束 |
|---|---|---|---|---|---|
| request_id | 是 | string | 无 | 请求链路唯一 ID | `^[a-zA-Z0-9_-]{8,64}$` |
| timestamp | 是 | string | 服务端生成 | 响应时间（UTC） | ISO8601（如 `2026-03-14T10:20:30Z`） |
| version | 是 | string | `v1` | 接口版本 | 非空 |
| duration_ms | 否 | integer | 无 | 服务端耗时 | `>=0` |
| pagination | 否 | object | 无 | 分页信息 | 仅列表接口需要 |

`error` 子字段约定：

| 字段 | 必填 | 类型 | 说明 | 约束 |
|---|---|---|---|---|
| code | 是 | string | 机器可读错误码 | 必须来自错误码表 |
| message | 是 | string | 人类可读错误信息 | 建议中文，长度 `1..256` |
| details | 否 | array | 字段级错误详情 | 422 场景建议必带 |
| retryable | 否 | boolean | 是否建议重试 | 默认 `false` |

`error.details[]` 子字段建议：

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| field | 是 | string | 错误字段路径，如 `query.min_overlap` |
| reason | 是 | string | 失败原因 |
| value | 否 | any | 实际值 |
| constraint | 否 | string | 约束表达式 |

#### 1.2 错误码规范

| HTTP | code | 场景 |
|---|---|---|
| 400 | `BAD_REQUEST` | 请求格式错误、非法枚举、时间区间格式错误 |
| 401 | `UNAUTHORIZED` | 未认证 |
| 403 | `FORBIDDEN` | 无权限 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 409 | `CONFLICT` | 并发冲突、策略版本冲突 |
| 422 | `VALIDATION_ERROR` | 参数校验失败（范围、互斥、依赖约束） |
| 429 | `RATE_LIMITED` | 请求频率超限 |
| 500 | `INTERNAL_ERROR` | 服务端未知错误 |
| 503 | `SERVICE_UNAVAILABLE` | 下游依赖不可用 |

参数校验失败统一使用：HTTP `422` + `error.code=VALIDATION_ERROR`。

### 2. 接口参数与响应字段契约

以下路径均相对于：`/api/v1/stats/prompt-time-density`

---

### 2.1 `GET /cloud`

#### 请求参数表

| 参数 | 必填 | 类型 | 默认 | 约束 |
|---|---|---|---|---|
| keyword | 否 | string | 无 | 长度 `1..128`，与 `noun_group_ids` 至少提供一个 |
| time_window | 否 | string | `7d` | 枚举：`24h`,`7d`,`14d`,`30d`,`90d`；与 `start/end` 互斥 |
| start | 否 | string | 无 | ISO8601；与 `end` 成对出现；与 `time_window` 互斥 |
| end | 否 | string | 无 | ISO8601；必须 `end > start` |
| bucket | 否 | string | `hour` | 枚举：`hour`,`day` |
| noun_group_ids | 否 | string | 无 | 逗号分隔 ID 列表；每项匹配 `^[A-Za-z0-9_-]{1,64}$` |
| prompt_group_ids | 否 | string | 无 | 兼容字段；存在时等价映射到 `noun_group_ids` |
| smoothing | 否 | number | `0.2` | `0 <= smoothing <= 1` |
| peak_percentile | 否 | integer | `90` | `50..99` |
| uncertainty | 否 | string | `normal` | 枚举：`off`,`normal`,`strict` |

#### 响应字段表（`data`）

| 字段 | 必填 | 类型 | 说明 | 约束 |
|---|---|---|---|---|
| cloud_points | 是 | array<object> | 时间云点集合 | 可为空数组 |
| cloud_points[].ts | 是 | string | 时间桶起点 | ISO8601 |
| cloud_points[].density | 是 | number | 原始密度 | `>=0` |
| cloud_points[].norm_density | 是 | number | 归一化密度 | `0..1` |
| cloud_points[].dup_ratio | 是 | number | 重复率 | `0..1` |
| cloud_summary | 是 | object | 云图汇总 | 非空对象 |
| cloud_summary.peak_ts | 否 | string | 峰值时间 | ISO8601 |
| cloud_summary.peak_density | 否 | number | 峰值密度 | `>=0` |
| cloud_summary.avg_density | 是 | number | 平均密度 | `>=0` |
| uncertainty_band | 是 | object | 不确定性区间 | 包含 low/high |
| uncertainty_band.low | 是 | number | 下界 | `>=0` |
| uncertainty_band.high | 是 | number | 上界 | `>= low` |
| cold_start_proxy | 是 | object | 冷启动代理信号 | 非空对象 |

---

### 2.2 `GET /priority`

#### 请求参数表

| 参数 | 必填 | 类型 | 默认 | 约束 |
|---|---|---|---|---|
| keyword | 否 | string | 无 | 长度 `1..128`，与 `noun_group_ids` 至少提供一个 |
| noun_group_ids | 否 | string | 无 | 逗号分隔 ID 列表 |
| prompt_group_ids | 否 | string | 无 | 兼容字段；映射至 `noun_group_ids` |
| time_window | 否 | string | `7d` | 枚举：`24h`,`7d`,`14d`,`30d`,`90d` |
| min_overlap | 否 | number | `0.15` | `0..1` |
| target_overlap | 否 | number | `0.50` | `0..1`；建议 `>= min_overlap` |
| eta | 否 | number | `0.30` | `0..2` |
| delta_max | 否 | number | `0.20` | `0..1` |
| tau | 否 | number | `1.0` | `0.1..10` |
| avoid_peak | 否 | boolean | `true` | `false` 时回退基线分布 |

#### 响应字段表（`data`）

| 字段 | 必填 | 类型 | 说明 | 约束 |
|---|---|---|---|---|
| items | 是 | array<object> | 优先级结果列表 | 可为空数组 |
| items[].noun_group_id | 是 | string | 语义组主键 | 非空 |
| items[].vector_overlap | 是 | number | 窗口语义重合度 | `0..1` |
| items[].shift_signal | 是 | number | 轻避峰策略信号 | 建议 `-1..1` |
| items[].p_base | 是 | object | 基线窗口分布 | 概率和约等于 `1` |
| items[].p_new | 是 | object | 重分布后窗口分布 | 概率和约等于 `1`，单窗口改变量不超过 `delta_max` |
| items[].kl_to_base | 是 | number | `KL(p_new || p_base)` | `>=0` |
| items[].policy_decision_trace | 是 | object | 策略可解释轨迹 | 非空对象 |

---

### 2.3 `GET /select-windows`

#### 请求参数表

| 参数 | 必填 | 类型 | 默认 | 约束 |
|---|---|---|---|---|
| keyword | 否 | string | 无 | 长度 `1..128`，与 `noun_group_ids` 至少提供一个 |
| noun_group_ids | 否 | string | 无 | 逗号分隔 ID 列表 |
| prompt_group_ids | 否 | string | 无 | 兼容字段；映射至 `noun_group_ids` |
| time_window | 否 | string | `7d` | 枚举：`24h`,`7d`,`14d`,`30d`,`90d` |
| min_overlap | 否 | number | `0.15` | `0..1` |
| target_overlap | 否 | number | `0.50` | `0..1` |
| eta | 否 | number | `0.30` | `0..2` |
| delta_max | 否 | number | `0.20` | `0..1` |
| tau | 否 | number | `1.0` | `0.1..10` |
| avoid_peak | 否 | boolean | `true` | 与 `/priority` 保持一致 |
| max_windows | 否 | integer | `5` | `1..48` |

#### 响应字段表（`data`）

| 字段 | 必填 | 类型 | 说明 | 约束 |
|---|---|---|---|---|
| selected_windows | 是 | array<object> | 选中窗口列表 | 长度 `<= max_windows` |
| selected_windows[].window_id | 是 | string | 窗口标识 | 非空 |
| selected_windows[].start_ts | 是 | string | 窗口开始时间 | ISO8601 |
| selected_windows[].end_ts | 是 | string | 窗口结束时间 | ISO8601 且 `end_ts > start_ts` |
| selected_windows[].score | 是 | number | 选择得分 | 实数 |
| selected_windows[].noun_group_id | 是 | string | 来源语义组 | 非空 |
| selected_windows[].vector_overlap | 是 | number | 重合度 | `0..1` |
| selected_windows[].shift_signal | 是 | number | 迁移信号 | 建议 `-1..1` |
| selected_windows[].p_base | 否 | object | 基线分布片段 | 如返回则概率合法 |
| selected_windows[].p_new | 否 | object | 新分布片段 | 如返回则概率合法 |
| selected_windows[].reason | 否 | string | 解释文本 | 长度 `<=256` |

### 3. JSON 示例

#### 3.1 正常返回示例（200）

```json
{
  "status": "ok",
  "data": {
    "items": [
      {
        "noun_group_id": "ng_1248",
        "vector_overlap": 0.62,
        "shift_signal": 0.18,
        "p_base": {
          "08:00-09:00": 0.30,
          "09:00-10:00": 0.40,
          "10:00-11:00": 0.30
        },
        "p_new": {
          "08:00-09:00": 0.34,
          "09:00-10:00": 0.29,
          "10:00-11:00": 0.37
        },
        "kl_to_base": 0.021,
        "policy_decision_trace": {
          "min_overlap": 0.15,
          "target_overlap": 0.5,
          "eta": 0.3,
          "delta_max": 0.2,
          "tau": 1.0,
          "avoid_peak": true
        }
      }
    ]
  },
  "error": null,
  "meta": {
    "request_id": "req_20260314_ab12cd34",
    "timestamp": "2026-03-14T10:20:30Z",
    "version": "v1",
    "duration_ms": 37
  }
}
```

#### 3.2 参数校验失败示例（422）

```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数校验失败",
    "retryable": false,
    "details": [
      {
        "field": "query.min_overlap",
        "reason": "must be between 0 and 1",
        "value": 1.2,
        "constraint": "0 <= min_overlap <= 1"
      },
      {
        "field": "query.target_overlap",
        "reason": "must be greater than or equal to min_overlap",
        "value": 0.1,
        "constraint": "target_overlap >= min_overlap"
      }
    ]
  },
  "meta": {
    "request_id": "req_20260314_ef56gh78",
    "timestamp": "2026-03-14T10:21:11Z",
    "version": "v1",
    "duration_ms": 4
  }
}
```
## 数据契约 + 实验评估闭环（OPE）加固草案

### 1. 目标与范围

本章节用于在既有 `API Contract + project_key 隔离 + observability` 基线上，补齐“可离线评估、可反事实对照、可门禁发布”的数据契约闭环，覆盖：
- 事件级日志契约（曝光、行为、收益、实验分流）
- 离线策略评估（Replay/IPS/SNIPS/DR/Switch-DR）
- 上线门禁（Go/No-Go）
- 反事实对照与因果风险防护
- 评估链路 observability 字段标准

---

### 2. 核心实体表结构定义（建议）

> 约定：所有事实表默认包含 `project_key`、`request_id`、`trace_id`、`schema_version`、`record_version`、`created_at`、`updated_at`。

#### 2.1 `dim_project`

- 主键：`project_id` (BIGINT)
- 维度键：`project_key` (UNIQUE), `tenant_id`, `region_code`
- 统计字段：`daily_active_users_7d`, `daily_req_qps_p95`
- 版本字段：`schema_version`, `record_version`, `is_current`
- 时间戳：`effective_from`, `effective_to`, `created_at`, `updated_at`
- 索引建议：
  - `UNIQUE(project_key)`
  - `INDEX(tenant_id, is_current)`
- TTL/回填策略：
  - 维表不做 TTL，SCD2 保留全量历史
  - 每日 01:00 对账回填缺失租户映射

#### 2.2 `dim_policy_version`

- 主键：`policy_version_id` (BIGINT)
- 维度键：`project_key`, `policy_id`, `model_name`, `feature_view`
- 统计字段：`offline_auc`, `calibration_ece`, `train_sample_cnt`
- 版本字段：`policy_semver`, `feature_semver`, `schema_version`, `record_version`, `is_current`
- 时间戳：`published_at`, `deployed_at`, `deprecated_at`, `created_at`, `updated_at`
- 索引建议：
  - `UNIQUE(project_key, policy_id, policy_semver)`
  - `INDEX(project_key, is_current, deployed_at DESC)`
- TTL/回填策略：
  - 不 TTL（作为审计基线）
  - 允许按 `policy_id + deployed_at` 回填历史元信息

#### 2.3 `fact_exposure_log`

- 主键：`exposure_id` (UUID)
- 维度键：`project_key`, `user_id`, `session_id`, `item_id`, `context_key`, `policy_version_id`, `experiment_id`, `arm_id`
- 统计字段：`rank_pos`, `score`, `propensity`, `candidate_set_size`, `latency_ms`
- 版本字段：`schema_version`, `record_version`, `feature_snapshot_version`
- 时间戳：`event_time`, `ingest_time`, `created_at`, `updated_at`
- 索引建议：
  - `INDEX(project_key, event_time DESC)`
  - `INDEX(experiment_id, arm_id, event_time)`
  - `INDEX(user_id, session_id, event_time)`
  - `INDEX(policy_version_id, event_time)`
- TTL/回填策略：
  - 明细保留 180 天，180 天后降采样为 5% 长留样本（用于漂移诊断）
  - T+1 回填延迟曝光（按 `request_id` 幂等 upsert）

#### 2.4 `fact_action_log`

- 主键：`action_id` (UUID)
- 维度键：`project_key`, `exposure_id`, `user_id`, `item_id`, `action_type`(click/like/save/share)
- 统计字段：`action_value`, `dwell_ms`, `scroll_depth`, `is_valid_action`
- 版本字段：`schema_version`, `record_version`
- 时间戳：`action_time`, `ingest_time`, `created_at`, `updated_at`
- 索引建议：
  - `INDEX(project_key, exposure_id)`
  - `INDEX(project_key, action_type, action_time DESC)`
  - `INDEX(user_id, action_time DESC)`
- TTL/回填策略：
  - 明细保留 365 天
  - 允许 7 天内迟到事件回填；超窗进入 `late_event_quarantine`

#### 2.5 `fact_reward_outcome`

- 主键：`reward_id` (UUID)
- 维度键：`project_key`, `exposure_id`, `user_id`, `reward_window`(1h/24h/7d)
- 统计字段：`reward`(FLOAT), `conversion_flag`, `revenue`, `cost`, `net_value`
- 版本字段：`reward_def_version`, `schema_version`, `record_version`
- 时间戳：`outcome_time`, `watermark_time`, `created_at`, `updated_at`
- 索引建议：
  - `INDEX(project_key, reward_window, outcome_time DESC)`
  - `INDEX(exposure_id, reward_window)`
- TTL/回填策略：
  - 明细保留 400 天（覆盖季节性）
  - 采用 watermark 回填：T+1、T+7、T+30 三次重算冻结

#### 2.6 `fact_experiment_assignment`

- 主键：`assignment_id` (UUID)
- 维度键：`project_key`, `experiment_id`, `arm_id`, `user_id`, `session_id`
- 统计字段：`traffic_ratio`, `bucket_id`, `eligibility_score`
- 版本字段：`assignment_algo_version`, `schema_version`, `record_version`
- 时间戳：`assigned_at`, `effective_from`, `effective_to`, `created_at`, `updated_at`
- 索引建议：
  - `UNIQUE(project_key, experiment_id, user_id, effective_from)`
  - `INDEX(experiment_id, arm_id, assigned_at)`
- TTL/回填策略：
  - 不 TTL（实验审计必须可追溯）
  - 仅允许“前向补录”，禁止覆盖历史分桶

#### 2.7 `fact_ope_eval_snapshot`

- 主键：`ope_snapshot_id` (UUID)
- 维度键：`project_key`, `experiment_id`, `target_policy_version_id`, `eval_slice`(global/device/channel)
- 统计字段：`replay_value`, `ips_value`, `snips_value`, `dr_value`, `switch_dr_value`, `ci_low`, `ci_high`, `effective_sample_size`, `weight_cv`
- 版本字段：`ope_method_version`, `reward_def_version`, `schema_version`, `record_version`
- 时间戳：`eval_data_from`, `eval_data_to`, `computed_at`, `created_at`, `updated_at`
- 索引建议：
  - `INDEX(project_key, experiment_id, computed_at DESC)`
  - `INDEX(target_policy_version_id, eval_data_to DESC)`
- TTL/回填策略：
  - 快照保留 730 天
  - 支持按“策略版本 + 时间窗”全量重算回填

---

### 3. OPE 设计：公式与使用条件

设日志样本为 \((x_i, a_i, r_i, p_b(a_i|x_i))\)，目标策略为 \(\pi\)，估计价值 \(V(\pi)=\mathbb{E}[r|a\sim\pi]\)。

#### 3.1 Replay（重放）

\[
\hat V_{Replay}=\frac{1}{N}\sum_{i=1}^{N} r_i\cdot \mathbf{1}[\pi(x_i)=a_i]
\]

- 使用条件：
  - 日志策略近似确定性且可复现排序/动作
  - 动作空间较小，匹配率不至于过低
- 优缺点：无权重方差问题，但样本利用率低。

#### 3.2 IPS（Inverse Propensity Scoring）

\[
\hat V_{IPS}=\frac{1}{N}\sum_{i=1}^{N}\frac{\mathbf{1}[\pi(x_i)=a_i] \cdot r_i}{p_b(a_i|x_i)}
\]

- 使用条件：
  - 日志必须记录可信 propensity，且满足 positivity（目标动作在日志中概率 > 0）
- 风险：小概率动作导致大权重，方差高。

#### 3.3 SNIPS（Self-Normalized IPS）

定义 \(w_i=\frac{\mathbf{1}[\pi(x_i)=a_i]}{p_b(a_i|x_i)}\)：
\[
\hat V_{SNIPS}=\frac{\sum_i w_i r_i}{\sum_i w_i}
\]

- 使用条件：同 IPS。
- 优点：较 IPS 更稳健；代价是引入轻微偏差。

#### 3.4 DR（Doubly Robust）

设 \(\hat q(x,a)\) 为奖励模型：
\[
\hat V_{DR}=\frac{1}{N}\sum_{i=1}^{N}\left[\hat q(x_i,\pi(x_i)) + \frac{\mathbf{1}[\pi(x_i)=a_i]}{p_b(a_i|x_i)}\big(r_i-\hat q(x_i,a_i)\big)\right]
\]

- 使用条件：
  - 有可用 reward model（可用交叉拟合减少过拟合偏差）
  - propensity 质量中等以上
- 优点：propensity 或 reward model 任一近似正确时仍一致（双稳健）。

#### 3.5 Switch-DR

设阈值 \(\tau\)，当权重过大时关闭校正项：
\[
\hat V_{SwitchDR}=\frac{1}{N}\sum_{i=1}^{N}\left[\hat q(x_i,\pi(x_i)) + \mathbf{1}\left(\frac{1}{p_b(a_i|x_i)}\le \tau\right)\cdot\frac{\mathbf{1}[\pi(x_i)=a_i]}{p_b(a_i|x_i)}\big(r_i-\hat q(x_i,a_i)\big)\right]
\]

- 使用条件：
  - 长尾权重明显（如 `weight_cv` 高、ESS 低）
  - 允许“轻偏差换低方差”
- 实务建议：同时报告 `tau`、权重截断比例、ESS。

---

### 4. Go/No-Go 阈值示例（上线门禁）

#### 4.1 一级门（离线 OPE）

- Go（全部满足）：
  - `Switch-DR uplift >= +2.0%`（相对当前策略）
  - `95% CI 下界 > 0`
  - `effective_sample_size / N >= 0.20`
  - `weight_cv <= 2.5`
  - 关键切片（新用户/低活跃/高价值）无负向显著退化
- No-Go（任一触发）：
  - `CI 下界 <= -0.5%`
  - 任一核心 guardrail（投诉率、延迟、成本）超阈
  - propensity 缺失率 `> 0.1%` 或 reward 对齐失败率 `> 0.5%`

#### 4.2 二级门（在线小流量）

- 5% 流量灰度 24~72h：
  - 主指标 uplift 与离线方向一致
  - 延迟 p95 不劣于基线超过 10ms
  - 业务风险指标（bad case）不显著上升

---

### 5. 反事实对照方案与因果风险

#### 5.1 反事实对照方案

1. Shadow Replay（推荐基线）
- 线上仍用旧策略出结果，新策略仅旁路打分并记录候选与 propensity。
- 用同一批真实上下文做离线 Replay/IPS/DR 对照。

2. Switchback（时段切换）
- 以小时/天为单位在同一流量池交替启用策略 A/B，降低用户层干扰。
- 适用于强网络外部性场景（用户间互相影响明显）。

3. 分层重加权对照
- 按 `device/channel/user_cohort` 分层计算 SNIPS/DR，再做分层汇总，防止样本构成漂移误导结论。

#### 5.2 关键因果风险

- 未观测混杂：日志未记录的上下文变量同时影响动作与奖励。
- Positivity 破坏：目标策略选择了日志几乎未覆盖动作。
- SUTVA/干扰：一个用户的曝光影响其他用户反馈（社交传播）。
- 奖励延迟与删失：长窗口转化尚未成熟导致低估。
- 策略/环境漂移：评估窗与上线窗分布不同（节假日、热点事件）。

#### 5.3 风险缓解

- 强制记录完整 propensity 与候选集摘要。
- 评估前做 overlap 检查：低覆盖切片直接 No-Go。
- 使用多估计器一致性检查：Replay/IPS/SNIPS/DR/Switch-DR 同向才进入灰度。
- 奖励采用多窗口（1h/24h/7d）并给出成熟度标签。

---

### 6. Observability 字段清单（评估闭环最小集合）

#### 6.1 请求与上下文

- `request_id`, `trace_id`, `span_id`
- `project_key`, `tenant_id`, `region_code`
- `user_id_hash`, `session_id`, `device_type`, `channel`, `locale`
- `api_route`, `http_status`, `latency_ms`

#### 6.2 策略与实验

- `policy_id`, `policy_semver`, `policy_version_id`
- `experiment_id`, `arm_id`, `bucket_id`, `traffic_ratio`
- `assignment_algo_version`, `feature_snapshot_version`

#### 6.3 决策与概率

- `action`, `action_rank`, `score`
- `propensity`, `propensity_source`(model/rule/fallback)
- `candidate_set_size`, `candidate_hash`
- `weight_raw`, `weight_clipped`, `clip_tau`

#### 6.4 反馈与收益

- `action_type`, `action_value`, `dwell_ms`
- `reward`, `reward_window`, `reward_def_version`
- `conversion_flag`, `revenue`, `cost`, `net_value`
- `outcome_maturity`(immature/partial/mature)

#### 6.5 评估结果与质量

- `ope_method`, `ope_method_version`
- `value_estimate`, `ci_low`, `ci_high`
- `effective_sample_size`, `weight_cv`, `overlap_ratio`
- `propensity_missing_rate`, `join_success_rate`, `late_event_rate`
- `data_quality_status`(pass/warn/fail), `quality_reason`

#### 6.6 告警与门禁状态

- `gate_name`, `gate_result`(go/no-go)
- `guardrail_name`, `guardrail_delta`, `guardrail_threshold`
- `rollback_recommendation`, `owner`, `computed_at`

---

### 7. 最小落地顺序（建议）

1. 先打通四张事实表：`exposure/action/reward/assignment`，并确保 `request_id + exposure_id` 可闭环关联。
2. 上线 `SNIPS + DR + Switch-DR` 三估计器并行日报（先不做自动门禁）。
3. 连续两周稳定后启用 Go/No-Go 自动判定，再接入 5% 灰度流程。
4. 每次策略发布必须附带：`ope_snapshot + observability 抽样证据 + guardrail 报告`。

## 11. 参考与实现映射注册表（Reference + Implementation Registry）

### 11.1 参考资料注册表（本地文档）

1. `ARCHIVE_01_04/01_merged-remediation-and-smart-timestamp-plan-2026-03-14.md`
- 用途：问题定义、时窗与时间统计修复口径。

2. `ARCHIVE_01_04/02_research-report-density-cloud-overlap-avoid-peak-2026-03-14.md`
- 用途：密度云、重叠度门控、软避峰策略研究结论。

3. `ARCHIVE_01_04/03_unified-research-and-design-report-density-cloud-overlap-shift-2026-03-14.md`
- 用途：统一术语、目标函数口径、实验方向。

4. `ARCHIVE_01_04/04_backend-interface-change-checklist-density-cloud-overlap-shift-2026-03-14.md`
- 用途：接口变更与代码差异核对清单。

### 11.2 实现路径注册表（当前仓库）

1. API 入口
- `main/backend/app/api/stats.py`
- 覆盖：`/prompt-time-density`、`/cloud`、`/priority`、`/select-windows`。

2. 核心服务
- `main/backend/app/services/stats/prompt_time_density.py`
- 覆盖：
  - `query_prompt_time_density(...)`
  - `query_prompt_time_density_cloud(...)`
  - `query_prompt_time_density_priority(...)`
  - `redistribute_window_probabilities(...)`
  - 日志持久化逻辑

3. 任务链路
- `main/backend/app/services/tasks.py`
- 覆盖：`task_select_prompt_time_windows(...)`。

4. 数据模型
- `main/backend/app/models/entities.py`
- 覆盖：`PromptTimePolicyDecisionLog` 与相关字段定义。

5. 迁移脚本
- `main/backend/migrations/versions/20260312_000008_add_prompt_time_policy_decision_logs.py`
- 覆盖：策略决策日志与反馈表落库结构。

6. 测试契约
- `main/backend/tests/core_business/test_api_group_a_core_contract.py`
- `main/backend/tests/core_business/test_process_consistency_core_contract.py`
- 覆盖：priority/select-windows/cloud 关键字段契约与错误路径。

7. 离线与门禁脚本
- `main/backend/scripts/run_prompt_time_density_ope.py`
- `main/backend/scripts/generate_prompt_time_density_gonogo.py`
- 覆盖：OPE 评估与 Go/No-Go 报告生成。

### 11.3 章节到实现的直接映射

1. 第 1-4 章（当前代码事实、主链路）：见 `api/stats.py` + `services/stats/prompt_time_density.py`。
2. 第 5 章（接口契约）：见 `api/stats.py` 与 core contract tests。
3. 第 6-7 章（补强项与执行清单）：对应 06 原子任务单与 `tests/`、`scripts/`。
4. 新增“接口契约硬化”章节：落地到 API 参数校验、错误码、响应 envelope。
5. 新增“数据契约 + OPE”章节：落地到 `entities/migrations/scripts` 三层。

### 11.4 一致性校验规则（文档维护）

1. 文档中出现的新字段，必须在以下三处至少两处可追溯：
- API/Service 代码
- DB 模型或迁移
- 核心契约测试

2. 文档中出现的新策略参数，必须具备：
- 默认值与范围
- 生效路径（函数/模块）
- 回滚路径（配置或开关）

3. 文档中出现的新评估指标，必须具备：
- 计算来源
- 输出位置（脚本/报告）
- 门禁阈值用途
