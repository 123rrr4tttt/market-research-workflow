# Search Provider Lab Execution Summary

日期：2026-05-14 PST  
范围：SearXNG / YaCy 本地开源搜索 provider 隔离部署、脚本、显式 adapter 接入与门禁验证。

## 官方文档校准

- SearXNG Search API：按官方 `/search?q=...&format=json` 组织；`format=json` 依赖 `settings.yml` 的 `search.formats` 启用。
- SearXNG settings：按官方 `SEARXNG_SETTINGS_PATH` 或 `/etc/searxng/settings.yml` 规则，把 `ops/search-lab/searxng` 挂载到 `/etc/searxng`。
- SearXNG Docker compose：按官方 compose 结构使用 `searxng/searxng:latest`、`./searxng:/etc/searxng:rw` 和独立 cache volume。
- YaCy Search API：按官方 `/yacysearch.json?query=...&resource=local|global&maximumRecords=...` 组织。
- YaCy Push API：按官方 `/api/push_p.json` 测试入口组织单文档 push，并要求 local 搜索命中。
- YaCy Docker image：使用官方 `yacy/yacy_search_server:latest` 镜像。

## 当前镜像实测差异

- 当前 YaCy 官方镜像的 push servlet 对单文档 GET-style push 需要 `data-0$file` 参数传正文；仅用 wiki 示例中的 `data-0` 会得到空数据异常。
- 当前 YaCy 官方镜像对最小 pushed 文档使用 `synchronous=true` 会触发同步压缩路径异常；smoke 使用异步 push，并轮询 `resource=local` 搜索命中。
- YaCy 通用关键词 compare 使用 `YACY_RESOURCE_MODE=global`；YaCy 本地索引能力由 `smoke_yacy.sh` 独立验证 `push -> resource=local hit`。

## 已交付

- `ops/search-lab/docker-compose.yml`
- `ops/search-lab/searxng/settings.yml`
- `ops/search-lab/yacy/.gitignore`
- `ops/search-lab/scripts/smoke_searxng.sh`
- `ops/search-lab/scripts/smoke_yacy.sh`
- `ops/search-lab/scripts/compare_keyword_search.py`
- `ops/search-lab/README.md`
- `main/backend/app/services/search/web.py` 显式 `searxng` / `yacy` provider adapter
- `main/backend/app/services/agent_core/project_tools.py` 显式 provider enum 与 readiness diagnostics
- `main/backend/tests/unit/test_search_web_provider_adapters_unittest.py`

## 验证结果

| 命令 | 结果 |
|---|---|
| `docker compose -f ops/search-lab/docker-compose.yml config` | 通过 |
| `bash -n ops/search-lab/scripts/smoke_searxng.sh ops/search-lab/scripts/smoke_yacy.sh` | 通过 |
| `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m py_compile main/backend/app/services/search/web.py main/backend/app/services/agent_core/project_tools.py main/backend/tests/unit/test_search_web_provider_adapters_unittest.py ops/search-lab/scripts/compare_keyword_search.py` | 通过 |
| `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_search_web_provider_adapters_unittest.py -q` | 4 passed |
| `PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_core_unittest.py -q -k "source_web_search"` | 4 passed, 56 deselected |
| `docker compose -f ops/search-lab/docker-compose.yml up -d searxng yacy` | 通过 |
| `bash ops/search-lab/scripts/smoke_searxng.sh` | 通过；root 200，search 200，17 条结果 |
| `YACY_ADMIN_USER=admin YACY_ADMIN_PASSWORD=mrwlabpass bash ops/search-lab/scripts/smoke_yacy.sh` | 通过；root 200，global 200，push 200，local 200，local hit true |
| `YACY_RESOURCE_MODE=global python3 ops/search-lab/scripts/compare_keyword_search.py --keywords "embodied ai" "robotics policy" --providers serper,searxng,yacy --out development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14/results.jsonl` | 已落盘 JSONL；SearXNG 2 行成功，YaCy 2 行成功，Serper 缺少 `SERPER_API_KEY` |

## 落盘记录

- `searxng_smoke.json`：`ok=true`，root/search 均 200，`embodied ai` 返回 17 条结构化结果。
- `yacy_smoke.json`：`ok=true`，root/global/push/local 均 200，`successall=true`，`local_hit=true`。
- `results.jsonl`：6 行 provider/keyword 记录；SearXNG 2 行成功，YaCy 2 行成功，Serper 2 行缺少本地 `SERPER_API_KEY`。

## 结论

源码 adapter、Agent tool 显式 provider 暴露、隔离实验目录和脚本已经完成，并按官方 API 组织。`provider="auto"` 未纳入 SearXNG / YaCy。

建议进入受控的显式 provider 试用阶段：

- `searxng`：作为低成本外部 metasearch 候选，只在显式 provider 下使用。
- `yacy`：作为本地资料库 / 自爬垂直索引候选，默认保持 `YACY_RESOURCE_MODE=local`；通用关键词对比才临时使用 `global`。
- `serper`：继续作为默认全网搜索主路径；当前本机未配置 `SERPER_API_KEY`，compare 中按 `MissingConfig` 记录。
