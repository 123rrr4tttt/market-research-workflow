# CURRENT_DEV Status Audit

更新时间：2026-04-07（PST）；2026-05-23 补充至 Wave28 状态证据、窄口径合同落地、主动开发收口、迁档与仍需保留的外部 / 生产化边界。

本审计基于对 `CURRENT_DEV` 一级目录的逐目录核对，判断标准同时参考：

- 文档是否明确宣称已收口
- 当前仓库代码、脚本、测试、工作流是否能直接支撑该宣称
- 文档表述与当前代码事实是否存在漂移

## 标签定义

- `clear_closed`：文档已给出明确收口结论，且当前仓库事实基本可支撑
- `partial`：存在明显落地或局部收口，但整目录仍未闭环
- `not_closed`：目录仍是未完成计划或明确未收口状态
- `no_closure_claim`：目录本身没有收口声明，或只是占位 / 映射 / 规划材料
- `retired_in_place`：原占位目录仅保留退场证据，现行入口已转交给其他专题或证据包
- `external_blocked`：仓内确定性门禁已有证据，但真实公网 / 运行时 / 环境依赖仍需外部条件
- `wave8_verified` / `wave8_checked`：Wave8 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题还保留更大范围或外部条件
- `wave9_verified` / `wave9_checked`：Wave9 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成窄口径合同、证据核查或 manifest 批次，仍保留生产化 / 迁移 / 外部 replay 范围
- `wave10_verified` / `wave10_checked`：Wave10 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成窄口径合同、治理门禁或 shim 批次，仍保留 live DB / public replay / 生产数据 / 前端真实数据验证范围
- `wave11_verified` / `wave11_checked`：Wave11 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成窄口径合同、deterministic replay、fake repository E2E、navigation promotion 或 no-dep frontend gate，仍保留 live provider / live scheduler / live external replay / 全量 UI 迁移边界
- `wave12_verified` / `wave12_checked`：Wave12 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成 readiness gate、review queue、decision log、content plan、persistence boundary 或 repo-local external-gap gate，仍保留 live provider / live DB / live canary / 人工 review / 全量 UI 迁移边界
- `wave13_verified` / `wave13_checked`：Wave13 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成 endpoint projection、consumer extraction、readiness/drift gate 或 repo-local external replay gate，仍保留 live provider / live scheduler / public replay / production quality / 更大迁移范围
- `wave14_verified` / `wave14_checked`：Wave14 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成 provider capability、visual/live DB readiness、canary metrics、taxonomy review、frontend migration boundary、content-gap cleanup 或 deterministic tool-calling quality gate，仍保留 live provider / live DB / live canary / 人工 review / 全量 UI 迁移边界
- `wave15_verified` / `wave15_checked`：Wave15 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成 runtime boundary、production readiness、manifest/schema、quality threshold、SQL helper、predicate facade、audit durability 或 live-boundary gate，仍保留 live provider / production data / live DB/API/UI / public replay / 更大迁移范围
- `wave16_verified` / `wave16_checked`：Wave16 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成 API route、typed fetch、audit UI controls、durable readback、content move、review batch、i18n slice 或 successor 拆分，仍保留 live provider / live DB/API/UI / production conflict / 更大迁移范围
- `wave17_verified` / `wave17_checked`：Wave17 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成 sample/readback、runtime pixel/shape、durable persistence、query boundary、i18n slice 或 content move 批次，仍保留 live provider / live DB/API/UI / production data / public replay / 全量迁移范围
- `wave18_verified` / `wave18_checked`：Wave18 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成 deterministic readback、health artifact、fixture replay、quality regression、scheduler handoff、audit readback、i18n slice 或 content move 批次，仍保留 live provider / live DB/API/UI / production data / public replay / human review / 全量迁移范围
- `wave19_verified` / `wave19_checked`：Wave19 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成 provider manifest、health schema、graph rollout、24h metrics artifact、public replay shards、provider redaction、deterministic review batch、i18n slice、content move 或 typed/writing boundary，仍保留 live provider / live DB/API/UI / production data / public replay / human review / 全量迁移范围
- `wave20_verified` / `wave20_checked`：Wave20 子代理分支已合并并通过聚焦门禁；若仍非 `clear_closed`，表示专题只完成 time semantics provenance、OpenClaw mirror manifest、graph audit conflict、scheduler queue、quality promotion、document-query endpoint、consumer facade、deterministic review batch、i18n slice 或 content move，仍保留 production data / external runtime / live tenant DB / live scheduler / live provider quality / live DB/API smoke / human review / 全量迁移范围
- `wave21_checked`：Wave21 封口优先波次已完成目录级判定；迁入 `ARCHIVE_EXTERNAL_BLOCKED` 的目录不再计入当前 `partial`，但仍不声明 full closure
- `wave22_checked`：Wave22 封口优先波次继续按目录级 repo-local blocker 判定；迁入 `ARCHIVE_EXTERNAL_BLOCKED` 的目录不再计入当前 `partial`，保留项必须说明内部 blocker
- `wave23_checked`：Wave23 改为封口优先波次，集中迁出只剩 live/provider/tenant/runtime evidence 的目录，以直接降低 `CURRENT_DEV` 的 `partial` 数
- `wave24_checked`：Wave24 继续按封口优先推进，只迁出 worker/reviewer 双证据均确认只剩外部 / live / runtime 条件的目录；带仓内 blocker 的目录保留在 `CURRENT_DEV`
- `wave25_verified`：Wave25 继续按封口优先推进，先用多代理复核避免误迁，再落地 docs-root 的 repo-local content move 批次；若仍为 `partial`，表示剩余 blocker 仍未清零
- `wave26_checked`：Wave26 继续按封口优先推进；Clue Chain successor repo-local graph-submit conflict 与 UI matrix gates 已落地，剩余 live provider reliability 作为外部条件迁出 `CURRENT_DEV`
- `wave27_checked`：Wave27 封口优先波次集中处理 graph/typed/writing/consumer/source-library 等接近封口目录；迁档目录只剩 live DB/API/UI、tenant DB durability、live external replay 或 migration/backfill 等外部条件，保留目录必须列明 repo-local blocker
- `wave28_checked`：Wave28 继续按目录级封口优先推进；无独立 repo-local blocker 且仅由后继三层重写继承的 frontend 目录迁入 `ARCHIVE_CLOSED` 或 `ARCHIVE_RETIRED`

