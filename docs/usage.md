# 使用说明

以下命令从仓库根目录执行。宿主直装和本机 Docker 属于同一个单用户工作台的两种安装方式。完整安装必须从业务页面进入 Codex WebUI，并经 Cell 在同一项目中执行和读回操作。

## 首次运行

本机启动以 macOS 为目标。先准备 Python 3.11、Node.js 22（22.13 或以上）、pnpm 和 PostgreSQL（含 pgvector）；依赖安装还需要能访问后端依赖清单中固定的 Git 依赖。队列任务还需要 Redis 与 Celery worker，全文检索使用 Elasticsearch。

1. 运行 `./scripts/local-deploy.sh prepare`，安装后端和界面依赖。这一步不启动服务、不建库、不执行迁移。
2. 复制 [后端环境模板](../main/backend/.env.example) 为 `main/backend/.env`，配置 `DATABASE_URL`，使用队列任务时也配置 `REDIS_URL`。确保 PostgreSQL 已启动、数据库已创建，且连接用户有权执行迁移。在新库运行：

   ```bash
   (cd main/backend && .venv311/bin/python -m alembic upgrade head)
   ```

3. 构建并启动业务界面与后端服务：

   ```bash
   pnpm --dir main/frontend-modern run build
   ./scripts/local-deploy.sh start --low-memory --non-interactive
   ./scripts/local-deploy.sh health
   ```

