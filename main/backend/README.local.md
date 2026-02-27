# 本地开发环境配置指南

> 最后更新：2026-02 | 首次运行请复制 `.env.example` 为 `.env`

## 快速开始

### 1. 环境配置

#### 方式一：使用 .env 文件（推荐）

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑 .env，设置本地服务地址（可选，有默认值）
# DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/market_intel_local
# ES_URL=http://localhost:9200
# REDIS_URL=redis://localhost:6379/0
```

#### 方式二：使用环境变量

```bash
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/market_intel_local"
export ES_URL="http://localhost:9200"
export REDIS_URL="redis://localhost:6379/0"
```

### 2. 启动依赖服务

#### 自动启动（推荐）

使用 `start-local.sh` 脚本会自动准备 Python 虚拟环境与依赖，并启动本地开发服务。

#### 手动启动（可选）

如果本地已安装PostgreSQL、Elasticsearch和Redis，可以跳过此步骤。

```bash
# 从 backend 目录运行（项目内独立入口）
cd ../ops
docker-compose up -d db es redis
```

这将启动：
- PostgreSQL (端口 5432)
- Elasticsearch (端口 9200)
- Redis (端口 6379)

### 3. 启动本地全量开发服务

#### 方式一：使用启动脚本（推荐，默认纯本机依赖 + modern 前端）

```bash
# 一键启动（纯本机依赖模式，不触发 Docker db/es/redis）
./start-local.sh

# 低内存模式启动（关闭自动重载）
./start-local.sh --low-memory

# 非交互模式（适合自动化）
./start-local.sh --non-interactive

# 强制模式（端口冲突时自动处理并继续）
./start-local.sh --force

# 需要 Docker 托管依赖时（可选）
./start-local.sh --with-docker-deps

# 停止服务（后端 + modern 前端，可选停止数据库服务）
./stop-local.sh

# 停止服务并同时停止 Docker db/es/redis（可选）
./stop-local.sh --with-docker-deps
```

启动脚本会自动：
- ✅ 自动创建 `.venv311`（若不存在）并按 `requirements.txt` 安装依赖（按哈希变更增量更新）
- ✅ 默认纯本机模式，不自动操作 Docker 依赖服务
- ✅ 启动 modern 前端开发服务（默认端口 5173）
- ✅ 自动检测并尝试拉起本机 PostgreSQL（默认 `localhost:5432`，优先 Homebrew service）
- ✅ 自动检测并尝试拉起本机 Redis（默认 `localhost:6379`，优先 Homebrew service）
- ✅ 检查端口占用并提示处理
- ✅ 需要时可通过 `--with-docker-deps` 启动 Docker 依赖
- ✅ 支持低内存模式（`--low-memory` 或 `DEV_RELOAD=0`）
- ✅ 默认同时启动本机 Celery worker（异步任务可直接消费）
- ✅ 可用 `--no-local-worker` 关闭本机 worker 启动

与一键 Docker 入口（仓库根目录）配合时：
- `./scripts/docker-deploy.sh start --non-interactive --force`：用于非交互/强制执行链路
- `./scripts/docker-deploy.sh start --profile <name>`：按 compose profile 启动
- `./scripts/docker-deploy.sh status <services...>`、`logs -f <services...>`：按服务维度排查
- `./scripts/docker-deploy.sh preflight|health`：启动前检查与健康检查
- `./scripts/docker-deploy.sh stop`（内部 `stop-all.sh`）默认保留数据卷；清空数据需显式 `docker compose down -v`

纯本地统一入口（仓库根目录）：
- `./scripts/local-deploy.sh start|stop|restart|status|health`
- `./scripts/local-deploy.sh start`（默认一键启动 backend + frontend + worker）
- `./scripts/local-deploy.sh stop`（默认一键停止并回收 worker）
- `./scripts/platform-macos.sh start|stop|restart|status|health`（等价代理）

#### 方式二：手动启动

```bash
# 激活虚拟环境
source .venv311/bin/activate

# 启动服务（自动重载）
uvicorn app.main:app --reload --port 8000

# 低内存启动（不使用重载）
uvicorn app.main:app --port 8000
```

### 低内存参数（Docker Compose）

`ops/docker-compose.yml` 支持以下环境变量（未设置时使用默认值）：

- `ES_JAVA_OPTS`（默认 `-Xms512m -Xmx512m`）
- `CELERY_LOG_LEVEL`（默认 `info`）
- `CELERY_CONCURRENCY`（Docker 默认 `1`；本机 `start-local.sh` 默认 `3`）
- `CELERY_PREFETCH_MULTIPLIER`（Docker 默认 `1`；本机默认 `2`）
- `CELERY_MAX_TASKS_PER_CHILD`（Docker 默认 `50`；本机默认 `100`）
- `CELERY_MAX_MEMORY_PER_CHILD`（Docker 默认 `300000`，单位 KiB；本机默认 `500000`）
- `CELERY_QUEUES`（仅本机 `start-local.sh` 使用，默认 `celery`）
- `GRAPH_STRUCTURED_ASYNC_DISPATCH_WORKERS`（默认 `4`，`/ingest/graph/structured-search` 异步批量入队并发度）

`start-local.sh` 启动的本机 Celery worker 也会读取以上同名环境变量，便于本机与 Docker 参数一致、快速回滚。

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8000/api/v1/health

# 深度健康检查（检查数据库和ES连接）
curl http://localhost:8000/api/v1/health/deep
```

## 配置说明

### 自动环境检测

系统会自动检测运行环境：
- **Docker环境**：如果检测到 `/.dockerenv` 文件或 `DOCKER_ENV=true`，使用容器主机名（db, es, redis）
- **本地环境**：否则使用 localhost

### 手动覆盖

即使自动检测，你也可以通过 `.env` 文件或环境变量手动覆盖配置。

## 常见问题

### 数据库连接失败

如果遇到数据库连接超时：
1. 确认PostgreSQL服务是否运行：`pg_isready` 或 `docker ps | grep postgres`
2. 检查端口是否正确：默认5432
3. 确认连接字符串中的用户名、密码、数据库名是否正确

### Elasticsearch连接失败

1. 确认ES服务是否运行：`curl http://localhost:9200`
2. 如果使用Docker：`docker ps | grep elasticsearch`
3. 检查防火墙设置

### 端口冲突

如果8000端口被占用：
```bash
# 查看占用端口的进程
lsof -i:8000

# 或使用其他端口启动
uvicorn app.main:app --reload --port 8001
```

## Docker完整部署

如果要使用Docker完整部署（包括后端服务）：

```bash
cd ../ops
docker-compose up -d
```

这将在Docker容器中运行所有服务，自动使用容器网络配置。
