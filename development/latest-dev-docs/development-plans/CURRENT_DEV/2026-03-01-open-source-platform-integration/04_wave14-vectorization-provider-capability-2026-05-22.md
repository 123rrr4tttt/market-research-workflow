# Wave14 Vectorization Provider Capability Evidence

- 状态：provider capability partial；不作 external provider 封口声明
- 分支：`codex/devdocs-wave14-vectorization-provider-capability`
- Evidence：[wave14-vectorization-provider-capability/2026-05-22](../../../automation-runs/wave14-vectorization-provider-capability/2026-05-22/README.md)
- Checker：`main/backend/scripts/check_wave14_vectorization_provider_capability.py`
- Unit gate：`main/backend/tests/unit/test_wave14_vectorization_provider_capability_unittest.py`

## 本次落地

- 新增 Wave14 deterministic provider capability gate，只读取 repo-controlled contract 和既有 Wave10 / Wave12 evidence，不启动容器、不访问外网。
- gate 输出 `local_capability`、`external_provider_gap`、`oss_node_platform_io` 和顶层 `closure_claim_allowed=false`，把本地可验证能力与 live / external provider 缺口拆开。
- `keyword` / `vector` / `hybrid` 的 recorded runtime、recorded benchmark 和 fallback visibility 均为 true；这是本地 deterministic capability，不等于生产 embedding semantic quality。
- `searxng` / `yacy` 继续保持 explicit route，`provider=auto` promotion 仍不允许。

## 对 open-source platform integration 的影响

- 平台层可以消费本地 vectorization contract：mode 集合、retrieval trace、fallback reason 和 deterministic vector provider boundary。
- 平台层不能把 OpenAI / Azure / Ollama / LiteLLM embeddings、SearXNG / YaCy live quality 或 `provider=auto` 默认能力写成已封口。
- 本轮实测仍显示当前 runtime 缺少 `lancedb` / `pyarrow`，SearXNG / YaCy live probe 来自 Wave12 evidence，状态为 unavailable / `ConnectError`。

## 保留缺口

- `external_embedding_provider_live_not_verified`
- `provider_auto_promotion_not_allowed`
- `local_open_search_live_quality_not_sealed`
- `semantic_embedding_quality_not_proven`
- `oss_node_platform_io_sla_not_closed`

## 最小复跑

```bash
PYTHONPATH=main/backend python3 main/backend/scripts/check_wave14_vectorization_provider_capability.py
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave14_vectorization_provider_capability_unittest.py
```
