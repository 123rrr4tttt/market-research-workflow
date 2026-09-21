# r13x 本地启动、停止与恢复说明

本说明只操作 r13x 已保留的本地制品与一次性本地运行资源。它不执行构建、拉取、GitHub/registry/签名写入或远端部署，也不建立发布权限。

## 1. 固定输入

```bash
export R13X_ROOT=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260912-v4-r13x
export R13X_CAND="$R13X_ROOT/candidate"
export R13X_EVID=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13x
export R13X_RUNTIME_EVID="$R13X_EVID/runtime"
export R13X_BACKEND_IMAGE=mrw-local/r13x-candidate-backend:8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2
export R13X_FRONTEND_IMAGE=mrw-local/r13x-candidate-frontend:8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2
export R13X_MIGRATION_IMAGE=mrw-local/r13x-candidate-migration-runner:8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2
export R13X_COMPOSE_PROJECT=mrw-r13x-runtime
```

候选身份必须为 commit `8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2`、tree `ce7c67c831b51f9d64b4c2f1a470a724a50b19df`，且 candidate/replay 均 clean：

```bash
git -C "$R13X_CAND" rev-parse HEAD 'HEAD^{tree}'
git -C "$R13X_CAND" status --short
git -C "$R13X_ROOT/replay" status --short
(cd "$R13X_EVID/artifacts" && shasum -a 256 -c SHA256SUMS)
```

本地运行使用以下 Compose 参数；不得加 `--build`，不得允许浮动 pull：

```bash
R13X_COMPOSE=(docker compose -p "$R13X_COMPOSE_PROJECT" \
  -f "$R13X_CAND/main/ops/docker-compose.yml" \
  -f "$R13X_RUNTIME_EVID/compose.override.yml" \
  --profile modern-ui)
```

运行时默认值已由 Compose 固定为本地 PostgreSQL、Elasticsearch、Redis 地址。可调但非必填的变量名包括 `ES_JAVA_OPTS`、`DATABASE_URL`、`ES_URL`、`REDIS_URL`、`SEARXNG_BASE_URL`、`YACY_BASE_URL`、`YACY_RESOURCE_MODE` 和 `MODERN_FRONTEND_URL`。真实 provider 验证只从当前项目 `main/backend/.env` 有界提取 `LLM_PROVIDER`、`OPENAI_API_KEY`、`OPENAI_API_BASE` 与可选 `OPENAI_MODEL`；不得复制 `.env` 到候选、证据目录或镜像。r13x 的 exact runtime override 将 `OPENAI_API_KEY` 留空，因此历史 full-stack deep health 的 provider 项为 degraded；本轮真实 provider 由独立 AgentCore gate 闭合，未重跑整个 stack。

## 2. 缺失 tag 时恢复

先校验制品索引，再从 canonical OCI archive 恢复。网络重建不属于恢复：

```bash
(cd "$R13X_EVID/artifacts" && shasum -a 256 -c SHA256SUMS)
docker load -i "$R13X_EVID/artifacts/candidate/backend/image.oci.tar"
docker load -i "$R13X_EVID/artifacts/candidate/frontend/image.oci.tar"
docker load -i "$R13X_EVID/artifacts/candidate/migration-runner/image.oci.tar"
docker image inspect "$R13X_BACKEND_IMAGE" --format '{{.Id}}'
docker image inspect "$R13X_FRONTEND_IMAGE" --format '{{.Id}}'
docker image inspect "$R13X_MIGRATION_IMAGE" --format '{{.Id}}'
```

期望 image IDs：

- backend: `sha256:d72688f24fb867ae2e0e9310cfc9ec25aac649a8da69130ee26469c0bd37c2ef`
- frontend: `sha256:f5641ba6d2b50135da1c9c9c3edfd067ed90ecfb37bcb8f0c7580b2e00aaa915`
- migration-runner: `sha256:3b409669bb8248f738c1133f9458d73725951140c0eae938064d469045960509`

