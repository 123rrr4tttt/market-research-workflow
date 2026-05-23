# ARCHIVE_EXTERNAL_BLOCKED - 外部条件阻塞开发计划

更新时间：2026-05-23（PST）

本目录用于存放已经完成仓内确定性门禁、但剩余验收依赖外部运行时、公网 replay、生产数据、真实租户环境或人工 review 的开发计划。它们不继续占用 `CURRENT_DEV` 的 `partial` 指标；重新进入当前开发前，必须先补齐对应外部条件或开新主题。

## 导航基线

- Target topic allowlist: [../TARGET_TOPIC_ALLOWLIST.json](../TARGET_TOPIC_ALLOWLIST.json)
- External blocker manifest: [../EXTERNAL_BLOCKER_MANIFEST.v1.json](../EXTERNAL_BLOCKER_MANIFEST.v1.json)
- Wave44 manual graph3d live UI closure: [../../automation-runs/wave44-manual-graph3d-live-ui-closure/2026-05-23/README.md](../../automation-runs/wave44-manual-graph3d-live-ui-closure/2026-05-23/README.md)
- Wave42 manual open search live closure: [../../automation-runs/wave42-manual-open-search-live-closure/2026-05-23/README.md](../../automation-runs/wave42-manual-open-search-live-closure/2026-05-23/README.md)
- Wave45 manual structured/consumer live API closure: [../../automation-runs/wave45-manual-structured-consumer-live-api-closure/2026-05-23/README.md](../../automation-runs/wave45-manual-structured-consumer-live-api-closure/2026-05-23/README.md)
- Wave46 manual graph editing live-audit closure: [../../automation-runs/wave46-manual-graph-editing-live-audit-closure/2026-05-23/README.md](../../automation-runs/wave46-manual-graph-editing-live-audit-closure/2026-05-23/README.md)
- Wave47 manual crawler public replay closure: [../../automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json](../../automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json)
- Wave48 manual R41 OpenClaw runtime closure: [../../automation-runs/wave48-manual-openclaw-runtime-closure/2026-05-23/README.md](../../automation-runs/wave48-manual-openclaw-runtime-closure/2026-05-23/README.md)
- Wave49 manual source-library adapter public replay closure: [../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-14-source-library-adapter-capability-remediation/20_wave49-manual-public-replay-closure-2026-05-23.md](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-14-source-library-adapter-capability-remediation/20_wave49-manual-public-replay-closure-2026-05-23.md)
- Wave50 non-target reclassification: [./2026-03-01-open-source-platform-integration/10_wave50-non-target-wrapper-reclassification-2026-05-23.md](./2026-03-01-open-source-platform-integration/10_wave50-non-target-wrapper-reclassification-2026-05-23.md), [./MERGED_OVERVIEW/05_wave50-non-target-drift-evidence-reclassification-2026-05-23.md](./MERGED_OVERVIEW/05_wave50-non-target-drift-evidence-reclassification-2026-05-23.md), [./2026-03-14-search-chain-source-library-mounting-audit/10_wave50-non-target-mounting-audit-reclassification-2026-05-23.md](./2026-03-14-search-chain-source-library-mounting-audit/10_wave50-non-target-mounting-audit-reclassification-2026-05-23.md)
- Wave51 non-target reclassification: [./2026-03-02-ingest-platformization-assessment/10_wave51-non-target-assessment-wrapper-reclassification-2026-05-23.md](./2026-03-02-ingest-platformization-assessment/10_wave51-non-target-assessment-wrapper-reclassification-2026-05-23.md)
- Wave41 external unblock attempt: [../../automation-runs/wave41-external-unblock-attempt/2026-05-23/README.md](../../automation-runs/wave41-external-unblock-attempt/2026-05-23/README.md)
- Wave40 manifest evidence: [../../automation-runs/wave40-external-blocker-manifest/2026-05-23/README.md](../../automation-runs/wave40-external-blocker-manifest/2026-05-23/README.md)
- Wave37 four-state review: [../../automation-runs/wave37-target-review-status/2026-05-23/README.md](../../automation-runs/wave37-target-review-status/2026-05-23/README.md)
- Wave36 target evidence profile: [../../automation-runs/wave36-target-topic-evidence-profile/2026-05-23/README.md](../../automation-runs/wave36-target-topic-evidence-profile/2026-05-23/README.md)

