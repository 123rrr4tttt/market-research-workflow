# frontend-modern

React + Vite 新前端栈（Docker-first），用于替代旧模板前端。

## 已完成（本轮）

- 迁移 `ingest` 核心参数：
  - 查询词、专题联想、语言、provider、max_items、start_offset、days_back
  - `enable_extraction`、`async_mode`
  - 社交参数：`platforms`、`base_subreddits`、`enable_subreddit_discovery`
  - 来源库执行：`item_key` / `handler_key` + `override_params`
  - 商品、电商采集参数
- 视觉升级 V2：深色侧栏 + 高对比卡片 + 渐变背景 + 强层级数据面板（偏 n8n/办公后台风格）

## 1) 本地开发

```bash
npm install
VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
```

默认会将 `/api/*` 代理到 `VITE_API_PROXY_TARGET`（未设置时为 `http://localhost:8000`）。

## 2) Docker 运行

```bash
docker build -t market-frontend-modern .
docker run --rm -p 5174:80 --network <your-compose-network> market-frontend-modern
```

容器内 Nginx 已将 `/api/*` 反向代理到 `http://backend:8000`。
默认建议不设置 `VITE_API_BASE_URL`（保持空值），前端将继续使用同源 `/api/*` 并走 Nginx 反代。

## 3) docker-compose 示例

```yaml
services:
  frontend-modern:
    build:
      context: ./main/frontend-modern
      args:
        VITE_API_BASE_URL: ${VITE_API_BASE_URL:-}
    ports:
      - "5174:80"
    depends_on:
      - backend
    networks:
      - default

# 使用仓库内 compose
docker compose -f main/ops/docker-compose.yml --profile modern-ui up -d frontend-modern

默认情况下（compose 中 backend 已设置 `MODERN_FRONTEND_URL=http://localhost:5174`），访问 `http://localhost:8000/`、`/app`、`/app.html` 会重定向到 modern 前端。

变量说明：
- `VITE_API_PROXY_TARGET`：仅本地 `npm run dev` 代理目标。
- `VITE_API_BASE_URL`：前端构建期变量，写入静态产物；不设置时保持当前相对路径行为。
```

## 4) 对齐的核心 API

- `GET /api/v1/health`
- `GET /api/v1/projects`
- `POST /api/v1/projects/{project_key}/activate`
- `POST /api/v1/discovery/generate-keywords`
- `POST /api/v1/ingest/policy`
- `POST /api/v1/ingest/policy/regulation`
- `POST /api/v1/ingest/market`
- `POST /api/v1/ingest/social/sentiment`
- `POST /api/v1/ingest/commodity/metrics`
- `POST /api/v1/ingest/ecom/prices`
- `POST /api/v1/ingest/source-library/sync`
- `POST /api/v1/ingest/source-library/run`
- `GET /api/v1/ingest/history`
- `GET /api/v1/source_library/items`
- `GET /api/v1/resource_pool/site_entries/grouped`

接口盘点见：
- `/Users/wangyiliang/projects/信息收集工作流/main/backend/docs/API_ROUTE_INVENTORY_2026-02-27.md`
- `/Users/wangyiliang/projects/信息收集工作流/main/backend/docs/FRONTEND_MODERNIZATION_API_MAP_2026-02-27.md`
