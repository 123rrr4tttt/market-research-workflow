# 市场情报（market-intel）项目说明

> 最后更新：2026-02-27  
> 当前版本：`v0.1.7-rc1`（预发布，团队联调）

本仓库实现一体化信息工作流：多来源采集 -> 结构化处理 -> 索引检索 -> 可视化与运维管理。  
适用于政策、市场、新闻、社媒等主题的数据采集与分析。

## 1. 项目总览

- 后端：`FastAPI + SQLAlchemy + Alembic + Celery + Redis + Elasticsearch`
- 数据库：`PostgreSQL + pgvector`
- 前端：
  - `main/frontend`：旧版模板前端（Jinja/静态页面）
  - `main/frontend-modern`：新版 React + Vite + TypeScript
- 首选运行方式：Docker（首选脚本：`./scripts/docker-deploy.sh`）
- 多项目隔离：按 `project_<key>` schema 进行业务数据隔离

## 2. 快速开始（首选 Docker）

### 2.1 首次准备

```bash
cp main/backend/.env.example main/backend/.env
```

### 2.2 可部署性检查（推荐先执行）

```bash
./scripts/docker-deploy.sh preflight
```

### 2.3 一键启动（首选）

```bash
./scripts/docker-deploy.sh start
```

### 2.4 常用运维命令（首选）

```bash
# 启动/停止/重启
./scripts/docker-deploy.sh start
./scripts/docker-deploy.sh stop
./scripts/docker-deploy.sh restart

# 预检查 / 状态 / 日志 / 健康检查
./scripts/docker-deploy.sh preflight
./scripts/docker-deploy.sh status
./scripts/docker-deploy.sh logs -f backend
./scripts/docker-deploy.sh health
```

参数能力（统一透传给底层脚本）：
- `--non-interactive`：非交互模式，适合 CI/自动化
- `--force`：强制执行清理/重启流程（不删除数据卷）
- `--profile <name>`：按 compose profile 启动（例如 `modern-ui`）
- `services...`：按服务维度查看状态/日志（例如 `status backend redis`、`logs -f celery-worker`）

示例：

```bash
./scripts/docker-deploy.sh start --non-interactive --force --profile modern-ui
./scripts/docker-deploy.sh status backend redis
./scripts/docker-deploy.sh logs -f celery-worker
```

### 2.5 常用访问地址

- OpenAPI：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/v1/health`
- 深度健康检查：`http://localhost:8000/api/v1/health/deep`
- 管理入口：`http://localhost:8000/resource-pool-management.html`

本地（非 Docker）模式仅用于开发调试，生产与联调默认按 Docker 链路执行。

### 2.6 脚本收敛（主入口 2 个）

当前统一为两个主入口：
- Docker 链路：`./scripts/docker-deploy.sh`
- 纯本地链路：`./scripts/local-deploy.sh`

平台脚本（`platform-macos/linux/windows`）现在只代理纯本地链路，不再混用 Docker 子命令。

`local-deploy.sh` 子命令：
- `start`：纯本地启动（后端 + modern 前端）
- `stop`：纯本地停止
- `restart`：纯本地重启
- `status`：本地端口状态检查（8000/5173）
- `health`：检查本地后端健康接口

macOS：

```bash
./scripts/platform-macos.sh start
./scripts/platform-macos.sh stop
./scripts/platform-macos.sh restart
./scripts/platform-macos.sh status
./scripts/platform-macos.sh health
./scripts/platform-macos.sh local-start
./scripts/platform-macos.sh local-stop
```

macOS `local-start` 说明（当前默认）：
- 一键启动本机后端 + modern 前端（`127.0.0.1:8000` / `127.0.0.1:5173`）
- 默认纯本机依赖，不自动拉起 Docker `db/es/redis`
- 会自动检查并尝试启动本机 PostgreSQL（Homebrew service）
- 会自动创建后端虚拟环境 `.venv311` 并按 `requirements.txt` 安装/更新依赖
- 当前本机库建议使用：`market_intel_local`（见 `main/backend/.env` 的 `DATABASE_URL`）
- 若要改用 Docker 依赖：`cd main/backend && ./start-local.sh --with-docker-deps`

Linux：

```bash
./scripts/platform-linux.sh start
./scripts/platform-linux.sh stop
./scripts/platform-linux.sh restart
./scripts/platform-linux.sh status
./scripts/platform-linux.sh health
./scripts/platform-linux.sh local-start
./scripts/platform-linux.sh local-stop
```

Windows（PowerShell，自动尝试 Git Bash/WSL）：

```powershell
.\scripts\platform-windows.ps1 start
.\scripts\platform-windows.ps1 stop
.\scripts\platform-windows.ps1 restart
.\scripts\platform-windows.ps1 status
.\scripts\platform-windows.ps1 health
.\scripts\platform-windows.ps1 local-start
.\scripts\platform-windows.ps1 local-stop
```

## 3. 运行拓扑

默认容器服务（`main/ops/docker-compose.yml`）：

- `db`（PostgreSQL）:`5432`
- `es`（Elasticsearch）:`9200`
- `redis`:`6379`
- `backend`（FastAPI）:`8000`
- `celery-worker`（异步任务）
- `frontend-modern`（可选 profile：`modern-ui`）:`5174`

后端核心环境变量：

- `DATABASE_URL`
- `ES_URL`
- `REDIS_URL`
- `MODERN_FRONTEND_URL`（启用新前端重定向）

## 4. 前端入口与迁移关系

