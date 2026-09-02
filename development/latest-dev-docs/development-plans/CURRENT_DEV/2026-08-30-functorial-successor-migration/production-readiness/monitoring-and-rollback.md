# Successor 生产监控与回滚

> 状态：`RECOMMENDATION_NOT_IMPLEMENTED`，但 2026-09-03 已完成三项本地 cutover drill（真实 rollback drill、DB 备份/恢复、DB 迁移 downgrade），见第 6 节。本文件把候选里已有的可观测/回滚基础与尚缺的生产能力分开；真实生产监控/告警/TLS/secret 扫描与生产回滚编排仍未实现。

## 1. 候选已有的可观测性基础

源码/既有脚本中可直接使用：

| 能力 | 位置/证据 | 说明 |
| --- | --- | --- |
| 请求指标 | `main/backend/app/main.py` | `/metrics` 暴露 Prometheus text；`market_api_requests_total{method,endpoint,status}`、`market_api_request_latency_seconds{endpoint}` |
| 请求日志 | 同上 | 每请求记录 `request_id/project_key/http_method/http_target/http_status/duration_ms/error_code`；HTTP 响应带 `X-Request-Id/X-Trace-Id` |
| 浅健康 | `GET /api/v1/health` | compose backend healthcheck 使用 |
| 深健康 | `GET /api/v1/health/deep` | database + pool + elasticsearch + latency；整体 `ok/degraded` |
| Docker 健康 | `main/ops/docker-compose.yml` | db/es/backend/celery 均有 healthcheck；celery 用 `celery inspect ping` |
| 配置/环境回退 | `scripts/docker-deploy.sh checkpoint|rollback|rollback-list|rollback-drill` | snapshot 只含 compose/env/git head 记录 |
| 发布前门禁 | `scripts/pre_release_min_gate.sh` | 含 rollback-drill dry-run |

重要限制（真实缺口）：

- compose/repo 内没有 Prometheus、Grafana、Alertmanager 或任意告警规则；`/metrics` 只是可被抓取端点。
- 没有 successor 领域指标（projection 状态、offset 滞后、command 状态计数）；`/metrics` 只有通用 HTTP endpoint 标签。
- `DEPLOY_COLOR`/`SERVICE_NAME`/`ENV` 只是日志静态字段（start 脚本设置默认 `blue/dev`），不代表真实蓝绿路由或 canary 流量开关。
- `frontend-modern` 的 Playwright/浏览器侧有观测 spec，但它不是运行时监控。

## 2. 建议监控指标与告警

以下阈值是建议起点，需在真实流量上校准；命令与指标名以第 1 节实际存在项为准。

| 指标/来源 | 建议采集方式 | 建议告警 |
| --- | --- | --- |
| backend 浅健康失败 | compose healthcheck / 外部探针 `GET /api/v1/health` | 连续 3 次失败即 P1 |
| deep health `status != ok` | 外部轮询 `GET /api/v1/health/deep`，解析 `database/database_pool/elasticsearch` | 任一非 ok 持续 > 2 分钟告警 |
| 5xx 速率 | `rate(market_api_requests_total{status=~"5.."}[5m])`，按 `endpoint` 拆分 | 全局 > 0 或 successor endpoint > 0 持续 5 分钟 P1 |
| 请求延迟 | `histogram_quantile(0.95, sum by(le,endpoint)(rate(market_api_request_latency_seconds_bucket[5m])))` | successor command/query 阈值先按 staging 实测基线定 |
| 容器状态 | `docker compose ps`、容器 restart count | backend 不在 Up 或 restart 增加即 P1；注意 compose 默认未给 backend 配置 restart policy |
| celery 健康 | `celery -A app.celery_app inspect ping` | ping 失败/worker 丢失 P1 |
| 数据库连接池 | `/api/v1/health/deep` 的 `details.database_pool` | `database_pool=error: pool_exhausted` 时告警（settings 有 `DEEP_HEALTH_POOL_GATE_ENABLED`/`DEEP_HEALTH_POOL_EXHAUSTION_RATIO` 可调） |
| 备份新鲜度 | 外部调度器记录备份时间 | 超过 RPO 未成功备份 P1 |
| 磁盘/数据卷 | 主机或容器监控 | 数据卷剩余 < 20% 告警 |

尚不存在、建议新增（独立里程碑）：

