# 最新开发文档总览（Snapshot）

> 本目录为按当前仓库状态同步后的开发文档快照与合并结果。
> 本目录是本项目开发文档的第一入口（重要索引）。

## 快速入口

- [合并总览](./MERGED_OVERVIEW.md)
- [同步状态](./SYNC_STATUS.md)
- [来源台账](./index.md)

## 分目录入口

- [root-plans](./root-plans/INDEX.md)
- [backend-core](./backend-core/INDEX.md)
- [backend-docs](./backend-docs/INDEX.md)
- [ops-frontend](./ops-frontend/INDEX.md)
- [development-plans](./development-plans/INDEX.md)

## 命名日期规则

- 开发文档的“目录日期”和“文件名日期”必须与文档实际更新日期一致（格式 `YYYY-MM-DD`）。
- 当更新日期变化时，必须同步更新目录名、文件名与索引引用（至少包含 `README.md`、`MERGED_OVERVIEW.md`、子目录 `INDEX.md`）。

## 最新补充

- `development-plans/CURRENT_DEV` 新增 R3 Must 最小实现与验证：
  - [01_r3-must-minimal-implementation-and-verification-2026-03-04.md](./development-plans/CURRENT_DEV/2026-03-04-r3-must-minimal-implementation/01_r3-must-minimal-implementation-and-verification-2026-03-04.md)
- `development-plans/CURRENT_DEV` 新增 Version B Round4（StreamPlus Gate Enhancement）：
  - [04_B-line-round4-streamplus-plan-and-atomic-task-table.md](./development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/04_B-line-round4-streamplus-plan-and-atomic-task-table.md)
  - [05_B-line-round4-streamplus-closure.md](./development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/05_B-line-round4-streamplus-closure.md)
- `development-plans/CURRENT_DEV` 新增 Version B Round7（Failure Diagnostics）：
  - [08_B-line-round7-plan-and-atomic-task-table.md](./development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/08_B-line-round7-plan-and-atomic-task-table.md)
  - [09_B-line-round7-closure.md](./development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/09_B-line-round7-closure.md)
- `development-plans/CURRENT_DEV` 新增 Version B Round3 R3（Must 最小实现 + 验证）：
  - [10_B-line-round3-r3-must-minimal-implementation.md](./development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/10_B-line-round3-r3-must-minimal-implementation.md)
- `development-plans/CURRENT_DEV` 新增 Version D 与 D 线增量文档：
  - [01_task_doc.md](./development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/01_task_doc.md)
  - [02_dev_doc.md](./development-plans/CURRENT_DEV/2026-03-03-version-D-doc-normalization/02_dev_doc.md)
  - [01_repo-mapping-and-minimal-implementation.md](./development-plans/CURRENT_DEV/2026-03-04-cd-r3-d-security-minimal/01_repo-mapping-and-minimal-implementation.md)
  - [01_repo-mapping-and-minimal-enforcement.md](./development-plans/CURRENT_DEV/2026-03-04-cd-r5-d-provenance-enforcement/01_repo-mapping-and-minimal-enforcement.md)
  - [01_task_and_closing.md](./development-plans/CURRENT_DEV/2026-03-04-d-line-rag-filter-robustness/01_task_and_closing.md)
- `development-plans/CURRENT_DEV` 新增 SA3-R3-F（llm-report 数据AI线）最小制度化落地记录：
  - [01_sa3-r3-f-implementation-2026-03-04.md](./development-plans/CURRENT_DEV/2026-03-04-sa3-r3-f-llm-report-must-minset/01_sa3-r3-f-implementation-2026-03-04.md)
- `development-plans/CURRENT_DEV` 新增“先平台化、后向量化”改造：
  - [01_platformization-first-vectorization-2026-03-03.md](./development-plans/CURRENT_DEV/2026-03-03-platformization-first-vectorization/01_platformization-first-vectorization-2026-03-03.md)
  - [02_atomic-zero-regression-tasklist-2026-03-03.md](./development-plans/CURRENT_DEV/2026-03-03-platformization-first-vectorization/02_atomic-zero-regression-tasklist-2026-03-03.md)
  - [03_ingest-platformization-to-cleanup-optimization-2026-03-03.md](./development-plans/CURRENT_DEV/2026-03-03-platformization-first-vectorization/03_ingest-platformization-to-cleanup-optimization-2026-03-03.md)
  - [04_adjusted-graph-node-phase-b-plan-2026-03-03.md](./development-plans/CURRENT_DEV/2026-03-03-platformization-first-vectorization/04_adjusted-graph-node-phase-b-plan-2026-03-03.md)
  - [05_graph-node-standardization-overall-completion-2026-03-03.md](./development-plans/CURRENT_DEV/2026-03-03-platformization-first-vectorization/05_graph-node-standardization-overall-completion-2026-03-03.md)
  - [06_backend-db-standardization-vectorization-closure-2026-03-03.md](./development-plans/CURRENT_DEV/2026-03-03-platformization-first-vectorization/06_backend-db-standardization-vectorization-closure-2026-03-03.md)
    - 口径同步：主路径统一为“数据库图真源主路径（graph_db / db-primary）”；兼容期继续接受历史配置字面量 `b_primary`。