时效标签：

- `doc_aligned`：文档状态与当前代码事实基本一致
- `doc_drift`：文档与代码有局部漂移，但主线仍可对齐
- `doc_stale`：代码明显已超前于文档状态
- `stale_claim`：文档的关键完成性陈述已被当前代码事实否定
- `external_gap`：文档依赖仓库外工件，仓内证据链不完整
- `placeholder`：目录为空或缺少可审计材料

## 已迁入 ARCHIVE_CLOSED

以下目录本轮已从 `CURRENT_DEV` 迁入 `ARCHIVE_CLOSED`：

- `clear_closed` [2026-03-02-ingest-chain-full-branch-map](../ARCHIVE_CLOSED/2026-03-02-ingest-chain-full-branch-map/)
- `clear_closed` [2026-04-06-repo-logic-gap-assessment](../ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment/)
- `clear_closed` [2026-03-07-后续安排](../ARCHIVE_CLOSED/2026-03-07-后续安排/07_wave15-final-closure-audit-2026-05-22.md)
- `clear_closed` [2026-04-07-parallel-agent-wave-orchestration](../ARCHIVE_CLOSED/2026-04-07-parallel-agent-wave-orchestration/07_wave16-runtime-boundary-closure-2026-05-22.md)
- `clear_closed` [2026-05-22-clue-chain-investigation-tool](../ARCHIVE_CLOSED/2026-05-22-clue-chain-investigation-tool/05_wave16_closure_split-2026-05-22.md)
- `clear_closed` [2026-03-07-frontend-i18n-theme-modularization](../ARCHIVE_CLOSED/2026-03-07-frontend-i18n-theme-modularization/12_wave28-closure-decision-2026-05-23.md)

## 已迁入 ARCHIVE_RETIRED

以下目录已从 `CURRENT_DEV` 退场。原因不是“已收口”，而是“继续放在当前入口会误导”：

