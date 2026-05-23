# Wave22 External Blocked Decision

日期：2026-05-22 PST

## 结论

Decision: `external_blocked`.

本目录可以作为后续集成 lane 的 `ARCHIVE_EXTERNAL_BLOCKED` 迁入候选；不应继续作为无条件 `retained_partial` 留在 `CURRENT_DEV`。本轮没有发现新的 repo-local blocker。当前不能标记为 `closed`，因为 SearXNG / YaCy 的 live availability、live result quality、freshness、latency stability、timeout policy、operator approval gate 和 `provider=auto` promotion 仍未闭合。

本文件只补 topic-local Wave22 判定证据，不修改共享索引。

## 支撑证据

| 证据面 | 判定 | 说明 |
|---|---|---|
| explicit provider trace contract | passed | `search_provider_trace_contract.py` 输出 `ok=true`；artifact 固定 `explicit:searxng` / `explicit:yacy`、`provider_family=local_open_search`、`provider_auto_included=false`，且 `auto_route.local_open_search_called=false`。 |
| historical real container replay | passed | `search-provider-container-replay/2026-05-22/provider_trace_replay_summary.json` 记录 `ok=true`；既有容器 replay 证明显式 provider trace 在真实容器端点可工作。 |
| current readiness probe | partial / external gap | Wave12 readiness gate 通过，但当前 `127.0.0.1:8088` 与 `127.0.0.1:8090` 均 connection refused；脚本把该事实记录为 readiness gap，不作为 gate failure。 |
| runtime boundary | passed / external gap retained | Wave15 runtime boundary gate 通过，`boundary_state=partial`、`external_runtime_gap=retained`、`closure_claim_allowed=false`，两个 provider 均为 `service_not_started_connect_error:unavailable`。 |
| health artifact | passed / partial | Wave18 health artifact gate 通过，`health_state=partial`、`closure_claim_allowed=false`、`live_probe_open=true`，两个 provider 均为 `service_not_started_connect_error:unavailable`。 |
| schema/readback | passed | Wave19 readback gate 通过，`compose_config_evidence=2`、`service_not_started_connect_error=2`、`real_live_probe_response=0`、`external_provider_closure_claimed=false`。 |
| unit gates | passed | runtime boundary、health artifact、schema/readback 三组单测共 11 个用例通过。 |

## 本轮命令

```bash
git status --short
find development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-05-14-local-open-search-provider-isolation -maxdepth 3 -type f | sort
rg -n "local-open-search-provider-isolation|SearXNG / YaCy|2026-05-14 SearXNG" development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md development/latest-dev-docs/development-plans/INDEX.md development/latest-dev-docs/README.md development/latest-dev-docs/MERGED_OVERVIEW.md
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_open_search_health_artifact_schema_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_open_search_runtime_boundary.py --probe-timeout 0.2
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_open_search_health_artifact.py --probe-timeout 0.2
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_open_search_runtime_boundary_unittest.py main/backend/tests/unit/test_open_search_health_artifact_unittest.py main/backend/tests/unit/test_open_search_health_artifact_schema_readback_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave12_provider_readiness_gate.py --probe-timeout 1.0
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/search_provider_trace_contract.py
```

## 本轮输出摘要

```text
OK open_search_health_artifact_schema_readback=passed compose_config_evidence=2 service_not_started_connect_error=2 real_live_probe_response=0 external_provider_closure_claimed=false
OK open_search_runtime_boundary=passed boundary_state=partial external_runtime_gap=retained closure_claim_allowed=false searxng=service_not_started_connect_error:unavailable yacy=service_not_started_connect_error:unavailable
OK open_search_health_artifact=passed health_state=partial closure_claim_allowed=false live_probe_open=true searxng=service_not_started_connect_error:unavailable yacy=service_not_started_connect_error:unavailable
11 passed in 4.93s
{"mode_live": {"hybrid": "blocked", "keyword": "blocked", "vector": "blocked"}, "provider_live": {"searxng": "unavailable", "yacy": "unavailable"}, "readiness_state": "partial", "status": "passed"}
{"ok": true, "contract_version": "search-provider-trace-artifacts.v1"}
```

## 迁档口径

建议后续共享索引 lane 将本 topic 从 `CURRENT_DEV` 迁入 `ARCHIVE_EXTERNAL_BLOCKED`，状态口径为：

```text
external_blocked / wave22_checked
```

迁档时不要宣称 `closed`。解除 `external_blocked` 至少需要补齐：

- 当前 SearXNG / YaCy live availability；
- live result quality、freshness、latency stability 和 timeout policy；
- operator approval gate；
- 明确的 `provider=auto` promotion owner decision 与对应回归证据。