## 迁入标准

- 仓内代码、fixture、manifest、readback 或 checker 已能重复验证当前边界
- 剩余 blocker 不可在当前仓库内用确定性测试闭合
- 目录继续留在 `CURRENT_DEV` 会让 `partial` 数虚高，并误导后续 agent 继续补小 gate
- 迁入记录必须写明外部条件、仓内已封证据、恢复条件和验证命令
- Wave40 之后，每个 `external_blocked` review target 还必须在 [EXTERNAL_BLOCKER_MANIFEST.v1.json](../EXTERNAL_BLOCKER_MANIFEST.v1.json) 中登记 `dependency_type`、`repo_local_evidence`、`probe_or_manual_evidence`、`exit_criteria` 和 `owner_surface`，并通过 `scripts/checkers/check_external_blocker_manifest.py`。

## 外部阻塞目录

- [Wave33 External-Blocked Revalidation](./2026-05-23-wave33-external-blocked-revalidation.md)
  状态：`wave33_checked` / historical snapshot。集中复核 source-library、time semantics 与 OpenClaw R41 近封口目录；当时 R41 仍为 `external_blocked`。Wave48 已用真实 OpenClaw runtime 读回关闭 R41，当前剩余外部阻塞不再包含 R41。
- [2026-03-02 Source Time Window Smart Timestamp Plan](./2026-03-02-source-time-window-smart-timestamp-plan/)
  状态：`external_blocked` / `wave21_checked` / `wave33_checked`。仓内 source-time window、decision-log provenance、sample/provenance readback 已可重复验证；Wave33 将证据路径修正为 archive-first/current-dev fallback；剩余条件是 production data semantic chain 的 live validation、coverage distribution 和 decision-log feature readback。
- [2026-03-05 Time Statistics Remediation Plan](./2026-03-05-time-statistics-remediation-plan/)
  状态：`external_blocked` / `wave21_checked` / `wave33_checked`。仓内 OPE freshness、decision-log freshness、current-state 和 sample/provenance readback 已封住；Wave33 将 current-state evidence 改为 archive-first/current-dev fallback；剩余条件是生产 freshness/volume/alignment 证据。
- [2026-03-11 Source Library Three-Lane Architecture](./2026-03-11-source-library-three-lane-architecture/)
  状态：`external_blocked` / `wave21_checked` / `wave33_checked`。仓内 deterministic review batch 1-4、legacy 410 replacement、relevance queue 与 taxonomy readiness 已可重复验证；Wave33 冻结旧 `external_blocked_candidate`/`retained_partial` 文案为历史快照；Wave49 已补齐 shared 45-site public replay；剩余条件是 live source collection、provider article extraction 与 completed human review。
- [2026-03-14 Time Semantics Density Merged Plan](./2026-03-14-time-semantics-density-merged-plan/README.md)
  状态：`external_blocked` / `wave21_checked` / `wave33_checked`。仓内 target-overlap、OPE contract、decision-log contract 与 sample/provenance readback 已封住；Wave33 将证据路径修正为 archive-first/current-dev fallback；剩余条件是 production semantic evidence 与 release gate 接入。
- [2026-03-08 LLM Crawler Unified FrontDoor](./2026-03-08-llm-crawler-unified-frontdoor/INDEX.md)
  状态：`external_blocked` / `wave23_checked`。仓内 frontdoor/router/manifest/fixture/shard gate 已封住；剩余条件是真实 high-JS public browser/crawler replay 与 five-shard public output。
