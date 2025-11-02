# 本地开发环境配置指南

## 快速开始

### 1. 环境配置

#### 方式一：使用 .env.local 文件（推荐）

```bash
# 复制示例配置文件
cp .env.local.example .env.local

# 编辑配置文件，设置本地服务地址
# DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/postgres
# ES_URL=http://localhost:9200
# REDIS_URL=redis://localhost:6379/0
```

#### 方式二：使用环境变量

```bash
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"
export ES_URL="http://localhost:9200"
export REDIS_URL="redis://localhost:6379/0"
```

### 2. 启动依赖服务

#### 自动启动（推荐）

使用 `start-local.sh` 脚本会自动检查并启动数据库服务，无需手动操作。

#### 手动启动（可选）

如果本地已安装PostgreSQL、Elasticsearch和Redis，可以跳过此步骤。

```bash
# 从项目根目录运行
cd ../../ops
docker-compose up -d db es redis
```

这将启动：
- PostgreSQL (端口 5432)
- Elasticsearch (端口 9200)
- Redis (端口 6379)

### 3. 启动后端服务

#### 方式一：使用启动脚本（推荐，自动启动数据库服务）

```bash
# 一键启动（会自动检查并启动数据库服务）
./start-local.sh

# 停止服务（包括数据库服务）
./stop-local.sh
```

启动脚本会自动：
- ✅ 检查并启动数据库服务（PostgreSQL, Elasticsearch, Redis）
- ✅ 等待服务就绪后再启动后端
- ✅ 检查端口占用并提示处理
- ✅ 如果Docker未运行，会跳过数据库服务启动并给出提示

#### 方式二：手动启动

```bash
# 激活虚拟环境
source .venv311/bin/activate

# 启动服务（自动重载）
uvicorn app.main:app --reload --port 8000
```

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
cd ../../ops
docker-compose up -d
```

这将在Docker容器中运行所有服务，自动使用容器网络配置。

