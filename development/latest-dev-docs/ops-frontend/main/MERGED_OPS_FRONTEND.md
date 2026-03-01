# Ops + Frontend 合并草案

> 文档日期: 2026-03-01  
> 范围: 部署、前端、Figma 同步、快速启动  
> 来源: `ops-README.md`、`frontend-modern-README.md`、`frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md`、`QUICKSTART.md`

## 1. 部署（Docker-first）

### 1.1 推荐入口与约定

- 推荐使用统一脚本，而非日常直接使用 `docker compose`：
  - `main/ops/start-all.sh`
  - `main/ops/stop-all.sh`
  - `main/ops/restart.sh`
  - 仓库根目录 `./scripts/docker-deploy.sh start|stop|restart|status|logs|health|preflight`
- 首次运行需确保 `main/backend/.env` 存在（可由 `.env.example` 复制）。
- 团队协作约定：命令在仓库根目录执行，并先设置：

```bash
export PROJECT_DIR="main"
```

### 1.2 一键启动与停止

```bash
cd "$PROJECT_DIR/ops"
./start-all.sh
```

默认启动主服务：
- PostgreSQL
- Elasticsearch
- Redis
- Backend API
- Celery Worker

停止：

```bash
cd "$PROJECT_DIR/ops"
./stop-all.sh
```

重启：

```bash
cd "$PROJECT_DIR/ops"
./restart.sh
```

### 1.3 启动机制（关键点）

- 启动顺序：数据库服务 -> Backend -> Celery Worker。
- Backend 启动脚本包含依赖等待和失败即停策略（fail-fast）。
- 自动执行数据库迁移：`alembic upgrade head`。
- 容器健康检查默认已启用（PostgreSQL / Elasticsearch / Backend）。

### 1.4 常用排障命令

```bash
cd "$PROJECT_DIR/ops"
docker-compose ps
docker-compose logs -f backend
docker-compose logs -f celery-worker
docker-compose exec backend alembic current
docker-compose exec backend alembic history
```

## 2. 前端（frontend-modern）

### 2.1 本地开发

```bash
cd main/frontend-modern
npm install
VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
```

- 本地开发时，`/api/*` 代理到 `VITE_API_PROXY_TARGET`（默认 `http://localhost:8000`）。

### 2.2 Docker 运行

```bash
cd main/frontend-modern
docker build -t market-frontend-modern .
docker run --rm -p 5174:80 --network <your-compose-network> market-frontend-modern
```

- 容器内 Nginx 将 `/api/*` 反向代理到 `http://backend:8000`。
- 默认建议不设置 `VITE_API_BASE_URL`，前端继续走同源 `/api/*`。

### 2.3 Compose 集成

```bash
docker compose -f main/ops/docker-compose.yml --profile modern-ui up -d frontend-modern
```

- 默认设置下（backend 已配置 `MODERN_FRONTEND_URL=http://localhost:5174`），访问 `http://localhost:8000/`、`/app`、`/app.html` 会重定向到 modern 前端。

### 2.4 核心 API 对齐（P0）

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

接口契约建议遵循统一 envelope：`status / data / error / meta`。

## 3. Figma 同步（frontend-modern）

### 3.1 已拉取并落地

- Source file: `1IGWKEkcI40MUEAW4HJyv3`
- Root node: `427:6918`
- 已落地组件：
  - Top nav（light）：`461:24152` -> `src/components/FigmaTopNav.tsx`
  - Side nav（light）：`1186:27288` -> `src/components/FigmaSideNav.tsx`
- 主题变体（本地 token 生成）：`dark`、`brand`
- 已应用文件：
  - `src/components/FigmaTopNav.tsx`
  - `src/components/FigmaSideNav.tsx`
  - `src/index.css`
  - `src/App.tsx`（默认 dark）

### 3.2 阻塞与待办

- 当前阻塞：Figma MCP 调用额度限制（plan limit）。
- 待补拉节点：
  - Top nav dark：`664:26504`
  - Top nav brand：`664:28359`
  - Side nav dark：`1186:27299`
  - Side nav brand：`1186:27310`
- 额度恢复后，按 node-by-node 继续拉取并追加状态记录。

## 4. 快速启动（最短路径）

```bash
export PROJECT_DIR="main"
cd "$PROJECT_DIR/ops"
./start-all.sh
```

启动成功后访问：
- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/v1/health>
- Modern 前端（若启用）：<http://localhost:5174>

停止：

```bash
cd "$PROJECT_DIR/ops"
./stop-all.sh
```

## 5. 参考文档

- `./ops-README.md`
- `./frontend-modern-README.md`
- `./frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md`
- `./QUICKSTART.md`
