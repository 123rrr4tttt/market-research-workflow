# CURRENT_DEV Status Audit

更新时间：2026-04-07（PST）；2026-05-22 补充 Wave16 状态证据、窄口径合同落地、主动开发收口、迁档与仍需保留的外部 / 生产化边界。

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

## 已迁入 ARCHIVE_RETIRED

以下目录已从 `CURRENT_DEV` 退场。原因不是“已收口”，而是“继续放在当前入口会误导”：

| 目录 | 原状态 | 原时效标签 | 退场原因 | 替代入口 |
|---|---|---|---|---|
| `2026-03-03-platformization-first-vectorization-gm` | `partial` | `stale_claim` | 以 `single_url` 为唯一写入主链的前提已失效 | `2026-03-14-search-chain-source-library-mounting-audit` / `2026-03-14-source-library-adapter-capability-remediation` |
| `2026-03-04-rag-line-round3-filter-robustness` | `not_closed` | `stale_claim` | 引用的代码与测试路径已不在当前仓库 | 无直接替代；若重做需按当前 RAG 实现重立项 |
| `2026-03-07-builtin-writing-workbench-design` | `partial` | `stale_claim` | 文档前提“写作域未落地”已被当前代码事实否定 | `2026-03-07-writing-workbench-evolution` |
| `2026-03-12-time-semantics-density-merged-plan` | `partial` | `doc_stale` | 目录自身已声明应切换到 2026-03-14 主入口 | `2026-03-14-time-semantics-density-merged-plan` |

## 结果矩阵

