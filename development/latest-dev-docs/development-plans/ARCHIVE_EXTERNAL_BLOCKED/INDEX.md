# ARCHIVE_EXTERNAL_BLOCKED - 外部条件阻塞开发计划

更新时间：2026-05-23（PST）

本目录用于存放已经完成仓内确定性门禁、但剩余验收依赖外部运行时、公网 replay、生产数据、真实租户环境或人工 review 的开发计划。它们不继续占用 `CURRENT_DEV` 的 `partial` 指标；重新进入当前开发前，必须先补齐对应外部条件或开新主题。

## 迁入标准

- 仓内代码、fixture、manifest、readback 或 checker 已能重复验证当前边界
- 剩余 blocker 不可在当前仓库内用确定性测试闭合
- 目录继续留在 `CURRENT_DEV` 会让 `partial` 数虚高，并误导后续 agent 继续补小 gate
- 迁入记录必须写明外部条件、仓内已封证据、恢复条件和验证命令

## 外部阻塞目录

- [2026-03-02 Source Time Window Smart Timestamp Plan](./2026-03-02-source-time-window-smart-timestamp-plan/)
  状态：`external_blocked` / `wave21_checked`。仓内 source-time window、decision-log provenance、sample/provenance readback 已可重复验证；剩余条件是 production data semantic chain 的 live validation、coverage distribution 和 decision-log feature readback。
- [2026-03-04 R41 OpenClaw Autodispatch](./2026-03-04-r41-openclaw-autodispatch/README.md)
  状态：`external_blocked` / `wave21_checked`。仓内 mirror/runtime/handoff checker 已通过；剩余条件是外部 OpenClaw runtime 的真实执行闭环。
- [2026-03-05 Time Statistics Remediation Plan](./2026-03-05-time-statistics-remediation-plan/)
  状态：`external_blocked` / `wave21_checked`。仓内 OPE freshness、decision-log freshness、current-state 和 sample/provenance readback 已封住；剩余条件是生产 freshness/volume/alignment 证据。
- [2026-03-11 Source Library Three-Lane Architecture](./2026-03-11-source-library-three-lane-architecture/)
  状态：`external_blocked` / `wave21_checked`。仓内 deterministic review batch 1-4、legacy 410 replacement、relevance queue 与 taxonomy readiness 已可重复验证；剩余条件是 live source collection、public replay 与 completed human review。
- [2026-03-14 Search Chain Source-Library Mounting Audit](./2026-03-14-search-chain-source-library-mounting-audit/)
  状态：`external_blocked` / `wave21_checked`。仓内 mount governance 与 deterministic review batch 已封住；剩余条件是 public replay、human review 和真实治理动作读回。
- [2026-03-14 Source-Library Adapter Capability Remediation](./2026-03-14-source-library-adapter-capability-remediation/)
  状态：`external_blocked` / `wave21_checked`。仓内 parser-profile、taxonomy/review readiness 与 deterministic review batch 已封住；剩余条件是 public replay 与人工 relevance review。
- [2026-03-14 Time Semantics Density Merged Plan](./2026-03-14-time-semantics-density-merged-plan/README.md)
  状态：`external_blocked` / `wave21_checked`。仓内 target-overlap、OPE contract、decision-log contract 与 sample/provenance readback 已封住；剩余条件是 production semantic evidence 与 release gate 接入。
- [2026-05-14 SearXNG / YaCy Isolated Deployment And Search Provider Integration Plan](./2026-05-14-local-open-search-provider-isolation/INDEX.md)
  状态：`external_blocked` / `wave22_checked`。仓内 explicit provider trace、runtime boundary、health artifact、schema/readback 与单测门禁已封住；剩余条件是 SearXNG / YaCy live availability、provider quality/freshness/latency、operator approval 与 `provider=auto` promotion。
- [2026-03-07 Crawler Source Expansion](./2026-03-07-crawler-source-expansion/2026-05-22-wave22-archive-external-blocked-decision.md)
  状态：`external_blocked` / `wave22_checked`。仓内 A1-A4/A6/A7 与 public replay deterministic gate 已封住；剩余条件是受控公网窗口产出 45-site replay 真实证据，尤其是缺失的 `output.public.json`。
