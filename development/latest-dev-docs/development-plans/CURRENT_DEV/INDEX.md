# CURRENT_DEV Index（当前入口 / 未封口 / 待迁档）

更新时间：2026-05-22（PST）

本目录优先保留尚未封口且仍可作为现行入口的开发计划；少量总体性完成审计和当前主入口文档可暂留，过程记录已迁入 [`ARCHIVE_CLOSED`](../ARCHIVE_CLOSED/INDEX.md)，已被后续代码事实或更新主入口覆盖的早期文档已迁入 [`ARCHIVE_RETIRED`](../ARCHIVE_RETIRED/INDEX.md)。

## 本次已迁档

- `clear_closed` [2026-03-02 Ingest Chain Full Branch Map](../ARCHIVE_CLOSED/2026-03-02-ingest-chain-full-branch-map/)
- `clear_closed` [2026-04-06 Repo Logic Gap Assessment](../ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/)
- `clear_closed` [2026-04-02 Claude Agent High-Fidelity Migration](../ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration/INDEX.md)
- `process_records` [2026-04-02 Claude Agent High-Fidelity Migration Process Records](../ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/INDEX.md)

## 本次已退场

- `retired` [2026-03-03 Platformization First Vectorization GM](../ARCHIVE_RETIRED/2026-03-03-platformization-first-vectorization-gm/)
- `retired` [2026-03-04 RAG Line Round3 Filter Robustness](../ARCHIVE_RETIRED/2026-03-04-rag-line-round3-filter-robustness/)
- `retired` [2026-03-07 Builtin Writing Workbench Design](../ARCHIVE_RETIRED/2026-03-07-builtin-writing-workbench-design/)
- `retired` [2026-03-12 Time Semantics Density Merged Plan](../ARCHIVE_RETIRED/2026-03-12-time-semantics-density-merged-plan/)

## 标签说明

- `partial`：已有明显落地或局部收口，但整目录未闭环
- `not_closed`：仍处于未完成计划或明确未收口状态
- `no_closure_claim`：目录没有收口声明，或只是映射 / 占位 / 规划材料
- 时效标签详见 [`STATUS_AUDIT_2026-04-07.md`](./STATUS_AUDIT_2026-04-07.md)

## 剩余状态分布

- `partial`: 23
- `not_closed`: 9
- `no_closure_claim`: 4

## Agent High-Fidelity Migration Split Result

`2026-04-02-claude-agent-high-fidelity-migration` no longer has an active `CURRENT_DEV` entry. Completed current-entry specs, final closure evidence, and the D47 diagnostic closure are archived at [ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration](../ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration/INDEX.md); numbered process records remain in [ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records](../ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/INDEX.md).

If a new AgentCore diagnostic reopens, create a new `D48` or later topic under `CURRENT_DEV`; do not append fresh diagnostic work to the closed `2026-04-02` archive.

## Partial

