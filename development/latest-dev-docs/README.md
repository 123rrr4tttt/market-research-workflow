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

- `development-plans/CURRENT_DEV` 新增 Agent + Symbolic + Batch Search 架构专题：
  - [2026-03-09-agent-symbolic-batch-search-architecture/README.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/README.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/01_agent-symbolic-batch-search-plan-2026-03-09.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/01_agent-symbolic-batch-search-plan-2026-03-09.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/02_atomic-tasklist-agent-symbolic-batch-search-2026-03-09.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/02_atomic-tasklist-agent-symbolic-batch-search-2026-03-09.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/03_atomic-task-library-investigation-map-2026-03-10.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/03_atomic-task-library-investigation-map-2026-03-10.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/04_parallel-execution-playbook-spark-codex-2026-03-10.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/04_parallel-execution-playbook-spark-codex-2026-03-10.md)
- `development-plans/CURRENT_DEV` 新增写作工作台演进主题文档：
  - [2026-03-07-writing-workbench-evolution/01_writing-workbench-evolution-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-writing-workbench-evolution/01_writing-workbench-evolution-plan-2026-03-07.md)
  - [2026-03-07-writing-workbench-evolution/02_atomic-tasklist-writing-workbench-evolution-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-writing-workbench-evolution/02_atomic-tasklist-writing-workbench-evolution-2026-03-07.md)
- `development-plans/CURRENT_DEV` 新增知识组织与图谱编辑主题文档：
  - [2026-03-07-typed-knowledge-organization/01_typed-knowledge-organization-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-typed-knowledge-organization/01_typed-knowledge-organization-plan-2026-03-07.md)
  - [2026-03-07-typed-knowledge-organization/02_atomic-tasklist-typed-knowledge-organization-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-typed-knowledge-organization/02_atomic-tasklist-typed-knowledge-organization-2026-03-07.md)
  - [2026-03-07-graph-editing-and-reporting/01_graph-editing-and-reporting-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-graph-editing-and-reporting/01_graph-editing-and-reporting-plan-2026-03-07.md)
  - [2026-03-07-graph-editing-and-reporting/02_atomic-tasklist-graph-editing-and-reporting-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-graph-editing-and-reporting/02_atomic-tasklist-graph-editing-and-reporting-2026-03-07.md)
- `development-plans/CURRENT_DEV` 新增采集、来源、前端基础设施主题文档：
  - [2026-03-07-ingest-digestion-and-long-cycle-automation/01_ingest-digestion-and-long-cycle-automation-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-ingest-digestion-and-long-cycle-automation/01_ingest-digestion-and-long-cycle-automation-plan-2026-03-07.md)
  - [2026-03-07-ingest-digestion-and-long-cycle-automation/02_atomic-tasklist-ingest-digestion-and-long-cycle-automation-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-ingest-digestion-and-long-cycle-automation/02_atomic-tasklist-ingest-digestion-and-long-cycle-automation-2026-03-07.md)
  - [2026-03-07-crawler-source-expansion/01_crawler-source-expansion-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-crawler-source-expansion/01_crawler-source-expansion-plan-2026-03-07.md)
  - [2026-03-07-crawler-source-expansion/02_atomic-tasklist-crawler-source-expansion-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-crawler-source-expansion/02_atomic-tasklist-crawler-source-expansion-2026-03-07.md)
  - [2026-03-07-frontend-i18n-theme-modularization/01_frontend-i18n-theme-modularization-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-frontend-i18n-theme-modularization/01_frontend-i18n-theme-modularization-plan-2026-03-07.md)
  - [2026-03-07-frontend-i18n-theme-modularization/02_atomic-tasklist-frontend-i18n-theme-modularization-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-frontend-i18n-theme-modularization/02_atomic-tasklist-frontend-i18n-theme-modularization-2026-03-07.md)
- `development-plans/CURRENT_DEV` 新增模型服务平台化与 modern 基座双交互前端拓扑主题文档：
  - [2026-03-07-llm-service-and-agent-platformization/01_llm-service-and-agent-platformization-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-llm-service-and-agent-platformization/01_llm-service-and-agent-platformization-plan-2026-03-07.md)
  - [2026-03-07-llm-service-and-agent-platformization/02_atomic-tasklist-llm-service-and-agent-platformization-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-llm-service-and-agent-platformization/02_atomic-tasklist-llm-service-and-agent-platformization-2026-03-07.md)
  - [2026-03-07-dual-frontend-workbench-topology/01_dual-frontend-workbench-topology-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-dual-frontend-workbench-topology/01_dual-frontend-workbench-topology-plan-2026-03-07.md)
  - [2026-03-07-dual-frontend-workbench-topology/02_atomic-tasklist-dual-frontend-workbench-topology-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-dual-frontend-workbench-topology/02_atomic-tasklist-dual-frontend-workbench-topology-2026-03-07.md)
