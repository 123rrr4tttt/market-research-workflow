# Search Provider Trace Contract Closure Replay

日期：2026-05-22 PST
状态：已落地最小兼容补丁并通过 lane 10 验证

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
