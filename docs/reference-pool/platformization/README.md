# Platformization Reference Pool

更新时间：2026-03-04 09:55 PST

本目录用于支撑“代码/IO 级重构”的平台化参考。

## 0) 收敛主文档（先看这个）

- [PLATFORMIZATION_CONVERGED.md](./PLATFORMIZATION_CONVERGED.md)
- 说明：这是 7 条链路的统一决策稿（Frozen v1），包含唯一选型、90天落地顺序、统一验收标准。

## 1) 链路文档（7 条主链路）

- [01 Ingest & Workflow Platformization](./chains/01_ingest_workflow_platformization.md)
- [02 Search & Index Platformization](./chains/02_search_index_platformization.md)
- [03 Multi-tenant & Config Platformization](./chains/03_multitenant_config_platformization.md)
- [04 Crawler & Source Platformization](./chains/04_crawler_source_platformization.md)
- [05 Data Contracts & API Governance](./chains/05_data_contracts_api_governance.md)
- [06 Observability & Ops Platformization](./chains/06_observability_ops_platformization.md)
- [07 Frontend Platformization](./chains/07_frontend_platformization.md)
- [08 LLM Embedded Platformization](./chains/08_llm_embedded_platformization.md)

## 2) 开源替代“爬取快照”

- 全量链接清单：[`snapshots/all_urls.txt`](./snapshots/all_urls.txt)
- GitHub 仓库清单：[`snapshots/github_repos.txt`](./snapshots/github_repos.txt)
- GitHub 元数据目录（stars/forks/更新时间）：[`snapshots/github_repo_catalog.csv`](./snapshots/github_repo_catalog.csv)
- 各仓库 README 快照目录：[`snapshots/readmes/`](./snapshots/readmes)
- LLM 专项快照索引：[`snapshots/llm_embedded/README.md`](./snapshots/llm_embedded/README.md)

当前快照规模（基础池）：
- 链路文档：8
- 抽取链接：82（不含 LLM 专项）
- GitHub 仓库：26（不含 LLM 专项）
- README 快照：26（不含 LLM 专项）

LLM 专项快照规模见：[`snapshots/llm_embedded/README.md`](./snapshots/llm_embedded/README.md)

## 3) 可直接用于重构的输入

- 代码级映射：每条链路文档中的“当前模块 -> 平台组件 -> 迁移策略”表。
- IO级映射：每条链路文档中的 request/event/schema/queue/storage 映射与 PoC 命令。
- 风险与回滚：每条链路文档末尾的 rollback/checklist。

## 4) 推荐先做顺序

- 先看 [`PLATFORMIZATION_CONVERGED.md`](./PLATFORMIZATION_CONVERGED.md)
- 再看 [`REFACTOR_ROADMAP.md`](./REFACTOR_ROADMAP.md)
- 再按链路文档里的 PoC 最小集逐条验证
