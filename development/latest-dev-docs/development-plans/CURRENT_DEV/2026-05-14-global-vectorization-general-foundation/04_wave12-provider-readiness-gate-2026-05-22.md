# Wave12 Provider Readiness Gate Evidence

- 状态：global vectorization readiness partial；不作全局封口声明
- 分支：`codex/devdocs-wave12-vector-provider-readiness`
- Evidence：[wave12-provider-readiness/2026-05-22](../../../automation-runs/wave12-provider-readiness/2026-05-22/README.md)
- Checker：`ops/search-lab/scripts/wave12_provider_readiness_gate.py`
- Unit gate：`main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py`

## 本次闭合的窄切片

- 新增 Wave12 readiness gate，把 Wave10 recorded runtime / benchmark evidence 与当前 live probe status 放进同一份 JSON / README。
- `keyword` / `vector` / `hybrid` 均保留 recorded runtime 和 recorded benchmark coverage；当前 live mode probe 由于运行环境缺少 `lancedb` / `pyarrow` 被标记为 `blocked`，不被误写成 ready。
- `vector` / `hybrid` fallback visibility 继续来自 Wave10 fallback contract：runtime exception 会降级到 keyword，并暴露 `fallback_from` / `fallback_reason`。
- Unsupported claims 明确列出 `semantic_embedding_quality_not_closed` 和 `current_local_index_live_quality_not_closed`，避免 deterministic fixture 被当作生产语义质量证明。

## 本轮实测状态

| mode | recorded runtime | recorded benchmark | current live probe | fallback / blocker |
|---|---:|---:|---|---|
| `keyword` | true | true | `blocked` | `missing_optional_dependency` |
| `vector` | true | true | `blocked` | `missing_optional_dependency`; fallback contract reason remains `RuntimeError` |
| `hybrid` | true | true | `blocked` | `missing_optional_dependency`; fallback contract reason remains `RuntimeError` |

## 对 global vectorization 的影响

- 现在有一个稳定 gate 能区分 recorded vectorization evidence、当前 runtime dependency availability、fallback visibility 和 unsupported claims。
- 本轮不关闭 global vector object schema、embedding version/provenance、生产语义相关性或主搜索 evidence contract。
- 下一步应先让 `lancedb` / `pyarrow` 在目标 runtime 可导入，再复跑 current mode probe；之后再接生产语义 benchmark。

## 最小复跑

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave12_provider_readiness_gate.py --probe-timeout 1.0
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py
```