- successor projection offset/backlog 指标（基于 `public.runtime_projection_offsets`/`runtime_run_projections` 的读取与 CAS 推进）。
- successor command/query envelope 状态计数（`ok/waiting/blocked/unavailable/conflict/error`）。
- 路由挂载/版本指标（例如 `app_version`、`route_mounted`），防止部署漂移到不含 successor 路由的 commit。

## 3. Canary / 灰度

### 3.1 当前事实

- 候选没有 successor 流量开关、灰度比例配置、A/B 分流或 registry-based production resolver。
- `app/api/__init__.py` 硬编码挂载 successor router；挂载与否没有独立 env 开关。
- 因此“在现网按 1%/5% 把用户切到 successor”目前没有可执行代码路径；真正的路由级 canary 需要新里程碑（flag 或 registry + resolver + scope digest 绑定）。
- 已有 `graph_node_projection_read_mode`、`ingest_frontdoor_rollout_mode` 等 legacy 领域 canary 字段，但属于其它子系统，不得当作 successor canary 证据。

### 3.2 候选内可先执行的“灰度等价验证”（本地/预发）

1. 字节验收：干净 checkout 候选 commit/tree，复跑 `../05_functorial-successor-final-review.md` 中的聚焦测试（router mount、I1、schema、依赖边界、C7 disposable PG）。
2. 本地 closed-fixture 冒烟：启动后调用 `/api/v1/successor-runtime/v2/queries`，验证 typed envelope、`control_feedback=false`、无控制字段。
3. staging 独立栈：与生产/legacy 主栈同库或独立库均可，但不共享 canonical write；候选栈只作为观察端点。
4. parity/regression 输入：用既有 legacy 与 successor 观察对（P3/P4 evidence、movement matrix）跑确定性 interpreter/parity 测试；parity 不是 live 调用。
5. 预发放行：仅在 movement matrix、decision parity、`UNASSIGNED_BLOCKER == 0` 与独立双门 review 完成、且 authority ceiling 被显式扩展后，才谈路由放行。

### 3.3 建议的真实 canary 前置条件

- 给 successor router 增加显式 enabled 开关或独立 deployment/ingress 挂载，保证可整体摘除。
- 增加真实 project registry resolver 与 production scope digest 绑定；当前 `LocalOnlyProjectScopeResolver.resolve_expected` 是关闭的。
- 增加请求级 trace 与响应 meta 关联，保证能按 project_key/request_id 分流核对。
- 每批灰度都有自动健康门禁：浅健康、deep health、HTTP 5xx、延迟、legacy 路由回归、DB 残留。

## 4. Cutover 决策与执行（约束）

按 02/05/06 冻结与 review 记录：

- 候选 `PASS_EXACT_CANDIDATE` 不授权 `live_provider`、`external_delivery`、`cutover`、`authority_transfer`、`production_canonical_write`。
- legacy 保持可用且不退休；successor 只以新增前缀出现。
- cutover 前必须单独建立 authority 里程碑并形成 stop/go 证据：备份演练、rollback drill、镜像可回退、DB 降级/恢复演练、监控告警在线。

建议 stop 条件（任一命中即停止放量并回退）：

- 候选栈启动失败或迁移失败。
- successor endpoint 5xx/异常 envelope 高于基线。
- deep health 中 DB/ES/pool 持续异常。
- legacy 路由回归（候选不修改 legacy 路径，若观察到回归应视为集成问题）。
- DB 残留/不可恢复状态无法在演练中复原。

## 5. Rollback 步骤

### 5.1 发布前

```bash
./scripts/docker-deploy.sh checkpoint
./scripts/docker-deploy.sh rollback-list
./scripts/docker-deploy.sh rollback-drill --dry-run
```

### 5.2 配置/env 回退（既有脚本能力）

```bash
# 恢复最新 snapshot
./scripts/docker-deploy.sh rollback

# 恢复指定 snapshot，先不重启
./scripts/docker-deploy.sh rollback <snapshot_id> --no-restart
```

恢复后检查 `main/ops/docker-compose.yml`、`main/backend/.env` 与记录里的 `git_head.txt`。该步骤不切代码。

### 5.3 代码/镜像回退（需要人工/CI 步骤）

当前 backend/frontend 镜像由本地 checkout `build`，无 registry 推送流程。回退序列：

