# Stage 5 本地运行说明

本说明只覆盖一次性、任务专属的本地演练，不授予生产权限。

## 恢复

1. 使用保留的 Stage4 C9 synthetic snapshot/seed，在独立 PostgreSQL 实例执行 schema restore、Alembic 到 head 和 C9 local projection effect。
2. 用 `pg_dump -Fc` 生成 custom dump；用独立实例 `pg_restore --no-owner --exit-on-error` 恢复。
3. 对 scope、successor values/receipts、projection offsets 做有序 JSON readback 与 SHA256 比对；检查 external receipts/effect attempts 保持为 0。
4. 迁移失败演练只在 disposable migration 实例执行：从 `20260830_000001` forward，预建 `public.runtime_run_projections` 触发 `DuplicateTable`，确认事务保留父 revision，删除冲突表后重新 `alembic upgrade head`。

证据和实测时间见 `recovery/recovery-result.v1.json` 与 `recovery/logs/`。不要把本地 RPO/RTO 外推为生产承诺。

Stage 6 复核后，原始 `recovery/artifacts/source-values.jsonl` 与 `restore-values.jsonl` 保留为历史执行证据；其中第 3、4、12 行的 `event_note` 有一层额外 JSON 转义，不能仅凭两份坏字节相同宣称语义相等。运行 `recovery/repair_jsonl_export.py` 可从现有 JSONL 无损派生修正版：只在 `event_note` 字段移除一层由重复 `json.dumps` 产生的反斜线，不做全局替换，并以嵌套 JSON、C9 `content_digest`、12 行计数和逐行 canonical digest 校验。修正版、摘要与结果见 `recovery/artifacts/*values.corrected.v1.jsonl`、`recovery/logs/08-row-digests-corrected.txt`、`recovery/values-jsonl-correction-result.v1.json` 和独立 `recovery/recovery-correction-result.v1.json`；原始 `recovery/recovery-result.v1.json` 保持不变，此修正未重跑数据库或 Stage 5。

## 可观测性

使用 `observability/compose.yaml` 启动唯一 Compose project `mrw-stage5-observability`，Prometheus scrape backend `/metrics`。需要验证独立 worker 时叠加 `observability/compose.worker-telemetry.yaml`，使用 task-local project（例如 `mrw-stage5-worker-telemetry`）；该 overlay 只挂载当前 `celery_app.py`、worker telemetry、task 和 readback metadata，不构建或发布镜像。认证失败和 token-file 修复记录在 `observability/logs/`；完成后只执行对应 project 的 down/资源清理。`production_observability` 提供三条既有规则和六条 Stage5 本地规则（含 request latency）；本地规则使用 `trigger=1.0/recover=0.0` 或明确的 `0.25s` latency 阈值。`run_alert_rule_probe.py` 用 typed source snapshot 与 controller-derived receipt 做有界 trigger→recover，不能替代 production receipt。`/health/deep` 真实读取 Redis LLEN、DB `SELECT 1`/pool、authority task/tenant scope/capability/step/epoch 和 C9 active offset/closure digest；authority/project 数据缺失时保持 `NOT_OBSERVED/UNKNOWN`，只对真实 mismatch 生成对应 observation。`run_live_runtime_health_receipt_probe.py` 的 68 号证据验证真实来源下 queue `trigger→receipt→recover`。`run_live_worker_chain_probe.py` 通过受保护 deep-health request dispatch task-owned no-op，验证 HTTP → Redis broker → 独立 Celery prefork worker → Redis result/backend，并在第二次 deep-health 和 `/metrics` 回读 worker_event/structured_log/trace。source-overlay 的 `/metrics` 导出 9 条规则的 `unknown/triggered/recovered` one-hot state；runtime-health gauge 仅在实际 runtime-health observation 发生后产生样本。

## 回退

运行 `rollback/run-rollback-fallback-rehearsal.py` 的 disposable no-network probes，核对当前/previous image、config/credential revision、legacy writer closed 和 exact replay counters。不得打开 legacy writer，不得用旧镜像冒充 C9 功能等价。

## Source-overlay 交接清单（2026-09-13）

worker 复核使用保留的 Stage 4 镜像加两个只读 source overlay：`observability/compose.yaml` 将当前 `main.py` 与整个 `production_observability/` 挂到 backend；`observability/compose.worker-telemetry.yaml` 另外将 `celery_app.py`、`services/tasks.py`、`services/task_readback_metadata.py` 以及同一 `production_observability/` 挂到 `celery-worker`。overlay 本身不构建、不发布镜像。以下是交接时实际涉及的工作树字节哈希（目录项逐文件展开）：

