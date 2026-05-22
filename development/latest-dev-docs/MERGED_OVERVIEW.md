# 合并文档总览

Updated: 2026-05-22 PST

## 目录级合并结果

| 目录 | 合并主文档 | 校对文档 | 说明 |
|---|---|---|---|
| `root-plans` | [main/MERGED_PLAN.md](./root-plans/main/MERGED_PLAN.md) | [G_REVIEW/MERGED_PLAN_REVIEW.md](./root-plans/G_REVIEW/MERGED_PLAN_REVIEW.md) | 根计划文档去重合并与时效校对 |
| `backend-core` | [main/MERGED_BACKEND_CORE.md](./backend-core/main/MERGED_BACKEND_CORE.md) | [G_REVIEW/MERGED_BACKEND_CORE_REVIEW.md](./backend-core/G_REVIEW/MERGED_BACKEND_CORE_REVIEW.md) | 运行、接口、测试三段合并 |
| `backend-docs` | [main/MERGED_BACKEND_DOCS.md](./backend-docs/main/MERGED_BACKEND_DOCS.md) | [G_REVIEW/MERGED_BACKEND_DOCS_REVIEW.md](./backend-docs/G_REVIEW/MERGED_BACKEND_DOCS_REVIEW.md) | 架构/API/采集/路线图统一汇总 |
| `ops-frontend` | [main/MERGED_OPS_FRONTEND.md](./ops-frontend/main/MERGED_OPS_FRONTEND.md) | [G_REVIEW/MERGED_OPS_FRONTEND_REVIEW.md](./ops-frontend/G_REVIEW/MERGED_OPS_FRONTEND_REVIEW.md) | 部署、前端、Figma、快速启动归并 |
| `frontend-modern` | [main/MERGED_FRONTEND_MODERN.md](./frontend-modern/main/MERGED_FRONTEND_MODERN.md) | [main/index.md](./frontend-modern/main/index.md) | modern 前端专项入口补齐 |
| `development-plans` | [main/MERGED_DEVELOPMENT_PLANS.md](./development-plans/main/MERGED_DEVELOPMENT_PLANS.md) | [G_REVIEW/MERGED_DEVELOPMENT_PLANS_REVIEW.md](./development-plans/G_REVIEW/MERGED_DEVELOPMENT_PLANS_REVIEW.md) | 阶段/里程碑/依赖视角合并 |

## 使用建议

1. 先读本文件和各目录 `INDEX.md`，再进入合并主文档。
2. 校对文档用于识别过时项，不直接替代原始来源文档。
3. 若要提交发布版，优先更新 `SYNC_STATUS.md` 的检查时间。

## 最近新增

- `automation-runs`：
  - [2026-05-22 Local Index LanceDB Benchmark Quality](./automation-runs/local-index-lancedb-benchmark/2026-05-22/README.md)
  - [2026-05-22 Ingest / Frontdoor Closure Evidence](./automation-runs/ingest-frontdoor-closure/2026-05-22/README.md)
  - [2026-05-22 Frontend Topology / I18N / Theme Contract Evidence](./automation-runs/frontend-topology-theme/2026-05-22/README.md)
  - [2026-05-22 Frontend Runtime Visual Evidence](./automation-runs/frontend-runtime-visual/2026-05-22/README.md)
  - [2026-05-22 Local Index LanceDB Runtime Smoke](./automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/README.md)
  - [2026-05-22 Local Index Runtime Contract Evidence](./automation-runs/local-index-runtime-contract/2026-05-22/README.md)
  - [2026-05-22 GraphPage Frontend E2E Evidence](./automation-runs/graph-frontend-e2e/2026-05-22/README.md)
  - [2026-05-22 Graph Visual Evidence](./automation-runs/graph-visual-evidence/2026-05-22/README.md)
  - [2026-05-22 Graph Curated Handoff API Evidence](./automation-runs/graph-handoff-evidence/2026-05-22/README.md)
  - [2026-05-22 Storybook / Launcher Gates Evidence](./automation-runs/storybook-launcher-gates/2026-05-22/README.md)
  - [2026-05-22 Development Docs Folder Audit And Landing Report](./automation-runs/dev-docs-folder-audit-2026-05-22/README.md)
  - [2026-05-22 Search Provider Trace Offline Artifact Contract](./automation-runs/search-provider-trace-artifacts/2026-05-22/README.md)
  - [2026-05-22 Source Library Real Probes](./automation-runs/source-library-real-probes/2026-05-22/README.md)
  - [2026-05-22 Source Library Public Live Probes](./automation-runs/source-library-live-probes/2026-05-22/README.md)
  - [2026-05-22 Wave2 Worktree Plan And Integration Status](./automation-runs/dev-docs-folder-audit-2026-05-22/wave2-worktree-plan-2026-05-22.md)
  - [2026-05-22 Wave3 Worktree Plan And Integration Status](./automation-runs/dev-docs-folder-audit-2026-05-22/wave3-worktree-plan-2026-05-22.md)
