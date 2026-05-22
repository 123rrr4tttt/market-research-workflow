# CURRENT_DEV Status Audit

更新时间：2026-04-07（PST）；2026-05-22 补充 Wave9 状态证据、窄口径合同落地与仍需保留的外部 / 生产化边界。

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
| `2026-03-01-open-source-platform-integration` | `partial` | `doc_aligned / wave8_checked` | Wave8 已补 search/vector deterministic contract 复核；平台化验收仍存在更大范围 |
| `2026-05-14-global-vectorization-general-foundation` | `partial` | `doc_aligned / wave8_checked` | Wave8 已把 search provider trace、container replay summary、local_index runtime/benchmark 组成确定性门禁；真实 embedding 质量与全局 vector contract 未封口 |
| `2026-05-14-local-open-search-provider-isolation` | `partial` | `doc_aligned / wave8_checked` | Wave6 已补 provider isolation / trace contract evidence，Wave8 复用真实容器 replay summary；当前容器可用性未复跑，仍保留生产化范围 |
| `2026-05-22-clue-chain-investigation-tool` | `partial` | `doc_aligned` | Wave5 已合并工具与实现证据，仍保留后续生产化和大范围验证 |
| `2026-03-02-graph-3d-force-engine-parallel-migration` | `partial` | `doc_drift / wave8_checked` | Wave8 已补 backend graph projection contract；frontend WebGL/engine-switch/real data visual smoke 仍缺 |
| `2026-03-02-graph-node-standardization-a-then-b-plan` | `partial` | `doc_drift / wave8_checked` | Wave7 已补 storage canonical id 规范化与单测；Wave8 已补 no-DB dry-run readmode/backfill contract，live DB rollout 仍缺 |
| `2026-03-02-ingest-platformization-assessment` | `partial` | `doc_aligned / wave8_verified` | Wave8 已补 fetch-router gap closure gate；生产级闭环仍未完成 |
| `2026-03-02-meaningful-ingest-guardrails-plan` | `partial` | `doc_aligned / wave9_verified` | Wave9 已补 request strict gate 与响应可见性合同；全局默认开关、canary 与生产化指标仍未封口 |
| `2026-03-02-single-url-first-ingest-allocation-plan` | `partial` | `doc_aligned / wave8_verified` | Wave8 已补 fetch-router/frontdoor context gap closure；前端消费和部分路径说明仍未全闭环 |
| `2026-03-02-source-time-window-smart-timestamp-plan` | `partial` | `doc_aligned / wave8_checked` | Wave8 已让 target-overlap gap 进入 prompt time-density priority；时间语义主链未闭环 |
| `2026-03-04-r41-openclaw-autodispatch` | `partial` | `external_gap` | 文档自洽，但执行态工件不在当前仓库 |
| `2026-03-05-oss-node-platform-io-plan` | `partial` | `doc_aligned / wave8_checked` | Wave8 search/vector deterministic gate 复核 runtime/replay 主线；整套平台目标未闭环 |
| `2026-03-05-time-statistics-remediation-plan` | `partial` | `doc_stale / wave8_checked` | Wave8 已补 target-overlap priority 代码与单测，旧任务状态仍滞后 |
| `2026-03-07-crawler-source-expansion` | `partial` | `doc_aligned / external_blocked / wave8_checked` | Wave8 已封 A7 validation pack；A1-A4/A6/A7 仓内可验证，A5 仍受 45-site public replay 外部阻塞 |
| `2026-04-07-parallel-agent-wave-orchestration` | `partial` | `doc_aligned / external_blocked` | repo 合同、fallback、任务模板和自检脚本可验证；子 worktree 记录的 runtime 仍未暴露 `spawn_agent` |
| `2026-03-07-docs-root-restructuring` | `partial` | `doc_aligned / wave9_checked` | `docs/development` 与 `docs/architecture` target roots 已准备，Wave9 已补首批 machine-checkable manifest；权威内容移动 / shim / shared navigation promotion 仍未执行 |
| `2026-03-07-dual-frontend-workbench-topology` | `partial` | `doc_aligned / wave8_verified` | Wave8 已补 topology contract checker 与 lint 证据，仍保留更大范围双交互面闭环 |
| `2026-03-07-frontend-i18n-theme-modularization` | `partial` | `doc_aligned / wave8_verified` | Wave8 已补 i18n/theme registry contract evidence，仍保留全量主题迁移范围 |
| `2026-03-07-graph-editing-and-reporting` | `partial` | `doc_aligned / wave8_verified` | Wave6 已补 reporting handoff bridge 与 curated API evidence，Wave8 已补 projection rollout contract；后端编辑闭环仍未全封 |
| `2026-03-07-ingest-digestion-and-long-cycle-automation` | `partial` | `doc_aligned / wave9_verified` | Wave7 已补 digestion / long-cycle pre-dispatch contract，Wave9 已补 persistent-task lifecycle contract；live scheduler / DB table write / end-to-end automation 仍未闭环 |
| `2026-03-07-llm-service-and-agent-platformization` | `partial` | `doc_aligned / wave6_verified / wave9_verified` | Wave6 已补 AgentCore schema inventory，Wave9 已补 tool-dispatch platform baseline；provider matrix 与外部 framework 评估仍需独立闭环 |
| `2026-03-07-typed-knowledge-organization` | `partial` | `doc_aligned / wave8_verified` | Wave8 已补 typed knowledge -> writing handoff contract，组织层对象模型仍未全闭环 |
| `2026-03-07-writing-workbench-evolution` | `partial` | `doc_stale / wave8_verified` | Wave8 已补 typed-knowledge keyword card consumer contract，演进任务仍未全闭环 |
| `2026-03-07-后续安排` | `partial` | `doc_aligned` | Wave6 已补 folderization structure evidence，抽象规划后续迁档仍未结束 |
| `2026-03-08-llm-crawler-unified-frontdoor` | `partial` | `doc_aligned / wave8_verified` | Wave8 已补 fetch-router/frontdoor context closure；高 JS/router 与三态消费仍未全封 |
| `2026-03-09-agent-symbolic-batch-search-architecture` | `partial` | `doc_aligned / wave9_verified` | Wave9 已补 `agent_batch` search brief / critic / bounded retry 确定性门禁；live provider quality 与 benchmark uplift 仍未封口 |
| `2026-03-11-source-library-three-lane-architecture` | `partial` | `doc_aligned / wave9_verified` | Wave9 已补 legacy item-run `410 Gone` replacement contract；live source collection 与三车道全量分类治理仍未封口 |
| `2026-03-12-data-structured-service-modularization` | `partial` | `doc_aligned / wave9_verified` | Wave9 已补 `document_queries.v1` query/envelope/view-consumer 合同；更多 API/search endpoint 与 DB statement builder 迁移仍未完成 |
| `2026-03-14-consumer-side-modularization` | `partial` | `doc_aligned / wave9_verified` | Wave9 已补 graph/writing consumer facade boundary guard；admin/dashboard/time-density JSON query 抽离仍未完成 |
| `2026-03-14-search-chain-source-library-mounting-audit` | `partial` | `doc_aligned` | 主入口与挂载关系能对上代码，但治理动作未结束 |
| `2026-03-14-source-library-adapter-capability-remediation` | `partial` | `doc_aligned / wave8_verified` | Wave8 已补 parser-profile capability gate；public replay 和人工 relevance review 仍未全封 |
| `2026-03-14-time-semantics-density-merged-plan` | `partial` | `doc_aligned / wave8_verified` | Wave8 已补 `target_overlap` priority 语义；OPE 强门禁与生产数据验证尚未闭环 |
| `2026-03-15-frontend-three-layer-rewrite` | `partial` | `doc_aligned / wave8_verified` | Wave8 已补 topology/i18n/theme contract checker；文档与代码仍表明目前是“半重构态” |
| `2026-03-24-frontend-visual-layering` | `retired_in_place` | `doc_aligned` | 原空占位已补退场证据；现行入口转交 `2026-03-15-frontend-three-layer-rewrite` 与 Wave3/Wave4 frontend evidence |
| `2026-03-25-source-library-ingest-minimal-migration` | `partial` | `doc_aligned / wave9_checked` | Wave9 已把 `AT-EXT-*` 拆成 current-state deterministic contract 与 known gaps；article extraction stack、python/CLI/container runners、live external replay 仍未封口 |
| `2026-04-02-claude-agent-high-fidelity-migration` | `clear_closed` | `doc_aligned` | 当前入口已拆分并迁入 `ARCHIVE_CLOSED`；如需新诊断应开 D48+ 新主题 |
| `MERGED_OVERVIEW` | `partial` | `doc_drift` | 合并总结有参考价值，但部分映射文件和能力边界已漂移 |

## 使用建议

- 需要做迁档决策时，优先使用本文件与 [`CURRENT_DEV/INDEX.md`](./INDEX.md)，不要直接凭目录名或单篇 closure 文档判断。
- 已迁入 [`ARCHIVE_RETIRED`](../ARCHIVE_RETIRED/INDEX.md) 的目录只保留历史价值，不应再作为现行代码事实或执行入口。
- 遇到 `doc_stale` 或 `stale_claim` 标签时，优先以当前代码和测试为准，再回补文档状态。
- `partial` 目录里若出现局部 closure 文档，不代表整目录可迁档；必须确认剩余 task / rollout / compatibility 也已关闭。
