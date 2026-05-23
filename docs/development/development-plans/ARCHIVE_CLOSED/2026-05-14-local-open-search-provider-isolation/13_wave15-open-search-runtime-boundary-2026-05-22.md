# Wave15 Open Search Runtime Boundary Evidence

- 状态：local open-search runtime boundary partial；external runtime gap 保留
- 分支：`codex/devdocs-wave15-open-search-runtime-boundary`
- Checker：`main/backend/scripts/check_open_search_runtime_boundary.py`
- Unit gate：`main/backend/tests/unit/test_open_search_runtime_boundary_unittest.py`

## 本轮闭合的窄切片

- 新增 repo-local runtime boundary checker，把 SearXNG / YaCy 的三类状态拆开记录：configured endpoint、service not started / connect error、live query unsealed。
- checker 读取既有 Wave6-9 topic evidence、Wave12 readiness summary、offline provider trace contract 和真实容器 replay summary，但不启动 Docker 容器。
- checker 继续固定 `provider_route=explicit:searxng|explicit:yacy`、`provider_family=local_open_search`、`provider_auto_included=false`、`provider_auto_promotion_allowed=false`、`closure_claim_allowed=false`。
- 即使当前 endpoint 返回 live result，也只归类为 `live_query_unsealed`，不把单次查询提升为 SearXNG / YaCy live closure。

## Runtime Boundary 分类

| 分类 | 含义 | 封口影响 |
|---|---|---|
| `configured_endpoint_only` | repo 配置面存在 endpoint，但本轮未跑 live probe | 只证明配置入口存在 |
| `service_not_started_connect_error` | endpoint 已配置，但当前服务未启动或不可连接 | 记录 external runtime gap |
| `service_unreachable_timeout` | endpoint 已配置，但当前探测超时 | 记录 external runtime gap |
| `endpoint_responded_with_http_error` | endpoint 响应 HTTP 错误 | 记录 runtime contract gap |
| `live_query_unsealed` | bounded live query 返回或空结果，但质量/稳定性未达标 | 不允许 closure claim |

## 本轮实测

命令：

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_open_search_runtime_boundary.py --probe-timeout 0.2
```

结果摘要：

```text
OK open_search_runtime_boundary=passed boundary_state=partial external_runtime_gap=retained closure_claim_allowed=false searxng=service_not_started_connect_error:unavailable yacy=service_not_started_connect_error:unavailable
```

| provider | endpoint | route | auto included | current boundary | live status | closure claim |
|---|---|---|---:|---|---|---:|
| `searxng` | `http://127.0.0.1:8088` | `explicit:searxng` | false | `service_not_started_connect_error` | `unavailable` | false |
| `yacy` | `http://127.0.0.1:8090` | `explicit:yacy` | false | `service_not_started_connect_error` | `unavailable` | false |

## 与 Wave6 / Wave12 证据的关系

- Wave6-9 证据已要求本主题保留 no closure claim，不启动或保留长期运行的 SearXNG / YaCy 容器。
- Wave12 readiness gate 已记录当前本机 endpoint connection refused，并把失败作为 readiness gap，而不是 gate failure。
- 本轮 checker 把 Wave12 的 current probe status 固化成独立 runtime boundary gate：配置可存在、服务可未启动、live 查询可发生，但三者都不自动推导为 provider=auto promotion 或 live quality closure。
- 既有真实容器 replay 仍作为历史 replay 证据保留；它证明当容器被显式启动时 adapter trace 能通过，不证明当前外部 runtime 正在运行。

## 未闭合项

- SearXNG / YaCy 当前 live availability 未闭合。
- SearXNG / YaCy live result quality、freshness、latency stability、timeout policy、operator approval gate 未闭合。
- `provider=auto` promotion 仍不成立。
- external runtime gap 明确保留；本轮不声称 SearXNG / YaCy live closure。

## 最小复跑

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_open_search_runtime_boundary.py --probe-timeout 0.2
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_open_search_runtime_boundary_unittest.py
```
