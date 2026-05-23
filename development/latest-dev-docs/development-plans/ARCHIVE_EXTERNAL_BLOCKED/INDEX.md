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

## 保留在 CURRENT_DEV 的相邻目录

- [2026-03-07 Docs Root Restructuring](../CURRENT_DEV/2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md)：`retained_partial`。剩余是 repo-local docs integration，不是外部条件。
- [2026-03-15 Frontend Three-Layer Rewrite](../CURRENT_DEV/2026-03-15-frontend-three-layer-rewrite/README.md)：`retained_partial`。剩余业务文案与兼容层迁移规模仍大。
- [2026-03-25 Source-Library Ingest Minimal Migration](../CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/01_source-library-ingest-minimal-migration-plan-2026-03-25.md)：`retained_partial`。仍有 `python_library_cli_container_runners_not_enabled` 仓内 runner 范围 blocker。
- [2026-05-14 Global Vectorization General Foundation](../CURRENT_DEV/2026-05-14-global-vectorization-general-foundation/01_global-vectorization-general-foundation-plan-2026-05-14.md)：`retained_partial`。统一 vector object、retrieval runs、provenance payload 与主检索/Agent schema 对齐仍是 repo-local blocker。
- [2026-03-02 Single URL First Ingest Allocation Plan](../CURRENT_DEV/2026-03-02-single-url-first-ingest-allocation-plan/01_single-url-first-ingest-allocation-plan-2026-03-02.md)：`retained_partial`。主文档仍保留 broader fetch-router、official API adapter 与 dashboard tri-state 对齐。
- [2026-05-22 Clue Chain Successor Scopes](../CURRENT_DEV/2026-05-22-clue-chain-successor-scopes/02_wave22_archive_external_blocked_decision-2026-05-22.md)：`retained_partial`。live provider 是外部条件，但 Clue Chain graph-submit conflict gate 与 UI/visual matrix 仍是仓内 blocker。

## 返回

- [CURRENT_DEV](../CURRENT_DEV/INDEX.md) - 当前仍可作为现行入口的未封口开发计划
- [ARCHIVE_CLOSED](../ARCHIVE_CLOSED/INDEX.md) - 已收口开发计划
- [ARCHIVE_RETIRED](../ARCHIVE_RETIRED/INDEX.md) - 已退场 / 过时开发计划
