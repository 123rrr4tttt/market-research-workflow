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

## 当前状态差异（已实现 vs 规划）

本文件关注后端实现与能力边界；与根目录 `README.md` 的 8.x 状态保持一致：  

- `8.1 来源池自动提取与整合`：**已完成**（来源抽取与统一搜索链路已稳定）
- `8.2 完善工作流平台化`：**部分完成**（已落地模板读取/保存 + 运行触发最小闭环）
- `8.3 集成 Perplexity`：**未开始**
- `8.4 时间轴与事件/实体演化`：**进行中**（时间线展示在前端有覆盖，但缺统一模型）
- `8.5 RAG + LLM 对话与分析报告`：**部分完成**（检索/向量能力到位，未有闭环对话与报表 API）
- `8.6 公司/商品/电商对象化采集`：**部分完成**（专题抽取与图谱资产存在，链路未统一）
- `8.7 数据类型优化`：**进行中**（提取与结构化持续优化）
- `8.8 其他迭代`：**进行中**（适配器稳定性、测试、脚本清理仍在持续）

建议参照：
- `README.md`：完整进度与验收动作
- `plans/status-8x-2026-02-27.md`：8.x 分项 owner/验收清单
- `plans/8x-multi-agent-kickoff-2026-02-27.md`：并行执行启动与角色说明
- `plans/8x-round-1-2026-02-27.md`：第1轮执行记录
- `plans/decision-log-2026-02-27.md`：关键决策与口径说明
- `plans/8x-round-2-2026-02-27.md`：第2轮执行记录（P0）
- `plans/8x-round-2-2026-02-27-taskboard.md`：P0 任务看板（8.2/8.5/8.6）
