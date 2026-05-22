# Search Provider Trace Artifacts

日期：2026-05-22 PST
范围：离线 adapter contract，不启动 SearXNG / YaCy 容器。

## 产物

- `search_provider_trace_contract.json`：由 `ops/search-lab/scripts/search_provider_trace_contract.py` 生成的确定性 artifact。

## 合同

- `provider=auto` 不调用 `_searxng_search` / `_yacy_search`。
- `provider=auto` 结果不包含 `source=searxng` 或 `source=yacy`。
- 显式 `provider=searxng` 结果必须包含 `provider_route=explicit:searxng`、`provider_family=local_open_search`、`provider_auto_included=false`、`backend_trace`。
- 显式 `provider=yacy` 结果必须包含 `provider_route=explicit:yacy`、`provider_family=local_open_search`、`provider_auto_included=false`、`backend_trace`。

## 复跑

```bash
PYTHONPATH=main/backend main/backend/.venv311/bin/python ops/search-lab/scripts/search_provider_trace_contract.py --out development/latest-dev-docs/automation-runs/search-provider-trace-artifacts/2026-05-22/search_provider_trace_contract.json
PYTHONPATH=main/backend main/backend/.venv311/bin/python -m pytest main/backend/tests/unit/test_search_web_provider_adapters_unittest.py
```

真实 Docker replay 仍由 `ops/search-lab/scripts/smoke_searxng.sh`、`ops/search-lab/scripts/smoke_yacy.sh` 和 `compare_keyword_search.py` 单独执行；本目录不作为容器运行态证据。
