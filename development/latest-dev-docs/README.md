# 最新开发文档总览（Snapshot）

> 本目录为按当前仓库状态同步后的开发文档快照与合并结果。
> 本目录是本项目开发文档的第一入口（重要索引）。

## 快速入口

- [合并总览](./MERGED_OVERVIEW.md)
- [同步状态](./SYNC_STATUS.md)
- [来源台账](./index.md)
- [开发条线/封口归档/未落地目标审计](./development-plans/main/DEVELOPMENT_STREAMS_CLOSURE_AND_GAPS_2026-03-03.md)

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

- `development-plans/CLOSED_DEV` 归档“先平台化、后向量化”封口项目：
  - [01_platformization-first-vectorization-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/01_platformization-first-vectorization-2026-03-03.md)
  - [02_atomic-zero-regression-tasklist-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/02_atomic-zero-regression-tasklist-2026-03-03.md)
  - [03_ingest-platformization-to-cleanup-optimization-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/03_ingest-platformization-to-cleanup-optimization-2026-03-03.md)
  - [04_adjusted-graph-node-phase-b-plan-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/04_adjusted-graph-node-phase-b-plan-2026-03-03.md)
  - [05_graph-node-standardization-overall-completion-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/05_graph-node-standardization-overall-completion-2026-03-03.md)
  - [06_backend-db-standardization-vectorization-closure-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/06_backend-db-standardization-vectorization-closure-2026-03-03.md)
    - 口径同步：主路径统一为“数据库图真源主路径（graph_db / db-primary）”；兼容期继续接受历史配置字面量 `b_primary`。
- `development-plans/CLOSED_DEV` 归档 single-url-first 方案封口：
  - [01_single-url-first-ingest-allocation-plan-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-single-url-first-ingest-allocation-closure/01_single-url-first-ingest-allocation-plan-2026-03-02.md)
  - [02_plan-domain-reinvestigation-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-single-url-first-ingest-allocation-closure/02_plan-domain-reinvestigation-2026-03-02.md)
- `development-plans/CLOSED_DEV` 归档 open-source platform integration 封口：
  - [01_multi-agent-taskboard-open-source-platform-integration-2026-03-01.md](./development-plans/CLOSED_DEV/2026-03-01-open-source-platform-integration-closure/01_multi-agent-taskboard-open-source-platform-integration-2026-03-01.md)
- `development-plans/CLOSED_DEV` 归档源时间窗与智能时间戳方案封口：
  - [01_source-time-window-smart-timestamp-plan-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-source-time-window-smart-timestamp-closure/01_source-time-window-smart-timestamp-plan-2026-03-02.md)
  - [02_execution-plan-source-time-window-smart-timestamp-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-source-time-window-smart-timestamp-closure/02_execution-plan-source-time-window-smart-timestamp-2026-03-02.md)
  - [03_decoupled-implementation-plan-source-time-window-and-noun-density-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-source-time-window-smart-timestamp-closure/03_decoupled-implementation-plan-source-time-window-and-noun-density-2026-03-02.md)
- `development-plans/CLOSED_DEV` 归档图谱节点 A→B 标准化方案：
  - [01_graph-node-standardization-a-then-b-plan-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-graph-node-standardization-a-then-b-closure/01_graph-node-standardization-a-then-b-plan-2026-03-02.md)
- `development-plans/CLOSED_DEV` 归档全局向量化通用基础方案：
  - [01_global-vectorization-general-foundation-plan-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-global-vectorization-general-foundation/01_global-vectorization-general-foundation-plan-2026-03-03.md)
  - [02_atomic-vectorization-tasklist-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-global-vectorization-general-foundation/02_atomic-vectorization-tasklist-2026-03-03.md)
  - [03_vectorization-atomic-execution-report-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-global-vectorization-general-foundation/03_vectorization-atomic-execution-report-2026-03-03.md)
- `development-plans/CLOSED_DEV` 新增图谱 3D 引擎并行迁移封口：
  - [README.md](./development-plans/CLOSED_DEV/2026-03-02-graph-3d-force-engine-parallel-migration-closure/README.md)
  - [01_graph-3d-force-engine-parallel-migration-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-graph-3d-force-engine-parallel-migration-closure/01_graph-3d-force-engine-parallel-migration-2026-03-02.md)
- `development-plans/main` 新增文档封口链（CV01~CV02）准备文档：
  - [CV01_CV02_CLOSURE_EVIDENCE_TEMPLATE_AND_MIGRATION_PREREQ_2026-03-03.md](./development-plans/main/CV01_CV02_CLOSURE_EVIDENCE_TEMPLATE_AND_MIGRATION_PREREQ_2026-03-03.md)
  - [CV02_BATCH_MIGRATION_QUEUE_2026-03-03.md](./development-plans/main/CV02_BATCH_MIGRATION_QUEUE_2026-03-03.md)
  - [CV02_IP03_BIP05_BLOCKED_CLOSURE_STRATEGY_2026-03-03.md](./development-plans/main/CV02_IP03_BIP05_BLOCKED_CLOSURE_STRATEGY_2026-03-03.md)
- `development-plans/CURRENT_DEV` 已清空（全部迁移封口）：
  - [CURRENT_DEV/README.md](./development-plans/CURRENT_DEV/README.md)
  - [2026-03-03-currentdev-unfinished-closure-taskboard.md](./development-plans/CLOSED_DEV/2026-03-03-currentdev-unfinished-closure-taskboard.md)
  - [2026-03-03-currentdev-unfinished-closure-summary.md](./development-plans/CLOSED_DEV/2026-03-03-currentdev-unfinished-closure-summary.md)
- `backend-core/main` 新增标准工作流打包文档：
  - [STANDARD_INGEST_WORKFLOWS_2026-03-02.md](./backend-core/main/STANDARD_INGEST_WORKFLOWS_2026-03-02.md)
- `ops-frontend/F_PLAN` 新增图谱 3D 控制面板左移与 2D 全局引力记录：
  - [graph-3d-controls-left-and-2d-gravity-2026-03-02.md](./ops-frontend/F_PLAN/graph-3d-controls-left-and-2d-gravity-2026-03-02.md)
