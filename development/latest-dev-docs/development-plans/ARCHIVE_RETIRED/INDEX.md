# ARCHIVE_RETIRED - 已退场 / 过时开发计划

更新时间：2026-05-23（PST）

本目录用于存放已经不应继续作为当前开发入口的历史计划文档。它们保留为背景材料，但不再作为当前代码事实、当前实施路径或当前主入口。

## 退场标准

- 关键前提已被当前代码事实否定
- 已被更新目录或更新主入口明确替代
- 仍有历史参考价值，但继续留在 `CURRENT_DEV` 会误导执行

## 已退场目录

- [2026-03-03 Platformization First Vectorization GM](./2026-03-03-platformization-first-vectorization-gm/)
  当前问题：文档把 `single_url` 视为唯一最终写入主链，但仓库现行主链已切到 `url_routing/source_library -> postprocess_frontdoor`，原前提已失效。
  替代入口：优先参考 [ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-search-chain-source-library-mounting-audit](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-search-chain-source-library-mounting-audit/01_system-investigation-search-chain-source-library-mounting-2026-03-14.md) 与 [ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-source-library-adapter-capability-remediation](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-source-library-adapter-capability-remediation/01_source-library-adapter-capability-remediation-2026-03-14.md)。
- [2026-03-04 RAG Line Round3 Filter Robustness](./2026-03-04-rag-line-round3-filter-robustness/)
  当前问题：文档引用的 `minimal_rag.py` 与测试路径已不在当前仓库；继续放在 `CURRENT_DEV` 会制造“还可按旧路径推进”的错觉。
  替代入口：无直接替代主文档；若要重启该主题，应按当前 RAG 代码结构重新立项。
- [2026-03-07 Builtin Writing Workbench Design](./2026-03-07-builtin-writing-workbench-design/)
  当前问题：文档前提是“写作域尚未落地”，但当前前后端写作域已经存在，原文已退化为早期设计稿。
  替代入口：优先参考 [ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-writing-workbench-evolution](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-writing-workbench-evolution/01_writing-workbench-evolution-plan-2026-03-07.md)。
- [2026-03-12 Time Semantics Density Merged Plan](./2026-03-12-time-semantics-density-merged-plan/)
  当前问题：该目录自己的 `README` 已声明“请使用新目录”，继续挂在 `CURRENT_DEV` 没有意义。
  替代入口：优先参考 [ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-time-semantics-density-merged-plan](../ARCHIVE_EXTERNAL_BLOCKED/2026-03-14-time-semantics-density-merged-plan/README.md)。
- [2026-03-24 Frontend Visual Layering](./2026-03-24-frontend-visual-layering/INDEX.md)
  当前问题：该目录是已补退场证据的空占位；可审计 scope 已由前端三层重写与 Wave3/Wave4 evidence 包承接，继续留在 `CURRENT_DEV` 会制造独立实施入口的错觉。
  替代入口：优先参考 [ARCHIVE_CLOSED/2026-03-15-frontend-three-layer-rewrite](../ARCHIVE_CLOSED/2026-03-15-frontend-three-layer-rewrite/16_wave32-frontend-i18n-final-closure-2026-05-23.md)、[frontend-topology-theme/2026-05-22](../../automation-runs/frontend-topology-theme/2026-05-22/README.md) 与 [frontend-runtime-visual/2026-05-22](../../automation-runs/frontend-runtime-visual/2026-05-22/README.md)。
- [2026-03-07 Dual Frontend Workbench Topology](./2026-03-07-dual-frontend-workbench-topology/13_wave28-retirement-decision-2026-05-23.md)
  当前问题：Wave27 i18n/page-shell disjoint gate、topology gate 与 business-string audit 已证明该目录没有独立 repo-local blocker；继续放在 `CURRENT_DEV` 会把三层重写继承事项重复计为单独 partial。
  替代入口：优先参考 [ARCHIVE_CLOSED/2026-03-15-frontend-three-layer-rewrite](../ARCHIVE_CLOSED/2026-03-15-frontend-three-layer-rewrite/16_wave32-frontend-i18n-final-closure-2026-05-23.md)。

## 返回

- [CURRENT_DEV](../CURRENT_DEV/INDEX.md) - 当前仍可作为现行入口的未封口开发计划
- [ARCHIVE_CLOSED](../ARCHIVE_CLOSED/INDEX.md) - 已收口开发计划