- 默认情况下，访问 `/`、`/app`、`/app.html` 会重定向到新版前端（优先使用 `MODERN_FRONTEND_URL`；未配置时默认 `http://127.0.0.1:5173`）。
- 旧版页面可通过 `?legacy=1` 回退访问。
- 本地开发新版前端：

```bash
cd main/frontend-modern
npm install
VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
```

- 访问：`http://localhost:5173`

## 5. 仓库结构与职责

```text
<repo-root>/
├── README.md                     # 项目主说明
├── GIT_WORKFLOW.md               # 协作规范
├── 信息源库/                     # 运行时来源配置库（global + projects）
├── 信息流优化/                   # 优化路线与阶段规划
├── reference_pool/               # 调研与参考资料库
└── main/
    ├── QUICKSTART.md             # 快速启动
    ├── ops/                      # Docker 编排与运维脚本
    ├── backend/                  # FastAPI 服务、模型、迁移、测试
    ├── frontend/                 # 旧版模板前端
    └── frontend-modern/          # 新版 React 前端
```

## 6. 后端架构（`main/backend`）

### 6.1 API 层

统一前缀：`/api/v1`。主要分组：

- `ingest`：采集与配置
- `search`：检索与索引初始化
- `resource_pool`：资源池抽取、站点入口、统一搜索
- `source_library`：来源库条目与执行
- `projects` / `project-customization`：项目管理与定制
- `dashboard` / `admin` / `process`：运营与任务管理

### 6.2 服务层

`main/backend/app/services` 关键模块：

- `ingest/`：政策、市场、新闻、社媒等采集
- `search/`：Web 检索、ES 检索、混合检索
- `resource_pool/`：URL 提取、站点入口发现、候选写回
- `source_library/`：来源条目解析、路由、执行、同步
- `collect_runtime/`：统一采集运行时与适配器执行
- `indexer/`：文本处理与索引写入
- `tasks.py`：Celery 异步任务

### 6.3 数据层与迁移

- ORM：`main/backend/app/models/entities.py`
- 迁移：`main/backend/migrations/versions/*`
- 策略：
  - `public`：共享与控制平面（如 shared_*、部分全局配置）
  - `project_<key>`：项目隔离业务数据
- 启动时会自动执行：`alembic upgrade head`

## 7. 核心数据流

### 7.1 采集流（Ingest）

输入任务 -> `ingest/*` / `collect_runtime/*` -> 落库 -> `indexer/*` -> 可检索。

### 7.2 检索流（Search）

`search` API -> ES/DB（bm25/vector/hybrid）-> 返回标准化结果。

### 7.3 来源库流（Source Library）

条目配置（global/project）-> handler 路由与适配器执行 -> 采集结果落库/索引。

### 7.4 资源池流（Resource Pool）

从文档/任务提取 URL -> 发现 site entries -> 统一搜索扩展候选 -> 写回资源池 -> 可触发后续入库。

## 8. API 快速验证

```bash
BASE=http://localhost:8000/api/v1

curl "$BASE/health"
curl "$BASE/health/deep"
curl "$BASE/search?q=lottery&top_k=5"
curl "$BASE/projects"
```

带项目上下文示例：

```bash
curl "$BASE/source_library/items?project_key=demo_proj&scope=effective"
curl "$BASE/resource_pool/urls?project_key=demo_proj&scope=effective&page=1&page_size=20"
```

说明：部分接口要求 `project_key` 参数或 `X-Project-Key` 请求头。

## 9. 运维与排障

常用命令：

```bash
cd main/ops
docker-compose ps
docker-compose logs -f backend
docker-compose logs -f celery-worker
```

端口排查：

```bash
lsof -i :8000
lsof -i :5432
lsof -i :9200
lsof -i :6379
```

快速自检：

```bash
cd main/ops
./test-docker-startup.sh
```

## 10. 演示数据

- SQL 数据包：`main/backend/seed_data/project_demo_proj_v0.1.7-rc1.sql`
- 导入脚本：`main/backend/scripts/load_demo_proj_seed.sh`
- 前端静态下载：
  - `/static/demo/project_demo_proj_v0.1.7-rc1.sql`
  - `/static/demo/load_demo_proj_seed.sh`

## 11. 文档导航

- 快速启动：`main/QUICKSTART.md`
- Docker 运维：`main/ops/README.md`
- 后端说明：`main/backend/README.md`
- 本地开发：`main/backend/README.local.md`
- API 总文档：`main/backend/API接口文档.md`
- API 路由清单：`main/backend/docs/API_ROUTE_INVENTORY_2026-02-27.md`
- 后端文档索引：`main/backend/docs/README.md`
- 资源库定义：`main/backend/docs/RESOURCE_LIBRARY_DEFINITION.md`
- 资源池 API：`main/backend/docs/RESOURCE_POOL_EXTRACTION_API.md`
- 前端迁移契约：`main/backend/docs/FRONTEND_MODERNIZATION_API_MAP_2026-02-27.md`
- 迭代计划：`plans/status-8x-2026-02-27.md`
- 版本说明：`RELEASE_NOTES_pre-release-1.7.md`

## 12. 当前已知风险（供联调参考）

- 新旧前端并行，功能存在重叠，迁移仍在进行中。
- `resource_pool` 路由存在下划线/连字符兼容写法，建议逐步统一。
- 部分接口仍处于响应风格过渡期（Envelope 统一尚未完全收口）。
- 异步任务依赖 Celery/Redis，排查问题需结合 worker 日志。
- 外部搜索/社媒/LLM 供应商能力受 API Key 与配额影响。

## 13. 协作规范

代码协作与分支策略见：`GIT_WORKFLOW.md`
