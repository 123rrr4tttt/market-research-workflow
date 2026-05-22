# Search Provider Trace Contract Closure Replay

日期：2026-05-22 PST
状态：已落地最小兼容补丁、lane 10 单测验证和 Wave2 真实容器 replay 证据

## 1. 目标

根据本目录的 SearXNG / YaCy explicit provider isolation 合同，补齐 search provider 结果中的可审计 trace 字段，避免只凭 `source` 判断调用路线。

本次 replay 只处理：

- `provider="searxng"` 的显式 provider trace。
- `provider="yacy"` 的显式 provider trace。
- `provider="auto"` 不纳入 SearXNG / YaCy 的既有隔离断言。

## 2. 落地合同

SearXNG 结果新增：

```json
{
  "provider_route": "explicit:searxng",
  "provider_family": "local_open_search",
  "provider_auto_included": false,
  "backend_trace": {
    "provider": "searxng",
    "provider_route": "explicit:searxng",
    "provider_family": "local_open_search",
    "auto_included": false,
    "pageno": 1
  }
}
```

YaCy 结果新增：

```json
{
  "provider_route": "explicit:yacy",
  "provider_family": "local_open_search",
  "provider_auto_included": false,
  "backend_trace": {
    "provider": "yacy",
    "provider_route": "explicit:yacy",
    "provider_family": "local_open_search",
    "auto_included": false,
    "resource": "local"
  }
}
```

## 3. 改动范围

| 文件 | 结果 |
|---|---|
| `main/backend/app/services/search/web.py` | `_searxng_search` 和 `_yacy_search` 返回 explicit provider trace 字段；SearXNG trace 保留 `pageno`，YaCy trace 保留规范化后的 `resource` |
| `main/backend/tests/unit/test_search_web_provider_adapters_unittest.py` | adapter 单测断言 `provider_route`、`provider_family`、`provider_auto_included`、`backend_trace`；分页测试断言最后一条结果的 `backend_trace.pageno=2` |

## 4. 验证

在 worktree `market-research-workflow.worktrees/search-provider-replay`，分支 `codex/devdocs-search-provider-replay` 执行：

```bash
git diff --check
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python3.11 -m py_compile main/backend/app/services/search/web.py main/backend/tests/unit/test_search_web_provider_adapters_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python3.11 -m pytest -q main/backend/tests/unit/test_search_web_provider_adapters_unittest.py
```

结果：

- `git diff --check`：通过。
- `py_compile`：通过。
- `test_search_web_provider_adapters_unittest.py`：`4 passed in 1.40s`。

## 5. 关闭判定

本次 closure replay 只关闭 explicit provider trace contract 的最小代码与单测缺口。SearXNG / YaCy 是否进入 `provider="auto"` 仍维持本目录原判定：不进入默认链，除非后续人工质量、稳定性和超时策略证据另行达标。

## 6. Wave2 真实容器 replay

补充 worktree `market-research-workflow.worktrees/search-provider-container-replay`，分支 `codex/devdocs-search-provider-container-replay` 执行真实 SearXNG / YaCy 容器回放，证据目录：

```text
development/latest-dev-docs/automation-runs/search-provider-container-replay/2026-05-22/
```

回放路径不再只使用 mock HTTP 单测，而是：

1. `docker compose -f ops/search-lab/docker-compose.yml up -d searxng yacy`
2. `smoke_searxng.sh` 验证 SearXNG root/search。
3. `smoke_yacy.sh` 验证 YaCy root/global/push/local search 和 local hit。
4. `replay_provider_trace.py` 调用 backend `search_sources(provider="searxng"|"yacy")`，以真实容器端点返回值生成 `provider_trace_replay.jsonl`。

结果：

| provider | keyword | ok | result_count | trace_failure_count |
|---|---|---:|---:|---:|
| `searxng` | `embodied ai` | true | 5 | 0 |
| `yacy` | `marketworkflow sentinel` | true | 2 | 0 |

样本结果确认：

- SearXNG：`provider_route=explicit:searxng`，`provider_family=local_open_search`，`provider_auto_included=false`，`backend_trace.pageno=1`。
- YaCy：`provider_route=explicit:yacy`，`provider_family=local_open_search`，`provider_auto_included=false`，`backend_trace.resource=local`。

复跑命令和 Docker 服务状态记录在同目录 `README.md`、`provider_trace_replay_summary.json` 和 `docker_status.json`。
