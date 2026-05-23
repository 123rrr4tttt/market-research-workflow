# Local Open Search Provider Isolation Index

更新时间：2026-05-23 PST
状态：`external_blocked` / `wave22_checked`。仓内 explicit provider trace、runtime boundary、health artifact、schema/readback 与单测门禁已封住；本目录不再作为 `CURRENT_DEV` partial 入口。剩余条件是 SearXNG / YaCy live availability、live result quality / freshness / latency stability、timeout policy、operator approval gate 与 `provider=auto` promotion owner decision。

防误读：下方“完成”项表示历史或仓内确定性证据已落地，不等于 `ARCHIVE_CLOSED`。当前 canonical readback 以本 `INDEX.md` 和 `16_wave22-external-blocked-decision-2026-05-22.md` 为准。

## 范围

本目录只覆盖以下目标：

- SearXNG / YaCy 的隔离 Docker 部署规划。
- `ops/search-lab/` 实验目录、smoke 脚本、compare 脚本的交付清单。
- `main/backend/app/services/search/web.py` 后续显式 provider adapter 接入边界。
- `development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14/` 实测记录要求。
- 下一轮 SearXNG 外部搜索管线接入目标。
- 下一轮本地索引加速后端候选评估框架。
- 后续解除隔离与全项目融贯性验证目标，包括本地 agent、写作工作台、候选来源审查和本地索引 prototype。
- 解除隔离实测证据，包括 agent SearXNG tool 调用、source candidate review、writing material retrieval backend replay、LanceDB local index prototype。
- 下一轮前端融贯性与 SearXNG candidate approval gate。
- SearXNG / YaCy / LanceDB 从隔离实验入口提升为项目级可选启动增强。
- Docker 模式跨平台 Web Launcher：通过独立 `launcher-ui` + 受控 `launcher-agent` 连接 Docker socket，只暴露当前 compose project 的白名单 start / stop / restart / status；控制面运行在 `5176`，业务前端继续运行在 `5174`。

本目录不覆盖 Claude Agent 高保真迁移、URL-pool、source history、long-task stage 等主题；这些主题的已封口主记录归档于 `../../ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration/`。

本目录也不继续推进 LanceDB vector / hybrid retrieval；该任务已定位到全项目数据向量化 / 标准化目录：

```text
../2026-05-14-global-vectorization-general-foundation/02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md
```

## 文件

- [01_searxng-yacy-isolated-deployment-and-search-provider-integration-plan-2026-05-14.md](./01_searxng-yacy-isolated-deployment-and-search-provider-integration-plan-2026-05-14.md)  
  SearXNG / YaCy 隔离部署与搜索 provider 接入计划。
- [02_target-and-execution-checklist-2026-05-14.md](./02_target-and-execution-checklist-2026-05-14.md)  
  本目录目标、产物、执行门禁和完成判定矩阵。
- [03_next-round-external-search-and-local-index-targets-2026-05-14.md](./03_next-round-external-search-and-local-index-targets-2026-05-14.md)  
  下一轮目标规定：SearXNG 接入外部搜索管线，本地索引后端重新选型。
- [04_local-index-backend-candidate-evaluation-framework-2026-05-14.md](./04_local-index-backend-candidate-evaluation-framework-2026-05-14.md)  
  本地索引加速候选评估框架，明确 source_library 数据库边界和候选实测口径。
- [05_searxng-external-search-pipeline-implementation-plan-2026-05-14.md](./05_searxng-external-search-pipeline-implementation-plan-2026-05-14.md)  
  SearXNG 外部搜索管线首轮实现、扩量策略与 20 关键词 × 30 条 benchmark 证据。
- [06_local-index-agent-backend-evaluation-plan-2026-05-14.md](./06_local-index-agent-backend-evaluation-plan-2026-05-14.md)  
  本地索引后端首轮评估执行记录，包含 dataset、SQLite FTS5 baseline、候选矩阵和推荐。
- [07_deisolation-and-project-coherence-targets-2026-05-14.md](./07_deisolation-and-project-coherence-targets-2026-05-14.md)  
  解除隔离与全项目融贯性目标及执行收口，记录本地 agent、写作工作台、候选来源审查、本地索引 prototype 的端到端验证证据。
- [08_next-round-frontend-coherence-and-searxng-candidate-gate-2026-05-14.md](./08_next-round-frontend-coherence-and-searxng-candidate-gate-2026-05-14.md)  
  WritingWorkbench 前端融贯性与 SearXNG candidate approval gate 执行收口：验证选区材料检索、agent / 写作工作台 contract 对齐、候选来源 approval / rejection gate 和 source_library 写边界。
- [09_optional-search-index-enhancements-launcher-integration-2026-05-14.md](./09_optional-search-index-enhancements-launcher-integration-2026-05-14.md)  
  SearXNG / YaCy / LanceDB 去实验化为可选增强：主 compose profile、跨平台启动窗口勾选项、本地 / Docker 启动参数、Docker Web Launcher / launcher-agent 和可选依赖边界。
- [10_search-provider-trace-contract-closure-replay-2026-05-22.md](./10_search-provider-trace-contract-closure-replay-2026-05-22.md)
  SearXNG / YaCy explicit provider trace contract closure replay，记录 `provider_route`、`provider_family`、`provider_auto_included`、`backend_trace` 的代码与单测落地证据。
