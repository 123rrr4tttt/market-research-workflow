# Wave10 Worker6 Vectorization Quality Gate

- 状态：deterministic quality contract partial；不作全局封口声明
- 分支：`codex/devdocs-wave10-vectorization-quality`
- Evidence：[wave10-vectorization-quality-gate/2026-05-22](../../../automation-runs/wave10-vectorization-quality-gate/2026-05-22/README.md)
- Checker：`ops/search-lab/scripts/wave10_vectorization_quality_gate.py`
- Unit gate：`main/backend/tests/unit/test_wave10_vectorization_quality_gate_unittest.py`

## Contract 内容

本次新增的 Wave10 gate 在不启动容器、不访问外网的前提下复核四组 evidence：

1. search provider trace：local open-search providers 只能 explicit route，`provider=auto` 不调用 `searxng` / `yacy`。
2. `local_index` runtime smoke：读取既有 LanceDB captured evidence，确认 `keyword` / `vector` / `hybrid` 均返回预期 top row 且无 fallback。
3. benchmark quality threshold：读取受控 benchmark fixture，要求三种 mode 都有 ranking/filter coverage，ranking case 至少 3 次 repeat，trace 包含 `project_id`、`source_id`、`top_k` 与 mode 字段。
4. fallback reason fixture：用 fake LanceDB table 确认 `vector` / `hybrid` runtime exception 会 fallback 到 keyword，并输出 `fallback_from` 与 `fallback_reason`。

## 验收结果

- `contract_version=wave10-vectorization-quality-gate.v1`
- `scope=deterministic_local_fixture_no_network_no_container_start`
- `status=passed`
- `quality_thresholds.required_modes=keyword, vector, hybrid`
- `local_index_fallback_contract.status=passed`

## 仍未封口

- `current_container_availability_not_replayed`：本 gate 不启动或探测 SearXNG / YaCy live container。
- `semantic_embedding_quality_not_proven`：benchmark fixture 使用 deterministic vectors，不证明生产 embedding model 的语义相关性。
- `global_vector_contract_not_closed`：统一 vector object schema、embedding provenance、主搜索 evidence contract 仍是本目录后续任务。

## 最小复跑

```bash
/Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave10_vectorization_quality_gate.py --out-dir development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_wave10_vectorization_quality_gate_unittest.py main/backend/tests/unit/test_local_index_service_unittest.py
```