- `development-plans/CURRENT_DEV` 新增抽象规划子文件夹拆分计划：
  - [2026-03-07-后续安排/01_abstract-planning-folderization-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-后续安排/01_abstract-planning-folderization-plan-2026-03-07.md)
- `development-plans/CURRENT_DEV` 新增抽象规划子文件夹拆分原子任务：
  - [2026-03-07-后续安排/02_atomic-tasklist-abstract-planning-folderization-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-后续安排/02_atomic-tasklist-abstract-planning-folderization-2026-03-07.md)
- `development-plans/CURRENT_DEV` 新增 docs 根目录重构迁移映射表：
  - [2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md)
- `development-plans/CURRENT_DEV` 新增内置写作工作台设计方案：
  - [2026-03-07-builtin-writing-workbench-design/01_builtin-writing-workbench-design-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-builtin-writing-workbench-design/01_builtin-writing-workbench-design-2026-03-07.md)
- `development-plans/CURRENT_DEV` 补充内置写作工作台原子任务清单：
  - [2026-03-07-builtin-writing-workbench-design/02_atomic-tasklist-builtin-writing-workbench-design-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-builtin-writing-workbench-design/02_atomic-tasklist-builtin-writing-workbench-design-2026-03-07.md)
- `development-plans/CURRENT_DEV` 新增 LLM + 爬虫统一前门架构草案：
  - [2026-03-08-llm-crawler-unified-frontdoor/01_llm-crawler-unified-frontdoor-architecture-2026-03-08.md](./development-plans/CURRENT_DEV/2026-03-08-llm-crawler-unified-frontdoor/01_llm-crawler-unified-frontdoor-architecture-2026-03-08.md)
  - [2026-03-08-llm-crawler-unified-frontdoor/02_atomic-tasklist-llm-crawler-unified-frontdoor-2026-03-08.md](./development-plans/CURRENT_DEV/2026-03-08-llm-crawler-unified-frontdoor/02_atomic-tasklist-llm-crawler-unified-frontdoor-2026-03-08.md)
  - [2026-03-08-llm-crawler-unified-frontdoor/03_a10-closure-and-validation-2026-03-08.md](./development-plans/CURRENT_DEV/2026-03-08-llm-crawler-unified-frontdoor/03_a10-closure-and-validation-2026-03-08.md)
- `development-plans/ARCHIVE_CLOSED` 已封口前侧收敛与系统中间层对齐计划：
  - [2026-03-06-handler-cluster-frontdoor-middle-layer-alignment/03_handler-cluster-frontdoor-middle-layer-alignment-closing-2026-03-06.md](./development-plans/ARCHIVE_CLOSED/2026-03-06-handler-cluster-frontdoor-middle-layer-alignment/03_handler-cluster-frontdoor-middle-layer-alignment-closing-2026-03-06.md)
- `development-plans/CURRENT_DEV` 持续维护时间功能与统计联动修复计划：
  - [2026-03-05-time-statistics-remediation-plan/01_time-statistics-remediation-plan-2026-03-05.md](./development-plans/CURRENT_DEV/2026-03-05-time-statistics-remediation-plan/01_time-statistics-remediation-plan-2026-03-05.md)
- `development-plans/CURRENT_DEV` 保留 OSS 代码采集与 IO 级任务规划：
  - [2026-03-05-oss-node-platform-io-plan/01_oss-code-harvest-and-io-taskplan-2026-03-05.md](./development-plans/CURRENT_DEV/2026-03-05-oss-node-platform-io-plan/01_oss-code-harvest-and-io-taskplan-2026-03-05.md)
- `ops-frontend/F_PLAN` 最近新增 modern API / graph 原子执行记录：
  - [frontend-modern-api-graph-atomic-execution-2026-03-05.md](./ops-frontend/F_PLAN/frontend-modern-api-graph-atomic-execution-2026-03-05.md)

更多历史新增请进入对应子目录 `INDEX.md`。
