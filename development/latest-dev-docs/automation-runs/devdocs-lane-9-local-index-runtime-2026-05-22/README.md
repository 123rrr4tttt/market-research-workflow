# Dev Docs Lane 9 Local Index Runtime Evidence

日期：2026-05-22 PST
分支：`codex/devdocs-local-index-runtime`
工作树：`/Users/wangyiliang/market-research-workflow.worktrees/local-index-runtime`

## 目标

根据 `2026-05-14-global-vectorization-general-foundation` 下的 local-index / LanceDB 文档，把 `local_index` 的 `keyword|vector|hybrid` mode contract 落到代码和测试。

## 结果

- 已在 `LocalIndexQuery` 层冻结合法 mode：`keyword`、`vector`、`hybrid`。
- 已在 `LocalIndexService.search()` 规范化 mode；未知 mode 降级为 `keyword`，避免 adapter 收到未定义语义。
- 已在 `LanceDBLocalIndexAdapter.search()` 按 mode 分发：
  - `keyword`：LanceDB FTS (`query_type="fts"`)。
  - `vector`：使用当前 prototype 的 deterministic query vector 调用 LanceDB vector search。
  - `hybrid`：调用 LanceDB hybrid search (`query_type="hybrid"`)。
- 已为 `LocalIndexSearchResult` 增加 `retrieval_mode`、`retrieval_family`、`trace`，用于和全局 retrieval contract 对齐。
- 已补 unit tests 覆盖 mode export/normalization、service mode 传递、LanceDB adapter fake-table dispatch、vector runtime fallback、optional dependency boundary。

## Runtime Smoke

本机 lane 环境检测：

```text
lancedb_available= False
```

因此没有运行真实 LanceDB optional runtime smoke。本分支以 fake LanceDB table 单测验证 adapter dispatch 和 fallback contract，并保留 `is_lancedb_available()` optional dependency boundary。真实 LanceDB runtime smoke 需要在安装 optional dependency 后补跑。

## 验证

```text
git diff --check
PASS

cd main/backend && PYTHONPATH=. python3 -m py_compile app/services/local_index/schema.py app/services/local_index/service.py app/services/local_index/adapters/lancedb_adapter.py tests/unit/test_local_index_service_unittest.py
PASS

cd main/backend && PYTHONPATH=. python3 -m pytest -q tests/unit/test_local_index_service_unittest.py
7 passed in 0.11s
```

## 合并建议

可作为 lane 9 独立分支合并。与其他 lane 的主要潜在冲突点是 `main/backend/app/services/local_index/**` 和 `test_local_index_service_unittest.py`；若其他分支也修改 retrieval result contract，应以 `retrieval_mode/retrieval_family/trace` 这组三个字段为主合同，避免再引入第二套 metadata-only 诊断字段。