- [11_wave6-9-status-evidence-and-min-plan-2026-05-22.md](./11_wave6-9-status-evidence-and-min-plan-2026-05-22.md)
  Wave6-9 topic-local 状态证据与最小开发计划，记录共享 `no_closure_claim` 状态滞后、本轮不编辑共享索引，以及 agent provider 配置护栏单测。

- [12_wave12-provider-readiness-gate-2026-05-22.md](./12_wave12-provider-readiness-gate-2026-05-22.md)
  Wave12 provider readiness gate，记录当前 SearXNG / YaCy live probe 仍是外部 runtime gap。
- [13_wave15-open-search-runtime-boundary-2026-05-22.md](./13_wave15-open-search-runtime-boundary-2026-05-22.md)
  Wave15 runtime boundary gate，固定 `closure_claim_allowed=false`。
- [14_wave18-open-search-health-artifact-2026-05-22.md](./14_wave18-open-search-health-artifact-2026-05-22.md)
  Wave18 health artifact gate，保留 live probe open / partial health state。
- [15_wave19-open-search-health-artifact-schema-readback-2026-05-22.md](./15_wave19-open-search-health-artifact-schema-readback-2026-05-22.md)
  Wave19 schema/readback gate，确认未宣称 external provider closure。
- [16_wave22-external-blocked-decision-2026-05-22.md](./16_wave22-external-blocked-decision-2026-05-22.md)
  当前 canonical decision：repo-local blocker 清零，剩余为外部 provider/runtime/quality 条件。

## 当前状态

| 项 | 状态 | 证据 |
|---|---|---|
| 当前封口口径 | `external_blocked` / `wave22_checked` | `16_wave22-external-blocked-decision-2026-05-22.md`；不能迁入 `ARCHIVE_CLOSED` |
| 规划文档 | 完成 | `01_...plan...md` 已包含目标、非目标、API、provider contract、源码接入面、门禁和风险 |
| 目录边界 | 已修正 | 本 `INDEX.md` 明确本目录只处理 local open search provider isolation |
| 执行产物 | 已落地 | `ops/search-lab/`、smoke 脚本、compare 脚本和 automation run 已在本目录目标下落地 |
| 运行态 smoke | 完成 | SearXNG root/search 200 且返回 17 条结果；YaCy root/global/push/local search 均 200，本地 push 文档可被 `resource=local` 命中 |
| 下一轮目标 | 已规定 | `03_...targets...md` 明确 SearXNG 外部搜索管线与本地索引后端选型两条线 |
| 本地索引评估 | 已规定 | `04_...framework...md` 明确 YaCy local 只做 baseline，优先实测 LanceDB / Qdrant / Meilisearch / Typesense |
| SearXNG 外部 benchmark | 完成 | `automation-runs/search-provider-benchmark/2026-05-14/`：20 queries 全部 ok，每条返回 30 条，p50 1404.49ms |
| 本地索引 baseline | 完成 | `automation-runs/local-index-backend-evaluation/2026-05-14/`：40 documents、232 chunks、30 queries，SQLite FTS5 与 LanceDB FTS 均 30 queries 全部 ok |
| 解除隔离与项目融贯性 | 后端 replay 完成；前端 e2e blocked_by_env | `automation-runs/deisolation-project-coherence/2026-05-14/`：agent SearXNG 调用 14 条候选、source candidate review 14 条 URL、writing material retrieval 10 条结果、LanceDB FTS prototype 通过，`provider=auto` 未接入 SearXNG |
| 前端融贯性与候选门禁 | 完成 | `automation-runs/frontend-coherence-and-searxng-gate/2026-05-14/`：WritingWorkbench e2e 6 passed，选区材料检索调用 `project.context.bundle` + `writing.document.list` 且未写回，SearXNG gate 14 candidates / 1 approved / 1 rejected / 12 pending，裸搜索结果未写入 source_library |
| 可选增强启动器 | 完成 | `09_...launcher-integration...md`：SearXNG / YaCy 主 compose profile、LanceDB optional requirements、跨平台窗口勾选项、macOS 包装窗口、独立 Docker Web Launcher / launcher-agent 控制面和启动脚本透传均已完成 |
| Explicit provider trace contract | 完成 | `10_...closure-replay...md`：SearXNG / YaCy 结果新增 explicit route trace；adapter 单测覆盖显式 provider trace 与 `provider=auto` 排除关系 |
| Explicit provider trace offline artifact | 完成 | `automation-runs/search-provider-trace-artifacts/2026-05-22/`：离线 artifact 复跑脚本固化 `provider_route`、`provider_family`、`provider_auto_included` 和 `backend_trace` 字段 |
| Explicit provider trace container replay | 完成 | `automation-runs/search-provider-container-replay/2026-05-22/`：SearXNG 与 YaCy 真实容器 replay 均通过，`provider_trace_replay.jsonl` 记录 explicit provider trace 字段 |
| Wave6-9 topic-local status evidence | 完成 | `11_wave6-9-status-evidence-and-min-plan-2026-05-22.md`：确认共享 `no_closure_claim` 状态滞后，本轮不改共享索引；新增 agent provider 配置护栏测试 |
