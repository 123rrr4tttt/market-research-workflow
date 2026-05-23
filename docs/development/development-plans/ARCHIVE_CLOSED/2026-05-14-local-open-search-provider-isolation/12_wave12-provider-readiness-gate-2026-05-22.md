# Wave12 Provider Readiness Gate Evidence

- 状态：local open-search provider readiness partial；不作 provider=auto 封口声明
- 分支：`codex/devdocs-wave12-vector-provider-readiness`
- Evidence：[wave12-provider-readiness/2026-05-22](../../../automation-runs/wave12-provider-readiness/2026-05-22/README.md)
- Checker：`ops/search-lab/scripts/wave12_provider_readiness_gate.py`
- Unit gate：`main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py`

## 本次闭合的窄切片

- 新增 Wave12 readiness gate，报告 SearXNG / YaCy 的 explicit route、auto exclusion、current live probe status、result count 和 fallback reason。
- gate 复用既有 provider trace contract，继续固定 `provider_route=explicit:searxng|explicit:yacy`、`provider_family=local_open_search`、`provider_auto_included=false`。
- 当前 live probe 不启动容器，只通过 backend adapter 短超时访问当前本地 endpoint；失败记录为 readiness gap，不伪造成 live closure。

## 本轮实测状态

| provider | route | auto included | current live probe | fallback / blocker |
|---|---|---:|---|---|
| `searxng` | `explicit:searxng` | false | `unavailable` | `ConnectError` / `127.0.0.1:8088` connection refused |
| `yacy` | `explicit:yacy` | false | `unavailable` | `ConnectError` / `127.0.0.1:8090` connection refused |

## 对 provider isolation 的影响

- 已闭合：有可复跑 gate 能把 provider trace contract 与 current provider availability 分开呈现。
- 未闭合：当前本地 SearXNG / YaCy live availability 未达成；本轮不启动容器，不声明真实 provider 质量。
- 未闭合：`provider=auto` promotion 仍不成立；需要独立质量、超时、结果稳定性、人工审阅策略和 operator approval gate。

## 最小复跑

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave12_provider_readiness_gate.py --probe-timeout 1.0
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py
```