| 路径 | 实际关系/职责 | SHA256 |
| --- | --- | --- |
| `main/backend/app/main.py` | backend base overlay；deep-health、metrics、URL credential redaction、worker dispatch/readback | `4894a86e301a09414b24e228138975c09c60ef09cd6f55ea83e990d9346723d9` |
| `main/backend/app/celery_app.py` | worker overlay；Celery app、`worker.py`/`worker_telemetry.py` 安装、task autodiscovery | `4f3f43ff3c002f51af452748345330b491b22d3abd6c14aeaba496328ac94a6e` |
| `main/backend/app/services/tasks.py` | backend + worker overlay；实际 dispatch 的 `task_worker_observability_noop` 与既有业务 tasks | `acaf7fa7a5cd925d62fba28b0be548c042bc123e075d1ea28e0c7903f3880668` |
| `main/backend/app/services/task_readback_metadata.py` | worker overlay；跨进程 runtime readback identity/event 合并 | `b855c9326e61a219ed716b8a6a64cb7d5af2433514c30754d5f4178e7fa1d699` |
| `main/backend/app/services/observability_tasks.py` | image-imported by `celery_app.autodiscover_tasks` (not mounted by this overlay)；保留的独立 probe task 定义，当前 deep-health dispatch 未启用该 task | `4f5ba2f98eba1dc71bf80a2b2021b1d69cf81de890c77154d48ae5851f66e278` |
| `stage5-evidence/observability/compose.yaml` | base overlay、runtime env、backend/worker/Prometheus wiring | `d3eb4c8a4657b5483b9806099d5ce526b8caf01a9428e50181609c0ef3a84414` |
| `stage5-evidence/observability/compose.worker-telemetry.yaml` | worker-only read-only overlay | `025ef6d85dae61fab42d0c5c85bcc857a8d2ca5293eec550a76ed3819b2deded` |
| `main/backend/app/production_observability/__init__.py` | package exports/contracts | `8703e8a8cdaeefe2b6662074ac9d971d213749fb1d3df92a2a0b9ec76b282ab8` |
| `main/backend/app/production_observability/alerts.py` | alert rule/state transitions | `ba65d05a40ab032a76b58b266bc1de2090183a468c804ecdd2fd82249b8e206b` |
| `main/backend/app/production_observability/config.py` | Stage 5 rule/config assembly | `33333aa0b54ab6bb440d21caddc7b7cbff83f3979a67781ae2c8d46f10dce0a9` |
| `main/backend/app/production_observability/contracts.py` | metric/source/receipt contracts | `5482a78cd028286ad743daa115712987f27a2518bfe171c5c6693977252c88bd` |
| `main/backend/app/production_observability/decision.py` | canary stop/continue decision | `651c6e362092fbc6c83db314d8991b9b0a615b888b58a9ac7d12f87fb28dfef3` |
| `main/backend/app/production_observability/errors.py` | observability failure types | `b5c076334cd71beefe136cd53cb33d1cdc1f3f6a8b5f79fdad200e9e72da0b9d` |
| `main/backend/app/production_observability/health.py` | typed runtime-health/authority/projection source reads | `cde11608ffe569f9fd0e81e056c59b157fd4f8580ce6a8c85a1767ca08d31a31` |
| `main/backend/app/production_observability/metrics.py` | backend Prometheus gauges/counters | `481cd8c8331a8d5c48860530d8473ffa2053aea1be07e54ed606392e7523295b` |
| `main/backend/app/production_observability/observations.py` | observation construction/digest | `bb3a0c29652b331a7b4989f333da5b93d4d4d680de2c4c556b9572e6eb7bdb51` |
| `main/backend/app/production_observability/receipts.py` | receipt creation/production-scope validation | `79aacbc79d8fc926fc990359a599f6943057283b7ea5aab8ee8c25252cb77b7b` |
| `main/backend/app/production_observability/runtime.py` | runtime observation/controller and fail-closed recovery | `cafdf3cf59ab2f16a4058c14358403883fa0792da5cc4bd34034dfbafb4d3b15` |
| `main/backend/app/production_observability/worker.py` | Celery lifecycle instrumentation and in-process worker metrics | `6c3796dfb305a2c3ad93f953d7619f9059024d34f33a320a2cfdbf43ad67cac4` |
| `main/backend/app/production_observability/worker_telemetry.py` | Redis bounded worker_event/structured_log/trace transport and `/metrics` projection | `06a7d08f979036d2816cacd2adcddc2264b9835c1420dbc9bc8d2b3e7721786c` |

`celery_app.py` therefore installs both lifecycle instrumentation (`worker.py`) and Redis transport telemetry (`worker_telemetry.py`), then autodiscovers `app.services.tasks` (the enabled no-op dispatch) and `app.services.observability_tasks` (retained, not the current dispatch path). This distinction preserves the two responsibilities without claiming duplicate active collection. Source hashes are handoff identity only; they do not establish release or production authority.

## 权限边界

禁止 push、registry publish、签名、远端部署、生产写入、付费 provider 调用和 Stage 6 启动。现有证据均为本地、非权威结果；监督需独立复核后才可决定下一阶段。
