# MRW 函子化后继候选生产 Runbook

> 状态：`DOCUMENTED_NOT_EXECUTED`。本文档依据候选字节与既有脚本整理启动、健康检查、端点、日志、备份/恢复与故障排查流程；本次生成环境没有运行 Docker、没有 `main/backend/.env`，因此本文所有启动/健康命令在本轮属于“待真实环境执行”，不是已通过记录。

## 1. 候选与运行基线

本 runbook 对应候选（与上一级目录 `../05_functorial-successor-final-review.md` 的 `PASS_EXACT_CANDIDATE` 记录一致）：

| 项 | 值 |
| --- | --- |
| 候选 commit | `452611fccb69188477f277550a7f8b6c98b4724c` |
| 候选 tree | `94a4038390ea8aeb70864ea67720d225576129d8` |
| 候选 branch | `codex/functorial-successor-p0` |
| review 中 source-identical commit | `1825870a9623dd256fa075053ab89d786c84b6bd` |
| review 中 source-identical tree | `63bcc270edf9e880ef04dfeb9413b9c634956bbb` |
| review verdict | `PASS_EXACT_CANDIDATE`（仅 exact candidate 字节验收） |
| promotion/live/cutover | `false`，02 冻结 authority exclusions 继续生效 |

验证候选身份的命令：

```bash
git rev-parse HEAD HEAD^{tree}
git status --porcelain
```

重要边界：

- 本 runbook 所在 manual worktree 不是干净候选树；编写时存在未提交的文档修改与未跟踪文件。生产部署应从干净 checkout 的候选 commit/tree 开始，不能把当前脏 tree 直接当作候选树。
- `main/backend/app/api/__init__.py` 默认挂载 successor v2 router，但依赖来自 `LOCAL_ONLY` closed-fixture assembly（`app/successor_runtime/assembly/app_assembly.py`）：无生产 resolver、无 live provider、无 canonical write、无 cutover。
- 候选保留 legacy 路由（挂载测试断言 `/api/v1/successor-runtime/v2/...` 只是新增前缀，legacy 路由数仍 > 200），legacy 不退休。

## 2. 当前本地环境现状（2026-09-02 实测）

```text
docker info                    -> Docker daemon NOT running
main/backend/.env              -> 不存在（只有 main/backend/.env.example）
pg_isready (Unix socket /tmp)  -> no response
```

因此下列命令中的启动路径无法在当前机器本轮执行。

## 3. 启动前准备

1. 启动并确认 Docker daemon：

   ```bash
   docker info
   ```

2. 准备后端 env。仓库没有 `.env`，必须从模板复制并填写真实值，禁止提交：

   ```bash
   cp main/backend/.env.example main/backend/.env
   ```

   候选使用的关键变量名见 `.env.example`：`DATABASE_URL`、`ES_URL`、`REDIS_URL`、`LLM_PROVIDER`、`OPENAI_API_KEY`、`AZURE_*`、`SERPER_API_KEY`、`CODEX_OAUTH_*` 等。Docker compose 会从 `main/backend/.env` 读取 `env_file`；未配置真实 provider key 时，相关 legacy 外部能力不可用，successor 默认挂载不受影响。

3. 运行 preflight：

   ```bash
   ./scripts/docker-deploy.sh preflight
   ```

   preflight 检查 docker/curl/compose、`main/ops/{start-all,stop-all,restart}.sh`、`main/backend/.env`、compose config，以及端口 `5432/9200/6379/8000`。Docker daemon 未运行时它返回失败（`return 2`）。

## 4. 启动顺序

仓库推荐入口为仓库根目录 wrapper `scripts/docker-deploy.sh`，其内部委托 `main/ops/start-all.sh`。compose 依赖顺序由 `main/ops/docker-compose.yml` 的 `depends_on` 控制：

1. PostgreSQL（`ankane/pgvector`，端口 5432，健康检查 `pg_isready`）
2. Elasticsearch（端口 9200，健康检查 `/_cluster/health`）
3. Redis（端口 6379，无显式 healthcheck，`service_started`）
4. Backend（`docker-entrypoint.sh`：先等 PG/ES/Redis 就绪，再执行 `alembic upgrade head`，最后 `uvicorn app.main:app --host 0.0.0.0 --port 8000`）
5. Celery worker（等待 backend healthy 后启动）
6. Frontend（可选）

### 4.1 主栈

```bash
./scripts/docker-deploy.sh start --services db,es,redis,backend,celery-worker --non-interactive
```

如需在端口冲突时自动失败而非交互等待，保留 `--non-interactive`；不要在生产使用 `--force` 自动忽略依赖端口冲突。

### 4.2 Modern 前端

容器前端是 `main/frontend-modern`，构建进 compose 的 `frontend-modern` 服务（profile `modern-ui`），容器 nginx 监听 80，宿主机映射 `5174:80`：

```bash
./scripts/docker-deploy.sh start --services frontend-modern --non-interactive
```

