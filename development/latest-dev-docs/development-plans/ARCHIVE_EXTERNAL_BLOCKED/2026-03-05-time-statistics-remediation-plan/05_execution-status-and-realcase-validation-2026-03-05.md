# Time-Statistics Remediation: 执行状态与实测对账（2026-03-05）

## 1. 对账结论

- 已完成“计划文档 + 原子任务清单 + 串并行规范 + 任务模块 IO 划定”的文档化落盘。
- `prompt-space × time-window density` 已落地后端 API、服务层、前端联动与核心契约测试。
- 已执行实际案例测试（8 case），结果 `8/8` 通过。

## 2. 开发记录与代码实现映射

开发记录基线（同目录）：
- `01_time-statistics-remediation-plan-2026-03-05.md`
- `02_atomic-tasklist-time-statistics-remediation-2026-03-05.md`
- `03_prompt-space-time-window-density-spec-2026-03-05.md`
- `04_executable-plan-task-orchestration-prompt-time-density-2026-03-05.md`

实现落点（代码）：
- 后端 API：`main/backend/app/api/stats.py`
- 统计服务：`main/backend/app/services/stats/prompt_time_density.py`
- 调度接入：`main/backend/app/services/tasks.py`
- 路由注册：`main/backend/app/api/__init__.py`
- 核心测试：`main/backend/tests/core_business/test_api_group_a_core_contract.py`
- 核心测试：`main/backend/tests/core_business/test_process_consistency_core_contract.py`
- 实测脚本：`main/backend/scripts/run_realcase_prompt_time_density.py`
- 前端 modern：`main/frontend-modern/src/lib/api.ts`
- 前端 modern：`main/frontend-modern/src/lib/queryKeys.ts`
- 前端 modern：`main/frontend-modern/src/pages/PolicyPage.tsx`
- 前端 legacy：`main/frontend/templates/policy-tracking.html`
- 前端 legacy：`main/frontend/templates/data-dashboard.html`

## 3. 原子任务编排状态（T01-T12）

| Task | 状态 | 结果摘要 |
|---|---|---|
| T01 契约冻结 | done | 错误码与字段在 stats API 中已固化，422 输入校验已覆盖 |
| T02 统计 API（density） | done | `/api/v1/stats/prompt-time-density` 已可用 |
| T03 基线密度服务 | done | baseline/norm_density 计算已接入服务层 |
| T04 重复率折算 | done | dup_ratio 采用 `text_hash` + `uri` 回退策略 |
| T05 priority API | done | `/api/v1/stats/prompt-time-density/priority` 已可用 |
| T06 调度接入 | done | `task_select_prompt_time_windows` 已接入 |
| T07 前端 modern 联动 | done | PolicyPage 已支持密度优先级查询与展示 |
| T08 前端 legacy 兼容 | done | 日期参数双写（`start/end` + `start_date/end_date`） |
| T09 非法输入硬化 | done | 非法 bucket/window 返回稳定 422 |
| T10 实际案例测试脚本 | done | `run_realcase_prompt_time_density.py` 已落地 |
| T11 前后端一致性对账 | in_progress | 已新增 API/UI 快照自动对账脚本，待接入真实 UI 快照流水线 |
| T12 发布门禁与回滚点 | in_progress | 已新增 Go/No-Go 报告脚本与回滚模板，待接入真实 perf 指标 |

## 4. 任务模块 IO 规范落地检查

- 已在计划文档中按任务声明：
  - `module_input_vars`
  - `module_output_vars`
  - `io_mapping`
  - `io_boundary`
- 变量命名前缀 `in_* / out_* / tmp_*` 规则已进入开发规范（`codex_settings/AGENTS.md`）。
- 串并行层级 `L0/L1/L2` 与 `depends_on/blocks` 规则已进入开发规范与任务编排文档。

## 5. 小范围实测（实际案例）

执行日期：`2026-03-05`（PST）

执行命令：

```bash
cd main/backend
python3.11 scripts/run_realcase_prompt_time_density.py --project demo_proj --case-set all --fail-fast
python3.11 -m pytest -q tests/core_business/test_api_group_a_core_contract.py tests/core_business/test_process_consistency_core_contract.py -k "prompt_time_density or invalid"
```

结果摘要：
- realcase：`total=8, passed=8, failed=0`
- pytest：`7 passed, 5 deselected`

逐案例可审计记录：

| Case | 输入/场景 | 期望 | 实际 | 结论 |
|---|---|---|---|---|
| C1 | density 正常查询 | `status=200` | `density status=200` | pass |
| C2 | density 数据量校验 | items > 0 | `density items=2` | pass |
| C3 | 非法 bucket | `422` | `invalid bucket status=422` | pass |
| C4 | 非法 time_window | `422` | `invalid window status=422` | pass |
| C5 | priority 正常查询 | `status=200` | `priority status=200` | pass |
| C6 | priority 返回项校验 | items > 0 | `priority items=4` | pass |
| C7 | priority 排序校验 | rank 有序 | `priority ranks are sorted` | pass |
| C8 | priority 非法窗口 | `422` | `invalid priority status=422` | pass |

实测报告：
- `main/backend/.artifacts/realcase_prompt_time_density_report.json`

T11/T12 产物：
- `main/backend/scripts/compare_prompt_time_density_snapshots.py`
- `main/backend/scripts/generate_prompt_time_density_gonogo.py`
- `06_t11-t12-execution-pack-2026-03-05.md`

## 6. 当前剩余风险与后续建议

- T11/T12 当前阻塞项如下：
  - T11：
    - `blocked_by`: 缺少稳定 UI 快照断言基线（Graph/Policy 图表数值比对未脚本化）
    - owner: Frontend QA + API Contract
    - target_date: 2026-03-08
  - T12：
    - `blocked_by`: 尚未形成统一 Go/No-Go 模板（性能阈值、回滚命令、发布检查清单）
    - owner: Backend Ops + Release
    - target_date: 2026-03-09
- 前端 modern 相关文件存在超出本任务的历史改动，后续建议在单独分支做一次范围收敛与差异清理。
