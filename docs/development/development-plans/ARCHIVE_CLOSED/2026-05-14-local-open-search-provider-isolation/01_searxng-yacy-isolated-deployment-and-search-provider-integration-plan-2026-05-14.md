# SearXNG / YaCy 隔离部署与搜索 Provider 接入计划

更新时间：2026-05-14 PST  
状态：源码、隔离脚本、官方文档对齐说明和 SearXNG / YaCy 运行态 smoke 均已完成  
范围：先隔离部署并验证关键词检索能力，再按统一搜索接口接入本项目。

## 1. 背景

Google Custom Search JSON API 对新客户和新全网搜索配置已经不适合作为默认路线。本项目当前已经验证 `SERPER_API_KEY` 可用，但仍需要一条低成本、可本地部署、可替换的搜索 provider 试验路径。

本计划只处理两个开源候选：

- `SearXNG`：自托管 metasearch，负责聚合上游搜索引擎结果。
- `YaCy`：自建 / P2P 搜索引擎，负责爬取、索引并搜索本地或 P2P 网络中的文档。

本阶段不直接替换生产搜索链路，先保持接口层标准，隔离跑通服务、API、关键词检索和结果标准化样例。

## 2. 目标

1. 在本机用独立 Docker Compose 或等价脚本分别启动 `SearXNG` 与 `YaCy`。
2. 不污染现有 MRW 后端、数据库、Celery、Redis、Elasticsearch 运行态。
3. 明确两者的关键词检索 API、返回结构、失败形态和稳定性边界。
4. 输出统一 provider contract，使后续接入 `main/backend/app/services/search/web.py` 时只新增 provider adapter，不改调用方语义。
5. 形成最小验证脚本：同一组关键词分别跑 `serper`、`searxng`、`yacy`，比较结果数量、字段完整度、延迟和失败原因。

## 3. 非目标

- 不把 YaCy 当作 Google 全网搜索的等价替代。
- 不在第一阶段让 SearXNG / YaCy 进入默认自动降级链。
- 不修改现有 `SERPER_API_KEY`、`GOOGLE_SEARCH_*`、LLM key。
- 不要求本机长期运行两个服务；先以可重复启动、可验证为准。
- 不在第一阶段做大规模爬虫任务，避免磁盘、网络和上游站点风险。

## 4. 推荐目录

建议把隔离实验放在项目内独立目录：

```text
ops/search-lab/
  docker-compose.yml
  searxng/
    settings.yml
  yacy/
    DATA/              # gitignore
  scripts/
    smoke_searxng.sh
    smoke_yacy.sh
    compare_keyword_search.py
  README.md
```

后续若决定并入正式部署，再迁移到 `main/ops/docker-compose.yml` 或新增 profile；第一阶段不直接挂到主 compose。

## 5. 统一接口标准

本项目内部搜索 provider 应统一输出以下字段：

```json
{
  "keyword": "embodied ai",
  "title": "Result title",
  "link": "https://example.com/page",
  "snippet": "Short summary or excerpt",
  "source": "searxng",
  "published_at": null,
  "rank": 1,
  "raw": {}
}
```

字段约束：

- `title`、`link`、`snippet` 是进入后续来源候选链路的最低字段。
- `source` 固定为 `searxng` 或 `yacy`，不要把上游搜索引擎名覆盖掉 provider 名；上游来源放入 `raw.engine` 或 `raw.origin`.
- `link` 必须走现有 URL canonicalization / tracking 参数清理。
- provider adapter 只负责外部搜索和结果标准化，不负责候选评分、抓取正文、入库。

## 6. SearXNG 隔离部署

### 6.1 应用方式

SearXNG 提供 `/search` HTTP API，关键词参数为 `q`，JSON 输出需要显式启用。

示例：

```bash
curl 'http://127.0.0.1:8088/search?q=embodied%20ai&format=json&language=en&pageno=1'
```

需要关注：

- `settings.yml` 中 `search.formats` 必须包含 `json`。
- 公共实例常关闭 JSON 输出；本计划只验证自托管实例。
- 可按需配置 `engines`，例如先关闭容易触发限流的上游，只保留稳定源。
- metasearch 的结果质量和稳定性取决于上游，失败形态包括 timeout、captcha、engine blocked、empty result。

### 6.2 最小验收

1. `GET /` 返回 200。
2. `GET /search?q=embodied%20ai&format=json` 返回 200。
3. JSON 中至少可解析出 3 个包含 `title` + `url/link` 的结果。
4. 连续 5 次关键词请求没有进程崩溃。
5. 失败时能返回可记录的错误类型，而不是让本项目搜索链路抛未捕获异常。

## 7. YaCy 隔离部署

### 7.1 应用方式

