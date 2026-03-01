# Docker 启动指南

> 最后更新：2026-02 | 首次运行请确保 `../backend/.env` 存在（可复制 `.env.example`）

## ⚠️ 重要提示

**本项目使用统一的容器启动脚本，这是启动所有服务的唯一方式。**

请使用 `start-all.sh` 脚本启动所有服务，不要使用其他方式启动单个服务。

> 团队协作约定：所有命令以仓库根目录为当前目录执行。
>
> ```bash
> export PROJECT_DIR="main"
> ```

## 快速启动

### 统一入口（推荐）

优先在仓库根目录使用：

```bash
./scripts/docker-deploy.sh preflight
./scripts/docker-deploy.sh start --non-interactive --force
./scripts/docker-deploy.sh status
./scripts/docker-deploy.sh logs -f backend
./scripts/docker-deploy.sh health
./scripts/docker-deploy.sh stop
```

参数说明（用于一键脚本）：
- `--non-interactive`：非交互执行，适合 CI/自动化环境
- `--force`：强制清理并继续执行（不删除数据卷）
- `--profile <name>`：按 compose profile 启动
- `services...`：按服务范围查看状态/日志（如 `status backend redis`、`logs -f celery-worker`）

说明：平台入口（macOS/Linux/Windows）现仅用于纯本地链路（`local-deploy.sh` 代理），
Docker 运维请统一使用 `./scripts/docker-deploy.sh`。

### 统一启动（唯一推荐方式）

```bash
# 启动所有服务（独立项目全量服务）
cd "$PROJECT_DIR/ops"
./start-all.sh
```

这将自动启动：
- ✅ **主服务**：PostgreSQL, Elasticsearch, Redis, Backend API, Celery Worker

### 停止所有服务

```bash
# 停止所有服务
cd "$PROJECT_DIR/ops"
./stop-all.sh
```

`stop-all.sh` 清理策略：
- 默认执行 `docker compose down`：停止并移除容器/网络，保留数据卷
- 不会默认删除卷，避免误删数据
- 若确需清空数据，手动执行 `docker compose down -v`

### 查看服务状态

```bash
# 查看主服务状态
cd "$PROJECT_DIR/ops"
docker-compose ps
```

### 查看日志

```bash
# 查看主服务日志
cd "$PROJECT_DIR/ops"
docker-compose logs -f backend
```

## 启动流程说明

### 1. 服务启动顺序

Docker Compose 会按以下顺序启动服务：

1. **数据库服务**（PostgreSQL、Elasticsearch、Redis）
   - 等待健康检查通过
   - PostgreSQL: 使用 `pg_isready` 检查
   - Elasticsearch: 使用 `/_cluster/health` 检查

2. **后端服务**（Backend）
   - 等待数据库服务健康检查通过
   - 执行启动脚本 (`docker-entrypoint.sh`)：
     - ✅ 等待 PostgreSQL 就绪（最多30次重试）
     - ✅ 等待 Elasticsearch 就绪（最多30次重试）
     - ✅ 等待 Redis 就绪（最多30次重试）
     - ✅ 运行数据库迁移 (`alembic upgrade head`)
     - ✅ 启动 FastAPI 应用

3. **Celery Worker**（可选）
   - 等待后端服务健康检查通过
   - 启动 Celery Worker 处理异步任务

### 2. 健康检查

所有服务都配置了健康检查：

- **PostgreSQL**: 每5秒检查一次
- **Elasticsearch**: 每10秒检查一次（启动等待期30秒）
- **Backend**: 每30秒检查一次（启动等待期40秒）

### 3. 数据库迁移

启动脚本会自动运行数据库迁移：

```bash
alembic upgrade head
```

如果迁移失败（例如数据库未初始化），会记录警告但继续启动。

## 常见问题排查

### 1. 服务启动失败

**检查服务日志：**
```bash
# 查看所有服务日志
docker-compose logs

# 查看特定服务日志
docker-compose logs backend
docker-compose logs db
docker-compose logs es
```

