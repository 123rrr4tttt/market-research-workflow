# 可执行计划 + 任务清单编排（Prompt-Space × Time-Window Density）

## 1. 目标与范围

- 目标：在现有时间统计修复基础上，落地“提示词空间 × 时间窗密度”可执行能力。
- 交付：
  - 后端密度统计 API
  - 低密度优先调度 API
  - 前端筛选联动与一致性
  - 实际案例测试脚本与回归门禁
- 非目标：本轮不做大规模 schema 重构，不替换现有全链路存储模型。

## 2. 执行节奏（L0-L3）

### L0 串行冻结（Day 1）

- 冻结字段与契约：`source_domain/prompt_group_id/bucket_time/effective_new_docs/density/norm_density/dup_ratio/collection_priority_score/rank`
- 冻结错误码：`INVALID_INPUT`、`CONTRACT_VIOLATION`、`UPSTREAM_ERROR`
- 门禁：
  - `python3 -m compileall main/backend/app/api main/backend/app/services`

### L1 并行开发（Day 2-3）

- Track A（统计聚合）
- Track B（优先级调度）
- Track C（前端联动）
- Track D（观测与日志）
- 门禁（每任务至少一项）：`pytest`/`lint`/契约断言

### L2 串行集成（Day 4）

- 合并冲突、统一契约、补齐跨模块测试
- 统一回归：
  - `cd main/backend && python3.11 -m pytest -q tests/core_business/test_api_group_b_core_contract.py tests/core_business/test_admin_dashboard_process_core_contract.py tests/core_business/test_process_consistency_core_contract.py`

### L3 实测发布（Day 5）

- 真实案例测试（至少 8 case）
- 输出 `realcase_report.json`
- 达标后进入发布窗口

## 3. 8 Agent 并行编排

| Agent | 任务域 | 主要文件/模块 | 产出 |
|---|---|---|---|
| A1 | API 契约 | `main/backend/app/api/stats*.py` | 统计/优先级接口定义 |
| A2 | 聚合服务 | `main/backend/app/services/stats/*` | density/norm_density 计算 |
| A3 | 调度服务 | `main/backend/app/services/tasks.py` `collect_runtime/*` | priority 排序与过滤 |
| A4 | 时间语义 | `main/backend/app/api/policies.py` `services/report.py` | effective_time 口径对齐 |
| A5 | 前端现代页 | `main/frontend-modern/src/pages/*` `src/lib/*` | 筛选、缓存键、错误展示 |
| A6 | 前端模板页 | `main/frontend/templates/*` | legacy 参数兼容 |
| A7 | 测试与实测 | `main/backend/tests/*` `main/backend/scripts/*` | 真实案例脚本与断言 |
| A8 | 观测与门禁 | CI/日志/报表脚本 | 指标与回归报告 |

并发约束：
- 同文件冲突禁止并行落盘。
- 依赖链：A1 -> (A2,A3,A5,A6) -> A7 -> A8。

## 4. 原子任务清单（可直接执行）

### T01 契约冻结

- 目标：冻结 API 字段和错误码。
- depends_on: `[]`
- 并行组：`L0-serial`
- module_input_vars: `in_api_schema_version(str)` `in_error_code_set(list[str])`
- module_output_vars: `out_contract_doc(md)` `out_openapi_delta(json)`
- io_boundary: `api/stats*.py` `development/latest-dev-docs/*`
- 最小门禁：`cd main/backend && python3.11 -m pytest -q tests/contract/test_openapi_contracts_unittest.py`
- 验收：字段名、类型、错误码一致。

### T02 统计 API（density）

- 目标：实现 `GET /api/v1/stats/prompt-time-density`。
- depends_on: `[T01]`
- 并行组：`L1-A`
- module_input_vars: `in_start(datetime?)` `in_end(datetime?)` `in_time_window(str?)` `in_bucket(str)` `in_source_domains(list[str]?)` `in_prompt_group_ids(list[str]?)` `in_normalize(bool)`
- module_output_vars: `out_items(list)` `out_total(int)`
- io_boundary: `main/backend/app/api/stats*.py` `main/backend/app/services/stats/*`
- 最小门禁：`python3 -m compileall main/backend/app/api main/backend/app/services/stats`
- 验收：返回 `density/norm_density/dup_ratio`。

