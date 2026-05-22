# Wave18 Open Search Health Artifact Evidence

- 状态：local open-search health artifact partial；不作 SearXNG / YaCy live closure 声明
- 分支：`codex/devdocs-wave18-open-search-health-artifact`
- Checker：`main/backend/scripts/check_open_search_health_artifact.py`
- Unit gate：`main/backend/tests/unit/test_open_search_health_artifact_unittest.py`
- Evidence：[wave18-open-search-health-artifact/2026-05-22](../../../automation-runs/wave18-open-search-health-artifact/2026-05-22/README.md)

## 本轮闭合的窄切片

- 新增 Wave18 health artifact checker，把 Wave12 provider readiness、Wave15 runtime boundary、launcher settings、Docker compose 服务期望和 backend search provider 代码统一记录为可机器检查 JSON。
- checker 明确记录 configured endpoint、compose/service expectation、current service status、`live_probe_open=true`、`service_not_started_connect_error`、`closure_claim_allowed=false`。
- checker 只读取 Docker compose 当前状态，不启动容器；Docker daemon 不可用时记录为当前 service status 的 `unknown`，不推断服务已运行。
- 单元测试覆盖 stopped-service connect error、running live query 仍为 `live_query_unsealed`、以及 stopped service 不允许 live closure claim。

## 本轮实测状态

命令：

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_open_search_health_artifact.py --probe-timeout 0.2 --write-output development/latest-dev-docs/automation-runs/wave18-open-search-health-artifact/2026-05-22/open_search_health_artifact.json
```

结果摘要：

```text
OK open_search_health_artifact=passed health_state=partial closure_claim_allowed=false live_probe_open=true searxng=service_not_started_connect_error:unavailable yacy=service_not_started_connect_error:unavailable
```

| provider | endpoint | current boundary | live status | service status | closure claim |
|---|---|---|---|---|---:|
| `searxng` | `http://127.0.0.1:8088` | `service_not_started_connect_error` | `unavailable` | Docker daemon unavailable, recorded as `unknown` | false |
| `yacy` | `http://127.0.0.1:8090` | `service_not_started_connect_error` | `unavailable` | Docker daemon unavailable, recorded as `unknown` | false |

## 与 Wave12 / Wave15 的关系

- Wave12 已记录 SearXNG / YaCy 当前 endpoint connection refused，并保留 readiness gap。
- Wave15 已把 configured endpoint、service not started / connect error、`live_query_unsealed` 拆开，并保留 external runtime gap。
- Wave18 在此基础上增加 compose/launcher/provider-code health artifact，确保后续 review 能直接检查配置入口、服务期望、当前服务状态和 no-closure facts。

## 未闭合项

- 当前 SearXNG / YaCy live availability 未闭合。
- SearXNG / YaCy live result quality、freshness、latency stability、timeout policy、operator approval gate 未闭合。
- `provider=auto` promotion 仍不成立。
- Docker daemon 当前不可用，因此本轮没有运行或验证容器进程，只记录该 current service status。

## 最小复跑

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_open_search_health_artifact.py --probe-timeout 0.2
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_open_search_health_artifact_unittest.py
```