1. 在干净 checkout 上取上一已知良好 commit（例如 source-identical `1825870a…` 或其它已放行基线），确认 `git rev-parse HEAD HEAD^{tree}`。
2. 停机或维护窗口：`./scripts/docker-deploy.sh stop`。
3. 重建并重启：`./scripts/docker-deploy.sh start --services db,es,redis,backend,celery-worker,frontend-modern --non-interactive --build`。
4. 健康与回归验证：浅健康、deep health、legacy 核心端点、successor 路由按目标状态检查。

不要使用 `./scripts/docker-deploy.sh stop --volumes` 或 `stop-all.sh --volumes` 作为回退步骤；它会删除 compose volume（含 `db_data`）。

### 5.4 数据库 schema/数据回退（独立流程）

- 后端 entrypoint 默认 `RUN_MIGRATIONS=true` 时自动 `alembic upgrade head`；候选迁移 `20260830_000001`、`20260831_000002` 带 downgrade 实现，但仓库没有 compose/脚本级 downgrade 编排。
- 应用回退不代表 DB 自动回退；若 schema 已升级且数据已按新结构写入，必须先演练数据/schema 回退。
- 数据回退以 8.2 类备份还原为主（先停后端写路径），并把 `restore + verify` 作为发布 drill 的一部分。

### 5.5 回退后验证清单

```bash
curl -fsS http://localhost:8000/api/v1/health
curl -fsS http://localhost:8000/api/v1/health/deep
./scripts/docker-deploy.sh status
```

再按回退目标执行 legacy 功能回归与 successor 路由存在性断言。回退完成后更新监控基线，保留 snapshot 至少一个发布周期。

## 6. 2026-09-03 Lane C 实测 drill 记录

> 执行范围：候选 commit `3706655f` / tree `5840bf9b` 的干净快照 `/tmp/mrw-cutover-drill.umjWv5`（`git archive 3706655f` 生成，`.env` 由 `.env.example` 复制，无真实密钥）。当时 live worktree 正被另一条线并发改写（15 个 backend/frontend 文件未提交），因此 drill 不在半成品字节上执行；最终 cutover 前需在 Lane A 收口后的字节上复跑。证据 JSON：`../evidence/all-lines-runnable/AllLinesItem04CutoverDrillsEvidence.v1.json`。

### 6.1 wrapper 限制实测

```text
COMPOSE_PROJECT_NAME=mrw-alllines-rehearsal ./scripts/docker-deploy.sh rollback-drill --skip-preflight --profile modern-ui
-> exit 1：start-all 非交互端口检查命中宿主 5432（Homebrew PostgreSQL），未启动任何容器
```

等价 drill（`COMPOSE_PROJECT_NAME=mrw-alllines-rehearsal`，`main/ops/docker-compose.yml` + db/es/redis 内部端口 override，profile `modern-ui`；backend 8000、frontend-modern 5174 暴露宿主）：

```text
docker compose ... config -q                                        -> exit 0
docker compose ... up -d db es redis backend celery-worker frontend-modern
                                                                    -> exit 0（cycle 1）
backend/celery/db/es: Up (healthy)；redis/frontend-modern: Up
GET /api/v1/health                                                   -> 200
GET /api/v1/health/deep                                              -> 200（database/pool/es ok）
POST /api/v1/successor-runtime/v2/queries                            -> 200（typed envelope，no_postgres_write=true）
GET /api/v1/agent-batch/executor/health（legacy）                    -> 200
GET http://localhost:5174/                                           -> 200
docker exec <es> curl http://localhost:9200/_cluster/health          -> green
docker compose ... down --remove-orphans（保留 volumes）             -> exit 0；残留容器 0
docker compose ... up -d ...                                         -> exit 0（cycle 2，20s 内全 healthy）
GET /api/v1/health、/api/v1/health/deep、http://localhost:5174/      -> 全部 200
docker compose ... down -v --remove-orphans                          -> exit 0；残留容器/网络/volume = 0/0/0
```

镜像沿用 ITEM-03 产物并保留：`mrw-alllines-rehearsal-backend:latest (25c7b263cf12)`、`-celery-worker:latest (eacf5d2c243f)`、`-frontend-modern:latest (16b83649a705)`。

### 6.2 DB 备份/恢复 drill（disposable local PG，完整 29 条迁移链）