- `backend-docs`：
  - [2026-05-22 Backend API Schema Inventory](./backend-docs/B_API/API_SCHEMA_INVENTORY_2026-05-22.md)
- `frontend-modern`：
  - [2026-05-22 frontend-modern topology/i18n/theme contract status](./frontend-modern/main/MERGED_FRONTEND_MODERN.md)
  - [2026-05-22 frontend-modern standard docs entry](./frontend-modern/INDEX.md)
- `development-plans`：
  - [2026-05-22 A_ARCHITECTURE index](./development-plans/A_ARCHITECTURE/INDEX.md)
  - [2026-05-22 B_API index](./development-plans/B_API/INDEX.md)
  - [2026-05-22 C_INGEST index](./development-plans/C_INGEST/INDEX.md)
  - [2026-05-22 D_TEST index](./development-plans/D_TEST/INDEX.md)
  - [2026-05-22 E_OPS index](./development-plans/E_OPS/INDEX.md)
  - [2026-05-22 F_PLAN index](./development-plans/F_PLAN/INDEX.md)
- 根目录：
  - [2026-05-14 当前预发布说明：pre-release-2026-05-14-rc1](../../RELEASE_NOTES_pre-release-2026-05-14-rc1.md)
- `automation-runs`：
  - [2026-05-14 pre-release-2026-05-14-rc1 completion audit](./automation-runs/pre-release-2026-05-14-rc1/completion_audit.md)
  - [2026-05-14 pre-release-2026-05-14-rc1 release merge manifest](./automation-runs/pre-release-2026-05-14-rc1/release_package_manifest.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-05-14 AgentCore Session Diagnostic Breakpoints And Repair Plan](./development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration/47_agentcore-session-diagnostic-breakpoints-and-repair-plan-2026-05-14.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-05-14 Agent Context Manifest And Demand-Read Synthesis（已实现并回归覆盖）](./development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration/46_agent-context-manifest-and-demand-read-synthesis-2026-05-14.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-05-14 Agent High-Fidelity Migration Final Completion Audit](./development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration/45_agent-high-fidelity-migration-final-completion-audit-2026-05-14.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-05-14 Claude Agent High-Fidelity Migration Process Records](./development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/INDEX.md)
- `development-plans/CURRENT_DEV`：
  - [2026-05-14 SearXNG / YaCy Isolated Deployment And Search Provider Integration Plan](./development-plans/CURRENT_DEV/2026-05-14-local-open-search-provider-isolation/INDEX.md)
  - [2026-05-22 Search Provider Trace Contract Closure Replay](./development-plans/CURRENT_DEV/2026-05-14-local-open-search-provider-isolation/10_search-provider-trace-contract-closure-replay-2026-05-22.md)
- `development-plans/CURRENT_DEV`：
  - [2026-05-22 Source Library Public Live Probes](./development-plans/CURRENT_DEV/2026-03-14-source-library-adapter-capability-remediation/11_wave3-public-live-probes-2026-05-22.md)
- `development-plans/CURRENT_DEV`：
  - [2026-05-14 Optional Search / Index Enhancements Launcher Integration](./development-plans/CURRENT_DEV/2026-05-14-local-open-search-provider-isolation/09_optional-search-index-enhancements-launcher-integration-2026-05-14.md)