**检查服务状态：**
```bash
docker-compose ps
```

### 2. 数据库连接失败

**问题：** Backend 无法连接到数据库

**排查步骤：**
1. 检查 PostgreSQL 是否健康：
   ```bash
   docker-compose exec db pg_isready -U postgres
   ```

2. 检查网络连接：
   ```bash
   docker-compose exec backend ping db
   ```

3. 检查环境变量：
   ```bash
   docker-compose exec backend env | grep DATABASE_URL
   ```

### 3. Elasticsearch 连接失败

**问题：** Backend 无法连接到 Elasticsearch

**排查步骤：**
1. 检查 Elasticsearch 是否健康：
   ```bash
   curl http://localhost:9200/_cluster/health
   ```

2. 检查容器内连接：
   ```bash
   docker-compose exec backend curl http://es:9200
   ```

### 4. 数据库迁移失败

**问题：** 迁移脚本执行失败

**手动运行迁移：**
```bash
docker-compose exec backend alembic upgrade head
```

**查看迁移历史：**
```bash
docker-compose exec backend alembic current
docker-compose exec backend alembic history
```

### 5. Celery Worker 未启动

**问题：** 异步任务无法执行

**解决方案：**
Celery Worker 现在会默认自动启动（已移除 profile 限制）。如果未启动，请检查：

```bash
# 查看 Worker 状态
cd "$PROJECT_DIR/ops"
docker-compose ps celery-worker

# 查看 Worker 日志
docker-compose logs -f celery-worker

# 手动启动 Worker（如果需要）
docker-compose up -d celery-worker

# 重启 Worker
docker-compose restart celery-worker
```

**注意：** Worker 已配置自动重启策略（`restart: unless-stopped`），如果崩溃会自动重启。

### 6. 端口冲突

**问题：** 端口已被占用

**检查端口占用：**
```bash
# 检查8000端口
lsof -i :8000

# 检查5432端口（PostgreSQL）
lsof -i :5432

# 检查9200端口（Elasticsearch）
lsof -i :9200
```

**解决方案：**
- 停止占用端口的进程
- 或修改 `docker-compose.yml` 中的端口映射

## 服务访问

启动成功后，可以通过以下地址访问：

### 主服务
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/api/v1/health
- **深度健康检查**: http://localhost:8000/api/v1/health/deep
- **PostgreSQL**: localhost:5432
- **Elasticsearch**: http://localhost:9200
- **Redis**: localhost:6379

## 停止服务

**推荐使用统一停止脚本：**

```bash
# 停止所有服务（推荐）
cd "$PROJECT_DIR/ops"
./stop-all.sh
```

**手动停止（不推荐）：**

```bash
# 停止主服务
cd "$PROJECT_DIR/ops"
docker-compose down

# 停止服务但保留数据卷
docker-compose stop

# 停止服务并删除数据卷（⚠️ 会删除所有数据）
docker-compose down -v
```

## 重建服务

```bash
# 重新构建并启动
docker-compose up -d --build

# 强制重新构建（不使用缓存）
docker-compose build --no-cache
docker-compose up -d
```

## 环境变量配置

可以通过 `.env` 文件或环境变量配置服务：

```bash
# 在 docker-compose.yml 所在目录创建 .env 文件
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/postgres
ES_URL=http://es:9200
REDIS_URL=redis://redis:6379/0
```

## 开发模式

开发模式下，代码变更会自动重载（通过 volume 挂载）：

```bash
# 启动服务
docker-compose up

# 代码修改后会自动重载（需要重启容器）
docker-compose restart backend
```

## 生产部署建议

1. **移除 volume 挂载**：生产环境不应挂载源代码目录
2. **配置环境变量**：使用 `.env` 文件或环境变量管理配置
3. **启用 Celery Worker**：确保异步任务可以正常处理
4. **配置日志**：设置日志轮转和集中日志管理
5. **资源限制**：为服务设置适当的资源限制（CPU、内存）
6. **安全配置**：使用强密码、启用 TLS 等