4. 按 [Codex WebUI 本机构建与启动](../main/ops/codex-webui/README.md#mrw-本机构建与启动)构建嵌入界面并配置宿主 OAuth。然后从业务界面进入「Codex 工作台」。业务界面可打开不等于 Agent 已获准执行，任务是否完成以实际结果读回为准。

普通启动使用已有配置、依赖和数据，不替你安装系统服务。主库不可用或迁移未就绪时先修复主库；Redis 或本机 worker 不可用时，API 可独立启动，但不能据此认定队列任务可执行。Redis 恢复后可按下节启动 worker，并在任务页确认任务结果。Elasticsearch 不可用时，仅影响使用该通道的搜索。端口已被占用时，不要停止其他 checkout 的服务。可在当前 shell 中设置 `BACKEND_PORT` 与 `FRONTEND_PORT`（例如 `export BACKEND_PORT=18080 FRONTEND_PORT=15173`），后续启停和健康检查沿用同一组变量。前端日志和 worker 日志写在当前 checkout 的 `.local-run/`。

## 日常操作

1. 在业务界面创建或选择项目，让来源、文档、检索和报告落在同一项目范围内。
2. 导入文件或采集来源，在任务页面查看解析、索引和失败原因。
3. 按项目检索材料，通过图谱或写作工作台组织结果。
4. 需要 Agent 时进入 Codex WebUI；任务是否完成以执行结果和持久读回为准。

| 服务 | 默认入口 |
| --- | --- |
| 业务界面 | <http://127.0.0.1:5173> |
| 后端 API | <http://127.0.0.1:8000/docs> |
| Codex WebUI（macOS 直装） | 从业务界面进入「Codex 工作台」；本机页面嵌入 <http://localhost:8172/> |

### 加载随附演示项目

`demo_proj` 是可以直接浏览和复制的研究项目。[随附数据包](../main/backend/seed_data/project_demo_proj.sql.gz)包含来源与材料、资源池、可用的内置来源库条目、持久化图谱，以及一篇带材料引用的写作文档。它不是数据库备份，不携带原实例的凭据、外部采集服务、定时任务、运行记录或审核状态；加载也不会开始采集或切换当前项目。

宿主安装完成数据库迁移后，使用后端的 `DATABASE_URL` 或 `main/backend/.env`，从仓库根目录运行：

```bash
bash main/backend/scripts/load_demo_proj_seed.sh
```

Docker 安装可在已启动的后端容器中加载同一数据包。macOS / Linux：

```bash
HOST_PROJECT_ROOT="$PWD" docker compose --project-name "${MRW_DOCKER_PROJECT:-mrw-local-user}" \
  --env-file main/ops/.env.local-user -f main/ops/docker-compose.yml \
  -f main/ops/docker-compose.local-user.yml exec backend bash /app/scripts/load_demo_proj_seed.sh
```

Windows PowerShell 沿用下文 Docker 部署配置的 `$compose`，运行 `docker compose @compose exec backend bash /app/scripts/load_demo_proj_seed.sh`。

加载后在项目列表选择 `demo_proj`。已有材料的演示项目保持原样，不会被重复导入或自动升级；已归档的项目、只有部分模板数据但没有材料的项目会被拒绝写入。要对照新版又保留已有工作，请在使用独立数据库的新实例中加载，不必清空原项目。

## 查看状态与启停

```bash
./scripts/local-deploy.sh status
./scripts/local-deploy.sh health
```

按需启动或停止本机进程：

```bash
./scripts/local-service-control.sh backend-start
./scripts/local-service-control.sh worker-start
./scripts/local-service-control.sh frontend-start

./scripts/local-service-control.sh frontend-stop
./scripts/local-service-control.sh worker-stop
./scripts/local-service-control.sh backend-stop
```

Codex WebUI 单独管理：

```bash
./main/ops/codex-webui/start.sh
./main/ops/codex-webui/stop.sh
```

WebUI 的构建、版本、数据库位置及 LaunchAgent 配置统一见[服务说明](../main/ops/codex-webui/README.md)。worker 与 Elasticsearch 的本机服务标签分别为 `com.mrw.local-worker`、`com.mrw.local-elasticsearch`。

## 宿主直装的认证

宿主直装时，Codex WebUI 共享宿主 `~/.codex/auth.json` 的 OAuth 身份；服务 home 为 `~/.codex-mrw-agent`，其中的认证文件以符号链接指向宿主身份。宿主尚未登录时，先完成宿主 Codex 登录，再启动 WebUI。

WebUI API 密钥由已有私密配置提供。启动脚本会验证配置、固定 Codex CLI 版本和认证链接；出现错误时按错误文字处理，不在文档或日志中记录凭据。

## 本机 Docker 部署

在 macOS、Linux 或 Windows 的 Linux 容器模式运行本机单用户工作台。使用 Docker Engine 和 [Compose 2.24.4 或以上](https://docs.docker.com/reference/compose-file/merge/#replace-value)；目标架构为 `linux/amd64`、`linux/arm64`。初次启动需从源码构建并下载镜像及应用依赖；可先用 `docker version` 和 `docker compose version` 确认 Engine 与 Compose 可用。目标架构不等于已完成该设备上的验收。

部署启动业务界面、API、PostgreSQL、Redis、Elasticsearch、Celery worker 和同实例的 Codex WebUI。随镜像提供仓库的默认来源配置；在「采集」中使用「同步来源库」导入本实例，不会自动运行采集。浏览器只使用本机 loopback，数据库、搜索服务、Redis 和 WebUI 不发布各自容器端口。不需要宿主的 MRW `.env`、数据库或 Codex 登录状态。

### macOS / Linux

在仓库根目录执行：

```bash
cp -n main/ops/.env.local-user.example main/ops/.env.local-user
```

编辑 `main/ops/.env.local-user`，给 `MRW_SERVER_API_KEY` 和 `MRW_WEBUI_API_KEY` 分别填两个不同的高熵值（如分别执行 `openssl rand -hex 32` 生成）。前者用于 MRW 服务调用，后者用于 WebUI 会话交换；浏览器不持有服务密钥。只使用 ASCII 字母、数字、下划线或连字符，不提交配置文件。设置完成后：

如果所在主机的 Docker 容器不能直接访问外网，在同一个配置文件中设置 `MRW_HTTP_PROXY` 与 `MRW_HTTPS_PROXY`；Docker Desktop 可用 `http://host.docker.internal:7892` 这类宿主代理地址。这两项同时用于镜像构建步骤和运行中的服务。基础镜像拉取由 Docker Engine 自己处理，必要时另外配置 Engine 代理。没有代理需求时保持为空。

```bash
./scripts/local-docker-deploy.sh config
./scripts/local-docker-deploy.sh up
./scripts/local-docker-deploy.sh status
./scripts/local-docker-deploy.sh health
```

### Windows PowerShell

在使用 Linux 容器的 Docker 环境中，于仓库根目录运行：

```powershell
if (!(Test-Path main/ops/.env.local-user)) {
    Copy-Item main/ops/.env.local-user.example main/ops/.env.local-user
}
notepad main/ops/.env.local-user
```

保存两个不同的高熵密钥后，再运行下面的命令。`HOST_PROJECT_ROOT` 只用于基础 Compose 文件的变量解析，显式服务列表不启动 launcher，不挂载 Docker socket：

```powershell
$env:HOST_PROJECT_ROOT = '/workspace'
$project = if ($env:MRW_DOCKER_PROJECT) { $env:MRW_DOCKER_PROJECT } else { 'mrw-local-user' }
$compose = @('--project-name', $project, '--env-file', 'main/ops/.env.local-user',
    '-f', 'main/ops/docker-compose.yml', '-f', 'main/ops/docker-compose.local-user.yml')
docker compose @compose config --quiet
docker compose @compose up -d --build --pull missing --wait --wait-timeout 180 db es redis backend celery-worker codex-webui frontend-modern
docker compose @compose ps
```

默认业务界面为 [127.0.0.1:15132](http://127.0.0.1:15132/)，API 文档为 [127.0.0.1:18132/docs](http://127.0.0.1:18132/docs)。端口冲突时修改 `main/ops/.env.local-user` 中的 `MRW_DOCKER_PORT` 和 `MRW_DOCKER_API_PORT`。浏览器使用 `127.0.0.1` 和设置的业务端口；不要用反向代理将这个单用户入口对外开放。同一台机器可以用 `MRW_DOCKER_PROJECT` 区分不同安装；每个实例保持自己的项目名、端口、配置和数据卷。

### Docker 中的 Codex 登录与项目绑定

首次从容器运行 Codex 时，先在实际运行 WebUI 的容器里授权。macOS / Linux 在仓库根目录执行：

```bash
HOST_PROJECT_ROOT="$PWD" docker compose --project-name "${MRW_DOCKER_PROJECT:-mrw-local-user}" \
  --env-file main/ops/.env.local-user \
  -f main/ops/docker-compose.yml \
  -f main/ops/docker-compose.local-user.yml \
  exec codex-webui codex login --device-auth
```

PowerShell 沿用启动时的 `$compose`：

```powershell
docker compose @compose exec codex-webui codex login --device-auth
```

先在 ChatGPT 个人安全设置或工作区权限中启用[设备代码登录](https://learn.chatgpt.com/docs/auth#preferred-device-code-authentication-beta)，然后按终端提示完成授权。登录状态保存在 `local_user_codex_home` 卷，不要复制宿主认证文件。该命令授权的是容器中的 Codex 进程，不建立 MRW 浏览器会话。返回业务界面，在目标项目打开「Codex 工作台」；它通过同一网关的 `/codex/` 嵌入 WebUI，并使用这个实例的项目绑定。直接打开 `/codex/` 不等于从项目打开线程，也不是 Cell 已接通的证明。

### Docker 的启停与恢复

macOS / Linux：

```bash
./scripts/local-docker-deploy.sh logs
./scripts/local-docker-deploy.sh down   # 停止并保留数据
./scripts/local-docker-deploy.sh up
```

PowerShell：

```powershell
docker compose @compose logs -f backend celery-worker codex-webui frontend-modern
docker compose @compose down
```

在 PowerShell 再次启动时，使用上面的完整 `up` 命令。不要对另一份 checkout 使用相同的 Compose 项目名。`down` 保留命名卷；POSIX 脚本的 `reset` 会移除该实例的卷，不能作为升级或修复步骤。

升级前备份 PostgreSQL 业务数据库和 WebUI 卷（包括 `codex-webui.sqlite`、登录状态及线程数据）；分别核对文件存储、搜索索引和队列的保留范围，不能用数据库备份替代。索引要重建完成后再验检索；在途任务或副作用结果未知时先查运行记录及领域读回，不因重启而重放。

## 安装验收

以下是验证条件，不是已通过的发布记录。首次验收用独立实例和空数据卷，不使用已有实例代替。至少检查：

1. 业务页面可创建项目；材料由后台任务提交成功后，详情能读到正文和来源，「资料与质量」的「资料列表」用正文关键词可查到记录，另一项目不能查到。列表直查项目库，不依赖向量或索引；另行核验政策词法索引：用 `POST /api/v1/indexer/policy` 为当前项目的政策材料建索引，再用 `GET /api/v1/search?rank=bm25&q=关键词` 验证命中。词法索引不需要向量密钥；普通原始笔记不进入政策索引。
2. 在同一项目打开嵌入 WebUI 并新建绑定线程；纯附件回合能经 Cell 实际执行，需批准的写入在批准前不落库，批准后能从原业务界面读回。另一项目不能读到这些结果。
3. 重启后仍能打开项目、已有材料、引用和已完成的 Agent 线程；未知副作用不会被当成成功或自动重放。

首页、健康接口和工具目录只能证明各自可访问。外部采集通道、模型、项目能力或权限未配置时，应核对相应缺口，不以空结果代替失败说明。
