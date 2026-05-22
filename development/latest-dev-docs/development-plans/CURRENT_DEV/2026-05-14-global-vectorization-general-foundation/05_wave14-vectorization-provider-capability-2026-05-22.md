# Wave14 Vectorization Provider Capability Gate

- 状态：global vectorization provider capability partial；不作全局封口声明
- 分支：`codex/devdocs-wave14-vectorization-provider-capability`
- Evidence：[wave14-vectorization-provider-capability/2026-05-22](../../../automation-runs/wave14-vectorization-provider-capability/2026-05-22/README.md)
- Checker：`main/backend/scripts/check_wave14_vectorization_provider_capability.py`
- Unit gate：`main/backend/tests/unit/test_wave14_vectorization_provider_capability_unittest.py`

## Contract 内容

本次新增的 Wave14 gate 在 deterministic / no-network / no-container 边界内复核三组能力：

1. local capability：`LOCAL_INDEX_QUERY_MODES=keyword|vector|hybrid`、Wave10 recorded runtime / benchmark coverage、fallback trace visibility，以及 repo deterministic hash vector provider。
2. external provider gap：OpenAI / Azure / Ollama / LiteLLM embedding provider branch 只记录为代码路径，未做 live verification；SearXNG / YaCy 仍 explicit-only。
3. OSS node platform IO：节点可消费 local trace 字段，但必须传播 unsupported claim 与 `closure_claim_allowed=false`。

## 验收结果

- `contract_version=wave14-vectorization-provider-capability.v1`
- `scope=deterministic_repo_contract_no_network_no_container_start_no_external_provider_seal`
- `status=passed`
- `capability_state=partial`
- `local_capability.status=passed`
- `closure_claim_allowed=false`

## 仍未封口

- external embedding provider live probe：未验证。
- SearXNG / YaCy live quality：未封口，`provider=auto` promotion 不允许。
- semantic embedding quality：deterministic vector fixture 不证明生产语义相关性。
- global vector object schema / embedding provenance / node SLA：仍是 CURRENT_DEV 后续工作。

## 最小复跑

```bash
PYTHONPATH=main/backend python3 main/backend/scripts/check_wave14_vectorization_provider_capability.py
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave14_vectorization_provider_capability_unittest.py
```
