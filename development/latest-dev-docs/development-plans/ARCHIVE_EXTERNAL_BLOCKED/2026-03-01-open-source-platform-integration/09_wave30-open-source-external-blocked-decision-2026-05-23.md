# Wave30 Open Source Platform External-Blocked Decision

日期：2026-05-23

状态：`external_blocked` / `wave30_checked`

## 结论

`2026-03-01-open-source-platform-integration` 迁入 `ARCHIVE_EXTERNAL_BLOCKED`。

本目录在 Wave27/Wave29 后保留在 `CURRENT_DEV` 的原因是依赖两个相邻边界：

- OSS-node platform IO boundary：Wave29 已迁入 `ARCHIVE_EXTERNAL_BLOCKED`。
- Global vector repo-local contract：Wave30 已由 `wave30-vector-closure-gate.v1` 关闭。

因此，本目录不再拥有独立仓内 blocker。剩余条件全部来自 live provider、local open-search quality、semantic relevance 或外部 runtime/SLA evidence。

## 仓内已封证据

- Wave8/Wave10/Wave12/Wave14/Wave18/Wave19 provider/vectorization deterministic gates 仍可作为历史 evidence。
- OSS-node slice 已在 Wave29 迁入 `ARCHIVE_EXTERNAL_BLOCKED`：[`2026-03-05 OSS Node Platform IO Plan`](../2026-03-05-oss-node-platform-io-plan/08_wave29-oss-node-vector-manifest-replay-2026-05-23.md)。
- Global vector repo-local blocker 已在 Wave30 清零：[`wave30-vector-closure-gate/2026-05-23`](../../../automation-runs/wave30-vector-closure-gate/2026-05-23/README.md)。

## 仍需外部条件

- `external_embedding_provider_live_not_verified`
- `local_open_search_live_quality_not_sealed`
- `semantic_embedding_quality_not_proven`
- `oss_node_platform_io_sla_not_closed`

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave30_vector_closure_gate.py --out-dir development/latest-dev-docs/automation-runs/wave30-vector-closure-gate/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_wave27_vectorization_closure_gate_unittest.py \
  main/backend/tests/unit/test_wave29_vector_schema_alignment_gate_unittest.py \
  main/backend/tests/unit/test_wave30_vector_closure_gate_unittest.py
```
