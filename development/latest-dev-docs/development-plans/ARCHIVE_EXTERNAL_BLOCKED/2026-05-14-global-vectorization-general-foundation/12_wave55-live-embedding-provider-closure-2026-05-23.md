# Wave55 Live Embedding Provider Closure

日期：2026-05-23

状态：`repo_local_live_provider_closed` / `production_quality_still_open`

## 结论

Wave55 新增一个可执行、无网络、无密钥的 repo-local embedding provider，并把 `local_index` 的 LanceDB vector/hybrid 写入与查询路径改为使用该 provider，而不是继续把 deterministic vector fixture 当作 provider 证据。

本轮可以关闭的范围是：

- `external_embedding_provider_live_not_verified`：仅在 repo-local provider path 范围内关闭。该 provider 是仓内代码、可执行、可单测、可 readback，不声明外部 API/key/provider 已验证。

仍保持打开：

- `semantic_embedding_quality_not_proven`
- `production_vector_quality_not_proven`

原因：Wave55 的质量门是受控语料 top-k/readback gate，只证明本地 provider、vector retrieval wiring、provenance 与 retrieval-run readback，不证明生产语料或外部 embedding model 的语义质量。

后续更新：Wave56 已在 repo-local production-like evaluation set 范围内关闭 `semantic_embedding_quality_not_proven`，但 `production_vector_quality_not_proven` 仍需真实生产流量或生产语料 replay。

## 落地

- `main/backend/app/services/local_index/embedding_provider.py` 新增 `RepoLocalHashingEmbeddingProvider`。
- `main/backend/app/services/local_index/adapters/lancedb_adapter.py` 在 upsert/search 中写入并读回 provider/model/version/dim/vector_version。
- `ops/search-lab/scripts/wave55_live_embedding_provider_gate.py` 串联 provider readback、受控质量 benchmark、`search_evidence_hit.v1` 与 `search_retrieval_run.v1` readback。

## 验证命令

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave55_live_embedding_provider_gate.py --out-dir development/latest-dev-docs/automation-runs/wave55-live-embedding-provider/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_local_index_service_unittest.py \
  main/backend/tests/unit/test_wave55_live_embedding_provider_gate_unittest.py \
  main/backend/tests/unit/test_search_vector_contracts_unittest.py \
  main/backend/tests/unit/test_search_retrieval_runs_readback_unittest.py \
  main/backend/tests/unit/test_wave30_vector_closure_gate_unittest.py \
  main/backend/tests/contract/test_vectorization_contract_unittest.py
```

## 边界

不改全局 manifest/index。本文件只记录 Wave55 worker B1 的局部闭环，顶层导航与归档合并由 main agent 处理。
