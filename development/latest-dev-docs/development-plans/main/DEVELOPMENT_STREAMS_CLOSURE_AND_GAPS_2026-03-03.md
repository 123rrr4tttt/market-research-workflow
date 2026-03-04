# Development Streams Closure and Gap Audit (2026-03-03)

更新时间：2026-03-03（PST）  
范围：`development/latest-dev-docs/*`

## 1) 全部开发条线（当前视图）

| 子项目 | 条线状态摘要 |
|---|---|
| `root-plans` | 主体为已合并基线，处于“归档+基线维护”状态 |
| `backend-core` | 接口与架构基线稳定；`C_INGEST/D_TEST` 仍有活跃收尾 |
| `backend-docs` | 以规范和计划文档为主，整体偏归档与知识沉淀 |
| `ops-frontend` | 基线稳定，`F_PLAN` 仍有活跃事项 |
| `development-plans` | `CURRENT_DEV` 活跃推进；`CLOSED_DEV` 存放封口项目 |

当前活跃主线（`development-plans/CURRENT_DEV`）：
- Graph 3D force engine parallel migration
- Ingest chain full branch map
- Ingest platformization assessment
- Meaningful ingest guardrails

## 2) 已封口并归档项目

已迁入：`development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/`
已迁入：`development-plans/CLOSED_DEV/2026-03-03-global-vectorization-general-foundation/`
已迁入：`development-plans/CLOSED_DEV/2026-03-03-gap-register-closure/`
已迁入：`development-plans/CLOSED_DEV/2026-03-02-single-url-first-ingest-allocation-closure/`
已迁入：`development-plans/CLOSED_DEV/2026-03-01-open-source-platform-integration-closure/`
已迁入：`development-plans/CLOSED_DEV/2026-03-02-source-time-window-smart-timestamp-closure/`
已迁入：`development-plans/CLOSED_DEV/2026-03-02-graph-node-standardization-a-then-b-closure/`

封口证据：
- `05_graph-node-standardization-overall-completion-2026-03-03.md`
- `06_backend-db-standardization-vectorization-closure-2026-03-03.md`

说明：本项目已从 `CURRENT_DEV` 移出，避免“封口项目与活跃项目混挂”。

## 3) 忘记落地或未闭环目标（优先级）

P0:
- `project_key` 强制切换前置未封口（`root-plans/main/MERGED_PLAN.md` Open Follow-ups）。
- `8.3 Perplexity 集成` 仍为 `planned`。

P1:
- `8.2 工作流平台化` 仍 `partial`（模板保存-读取-运行闭环不完整）。
- `8.5 RAG + 报告` 仍 `partial`（对话/报告 API 未闭环）。
- `8.6 对象化采集` 仍 `partial`（company/product/operation 未统一闭环）。
- `Graph 3D force engine parallel migration` 仍 `not_closed`（缺封口证据入口与项目级结论）。
- `Ingest chain full branch map` 仍 `not_closed`（`planned_handler` 收敛未完成）。
- `Ingest platformization assessment` 仍 `not_closed`（`IP03` 受 `WAIVER-DOCKER-001` 暂缓）。
- `Meaningful ingest guardrails` 仍 `not_closed`（production 级闭环证据未完成）。

P2:
- `social.py` 尚未纳入 `collect_runtime` 统一通道。
- `backend-core/main/TEST_SCENARIO_MATRIX.md` 仍存在 `partial/gap` 条目。

P3:
- `ops-frontend` Figma 同步存在 `Pending (blocked)` 长尾。

## 4) 最小落地动作（每项 1-2 步）

1. `project_key require`：补显式 key 覆盖检查 + 两条关键入口 e2e 回归。
2. `8.3`：落地 provider 适配 + source 归因输出。
3. `8.2/8.5/8.6`：各补一个最小闭环 API 与一组可重复验收用例。
4. `Graph 3D`：补封口结论页 + 最小前后端联动验收证据索引。
5. `Ingest Chain`：按分支清单补齐 `planned_handler -> effective` 证据并回写映射。
6. `Ingest Platformization`：在 Docker 环境恢复后执行 `IP03 preflight` 并补 runbook/SOP 链接。
7. `Meaningful Guardrails`：补 production 级运行观测证据（告警、看板、回归样例）。
8. social collect_runtime：先加 adapter 保持外部 API 不变，再切入口并回归 process 展示。

## 5) 最小验证步骤

- 索引检查：
  - `find development/latest-dev-docs/development-plans -maxdepth 2 -type d | sort`
  - `find development/latest-dev-docs/development-plans/CLOSED_DEV -type f -name '*.md' | sort`
- 链接检查（抽样）：
  - `grep -RIn "CLOSED_DEV/2026-03-03-platformization-first-vectorization" development/latest-dev-docs --include='*.md'`
- 状态检查（抽样）：
  - `grep -RInE "Open Follow-ups|planned|partial|尚未完成|Not Implemented" development/latest-dev-docs --include='*.md'`
