# Successor 生产监控与回滚

> 状态：`RECOMMENDATION_NOT_IMPLEMENTED`。本文件把候选里已有的可观测/回滚基础与尚缺的生产能力分开；所有阈值、canary 与回滚步骤都是建议流程，标注为“待真实环境验证”的部分没有在本轮被执行。

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
