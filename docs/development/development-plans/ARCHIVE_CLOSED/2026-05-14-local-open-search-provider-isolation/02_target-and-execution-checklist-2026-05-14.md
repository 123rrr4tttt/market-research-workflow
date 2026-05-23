# Local Open Search Provider Target And Execution Checklist

更新时间：2026-05-14 PST  
状态：目录目标修复完成；源码、脚本、官方文档对齐说明和 SearXNG / YaCy 运行态 smoke 均已完成

## 1. 目标重述

本目录的目标是把 SearXNG / YaCy 作为本地可控、低成本、开源搜索 provider 候选完成隔离验证路线，而不是继续扩写 Agent 高保真迁移文档。

成功标准：

1. 形成目录内自洽的计划入口和执行清单。
2. 明确第一阶段只做隔离部署、smoke、compare，不修改主 MRW 服务链路。
3. 明确第二阶段才接入 `main/backend/app/services/search/web.py` 的显式 provider adapter。
4. 明确 SearXNG / YaCy 第一阶段不进入 `provider="auto"` 默认链。
5. 形成可审计的执行产物路径和完成判定。

## 2. prompt-to-artifact checklist

| 用户目标 / 文档要求 | 应有产物 | 当前证据 | 状态 |
|---|---|---|---|
| “这组文档”应回到指定文件夹 | `INDEX.md` 和本 checklist 位于 `2026-05-14-local-open-search-provider-isolation/` | 本文件和 `INDEX.md` | 完成 |
| SearXNG / YaCy 隔离部署规划 | `01_searxng-yacy-isolated-deployment-and-search-provider-integration-plan-2026-05-14.md` | 计划文件已存在 | 完成 |
| 不混入 Agent 高保真迁移文档 | 本目录不引用 `21-40_agent...` 作为本组目标 | `INDEX.md` 已声明边界 | 完成 |
| 第一阶段执行产物 | `ops/search-lab/docker-compose.yml`、配置、smoke、compare、README | 已落地 | 完成 |
| 第一阶段实测记录 | `development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14/SUMMARY.md` 和 `results.jsonl` | 已落盘；SearXNG 通过，YaCy global/push/local hit 通过，compare JSONL 已重跑 | 完成 |
| 第二阶段源码接入 | `search/web.py` 新增显式 `searxng` / `yacy` provider adapter | 已新增显式 provider，未进入 auto | 完成 |
| 第二阶段测试 | `test_search_web_provider_adapters_unittest.py` 和 `source_web_search` 相关测试 | adapter 4 passed；agent core source_web_search 4 passed | 完成 |

## 3. 第一阶段执行门禁

第一阶段只允许新增隔离实验目录和执行记录：

```text
ops/search-lab/
development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14/
```

第一阶段禁止：

- 修改 `main/ops/docker-compose.yml`。
- 修改主后端服务默认搜索链。
- 修改 `SERPER_API_KEY`、`GOOGLE_SEARCH_*` 或 LLM key。
- 把 `searxng` / `yacy` 放入 `provider="auto"`。

## 4. 完成判定

本目录文档修复完成的判定：

- `INDEX.md` 存在，且只说明 local open search provider isolation 主题。
- `02_target-and-execution-checklist-2026-05-14.md` 存在，且把计划要求映射到具体产物。
- 目录内没有混入 Claude Agent / writing / URL-pool / source-history 目标文档。

本目录目标全部完成的判定：

- 第一阶段 `ops/search-lab/` 产物全部存在。
- SearXNG smoke 有 HTTP 状态、结果数、错误类型。
- YaCy smoke 有 global JSON 解析、本地测试文档 push、local 命中记录。
- compare 脚本输出 JSONL，包含 `provider`、`keyword`、`ok`、`result_count`、`latency_ms`、`error_type`、`results`。
- `automation-runs/search-provider-lab/2026-05-14/SUMMARY.md` 明确是否进入第二阶段 adapter。

当前实测判定：

- `searxng_smoke.json`：`ok=true`，root 200，search 200，`embodied ai` 返回 17 条结果。
- `yacy_smoke.json`：`ok=true`，root 200，global 200，push 200，local 200，`local_push_success=true`，`local_hit=true`。
- `results.jsonl`：6 行记录；SearXNG 2 行成功，YaCy 2 行成功，Serper 2 行因本地未配置 `SERPER_API_KEY` 标记为 `MissingConfig`。

## 5. SearXNG 扩量策略

SearXNG 的结果量通过官方 `/search` API 的 `pageno` 翻页扩大，不依赖非官方大 `num` 参数。

- 后端 adapter：当 `max_results > 10` 时自动请求多页，默认最多 `SEARXNG_MAX_PAGES=5` 页。
- compare 脚本：同样按 `--limit` 自动翻页，便于实验对比 20、30、50 条结果。
- 安全上限：`SEARXNG_MAX_PAGES` 被硬限制在 10 页以内，避免本地 metasearch 与上游 engine 被单次任务拖垮。
- 默认链路：即使扩量，`searxng` 仍是显式 provider，不进入 `provider="auto"`。
