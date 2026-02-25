# 彩票情报后端数据采集扩展说明

## 新增配置项
- `magayo_api_key`
- `lotterydata_api_key`
- `reddit_client_id` / `reddit_client_secret` / `reddit_user_agent`
- `twitter_bearer_token`
- `rapidapi_key`

均可在 `.env` 中配置，未提供时相关抓取会自动跳过。

## 新增抓取能力
- Magayo Lottery API（`source_hint=magayo`）
- LotteryData.io 市场数据（`source_hint=lotterydata`）
- 加州官网新闻 / 零售商公告
- Reddit `r/Lottery` 等子论坛讨论
- 周度 / 月度行业报告聚合

## 对应接口
- `POST /api/ingest/news/calottery`
- `POST /api/ingest/news/calottery/retailer`
- `POST /api/ingest/social/reddit`
- `POST /api/ingest/reports/weekly`
- `POST /api/ingest/reports/monthly`

均支持 `async_mode=true` 触发 Celery 任务。详细参数见 FastAPI OpenAPI 说明。