YaCy 默认端口为 `8090`，可以通过 `yacysearch.json` 或内置 Solr API 做关键词检索。

YaCy 标准搜索：

```bash
curl 'http://127.0.0.1:8090/yacysearch.json?query=embodied%20ai&resource=global&maximumRecords=10'
```

本地索引搜索：

```bash
curl 'http://127.0.0.1:8090/yacysearch.json?query=embodied%20ai&resource=local&maximumRecords=10'
```

Solr 直接查询：

```bash
curl 'http://127.0.0.1:8090/solr/select?q=text_t:embodied%20ai&defType=edismax&rows=10&wt=yjson&core=collection1'
```

需要关注：

- `resource=global` 依赖 YaCy P2P 网络，可用性和质量不可控。
- `resource=local` 只搜本机索引；如果没有先爬取或 push 文档，结果可能为空。
- YaCy 更适合做“本地资料库 / 行业垂直库关键词检索”，不适合直接作为全网 Google 替代。
- YaCy 带爬虫和索引，必须限制数据卷、爬取范围和资源消耗。

当前官方镜像实测补充：

- `yacy/yacy_search_server:latest` 可在本隔离 compose 中启动，端口固定绑定 `127.0.0.1:8090`。
- `/yacysearch.json` 按官方 search API 工作，`resource=global` 可用于通用关键词对比，`resource=local` 只验证本地索引。
- `/api/push_p.json` 仍按官方 push API 组织；当前镜像对单文档 GET-style push 需要使用 `data-0$file` 传入正文。仅用 wiki 示例中的 `data-0` 会返回 200 但服务端实际报空数据异常。
- 当前镜像对该最小文档使用 `synchronous=true` 时会触发服务端同步压缩路径异常；实验脚本使用异步 push，再轮询 `resource=local` 搜索命中。

### 7.2 最小验收

1. `GET /` 或管理页面返回 200。
2. `GET /yacysearch.json?...resource=global...` 可返回合法 JSON，即使结果为空也要能解析。
3. 向本地索引 push 一个测试文档后，`resource=local` 能通过关键词检索命中该文档。
4. 数据目录独立挂载，停止容器后不影响主项目 Elasticsearch / 数据库。
5. 记录一次 `global` 与 `local` 的结果差异，明确后续接入默认使用哪一种模式。

## 8. 接入策略

### 8.1 第一阶段：外部服务不进主链路

只新增隔离脚本和 README：

- `smoke_searxng.sh`：验证服务和 JSON 搜索。
- `smoke_yacy.sh`：验证服务、global 搜索、本地 push + local 搜索。
- `compare_keyword_search.py`：输入关键词数组，输出标准化 JSONL。

验收输出保存到：

```text
development/latest-dev-docs/automation-runs/search-provider-lab/YYYY-MM-DD/
```

### 8.2 第二阶段：新增 provider adapter

在 `main/backend/app/services/search/web.py` 中新增 provider 分支：

- `provider="searxng"`：读取 `SEARXNG_BASE_URL`，调用 `/search`.
- `provider="yacy"`：读取 `YACY_BASE_URL` 和 `YACY_RESOURCE_MODE`，调用 `/yacysearch.json`.

建议环境变量：

```bash
SEARXNG_BASE_URL=http://127.0.0.1:8088
YACY_BASE_URL=http://127.0.0.1:8090
YACY_RESOURCE_MODE=local
```

第二阶段仍不放入 `auto` 默认链，先只允许显式 provider 调用：

```python
search_sources("embodied ai", "en", max_results=5, provider="searxng")
search_sources("embodied ai", "en", max_results=5, provider="yacy")
```

### 8.3 第三阶段：纳入降级链

只有在连续验证满足以下条件后，才考虑放入自动链：

- SearXNG：常用关键词连续批量搜索稳定，空结果率可接受。
- YaCy：本地索引已有明确数据来源，且命中质量优于通用外部搜索补充。
- 两者失败时不会拖慢 `serper` 主路径。

推荐自动链优先级：

```text
serper -> brave/dataforseo/searchapi paid providers -> searxng optional -> yacy local corpus -> ddg fallback
```

YaCy 不建议作为通用全网 fallback；更适合作为 `local_corpus_search` 或 `source_library_search` 的补充 provider。

## 9. 当前代码接入面

规划完成时的 repo-grounded 接入点如下，执行阶段必须先按这些位置做最小改动：

