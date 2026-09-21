# Stage 5 本地证据索引

范围：`LOCAL_STAGE5_ONLY / NOT_AUTHORITY / RELEASE_DEFERRED`。

主结果：[stage5-stage-result.json](stage5-stage-result.json)。六类本地告警规则、controller-derived receipt trigger→recover 及真实 collector 的 gauge/state 抓取已补齐；HTTP 层仍保持无 production receipt 时 fail-closed。三个工作包结果如下：

| 工作包 | 状态 | 主证据 |
| --- | --- | --- |
| 可观测性 | `PASS_LOCAL_SUBPACKAGE_WITH_EXPLICIT_RUNTIME_BOUNDARY` | [observability-work-package-result.json](observability/observability-work-package-result.json) |
| 恢复 | `PASS_LOCAL_RECOVERY_DRILL_NOT_AUTHORITY` | [recovery-result.v1.json](recovery/recovery-result.v1.json) |
| 回退 | `PASS_LOCAL_ROLLBACK_REHEARSAL_NOT_AUTHORITY` | [rollback-fallback-result.v1.json](rollback/rollback-fallback-result.v1.json) |

恢复演练证明了 pg_dump/pg_restore 后 scope、generation、12 个 successor values、6 个 receipts、2 个 projection offsets 的一致性；有序行 JSON 摘要哈希逐表相等。迁移实例实际经历 `DuplicateTable` 失败，清理冲突后 forward-fix 到 `20260905_000001`，数据计数保持不变。RPO 实测为 0 行损失；单次本地 RTO 为 577 ms restore、699 ms 含 readback。

Stage 6 复核发现原始 `recovery/artifacts/source-values.jsonl` 与 `restore-values.jsonl` 第 3、4、12 行存在 `event_note` 的额外 JSON 转义层；原始字节保留不改。使用 [repair_jsonl_export.py](recovery/repair_jsonl_export.py) 做字段级、单层、非全局反斜线修复，生成 [source-values.corrected.v1.jsonl](recovery/artifacts/source-values.corrected.v1.jsonl) 与 [restore-values.corrected.v1.jsonl](recovery/artifacts/restore-values.corrected.v1.jsonl)。12/12 行严格解析，逐行 canonical digest、`content_digest`、值 ID 与行数均一致；无数据库恢复或 Stage 5 重跑。完整记录见 [values-jsonl-correction-result.v1.json](recovery/values-jsonl-correction-result.v1.json)、独立 [recovery-correction-result.v1.json](recovery/recovery-correction-result.v1.json) 与 [08-row-digests-corrected.txt](recovery/logs/08-row-digests-corrected.txt)。原始 `recovery-result.v1.json` 保持不变。

外部 provider/sink 没有被调用：恢复库中 external receipts 和 runtime effect attempts 均为 0，外部 sink 继续是 `DECLARED_LOSS_NO_CALL`。

可观测性已真实 scrape `/metrics`，并保留初次认证失败、修复后 target `up`、HTTP 403 domain rejection、9 条规则的 controller probe，以及 source-overlay 的新 gauge/state 证据。Prometheus 查询得到 27 个 alert-state series（9 条规则 × `unknown/triggered/recovered`）。`/health/deep` 真实读取 Redis LLEN、DB `SELECT 1`/pool 与 runtime binding；authority 读取现在只在 task/tenant/project-scope/capability/step/epoch 完整且一致时报告 observed，缺失时为 `NOT_OBSERVED/UNKNOWN`，真实错配才报告 mismatch。projection drift 只由 C9 active offset digest 与当前 closure digest 的真实比较决定；无 project/source/offset 时为 `NOT_OBSERVED/UNKNOWN`，不生成 metric。队列故障证据显示 gauge `1→0`，无 receipt 时 alert 仍 fail-closed 保持 triggered。`68-gap-closure2-live-runtime-health-receipt.json` 进一步证明真实来源下 controller-derived receipt 的 queue trigger→recover。新增 `observability/live-worker-chain-result.v1.json` 证明真实 HTTP deep-health request → Redis broker → 独立 Celery prefork worker → Redis result/backend 回读；worker_event、structured_log、trace 均按 request_id/run_id/project_key/candidate_id/trace_id 关联并由 backend `/metrics` 导出 Redis-backed worker metric。provider failure 明确为本地模拟，无外部 provider 调用；HTTP 层 production-receipt recovery 仍未观察到。

回退演练覆盖 backend/frontend、config/credential revision 和 successor/legacy route 边界；legacy writer 保持关闭，exact replay 不增加 effect/journal/receipt/idempotency。路由 focused recheck 为 `21 passed, 2 warnings`。

所有 Stage 5 专属容器、卷和网络已清理；未执行全局 Docker prune，`ops-scrapyd-1` 及宿主备份/未知卷未触碰。Stage 6 只由监督独立验收后启动。

完整文件哈希见 [SHA256SUMS](SHA256SUMS)。