```text
库名：mrw_cutover_drill_backup_20260903
alembic upgrade head                                                -> exit 0，version=20260831_000002
seed：public.project_scope_registry 一行（count=1）
pg_dump --format=custom                                             -> sha256 30a25e39ccf33626110f72feae1e850e02e69d1ea7b77ac993af951b39fdfbdc
DROP DATABASE ... WITH (FORCE) → CREATE DATABASE → pg_restore（--no-owner --no-privileges --exit-on-error）
                                                                    -> exit 0；version=20260831_000002；seed row 恢复（count=1）
C7 focused PG：test_c7_canonical_write_projector_postgres.py          -> exit 0，9 passed / 0 failed（1.29s，自建自删专用库）
teardown：删除 drill 库；pg_database/pg_roles 回到基线
```

### 6.3 DB 迁移 downgrade drill（disposable local PG）

```text
库名：mrw_cutover_drill_downgrade_20260903
alembic upgrade head                                                -> exit 0；version=20260831_000002；runtime_* 表 22、project_scope_registry 1
alembic downgrade 20260402_000004                                   -> exit 0；version=20260402_000004；runtime_* 表 0、project_scope_registry 0
alembic upgrade head（再次）                                         -> exit 0；version=20260831_000002；runtime_* 表 22
teardown：删除 drill 库；残留 0
```

### 6.4 结论与剩余环境项

- 三项 drill 在本机 disposable/local 范围通过并零残留；这是 local 演练证据，不是生产 cutover/authority 证据。
- 尚未满足的生产环境项（如实保留为缺口）：TLS 终结、镜像 digest/registry tag、Prometheus/Alertmanager 在线告警、secret/依赖漏洞扫描、生产 successor registry resolver + 端点认证、successor 前端页面接线、计划备份/RPO 自动化、生产 owner/ACL 与 volume 级恢复 drill。

## 7. 2026-09-03 最终字节复跑记录（commit `6f5f5900`）

> 执行范围：最终提交 `6f5f5900` / tree `28b64ad6` 的干净快照（`git archive 6f5f5900` 生成，`.env` 由 `.env.example` 复制，无真实密钥）。三项 drill 与 production_registry smoke 均在该字节上执行，产出证据见 `../evidence/all-lines-runnable/AllLinesFinalRunnableEvidence.v1.json`。本轮只做本地 disposable 复跑与记录，不 commit/push，不改 donor。

### 7.1 rollback drill（project `mrw-final-runnable`，等价 compose）

`docker-deploy.sh rollback-drill --skip-preflight` 仍因宿主端口 5432（Homebrew PostgreSQL）被占用返回 `rc=1`，未启动任何容器；本轮用 `main/ops/docker-compose.yml` + db/es/redis 内部端口 override（backend 8000、frontend-modern 5174 暴露宿主）执行等价 rollback drill：

```text
config -q                                                       -> exit 0
up -d db es redis backend celery-worker frontend-modern         -> exit 0（cycle 1，含 --build）
backend/celery/db/es: Up (healthy)；redis/frontend-modern: Up
GET /api/v1/health                                               -> 200
GET /api/v1/health/deep                                          -> 200（database/database_pool/elasticsearch ok）
POST /api/v1/successor-runtime/v2/queries                        -> 200（typed envelope，status=ok，no_postgres_write=true）
GET /api/v1/agent-batch/executor/health（legacy）                -> 200
GET http://localhost:5174/                                       -> 200
ES cluster health（docker exec）                                  -> green
down --remove-orphans（卷保留）                                   -> exit 0；容器/网络残留 0
up -d ...                                                        -> exit 0（cycle 2，全 healthy）
GET /api/v1/health、/health/deep、successor query、:5174/         -> 全部 200
down -v --remove-orphans                                         -> exit 0；残留 0/0/0
```

镜像按 project 名保留未删除：`mrw-final-runnable-backend:latest (3e01f63b99b3)`、`mrw-final-runnable-celery-worker:latest (5129a464d5bd)`、`mrw-final-runnable-frontend-modern:latest (8dc65e724970)`。

### 7.2 DB 备份/恢复 drill（disposable local PG）

