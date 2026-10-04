# 本地与容器运行入口

## 本机日常运行

当前宿主日常链路由业务前端、后端 API、Codex WebUI、launchd 管理的 Celery worker 和
Elasticsearch 组成。访问地址为前端 <http://127.0.0.1:5173>、API
<http://127.0.0.1:8000/docs>、Codex WebUI <http://127.0.0.1:8172>。OAuth 身份由宿主
`~/.codex/auth.json` 共享给 WebUI；WebUI home 是 `~/.codex-mrw-agent`，并通过共享
symlink 读取宿主身份。当前全链路证据见
[`.data/readiness-repair/20261004-daily-chain/daily-chain-state.json`](../../.data/readiness-repair/20261004-daily-chain/daily-chain-state.json)。结构整理后的服务重载、正式worker材料链和WebUI浏览器读回见
[结构整理实施结果](../../docs/development/MRW结构整理方案与分发包.md#8-实际实施进度)。

### Codex WebUI 生命周期

当前服务来自 [vendored README](./codex-webui/README.md) 所描述的主仓副本，运行主程序为
`main/ops/codex-webui/dist/main.js`，协议依赖固定为 `@openai/codex@0.160.0`。原 SQLite
数据已完整迁入 `main/ops/codex-webui/.tmp`；宿主 LaunchAgent 指向主仓路径，
`com.mrw.codex-webui` 的认证 symlink 仍共享宿主 `~/.codex/auth.json`。

启动时由已有私密配置提供 `WEBUI_API_KEY`；不要打印、记录或提交该密钥：

```bash
./main/ops/codex-webui/start.sh
```

停止同一 LaunchAgent：

```bash
./main/ops/codex-webui/stop.sh
```

构建、版本校验、认证 symlink、数据库路径和 LaunchAgent 生成的完整说明见
[`./codex-webui/README.md`](./codex-webui/README.md)。

本机状态与健康检查：

```bash
./scripts/local-deploy.sh status
./scripts/local-deploy.sh health
```

分面控制使用既有入口：

```bash
./scripts/local-service-control.sh frontend-start
./scripts/local-service-control.sh worker-start
./scripts/local-service-control.sh backend-start
```

## Compose 隔离本地用户环境（2026-09-21）

这个模式用于容器边界下的本地用户验证，不是当前宿主 daily 默认叙述。本机可使用此前
生产部署验证保留的 backend 镜像与当前源码只读挂载启动用户界面，无需重建镜像。
这不是冻结候选的 exact-byte replay，也不是生产部署。Compose project 固定为
`mrw-local-user`；数据保存在该 project 的独立命名卷中，不使用宿主 PostgreSQL/Redis。

在仓库根目录执行：

```bash
# 首次启动或前端修改后构建；纯重启无需重复。
npm --prefix main/frontend-modern run build

docker compose -p mrw-local-user \
  -f main/ops/docker-compose.yml -f main/ops/docker-compose.local-user.yml \
  --profile modern-ui up -d --no-build --pull never \
  db es redis backend celery-worker frontend-modern
```

界面为 <http://127.0.0.1:15132/>，API 为 <http://127.0.0.1:18132/docs>，仅绑定 loopback。
只有列出的六个服务被启动，不包含 launcher、scrapyd 或搜索增强服务。
源码依赖使用 `pyproject.toml` 已声明的 sibling `Desktop/functorial-kit/python`；
可用 `MRW_FUNCTORIAL_KIT_PATH` 指定其他已有 checkout。当前源码需要其中的
`functorial_kit.contributions`，保留镜像自带旧 wheel 不具备此模块。
backend 同时挂载当前 `app`、`migrations`、`llm_prompts`、`src` 与 `seed_data`；
worker 使用同一 `app/src/kit`，前端使用当前 `dist`。修改普通 API Python 后重启 backend；修改 Celery task 定义或注册时重启 backend 和 `celery-worker`，避免 worker 保留旧注册清单：

```bash
docker compose -p mrw-local-user \
  -f main/ops/docker-compose.yml -f main/ops/docker-compose.local-user.yml \
  restart backend celery-worker
```

此配置不读取宿主 `.env`，不注入 provider key 或 Codex 登录文件。默认 dev 模式没有普通账号登录要求；
Codex OAuth、模型、外部检索与网页采集未验证。不要把页面显示的 `missing/login` 当成已配置。

停止并保留所有本地数据：

```bash
docker compose -p mrw-local-user \
  -f main/ops/docker-compose.yml -f main/ops/docker-compose.local-user.yml \
  --profile modern-ui stop db es redis backend celery-worker frontend-modern
```

重新执行上述 `up` 恢复。不要使用 `down -v` 或全局 prune。日志可从
`docker compose` 同样参数的 `logs backend celery-worker` 读取，worker 文件日志也由任务详情页读取。

已注入的演示项目是 `local_demo_20260921`：通过产品 `POST /api/v1/projects/inject-initial`
从 `seed_data/project_demo_proj_v0.9-rc2.0.sql` 复制 75 条文档、6 条来源；`overwrite=false`，
没有复制 seed 内的历史 ETL 任务。当前 URL 池的 267 条链接由本次页面“提取 URL”提交的真实
Celery 任务产生。用户操作：项目管理切换该项目 → 管理/提取 → 提取 URL → 任务详情查看
`SUCCESS` 与 result → 返回提取页刷新列表。提取仅扫描已入库文档，不访问链接目标。
重复提取使用已有去重逻辑，不重复新增相同链接。

原始数据导入接口的 `async_mode=true` 使用 Celery task
`app.services.tasks.task_raw_import_documents`；可通过 Process 详情读回任务结果，再从文档列表检索新记录。2026-09-21 的有界验证及回执位于下方运行记录目录。

本次运行证据：[`local-user-chain/2026-09-21`](../../development/latest-dev-docs/automation-runs/local-user-chain/2026-09-21/)。
此前生产部署的历史验收结果保持原义；本环境不延续那轮已停止的执行，也不授予发布权限。

> 最后更新：2026-05-14 | 首次运行请确保 `../backend/.env` 存在（可复制 `.env.example`）

## ⚠️ 重要提示

**在容器/Compose 模式中，推荐使用统一的容器启动脚本作为该模式入口；本机 daily 默认入口仍见顶部。**

推荐入口：
- `./start-all.sh`
- `./stop-all.sh`
- `./restart.sh`
- 仓库根目录 `./scripts/docker-deploy.sh start|stop|restart|status|logs|health|preflight|checkpoint|rollback|rollback-list`
- 发布前门禁：仓库根目录 `./scripts/pre_release_min_gate.sh`
- 跨平台启动与外部服务配置：仓库根目录 `./scripts/platform-macos.sh|platform-linux.sh|platform-windows.ps1`

`docker compose` / `docker-compose` 可用于排障与临时操作，但日常启动与停机建议走统一脚本入口。

> 团队协作约定：所有命令以仓库根目录为当前目录执行。
>
> ```bash
> export PROJECT_DIR="main"
> ```

## 外部服务配置

本项目的 LLM、搜索、社交和部分数据源能力依赖本地 `main/backend/.env` 中的 key。推荐使用图形化配置入口，不手工复制到聊天或提交记录中：

```bash
python3 scripts/launch.py
```

跨平台入口：

```bash
python3 scripts/launch.py
./scripts/platform-macos.sh configure
./scripts/platform-linux.sh configure
```

Windows：

```powershell
python scripts\launch.py
.\scripts\platform-windows.ps1 configure
```

macOS 桌面小窗口中可点击 `Configure Keys` 打开同一个图形化设置窗口。保存后会写入本地 `main/backend/.env`。

## 快速启动

### 统一启动（推荐方式）

```bash
# 启动所有服务（独立项目全量服务）
cd "$PROJECT_DIR/ops"
./start-all.sh

# 启动核心服务 + scrapyd（可选 profile）
./start-all.sh --profile scrapyd
```

这将自动启动：
- ✅ **主服务**：PostgreSQL, Elasticsearch, Redis, Backend API, Celery Worker
- ℹ️ **可选服务**：Scrapyd（`--profile scrapyd` 时启用，端口 `6800`）

推荐先运行 preflight（含端口检查）：

```bash
./scripts/docker-deploy.sh preflight
./scripts/docker-deploy.sh preflight --profile scrapyd
```

Linux 桌面环境若需要 Docker Launcher 在容器启动后自动弹出浏览器，还需要安装宿主机包 `xdg-utils`：

```bash
sudo apt-get install -y xdg-utils
```

发布前建议先创建回滚检查点：

```bash
./scripts/docker-deploy.sh checkpoint
./scripts/docker-deploy.sh rollback-list
```

回滚到最新检查点（一键恢复 compose/env 并重启）：

```bash
./scripts/docker-deploy.sh rollback
```

回滚但暂不重启（用于人工确认）：

```bash
./scripts/docker-deploy.sh rollback --no-restart
```

### 回滚 fixture dry-run

`rollback.sh` 的 `dry-run` 分支只生成或校验 `fixture_recovery_tools.py` 的
fixture-only plan receipt，不执行 restore、restart、compose、数据库或文件恢复。
生成的 receipt 固定为 `result=planned_dry_run_fixture`、`authority=false`、
`executed=false`，不能作为真实回滚凭据。

生成 fixture rollback plan：

```bash
./rollback.sh dry-run --dry-run --fixture \
  --fixture-root /path/to/fixture \
  --operation config_rollback
```

校验已有 plan receipt：

```bash
./rollback.sh dry-run --dry-run --fixture \
  --fixture-root /path/to/fixture \
  --plan-receipt /path/to/fixture/plan-receipt.json
```

receipt 文件和全部 planned path 必须位于 `--fixture-root` 内；production/live
endpoint、secret-like 参数、非 fixture 命令和越界路径都会 fail closed。原有
`snapshot`、`list`、`rollback` 行为不变。

回滚路径演练（默认执行 preflight + 停启 + 健康检查 + 清理）：

```bash
./scripts/docker-deploy.sh rollback-drill
./scripts/docker-deploy.sh rollback-drill --profile scrapyd
./scripts/docker-deploy.sh rollback-drill --dry-run
```

### 停止所有服务

```bash
# 停止所有服务
cd "$PROJECT_DIR/ops"
./stop-all.sh
```

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

3. **Celery Worker**（默认启动）
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

如果迁移失败，启动会直接失败并退出（fail-fast），以避免服务在 schema 未就绪状态下对外提供接口。

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

# 检查6800端口（Scrapyd，可选）
lsof -i :6800
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
