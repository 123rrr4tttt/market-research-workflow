# Wave19 Open Search Health Artifact Schema Readback

- 状态：schema/readback gate passed；仍不作 SearXNG / YaCy live closure 声明
- 分支：`codex/devdocs-wave19-open-search-health-schema`
- Checker：`main/backend/scripts/check_open_search_health_artifact_schema_readback.py`
- Unit gate：`main/backend/tests/unit/test_open_search_health_artifact_schema_readback_unittest.py`
- 输入 artifact：`development/latest-dev-docs/automation-runs/wave18-open-search-health-artifact/2026-05-22/open_search_health_artifact.json`

## 本轮闭合的窄切片

- 新增 Wave19 schema/readback checker，读取 Wave18 health artifact 并固定 `wave19-open-search-health-artifact-schema-readback.v1`。
- gate 把 provider evidence 拆成两个互不混淆的 lane：
  - `compose_config_evidence`：只代表 repo compose、endpoint config 和 explicit provider route 存在。
  - runtime evidence：区分 `service_not_started_connect_error` 与 `real_live_probe_response`。
- `real_live_probe_response` 只代表 bounded probe 有返回，仍必须保持 `live_query_unsealed`，不能转成 external provider closure、quality closure 或 `provider=auto` promotion。
- checker 只读已落盘 artifact；不启动 Docker、不重新探测网络、不生成外部 provider closure 结论。

## 当前 readback 结果

命令：

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_open_search_health_artifact_schema_readback.py
```

输出：

```text
OK open_search_health_artifact_schema_readback=passed compose_config_evidence=2 service_not_started_connect_error=2 real_live_probe_response=0 external_provider_closure_claimed=false
```

| class | count | 语义 |
|---|---:|---|
| `compose_config_evidence` | 2 | SearXNG / YaCy 的 compose/config/explicit-provider evidence 都存在 |
| `service_not_started_connect_error` | 2 | 当前 Wave18 artifact 记录的是 connect error，不是 live provider closure |
| `real_live_probe_response` | 0 | 当前 readback 没有 live response；即使未来出现，也只能保持 unsealed |

## 单元测试覆盖

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_open_search_health_artifact_schema_readback_unittest.py
```

结果：

```text
4 passed
```

覆盖点：

- stopped services：`compose_config_evidence=2` 与 `service_not_started_connect_error=2` 同时存在，但语义分离。
- running fixture：`live_query_unsealed` 被 readback 为 `real_live_probe_response`，并保持 `external_provider_closure_claimed=false`。
- closure guard：runtime row 一旦把 `live_closure_claim_allowed` 改为 true，schema/readback gate 失败。
- deterministic readback：同一 artifact 重放得到相同 readback contract。

## 未闭合项

- SearXNG / YaCy 当前 live availability 未闭合。
- Live result quality、freshness、latency stability、timeout policy 和 operator approval gate 未闭合。
- `provider=auto` promotion 仍不成立。
- 本轮没有修改共享索引，也没有把 Wave18 health artifact 的当前 connect-error 读数改写为 closure。
