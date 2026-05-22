# Search Provider Replay Lane 10 Evidence

日期：2026-05-22 PST
worktree：`/Users/wangyiliang/market-research-workflow.worktrees/search-provider-replay`
分支：`codex/devdocs-search-provider-replay`

## 1. 任务

根据 `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-local-open-search-provider-isolation/`，把 SearXNG / YaCy explicit provider trace 合同落到 search provider 代码和单测。

## 2. 结果

| 项 | 状态 | 证据 |
|---|---|---|
| SearXNG explicit trace | passed | `_searxng_search` 返回 `provider_route=explicit:searxng`、`provider_family=local_open_search`、`provider_auto_included=false`、`backend_trace.pageno` |
| YaCy explicit trace | passed | `_yacy_search` 返回 `provider_route=explicit:yacy`、`provider_family=local_open_search`、`provider_auto_included=false`、`backend_trace.resource` |
| Auto isolation | unchanged | 既有单测仍断言 `provider=auto` 不调用 `_searxng_search` / `_yacy_search` |
| Closure replay doc | passed | `10_search-provider-trace-contract-closure-replay-2026-05-22.md` |

## 3. 验证命令

```bash
git diff --check
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python3.11 -m py_compile main/backend/app/services/search/web.py main/backend/tests/unit/test_search_web_provider_adapters_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python3.11 -m pytest -q main/backend/tests/unit/test_search_web_provider_adapters_unittest.py
```

结果：

- `git diff --check`：通过。
- `py_compile`：通过。
- `pytest`：`4 passed in 1.40s`。

## 4. 风险

- 本次只验证 adapter 层 mock HTTP 响应，不启动真实 SearXNG / YaCy 容器。
- Worktree 没有自己的 `main/backend/.venv311`，验证使用主工作树已有 Python 3.11 venv 解释器。

## 5. 建议合并方式

先合并本 lane 的 `web.py` 与 adapter 单测，再合并文档证据。若其他 lane 同时改 `search/web.py`，以保持 `provider=auto` 不调用 SearXNG / YaCy 为硬约束，保留本 lane 新增的 explicit trace 字段。
