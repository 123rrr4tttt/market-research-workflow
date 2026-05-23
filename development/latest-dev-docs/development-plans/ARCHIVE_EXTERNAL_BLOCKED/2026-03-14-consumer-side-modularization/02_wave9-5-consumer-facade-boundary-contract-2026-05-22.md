# Wave9-5 Consumer Facade Boundary Contract（2026-05-22）

## status

`partial_narrow_facade_boundary_guard`

本轮没有宣称 `2026-03-14-consumer-side-modularization` 全量封口；只完成 worker5 负责的窄切片：graph adapters / writing suggest / search+writing API 消费面必须通过 `document_views` 或既有 `document_queries` 边界读取，不再在这些消费面继续散落 `doc.extracted_data` Python 直读。

## worker5 scope

1. 新增 `main/backend/app/services/document_views/consumer_boundary.py`。
2. graph adapters 的 Python 读取改走 `document_views` facade：
   - `has_structured_data(...)`
   - `get_social_identity(...)`
   - `get_document_source_label(...)`
3. writing suggest 的 source-library material 检索改走既有 `query_source_library_material_rows(...)`，不再直接 import `source_library.resolver`。
4. 新增 `main/backend/scripts/check_consumer_side_facade_contract.py`，静态验证 worker5 覆盖的 consumer surfaces 没有重新绕过 facade/query boundary。

## worker4 boundary

worker5 没有编辑 `main/backend/app/services/document_queries/*` 核心文件。

SQL JSON predicate / sort / cast helper 的抽离仍归 worker4 或集成分支处理。本轮 checker 只把这些面列为 deferred query surfaces，不把它们伪装成已封口：

1. `main/backend/app/services/document_queries/policy_filters.py`
2. `main/backend/app/api/admin.py`
3. `main/backend/app/api/dashboard.py`
4. `main/backend/app/services/stats/prompt_time_density.py`

## evidence

新增 checker 输出：

```text
python3 main/backend/scripts/check_consumer_side_facade_contract.py
status: passed
checked_python_read_surface_count: 11
direct_extracted_data_read_count: 0
```

聚焦测试：

```text
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_consumer_side_facade_contract_unittest.py \
  main/backend/tests/unit/test_writing_keyword_card_service_unittest.py \
  main/backend/tests/integration/test_search_api_unittest.py
```

差异门禁：

```text
git diff --check
```

## remaining gaps

1. `admin.py` / `dashboard.py` / `prompt_time_density.py` 仍存在消费侧 Python 读取和 SQL JSON query 混杂问题。
2. `document_queries` 的完整 query helper 收敛未在 worker5 切片内完成。
3. 本轮只证明 worker5 覆盖面不再直接散读底层结构，不证明整个消费侧模块化已封口。