| 目录 | 原状态 | 原时效标签 | 退场原因 | 替代入口 |
|---|---|---|---|---|
| `2026-03-03-platformization-first-vectorization-gm` | `partial` | `stale_claim` | 以 `single_url` 为唯一写入主链的前提已失效 | `2026-03-14-search-chain-source-library-mounting-audit` / `2026-03-14-source-library-adapter-capability-remediation` |
| `2026-03-04-rag-line-round3-filter-robustness` | `not_closed` | `stale_claim` | 引用的代码与测试路径已不在当前仓库 | 无直接替代；若重做需按当前 RAG 实现重立项 |
| `2026-03-07-builtin-writing-workbench-design` | `partial` | `stale_claim` | 文档前提“写作域未落地”已被当前代码事实否定 | `2026-03-07-writing-workbench-evolution` |
| `2026-03-12-time-semantics-density-merged-plan` | `partial` | `doc_stale` | 目录自身已声明应切换到 2026-03-14 主入口 | `2026-03-14-time-semantics-density-merged-plan` |
| `2026-03-24-frontend-visual-layering` | `retired_in_place` | `doc_aligned` | 原空占位已补退场证据，且可审计 scope 已转交新前端主线与 evidence 包；继续留在 `CURRENT_DEV` 会误导执行 | `2026-03-15-frontend-three-layer-rewrite` / `frontend-topology-theme/2026-05-22` / `frontend-runtime-visual/2026-05-22` |
| `2026-03-07-dual-frontend-workbench-topology` | `partial` | `doc_aligned / wave28_checked` | Wave27 disjoint gate 已证明 dual frontend 无独立 repo-local blocker；继续保留会重复三层重写的继承 blocker | `2026-03-15-frontend-three-layer-rewrite` |


## 已迁入 ARCHIVE_EXTERNAL_BLOCKED

以下目录本轮已从 `CURRENT_DEV` 迁入 `ARCHIVE_EXTERNAL_BLOCKED`。原因不是 full closure，而是仓内确定性门禁已封住，剩余条件明确依赖外部 runtime、公网 replay、生产数据或人工 review：

