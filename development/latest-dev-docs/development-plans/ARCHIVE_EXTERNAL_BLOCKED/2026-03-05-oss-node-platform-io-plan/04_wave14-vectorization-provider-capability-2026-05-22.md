# Wave14 Vectorization Provider Capability Evidence

- 状态：OSS node IO provider capability partial；不作 live SLA 封口声明
- 分支：`codex/devdocs-wave14-vectorization-provider-capability`
- Evidence：[wave14-vectorization-provider-capability/2026-05-22](../../../automation-runs/wave14-vectorization-provider-capability/2026-05-22/README.md)
- Checker：`main/backend/scripts/check_wave14_vectorization_provider_capability.py`
- Unit gate：`main/backend/tests/unit/test_wave14_vectorization_provider_capability_unittest.py`

## 本次落地

- Wave14 gate 把 node IO 可消费字段固定为 `retrieval_mode`、`retrieval_family`、`trace.requested_mode`、`trace.executed_mode`、`trace.project_id`、`trace.source_id`、`trace.top_k`。
- node IO 必须继续传播 `trace.fallback_from`、`trace.fallback_reason`、`provider_auto_included=false`、`unsupported_claim_codes` 和 `closure_claim_allowed=false`。
- gate 的 `status=passed` 只表示本地 contract 和 gap reporting 有效；`capability_state=partial` 是本轮结论。

## 对 OSS node platform IO 的影响

- 节点平台可以把 local vectorization capability 当作 repo-controlled 输入 contract 使用。
- 节点平台不能把 external embedding provider、SearXNG / YaCy live quality、provider auto promotion 或 semantic relevance 写成 SLA-backed primitive。
- 后续 node-level replay 应断言 unsupported claim 不会在 graph / agent / node trace 中被抹掉。

## 当前边界

| 维度 | 本轮可用 | 不允许声明 |
|---|---|---|
| local mode IO | `keyword` / `vector` / `hybrid` recorded coverage 与 fallback trace | 当前 runtime 已具备 `lancedb` / `pyarrow` live readiness |
| provider IO | explicit provider route 与 auto exclusion | SearXNG / YaCy live quality sealed |
| embedding IO | provider branch inventory | OpenAI / Azure / Ollama / LiteLLM embedding provider 已 live verified |
| node closure | `closure_claim_allowed=false` 可传播 | OSS node IO live SLA 已封口 |

## 最小复跑

```bash
PYTHONPATH=main/backend python3 main/backend/scripts/check_wave14_vectorization_provider_capability.py
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave14_vectorization_provider_capability_unittest.py
```
