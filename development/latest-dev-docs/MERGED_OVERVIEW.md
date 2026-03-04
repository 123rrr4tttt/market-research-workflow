# 合并文档总览

Updated: 2026-03-03 PST

## 目录级合并结果

| 目录 | 合并主文档 | 校对文档 | 说明 |
|---|---|---|---|
| `root-plans` | [main/MERGED_PLAN.md](./root-plans/main/MERGED_PLAN.md) | [G_REVIEW/MERGED_PLAN_REVIEW.md](./root-plans/G_REVIEW/MERGED_PLAN_REVIEW.md) | 根计划文档去重合并与时效校对 |
| `backend-core` | [main/MERGED_BACKEND_CORE.md](./backend-core/main/MERGED_BACKEND_CORE.md) | [G_REVIEW/MERGED_BACKEND_CORE_REVIEW.md](./backend-core/G_REVIEW/MERGED_BACKEND_CORE_REVIEW.md) | 运行、接口、测试三段合并 |
| `backend-docs` | [main/MERGED_BACKEND_DOCS.md](./backend-docs/main/MERGED_BACKEND_DOCS.md) | [G_REVIEW/MERGED_BACKEND_DOCS_REVIEW.md](./backend-docs/G_REVIEW/MERGED_BACKEND_DOCS_REVIEW.md) | 架构/API/采集/路线图统一汇总 |
| `ops-frontend` | [main/MERGED_OPS_FRONTEND.md](./ops-frontend/main/MERGED_OPS_FRONTEND.md) | [G_REVIEW/MERGED_OPS_FRONTEND_REVIEW.md](./ops-frontend/G_REVIEW/MERGED_OPS_FRONTEND_REVIEW.md) | 部署、前端、Figma、快速启动归并 |
| `development-plans` | [main/MERGED_DEVELOPMENT_PLANS.md](./development-plans/main/MERGED_DEVELOPMENT_PLANS.md) | [G_REVIEW/MERGED_DEVELOPMENT_PLANS_REVIEW.md](./development-plans/G_REVIEW/MERGED_DEVELOPMENT_PLANS_REVIEW.md) | 阶段/里程碑/依赖视角合并 |

## 使用建议

1. 先读本文件和各目录 `INDEX.md`，再进入合并主文档。
2. 校对文档用于识别过时项，不直接替代原始来源文档。
3. 若要提交发布版，优先更新 `SYNC_STATUS.md` 的检查时间。
4. 若要查看“开发条线盘点 + 封口归档 + 未落地目标”，优先阅读 [development-plans/main/DEVELOPMENT_STREAMS_CLOSURE_AND_GAPS_2026-03-03.md](./development-plans/main/DEVELOPMENT_STREAMS_CLOSURE_AND_GAPS_2026-03-03.md)。

## 最近新增

- `development-plans/CLOSED_DEV`（封口归档）：
  - [01_platformization-first-vectorization-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/01_platformization-first-vectorization-2026-03-03.md)
  - [02_atomic-zero-regression-tasklist-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/02_atomic-zero-regression-tasklist-2026-03-03.md)
  - [03_ingest-platformization-to-cleanup-optimization-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/03_ingest-platformization-to-cleanup-optimization-2026-03-03.md)
  - [04_adjusted-graph-node-phase-b-plan-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/04_adjusted-graph-node-phase-b-plan-2026-03-03.md)
  - [05_graph-node-standardization-overall-completion-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/05_graph-node-standardization-overall-completion-2026-03-03.md)
  - [06_backend-db-standardization-vectorization-closure-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-platformization-first-vectorization/06_backend-db-standardization-vectorization-closure-2026-03-03.md)
    - 增补：`single_url` 分层为入口/编排/结构化/入库路由四层；结构化模块从单链路中解耦，供 `single_url + url_pool + raw_import + social + market_web` 统一复用。
    - 口径同步：主路径统一为“数据库图真源主路径（graph_db / db-primary）”；兼容期继续接受历史配置字面量 `b_primary`。
