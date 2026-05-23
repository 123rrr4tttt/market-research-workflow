# Prompt-Space × Time-Window Density Spec (2026-03-05)

## 1. 结论（先读）

- 现有开发文档已包含 `noun-space × time-window density` 的规划与公式。
- 当前仓库实现仍以时间窗和图时间参数修复为主，尚未形成统一可调用的密度聚合 API 与默认调度策略。
- 本文档补齐“可落地规范 + 模块 IO + 小范围实测口径”，作为本轮开发直接执行依据。

## 2. 目标范围

- 统计维度：`source_domain × prompt_group × time_bucket`。
- 指标维度：`effective_new_docs / density / norm_density / dup_ratio / collection_priority_score`。
- 产出维度：
  - 统计 API（查询密度）
  - 调度 API（低密度窗口优先）
  - 最小实测用例（真实入库 + 查询 + 断言）

## 3. 统一术语

- `prompt_group`：提示词空间分组（可由关键词、同义词、模板 prompt 绑定形成）。
- `time_window`：查询时间窗，当前实现支持 `Nd`（如 `7d/30d/90d`）；`custom` 口径通过 `start+end` 显式传参实现。
- `time_bucket`：桶粒度，支持 `day/week/month`。
- `effective_time`：统一时间语义字段（优先业务时间，回退到发布时间/创建时间）。

## 4. 指标定义

- `effective_new_docs(d,g,W)`：域 `d`、提示词组 `g`、窗口 `W` 内的有效新增文档数。
- `window_days(W)`：窗口天数。
- `density(d,g,W) = effective_new_docs(d,g,W) / window_days(W)`。
- `baseline_density(g,W_ref)`：提示词组 `g` 在参考窗 `W_ref`（默认近 90 天）全域日均值。
- `norm_density(d,g,W) = density(d,g,W) / max(baseline_density(g,W_ref), epsilon)`。
- `dup_ratio(d,g,W) = duplicate_docs / total_docs`。
- `collection_priority_score`（越小越优先）：
  - `score = w1*norm_density + w2*dup_ratio + w3*freshness_penalty`
  - 默认 `w1=0.6, w2=0.3, w3=0.1`。

## 5. API 契约（新增）

### 5.1 查询密度

- `GET /api/v1/stats/prompt-time-density`
- Query:
  - `time_window` | `start` + `end`
  - `bucket`
  - `source_domains[]`
  - `prompt_group_ids[]`
  - `normalize=true|false`
- Response `data.items[]`:
  - `source_domain`
  - `prompt_group_id`
  - `bucket_time`
  - `effective_new_docs`
  - `density`
  - `baseline_density`
  - `norm_density`
  - `dup_ratio`

### 5.2 调度优先级

- `GET /api/v1/stats/prompt-time-density/priority`
- Query:
  - `candidate_windows[]`
  - `prefer_low_density=true|false`（默认 true）
  - `exclude_high_dup=true|false`（默认 true）
- Response `data.items[]`:
  - `source_domain`
  - `prompt_group_id`
  - `window`
  - `norm_density`
  - `dup_ratio`
  - `collection_priority_score`
  - `rank`

## 6. 模块 IO（任务级）

### Task PTD-A: 密度聚合服务

- module_input_vars:
  - `in_start_date(datetime?)`
  - `in_end_date(datetime?)`
  - `in_time_window(str?)`
  - `in_bucket(str)`
  - `in_source_domains(list[str]?)`
  - `in_prompt_group_ids(list[str]?)`
  - `in_normalize(bool)`
- module_output_vars:
  - `out_density_rows(list[dict])`
  - `out_total_rows(int)`
  - `out_compute_ms(int)`
- io_mapping:
  - `in_*` -> `out_density_rows[*].{density,norm_density,dup_ratio}`
- io_boundary:
  - `main/backend/app/services/stats/*`
  - `main/backend/app/api/stats*.py`

### Task PTD-B: 低密度优先调度

- module_input_vars:
  - `in_candidate_windows(list[str])`
  - `in_prefer_low_density(bool)`
  - `in_exclude_high_dup(bool)`
  - `in_source_domains(list[str]?)`
  - `in_prompt_group_ids(list[str]?)`
- module_output_vars:
  - `out_priority_rows(list[dict])`
  - `out_ranked_windows(list[str])`
- io_mapping:
  - `in_*` -> `out_priority_rows[*].collection_priority_score/rank`
- io_boundary:
  - `main/backend/app/services/tasks.py`
  - `main/backend/app/services/collect_runtime/*`

### Task PTD-C: 实测与回归

- module_input_vars:
  - `in_fixture_docs(fixture)`
  - `in_time_window(tuple)`
  - `in_invalid_params(case-set)`
- module_output_vars:
  - `out_passed(int)`
  - `out_failed(int)`
  - `out_realcase_report(file)`
- io_mapping:
  - 每个 `in_invalid_params` 都必须产生稳定 `4xx + error_code`
- io_boundary:
  - `main/backend/tests/core_business/*`

## 7. 串并行执行规范（补齐）

- L0 串行：冻结 API 契约与字段命名。
- L1 并行：
  - Track-1 聚合查询
  - Track-2 调度排序
  - Track-3 前端筛选联动
- L2 串行：合并冲突 + 实测回归。
- 并行限制：同文件冲突任务不得并行落盘。
- 失败隔离：单任务失败仅重试本任务，不阻塞其他轨道。

## 8. 小范围实测清单（必须执行）

1. 正常窗口命中
- 构造 A/B/C/D 四类文档（命中、回退命中、跨窗、不命中）。
- 断言 `density` 与命中集一致。

2. 规范化密度
- 同一 `prompt_group` 在高/低采样域分别断言 `norm_density` 大小关系。

3. 调度优先级
- `prefer_low_density=true` 时，低 `norm_density` 窗口 rank 更靠前。

4. 非法参数
- 非法日期、非法 bucket、空窗口，均返回确定性 `4xx` 与错误码。

## 9. 验收门槛

- 统计 API P95 <= 1.5s（常用窗口，样本 >= 10k 文档）。
- `norm_density` 计算成功率 >= 99.5%。
- 低密度窗口优先命中率 >= 70%（默认策略）。
- 前后端同窗口口径一致（抽样 10 组，全部通过）。

## 10. 与现有计划关系

- 本文是 `2026-03-05-time-statistics-remediation-plan` 的执行补充，不替代 `2026-03-02` 的总体方案文档。
- 若后续进入 schema 升级，再升级为独立里程碑文档。