```text
库名：mrw_final_drill_backup_20260903
alembic upgrade head                                            -> exit 0；version=20260831_000002
seed：public.project_scope_registry 一行 ACTIVE（digest 2242a8d1…，pre_dump_count=1）
pg_dump --format=custom                                         -> sha256 7136b4a8f9174412a826242deb4f037d7ef1252f149e773037b52b5dbbed05c8
DROP → CREATE → pg_restore（--no-owner --no-privileges --exit-on-error）
                                                                -> exit 0；version=20260831_000002；seed row count=1
C7 focused PG：test_c7_canonical_write_projector_postgres.py      -> 9 passed / 0 failed（1.27s，自建自删专用库）
teardown：删除 drill 库；pg_database/pg_roles 回到基线
```

### 7.3 DB 迁移 downgrade/upgrade drill（disposable local PG）

```text
库名：mrw_final_drill_downgrade_20260903
alembic upgrade head                                            -> exit 0；version=20260831_000002
alembic downgrade 20260402_000004                               -> exit 0；version=20260402_000004；public successor 表 0
alembic upgrade head（再次）                                     -> exit 0；version=20260831_000002；public successor 表 23
teardown：删除 drill 库；残留 0
```

### 7.4 production_registry runnable smoke（关键新证据）

disposable 库 `mrw_final_runnable_prod_20260903` upgrade head 后 seed 一行 ACTIVE registry（key `final-runnable-prod`），以 `SUCCESSOR_MOUNT_MODE=production_registry`、`SUCCESSOR_PRODUCTION_REQUIRES_AUTH=true`、`CODEX_AUTH_ENABLED=true`、`CODEX_AUTH_TOKENS=dev-final-runnable-token` 启动 app：

```text
（隔离 ambient 会话后，禁用 token-sink/CLI auth/oauth）
无 Authorization                          -> HTTP 401
错误 Bearer                               -> HTTP 401
Authorization: Bearer dev-final-runnable-token -> HTTP 200
  status=ok；meta.project_key=final-runnable-prod
  project_scope_ref.scope_digest=e7bd7d36…；registry_revision=1
  data.no_postgres_write=true；无 503
负例：production_registry + requires_auth=true + codex_auth_enabled=false
  -> 进程退出 1（ValidationError：requires codex_auth_enabled=true），fail-closed 生效
```

说明：本机若保留真实 Codex token-sink/CLI 登录且 `codex_oauth_token_sink_enabled=true`，中间件会把宿主机会话视为已认证 OAuth 会话，无 token 请求也会放行（首轮实测 200）。因此上述 401 语义是在禁用 ambient 会话源的隔离进程中验证的；真实生产 ingress 的认证边界仍应以部署环境配置复测。

### 7.5 本轮未满足项（与 6.4 相比已收口/保留）

- 已收口：生产 successor registry resolver + 端点认证接线、successor 前端页面接线在最终字节已存在并通过本机 smoke；这两项不再属于剩余缺口。
- 仍保留为环境边界缺口：TLS 终结、镜像 digest/registry tag、Prometheus/Alertmanager 在线告警、secret/依赖漏洞扫描、计划备份/RPO 自动化、生产 owner/ACL 与 volume 级恢复 drill、真实网络级（非 TestClient）ingress 认证复测。
- 本轮全部结果仅对 disposable/local 快照成立；`production_canonical_write=false`、`legacy_retired=false`、`authority_transfer=false`、正式 `cutover=false`。

## 8. Infra 上线差距 #3：已执行/已调度记录（2026-09-03）

> 本节把第 7.5 节列为环境边界缺口的 ES、计划备份/RPO、Prometheus/Alertmanager 在线告警三项落实为本机实际运行/调度状态。本节证据文件：`evidence/all-lines-runnable/AllLinesInfraMonitorEvidence.v1.json`。全部文件未 commit/push，交由监督裁决。

### 8.1 Elasticsearch（本机单节点，独立 compose project `mrw-infra`）

- 新增 `main/ops/mrw-infra/docker-compose.yml`：`docker.elastic.co/elasticsearch/elasticsearch:8.15.3`，单节点、`xpack.security.enabled=false`、`discovery.type=single-node`、host `9200:9200`、`mrw_es_data` volume、healthcheck、`mem_limit: 1g`、`restart: unless-stopped`。
- 容器 `mrw-infra-es` healthy；`GET http://127.0.0.1:9200/_cluster/health` → `status=green`、`number_of_nodes=1`、`number_of_pending_tasks=0`。
- 后端 `.env` 原 `ES_URL=http://localhost:9200`（未改 secret/配置）；`GET /api/v1/health/deep` → `status=ok, database=ok, database_pool=ok, elasticsearch=ok`（此前为 `elasticsearch: error: ping failed`）。

