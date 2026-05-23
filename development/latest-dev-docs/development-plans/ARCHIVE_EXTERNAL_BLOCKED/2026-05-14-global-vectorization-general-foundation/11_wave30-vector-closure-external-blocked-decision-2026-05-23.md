# Wave30 Vector Closure External-Blocked Decision

日期：2026-05-23

状态：`external_blocked` / `wave30_checked`

## 结论

`2026-05-14-global-vectorization-general-foundation` 迁入 `ARCHIVE_EXTERNAL_BLOCKED`。

Wave30 已关闭本目录上一次保留在 `CURRENT_DEV` 的三个仓内 blocker：

- `retrieval_runs_branches_hits_persistence_not_implemented`
- `embedding_qdrant_pgvector_payload_provenance_not_unified`
- `agent_matrix_and_main_search_schema_not_joined`

这不是 `ARCHIVE_CLOSED`。本目录仍不声明 live embedding provider、生产语义质量或 production vector quality 已完成；这些条件必须由外部 runtime / provider / production evidence 补齐后才能重新判断。

## 仓内已封证据

- `/api/v1/search` 现在返回 `retrieval_run_id`、`search_branches`、`branch_hit_details`、`retrieval_run` 与 JSONL readback 摘要。
- Qdrant 与 pgvector fallback 输出统一 `payload_provenance` / `global_vector_object.provenance` 字段，覆盖 provider/backend、embedding model/version、source/reference、score 与 fallback reason。
- Agent matrix `source.web.search` 输出与主搜索一致的 `evidence_hits` / `global_vector_object` schema，并生成 `agent_matrix` retrieval run。
- Wave30 deterministic gate 输出：[`wave30-vector-closure-gate/2026-05-23`](../../../automation-runs/wave30-vector-closure-gate/2026-05-23/README.md)。

## 仍需外部条件

- `external_embedding_provider_live_not_verified`
- `semantic_embedding_quality_not_proven`
- `production_vector_quality_not_proven`

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave30_vector_closure_gate.py --out-dir development/latest-dev-docs/automation-runs/wave30-vector-closure-gate/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_search_vector_contracts_unittest.py \
  main/backend/tests/unit/test_search_retrieval_runs_readback_unittest.py \
  main/backend/tests/unit/test_wave30_vector_closure_gate_unittest.py \
  main/backend/tests/contract/test_vectorization_contract_unittest.py \
  main/backend/tests/core_business/test_search_core_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_core_unittest.py -k "source_web_search"
```