- [2026-03-09 Agent Symbolic Batch Search Architecture](./2026-03-09-agent-symbolic-batch-search-architecture/22_wave23-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave23_checked`。仓内 deterministic search quality、provider-independent regression 与 quality promotion/readback 已封住；剩余条件是 SearXNG / YaCy / web live provider replay、operator review 与 `provider=auto` rollout policy。
- [2026-03-07 LLM Service And Agent Platformization](./2026-03-07-llm-service-and-agent-platformization/10_wave23-closure-decision-2026-05-23.md)
  状态：`external_blocked` / `wave23_checked`。仓内 AgentCore platform/provider-readiness/tool-calling/trace-redaction gates 已封住；剩余条件是真实 provider/API/account/network invocation evidence。
- [2026-03-07 Ingest Digestion And Long-Cycle Automation](./2026-03-07-ingest-digestion-and-long-cycle-automation/10_wave23-closure-decision-2026-05-23.md)
  状态：`external_blocked` / `wave23_checked`。仓内 long-cycle lifecycle、scheduler intent、JSONL durable readback、handoff trace 与 queue replay gate 已封住；剩余条件是 live scheduler enqueue、worker consumption、live DB write/readback 与 downstream handoff evidence。
- [2026-03-07 Typed Knowledge Organization](./2026-03-07-typed-knowledge-organization/INDEX.md)
  状态：`external_blocked` / `wave27_checked`。仓内 typed-knowledge JSONL durable readback、public API route contract、persisted-card request/response readback 与 overclaim guards 已封住；剩余条件是 live DB/API/UI、governance UI 与 migration/backfill evidence。
- [2026-03-07 Writing Workbench Evolution](./2026-03-07-writing-workbench-evolution/INDEX.md)
  状态：`external_blocked` / `wave27_checked`。仓内 Writing Workbench typed-card request shape、keyword-card consumer readback、preview/detail readback 与 live-closure guards 已封住；剩余条件是 live persisted UI/API/DB readback、governance mutation 与 migration/backfill evidence。
- [2026-03-25 Source-Library Ingest Minimal Migration](./2026-03-25-source-library-ingest-minimal-migration/18_wave27-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave27_checked` / `wave33_checked`。仓内 `python_library` 与 `cli_or_container` bounded runner gates 已封住，AT-EXT checker `failures=[]`；Wave33 标注旧 Wave9/Wave21 runner blocker 文案为历史快照；剩余条件是 live article-extraction stack replay 与 live external-project replay。
- [2026-03-02 Meaningful Ingest Guardrails Plan](./2026-03-02-meaningful-ingest-guardrails-plan/10_wave29-source-policy-tuning-attachment-decision-2026-05-23.md)
  状态：`external_blocked` / `wave29_checked`。仓内 source-policy tuning attachment 已归入 crawler source-policy matrix 责任面；剩余条件是 live canary feedback、production 24h guardrail metrics 与 operations strict-gate promotion decision。
- [2026-03-02 Single URL First Ingest Allocation Plan](./2026-03-02-single-url-first-ingest-allocation-plan/10_wave29-ingest-blocker-alignment-2026-05-23.md)
  状态：`external_blocked` / `wave29_checked`。仓内 broader fetch-router、official API adapter 与 dashboard tri-state blockers 已封住；剩余条件是 public browser/runtime replay、非 arXiv provider live API maturity、configured-service canary 与 production 24h readback。
- [2026-03-05 OSS Node Platform IO Plan](./2026-03-05-oss-node-platform-io-plan/INDEX.md)
  状态：`external_blocked` / `wave29_checked`。仓内 node manifest/runtime replay 已覆盖 `keyword` / `vector` / `hybrid` provider manifest consumption；剩余条件是 live embedding provider verification、local open-search quality、semantic relevance 与 live scheduler/tenant DB/UI SLA。
- [2026-05-14 Global Vectorization General Foundation](./2026-05-14-global-vectorization-general-foundation/INDEX.md)
  状态：`external_blocked` / `wave30_checked`。Wave30 已关闭 retrieval run JSONL persistence/readback、qdrant/pgvector payload provenance 统一、Agent matrix/main search schema join 三个 repo-local blocker；剩余条件是 live embedding provider、semantic embedding quality 与 production vector quality。
## 非目标证据 / 父级汇总

- [MERGED_OVERVIEW Topic Drift Gate](./MERGED_OVERVIEW/05_wave50-non-target-drift-evidence-reclassification-2026-05-23.md)
  状态：`non_target_topic_local_drift_evidence` / `wave50_reclassified`。仓内 RAG drift gate 是过程证据；vector optional dependency / semantic quality 条件由 [Global Vectorization General Foundation](./2026-05-14-global-vectorization-general-foundation/INDEX.md) 承接，不再重复计入 external target。
- [2026-03-01 Open Source Platform Integration](./2026-03-01-open-source-platform-integration/10_wave50-non-target-wrapper-reclassification-2026-05-23.md)
  状态：`non_target_superseded_parent_wrapper` / `wave50_reclassified`。Wave29 已迁出 OSS-node slice，Wave30 已清零 global-vector repo-local blocker；本父级目录不再有独立 target 身份，剩余条件由 [Global Vectorization General Foundation](./2026-05-14-global-vectorization-general-foundation/INDEX.md) 与 [OSS Node Platform IO Plan](./2026-03-05-oss-node-platform-io-plan/INDEX.md) 承接。
- [2026-03-02 Ingest Platformization Assessment](./2026-03-02-ingest-platformization-assessment/10_wave51-non-target-assessment-wrapper-reclassification-2026-05-23.md)
  状态：`non_target_ingest_platformization_assessment_wrapper` / `wave51_reclassified`。Wave29 已清零 fetch-router decomposition、GateService/rule-source、default propagation、replay/SLO 与 frontend/ops entry repo-local blockers；本 assessment wrapper 不再有独立 target 身份，live canary、production 24h readback 与 ops approval 由 [Meaningful Ingest Guardrails Plan](./2026-03-02-meaningful-ingest-guardrails-plan/10_wave29-source-policy-tuning-attachment-decision-2026-05-23.md) 和 [Single URL First Ingest Allocation Plan](./2026-03-02-single-url-first-ingest-allocation-plan/10_wave29-ingest-blocker-alignment-2026-05-23.md) 承接。
- [2026-03-14 Search Chain Source-Library Mounting Audit](./2026-03-14-search-chain-source-library-mounting-audit/10_wave50-non-target-mounting-audit-reclassification-2026-05-23.md)
  状态：`non_target_source_library_mounting_audit_evidence` / `wave50_reclassified`。仓内 mount governance 与 deterministic review batch 是 source-library 证据；human review、live source collection、live ingest migration 和真实治理动作读回由 [Source Library Three-Lane Architecture](./2026-03-11-source-library-three-lane-architecture/) 与 [Source-Library Ingest Minimal Migration](./2026-03-25-source-library-ingest-minimal-migration/18_wave27-external-blocked-decision-2026-05-23.md) 承接，不再重复计入 external target。

## 相邻目录状态

- [2026-05-14 Local Open Search Provider Isolation](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-05-14-local-open-search-provider-isolation/17_wave42-manual-open-search-live-closure-2026-05-23.md)：`clear_closed`。Wave42 手动启动 SearXNG / YaCy 并通过 backend `search_sources(provider=...)` 完成 2 provider x 3 query live replay；该目录不再计入 `ARCHIVE_EXTERNAL_BLOCKED`。
- [2026-05-22 Clue Chain Successor Scopes](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-05-22-clue-chain-successor-scopes/04_wave42-live-provider-reliability-closure-2026-05-23.md)：`clear_closed`。Wave42 使用同一 live provider 证据关闭 Clue Chain successor 的 live-provider reliability 条件；该目录不再计入 `ARCHIVE_EXTERNAL_BLOCKED`。
- [2026-03-02 Graph Node Standardization A Then B Plan](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-02-graph-node-standardization-a-then-b-plan/10_wave43-manual-live-db-closure-2026-05-23.md)：`clear_closed`。Wave43 修复 tenant graph projection constraints，并用 live DB dry-run、非空 graph endpoint smoke、projection write/readback 和 B-read parity 关闭 graph-node live DB 条件；该目录不再计入 `ARCHIVE_EXTERNAL_BLOCKED`。
- [2026-03-02 Graph 3D Force Engine Parallel Migration](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-02-graph-3d-force-engine-parallel-migration/09_wave44-manual-live-ui-closure-2026-05-23.md)：`clear_closed`。Wave44 修复 force3d dynamic component state 与 visible-node debug stats，并用 live backend GraphPage/WebGL 非空 canvas 证据关闭 Graph 3D live UI 条件；该目录不再计入 `ARCHIVE_EXTERNAL_BLOCKED`。
- [2026-03-12 Data Structured Service Modularization](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-12-data-structured-service-modularization/15_wave45-manual-live-api-closure-2026-05-23.md)：`clear_closed`。Wave45 手动验证 `/search` document-query projection、retrieval readback 与 `DocumentQuery -> SQLAlchemy statement` live DB execution，关闭 structured live DB/API 条件；该目录不再计入 `ARCHIVE_EXTERNAL_BLOCKED`。
- [2026-03-14 Consumer-Side Modularization](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-14-consumer-side-modularization/09_wave45-manual-live-api-closure-2026-05-23.md)：`clear_closed`。Wave45 手动验证 search/admin/dashboard/policy/prompt-time-density consumer live readback，关闭 consumer live DB/API 条件；该目录不再计入 `ARCHIVE_EXTERNAL_BLOCKED`。
- [2026-03-07 Graph Editing And Reporting](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-graph-editing-and-reporting/12_wave46-manual-live-audit-closure-2026-05-23.md)：`clear_closed`。Wave46 手动验证 curated submit/rollback audit live DB durability、persistent handoff replay readback 与 tenant/project scoping；该目录不再计入 `ARCHIVE_EXTERNAL_BLOCKED`。
- [2026-03-07 Crawler Source Expansion](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-crawler-source-expansion/10_wave47-manual-public-replay-closure-2026-05-23.md)：`clear_closed`。Wave47 执行真实 opt-in 45-site public replay，记录 40 个 public targets attempted、5 个 policy skips、0 个 operator-gate skips，并完成 A5 manual review；该目录不再计入 `ARCHIVE_EXTERNAL_BLOCKED`。
- [2026-03-04 R41 OpenClaw Autodispatch](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-04-r41-openclaw-autodispatch/22_wave48-manual-openclaw-runtime-closure-2026-05-23.md)：`clear_closed`。Wave48 手动启动真实 OpenClaw runtime gateway，读回 R41 `skipped/no_unfinished_line_task/ready_dispatch_count=0` 外部 run state，并确认无 active/stuck sessions；该目录不再计入 `ARCHIVE_EXTERNAL_BLOCKED`。
- [2026-03-14 Source-Library Adapter Capability Remediation](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-14-source-library-adapter-capability-remediation/20_wave49-manual-public-replay-closure-2026-05-23.md)：`clear_closed`。Wave49 使用真实 opt-in 45-site public replay 关闭 AT-AC-10，记录 40 个 public targets attempted、5 个 policy skips、0 个 operator-gate skips，并保留 term-fallback rows 作为 broader source-library relevance review 输入；该目录不再计入 `ARCHIVE_EXTERNAL_BLOCKED`。
- [2026-03-07 Docs Root Restructuring](../../../../docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/21_wave31-docs-root-shared-navigation-sync-2026-05-23.md)：`clear_closed`。Wave31 `check_docs_root_navigation_drift.py --require-clean` 已清零 navigation drift；该目录不再计入 `CURRENT_DEV` partial。
- [2026-03-15 Frontend Three-Layer Rewrite](../ARCHIVE_CLOSED/2026-03-15-frontend-three-layer-rewrite/16_wave32-frontend-i18n-final-closure-2026-05-23.md)：`clear_closed`。Wave32 已清零 frontend business-string repo-local blocker，并迁入 `ARCHIVE_CLOSED`。

## 返回

- [CURRENT_DEV](../CURRENT_DEV/INDEX.md) - 当前仍可作为现行入口的未封口开发计划
- [ARCHIVE_CLOSED](../ARCHIVE_CLOSED/INDEX.md) - 已收口开发计划
- [ARCHIVE_RETIRED](../ARCHIVE_RETIRED/INDEX.md) - 已退场 / 过时开发计划
