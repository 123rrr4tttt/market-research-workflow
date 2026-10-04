# 市场情报（market-intel）后端数据采集扩展说明

> 最后更新：2026-10-05 | 当前入口：[`../../README.md`](../../README.md) | API 文档：[`API接口文档.md`](API接口文档.md) | 文档索引：[`docs/README.md`](docs/README.md)

本文件说明后端采集、发现接口与配置边界。当前实现状态、运行入口和生产历史以根 README 和 [2026-10-04 本机日常链路证据](../../.data/readiness-repair/20261004-daily-chain/daily-chain-state.json) 为准。

## 配置项（`.env`）

核心服务：`DATABASE_URL`、`ES_URL`、`REDIS_URL`（Docker 下有默认值）

LLM：`OPENAI_API_KEY`、`AZURE_*`、`OLLAMA_BASE_URL`（提取与发现依赖）

搜索/发现：`SERPER_API_KEY`、`GOOGLE_SEARCH_API_KEY`、`GOOGLE_SEARCH_CSE_ID`、`SERPAPI_KEY`、`SERPSTACK_KEY`、`BING_SEARCH_KEY`（见 `SEARCH_API_SETUP.md`）

数据源：`reddit_client_id`/`reddit_client_secret`/`reddit_user_agent`、`twitter_*`（api_key/secret/bearer_token/access_token/access_token_secret）、`rapidapi_key`

未配置时相关抓取/发现会自动跳过。

## 抓取能力

- 政策、市场数据（按项目接入）
- 区域官网新闻 / 公告（按项目接入）
- Reddit、Twitter（作为数据 API 来源）
- 周度 / 月度报告、商品指标、电商价格
- 发现搜索（网页搜索 + 智能/深度发现）

## 主要接口

- `POST /api/v1/ingest/market`、`/news/resource/{resource_id}`、`/social/reddit`、`/data-api`、`/reports/weekly`、`/commodity/metrics`、`/ecom/prices` 等
- `POST /api/v1/discovery/search`、`/smart`、`/deep`、`/generate-keywords`

均支持 `async_mode=true` 触发 Celery 任务。完整接口见 `API接口文档.md` 或 `http://localhost:8000/docs`。

## 当前能力边界

- **来源与采集**：来源库、文件导入、HTTP 来源获取和异步采集任务继续由原服务与 Celery worker 执行；任务状态和业务结果从 Process/文档接口读回。
- **发现与检索**：网页搜索、智能/深度发现入口和 BM25、向量、混合检索并存；2026-10-04 日常链路证据覆盖 pgvector 后端的实际读回。
- **Agent 对话**：`/api/v1/agent-chat` 只接受显式 `agent_macro_native` 或 `agent_macro_rapid_native`。两者通过 `CodexAppServerCore.invoke_native` 和项目绑定执行；旧 Agent runtime 请求返回 410，旧控制字段返回 400。
- **WebUI 边界**：Codex WebUI 的源码、协议版本、OAuth 和 LaunchAgent 说明见 [`../ops/codex-webui/README.md`](../ops/codex-webui/README.md)，其线程存储不自动等同于后端 native binding 的会话。

## 贡献开发入口

后端贡献检查从仓库根执行 `python3 scripts/dev.py`，默认选择本目录的 `.venv311`，或用 `MRW_DEV_PYTHON` 指向等价环境。默认 kit 来源由根 [`pyproject.toml`](../../pyproject.toml) 固定为 Git revision `6dbae536a72ab235998b21c9647b8b00d15a71e6`；`setup` 显式安装并回验，`check` 只核验不安装。

显式本地开发时，同一子命令追加 `--local-kit <checkout>/python`。该路径必须是真实 functorial-kit Git checkout 的 `python` 包目录，先经 `setup --local-kit` 安装为 editable，后续子命令核验安装路径一致：

```bash
python3 scripts/dev.py setup --local-kit /path/to/functorial-kit/python
python3 scripts/dev.py check --local-kit /path/to/functorial-kit/python
python3 scripts/dev.py validate --local-kit /path/to/functorial-kit/python
```

`test` 和 `validate` 还要求所选环境已有 SQLAlchemy 等后端测试依赖；完整子命令和验证口径见根 [`README.md`](../../README.md#项目贡献检查)。

## 历史状态入口

以下 2026-02-27 文件是当时 8.x 路线的工作快照，仅用于追溯分项 owner、验收和执行记录；它们不是当前实现状态或新的执行指令：

- [`../../plans/status-8x-2026-02-27.md`](../../plans/status-8x-2026-02-27.md)
- [`../../plans/8x-multi-agent-kickoff-2026-02-27.md`](../../plans/8x-multi-agent-kickoff-2026-02-27.md)
- [`../../development/latest-dev-docs/root-plans/G_REVIEW/MERGED_PLAN_REVIEW.md`](../../development/latest-dev-docs/root-plans/G_REVIEW/MERGED_PLAN_REVIEW.md)：记录当时同组缺失的 round/decision 文件及合并审查结论。
