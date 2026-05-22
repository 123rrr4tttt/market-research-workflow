# Ops + Frontend 合并草案

> 文档日期: 2026-05-22
> 范围: 部署、前端、Figma 同步、快速启动  
> 来源: `ops-README.md`、`frontend-modern-README.md`、`frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md`、`QUICKSTART.md`、`automation-runs/storybook-launcher-gates/2026-05-22/README.md`

## 1. 部署（Launcher-first / Docker-first）

### 1.1 推荐入口与约定

- 推荐从仓库根目录使用平台脚本，而非日常直接使用 `docker compose`：
  - `bash scripts/platform-macos.sh docker-start`：启动 Docker Web Launcher。
  - `bash scripts/platform-macos.sh docker-status`：只读查看 Docker 应用服务状态。
  - `bash scripts/platform-macos.sh docker-full-start`：直接启动完整 modern-ui 栈。
  - `bash scripts/platform-macos.sh docker-stop|docker-restart`：停止或重启 Docker 应用服务。
  - `bash scripts/platform-macos.sh local-start|local-stop|status|health`：本地非 Docker 路径。
  - 仓库根目录 `./scripts/docker-deploy.sh start|stop|restart|status|logs|health|preflight` 仍可作为底层部署入口。
- 首次运行需确保 `main/backend/.env` 存在（可由 `.env.example` 复制）。
- `main/ops/start-all.sh`、`stop-all.sh`、`restart.sh` 保留为兼容路径，但不再是快速启动首选入口。

### 1.2 一键启动与停止

```bash
bash scripts/platform-macos.sh docker-start
```

默认启动 Docker Web Launcher，随后可在 Launcher 中选择启动或管理完整应用栈。直接启动完整 modern-ui 栈可运行：

```bash
bash scripts/platform-macos.sh docker-full-start
```

停止：

```bash
bash scripts/platform-macos.sh docker-stop
```

重启：

```bash
bash scripts/platform-macos.sh docker-restart
```

### 1.3 完整栈启动机制（关键点）

- 启动顺序：数据库服务 -> Backend -> Celery Worker。
- Backend 启动脚本包含依赖等待和失败即停策略（fail-fast）。
- 自动执行数据库迁移：`alembic upgrade head`。
- 容器健康检查默认已启用（PostgreSQL / Elasticsearch / Backend）。

### 1.4 常用排障命令

```bash
cd main/ops
docker compose ps
docker compose logs -f backend
docker compose logs -f celery-worker
docker compose exec backend alembic current
docker compose exec backend alembic history
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
- `POST /api/v1/ingest/data-api`
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
bash scripts/platform-macos.sh docker-start
```

启动成功后访问：
- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/v1/health>
- Modern 前端（若启用）：<http://localhost:5174>
- Docker Web Launcher：<http://127.0.0.1:5176>

停止：

```bash
bash scripts/platform-macos.sh docker-stop
```

## 5. 参考文档

- `./ops-README.md`
- `./frontend-modern-README.md`
- `./frontend-modern-figma-sync-PULL_STATUS_2026-02-27.md`
- `./QUICKSTART.md`

## 6. 当前封口快照（2026-05-22）

详见 [F_PLAN/INDEX.md](../F_PLAN/INDEX.md)。

| Track | 当前状态 | 下一轮门禁 |
| --- | --- | --- |
| Graph rendering and interaction | `需更新` | `npm run test:e2e -- tests/e2e/graphpage.spec.ts`，并补 graph lint/screenshot 证据 |
| Frontend API facade and graph query keys | `需更新` | API/query-key 目标文件 lint，依赖可用后跑 `npm run build` |
| Storybook and Storybook MCP | `已封口` | 2026-05-22 已通过 `npm --prefix main/frontend-modern run storybook:build` 与 `/mcp` HEAD 端点验证 |
| Launcher-first ops flow | `已封口` | 2026-05-22 已通过只读 dry-run gate 与 `bash scripts/platform-macos.sh docker-status`；app bundle build 仍留给显式 packaging lane |

本快照回写 ops-frontend 文档状态，并新增只读 launcher dry-run gate；未改 backend 或 frontend 运行时代码。