- `[partial][doc_aligned]` [2026-03-01 Open Source Platform Integration](./2026-03-01-open-source-platform-integration/01_multi-agent-taskboard-open-source-platform-integration-2026-03-01.md)
- `[partial][doc_aligned]` [2026-05-14 Global Vectorization General Foundation](./2026-05-14-global-vectorization-general-foundation/01_global-vectorization-general-foundation-plan-2026-05-14.md) - local_index evidence: [runtime-contract](../../automation-runs/local-index-runtime-contract/2026-05-22/README.md), [benchmark-quality](../../automation-runs/local-index-lancedb-benchmark/2026-05-22/README.md)
- `[partial][doc_drift]` [2026-03-02 Graph 3D Force Engine Parallel Migration](./2026-03-02-graph-3d-force-engine-parallel-migration/01_graph-3d-force-engine-parallel-migration-2026-03-02.md)
- `[partial][doc_aligned][fetch_router_gap]` [2026-03-02 Ingest Platformization Assessment](./2026-03-02-ingest-platformization-assessment/01_ingest-platformization-assessment-and-roadmap-2026-03-02.md) - ingest/frontdoor evidence: [ingest-frontdoor-closure/2026-05-22](../../automation-runs/ingest-frontdoor-closure/2026-05-22/README.md)
- `[partial][doc_drift]` [2026-03-02 Meaningful Ingest Guardrails Plan](./2026-03-02-meaningful-ingest-guardrails-plan/01_meaningful-ingest-guardrails-plan-2026-03-02.md)
- `[partial][doc_aligned][fetch_router_gap]` [2026-03-02 Single URL First Ingest Allocation Plan](./2026-03-02-single-url-first-ingest-allocation-plan/01_single-url-first-ingest-allocation-plan-2026-03-02.md) - legacy `single_url` mapped to source-library/frontdoor chain; evidence: [ingest-frontdoor-closure/2026-05-22](../../automation-runs/ingest-frontdoor-closure/2026-05-22/README.md)
- `[partial][doc_aligned]` [2026-03-02 Source Time Window Smart Timestamp Plan](./2026-03-02-source-time-window-smart-timestamp-plan/01_source-time-window-smart-timestamp-plan-2026-03-02.md)
- `[partial][external_gap]` [2026-03-04 R41 OpenClaw Autodispatch](./2026-03-04-r41-openclaw-autodispatch/README.md)
- `[partial][doc_aligned]` [2026-03-05 OSS Node Platform IO Plan](./2026-03-05-oss-node-platform-io-plan/01_oss-code-harvest-and-io-taskplan-2026-03-05.md)
- `[partial][doc_stale]` [2026-03-05 Time Statistics Remediation Plan](./2026-03-05-time-statistics-remediation-plan/01_time-statistics-remediation-plan-2026-03-05.md)
- `[partial][doc_aligned][fetch_router_gap]` [2026-03-08 LLM Crawler Unified FrontDoor](./2026-03-08-llm-crawler-unified-frontdoor/01_llm-crawler-unified-frontdoor-architecture-2026-03-08.md) - current entry map refreshed; high-JS/router and tri-state gaps remain
- `[partial][doc_aligned]` [2026-03-09 Agent Symbolic Batch Search Architecture](./2026-03-09-agent-symbolic-batch-search-architecture/README.md)
- `[partial][doc_drift]` [2026-03-11 Source Library Three-Lane Architecture](./2026-03-11-source-library-three-lane-architecture/01_source-library-three-lane-architecture-2026-03-11.md)
- `[partial][doc_aligned]` [2026-03-12 Data Structured Service Modularization](./2026-03-12-data-structured-service-modularization/01_terminal-structured-ingest-output-standardization-plan-2026-03-12.md)
- `[partial][doc_aligned]` [2026-03-14 Consumer-Side Modularization](./2026-03-14-consumer-side-modularization/01_consumer-side-modularization-assessment-and-plan-2026-03-14.md)
- `[partial][doc_aligned]` [2026-03-14 Search Chain Source-Library Mounting Audit](./2026-03-14-search-chain-source-library-mounting-audit/01_system-investigation-search-chain-source-library-mounting-2026-03-14.md)
- `[partial][doc_aligned]` [2026-03-14 Source-Library Adapter Capability Remediation](./2026-03-14-source-library-adapter-capability-remediation/01_source-library-adapter-capability-remediation-2026-03-14.md) - public live probe evidence: [source-library-live-probes/2026-05-22](../../automation-runs/source-library-live-probes/2026-05-22/README.md); 45-site replay gate: [source-library-replay-scaleout/2026-05-22](../../automation-runs/source-library-replay-scaleout/2026-05-22/README.md)
- `[partial][doc_aligned]` [2026-03-14 Time Semantics Density Merged Plan](./2026-03-14-time-semantics-density-merged-plan/README.md)
- `[partial][doc_aligned]` [2026-03-07 Dual Frontend Workbench Topology](./2026-03-07-dual-frontend-workbench-topology/01_dual-frontend-workbench-topology-plan-2026-03-07.md) - topology contract evidence: [frontend-topology-theme/2026-05-22](../../automation-runs/frontend-topology-theme/2026-05-22/README.md)
- `[partial][doc_aligned]` [2026-03-07 Frontend I18N Theme Modularization](./2026-03-07-frontend-i18n-theme-modularization/01_frontend-i18n-theme-modularization-plan-2026-03-07.md) - i18n/theme contract evidence: [frontend-topology-theme/2026-05-22](../../automation-runs/frontend-topology-theme/2026-05-22/README.md)
- `[partial][doc_aligned]` [2026-03-15 Frontend Three-Layer Rewrite](./2026-03-15-frontend-three-layer-rewrite/README.md)
- `[partial][doc_aligned]` [2026-03-25 Source-Library Ingest Minimal Migration](./2026-03-25-source-library-ingest-minimal-migration/01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- `[partial][doc_drift]` [MERGED_OVERVIEW](./MERGED_OVERVIEW/index.md)

## Not Closed

- `[not_closed][doc_aligned]` [2026-04-07 Parallel Agent Wave Orchestration](./2026-04-07-parallel-agent-wave-orchestration/README.md)
- `[not_closed][planned_ready]` [2026-05-22 Clue Chain Investigation Tool](./2026-05-22-clue-chain-investigation-tool/01_clue-chain-investigation-tool-plan-2026-05-22.md)
- `[not_closed][doc_aligned]` [2026-03-07 Crawler Source Expansion](./2026-03-07-crawler-source-expansion/01_crawler-source-expansion-plan-2026-03-07.md)
- `[not_closed][doc_aligned]` [2026-03-07 Docs Root Restructuring](./2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md)
- `[not_closed][doc_aligned]` [2026-03-07 Graph Editing And Reporting](./2026-03-07-graph-editing-and-reporting/01_graph-editing-and-reporting-plan-2026-03-07.md) - API handoff evidence: [graph-handoff-evidence/2026-05-22](../../automation-runs/graph-handoff-evidence/2026-05-22/README.md)
- `[not_closed][doc_stale]` [2026-03-07 LLM Service And Agent Platformization](./2026-03-07-llm-service-and-agent-platformization/01_llm-service-and-agent-platformization-plan-2026-03-07.md)
- `[not_closed][doc_aligned]` [2026-03-07 Typed Knowledge Organization](./2026-03-07-typed-knowledge-organization/01_typed-knowledge-organization-plan-2026-03-07.md)
- `[not_closed][doc_stale]` [2026-03-07 Writing Workbench Evolution](./2026-03-07-writing-workbench-evolution/01_writing-workbench-evolution-plan-2026-03-07.md)
- `[not_closed][doc_aligned]` [2026-03-07 后续安排](./2026-03-07-后续安排/01_abstract-planning-folderization-plan-2026-03-07.md)

## No Closure Claim / Retained Current Evidence

- `[no_closure_claim][planned_ready]` [2026-05-14 SearXNG / YaCy Isolated Deployment And Search Provider Integration Plan](./2026-05-14-local-open-search-provider-isolation/INDEX.md)
- `[no_closure_claim][doc_drift]` [2026-03-02 Graph Node Standardization A Then B Plan](./2026-03-02-graph-node-standardization-a-then-b-plan/01_graph-node-standardization-a-then-b-plan-2026-03-02.md)
- `[no_closure_claim][doc_aligned]` [2026-03-07 Ingest Digestion And Long-Cycle Automation](./2026-03-07-ingest-digestion-and-long-cycle-automation/01_ingest-digestion-and-long-cycle-automation-plan-2026-03-07.md)
- `[no_closure_claim][placeholder]` `2026-03-24 Frontend Visual Layering`（placeholder path is not present in this snapshot）

## 说明

- 目录标签以当前仓库代码事实为准，不以目录名、历史 closure 文件名或单篇执行记录为准。
- 已迁入 `ARCHIVE_RETIRED` 的目录只作为历史背景，不再作为当前实施入口。
- 含 `doc_stale` / `stale_claim` / `doc_drift` 的目录，继续推进前应先回补文档，不宜直接把现有文档当作最新事实。
