# 市场情报（market-intel）后端数据采集扩展说明

> 最后更新：2026-02 | API 文档：`API接口文档.md` | 文档索引：`docs/README.md`

## 配置项（`.env`）

核心服务：`DATABASE_URL`、`ES_URL`、`REDIS_URL`（Docker 下有默认值）

LLM：`OPENAI_API_KEY`、`AZURE_*`、`OLLAMA_BASE_URL`（提取与发现依赖）

搜索/发现：`SERPER_API_KEY`、`GOOGLE_SEARCH_API_KEY`、`GOOGLE_SEARCH_CSE_ID`、`SERPAPI_KEY`、`SERPSTACK_KEY`、`BING_SEARCH_KEY`（见 `SEARCH_API_SETUP.md`）

数据源：`magayo_api_key`、`lotterydata_api_key`、`reddit_client_id`/`reddit_client_secret`/`reddit_user_agent`、`twitter_*`（api_key/secret/bearer_token/access_token/access_token_secret）、`rapidapi_key`

未配置时相关抓取/发现会自动跳过。

## 抓取能力

- 政策、市场数据（州彩票 API / 官网）
- 区域官网新闻 / 公告（如加州彩票）
- Reddit、Twitter 社媒
- 周度 / 月度报告、商品指标、电商价格
- 发现搜索（网页搜索 + 智能/深度发现）

## 主要接口

- `POST /api/v1/ingest/policy`、`/market`、`/news/calottery`、`/social/reddit`、`/social/sentiment`、`/reports/weekly`、`/commodity/metrics`、`/ecom/prices` 等
- `POST /api/v1/discovery/search`、`/smart`、`/deep`、`/generate-keywords`

均支持 `async_mode=true` 触发 Celery 任务。完整接口见 `API接口文档.md` 或 `http://localhost:8000/docs`。