- `development-plans/CLOSED_DEV`（新增封口迁移）：
  - [01_source-time-window-smart-timestamp-plan-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-source-time-window-smart-timestamp-closure/01_source-time-window-smart-timestamp-plan-2026-03-02.md)
  - [02_execution-plan-source-time-window-smart-timestamp-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-source-time-window-smart-timestamp-closure/02_execution-plan-source-time-window-smart-timestamp-2026-03-02.md)
  - [03_decoupled-implementation-plan-source-time-window-and-noun-density-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-source-time-window-smart-timestamp-closure/03_decoupled-implementation-plan-source-time-window-and-noun-density-2026-03-02.md)
  - [01_graph-node-standardization-a-then-b-plan-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-graph-node-standardization-a-then-b-closure/01_graph-node-standardization-a-then-b-plan-2026-03-02.md)
  - [01_global-vectorization-general-foundation-plan-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-global-vectorization-general-foundation/01_global-vectorization-general-foundation-plan-2026-03-03.md)
  - [02_atomic-vectorization-tasklist-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-global-vectorization-general-foundation/02_atomic-vectorization-tasklist-2026-03-03.md)
  - [03_vectorization-atomic-execution-report-2026-03-03.md](./development-plans/CLOSED_DEV/2026-03-03-global-vectorization-general-foundation/03_vectorization-atomic-execution-report-2026-03-03.md)
  - [README.md](./development-plans/CLOSED_DEV/2026-03-02-graph-3d-force-engine-parallel-migration-closure/README.md)
  - [01_graph-3d-force-engine-parallel-migration-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-graph-3d-force-engine-parallel-migration-closure/01_graph-3d-force-engine-parallel-migration-2026-03-02.md)
- `backend-core/main`：
  - [STANDARD_INGEST_WORKFLOWS_2026-03-02.md](./backend-core/main/STANDARD_INGEST_WORKFLOWS_2026-03-02.md)
- `development-plans/main`：
  - [CV01_CV02_CLOSURE_EVIDENCE_TEMPLATE_AND_MIGRATION_PREREQ_2026-03-03.md](./development-plans/main/CV01_CV02_CLOSURE_EVIDENCE_TEMPLATE_AND_MIGRATION_PREREQ_2026-03-03.md)
  - [CV02_BATCH_MIGRATION_QUEUE_2026-03-03.md](./development-plans/main/CV02_BATCH_MIGRATION_QUEUE_2026-03-03.md)
  - [CV02_IP03_BIP05_BLOCKED_CLOSURE_STRATEGY_2026-03-03.md](./development-plans/main/CV02_IP03_BIP05_BLOCKED_CLOSURE_STRATEGY_2026-03-03.md)
- `development-plans/CURRENT_DEV`（状态更新）：
  - [CURRENT_DEV/README.md](./development-plans/CURRENT_DEV/README.md)
  - [2026-03-03-currentdev-unfinished-closure-taskboard.md](./development-plans/CLOSED_DEV/2026-03-03-currentdev-unfinished-closure-taskboard.md)
  - [2026-03-03-currentdev-unfinished-closure-summary.md](./development-plans/CLOSED_DEV/2026-03-03-currentdev-unfinished-closure-summary.md)
- `development-plans/CLOSED_DEV`（新增封口迁移）：
  - [01_single-url-first-ingest-allocation-plan-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-single-url-first-ingest-allocation-closure/01_single-url-first-ingest-allocation-plan-2026-03-02.md)
  - [02_plan-domain-reinvestigation-2026-03-02.md](./development-plans/CLOSED_DEV/2026-03-02-single-url-first-ingest-allocation-closure/02_plan-domain-reinvestigation-2026-03-02.md)
  - [01_multi-agent-taskboard-open-source-platform-integration-2026-03-01.md](./development-plans/CLOSED_DEV/2026-03-01-open-source-platform-integration-closure/01_multi-agent-taskboard-open-source-platform-integration-2026-03-01.md)
- `ops-frontend/F_PLAN`：
  - [graph-3d-controls-left-and-2d-gravity-2026-03-02.md](./ops-frontend/F_PLAN/graph-3d-controls-left-and-2d-gravity-2026-03-02.md)