### T03 基线密度服务

- 目标：实现 `baseline_density(g, W_ref=90d)`。
- depends_on: `[T01]`
- 并行组：`L1-A`
- module_input_vars: `in_prompt_group_id(str)` `in_ref_window(str)`
- module_output_vars: `out_baseline_density(float)`
- io_boundary: `main/backend/app/services/stats/*`
- 最小门禁：`cd main/backend && python3.11 -m pytest -q tests/core_business -k density`
- 验收：`norm_density = density / max(baseline, epsilon)`。

### T04 重复率折算

- 目标：按 `text_hash` 计算 `dup_ratio` 与 `effective_new_docs`。
- depends_on: `[T01]`
- 并行组：`L1-A`
- module_input_vars: `in_docs(list)`
- module_output_vars: `out_dup_ratio(float)` `out_effective_new_docs(int)`
- io_boundary: `main/backend/app/services/stats/*`
- 最小门禁：`cd main/backend && python3.11 -m pytest -q tests -k dup_ratio`
- 验收：公式可复现，边界无 NaN。

### T05 priority API

- 目标：实现 `GET /api/v1/stats/prompt-time-density/priority`。
- depends_on: `[T02,T03,T04]`
- 并行组：`L1-B`
- module_input_vars: `in_candidate_windows(list[str])` `in_prefer_low_density(bool)` `in_exclude_high_dup(bool)`
- module_output_vars: `out_priority_rows(list)`
- io_boundary: `main/backend/app/api/stats*.py` `main/backend/app/services/tasks.py`
- 最小门禁：`cd main/backend && python3.11 -m pytest -q tests -k priority`
- 验收：`rank` 与 `collection_priority_score` 单调一致。

### T06 调度接入

- 目标：采集调度默认支持低密度优先。
- depends_on: `[T05]`
- 并行组：`L1-B`
- module_input_vars: `in_priority_rows(list)` `in_budget(int)`
- module_output_vars: `out_selected_windows(list)`
- io_boundary: `main/backend/app/services/collect_runtime/*` `main/backend/app/services/tasks.py`
- 最小门禁：`cd main/backend && python3.11 -m pytest -q tests -k schedule`
- 验收：低密度窗口选中率 >= 70%。

### T07 前端 modern 联动

- 目标：时间窗+提示词组筛选联动 density API，规范 query key。
- depends_on: `[T02,T05]`
- 并行组：`L1-C`
- module_input_vars: `in_time_window(str)` `in_prompt_group_ids(list[str])` `in_source_domains(list[str])`
- module_output_vars: `out_query_key(array)` `out_chart_series(list)`
- io_boundary: `main/frontend-modern/src/pages/*` `main/frontend-modern/src/lib/*`
- 最小门禁：`cd main/frontend-modern && npm run -s lint`
- 验收：切窗后图表刷新且无缓存污染。

### T08 前端 legacy 兼容

- 目标：模板页支持新参数与兼容参数并行。
- depends_on: `[T02]`
- 并行组：`L1-C`
- module_input_vars: `in_start(str?)` `in_end(str?)` `in_time_window(str?)`
- module_output_vars: `out_request_query(str)`
- io_boundary: `main/frontend/templates/*.html`
- 最小门禁：`rg -n "time_window|prompt_group|source_domains" main/frontend/templates`
- 验收：legacy 页面结果与后端一致。

### T09 非法输入硬化

- 目标：日期/bucket/候选窗口非法输入返回稳定 4xx。
- depends_on: `[T01]`
- 并行组：`L1-D`
- module_input_vars: `in_invalid_params(case-set)`
- module_output_vars: `out_error_status(int)` `out_error_code(str)`
- io_boundary: `main/backend/app/api/*.py` `tests/core_business/*`
- 最小门禁：`cd main/backend && python3.11 -m pytest -q tests/core_business -k invalid`
- 验收：无 silent fallback。

