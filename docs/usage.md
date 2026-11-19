# 使用说明

以下命令从仓库根目录执行。当前本机日常模式由业务前端、API、任务 worker、搜索依赖和 Codex WebUI 组成。

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

4. 按 [Codex WebUI 本机构建与启动](../main/ops/codex-webui/README.md#mrw-本机构建与启动)构建嵌入界面并配置宿主 OAuth。然后从业务工作台进入 Agent。业务界面可打开不等于 Agent 已获准执行，任务是否完成以实际结果读回为准。

普通启动使用已有配置、依赖和数据，不替你安装系统服务。主库不可用或迁移未就绪时先修复主库；Redis 或本机 worker 不可用时，API 可独立启动，但不能据此认定队列任务可执行。Redis 恢复后可按下节启动 worker，并在任务页确认任务结果。Elasticsearch 不可用时，仅影响使用该通道的搜索。端口已被占用时，先确认所属进程；不要覆盖其他 checkout 的服务。

## 日常操作

1. 在业务界面创建或选择项目，让来源、文档、检索和报告落在同一项目范围内。
2. 导入文件或采集来源，在任务页面查看解析、索引和失败原因。
3. 按项目检索材料，通过图谱或写作工作台组织结果。
4. 需要 Agent 时进入 Codex WebUI；任务是否完成以执行结果和持久读回为准。

| 服务 | 默认入口 |
| --- | --- |
| 业务界面 | <http://127.0.0.1:5173> |
| 后端 API | <http://127.0.0.1:8000/docs> |
| Codex WebUI | <http://127.0.0.1:8172>；业务界面代理路由 `/codex/` |

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

## 认证

Codex WebUI 共享宿主 `~/.codex/auth.json` 的 OAuth 身份；服务 home 为 `~/.codex-mrw-agent`，其中的认证文件以符号链接指向宿主身份。宿主尚未登录时，先完成宿主 Codex 登录，再启动 WebUI。

WebUI API 密钥由已有私密配置提供。启动脚本会验证配置、固定 Codex CLI 版本和认证链接；出现错误时按错误文字处理，不在文档或日志中记录凭据。

## 容器验证

容器模式的具体命令、隔离数据和端口统一见[运维说明](../main/ops/README.md)。

| 模式 | 入口 | 默认端口 |
| --- | --- | --- |
| Docker 控制台 | `./scripts/platform-macos.sh docker-start` | 控制台 5176 |
| Docker 应用栈 | 控制台 Start 或 `./scripts/platform-macos.sh docker-app-start` | 前端 5174，API 8000 |
| Compose 隔离验证 | 按运维说明使用独立 Compose project | 前端 15132，API 18132 |

控制台启动后需要启动应用栈；显示 `App 6/6` 后再访问业务界面。宿主和 Docker 应用栈默认都使用 API 8000，切换模式前确认端口所属进程。

## 上线前预检

生产容器配置使用独立的 [生产 Compose](../main/ops/docker-compose.production.yml)，不与本机或开发 Compose 叠加。先运行与 CI 同源的两项检查：

```bash
python3 scripts/formal_release/check_static_production_contract.py
python3 scripts/formal_release/check_production_compose_config.py
```

前者需要 Python 环境中已安装 `packaging`，检查发布版本、配置结构和仓库门禁声明；后者用合成输入只渲染，既不拉取镜像也不启动服务。两项通过不代表镜像、迁移、认证或业务链路已验收。

有获准的目标环境后，从 [生产环境模板](../main/backend/.env.production.example) 在仓库外准备私密 env 文件；凭据不进 Git、不进镜像。使用真实镜像摘要、构建标识和运行策略，只返回检查状态，不输出渲染后的配置：

```bash
docker compose -f main/ops/docker-compose.production.yml \
  --env-file "$MRW_PRODUCTION_ENV_FILE" config --quiet
```

执行前确保当前 shell 没有同名变量覆盖该文件。真实上线还需在目标环境独立验证镜像、迁移和回滚、API/worker，以及经 Cell 的实际调用与持久读回；不要用本机或历史记录替代。