- `development-plans/CURRENT_DEV`：
  - [2026-04-07 Parallel Agent Wave Orchestration](./development-plans/CURRENT_DEV/2026-04-07-parallel-agent-wave-orchestration/01_parallel-agent-wave-orchestration-plan-2026-04-07.md)
  - [2026-04-07 Subagent Task Contract Template](./development-plans/CURRENT_DEV/2026-04-07-parallel-agent-wave-orchestration/02_subagent-task-contract-template-2026-04-07.md)
  - [2026-04-07 Wave 0 Baseline Freeze Task Pool](./development-plans/CURRENT_DEV/2026-04-07-parallel-agent-wave-orchestration/03_wave0-baseline-freeze-task-pool-2026-04-07.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-04-07 Runtime Smoke Reproduction: Repo Closure Plan](./development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/09_runtime-smoke-reproduction-repo-closure-plan-2026-04-07.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-04-07 Agent Runtime Canonical Path Closure: Repo Closure Plan](./development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/08_agent-runtime-canonical-path-closure-2026-04-07.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-04-07 Topic Closure Matrix: Repo Closure Plan](./development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/07_topic-closure-matrix-repo-closure-plan-2026-04-07.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-04-07 Validation Closure: Repo Closure Plan](./development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/06_validation-closure-repo-closure-plan-2026-04-07.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-04-07 Governance Default Gates, PR Evidence, and Docs Navigation](./development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/05_governance-default-gates-pr-evidence-and-docs-navigation-2026-04-07.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-04-06 Topology Risk Freeze: Compat Caller Matrix And Rollout Guards](./development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/04_topology-risk-freeze-compat-caller-matrix-and-rollout-guards-2026-04-06.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-04-06 Atomic Task List: Repo Closure Plan](./development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/03_atomic-tasklist-repo-closure-plan-2026-04-06.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-04-06 Repo Closure Plan Aligned With Latest Direction](./development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/02_repo-closure-plan-aligned-with-latest-direction-2026-04-06.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-04-06 Repo Logic Gap Assessment](./development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/01_repo-logic-gap-assessment-2026-04-06.md)
- `development-plans/CURRENT_DEV`：
  - [2026-04-07 Current-Dev Status Audit](./development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md)
- `development-plans/ARCHIVE_RETIRED`：
  - [2026-04-07 Retired Development Plans Index](./development-plans/ARCHIVE_RETIRED/INDEX.md)
- `development-plans/CURRENT_DEV`：
  - [2026-03-15-frontend-three-layer-rewrite/03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md](./development-plans/CURRENT_DEV/2026-03-15-frontend-three-layer-rewrite/03_frontend-three-layer-rewrite-closure-gap-assessment-and-rollout-2026-04-02.md)
- `backend-core`：
  - [F_PLAN/2026-03-14-frontdoor-content-extraction-cleaning-best-practices.md](./backend-core/F_PLAN/2026-03-14-frontdoor-content-extraction-cleaning-best-practices.md)
  - [D_TEST/2026-03-14-source-library-frontdoor-cleaning-sample-validation-temp.md](./backend-core/D_TEST/2026-03-14-source-library-frontdoor-cleaning-sample-validation-temp.md)