| 目录 | 状态 | 时效标签 | 说明 |
|---|---|---|---|
| `2026-03-01-open-source-platform-integration` | `partial` | `doc_aligned / wave8_checked / wave10_checked / wave12_checked / wave14_checked` | Wave8 已补 search/vector deterministic contract 复核，Wave10 已补 vectorization quality gate，Wave12 已补 provider readiness gate，Wave14 已补 provider capability gate；平台化验收仍存在更大范围 |
| `2026-05-14-global-vectorization-general-foundation` | `partial` | `doc_aligned / wave8_checked / wave10_checked / wave12_checked / wave14_checked` | Wave8 已把 search provider trace、container replay summary、local_index runtime/benchmark 组成确定性门禁，Wave10 已补 keyword/vector/hybrid quality gate，Wave12 已补 provider readiness gate，Wave14 已补 provider capability gate；真实 embedding 质量与全局 vector contract 未封口 |
| `2026-05-14-local-open-search-provider-isolation` | `partial` | `doc_aligned / external_blocked / wave8_checked / wave12_checked / wave15_checked` | Wave6 已补 provider isolation / trace contract evidence，Wave8 复用真实容器 replay summary，Wave12 记录当前 SearXNG/YaCy ConnectError，Wave15 补 runtime boundary gate；当前容器可用性仍未封口 |
| `2026-05-22-clue-chain-successor-scopes` | `partial` | `external_blocked / wave16_checked` | 原 Wave5 实现目录已迁入 `ARCHIVE_CLOSED`；当前只保留 live provider reliability、production graph-submit conflict handling、broader UI / visual regression 三个 successor 范围 |
| `2026-03-02-graph-3d-force-engine-parallel-migration` | `partial` | `doc_aligned / wave8_checked / wave10_verified / wave12_checked / wave14_checked` | Wave8 已补 backend graph projection contract；Wave10 已补 frontend force3d/engine-switch smoke，Wave12 已补 live-smoke readiness gate，Wave14 已补 backend-data visual smoke boundary；real live UI WebGL visual smoke 仍缺 |
| `2026-03-02-graph-node-standardization-a-then-b-plan` | `partial` | `doc_aligned / wave8_checked / wave10_verified / wave12_checked / wave14_checked` | Wave7 已补 storage canonical id 规范化与单测；Wave8 已补 no-DB dry-run readmode/backfill contract，Wave10 已补 pre-live DB rollout readiness，Wave12 已补 live-smoke readiness gate，Wave14 已补 live DB rollout gate；real tenant DB rollout 仍缺 |
| `2026-03-02-ingest-platformization-assessment` | `partial` | `doc_aligned / wave8_verified / wave12_verified / wave14_checked` | Wave8 已补 fetch-router gap closure gate，Wave12 已补 single-url canary handoff contract，Wave14 已补 canary metrics readiness；生产级 live canary 和 24h metric readback 仍未完成 |
| `2026-03-02-meaningful-ingest-guardrails-plan` | `partial` | `doc_aligned / wave9_verified / wave11_verified / wave12_verified / wave14_checked` | Wave9 已补 request strict gate 与响应可见性合同；Wave11 已补 URL-execution canary rollout default 与 task-local metrics；Wave12 已补 canary handoff contract，Wave14 已补 canary metrics readiness；live demo_proj canary 和 24h 指标仍未封口 |
| `2026-03-02-single-url-first-ingest-allocation-plan` | `partial` | `doc_aligned / wave8_verified / wave12_verified / wave14_checked` | Wave8 已补 fetch-router/frontdoor context gap closure，Wave12 已补 single-url canary handoff contract，Wave14 已补 canary metrics readiness；前端消费和 live canary 仍未全闭环 |
| `2026-03-02-source-time-window-smart-timestamp-plan` | `partial` | `doc_aligned / wave8_checked / wave10_verified / wave12_verified / wave15_checked` | Wave8 已让 target-overlap gap 进入 prompt time-density priority，Wave10 已补 source-time window deterministic contract，Wave12 已补 decision-log provenance gate，Wave15 补 production readiness gate；生产数据语义链未闭环 |
| `2026-03-04-r41-openclaw-autodispatch` | `partial` | `external_gap / wave12_checked / wave15_checked` | Wave12 已补 repo-local mirror gate，Wave15 已补 runtime handoff gate；外部 OpenClaw 当前运行态仍不在当前仓库证据链内 |
| `2026-03-05-oss-node-platform-io-plan` | `partial` | `doc_aligned / wave8_checked / wave10_checked / wave12_checked / wave14_checked` | Wave8 search/vector deterministic gate 复核 runtime/replay 主线，Wave10 已补 vectorization quality gate，Wave12 已补 provider readiness gate，Wave14 已补 provider capability gate；整套平台目标未闭环 |
| `2026-03-05-time-statistics-remediation-plan` | `partial` | `doc_aligned / wave8_checked / wave10_verified / wave12_verified / wave14_checked` | Wave8 已补 target-overlap priority 代码与单测，Wave10 已补 OPE freshness deterministic gate，Wave12 已补 decision-log freshness contract，Wave14 已补 current-state checker；旧任务状态仍需更大范围生产验证 |
| `2026-03-07-crawler-source-expansion` | `partial` | `doc_aligned / external_blocked / wave8_checked / wave13_checked` | Wave8 已封 A7 validation pack；Wave13 已补 public replay manifest/checker 并把缺少真实 `output.public.json` 标为 not closed；A5 仍受 45-site public replay 外部阻塞 |
| `2026-03-07-docs-root-restructuring` | `partial` | `doc_aligned / wave9_checked / wave10_checked / wave11_checked / wave12_checked / wave16_verified` | `docs/development` 与 `docs/architecture` target roots 已准备，Wave9 已补首批 machine-checkable manifest，Wave10 已补 content shim，Wave11 已补 `docs/development` local navigation promotion，Wave12 已补 content-plan gate，Wave16 已真实迁移一个 backend-core architecture content batch；权威内容移动仍未全执行 |
| `2026-03-07-dual-frontend-workbench-topology` | `partial` | `doc_aligned / wave8_verified / wave11_verified / wave12_checked / wave14_checked / wave16_verified` | Wave8 已补 topology contract checker 与 lint 证据，Wave11 已补 no-dep layer-shell route/surface contract，Wave12 已补 business-string audit，Wave14 已补 static migration boundary，Wave16 已迁移 Agent Chat i18n slice；仍保留更大范围双交互面闭环 |
| `2026-03-07-frontend-i18n-theme-modularization` | `partial` | `doc_aligned / wave8_verified / wave11_verified / wave12_checked / wave14_checked / wave16_verified` | Wave8 已补 i18n/theme registry contract evidence，Wave11 已把 theme/i18n anchor 纳入 layer-shell contract，Wave12 已补 business-string audit，Wave14 已补 static migration boundary，Wave16 已迁移 Agent Chat i18n slice；仍保留全量业务文案迁移范围 |
| `2026-03-07-graph-editing-and-reporting` | `partial` | `doc_aligned / wave8_verified / wave11_verified / wave12_checked / wave15_checked / wave16_verified` | Wave6 已补 reporting handoff bridge 与 curated API evidence，Wave8 已补 projection rollout contract，Wave11 已补 service-layer audit/rollback governance，Wave12 已补 live-smoke readiness gate，Wave15 已补 repo-local audit durability/readback gate，Wave16 已补 GraphPage audit readback / rollback controls；live tenant DB audit durability 仍未全封 |
| `2026-03-07-ingest-digestion-and-long-cycle-automation` | `partial` | `doc_aligned / wave9_verified / wave11_verified / wave13_checked / wave16_verified` | Wave7 已补 digestion / long-cycle pre-dispatch contract，Wave9 已补 persistent-task lifecycle contract，Wave11 已补 fake repository scheduler E2E contract，Wave13 已补 scheduler readiness/dry-run boundary，Wave16 已补 durable JSONL repository readback / event contract；live scheduler / live DB write / end-to-end automation 仍未闭环 |
| `2026-03-07-llm-service-and-agent-platformization` | `partial` | `doc_aligned / wave6_verified / wave9_verified / wave11_verified / wave13_checked / wave14_checked` | Wave6 已补 AgentCore schema inventory，Wave9 已补 tool-dispatch platform baseline，Wave11 已补 provider matrix 与 external framework boundary，Wave13 已补 live-provider readiness contract，Wave14 已补 native tool-calling quality gate；provider live calls 仍需独立闭环 |
| `2026-03-07-typed-knowledge-organization` | `partial` | `doc_aligned / wave8_verified / wave10_verified / wave12_verified / wave15_checked / wave16_verified` | Wave8 已补 typed knowledge -> writing handoff contract，Wave10 已补 writing context envelope，Wave12 已补 persistence/API boundary，Wave15 已补 live DB/API/UI boundary inventory，Wave16 已补 public API route contract；live DB/API/UI 仍未全闭环 |
| `2026-03-07-writing-workbench-evolution` | `partial` | `doc_aligned / wave8_verified / wave10_verified / wave12_verified / wave15_checked / wave16_verified` | Wave8 已补 typed-knowledge keyword card consumer contract，Wave10 已补 resource-card consumer boundary，Wave12 已补 typed-knowledge persistence boundary，Wave15 已补 live DB/API/UI boundary inventory，Wave16 已接入 typed-knowledge fetch/readback；persisted-card live UI readback 仍未全闭环 |
| `2026-03-07-后续安排` | `clear_closed` | `doc_aligned / wave13_checked / wave14_verified / wave15_verified` | Wave6 已补 folderization structure evidence，Wave13 已把该入口收窄为 retained coordination topic，Wave14 已把 downstream content gaps 降为 0，Wave15 `--strict-content` 复核 `hard_failures=0/content_gaps=0`；已迁入 `ARCHIVE_CLOSED` |
| `2026-03-08-llm-crawler-unified-frontdoor` | `partial` | `doc_aligned / wave8_verified / wave10_verified / wave13_checked / wave15_checked` | Wave8 已补 fetch-router/frontdoor context closure，Wave10 已补 tri-state router contract，Wave13 已补 high-JS/public replay readiness gate，Wave15 已补 replay manifest/schema gate；真实 high-JS browser fleet replay 仍未全封 |
| `2026-03-09-agent-symbolic-batch-search-architecture` | `partial` | `doc_aligned / wave9_verified / wave11_verified / wave13_checked / wave15_verified` | Wave9 已补 `agent_batch` search brief / critic / bounded retry 确定性门禁，Wave11 已补 fixture quality replay 与 benchmark uplift boundary，Wave13 已补 provider-quality readiness gate，Wave15 已补 live quality threshold contract；live provider quality 仍未封口 |
| `2026-03-11-source-library-three-lane-architecture` | `partial` | `doc_aligned / wave9_verified / wave12_verified / wave14_checked / wave16_checked` | Wave9 已补 legacy item-run `410 Gone` replacement contract，Wave12 已补 relevance review queue，Wave14 已补 taxonomy/review readiness，Wave16 已闭合一个 deterministic fixture review batch；live source collection、三车道全量分类治理和人工 review 仍未封口 |
| `2026-03-12-data-structured-service-modularization` | `partial` | `doc_aligned / wave9_verified / wave11_verified / wave13_verified / wave15_verified` | Wave9 已补 `document_queries.v1` query/envelope/view-consumer 合同，Wave11 已抽离 prompt-time-density query path，Wave13 已补 `/api/v1/search` document-query projection，Wave15 已补 SQL/helper migration inventory；更多 API/search endpoint 与 DB statement builder 迁移仍未完成 |
| `2026-03-14-consumer-side-modularization` | `partial` | `doc_aligned / wave9_verified / wave11_verified / wave13_verified / wave15_verified` | Wave9 已补 graph/writing consumer facade boundary guard，Wave11 已抽离 prompt-time-density JSON query path，Wave13 已补 bounded admin/dashboard document-view extraction，Wave15 已把选定 admin/dashboard SQL JSON predicates 收口到 `document_queries.consumer_predicates`；非 admin/dashboard 与 live DB/API smoke 仍未全封 |
| `2026-03-14-search-chain-source-library-mounting-audit` | `partial` | `doc_aligned / wave10_checked / wave12_verified / wave14_checked / wave16_checked` | 主入口与挂载关系能对上代码，Wave10 已补 source-library search/mount governance checker，Wave12 已补 relevance review queue，Wave14 已补 taxonomy/review readiness，Wave16 已闭合 deterministic fixture review batch；治理动作仍未结束 |
| `2026-03-14-source-library-adapter-capability-remediation` | `partial` | `doc_aligned / wave8_verified / wave10_checked / wave12_verified / wave14_checked / wave16_checked` | Wave8 已补 parser-profile capability gate，Wave10 已补 governance gate，Wave12 已补 relevance review queue，Wave14 已补 taxonomy/review readiness，Wave16 已闭合 deterministic fixture review batch；public replay 和人工 relevance review 仍未全封 |
| `2026-03-14-time-semantics-density-merged-plan` | `partial` | `doc_aligned / wave8_verified / wave10_verified / wave12_verified` | Wave8 已补 `target_overlap` priority 语义，Wave10 已补 OPE deterministic contract，Wave12 已补 decision-log contract；真实生产数据验证尚未闭环 |
| `2026-03-15-frontend-three-layer-rewrite` | `partial` | `doc_aligned / wave8_verified / wave11_verified / wave12_checked / wave14_checked / wave16_verified` | Wave8 已补 topology/i18n/theme contract checker，Wave11 已补 layer-shell coverage gate，Wave12 已补 business-string audit，Wave14 已补 static migration boundary，Wave16 已迁移 Agent Chat i18n slice；文档与代码仍表明目前是“半重构态” |
| `2026-03-24-frontend-visual-layering` | `retired_in_place` | `doc_aligned` | 原空占位已补退场证据；现行入口转交 `2026-03-15-frontend-three-layer-rewrite` 与 Wave3/Wave4 frontend evidence |
| `2026-03-25-source-library-ingest-minimal-migration` | `partial` | `doc_aligned / wave9_checked / wave11_verified / wave12_verified / wave16_checked` | Wave9 已把 `AT-EXT-*` 拆成 current-state deterministic contract 与 known gaps，Wave11 已补 article extraction runner / frontdoor document-candidate contract，Wave12 已补 relevance review queue，Wave16 已闭合 deterministic fixture review batch；python/CLI/container runners 与 live external replay 仍未封口 |
| `2026-04-02-claude-agent-high-fidelity-migration` | `clear_closed` | `doc_aligned` | 当前入口已拆分并迁入 `ARCHIVE_CLOSED`；如需新诊断应开 D48+ 新主题 |
| `MERGED_OVERVIEW` | `partial` | `doc_drift / wave13_checked` | 合并总结有参考价值，Wave13 已补 topic-local RAG drift gate；global vector contract、production semantic quality 与 live optional dependency readiness 仍未闭环 |

## 使用建议

- 需要做迁档决策时，优先使用本文件与 [`CURRENT_DEV/INDEX.md`](./INDEX.md)，不要直接凭目录名或单篇 closure 文档判断。
- 已迁入 [`ARCHIVE_RETIRED`](../ARCHIVE_RETIRED/INDEX.md) 的目录只保留历史价值，不应再作为现行代码事实或执行入口。
- 遇到 `doc_stale` 或 `stale_claim` 标签时，优先以当前代码和测试为准，再回补文档状态。
- `partial` 目录里若出现局部 closure 文档，不代表整目录可迁档；必须确认剩余 task / rollout / compatibility 也已关闭。