`main/frontend-modern/nginx.conf` 会把 `/api/` 代理到 `http://backend:8000`。不要用默认 `--profile modern-ui` 全量启动方式把 launcher-agent/launcher-ui 一并带入生产：launcher 需要挂载 Docker socket 与宿主项目目录，且 compose 中 `HOST_PROJECT_ROOT` 默认指向 `/Users/wangyiliang/market-research-workflow` 源 checkout。

非容器本地开发等价入口（后端 8000、Vite 5173、worker PID/日志在 `/tmp`）：

```bash
./scripts/local-deploy.sh start
./scripts/local-deploy.sh health
```

### 4.3 启动失败语义

`docker-entrypoint.sh` 是 fail-fast：PG/ES/Redis 任一在默认 30 次重试内未就绪，或 `alembic upgrade head` 失败，容器直接退出，不会带半迁移 schema 对外服务。

## 5. Successor router 端点

候选最终挂载路径（`app/api/__init__.py` 中 `router.include_router(..., prefix="/api/v1")` + router prefix `/successor-runtime/v2`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/successor-runtime/v2/commands` | 提交 typed successor command |
| POST | `/api/v1/successor-runtime/v2/queries` | 执行只读 projection query |

语义边界（来自 `app/api/successor_runtime.py`、`app/successor_runtime/assembly/app_assembly.py` 与 DTO 测试）：

- 请求 DTO 只允许 project locator + typed payload；actor、scope、authority、execute 等由服务端注入，wire 上禁止未知字段。
- 默认 assembly 是 `LOCAL_ONLY_MOUNT_CONFIGURATION = local_only_closed_fixture_options`，actor 固定为 `actor:local-only-app-mount`，authority ceiling 全 false，生产 `resolve_expected` 路径保持关闭。
- 响应是 `{status, data, error, meta, control_feedback: false}` envelope；`ok/waiting` 不带 error，`blocked/unavailable/conflict/error` 不带 data。
- 非 2xx 只应来自路由不存在、DTO 校验失败等传输层；scope/actor 解析失败会以 200 typed envelope 返回 `SCOPE_RESOLUTION_FAILED` / `ACTOR_RESOLUTION_FAILED`。

### 端点冒烟示例（read-only query）

以下 body 字段来自挂载测试样例（`main/backend/tests/successor_runtime/test_api_successor_runtime_mount.py`）；在真实默认 fixture 上可能返回 `ok` 或带 error 的 typed envelope，但合法 DTO 不应 404/422：

```bash
curl -fsS -X POST http://localhost:8000/api/v1/successor-runtime/v2/queries \
  -H 'Content-Type: application/json' \
  -d '{
    "query_id": "prod-readiness-query-1",
    "query_kind": "projection_snapshot",
    "project_locator": "local-mount-demo",
    "trace_id": "trace:prod-readiness:1",
    "params": {
      "params_kind": "projection_snapshot",
      "projection_id": "projection.run-summary.v1",
      "projector_id": "projector:c9-mount",
      "projector_version": "1",
      "source_kind": "successor_values",
      "source_ref": "c9:mount:source:001",
      "source_incarnation": "inc:c9-mount"
    }
  }'
