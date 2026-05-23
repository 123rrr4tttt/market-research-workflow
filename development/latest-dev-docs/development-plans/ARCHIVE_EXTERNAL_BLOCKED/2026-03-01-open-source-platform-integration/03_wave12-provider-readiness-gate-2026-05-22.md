# Wave12 Provider Readiness Gate Evidence

- 状态：provider readiness gate partial；不作封口声明
- 分支：`codex/devdocs-wave12-vector-provider-readiness`
- Evidence：[wave12-provider-readiness/2026-05-22](../../../automation-runs/wave12-provider-readiness/2026-05-22/README.md)
- Checker：`ops/search-lab/scripts/wave12_provider_readiness_gate.py`
- Unit gate：`main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py`

## 本次闭合的窄切片

- 新增 Wave12 repo-controlled readiness gate，统一报告 `keyword` / `vector` / `hybrid` mode availability、SearXNG / YaCy provider availability、current live probe status、fallback reason 和 unsupported claims。
- gate 复用 Wave10 deterministic evidence，确认已有记录证据仍显示三种 local-index mode 的 recorded runtime / benchmark coverage 为 true。
- gate 明确保留 open-source provider 隔离：`searxng` / `yacy` 仍为 explicit route，`provider=auto` 不被本轮推广。
- gate 的 `status=passed` 只代表记录证据和报告形状有效；`readiness_state=partial` 是本轮真实结论。

## 本轮实测状态

| 范围 | 当前状态 | fallback / blocker |
|---|---|---|
| `keyword` | `blocked` | `missing_optional_dependency` (`lancedb=None`, `pyarrow=None`) |
| `vector` | `blocked` | `missing_optional_dependency` |
| `hybrid` | `blocked` | `missing_optional_dependency` |
| `searxng` | `unavailable` | `ConnectError` / `127.0.0.1:8088` connection refused |
| `yacy` | `unavailable` | `ConnectError` / `127.0.0.1:8090` connection refused |

## 对 open-source platform integration 的影响

- 可以把 provider readiness 作为平台集成输入字段暴露：调用方能看到 explicit provider route、当前 live probe status、fallback reason 和 unsupported claims。
- 不能把 open-source provider 声明为默认可用平台能力；当前只证明隔离策略和报告契约存在。
- 不能把 deterministic vector fixture 当作生产向量质量证据；平台层仍需要 live provider replay、optional LanceDB runtime 和 embedding provenance 后续证据。

## 最小复跑

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave12_provider_readiness_gate.py --probe-timeout 1.0
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py
```