- `development-plans/CURRENT_DEV`：
  - [2026-03-25-source-library-ingest-minimal-migration/01_source-library-ingest-minimal-migration-plan-2026-03-25.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
  - [2026-03-25-source-library-ingest-minimal-migration/02_wave0-freeze-and-acceptance-contract-2026-03-26.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/02_wave0-freeze-and-acceptance-contract-2026-03-26.md)
  - [2026-03-25-source-library-ingest-minimal-migration/03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md)
  - [2026-03-25-source-library-ingest-minimal-migration/04_parallel-wave-plan-source-library-ingest-minimal-migration-2026-03-26.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/04_parallel-wave-plan-source-library-ingest-minimal-migration-2026-03-26.md)
  - [2026-03-25-source-library-ingest-minimal-migration/05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/05_validation-closure-source-library-ingest-minimal-migration-2026-03-26.md)
  - [2026-03-25-source-library-ingest-minimal-migration/06_atomic-tasklist-item-layering-migration-2026-03-27.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/06_atomic-tasklist-item-layering-migration-2026-03-27.md)
  - [2026-03-25-source-library-ingest-minimal-migration/07_validation-closure-item-layering-migration-2026-03-27.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/07_validation-closure-item-layering-migration-2026-03-27.md)
  - [2026-03-25-source-library-ingest-minimal-migration/08_atomic-tasklist-external-project-powered-item-2026-03-27.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/08_atomic-tasklist-external-project-powered-item-2026-03-27.md)
  - [2026-03-25-source-library-ingest-minimal-migration/references/INDEX.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/references/INDEX.md)
  - [2026-03-25-source-library-ingest-minimal-migration/references/2026-03-26-batch-helper-input-boundary-and-runtime-target-contract.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/references/2026-03-26-batch-helper-input-boundary-and-runtime-target-contract.md)
  - [2026-03-25-source-library-ingest-minimal-migration/references/2026-03-26-batch-switch-rollout-dispatch-precedence-matrix.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/references/2026-03-26-batch-switch-rollout-dispatch-precedence-matrix.md)
  - [2026-03-25-source-library-ingest-minimal-migration/references/2026-03-26-item-layering-boundary-constraints.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/references/2026-03-26-item-layering-boundary-constraints.md)
  - [2026-03-25-source-library-ingest-minimal-migration/references/2026-03-27-item-field-classification-freeze.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/references/2026-03-27-item-field-classification-freeze.md)
  - [2026-03-25-source-library-ingest-minimal-migration/references/2026-03-27-item-execution-plan-contract.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/references/2026-03-27-item-execution-plan-contract.md)
  - [2026-03-25-source-library-ingest-minimal-migration/references/2026-03-27-external-project-powered-item-design.md](./development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/references/2026-03-27-external-project-powered-item-design.md)
- `development-plans/CURRENT_DEV`：
  - [2026-03-11-source-library-three-lane-architecture/03_validation-closure-source-library-three-lane-architecture-2026-03-12.md](./development-plans/CURRENT_DEV/2026-03-11-source-library-three-lane-architecture/03_validation-closure-source-library-three-lane-architecture-2026-03-12.md)
  - [2026-03-14-source-library-adapter-capability-remediation/01_source-library-adapter-capability-remediation-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-14-source-library-adapter-capability-remediation/01_source-library-adapter-capability-remediation-2026-03-14.md)
  - [2026-03-14-source-library-adapter-capability-remediation/02_atomic-tasklist-source-library-adapter-capability-remediation-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-14-source-library-adapter-capability-remediation/02_atomic-tasklist-source-library-adapter-capability-remediation-2026-03-14.md)
  - [2026-03-14-source-library-adapter-capability-remediation/03_source-library-capability-service-map-and-modular-rollout-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-14-source-library-adapter-capability-remediation/03_source-library-capability-service-map-and-modular-rollout-2026-03-14.md)
  - [2026-03-14-source-library-adapter-capability-remediation/04_site-search-open-source-capability-matrix-and-execution-2026-03-15.md](./development-plans/CURRENT_DEV/2026-03-14-source-library-adapter-capability-remediation/04_site-search-open-source-capability-matrix-and-execution-2026-03-15.md)
  - [2026-03-14-source-library-adapter-capability-remediation/05_search-contract-discovery-service-and-storage-2026-03-15.md](./development-plans/CURRENT_DEV/2026-03-14-source-library-adapter-capability-remediation/05_search-contract-discovery-service-and-storage-2026-03-15.md)
  - [2026-03-14-source-library-adapter-capability-remediation/06_open-source-source-presets-and-candidate-plan-2026-03-15.md](./development-plans/CURRENT_DEV/2026-03-14-source-library-adapter-capability-remediation/06_open-source-source-presets-and-candidate-plan-2026-03-15.md)
  - [2026-03-14-source-library-adapter-capability-remediation/07_site-routing-remediation-table-and-parser-focus-2026-03-15.md](./development-plans/CURRENT_DEV/2026-03-14-source-library-adapter-capability-remediation/07_site-routing-remediation-table-and-parser-focus-2026-03-15.md)
  - [2026-03-14-source-library-adapter-capability-remediation/08_search-template-parser-pool-and-url-experiment-loop-2026-03-15.md](./development-plans/CURRENT_DEV/2026-03-14-source-library-adapter-capability-remediation/08_search-template-parser-pool-and-url-experiment-loop-2026-03-15.md)
  - [2026-03-12-data-structured-service-modularization/02_source-library-terminal-output-unification-and-boundary-2026-03-12.md](./development-plans/CURRENT_DEV/2026-03-12-data-structured-service-modularization/02_source-library-terminal-output-unification-and-boundary-2026-03-12.md)
  - [2026-03-12-data-structured-service-modularization/05_runtime-validation-source-library-write-through-and-structured-path-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-12-data-structured-service-modularization/05_runtime-validation-source-library-write-through-and-structured-path-2026-03-14.md)
  - [2026-03-12-data-structured-service-modularization/06_atomic-tasklist-quality-frontdoor-source-library-first-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-12-data-structured-service-modularization/06_atomic-tasklist-quality-frontdoor-source-library-first-2026-03-14.md)
  - [2026-03-14-consumer-side-modularization/01_consumer-side-modularization-assessment-and-plan-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-14-consumer-side-modularization/01_consumer-side-modularization-assessment-and-plan-2026-03-14.md)
  - [2026-03-14-search-chain-source-library-mounting-audit/01_system-investigation-search-chain-source-library-mounting-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-14-search-chain-source-library-mounting-audit/01_system-investigation-search-chain-source-library-mounting-2026-03-14.md)
- `development-plans/ARCHIVE_RETIRED`：
  - [2026-03-12-time-semantics-density-merged-plan/README.md](./development-plans/ARCHIVE_RETIRED/2026-03-12-time-semantics-density-merged-plan/README.md)
- `development-plans/CURRENT_DEV`：
  - [2026-03-11-source-library-three-lane-architecture/01_source-library-three-lane-architecture-2026-03-11.md](./development-plans/CURRENT_DEV/2026-03-11-source-library-three-lane-architecture/01_source-library-three-lane-architecture-2026-03-11.md)
  - [2026-03-11-source-library-three-lane-architecture/02_atomic-tasklist-source-library-three-lane-architecture-2026-03-12.md](./development-plans/CURRENT_DEV/2026-03-11-source-library-three-lane-architecture/02_atomic-tasklist-source-library-three-lane-architecture-2026-03-12.md)
  - [2026-03-11-source-library-three-lane-architecture/03_validation-closure-source-library-three-lane-architecture-2026-03-12.md](./development-plans/CURRENT_DEV/2026-03-11-source-library-three-lane-architecture/03_validation-closure-source-library-three-lane-architecture-2026-03-12.md)
  - [2026-03-11-source-library-three-lane-architecture/04_search-parameter-remediation-plan-2026-03-12.md](./development-plans/CURRENT_DEV/2026-03-11-source-library-three-lane-architecture/04_search-parameter-remediation-plan-2026-03-12.md)
  - [2026-03-11-source-library-three-lane-architecture/05_agent-dispatch-lane-alignment-and-contract-closure-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-11-source-library-three-lane-architecture/05_agent-dispatch-lane-alignment-and-contract-closure-2026-03-14.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/11_agent-exposed-task-contract-completeness-audit-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/11_agent-exposed-task-contract-completeness-audit-2026-03-14.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/12_search-brief-critic-retry-policy-and-agent-strategy-selection-2026-03-25.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/12_search-brief-critic-retry-policy-and-agent-strategy-selection-2026-03-25.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/13_reference-library-search-brief-critic-retry-implementation-2026-03-25.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/13_reference-library-search-brief-critic-retry-implementation-2026-03-25.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/14_atomic-tasklist-search-brief-critic-retry-implementation-2026-03-25.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/14_atomic-tasklist-search-brief-critic-retry-implementation-2026-03-25.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/15_multi-agent-wave-execution-order-search-brief-critic-retry-2026-03-25.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/15_multi-agent-wave-execution-order-search-brief-critic-retry-2026-03-25.md)
  - [2026-03-12-data-structured-service-modularization/01_terminal-structured-ingest-output-standardization-plan-2026-03-12.md](./development-plans/CURRENT_DEV/2026-03-12-data-structured-service-modularization/01_terminal-structured-ingest-output-standardization-plan-2026-03-12.md)
  - [2026-03-12-data-structured-service-modularization/02_source-library-terminal-output-unification-and-boundary-2026-03-12.md](./development-plans/CURRENT_DEV/2026-03-12-data-structured-service-modularization/02_source-library-terminal-output-unification-and-boundary-2026-03-12.md)
  - [2026-03-12-data-structured-service-modularization/03_discrete-retained-modules-and-preprocess-frontdoor-plan-2026-03-12.md](./development-plans/CURRENT_DEV/2026-03-12-data-structured-service-modularization/03_discrete-retained-modules-and-preprocess-frontdoor-plan-2026-03-12.md)
  - [2026-03-12-data-structured-service-modularization/05_runtime-validation-source-library-write-through-and-structured-path-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-12-data-structured-service-modularization/05_runtime-validation-source-library-write-through-and-structured-path-2026-03-14.md)
  - [2026-03-14-consumer-side-modularization/01_consumer-side-modularization-assessment-and-plan-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-14-consumer-side-modularization/01_consumer-side-modularization-assessment-and-plan-2026-03-14.md)
- `development-plans/CURRENT_DEV`：
  - [2026-03-09-agent-symbolic-batch-search-architecture/README.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/README.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/01_agent-symbolic-batch-search-plan-2026-03-09.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/01_agent-symbolic-batch-search-plan-2026-03-09.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/02_atomic-tasklist-agent-symbolic-batch-search-2026-03-09.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/02_atomic-tasklist-agent-symbolic-batch-search-2026-03-09.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/03_atomic-task-library-investigation-map-2026-03-10.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/03_atomic-task-library-investigation-map-2026-03-10.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/04_parallel-execution-playbook-spark-codex-2026-03-10.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/04_parallel-execution-playbook-spark-codex-2026-03-10.md)
  - [2026-03-09-agent-symbolic-batch-search-architecture/10_backend-mcp-vs-skill-layering-and-rollout-2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture/10_backend-mcp-vs-skill-layering-and-rollout-2026-03-14.md)
  - [2026-03-07-writing-workbench-evolution/01_writing-workbench-evolution-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-writing-workbench-evolution/01_writing-workbench-evolution-plan-2026-03-07.md)
  - [2026-03-07-writing-workbench-evolution/02_atomic-tasklist-writing-workbench-evolution-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-writing-workbench-evolution/02_atomic-tasklist-writing-workbench-evolution-2026-03-07.md)
  - [2026-03-07-typed-knowledge-organization/01_typed-knowledge-organization-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-typed-knowledge-organization/01_typed-knowledge-organization-plan-2026-03-07.md)
  - [2026-03-07-typed-knowledge-organization/02_atomic-tasklist-typed-knowledge-organization-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-typed-knowledge-organization/02_atomic-tasklist-typed-knowledge-organization-2026-03-07.md)
  - [2026-03-07-graph-editing-and-reporting/01_graph-editing-and-reporting-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-graph-editing-and-reporting/01_graph-editing-and-reporting-plan-2026-03-07.md)
  - [2026-03-07-graph-editing-and-reporting/02_atomic-tasklist-graph-editing-and-reporting-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-graph-editing-and-reporting/02_atomic-tasklist-graph-editing-and-reporting-2026-03-07.md)
  - [2026-03-07-ingest-digestion-and-long-cycle-automation/01_ingest-digestion-and-long-cycle-automation-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-ingest-digestion-and-long-cycle-automation/01_ingest-digestion-and-long-cycle-automation-plan-2026-03-07.md)
  - [2026-03-07-ingest-digestion-and-long-cycle-automation/02_atomic-tasklist-ingest-digestion-and-long-cycle-automation-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-ingest-digestion-and-long-cycle-automation/02_atomic-tasklist-ingest-digestion-and-long-cycle-automation-2026-03-07.md)
  - [2026-03-07-crawler-source-expansion/01_crawler-source-expansion-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-crawler-source-expansion/01_crawler-source-expansion-plan-2026-03-07.md)
  - [2026-03-07-crawler-source-expansion/02_atomic-tasklist-crawler-source-expansion-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-crawler-source-expansion/02_atomic-tasklist-crawler-source-expansion-2026-03-07.md)
  - [2026-03-07-frontend-i18n-theme-modularization/01_frontend-i18n-theme-modularization-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-frontend-i18n-theme-modularization/01_frontend-i18n-theme-modularization-plan-2026-03-07.md)
  - [2026-03-07-frontend-i18n-theme-modularization/02_atomic-tasklist-frontend-i18n-theme-modularization-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-frontend-i18n-theme-modularization/02_atomic-tasklist-frontend-i18n-theme-modularization-2026-03-07.md)
  - [2026-03-07-llm-service-and-agent-platformization/01_llm-service-and-agent-platformization-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-llm-service-and-agent-platformization/01_llm-service-and-agent-platformization-plan-2026-03-07.md)
  - [2026-03-07-llm-service-and-agent-platformization/02_atomic-tasklist-llm-service-and-agent-platformization-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-llm-service-and-agent-platformization/02_atomic-tasklist-llm-service-and-agent-platformization-2026-03-07.md)
  - [2026-03-07-dual-frontend-workbench-topology/01_dual-frontend-workbench-topology-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-dual-frontend-workbench-topology/01_dual-frontend-workbench-topology-plan-2026-03-07.md)
  - [2026-03-07-dual-frontend-workbench-topology/02_atomic-tasklist-dual-frontend-workbench-topology-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-dual-frontend-workbench-topology/02_atomic-tasklist-dual-frontend-workbench-topology-2026-03-07.md)
  - [2026-03-07-后续安排/01_abstract-planning-folderization-plan-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-后续安排/01_abstract-planning-folderization-plan-2026-03-07.md)
  - [2026-03-07-后续安排/02_atomic-tasklist-abstract-planning-folderization-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-后续安排/02_atomic-tasklist-abstract-planning-folderization-2026-03-07.md)
  - [2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md](./development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md)
  - [2026-03-07-builtin-writing-workbench-design/01_builtin-writing-workbench-design-2026-03-07.md](./development-plans/ARCHIVE_RETIRED/2026-03-07-builtin-writing-workbench-design/01_builtin-writing-workbench-design-2026-03-07.md)
  - [2026-03-07-builtin-writing-workbench-design/02_atomic-tasklist-builtin-writing-workbench-design-2026-03-07.md](./development-plans/ARCHIVE_RETIRED/2026-03-07-builtin-writing-workbench-design/02_atomic-tasklist-builtin-writing-workbench-design-2026-03-07.md)
  - [2026-03-08-llm-crawler-unified-frontdoor/01_llm-crawler-unified-frontdoor-architecture-2026-03-08.md](./development-plans/CURRENT_DEV/2026-03-08-llm-crawler-unified-frontdoor/01_llm-crawler-unified-frontdoor-architecture-2026-03-08.md)
  - [2026-03-08-llm-crawler-unified-frontdoor/02_atomic-tasklist-llm-crawler-unified-frontdoor-2026-03-08.md](./development-plans/CURRENT_DEV/2026-03-08-llm-crawler-unified-frontdoor/02_atomic-tasklist-llm-crawler-unified-frontdoor-2026-03-08.md)
  - [2026-03-08-llm-crawler-unified-frontdoor/03_a10-closure-and-validation-2026-03-08.md](./development-plans/CURRENT_DEV/2026-03-08-llm-crawler-unified-frontdoor/03_a10-closure-and-validation-2026-03-08.md)
- `development-plans/ARCHIVE_CLOSED`：
  - [2026-03-06-handler-cluster-frontdoor-middle-layer-alignment/03_handler-cluster-frontdoor-middle-layer-alignment-closing-2026-03-06.md](./development-plans/ARCHIVE_CLOSED/2026-03-06-handler-cluster-frontdoor-middle-layer-alignment/03_handler-cluster-frontdoor-middle-layer-alignment-closing-2026-03-06.md)
  - [2026-03-05-time-statistics-remediation-plan/01_time-statistics-remediation-plan-2026-03-05.md](./development-plans/CURRENT_DEV/2026-03-05-time-statistics-remediation-plan/01_time-statistics-remediation-plan-2026-03-05.md)
  - [2026-03-05-oss-node-platform-io-plan/01_oss-code-harvest-and-io-taskplan-2026-03-05.md](./development-plans/CURRENT_DEV/2026-03-05-oss-node-platform-io-plan/01_oss-code-harvest-and-io-taskplan-2026-03-05.md)
- `ops-frontend/F_PLAN`：
  - [frontend-modern-api-graph-atomic-execution-2026-03-05.md](./ops-frontend/F_PLAN/frontend-modern-api-graph-atomic-execution-2026-03-05.md)

更多历史新增请进入对应子目录 `INDEX.md`。

## 2026-03-14 迁移补充（最新口径主入口）

- `development-plans/CURRENT_DEV` 时间语义与密度合并计划最新口径主入口：
  - [2026-03-14-time-semantics-density-merged-plan/README.md](./development-plans/CURRENT_DEV/2026-03-14-time-semantics-density-merged-plan/README.md)
  - [2026-03-14-time-semantics-density-merged-plan/CHANGELOG_2026-03-14.md](./development-plans/CURRENT_DEV/2026-03-14-time-semantics-density-merged-plan/CHANGELOG_2026-03-14.md)
- 旧目录兼容迁移说明：
  - [2026-03-12-time-semantics-density-merged-plan/README.md](./development-plans/ARCHIVE_RETIRED/2026-03-12-time-semantics-density-merged-plan/README.md)
- 2026-03-14 最新收敛：
  - `single_url` 历史实现已被 `url_routing/source_library -> postprocess_frontdoor` 替代。
  - 当前代码主链不再保留 `single_url.py`、`task_ingest_single_url`、`single_url_*` 参数兼容层。
