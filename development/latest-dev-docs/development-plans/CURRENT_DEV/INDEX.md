# CURRENT_DEV Index（未封口）

仅保留尚未封口的开发计划。

## 当前进行中

- [2026-04-06 Repo Logic Gap Assessment](./2026-04-06-repo-logic-gap-assessment/01_repo-logic-gap-assessment-2026-04-06.md)
- [2026-04-06 Repo Closure Plan Aligned With Latest Direction](./2026-04-06-repo-logic-gap-assessment/02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md)
- [2026-04-06 Atomic Task List: Repo Closure Plan](./2026-04-06-repo-logic-gap-assessment/03_atomic-tasklist-repo-closure-plan-2026-04-06.md)
- [2026-04-06 Topology Risk Freeze: Compat Caller Matrix And Rollout Guards](./2026-04-06-repo-logic-gap-assessment/04_topology-risk-freeze-compat-caller-matrix-and-rollout-guards-2026-04-06.md)
- [2026-04-02 Claude Agent High-Fidelity Migration Mapping](./2026-04-02-claude-agent-high-fidelity-migration/01_claude-agent-high-fidelity-migration-mapping-2026-04-02.md)

- 2026-03-14 状态说明：
  - 来源库三车道分发已落到独立 orchestrator 模块。
  - `ItemResolver` 已独立模块化，`resolver` 更接近 compile + dispatch。
  - 来源库对外 terminal output 已切换为 clean terminal contract。
  - `legacy_result` 仅保留兼容，不再作为权威输出。
  - 历史 `single_url.py` 已物理移除；`task_ingest_single_url` 与 `single_url_*` 参数兼容层也已删除。
  - 当前单 URL 主路径已统一为 `url_routing/source_library -> postprocess_frontdoor`。


