# Wave10 Worker6 Vectorization Quality Evidence

- 状态：平台化 / provider evidence partial；不作封口声明
- 分支：`codex/devdocs-wave10-vectorization-quality`
- Evidence：[wave10-vectorization-quality-gate/2026-05-22](../../../automation-runs/wave10-vectorization-quality-gate/2026-05-22/README.md)
- Checker：`ops/search-lab/scripts/wave10_vectorization_quality_gate.py`

## 本次落地

- 新增 Wave10 deterministic quality gate，把 search provider trace、`local_index` runtime smoke、LanceDB benchmark fixture 和 fallback trace contract 串成同一个本地复核入口。
- 固定 open-source search provider 边界：`searxng` / `yacy` 仍要求 explicit route，`provider=auto` 不自动调用 local open-search provider。
- 固定 `local_index` mode quality threshold：`keyword` / `vector` / `hybrid` 三种 mode 均需有 benchmark ranking case、filter case，且 ranking case 至少 3 次 repeat。
- 固定 fallback 可观测字段：当 `vector` 或 `hybrid` runtime path 异常时，adapter fallback 到 keyword，并在 trace 中写入 `fallback_from` 与 `fallback_reason`。

## 不封口项

- 该 gate 不启动容器、不访问外网，不声明当前 SearXNG / YaCy live availability。
- Benchmark fixture 使用 deterministic vectors，只证明 adapter wiring、filter、trace 和稳定排序，不证明生产 embedding semantic quality。
- 全局 vector object schema、embedding provenance、主搜索 evidence contract 仍归 `2026-05-14-global-vectorization-general-foundation` 后续推进。

## 最小验证

```bash
/Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave10_vectorization_quality_gate.py --out-dir development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_wave10_vectorization_quality_gate_unittest.py main/backend/tests/unit/test_local_index_service_unittest.py
```