- `external_blocked` [2026-03-02-source-time-window-smart-timestamp-plan](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-source-time-window-smart-timestamp-plan/) - production data semantic chain 未跑 live validation
- `external_blocked` [2026-03-04-r41-openclaw-autodispatch](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-04-r41-openclaw-autodispatch/README.md) - 外部 OpenClaw runtime 未实测闭环
- `external_blocked` [2026-03-05-time-statistics-remediation-plan](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-05-time-statistics-remediation-plan/) - production freshness / volume / alignment 未验证
- `external_blocked` [2026-03-11-source-library-three-lane-architecture](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-11-source-library-three-lane-architecture/) - live source collection / public replay / completed human review 未闭环
- `external_blocked` [2026-03-14-search-chain-source-library-mounting-audit](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-search-chain-source-library-mounting-audit/) - public replay / human review / live governance readback 未闭环
- `external_blocked` [2026-03-14-source-library-adapter-capability-remediation](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-source-library-adapter-capability-remediation/) - public replay / human relevance review 未闭环
- `external_blocked` [2026-03-14-time-semantics-density-merged-plan](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-time-semantics-density-merged-plan/README.md) - production semantic evidence 与 release gate 未接入
- `external_blocked` [2026-05-14-local-open-search-provider-isolation](../ARCHIVE_EXTERNAL_BLOCKED/2026-05-14-local-open-search-provider-isolation/INDEX.md) - SearXNG / YaCy live availability、provider quality/freshness/latency 与 `provider=auto` promotion 未闭环
- `external_blocked` [2026-03-07-crawler-source-expansion](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-crawler-source-expansion/2026-05-22-wave22-archive-external-blocked-decision.md) - 45-site public replay 真实公网证据与 `output.public.json` 未闭环
- `external_blocked` [2026-03-08-llm-crawler-unified-frontdoor](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-08-llm-crawler-unified-frontdoor/10_wave23-external-blocked-decision-2026-05-23.md) - high-JS public browser/crawler replay 与 five-shard public output 未闭环
- `external_blocked` [2026-03-09-agent-symbolic-batch-search-architecture](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-09-agent-symbolic-batch-search-architecture/22_wave23-external-blocked-decision-2026-05-23.md) - live provider quality replay、operator review 与 provider-auto rollout policy 未闭环
- `external_blocked` [2026-03-07-llm-service-and-agent-platformization](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-llm-service-and-agent-platformization/10_wave23-closure-decision-2026-05-23.md) - 真实 provider/API/account/network invocation evidence 未闭环
- `external_blocked` [2026-03-07-ingest-digestion-and-long-cycle-automation](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-ingest-digestion-and-long-cycle-automation/10_wave23-closure-decision-2026-05-23.md) - live scheduler enqueue、worker consumption、live DB write/readback 与 downstream handoff 未闭环
- `external_blocked` [2026-03-02-graph-node-standardization-a-then-b-plan](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-graph-node-standardization-a-then-b-plan/09_wave23-closure-decision-2026-05-23.md) - tenant schema、live backfill dry-run、nonempty tenant graph endpoint smoke 与 read-mode parity evidence 未闭环
- `external_blocked` [2026-03-02-graph-3d-force-engine-parallel-migration](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-graph-3d-force-engine-parallel-migration/08_wave24-external-blocked-decision-2026-05-23.md) - live tenant DB GraphPage run、backend graph endpoint data、WebGL nonblank canvas 与 `window.__graph3dDebug` evidence 未闭环
- `external_blocked` [MERGED_OVERVIEW](../ARCHIVE_EXTERNAL_BLOCKED/MERGED_OVERVIEW/04_wave24-external-blocked-decision-2026-05-23.md) - live/vector optional dependency readiness、production semantic quality 与 global vector contract 未闭环
- `external_blocked` [2026-05-22-clue-chain-successor-scopes](../ARCHIVE_EXTERNAL_BLOCKED/2026-05-22-clue-chain-successor-scopes/03_wave26_graph_submit_conflict_and_ui_matrix_closure-2026-05-23.md) - Clue Chain graph-submit conflict 与 UI matrix repo-local gates 已闭；live provider reliability 未闭环
- `external_blocked` [2026-03-07-graph-editing-and-reporting](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-graph-editing-and-reporting/11_wave27-external-blocked-decision-2026-05-23.md) - graph editing audit/readback/UI deterministic gates 已闭；live tenant DB audit durability 未闭环
- `external_blocked` [2026-03-07-typed-knowledge-organization](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-typed-knowledge-organization/10_wave27-external-blocked-decision-2026-05-23.md) - typed-knowledge persistence/readback/API deterministic gates 已闭；live DB/API/UI、governance UI 与 migration/backfill 未闭环
- `external_blocked` [2026-03-07-writing-workbench-evolution](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-writing-workbench-evolution/11_wave27-external-blocked-decision-2026-05-23.md) - writing typed-card request/consumer/readback deterministic gates 已闭；live persisted UI/API/DB readback、governance mutation 与 migration/backfill 未闭环
- `external_blocked` [2026-03-14-consumer-side-modularization](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-consumer-side-modularization/08_wave27-external-blocked-decision-2026-05-23.md) - consumer facade/query deterministic gates 已闭；live DB/API smoke 未闭环
- `external_blocked` [2026-03-25-source-library-ingest-minimal-migration](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-25-source-library-ingest-minimal-migration/18_wave27-external-blocked-decision-2026-05-23.md) - source-library python/CLI/container runner deterministic gates 已闭；live article-extraction stack replay 与 live external-project replay 未闭环
- `external_blocked` [2026-03-12-data-structured-service-modularization](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-12-data-structured-service-modularization/14_wave28-structured-document-query-statement-builder-2026-05-23.md) - generic DocumentQuery statement builder 与 focused gates 已闭；live DB/API smoke 未闭环

## 结果矩阵

