# 后端

API、领域服务和后台任务在这里实现。运行见[使用说明](../../docs/usage.md)，接口和专题见[后端文档](docs/README.md)。

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

均支持 `async_mode=true` 触发 Celery 任务。完整接口与当前 schema 见启动后的 `/docs`，实现入口见 `app/api`。

## 当前能力边界

- **来源与采集**：来源库、文件导入、HTTP 来源获取和异步采集任务继续由原服务与 Celery worker 执行；任务状态和业务结果从 Process/文档接口读回。
- **发现与检索**：网页搜索、智能/深度发现入口和 BM25、向量、混合检索并存。
- **Agent 工作台**：当前对话入口为 Codex WebUI，项目能力通过现有 AgentCore 宿主绑定提供；胞腔结构从 `GET /api/v1/agent-cell` 只读查询，显式选择的 package identity 随请求传递。
- **WebUI 边界**：Codex WebUI 的源码、协议版本、OAuth 和 LaunchAgent 说明见 [`../ops/codex-webui/README.md`](../ops/codex-webui/README.md)，其线程存储不自动等同于后端 native binding 的会话。

## 开发与验证

依赖来源、本地 kit 调试、贡献检查和测试入口见[开发指南](../../docs/development/README.md)。