### 8.2 计划备份/RPO（脚本 + launchd，每日 02:30）

- 新增备份脚本 `/Users/wangyiliang/.codex/rollback/production-backup/backup-postgres.sh`（chmod +x）：`pg_dump -Fc -d postgres`（默认 Homebrew 本机 socket/当前 OS 用户，可经 `MRW_PG_DUMP_ARGS` 覆写；不读取 `.env` secret）→ 时间戳文件 + `.sha256` + 日志 + 轮转保留最近 14 份。
- 立即执行一次真实备份成功：
  - 文件：`postgres-20260903-023158.dump`（66,157,986 bytes）
  - SHA-256：`24fc2eeee7ec416f32e7e3dc05fe2d6ee249370f6b08f507d64cc7998529c1de`
- launchd：`~/Library/LaunchAgents/com.github.mrw.postgres-backup.plist`，`StartCalendarInterval` Hour=2 Minute=30，已 `launchctl load`，状态 exit 0。
- 告警 webhook 本地落盘接收器：`/Users/wangyiliang/.codex/rollback/production-monitoring/alert-webhook.py` + `com.github.mrw.alert-webhook.plist`（已加载，pid 运行中，`GET :9094/` → `{"ok":true}`）；告警落点 `/Users/wangyiliang/.codex/rollback/production-backup/alerts.jsonl`（当前无告警属正常）。

### 8.3 Prometheus + Alertmanager + Grafana（独立 compose project `mrw-monitoring`）

- 新增 `main/ops/mrw-monitoring/`：`docker-compose.yml`（prometheus:2.55.1 / alertmanager:0.28.1 / blackbox-exporter:0.25.0 / grafana:11.4.0，30d TSDB 保留，容器 healthcheck，`restart: unless-stopped`）、`prometheus/prometheus.yml`、`prometheus/rules.yml`、`blackbox/blackbox.yml`、`alertmanager/alertmanager.yml`。
- 运行态（2026-09-03 本机）：
  - Prometheus `:9090/-/healthy` 200；targets：`mrw-backend`、`mrw-deep-health`、`mrw-blackbox`、`prometheus-self` 全部 `health=up`；`probe_success{job="mrw-deep-health"}=1`。
  - 告警规则 4 条已加载且 `health=ok`：`MRWBackendDown`（真实 `up==0`）、`MRWDeepHealthProbeDown`（HTTP 探针失败）、`MRWSuccessor5xxRate`（真实 `market_api_requests_total{endpoint=~"/api/v1/successor-runtime.*",status=~"5.."}` 5m rate）、`MRWApi5xxRate`。
  - Alertmanager `:9093/-/healthy` 200；receiver 为本地 webhook（`host.docker.internal:9094`）。
  - Grafana `:3000/api/health` → `database=ok, version=11.4.0`；管理员密码以 compose secret 文件随机生成（`main/ops/mrw-monitoring/secrets/`，权限 600，owner 本机用户）。
- 修复记录：blackbox 探针曾因 `host.docker.internal` 解析为不可达 IPv6 地址导致 `probe_success=0`；在 `blackbox.yml` 增加 `preferred_ip_protocol: ip4` 后 `probe_success=1`。

### 8.4 缺口收口/保留（如实更新）

- 已收口（原 7.5 保留项）：ES 单节点运行并接入 deep health；计划备份脚本 + launchd 调度 + 一次真实备份（RPO 基线文件存在）；Prometheus/Alertmanager 在线采集与本地告警落盘。
- 仍保留：deep health `status=degraded`（HTTP 200 + JSON degraded）的语义级告警需后端领域指标（如 `deep_health_status`），规则中已注释标注未实现；外部通知通道（email/Slack/PagerDuty）未配置（仅本地文件 webhook）；TLS 终结、镜像 digest、secret/依赖漏洞扫描、volume 级恢复 drill、真实网络级 ingress 认证复测、生产 owner/ACL 仍为环境边界缺口。
- Grafana 登录凭据是本机随机生成文件（非仓库 commit 内容，未 commit/push）；若纳入版本管理需先迁移到 secret 管理。
