# CURRENT_DEV Status Audit

更新时间：2026-04-07（PST）；2026-05-22 补充 `2026-03-24-frontend-visual-layering` 退场覆盖。

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
| `2026-03-01-open-source-platform-integration` | `partial` | `doc_aligned` | 有大量落地，但验收记录仍存在 skip / 未完成项 |
| `2026-05-14-global-vectorization-general-foundation` | `partial` | `doc_aligned` | 2026-05-14 已做实效性更新，仍未形成全局底座 |
| `2026-03-02-graph-3d-force-engine-parallel-migration` | `partial` | `doc_drift` | 双引擎和懒加载成立，但 chunk / 类型文件陈述漂移 |
| `2026-03-02-graph-node-standardization-a-then-b-plan` | `no_closure_claim` | `doc_drift` | 方案文档为主，且目标模型与当前表结构不完全一致 |
| `2026-03-02-ingest-platformization-assessment` | `partial` | `doc_aligned` | 平台化主链已落地，但仍不是生产级闭环 |
| `2026-03-02-meaningful-ingest-guardrails-plan` | `partial` | `doc_drift` | 门禁与指标已落地，但开关与响应细节未完全对齐 |
| `2026-03-02-single-url-first-ingest-allocation-plan` | `partial` | `doc_drift` | 后端三态基础存在，但前端消费和部分路径说明未闭环 |
| `2026-03-02-source-time-window-smart-timestamp-plan` | `partial` | `doc_aligned` | 关键词记忆和密度统计存在，时间语义主链未闭环 |
| `2026-03-04-r41-openclaw-autodispatch` | `partial` | `external_gap` | 文档自洽，但执行态工件不在当前仓库 |
| `2026-03-05-oss-node-platform-io-plan` | `partial` | `doc_aligned` | runtime / replay 主线已存在，但整套平台目标未闭环 |
| `2026-03-05-time-statistics-remediation-plan` | `partial` | `doc_stale` | 核心接口和 realcase 结果已落地，文档任务状态滞后 |
| `2026-03-07-crawler-source-expansion` | `not_closed` | `doc_aligned` | 仍是规划和待办链条 |
| `2026-04-07-parallel-agent-wave-orchestration` | `not_closed` | `doc_aligned` | 当前作为仓库级并行执行主入口，主文档、契约模板与 Wave 0 任务池均可直接复用 |
| `2026-03-07-docs-root-restructuring` | `not_closed` | `doc_aligned` | 旧根路径仍是当前权威入口 |
| `2026-03-07-dual-frontend-workbench-topology` | `not_closed` | `doc_stale` | 代码已有部分双交互面能力，文档仍停在规划态 |
| `2026-03-07-frontend-i18n-theme-modularization` | `not_closed` | `doc_stale` | i18n/theme/registry 已落地，任务文档仍全 pending |
| `2026-03-07-graph-editing-and-reporting` | `not_closed` | `doc_aligned` | 前端草稿能力存在，但后端编辑契约未闭环 |
| `2026-03-07-ingest-digestion-and-long-cycle-automation` | `no_closure_claim` | `doc_aligned` | 规划文档，无收口声明 |
| `2026-03-07-llm-service-and-agent-platformization` | `not_closed` | `doc_stale` | 平台化模块已不少，但文档仍全部 pending |
| `2026-03-07-typed-knowledge-organization` | `not_closed` | `doc_aligned` | 组织层对象模型未在代码中闭环 |
| `2026-03-07-writing-workbench-evolution` | `not_closed` | `doc_stale` | 现有写作工作台已可用，演进任务仍未闭环 |
| `2026-03-07-后续安排` | `not_closed` | `doc_aligned` | 仍是抽象规划拆分方案 |
| `2026-03-08-llm-crawler-unified-frontdoor` | `partial` | `doc_drift` | `AT-06/09/10` 有锚点，文档“全部实现”证据不够完整 |
| `2026-03-09-agent-symbolic-batch-search-architecture` | `partial` | `doc_aligned` | brief / critic / retry 机制已在代码里，但目录仍标明未封口 |
| `2026-03-11-source-library-three-lane-architecture` | `partial` | `doc_drift` | 三车道主线成立，但 legacy `410` 回退未见明确证据 |
| `2026-03-12-data-structured-service-modularization` | `partial` | `doc_aligned` | `document_views` 已起步，`document_queries` 未闭环 |
| `2026-03-14-consumer-side-modularization` | `partial` | `doc_aligned` | 消费层 facade / query 分层目标仍未完成 |
| `2026-03-14-search-chain-source-library-mounting-audit` | `partial` | `doc_aligned` | 主入口与挂载关系能对上代码，但治理动作未结束 |
| `2026-03-14-source-library-adapter-capability-remediation` | `partial` | `doc_drift` | parser / policy / routing 能力已有落地，目录仍在 in-review / pending |
| `2026-03-14-time-semantics-density-merged-plan` | `partial` | `doc_aligned` | 主入口有效，但 `target_overlap` 与 OPE 强门禁尚未闭环 |
| `2026-03-15-frontend-three-layer-rewrite` | `partial` | `doc_aligned` | 文档与代码都表明目前是“半重构态” |
| `2026-03-24-frontend-visual-layering` | `retired_in_place` | `doc_aligned` | 原空占位已补退场证据；现行入口转交 `2026-03-15-frontend-three-layer-rewrite` 与 Wave3/Wave4 frontend evidence |
| `2026-03-25-source-library-ingest-minimal-migration` | `partial` | `doc_aligned` | `AT-SLIM` / `AT-ITEM` 已收口，但 `AT-EXT-*` 仍 pending |
| `2026-04-02-claude-agent-high-fidelity-migration` | `no_closure_claim` | `doc_aligned` | 迁移映射文档，方向有代码支撑，但不是收口文档 |
| `MERGED_OVERVIEW` | `partial` | `doc_drift` | 合并总结有参考价值，但部分映射文件和能力边界已漂移 |

## 使用建议

- 需要做迁档决策时，优先使用本文件与 [`CURRENT_DEV/INDEX.md`](./INDEX.md)，不要直接凭目录名或单篇 closure 文档判断。
- 已迁入 [`ARCHIVE_RETIRED`](../ARCHIVE_RETIRED/INDEX.md) 的目录只保留历史价值，不应再作为现行代码事实或执行入口。
- 遇到 `doc_stale` 或 `stale_claim` 标签时，优先以当前代码和测试为准，再回补文档状态。
- `partial` 目录里若出现局部 closure 文档，不代表整目录可迁档；必须确认剩余 task / rollout / compatibility 也已关闭。