三角色 OCI manifest digests 分别为 backend `sha256:dd4b1f3b512da6d013feb7f5925f343e5a639263b037d5a81445bfa2f8c93c0b`、frontend `sha256:a5b09b80fde1d2bbeb31c54137292e4a4bca7e2cf1f665b858f2d68a05c54e5c`、migration-runner `sha256:535ac0b1b06ed507e14bc9a1bfc96c27d4522bada61cbc63a9fa959721b59bc5`。Docker image ID 与 OCI manifest digest 是不同身份，不得互换。

基础服务仍依赖本机已有的 `ankane/pgvector:latest`、`docker.elastic.co/elasticsearch/elasticsearch:8.15.3` 与 `redis:7.4`；r13x 未为这三项建立 canonical archive。`--pull never` 会在它们缺失时失败关闭。

## 3. 启动和迁移

```bash
cd "$R13X_CAND"
"${R13X_COMPOSE[@]}" up -d --no-build --pull never --wait --wait-timeout 120 db

docker run --rm --name mrw-r13x-migration-upgrade \
  --platform linux/amd64 \
  --network "${R13X_COMPOSE_PROJECT}_default" \
  -e DATABASE_URL='postgresql+psycopg2://postgres:postgres@db:5432/postgres' \
  "$R13X_MIGRATION_IMAGE"

"${R13X_COMPOSE[@]}" up -d --no-build --pull never --wait --wait-timeout 300 \
  db es redis backend celery-worker frontend-modern
```

默认 migration entrypoint 已验证执行 `alembic upgrade head`，数据库 head 为 `20260905_000001`，公开表数为 67。`alembic heads` console script 的 namespace introspection 限定不影响已通过的默认 upgrade；需要查看 heads 时使用镜像内 `python -m alembic heads`。

## 4. 状态与 health

```bash
"${R13X_COMPOSE[@]}" ps --format json
curl -fsS http://127.0.0.1:18132/api/v1/health
curl -fsS http://127.0.0.1:18132/api/v1/health/deep
curl -fsS http://127.0.0.1:15132/
curl -fsS http://127.0.0.1:15132/api/v1/health
curl -fsS http://127.0.0.1:15132/api/v1/health/deep
```

只有 backend `127.0.0.1:18132` 和 frontend `127.0.0.1:15132` 对宿主机开放；db、Elasticsearch 和 Redis 只在 Compose 网络内。历史 r13x receipt 中六个服务均运行，db/es/redis/backend/celery-worker healthy，浅 health 为 `ok`，frontend 与静态资源为 HTTP 200；deep health 仅因当时未注入 provider key 而 degraded。本轮独立真实 provider 报告见 `local-delivery/provider-live-readback.r13x.json`。

## 5. 停止、保留数据与彻底清理

仅停止并保留命名卷中的 PostgreSQL/Elasticsearch 数据：

```bash
cd "$R13X_CAND"
"${R13X_COMPOSE[@]}" down --remove-orphans --timeout 30
```

删除本次一次性 runtime 的容器、网络和命名卷：

```bash
cd "$R13X_CAND"
"${R13X_COMPOSE[@]}" down --volumes --remove-orphans --timeout 30
```

第二条命令会删除 `mrw-r13x-runtime_*` 的 PostgreSQL、Elasticsearch 和 `codex_auth` 卷；Redis 未配置持久卷。它不会删除三角色 tag、六个 OCI archives 或三个 canonical layouts。不得执行 `docker system prune`、`docker image prune` 或任何广域清理。

三角色 tag、canonical/replay archives 和 canonical layouts 继续保留，直到 Supervisor 验收、明确 supersession 或明确放弃。未来如清理，只能逐项删除 `retained-artifact-lifecycle.r13x.json` 列出的精确对象，并先保留 checksum index 与最终结果。

## 6. 延后的发布事项

以下均未执行且未获授权：GitHub exact-SHA push/CI/required-check enforcement、registry publish/promotion/immutability readback、签名与 transparency log、actual release manifest、完整 stock R2、staging/production 部署。它们不阻塞本地交付，但仍是未来正式发布前置。