```

响应应包含 `control_feedback: false`，且顶层不得出现 `actor/authority/execute/scope/control` 等控制字段。

## 6. 健康检查

### 6.1 wrapper

```bash
./scripts/docker-deploy.sh health
```

等价于连续请求：

```bash
curl -fsS http://localhost:8000/api/v1/health
curl -fsS http://localhost:8000/api/v1/health/deep
```

### 6.2 端点语义

- `/api/v1/health`：轻量进程存活检查，返回 `status/provider/env`；compose backend healthcheck 使用它（30s interval，40s start period）。
- `/api/v1/health/deep`：检查 database、database_pool、elasticsearch 及 latency；任一非 `ok` 时整体返回 `status: degraded`。注意 deep check 不验证 provider key/外部 API，也不验证 successor projection。
- `/metrics`：Prometheus text format，当前指标含 `market_api_requests_total`（method/endpoint/status）与 `market_api_request_latency_seconds`（endpoint）。

### 6.3 服务级检查

```bash
./scripts/docker-deploy.sh status
cd main/ops && docker compose ps
```

## 7. 日志

Docker 主路径：

```bash
./scripts/docker-deploy.sh logs                 # backend，跟随
./scripts/docker-deploy.sh logs celery-worker   # 或任意 compose service
cd main/ops && docker compose logs -f backend
```

backend 启动日志中应能看到 entrypoint 的 PG/ES/Redis 就绪、`alembic upgrade head` 与 `uvicorn` 启动；应用日志统一包含 `service env version deploy_color` 字段。celery worker 容器把日志写到 `/var/log/celery/worker.log`（compose volume 映射到 `main/logs`）。

纯本地模式日志/进程文件：

```text
/tmp/frontend-modern-dev.log / /tmp/frontend-modern-dev.pid
/tmp/celery-local-worker.log / /tmp/celery-local-worker.pid
```

## 8. 备份 / 恢复

### 8.1 仓库既有 rollout snapshot（只覆盖 compose/env/git head 记录）

```bash
./scripts/docker-deploy.sh checkpoint        # 写 main/ops/.rollback_snapshots/<timestamp>/
./scripts/docker-deploy.sh rollback-list
./scripts/docker-deploy.sh rollback          # 恢复最新 snapshot 并 restart
./scripts/docker-deploy.sh rollback --no-restart
```

`main/ops/rollback.sh` snapshot 只保存 `docker-compose.yml`、`backend.env` 和 `git_head.txt`；它不恢复代码、不 dump 数据库、不降级 schema。因此它适合作为“配置/env 回退”，不能单独作为完整数据恢复手段。

### 8.2 数据库备份（仓库无备份脚本，下列为运维建议，未在候选上演练）

停止写入窗口或先在 staging 演练：

```bash
cd main/ops
docker compose exec -T db pg_dump -U postgres -d postgres --format=custom --file=/tmp/mrw-backup.pgc
docker compose cp db:/tmp/mrw-backup.pgc ./mrw-backup.pgc
```

恢复演练：

```bash
cd main/ops
docker compose cp ./mrw-backup.pgc db:/tmp/mrw-backup.pgc
docker compose exec -T db pg_restore -U postgres -d postgres --clean --if-exists /tmp/mrw-backup.pgc
```

真实生产凭据、DB 名与 `pg_dump/pg_restore` 版本必须先替换为环境值并在恢复环境做 full drill；`--clean` 会删除目标对象，禁止无演练直接执行。

### 8.3 代码/镜像回退

当前 compose 服务没有 registry image tag，backend/frontend 都从 checkout 本地 `build`。回退到上一版本需要：干净 checkout 上一已知良好 commit → 重建镜像 → 重启。`rollback.sh` 不会自动完成 git checkout 或镜像切换。

## 9. 故障排查

| 现象 | 处置 |
| --- | --- |
| `preflight` 报 Docker daemon 未运行 | 启动 Docker Desktop 后重跑；本轮实测 daemon 未运行 |
| `preflight` 报缺 `.env` | 从 `.env.example` 复制并填真实值 |
| 端口 5432/9200/6379/8000 被占 | `lsof -i :<port>`；确认不是其他实例；Docker 模式用 `--non-interactive` 让它失败而不是 `--force` |
| backend 容器反复退出 | `docker compose logs backend`；检查 entrypoint 等待或 `alembic upgrade head` 错误；migration fail-fast 不会带半 schema 启动 |
| `/health` ok 但 `/health/deep` degraded | 按 checks 定位 database/database_pool/elasticsearch；deep 不覆盖 provider/successor 语义 |
| successor 请求返回 typed error envelope | 按 `error.code`：`SCOPE_RESOLUTION_FAILED`、`ACTOR_RESOLUTION_FAILED` 是解析层；其它 code 来自 facade。合法 DTO 不应 HTTP 500 |
| successor 路径 404 | 确认部署的是候选 commit（`app/api/__init__.py` 已 include successor router），且代理没有改写该前缀 |
| celery 不消费任务 | `docker compose ps celery-worker`、`docker compose logs celery-worker`；compose 对其配置了 `celery inspect ping` healthcheck |
| 前端 5174 打不开 | 确认 `frontend-modern` 已启动且 backend healthy；nginx 把 `/api/` 代理到容器网络 `backend:8000`，不要用宿主机 URL 直连该代理 |
| 怀疑候选/代码漂移 | 在干净 checkout 上 `git rev-parse HEAD HEAD^{tree}` 对照第 1 节，并运行 review 中的聚焦测试 |

## 10. 候选验证脚本（非生产启动依赖）

仓库根 `scripts/` 下没有同名文件；实际候选路径是 `main/backend/scripts/run_successor_postgres_validation.py`。它是 bounded 本地 disposable-PG runner，不是部署器：

- 必须传 `--database-url` 或环境变量 `SUCCESSOR_POSTGRES_VALIDATION_DATABASE_URL`，且 URL 只能是 Unix socket、无密码、admin DB 不能是 `postgres/template0/template1`。
- 每次创建/删除唯一 `mrw_successor_validation_<token>` DB 与 role，child 以受限环境、非 shell 字符串方式执行 `--` 后的命令。
- 退出码：0 = 通过且 teardown 干净；1 = child 失败或残留变化；2 = usage/guard/执行/teardown 错误。报告 JSON 写 stdout，可用 `--report <path>` 落盘。

候选验收测试的实测命令与计数记录在 `../05_functorial-successor-final-review.md`（如 router mount `15 passed`、非 PG full `1399 passed`、PG C7 `59 passed`），属于历史/审查证据，本轮未复跑。