- [2026-03-11 Source Library Three-Lane Architecture](./2026-03-11-source-library-three-lane-architecture/01_source-library-three-lane-architecture-2026-03-11.md)
- [2026-03-12 Atomic Task List: Source Library Three-Lane Architecture](./2026-03-11-source-library-three-lane-architecture/02_atomic-tasklist-source-library-three-lane-architecture-2026-03-12.md)
- [2026-03-12 Validation Closure: Source Library Three-Lane Architecture](./2026-03-11-source-library-three-lane-architecture/03_validation-closure-source-library-three-lane-architecture-2026-03-12.md)
- [2026-03-12 Search Parameter Remediation: Source Library](./2026-03-11-source-library-three-lane-architecture/04_search-parameter-remediation-plan-2026-03-12.md)
- [2026-03-14 Agent Dispatch Lane Alignment and Contract Closure](./2026-03-11-source-library-three-lane-architecture/05_agent-dispatch-lane-alignment-and-contract-closure-2026-03-14.md)
- [2026-03-14 Source Library Adapter Capability Remediation](./2026-03-14-source-library-adapter-capability-remediation/01_source-library-adapter-capability-remediation-2026-03-14.md)
- [2026-03-14 Atomic Task List: Source Library Adapter Capability Remediation](./2026-03-14-source-library-adapter-capability-remediation/02_atomic-tasklist-source-library-adapter-capability-remediation-2026-03-14.md)
- [2026-03-14 Source Library Capability Service Map and Modular Rollout](./2026-03-14-source-library-adapter-capability-remediation/03_source-library-capability-service-map-and-modular-rollout-2026-03-14.md)
- [2026-03-15 Site Search Open-Source Capability Matrix and Execution](./2026-03-14-source-library-adapter-capability-remediation/04_site-search-open-source-capability-matrix-and-execution-2026-03-15.md)
- [2026-03-15 Search Contract Discovery Service and Storage](./2026-03-14-source-library-adapter-capability-remediation/05_search-contract-discovery-service-and-storage-2026-03-15.md)
- [2026-03-15 Open-Source Source Presets and Candidate Plan](./2026-03-14-source-library-adapter-capability-remediation/06_open-source-source-presets-and-candidate-plan-2026-03-15.md)
- [2026-03-15 Site Routing Remediation Table and Parser Focus](./2026-03-14-source-library-adapter-capability-remediation/07_site-routing-remediation-table-and-parser-focus-2026-03-15.md)
- [2026-03-15 Search Template Parser Pool and URL Experiment Loop](./2026-03-14-source-library-adapter-capability-remediation/08_search-template-parser-pool-and-url-experiment-loop-2026-03-15.md)
- [2026-03-25 Source-Library / Ingest Minimal Migration Plan](./2026-03-25-source-library-ingest-minimal-migration/01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- [2026-03-26 Wave 0 Freeze And Acceptance Contract](./2026-03-25-source-library-ingest-minimal-migration/02_wave0-freeze-and-acceptance-contract-2026-03-26.md)
- [2026-03-26 Atomic Task List: Source-Library / Ingest Minimal Migration](./2026-03-25-source-library-ingest-minimal-migration/03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md)
- [2026-03-26 Parallel Wave Plan: Source-Library / Ingest Minimal Migration](./2026-03-25-source-library-ingest-minimal-migration/04_parallel-wave-plan-source-library-ingest-minimal-migration-2026-03-26.md)
- [2026-03-26 Validation Closure: Source-Library / Ingest Minimal Migration](./2026-03-25-source-library-ingest-minimal-migration/05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md)
- [2026-03-27 Atomic Task List: Item Layering Migration](./2026-03-25-source-library-ingest-minimal-migration/06_atomic-tasklist-item-layering-migration-2026-03-27.md)
- [2026-03-27 Validation Closure: Item Layering Migration](./2026-03-25-source-library-ingest-minimal-migration/07_validation-closure-item-layering-migration-2026-03-27.md)
- [2026-03-27 Atomic Task List: External Project Powered Item](./2026-03-25-source-library-ingest-minimal-migration/08_atomic-tasklist-external-project-powered-item-2026-03-27.md)
- [2026-03-26 Source-Library / Ingest References Bundle](./2026-03-25-source-library-ingest-minimal-migration/references/INDEX.md)
- [2026-03-26 Batch Helper Input Boundary Contract](./2026-03-25-source-library-ingest-minimal-migration/references/2026-03-26-batch-helper-input-boundary-and-runtime-target-contract.md)
- [2026-03-26 Batch Switch / Rollout / Dispatch Precedence Matrix](./2026-03-25-source-library-ingest-minimal-migration/references/2026-03-26-batch-switch-rollout-dispatch-precedence-matrix.md)
- [2026-03-26 Item Layering Boundary Constraints](./2026-03-25-source-library-ingest-minimal-migration/references/2026-03-26-item-layering-boundary-constraints.md)
- [2026-03-27 Item Field Classification Freeze](./2026-03-25-source-library-ingest-minimal-migration/references/2026-03-27-item-field-classification-freeze.md)
- [2026-03-27 Item Execution Plan Contract](./2026-03-25-source-library-ingest-minimal-migration/references/2026-03-27-item-execution-plan-contract.md)
- [2026-03-27 External Project Powered Item Design](./2026-03-25-source-library-ingest-minimal-migration/references/2026-03-27-external-project-powered-item-design.md)
- [2026-03-12 Terminal Structured Ingest Output Standardization](./2026-03-12-data-structured-service-modularization/01_terminal-structured-ingest-output-standardization-plan-2026-03-12.md)
- [2026-03-12 Source Library Terminal Output Unification and Boundary](./2026-03-12-data-structured-service-modularization/02_source-library-terminal-output-unification-and-boundary-2026-03-12.md)
- [2026-03-12 Discrete Retained Modules and Preprocess Frontdoor Plan](./2026-03-12-data-structured-service-modularization/03_discrete-retained-modules-and-preprocess-frontdoor-plan-2026-03-12.md)
- [2026-03-09 Agent + Symbolic + Batch Search (Topic README)](./2026-03-09-agent-symbolic-batch-search-architecture/README.md)
- [2026-03-09 Agent + Symbolic + Batch Search Plan](./2026-03-09-agent-symbolic-batch-search-architecture/01_agent-symbolic-batch-search-plan-2026-03-09.md)
- [2026-03-09 Atomic Tasklist: Agent + Symbolic + Batch Search](./2026-03-09-agent-symbolic-batch-search-architecture/02_atomic-tasklist-agent-symbolic-batch-search-2026-03-09.md)
- [2026-03-10 Atomic Task Library Investigation Map (AT-00 ~ AT-09)](./2026-03-09-agent-symbolic-batch-search-architecture/03_atomic-task-library-investigation-map-2026-03-10.md)
- [2026-03-10 Parallel Execution Playbook (Spark/Codex)](./2026-03-09-agent-symbolic-batch-search-architecture/04_parallel-execution-playbook-spark-codex-2026-03-10.md)
- [2026-03-10 P1 Delivery Checklist](./2026-03-09-agent-symbolic-batch-search-architecture/05_p1-delivery-checklist-2026-03-10.md)
- [2026-03-11 Backend Full Skillization Best Practices and Implementation Plan](./2026-03-09-agent-symbolic-batch-search-architecture/09_backend-full-skillization-best-practices-and-implementation-plan-2026-03-11.md)
- [2026-03-14 Backend MCP vs Skill Layering and Rollout](./2026-03-09-agent-symbolic-batch-search-architecture/10_backend-mcp-vs-skill-layering-and-rollout-2026-03-14.md)
- [2026-03-14 Agent-Exposed Task Contract Completeness Audit](./2026-03-09-agent-symbolic-batch-search-architecture/11_agent-exposed-task-contract-completeness-audit-2026-03-14.md)
- [2026-03-25 Search Brief / Critic / Retry Policy and Agent Strategy Selection](./2026-03-09-agent-symbolic-batch-search-architecture/12_search-brief-critic-retry-policy-and-agent-strategy-selection-2026-03-25.md)
- [2026-03-25 Reference Library: Search Brief / Critic / Retry Implementation](./2026-03-09-agent-symbolic-batch-search-architecture/13_reference-library-search-brief-critic-retry-implementation-2026-03-25.md)
- [2026-03-25 Atomic Tasklist: Search Brief / Critic / Retry Implementation](./2026-03-09-agent-symbolic-batch-search-architecture/14_atomic-tasklist-search-brief-critic-retry-implementation-2026-03-25.md)
- [2026-03-25 Multi-Agent Wave Execution Order: Search Brief / Critic / Retry](./2026-03-09-agent-symbolic-batch-search-architecture/15_multi-agent-wave-execution-order-search-brief-critic-retry-2026-03-25.md)
- [2026-03-07 Writing Workbench Evolution](./2026-03-07-writing-workbench-evolution/01_writing-workbench-evolution-plan-2026-03-07.md)
- [2026-03-07 Atomic Task List: Writing Workbench Evolution](./2026-03-07-writing-workbench-evolution/02_atomic-tasklist-writing-workbench-evolution-2026-03-07.md)
- [2026-03-07 Typed Knowledge Organization](./2026-03-07-typed-knowledge-organization/01_typed-knowledge-organization-plan-2026-03-07.md)
- [2026-03-07 Atomic Task List: Typed Knowledge Organization](./2026-03-07-typed-knowledge-organization/02_atomic-tasklist-typed-knowledge-organization-2026-03-07.md)
- [2026-03-07 Graph Editing and Reporting](./2026-03-07-graph-editing-and-reporting/01_graph-editing-and-reporting-plan-2026-03-07.md)
- [2026-03-07 Atomic Task List: Graph Editing and Reporting](./2026-03-07-graph-editing-and-reporting/02_atomic-tasklist-graph-editing-and-reporting-2026-03-07.md)
- [2026-03-07 Ingest Digestion and Long-Cycle Automation](./2026-03-07-ingest-digestion-and-long-cycle-automation/01_ingest-digestion-and-long-cycle-automation-plan-2026-03-07.md)
- [2026-03-07 Atomic Task List: Ingest Digestion and Long-Cycle Automation](./2026-03-07-ingest-digestion-and-long-cycle-automation/02_atomic-tasklist-ingest-digestion-and-long-cycle-automation-2026-03-07.md)
- [2026-03-07 Crawler Source Expansion](./2026-03-07-crawler-source-expansion/01_crawler-source-expansion-plan-2026-03-07.md)
- [2026-03-07 Atomic Task List: Crawler Source Expansion](./2026-03-07-crawler-source-expansion/02_atomic-tasklist-crawler-source-expansion-2026-03-07.md)
- [2026-03-07 Frontend I18N Theme Modularization](./2026-03-07-frontend-i18n-theme-modularization/01_frontend-i18n-theme-modularization-plan-2026-03-07.md)
- [2026-03-07 Atomic Task List: Frontend I18N Theme Modularization](./2026-03-07-frontend-i18n-theme-modularization/02_atomic-tasklist-frontend-i18n-theme-modularization-2026-03-07.md)
- [2026-03-07 LLM Service and Agent Platformization](./2026-03-07-llm-service-and-agent-platformization/01_llm-service-and-agent-platformization-plan-2026-03-07.md)
- [2026-03-07 Atomic Task List: LLM Service and Agent Platformization](./2026-03-07-llm-service-and-agent-platformization/02_atomic-tasklist-llm-service-and-agent-platformization-2026-03-07.md)
- [2026-03-07 Modern-Based Dual-Interaction Frontend Topology](./2026-03-07-dual-frontend-workbench-topology/01_dual-frontend-workbench-topology-plan-2026-03-07.md)
- [2026-03-07 Atomic Task List: Modern-Based Dual-Interaction Frontend Topology](./2026-03-07-dual-frontend-workbench-topology/02_atomic-tasklist-dual-frontend-workbench-topology-2026-03-07.md)
- [2026-03-15 Frontend Three-Layer Rewrite (Topic README)](./2026-03-15-frontend-three-layer-rewrite/README.md)
- [2026-03-15 Frontend Three-Layer Rewrite Architecture](./2026-03-15-frontend-three-layer-rewrite/01_frontend-three-layer-rewrite-architecture-2026-03-15.md)
- [2026-03-15 Atomic Task List: Frontend Three-Layer Rewrite](./2026-03-15-frontend-three-layer-rewrite/02_atomic-tasklist-frontend-three-layer-rewrite-2026-03-15.md)
- [2026-04-02 Frontend Three-Layer Rewrite Closure Gap Assessment And Rollout](./2026-03-15-frontend-three-layer-rewrite/03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md)
- [2026-03-07 Abstract Planning Folderization Plan](./2026-03-07-后续安排/01_abstract-planning-folderization-plan-2026-03-07.md)
- [2026-03-07 Atomic Task List: Abstract Planning Folderization](./2026-03-07-后续安排/02_atomic-tasklist-abstract-planning-folderization-2026-03-07.md)
- [2026-03-07 Docs Root Restructuring Mapping](./2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md)
- [2026-03-07 Builtin Writing Workbench Design](./2026-03-07-builtin-writing-workbench-design/01_builtin-writing-workbench-design-2026-03-07.md)
- [2026-03-07 Atomic Task List: Builtin Writing Workbench](./2026-03-07-builtin-writing-workbench-design/02_atomic-tasklist-builtin-writing-workbench-design-2026-03-07.md)
- [2026-03-05 Time Statistics Remediation Plan](./2026-03-05-time-statistics-remediation-plan/01_time-statistics-remediation-plan-2026-03-05.md)
- [2026-03-05 Atomic Task List: Time Statistics Remediation](./2026-03-05-time-statistics-remediation-plan/02_atomic-tasklist-time-statistics-remediation-2026-03-05.md)
- [2026-03-05 Prompt-Space × Time-Window Density Spec](./2026-03-05-time-statistics-remediation-plan/03_prompt-space-time-window-density-spec-2026-03-05.md)
- [2026-03-05 Executable Plan & Orchestration (Prompt-Time Density)](./2026-03-05-time-statistics-remediation-plan/04_executable-plan-task-orchestration-prompt-time-density-2026-03-05.md)
- [2026-03-05 Execution Status & Realcase Validation](./2026-03-05-time-statistics-remediation-plan/05_execution-status-and-realcase-validation-2026-03-05.md)
- [2026-03-05 T11/T12 Execution Pack](./2026-03-05-time-statistics-remediation-plan/06_t11-t12-execution-pack-2026-03-05.md)
- [2026-03-12 Merged Plan: Time Semantics + Noun Group Density](./2026-03-12-time-semantics-density-merged-plan/ARCHIVE_01_04/01_merged-remediation-and-smart-timestamp-plan-2026-03-12.md)
- [2026-03-12 Research Report: Density Cloud + Overlap-Constrained Off-Peak Collection](./2026-03-12-time-semantics-density-merged-plan/ARCHIVE_01_04/02_research-report-density-cloud-overlap-avoid-peak-2026-03-12.md)
- [2026-03-12 Unified Report: Density Cloud + Overlap + Shift (Reference-Driven)](./2026-03-12-time-semantics-density-merged-plan/ARCHIVE_01_04/03_unified-research-and-design-report-density-cloud-overlap-shift-2026-03-12.md)
- [2026-03-12 Backend Interface Change Checklist: Density Cloud + Overlap + Shift](./2026-03-12-time-semantics-density-merged-plan/ARCHIVE_01_04/04_backend-interface-change-checklist-density-cloud-overlap-shift-2026-03-12.md)
- [2026-03-12 Merged Unified Report From Two Reports: Density Cloud + Overlap + Shift](./2026-03-12-time-semantics-density-merged-plan/05_merged-unified-report-from-two-reports-density-cloud-overlap-shift-2026-03-12.md)
- [2026-03-12 Atomic Task List: Density Cloud + Overlap + Shift](./2026-03-12-time-semantics-density-merged-plan/06_atomic-tasklist-density-cloud-overlap-shift-implementation-2026-03-12.md)
- [2026-03-14 System Investigation: Search Chain + Source Library Mounting](./2026-03-14-search-chain-source-library-mounting-audit/01_system-investigation-search-chain-source-library-mounting-2026-03-14.md)

- [2026-03-05 OSS Node Platform IO Plan](./2026-03-05-oss-node-platform-io-plan/01_oss-code-harvest-and-io-taskplan-2026-03-05.md)
- [2026-03-05 L1L2L3L4 Live R1](./2026-03-05-l1l2l3l4-live-r1/README.md)

- [2026-03-04 R41 OpenClaw Autodispatch Migration Bundle](./2026-03-04-r41-openclaw-autodispatch/README.md)
- [2026-03-04 RAG Line Round3 Filter Robustness](./2026-03-04-rag-line-round3-filter-robustness/01_rag-filter-robustness-minimal-enhancement-2026-03-04.md)
- [2026-03-08 LLM + Crawler Unified FrontDoor Architecture](./2026-03-08-llm-crawler-unified-frontdoor/01_llm-crawler-unified-frontdoor-architecture-2026-03-08.md)
- [2026-03-08 Atomic Task List: LLM + Crawler Unified FrontDoor](./2026-03-08-llm-crawler-unified-frontdoor/02_atomic-tasklist-llm-crawler-unified-frontdoor-2026-03-08.md)
- [2026-03-08 A10 Closure and Validation: LLM + Crawler Unified FrontDoor](./2026-03-08-llm-crawler-unified-frontdoor/03_a10-closure-and-validation-2026-03-08.md)

- [2026-03-01 Open Source Platform Integration](./2026-03-01-open-source-platform-integration/01_multi-agent-taskboard-open-source-platform-integration-2026-03-01.md)
- [2026-03-02 Single URL First Ingest](./2026-03-02-single-url-first-ingest-allocation-plan/01_single-url-first-ingest-allocation-plan-2026-03-02.md)
- [2026-03-02 Source Time Window Smart Timestamp](./2026-03-02-source-time-window-smart-timestamp-plan/01_source-time-window-smart-timestamp-plan-2026-03-02.md)
- [2026-03-02 Graph Node Standardization](./2026-03-02-graph-node-standardization-a-then-b-plan/01_graph-node-standardization-a-then-b-plan-2026-03-02.md)
- [2026-03-02 Global Vectorization](./2026-03-02-global-vectorization-general-foundation/01_global-vectorization-general-foundation-plan-2026-03-03.md)
- [2026-03-02 Graph 3D Force Engine](./2026-03-02-graph-3d-force-engine-parallel-migration/01_graph-3d-force-engine-parallel-migration-2026-03-02.md)
- [2026-03-03 Platformization First Vectorization GM](./2026-03-03-platformization-first-vectorization-gm/01_platformization-first-vectorization-gm-2026-03-03.md)

## 已封口归档

已封口开发计划已移至 [ARCHIVE_CLOSED](../ARCHIVE_CLOSED/INDEX.md)。

## 2026-03-14 迁移补充（最新口径主入口）

- 最新口径主入口：[2026-03-14-time-semantics-density-merged-plan/README.md](./2026-03-14-time-semantics-density-merged-plan/README.md)
- 变更记录：[2026-03-14-time-semantics-density-merged-plan/CHANGELOG_2026-03-14.md](./2026-03-14-time-semantics-density-merged-plan/CHANGELOG_2026-03-14.md)
- 旧目录兼容说明：[2026-03-12-time-semantics-density-merged-plan/README.md](./2026-03-12-time-semantics-density-merged-plan/README.md)
