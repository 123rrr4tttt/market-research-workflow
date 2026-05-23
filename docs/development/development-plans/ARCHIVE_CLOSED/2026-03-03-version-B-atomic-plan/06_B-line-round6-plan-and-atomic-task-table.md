<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-atomic-plan/06_B-line-round6-plan-and-atomic-task-table.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-atomic-plan/06_B-line-round6-plan-and-atomic-task-table.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# B线第6轮：GatePlus CI Required Checks 化（原子任务表）

- 轮次：Night Continuous Iteration / Round 6
- 目标：完成“统一知识池 -> 原子编排 -> 实现 -> 可执行验证 -> 封口文档”的闭环
- 关联统一知识池：
  - `external_refs/version-B/INDEX.md`
  - `external_refs/version-B/B-line-round6-gateplus-ci-required-checks-best-practices-2026-03-03.md`
- 负责人：dev-owner（本子任务执行体）

## 1. 串行依赖与门禁总览

1. G0：联网检索并合并写入统一知识池（单一入口索引）
2. G1：冻结 Round6 原子任务表
3. G2：实现 CI workflow 增量改造
4. G3：可执行验证（脚本执行 + workflow 语法校验）
5. G4：closing doc + 索引更新

## 2. 原子任务表

| 原子任务ID | 任务 | 输入 | 输出 | 依赖 | 阶段门禁 | 负责人 | 预期产物 |
|---|---|---|---|---|---|---|---|
| B6-AT-01 | 联网检索并沉淀 Round6 增量最佳实践 | GitHub Actions / pytest 官方文档 | Round6 知识池文档 + 统一索引更新 | 无 | G0 | dev-owner | `external_refs/version-B/B-line-round6-gateplus-ci-required-checks-best-practices-2026-03-03.md` + `external_refs/version-B/INDEX.md` |
| B6-AT-02 | 冻结 Round6 开发编排文档 | B6-AT-01 | 本文档 | B6-AT-01 | G1 | dev-owner | `06_B-line-round6-plan-and-atomic-task-table.md` |
| B6-AT-03 | CI workflow 实现 GatePlus 独立门禁 job | 现有 backend-tests workflow + gateplus 脚本 | 新增 `gateplus-guard-check` job + artifact 上传 | B6-AT-02 | G2 | dev-owner | `.github/workflows/backend-tests.yml` |
| B6-AT-04 | 可执行验证并记录证据 | B6-AT-03 | 本地脚本执行记录 + workflow 语法检查 | B6-AT-03 | G3 | dev-owner | 命令输出证据 |
| B6-AT-05 | 输出封口文档并更新索引 | B6-AT-04 | Round6 closing doc + Version B index/README/CURRENT_DEV 索引更新 | B6-AT-04 | G4 | dev-owner | `07_B-line-round6-closure.md` + 索引变更 |

## 3. 跨版本去重与差异化声明

- 去重项（沿用 Round4，不重复开发）：
  - `main/backend/scripts/gateplus_ci_guard.sh` 的 junit/json 输出逻辑
  - skip/fail/pass/warnings 判定逻辑
- Round6 差异项（本轮新增）：
  - 将 GatePlus 纳入 `.github/workflows/backend-tests.yml` 独立 job
  - job 级 artifact 上传与 required checks 对齐能力

## 4. 实施边界

- 仅改动：
  - `.github/workflows/backend-tests.yml`
  - `external_refs/version-B/*`（统一知识池）
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/*`（Round6 文档）
- 不改动业务接口、数据库结构、前端逻辑。