| 目录 | 状态 | 时效标签 | 说明 |
|---|---|---|---|
| `2026-03-01-open-source-platform-integration` | `partial` | `doc_aligned / wave8_checked / wave10_checked / wave12_checked / wave14_checked / wave18_checked / wave19_checked` | Wave8 已补 search/vector deterministic contract 复核，Wave10 已补 vectorization quality gate，Wave12 已补 provider readiness gate，Wave14 已补 provider capability gate，Wave18 已补 hybrid readback；平台化验收仍存在更大范围；Wave19 已补 provider manifest readback 并继续保留 live provider / platform closure 边界 |
| `2026-05-14-global-vectorization-general-foundation` | `partial` | `doc_aligned / wave8_checked / wave10_checked / wave12_checked / wave14_checked / wave18_checked / wave19_checked` | Wave8 已把 search provider trace、container replay summary、local_index runtime/benchmark 组成确定性门禁，Wave10 已补 keyword/vector/hybrid quality gate，Wave12 已补 provider readiness gate，Wave14 已补 provider capability gate，Wave18 已补 hybrid readback；真实 embedding 质量与全局 vector contract 未封口；Wave19 已补 provider manifest readback；真实 embedding 质量与 provider promotion 未封口 |
| `2026-03-02-ingest-platformization-assessment` | `partial` | `doc_aligned / wave8_verified / wave12_verified / wave14_checked / wave17_verified / wave19_verified` | Wave8 已补 fetch-router gap closure gate，Wave12 已补 single-url canary handoff contract，Wave14 已补 canary metrics readiness，Wave17 已补 deterministic canary metrics readback；生产级 live canary 和 24h metric readback 仍未完成；Wave19 已补 24h metrics artifact contract；live canary 24h readback 仍未完成 |
| `2026-03-02-meaningful-ingest-guardrails-plan` | `partial` | `doc_aligned / wave9_verified / wave11_verified / wave12_verified / wave14_checked / wave17_verified / wave19_verified` | Wave9 已补 request strict gate 与响应可见性合同；Wave11 已补 URL-execution canary rollout default 与 task-local metrics；Wave12 已补 canary handoff contract，Wave14 已补 canary metrics readiness，Wave17 已补 deterministic canary metrics readback；live demo_proj canary 和 24h 指标仍未封口；Wave19 已补 24h metrics artifact contract；live demo/prod canary 仍未封口 |
| `2026-03-02-single-url-first-ingest-allocation-plan` | `partial` | `doc_aligned / wave8_verified / wave12_verified / wave14_checked / wave17_verified / wave19_verified` | Wave8 已补 fetch-router/frontdoor context gap closure，Wave12 已补 single-url canary handoff contract，Wave14 已补 canary metrics readiness，Wave17 已补 deterministic readback；前端消费、live canary 和 24h metrics 仍未全闭环；Wave19 已补 24h metrics artifact contract；前端消费与 live metrics 仍未全闭环 |
| `2026-03-05-oss-node-platform-io-plan` | `partial` | `doc_aligned / wave8_checked / wave10_checked / wave12_checked / wave14_checked / wave18_checked / wave19_checked` | Wave8 search/vector deterministic gate 复核 runtime/replay 主线，Wave10 已补 vectorization quality gate，Wave12 已补 provider readiness gate，Wave14 已补 provider capability gate，Wave18 已补 hybrid readback；整套平台目标未闭环；Wave19 已补 provider manifest readback；整套平台 / live provider 目标仍未闭环 |
| `2026-03-07-docs-root-restructuring` | `partial` | `doc_aligned / wave9_checked / wave10_checked / wave11_checked / wave12_checked / wave16_verified / wave17_verified / wave18_verified / wave19_verified / wave20_verified / wave25_verified / retained_partial` | `docs/development` 与 `docs/architecture` target roots 已准备，Wave9 已补首批 machine-checkable manifest，Wave10 已补 content shim，Wave11 已补 `docs/development` local navigation promotion，Wave12 已补 content-plan gate，Wave16 已真实迁移一个 backend-core architecture content batch，Wave17 迁移一个 ops-frontend architecture batch并将 unsafe moves 降到 8，Wave18 迁移 root-plans architecture 批次并降到 7；权威内容移动仍未全执行；Wave19 已迁移 backend-docs architecture 批次并将 unsafe moves 降到 6；权威内容移动仍未全执行；Wave20 已迁移 development-plans architecture 批次并将 unsafe moves 降到 5；Wave25 已迁移 development-plans main 批次并将 unsafe moves 降到 4；权威内容移动仍未全执行 |
| `2026-03-07-dual-frontend-workbench-topology` | `retired` | `doc_aligned / wave8_verified / wave11_verified / wave12_checked / wave14_checked / wave16_verified / wave17_verified / wave18_verified / wave19_verified / wave20_verified / wave28_checked` | Wave27 i18n/page-shell disjoint gate、topology gate 与 business-string audit 已证明 dual frontend 无独立 repo-local blocker；剩余 page-shell/AppShell/全量文案与页面重构事项由 `2026-03-15-frontend-three-layer-rewrite` 继承，目录迁入 `ARCHIVE_RETIRED` |
| `2026-03-07-frontend-i18n-theme-modularization` | `clear_closed` | `doc_aligned / wave8_verified / wave11_verified / wave12_checked / wave14_checked / wave16_verified / wave17_verified / wave18_verified / wave19_verified / wave20_verified / wave28_checked` | Wave28 复核 `check:i18n-page-shell-disjoint` 与 `check:topology-platform`：一阶 i18n/theme/module platform 已闭合，剩余 business-string 与 page-shell retirement 已明确转交 `2026-03-15-frontend-three-layer-rewrite`，本目录迁入 `ARCHIVE_CLOSED` |
| `2026-03-07-后续安排` | `clear_closed` | `doc_aligned / wave13_checked / wave14_verified / wave15_verified` | Wave6 已补 folderization structure evidence，Wave13 已把该入口收窄为 retained coordination topic，Wave14 已把 downstream content gaps 降为 0，Wave15 `--strict-content` 复核 `hard_failures=0/content_gaps=0`；已迁入 `ARCHIVE_CLOSED` |
| `2026-03-12-data-structured-service-modularization` | `external_blocked` | `doc_aligned / wave9_verified / wave11_verified / wave13_verified / wave15_verified / wave17_verified / wave20_verified / wave27_checked / wave28_checked` | Wave9 已补 `document_queries.v1` query/envelope/view-consumer 合同，Wave11 已抽离 prompt-time-density SQL JSON query path，Wave13 已补 `/api/v1/search` document-query projection，Wave15 已补 SQL/helper migration inventory，Wave17 已补 policy-state query boundary，Wave20 已补 structured-data search document-query endpoint slice；Wave27 endpoint/query/consumer facade 组合 gate 已通过；Wave28 generic DocumentQuery statement builder 已落地并让 repo-local blocker 清零；目录迁入 `ARCHIVE_EXTERNAL_BLOCKED`，剩余条件为 live DB/API smoke |
| `2026-03-15-frontend-three-layer-rewrite` | `partial` | `doc_aligned / wave8_verified / wave11_verified / wave12_checked / wave14_checked / wave16_verified / wave17_verified / wave18_verified / wave19_verified / wave20_verified / retained_partial` | Wave8 已补 topology/i18n/theme contract checker，Wave11 已补 layer-shell coverage gate，Wave12 已补 business-string audit，Wave14 已补 static migration boundary，Wave16 已迁移 Agent Chat i18n slice，Wave17 已迁移 Projects page business strings，Wave18 已迁移 Catalog page business strings；文档与代码仍表明目前是“半重构态”；Wave19 已迁移 Dashboard page i18n slice；仍是半重构态；Wave20 已迁移 ProcessPage i18n slice；仍是半重构态 |
| `2026-04-02-claude-agent-high-fidelity-migration` | `clear_closed` | `doc_aligned` | 当前入口已拆分并迁入 `ARCHIVE_CLOSED`；如需新诊断应开 D48+ 新主题 |

## 使用建议

- 需要做迁档决策时，优先使用本文件与 [`CURRENT_DEV/INDEX.md`](./INDEX.md)，不要直接凭目录名或单篇 closure 文档判断。
- 已迁入 [`ARCHIVE_RETIRED`](../ARCHIVE_RETIRED/INDEX.md) 的目录只保留历史价值，不应再作为现行代码事实或执行入口。
- 遇到 `doc_stale` 或 `stale_claim` 标签时，优先以当前代码和测试为准，再回补文档状态。
- `partial` 目录里若出现局部 closure 文档，不代表整目录可迁档；必须确认剩余 task / rollout / compatibility 也已关闭。
