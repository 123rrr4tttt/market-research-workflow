<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-atomic-plan/04_B-line-round4-streamplus-plan-and-atomic-task-table.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-atomic-plan/04_B-line-round4-streamplus-plan-and-atomic-task-table.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# B线第4轮：StreamPlus 门禁增强开发文档与原子任务表

- 轮次：Night Continuous Iteration / Round 4
- 目标：把 GatePlus 门禁升级为“可观测 + 可配置 + 可归档”的 StreamPlus 形态
- 关联知识池：`external_refs/version-B/B-line-round4-streamplus-best-practices-2026-03-03.md`
- 负责人：dev-owner（本子任务执行体）

## 1. 串行依赖与门禁总览

1. G0：知识池完成（联网检索 + 本地沉淀）
2. G1：开发文档与原子任务表冻结
3. G2：脚本实现
4. G3：本地验证（脚本运行 + 产物检查）
5. G4：封口文档与索引更新

## 2. 原子任务表

| 原子任务ID | 任务 | 输入 | 输出 | 依赖 | 阶段门禁 | 负责人 | 预期产物 | 回滚点 |
|---|---|---|---|---|---|---|---|---|
| B4-AT-01 | 沉淀联网最佳实践到知识池 | pytest/github 官方文档 | round4 best-practices 文档 | 无 | G0 | dev-owner | `external_refs/version-B/B-line-round4-streamplus-best-practices-2026-03-03.md` | 删除该文档 |
| B4-AT-02 | 冻结 round4 执行计划与任务表 | B4-AT-01 | 本文档 | B4-AT-01 | G1 | dev-owner | `04_B-line-round4-streamplus-plan-and-atomic-task-table.md` | 回退本文档 |
| B4-AT-03 | 增强 gateplus 脚本（junit/json/阈值） | 现有 `gateplus_ci_guard.sh` | 新版脚本 | B4-AT-02 | G2 | dev-owner | `main/backend/scripts/gateplus_ci_guard.sh` | 回退该脚本 |
| B4-AT-04 | 验证脚本执行与产物可用 | B4-AT-03 | 通过证据 | B4-AT-03 | G3 | dev-owner | 控制台输出 + `.artifacts/gateplus/{junit.xml,summary.json}` | 删除 artifacts 并回退脚本 |
| B4-AT-05 | 封口文档+索引/README 更新 | B4-AT-04 | round4 closure + 索引条目 | B4-AT-04 | G4 | dev-owner | `05_B-line-round4-streamplus-closure.md` + index/README 更新 | 回退文档改动 |

## 3. 实施范围（本轮）

- 仅限：`main/backend/scripts/gateplus_ci_guard.sh` 与文档/索引。
- 不包含：业务 API、DB schema、迁移脚本、前端逻辑。
