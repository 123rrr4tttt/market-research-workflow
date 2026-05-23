<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-atomic-plan/12_A-line-round6-atomic-task-table-and-gates-2026-03-03.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-atomic-plan/12_A-line-round6-atomic-task-table-and-gates-2026-03-03.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# A线第6轮：原子任务表（依赖 / 门禁 / 负责人 / 产物）

| ID | 原子任务 | 依赖 | 门禁(Gate) | 负责人 | 产物 |
|---|---|---|---|---|---|
| R6-T1 | 联网检索 flaky 趋势治理最佳实践 | 无 | 至少3个权威来源，含官方文档 | A线子agent | round6研究文档 |
| R6-T2 | 合并写入统一知识池并更新单一入口索引 | R6-T1 | 仅允许 `信息源库/INDEX.md` 作为入口 | A线子agent | INDEX.md + round6知识文档 |
| R6-T3 | 实现趋势聚合脚本（多XML聚合） | R6-T2 | 脚本可处理 failure/error，输出 markdown | A线子agent | `main/backend/scripts/flake_trend.py` |
| R6-T4 | 增补单元测试 | R6-T3 | 覆盖多文件聚合与阈值告警标记 | A线子agent | `test_flake_trend_unittest.py` |
| R6-T5 | 接入 CI workflow 汇总 | R6-T3 | 不破坏现有 flaky report 输出，新增 trend 输出 | A线子agent | `.github/workflows/backend-tests.yml` |
| R6-T6 | 可执行验证 | R6-T4,R6-T5 | pytest 通过；趋势报告可生成 | A线子agent | 测试日志 + 报告产物 |
| R6-T7 | closing 文档与索引回填 | R6-T6 | 含去重声明、关键路径、下一轮草案 | A线子agent | round6 closing + index 更新 |

## 执行门禁说明
- **安全门禁**：不调整现有硬门禁，仅新增观测层。
- **质量门禁**：新增测试必须通过，且不影响 round5 既有测试。
- **去重门禁**：closing 中明确 round4/5/6 边界与增量价值。