- [2026-03-08 LLM Crawler Unified FrontDoor](./2026-03-08-llm-crawler-unified-frontdoor/10_wave23-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave23_checked`。仓内 frontdoor/router/manifest/fixture/shard gate 已封住；剩余条件是真实 high-JS public browser/crawler replay 与 five-shard public output。
- [2026-03-09 Agent Symbolic Batch Search Architecture](./2026-03-09-agent-symbolic-batch-search-architecture/22_wave23-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave23_checked`。仓内 deterministic search quality、provider-independent regression 与 quality promotion/readback 已封住；剩余条件是 SearXNG / YaCy / web live provider replay、operator review 与 `provider=auto` rollout policy。
- [2026-03-07 LLM Service And Agent Platformization](./2026-03-07-llm-service-and-agent-platformization/10_wave23-closure-decision-2026-05-23.md)
  状态：`external_blocked` / `wave23_checked`。仓内 AgentCore platform/provider-readiness/tool-calling/trace-redaction gates 已封住；剩余条件是真实 provider/API/account/network invocation evidence。
- [2026-03-07 Ingest Digestion And Long-Cycle Automation](./2026-03-07-ingest-digestion-and-long-cycle-automation/10_wave23-closure-decision-2026-05-23.md)
  状态：`external_blocked` / `wave23_checked`。仓内 long-cycle lifecycle、scheduler intent、JSONL durable readback、handoff trace 与 queue replay gate 已封住；剩余条件是 live scheduler enqueue、worker consumption、live DB write/readback 与 downstream handoff evidence。
- [2026-03-02 Graph Node Standardization A Then B Plan](./2026-03-02-graph-node-standardization-a-then-b-plan/09_wave23-closure-decision-2026-05-23.md)
  状态：`external_blocked` / `wave23_checked`。仓内 canonical-id/backfill readiness/live-DB rollout manifest/readback gates 已封住；剩余条件是 configured tenant schema、live backfill dry-run、nonempty tenant graph endpoint smoke 与 read-mode parity evidence。
- [2026-03-02 Graph 3D Force Engine Parallel Migration](./2026-03-02-graph-3d-force-engine-parallel-migration/08_wave24-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave24_checked`。仓内 Force3D frontend contract、runtime pixel/shape、visual-data smoke、rollback/readback gate 已封住；剩余条件是 live tenant DB GraphPage run、backend graph endpoint data、WebGL nonblank canvas 与 `window.__graph3dDebug` evidence。
- [MERGED_OVERVIEW Topic Drift Gate](./MERGED_OVERVIEW/04_wave24-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave24_checked`。仓内 RAG drift gate 已证明 retired RAG anchors 与 current local-index/vectorization anchors 的映射；剩余条件是 live/vector optional dependency readiness、production semantic quality 与 global vector contract closure。
- [2026-05-22 Clue Chain Successor Scopes](./2026-05-22-clue-chain-successor-scopes/03_wave26_graph_submit_conflict_and_ui_matrix_closure-2026-05-23.md)
  状态：`external_blocked` / `wave26_checked`。仓内 graph-submit conflict bridge/curated conflict/readback 与 GraphPage Clue Chain UI matrix 已封住；剩余条件是 SearXNG / YaCy / project search adapter live provider reliability。
- [2026-03-07 Graph Editing And Reporting](./2026-03-07-graph-editing-and-reporting/11_wave27-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave27_checked`。仓内 backend audit/readback、tenant-like fixture、conflict/rollback readback 与 GraphPage audit/rollback/handoff replay UI gate 已封住；剩余条件是 live tenant DB audit durability、persistent handoff replay readback 和 tenant/project scoping。
- [2026-03-07 Typed Knowledge Organization](./2026-03-07-typed-knowledge-organization/10_wave27-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave27_checked`。仓内 typed-knowledge JSONL durable readback、public API route contract、persisted-card request/response readback 与 overclaim guards 已封住；剩余条件是 live DB/API/UI、governance UI 与 migration/backfill evidence。
- [2026-03-07 Writing Workbench Evolution](./2026-03-07-writing-workbench-evolution/11_wave27-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave27_checked`。仓内 Writing Workbench typed-card request shape、keyword-card consumer readback、preview/detail readback 与 live-closure guards 已封住；剩余条件是 live persisted UI/API/DB readback、governance mutation 与 migration/backfill evidence。
- [2026-03-14 Consumer-Side Modularization](./2026-03-14-consumer-side-modularization/08_wave27-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave27_checked`。仓内 consumer facade/query、admin/dashboard、policy-state 与 prompt-time-density gates 已封住；剩余条件是 live DB/API smoke。
- [2026-03-25 Source-Library Ingest Minimal Migration](./2026-03-25-source-library-ingest-minimal-migration/18_wave27-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave27_checked`。仓内 `python_library` 与 `cli_or_container` bounded runner gates 已封住，AT-EXT checker `failures=[]`；剩余条件是 live article-extraction stack replay 与 live external-project replay。
- [2026-03-12 Data Structured Service Modularization](./2026-03-12-data-structured-service-modularization/14_wave28-structured-document-query-statement-builder-2026-05-23.md)
  状态：`external_blocked` / `wave28_checked`。仓内 generic DocumentQuery statement builder、structured SQL helper migration 与 focused closure gates 已封住；剩余条件是 live DB/API smoke。
- [2026-03-02 Ingest Platformization Assessment](./2026-03-02-ingest-platformization-assessment/09_wave29-ingest-platformization-repo-local-closure-2026-05-23.md)
  状态：`external_blocked` / `wave29_checked`。仓内 fetch-router decomposition、GateService/rule-source、default propagation、replay/SLO 与 frontend/ops entry gates 已封住；剩余条件是 configured-service demo canary、production 24h readback 与 ops promotion approval。
- [2026-03-02 Meaningful Ingest Guardrails Plan](./2026-03-02-meaningful-ingest-guardrails-plan/10_wave29-source-policy-tuning-attachment-decision-2026-05-23.md)
  状态：`external_blocked` / `wave29_checked`。仓内 source-policy tuning attachment 已归入 crawler source-policy matrix 责任面；剩余条件是 live canary feedback、production 24h guardrail metrics 与 operations strict-gate promotion decision。
- [2026-03-02 Single URL First Ingest Allocation Plan](./2026-03-02-single-url-first-ingest-allocation-plan/10_wave29-ingest-blocker-alignment-2026-05-23.md)
  状态：`external_blocked` / `wave29_checked`。仓内 broader fetch-router、official API adapter 与 dashboard tri-state blockers 已封住；剩余条件是 public browser/runtime replay、非 arXiv provider live API maturity、configured-service canary 与 production 24h readback。
- [2026-03-05 OSS Node Platform IO Plan](./2026-03-05-oss-node-platform-io-plan/08_wave29-oss-node-vector-manifest-replay-2026-05-23.md)
  状态：`external_blocked` / `wave29_checked`。仓内 node manifest/runtime replay 已覆盖 `keyword` / `vector` / `hybrid` provider manifest consumption；剩余条件是 live embedding provider verification、local open-search quality、semantic relevance 与 live scheduler/tenant DB/UI SLA。
- [2026-05-14 Global Vectorization General Foundation](./2026-05-14-global-vectorization-general-foundation/11_wave30-vector-closure-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave30_checked`。Wave30 已关闭 retrieval run JSONL persistence/readback、qdrant/pgvector payload provenance 统一、Agent matrix/main search schema join 三个 repo-local blocker；剩余条件是 live embedding provider、semantic embedding quality 与 production vector quality。
- [2026-03-01 Open Source Platform Integration](./2026-03-01-open-source-platform-integration/09_wave30-open-source-external-blocked-decision-2026-05-23.md)
  状态：`external_blocked` / `wave30_checked`。Wave29 已迁出 OSS-node slice，Wave30 已清零 global-vector repo-local blocker；本目录不再有独立仓内 blocker，剩余条件是 live provider、local open-search quality、semantic relevance 与外部 runtime/SLA evidence。

## 保留在 CURRENT_DEV 的相邻目录

- [2026-03-07 Docs Root Restructuring](../CURRENT_DEV/2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md)：`retained_partial`。剩余是 repo-local docs integration，不是外部条件。
- [2026-03-15 Frontend Three-Layer Rewrite](../CURRENT_DEV/2026-03-15-frontend-three-layer-rewrite/README.md)：`retained_partial`。剩余业务文案与兼容层迁移规模仍大。

## 返回

- [CURRENT_DEV](../CURRENT_DEV/INDEX.md) - 当前仍可作为现行入口的未封口开发计划
- [ARCHIVE_CLOSED](../ARCHIVE_CLOSED/INDEX.md) - 已收口开发计划
- [ARCHIVE_RETIRED](../ARCHIVE_RETIRED/INDEX.md) - 已退场 / 过时开发计划