| 接入面 | 当前状态 | 执行要求 |
|---|---|---|
| `main/backend/app/services/search/web.py::search_sources` | 显式 provider 已支持 `ddg`、`google`、`serper`、`serpstack`、`serpapi`；`auto` 链为 Serper -> Google -> Serpstack -> SerpAPI -> DDG/site fallback | 新增 `searxng` / `yacy` 分支时只放在 `provider != "auto"` 路径，不改 `auto` 链 |
| `main/backend/app/services/search/web.py::_score_search_result` | provider 加权列表只包含现有 provider | 若新 provider 进入结果排序，只加最小中性权重或保持无额外权重，避免把本地实验 provider 错当高可信源 |
| `main/backend/app/services/search/web.py::_canonicalize_url` 与 `_add_result_dedup` | 已有 URL 清洗和去重入口 | 新 adapter 返回前必须复用现有清洗 / 去重路径，不在 adapter 内另写一套规则 |
| `main/backend/app/services/agent_core/project_tools.py::source.web.search` | tool schema 的 provider enum 还没有 `searxng` / `yacy`；诊断只覆盖现有 provider key | 后端 adapter 验证通过后，才允许把 enum 和 readiness diagnostics 加入新 provider |
| `main/backend/app/settings/config.py` | 只有 `serper_api_key`、`google_search_*` 等现有 provider 配置 | 第二阶段再新增 `searxng_base_url`、`yacy_base_url`、`yacy_resource_mode`，第一阶段只用 shell/env 脚本 |
| `main/backend/tests/unit/` | 已有 provider、agent tool、source_library 边界单测 | 第二阶段必须加 adapter 单测，第三阶段才补 agent tool schema / diagnostics 单测 |

第一阶段不修改上述源码；只创建 `ops/search-lab/`、脚本、README 和 `automation-runs/search-provider-lab/` 记录。第二阶段若开始源码接入，必须在同一 PR / 同一任务内补齐测试。

## 10. 执行门禁与产物

第一阶段产物：

- `ops/search-lab/docker-compose.yml`
- `ops/search-lab/searxng/settings.yml`
- `ops/search-lab/scripts/smoke_searxng.sh`
- `ops/search-lab/scripts/smoke_yacy.sh`
- `ops/search-lab/scripts/compare_keyword_search.py`
- `ops/search-lab/README.md`
- `development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14/SUMMARY.md`
- `development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14/results.jsonl`

第一阶段最小命令：

```bash
docker compose -f ops/search-lab/docker-compose.yml up -d searxng yacy
bash ops/search-lab/scripts/smoke_searxng.sh
bash ops/search-lab/scripts/smoke_yacy.sh
python3 ops/search-lab/scripts/compare_keyword_search.py --keywords "embodied ai" "robotics policy" --providers serper,searxng,yacy --out development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14/results.jsonl
docker compose -f ops/search-lab/docker-compose.yml down
```

第一阶段完成判定：

- `docker compose` 只使用 `ops/search-lab/docker-compose.yml`，不改 `main/ops/docker-compose.yml`。
- `searxng` 绑定 `127.0.0.1:8088`，`yacy` 绑定 `127.0.0.1:8090`，不占用主项目端口。
- `smoke_searxng.sh` 至少保存一次 HTTP 状态、结果数、错误类型。
- `smoke_yacy.sh` 至少保存 global 搜索解析结果、本地测试文档 push 记录、local 搜索命中记录。
- `compare_keyword_search.py` 输出 JSONL，每行包含 `provider`、`keyword`、`ok`、`result_count`、`latency_ms`、`error_type`、`results`。
- `SUMMARY.md` 明确写出是否建议进入第二阶段 adapter；若不建议，也必须写出阻塞原因。

2026-05-14 实测结论：

- 第一阶段隔离部署、smoke 与 compare 已通过，记录位于 `development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14/`。
- 第二阶段显式 adapter 已完成，`searxng` / `yacy` 只允许显式 provider 调用，未进入 `provider="auto"`。
- YaCy 的通用关键词 compare 使用 `YACY_RESOURCE_MODE=global`；YaCy 的本地索引能力由 `smoke_yacy.sh` 独立验证 `push -> resource=local hit`。

第二阶段源码门禁：

```bash
cd main/backend
python3.11 -m pytest -q tests/unit/test_search_web_provider_adapters_unittest.py
python3.11 -m pytest -q tests/unit/test_agent_core_unittest.py -k "source_web_search"
```

若新增配置字段，还要运行：

```bash
cd main/backend
python3.11 -m pytest -q tests/unit/test_settings_manager_unittest.py
```

## 11. 任务拆解

