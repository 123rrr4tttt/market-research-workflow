<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-04-r12-a-line/02_atomic-task-table-r12-a.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-04-r12-a-line/02_atomic-task-table-r12-a.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# R12 A线 M1 Atomic Task Table（2026-03-04）

## research
- scout_batch_id: `2026-03-04-scout-r12`
- TaskID: `A-R12-M1`
- 目标：引入稳定性预算计算并产出 `flake-budget.json`（`flake_rate` / `rerun_pass_rate` / `test_determinism_score`）。
- 约束：仅 A 线最小切片；本轮仅 `warning` 灰度；不启用 blocking；禁止无限 rerun 掩盖失败；failure isolation 仅限 A 线。

## plan
- P1（并行）：
  - 原子任务 T1：扩展 `flake_trend.py` 输出三指标与 `budget` 区块（兼容旧字段）。
  - 原子任务 T2：扩展 `check_flake_trend_thresholds.py` 增加 `--mode warning|blocking`，M1 使用 warning。
  - 原子任务 T3：更新 `backend-tests.yml`，落地 `flake-budget.json` 工件并保持观察链路不阻断。
- P2（串行）：补齐单测与本地验证，生成目标绝对路径工件，记录 rollback。

## atomic
| task_id | goal | input | output | acceptance |
|---|---|---|---|---|
| A-R12-M1-T1 | 三指标预算计算 | `main/backend/scripts/flake_trend.py` | `totals`/`items`/`budget` 含三指标 | 单测通过且旧字段仍可读 |
| A-R12-M1-T2 | warning 灰度门禁 | `main/backend/scripts/check_flake_trend_thresholds.py` | `--mode warning` 返回 0，状态 `warn/pass` | 不阻断本轮 |
| A-R12-M1-T3 | 产出机读工件 | `.github/workflows/backend-tests.yml` | `artifacts/gates/r12_a/flake-budget.json` | 文件存在且含三指标 |

原子任务并行序列：
- Phase P1: `[A-R12-M1-T1, A-R12-M1-T2, A-R12-M1-T3]`
- Phase P2: `[A-R12-M1-VER, A-R12-M1-CLOSE]`（depends_on: P1）

## ver
- 最小验证命令在 `03_impl-verification-r12-a.md` 固化。
- M1 验证口径：必须看到 `flake-budget.json` 三指标且 gate 结果为 warning/pass（非 blocking）。

## close
- rollback_ref: `400beb9f7d3dd10940daabdb7deea0bed3f2bd14`
- 回滚方式：`git checkout 400beb9f7d3dd10940daabdb7deea0bed3f2bd14 -- <changed-files>`
