# B线第7轮：GatePlus Failure Diagnostics 增强（原子任务表）

- 轮次：Night Continuous Iteration / Round 7
- 时间：2026-03-04 00:20 PST
- 目标：在不破坏 Round6 Required Checks 语义的前提下，增强 GatePlus 失败诊断可观测性（结构化原因 + actionable hint + CI job summary 可见）
- 负责人：dev-owner（本子任务执行体）

## 1. 串行依赖与门禁总览

1. G0：对齐 Round6 已有实现边界（guard script + workflow job + artifact 路径）
2. G1：冻结 Round7 原子任务表
3. G2：实现 failure diagnostics 增量（脚本）
4. G3：实现 CI job summary 展示（workflow）
5. G4：可执行验证（成功路径 + 失败路径 + YAML 校验）
6. G5：封口文档与索引更新

## 2. 原子任务表

| 原子任务ID | 任务 | 输入 | 输出 | 依赖 | 阶段门禁 | 负责人 | 预期产物 |
|---|---|---|---|---|---|---|---|
| B7-AT-01 | 对齐 Round6 边界并确认不可破坏项 | Round6 06/07 文档 + guard/workflow 实现 | Round7 执行边界 | 无 | G0 | dev-owner | 本文档第3节 |
| B7-AT-02 | 增强 gateplus guard 的失败结构化诊断 | `main/backend/scripts/gateplus_ci_guard.sh` | `summary.json` 新增 `failure_diagnostics`、`status` | B7-AT-01 | G2 | dev-owner | `main/backend/scripts/gateplus_ci_guard.sh` |
| B7-AT-03 | 在 workflow 输出 GatePlus 诊断摘要 | `.github/workflows/backend-tests.yml` | `gateplus-guard-check` 新增 summary 步骤 | B7-AT-02 | G3 | dev-owner | `.github/workflows/backend-tests.yml` |
| B7-AT-04 | 执行最小回归验证并记录证据 | B7-AT-03 | 成功+失败路径关键输出 | B7-AT-03 | G4 | dev-owner | 命令输出证据 |
| B7-AT-05 | 输出封口文档并更新索引 | B7-AT-04 | Round7 封口文档 + 索引更新 | B7-AT-04 | G5 | dev-owner | `09_B-line-round7-closure.md` + 索引变更 |

## 3. Round7 执行边界（对齐 Round6）

- 保持不变：
  - workflow job 名称：`gateplus-guard-check`
  - 门禁失败语义：脚本失败必须返回非零退出码
  - artifact 路径：`main/backend/.artifacts/gateplus/junit.xml` 与 `summary.json`
  - `summary.json` 既有字段：`tool/summary_line/pytest_exit/counts/gates`
- 本轮仅增量：
  - `summary.json` 新增结构化失败诊断字段
  - CI job 增加 `if: always()` 的 diagnostics summary 渲染步骤
- 不改动业务接口、数据库结构与前端逻辑。

## 4. 验证策略

1. guard 脚本成功路径：保证门禁可通过且产物存在
2. guard 脚本失败路径：触发阈值失败，确认结构化诊断字段出现
3. workflow YAML 语法校验：确认编排文件合法
4. summary 契约回归：确认既有字段未被破坏