- `development-plans/CURRENT_DEV` 新增单 URL 优先方案：
  - [01_single-url-first-ingest-allocation-plan-2026-03-02.md](./development-plans/CURRENT_DEV/2026-03-02-single-url-first-ingest-allocation-plan/01_single-url-first-ingest-allocation-plan-2026-03-02.md)
- `development-plans/CURRENT_DEV` 新增源时间窗与智能时间戳方案：
  - [01_source-time-window-smart-timestamp-plan-2026-03-02.md](./development-plans/CURRENT_DEV/2026-03-02-source-time-window-smart-timestamp-plan/01_source-time-window-smart-timestamp-plan-2026-03-02.md)
  - [02_execution-plan-source-time-window-smart-timestamp-2026-03-02.md](./development-plans/CURRENT_DEV/2026-03-02-source-time-window-smart-timestamp-plan/02_execution-plan-source-time-window-smart-timestamp-2026-03-02.md)
  - [03_decoupled-implementation-plan-source-time-window-and-noun-density-2026-03-02.md](./development-plans/CURRENT_DEV/2026-03-02-source-time-window-smart-timestamp-plan/03_decoupled-implementation-plan-source-time-window-and-noun-density-2026-03-02.md)
- `development-plans/CURRENT_DEV` 新增图谱节点 A→B 标准化方案：
  - [01_graph-node-standardization-a-then-b-plan-2026-03-02.md](./development-plans/CURRENT_DEV/2026-03-02-graph-node-standardization-a-then-b-plan/01_graph-node-standardization-a-then-b-plan-2026-03-02.md)
- `development-plans/CURRENT_DEV` 新增全局向量化通用基础方案：
  - [01_global-vectorization-general-foundation-plan-2026-03-03.md](./development-plans/CURRENT_DEV/2026-03-03-global-vectorization-general-foundation/01_global-vectorization-general-foundation-plan-2026-03-03.md)
  - [02_atomic-vectorization-tasklist-2026-03-03.md](./development-plans/CURRENT_DEV/2026-03-03-global-vectorization-general-foundation/02_atomic-vectorization-tasklist-2026-03-03.md)
  - [03_vectorization-atomic-execution-report-2026-03-03.md](./development-plans/CURRENT_DEV/2026-03-03-global-vectorization-general-foundation/03_vectorization-atomic-execution-report-2026-03-03.md)
- `development-plans/CURRENT_DEV` 新增图谱 3D 引擎并行迁移方案：
  - [01_graph-3d-force-engine-parallel-migration-2026-03-02.md](./development-plans/CURRENT_DEV/2026-03-02-graph-3d-force-engine-parallel-migration/01_graph-3d-force-engine-parallel-migration-2026-03-02.md)
- `backend-core/main` 新增标准工作流打包文档：
  - [STANDARD_INGEST_WORKFLOWS_2026-03-02.md](./backend-core/main/STANDARD_INGEST_WORKFLOWS_2026-03-02.md)
- `backend-docs/E_OPS` 新增 E-DB R5 执行记录（参考包代理映射 + deep health 连接池门禁）：
  - [E_DB_R5_REFERENCE_POOL_PROXY_AND_POOL_GATE_2026-03-04.md](./backend-docs/E_OPS/E_DB_R5_REFERENCE_POOL_PROXY_AND_POOL_GATE_2026-03-04.md)
- `ops-frontend/F_PLAN` 新增图谱 3D 控制面板左移与 2D 全局引力记录：
  - [graph-3d-controls-left-and-2d-gravity-2026-03-02.md](./ops-frontend/F_PLAN/graph-3d-controls-left-and-2d-gravity-2026-03-02.md)
