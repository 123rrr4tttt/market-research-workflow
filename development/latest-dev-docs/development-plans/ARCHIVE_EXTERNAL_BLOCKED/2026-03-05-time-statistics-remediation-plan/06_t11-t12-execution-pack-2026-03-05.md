# T11/T12 Execution Pack (2026-03-05)

## 1. 目标

- T11：提供 API 与 UI 快照的自动对账工具，输出可审计 diff 报告。
- T12：提供 Go/No-Go 决策与回滚模板生成工具，形成发布门禁最小闭环。

## 2. 交付文件

- 对账脚本：`main/backend/scripts/compare_prompt_time_density_snapshots.py`
- 门禁脚本：`main/backend/scripts/generate_prompt_time_density_gonogo.py`
- 实测报告：`main/backend/.artifacts/realcase_prompt_time_density_report.json`

## 3. 模块 IO 契约

### T11 对账脚本

- module_input_vars:
  - `in_api_snapshot(json file)`
  - `in_ui_snapshot(json file)`
  - `in_tolerance(float, default=1e-6)`
- module_output_vars:
  - `out_diff_report(md file)`
  - `out_status(str: PASS/FAIL)`
- io_mapping:
  - `in_api_snapshot + in_ui_snapshot -> out_diff_report`
- io_boundary:
  - read: snapshot json files
  - write: `.artifacts/prompt_time_density_diff_report.md`

### T12 门禁脚本

- module_input_vars:
  - `in_realcase_report(json file)`
  - `in_perf_metrics(json file)`
  - `in_p95_threshold(float, default=1.5)`
  - `in_error_rate_threshold(float, default=0.01)`
- module_output_vars:
  - `out_release_decision(str: GO/NO-GO)`
  - `out_gonogo_report(md file)`
- io_mapping:
  - gate_realcase + gate_p95 + gate_error -> `out_release_decision`
- io_boundary:
  - read: reports/metrics json
  - write: `.artifacts/prompt_time_density_gonogo.md`

## 4. 可执行命令

```bash
cd main/backend

# T11: API/UI 对账（示例路径）
python3.11 scripts/compare_prompt_time_density_snapshots.py \
  --api .artifacts/api_snapshot.json \
  --ui .artifacts/ui_snapshot.json \
  --output .artifacts/prompt_time_density_diff_report.md

# T12: Go/No-Go 报告生成
python3.11 scripts/generate_prompt_time_density_gonogo.py \
  --realcase .artifacts/realcase_prompt_time_density_report.json \
  --perf .artifacts/perf_metrics.json \
  --output .artifacts/prompt_time_density_gonogo.md
```

## 5. 结果判定

- T11 通过：脚本退出码 `0` 且 diff 报告状态为 `PASS`。
- T12 通过：脚本退出码 `0` 且决策为 `GO`。

## 6. 回滚锚点

- 回滚范围仅限本轮新增时间密度能力：
  - `main/backend/app/api/stats.py`
  - `main/backend/app/services/stats/*`
  - `main/backend/app/services/tasks.py`（time-density 调度入口）
- 回滚后必须重跑：
  - core contract tests（prompt_time_density 相关）
  - `run_realcase_prompt_time_density.py`
