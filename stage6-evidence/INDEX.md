# Stage 6 本地独立验收索引

范围：`LOCAL_INDEPENDENT_REVIEW / NOT_AUTHORITY / RELEASE_DEFERRED`。

主结果：[stage6-stage-result.json](stage6-stage-result.json)。本次复核消费 Stage4/Stage5 已有真实证据，未重跑 Stage3 双重构建、安全全套或 Stage4/5 矩阵；只执行了 checksum、Docker image identity、JSON 一致性、`py_compile` 与 `git diff --check` 等有界检查。

Stage6 验收后清理记录：[post-acceptance-cleanup.v1.json](post-acceptance-cleanup.v1.json)。25 个本任务临时/可重建文件（371764 bytes）已移入可恢复 Trash；无 Docker 对象删除、无全局 prune，四个 Stage6 交付文件及全部 Stage4/5 输入保留。

| 复核面 | 结论 | 主要证据 |
| --- | --- | --- |
| Stage4 identity/effect | `PASS_LOCAL_STAGE4_NOT_AUTHORITY` | `stage4-evidence/stage4-stage-result.json`、`runtime/s4-c9-effect-live.json`、`runtime/s4-c9-effect-focused.json` |
| Stage5 observability | `PASS_LOCAL_SUBPACKAGE_WITH_EXPLICIT_RUNTIME_BOUNDARY` | `stage5-evidence/observability/observability-work-package-result.json`、`logs/68-gap-closure2-live-runtime-health-receipt.json`、`logs/72-gap-closure3-alert-state-count.json` |
| Worker chain | `PASS_LOCAL_LIVE_WORKER_CHAIN_NOT_AUTHORITY` | `stage5-evidence/observability/live-worker-chain-result.v1.json`、`worker-logs-traces-closure-result.v1.json` |
| Recovery/migration | `PASS_LOCAL_RECOVERY_DRILL_NOT_AUTHORITY`（values JSONL 3 行格式缺口） | `stage5-evidence/recovery/recovery-result.v1.json`、`recovery/logs/17-migration-failure.log`、`recovery/logs/21-forward-fix-upgrade.log` |
| Rollback | `PASS_LOCAL_ROLLBACK_REHEARSAL_NOT_AUTHORITY` | `stage5-evidence/rollback/rollback-fallback-result.v1.json`、`focused-route-recheck.v1.json` |
| Cleanup | `CLEANUP_RESULT_S5_ACCEPTED` | `stage5-evidence/post-acceptance-cleanup.v1.json` |

当前 manifest：Stage4 runtime 132 项、Stage5 root 214 项、Stage5 observability 153 项，均逐项 `sha256sum -c` 通过。Stage5 root manifest 的当前 hash 是 `247ea799067f7cbf8d5846242b7c16fac9fd7afcc834479e413eefb79f05a33c`，包含验收后清理与 values JSONL correction 记录；此前进度中的旧 hash 仅作历史记录。

明确保留的上限：provider 故障是本地模拟；外部 sink 未调用；恢复数据是合成 C9 数据；RPO/RTO 是单次本地测量；HTTP production-receipt recovery 未观察到；深度健康可能因缺少 task-local `OPENAI_API_KEY` 保持 degraded；worker telemetry 是有界 Redis 观察流。一次 live-worker Compose 快照早于最终 overlay，但 governance.py 当前源与镜像字节相同且不在 worker autodiscovery 路径，故移除该冗余挂载无观察到的 worker 影响；仍不宣称对最终 overlay 的 exact-byte replay。Stage4 commit 依赖原 r13x candidate/replay 仓库、保留镜像与构建映射而非当前 Git 对象库；凭据只做定向脱敏核对，未宣称全量 secret scan。上述边界不阻塞本地 Stage6，但不构成生产授权。

原始 source/restore `values.jsonl` 第 3、4、12 行的双重转义已保留为历史证据；Stage5 owner 通过字段级单层无损修复生成 corrected v1 文件，12/12 行严格解析、canonical/content digest 与 value ID 逐行一致，且 214 项根 manifest fresh 校验通过。另有 Stage4 历史计数（131/129）与当前 132 项 manifest 的差异；当前 manifest 已 fresh 校验通过，旧日志不作当前证明。

Stage6 完成后停止，不启动 Stage7–9，不执行 push、registry、签名、远端部署、canary 或生产写入。