### T10 实际案例测试脚本

- 目标：新增一键实测脚本（至少 8 case）。
- depends_on: `[T02,T05,T07,T09]`
- 并行组：`L2-serial`
- module_input_vars: `in_case_set(str)` `in_project_key(str)` `in_base_url(str)`
- module_output_vars: `out_realcase_report(json)` `out_failed_cases(list)`
- io_boundary: `main/backend/scripts/*` `main/backend/tests/*`
- 最小门禁：`python3.11 main/backend/scripts/run_realcase_prompt_time_density.py --project demo_proj --case-set all --fail-fast`
- 验收：8+ case 全通过。

### T11 前后端一致性对账

- 目标：同窗口下 API 与前端图表值一致。
- depends_on: `[T07,T10]`
- 并行组：`L2-serial`
- module_input_vars: `in_api_snapshot(json)` `in_ui_snapshot(json)`
- module_output_vars: `out_diff_report(md)`
- io_boundary: `main/frontend-modern/*` `main/backend/scripts/*`
- 最小门禁：`cd main/frontend-modern && npm run -s test -- GraphPage`
- 验收：抽样 10 组零差异（允许显示层四舍五入）。

### T12 发布门禁与回滚点

- 目标：形成 Go/No-Go 报告和回滚命令。
- depends_on: `[T10,T11]`
- 并行组：`L3-serial`
- module_input_vars: `in_test_report(json)` `in_perf_metrics(json)`
- module_output_vars: `out_release_decision(str)` `out_rollback_steps(md)`
- io_boundary: `development/latest-dev-docs/*` `ops scripts`
- 最小门禁：聚合执行 T02/T05/T07/T10/T11 的全部命令
- 验收：P95 <= 1.5s、错误率达标、报告归档。

## 5. 失败隔离与回传规范

- 失败隔离：单任务失败仅重试本任务（最多 2 次，仅瞬时故障可重试）。
- 回传格式（所有 Agent 固定）：
  - `结果`: pass/fail
  - `改动文件`: list
  - `验证状态`: command + summary
  - `风险`: blocking/non-blocking
- 冲突处理：同文件冲突进入 merge queue，由依赖后置任务串行合并。

## 6. 实际案例测试编排（最低集）

- C1 基础命中（单域单组）
- C2 跨域密度对比
- C3 重复折算（dup_ratio）
- C4 边界时间窗（start/end）
- C5 非法日期
- C6 非法 bucket
- C7 priority 排序
- C8 前后端一致性

执行前置条件：

- 当前目录在仓库根目录（`market-research-workflow-parallel-20260303-215619`）。
- Python 3.11 可用，且后端依赖已安装。
- 前端 modern 依赖已安装（`npm ci` 或等价）。
- 若使用 `--base-url` 访问在线服务，需保证服务可访问。

一键执行命令（相对路径）：

```bash
cd main/backend && \
python3.11 -m pytest -q \
  tests/core_business/test_api_group_b_core_contract.py \
  tests/core_business/test_admin_dashboard_process_core_contract.py \
  tests/core_business/test_process_consistency_core_contract.py

python3.11 scripts/run_realcase_prompt_time_density.py \
  --project demo_proj \
  --base-url http://127.0.0.1:8000 \
  --case-set all \
  --fail-fast

cd ../frontend-modern && \
npm run -s lint && \
npm run -s test -- GraphPage
```

成功标准：

- 后端 pytest 退出码为 `0`。
- realcase 报告中 `failed=0`。
- 前端 lint/test 退出码为 `0`。

## 7. 通过标准

- 必过：T01~T12 全部完成，C1~C8 全通过。
- 指标：
  - `norm_density` 计算成功率 >= 99.5%
  - 低密度窗口优先命中率 >= 70%
  - 常用窗口统计 API P95 <= 1.5s
