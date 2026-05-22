# Wave12 Provider Readiness Gate Evidence

- 状态：OSS node IO readiness partial；不作 live SLA 封口声明
- 分支：`codex/devdocs-wave12-vector-provider-readiness`
- Evidence：[wave12-provider-readiness/2026-05-22](../../../automation-runs/wave12-provider-readiness/2026-05-22/README.md)
- Checker：`ops/search-lab/scripts/wave12_provider_readiness_gate.py`
- Unit gate：`main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py`

## 本次闭合的窄切片

- 新增 Wave12 gate，为 OSS node platform IO 提供一个可消费的 readiness envelope：mode availability、provider availability、live probe status、fallback reason、unsupported claims。
- gate 明确区分两类输入：recorded deterministic evidence 可作为节点契约输入，current live probe status 只能作为本次运行状态输入。
- gate 的 unsupported claims 包含 `oss_node_platform_io_not_closed`，防止节点层把 explicit trace 字段误解成 live SLA-backed primitive。

## 本轮实测状态

| IO 维度 | 可消费字段 | 当前结论 |
|---|---|---|
| mode IO | `keyword` / `vector` / `hybrid` recorded coverage、live probe status、fallback reason | recorded coverage 存在；current live probe 因缺少 `lancedb` / `pyarrow` 为 `blocked` |
| provider IO | explicit provider route、auto exclusion、live provider status、fallback reason | trace contract 存在；SearXNG / YaCy current live probe 为 `unavailable` |
| unsupported claims | provider auto、semantic quality、current live quality、node SLA closure | 均显式输出，不允许上游节点吞掉 |

## 对 OSS node platform IO 的影响

- 节点平台可以开始要求 search/vector provider 输出携带 readiness envelope，而不是只消费结果列表。
- 节点平台不能声明 live provider SLA、production embedding relevance、provider=auto promotion 或 global vector schema closure。
- 后续 node-level replay 应断言 unsupported claims 会沿 IO 传递到节点 trace artifact，避免在 agent / node 层被抹平。

## 最小复跑

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave12_provider_readiness_gate.py --probe-timeout 1.0
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py
```