| 阶段 | 任务 | 输出 | 验收 |
|---|---|---|---|
| P0 | 创建 `ops/search-lab` 隔离目录 | compose、配置、README | 不改主 compose，不影响主服务 |
| P1 | 跑通 SearXNG | 本地服务 + smoke 记录 | `/search?...format=json` 有结构化结果 |
| P2 | 跑通 YaCy | 本地服务 + push/local 搜索记录 | 测试文档可被关键词命中 |
| P3 | 输出标准化 compare 脚本 | JSONL 对比结果 | 同关键词可比较 Serper/SearXNG/YaCy |
| P4 | 评估接入点 | provider contract + 风险表 | 明确是否进入后端 adapter |
| P5 | 后端显式 provider 接入 | `searxng` / `yacy` adapter | 单测 + 显式 provider smoke 通过 |
| P6 | Agent tool 显式 provider 暴露 | schema enum + readiness diagnostics | `source.web.search` 只在显式 provider 下可选新 provider |

## 12. 风险与控制

| 风险 | 影响 | 控制 |
|---|---|---|
| SearXNG 上游限流 | 空结果或不稳定 | 默认不进 auto 链；记录 engine-level failure |
| SearXNG JSON 未启用 | 403 | 自托管配置固定启用 `json` |
| YaCy 本地索引为空 | local 搜索无结果 | smoke 中必须 push 测试文档 |
| YaCy P2P 质量不可控 | global 搜索噪音大 | 默认评估 local 和 global，不承诺全网质量 |
| 容器资源占用 | 影响主项目 | 独立 compose、独立数据卷、限制爬取范围 |
| 接口字段不一致 | 后续链路失败 | 先用统一 JSONL contract 做适配 |
| 新 provider 误入 auto 链 | 拖慢或污染默认搜索 | 第二阶段测试必须断言 `provider="auto"` 不调用 SearXNG / YaCy |
| Agent tool 过早暴露实验 provider | 模型误用未验证链路 | 仅在 adapter 单测和 smoke 通过后再更新 provider enum |

## 13. 决策口径

推荐结论先按以下方向推进：

1. `SearXNG`：作为低成本“外部 web metasearch provider”候选，适合优先接显式 provider。
2. `YaCy`：作为“本地资料库 / 自爬垂直索引 provider”候选，先验证 local corpus 检索，不作为全网搜索替代。
3. `Serper`：继续作为当前默认可用的全网搜索 provider。

本计划完成后，下一份文档应是执行记录，而不是继续扩写方案：

```text
development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14/SUMMARY.md
```

## 14. 规划完成审计

目标文件已覆盖本规划任务的成功标准：

| 明确要求 | 规划证据 | 状态 |
|---|---|---|
| 隔离启动 SearXNG / YaCy | 第 4、6、7、10 节定义 `ops/search-lab`、端口、compose、smoke 命令 | 完成 |
| 不污染主 MRW 运行态 | 第 3、4、10、12 节规定不改主 compose、不占用主端口、独立数据卷 | 完成 |
| 明确 API、返回结构、失败形态 | 第 5、6、7、10 节定义 provider contract、curl 示例、错误记录字段 | 完成 |
| 后续接入 `main/backend/app/services/search/web.py` 的边界 | 第 8、9、10 节映射真实源码入口、限制只走显式 provider、不进 auto 链 | 完成 |
| 最小验证脚本与对比产物 | 第 8、10 节定义 smoke 和 compare 脚本、JSONL 字段、落盘目录 | 完成 |
| 开发文档索引可追踪 | 已在 `development/latest-dev-docs/README.md`、`MERGED_OVERVIEW.md`、`development-plans/INDEX.md`、`development-plans/main/index.md`、`CURRENT_DEV/INDEX.md` 建立引用 | 完成 |

因此，本文件的“规划”本身已经完成；后续工作应进入 `ops/search-lab` 执行与 `automation-runs/search-provider-lab/2026-05-14/SUMMARY.md` 实测记录，不再继续扩写本计划。

## 15. 执行状态补记

已按官方文档完成隔离目录、脚本与显式 provider adapter：

- `ops/search-lab/README.md` 记录 SearXNG / YaCy 官方接口依据。
- `ops/search-lab/docker-compose.yml` 通过 `docker compose config` 校验。
- `main/backend/app/services/search/web.py` 已新增显式 `searxng` / `yacy` adapter，且不进入 `provider="auto"`。
- `main/backend/app/services/agent_core/project_tools.py` 已将两个 provider 加入显式 enum 与 diagnostics。
- `main/backend/tests/unit/test_search_web_provider_adapters_unittest.py` 已覆盖标准化与 auto 隔离。
- `development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14/SUMMARY.md` 已记录实测结果。

运行态 smoke 已通过：SearXNG 官方镜像已拉取并启动，`/` 与 `/search?format=json` 均返回 200，`embodied ai` 返回 17 条结构化结果；YaCy 官方镜像已启动，`/`、`/yacysearch.json?resource=global`、`/api/push_p.json` 和 `resource=local` 搜索命中均通过。最终验证后应执行 `docker compose -f ops/search-lab/docker-compose.yml down`，不保留运行容器。
