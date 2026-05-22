# Wave13 Admin/Dashboard Consumer Extraction Evidence (2026-05-22)

## Status

- Topic: `2026-03-14-consumer-side-modularization`
- Branch: `codex/devdocs-wave13-consumer-dashboard-extraction`
- Result: bounded admin/dashboard Python-read extraction slice landed.

This does not claim full consumer-side modularization closure. It moves a selected admin/dashboard consumer slice behind `document_views` and adds a checker that keeps the boundary explicit.

## What Changed

Selected Python read paths now use `main/backend/app/services/document_views` instead of reading `doc.extracted_data` directly:

1. `main/backend/app/api/dashboard.py`
   - `get_sentiment_analysis(...)`
   - `get_sentiment_sources(...)`
2. `main/backend/app/api/admin.py`
   - `_augment_market_graph_with_topic_structured(...)`
   - `list_social_data(...)`
   - `get_content_graph(...)`
   - `get_market_graph(...)`
   - `get_policy_graph(...)`

The reusable social facade now exposes dashboard/admin-facing helpers:

1. `get_social_platform_label(...)`
2. `get_social_sentiment_orientation(...)`
3. `get_social_sentiment_terms(...)`
4. `build_social_data_item(...)`

## Guardrail

Added `main/backend/scripts/check_admin_dashboard_consumer_boundary.py`.

The checker verifies:

1. selected admin/dashboard consumer functions import the `document_views` boundary;
2. selected functions call their expected boundary helper;
3. selected functions contain no instance-level `*.extracted_data` Python reads;
4. `Document.extracted_data[...]` SQL JSON expressions are counted but explicitly left in deferred query-layer scope.

Current checker result:

```text
python3 main/backend/scripts/check_admin_dashboard_consumer_boundary.py
status: passed
checked_python_consumer_function_count: 7
direct_instance_extracted_data_read_count: 0
allowed_sql_json_expression_count: 25
```

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave13-consumer-dashboard-extraction`:

```bash
python3 main/backend/scripts/check_admin_dashboard_consumer_boundary.py
```

Result: passed.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_admin_dashboard_consumer_boundary_unittest.py \
  main/backend/tests/unit/test_document_views_unittest.py \
  main/backend/tests/unit/test_consumer_side_facade_contract_unittest.py \
  main/backend/tests/integration/test_admin_graph_standardization_unittest.py \
  main/backend/tests/contract/test_admin_dashboard_schema_contract_unittest.py
```

Result: `27 passed`.

```bash
python3 main/backend/scripts/check_consumer_side_facade_contract.py
```

Result: passed; prior graph/writing facade contract remains intact.

```bash
python3 scripts/check_current_dev_wave13_plan.py
```

Result: passed.

```bash
git diff --check
```

Result: passed.

## Remaining Scope

1. `admin.py` / `dashboard.py` still contain SQL JSON predicates and sort/filter expressions; those remain query-helper extraction work, not claimed by this slice.
2. Admin governance/write paths still operate on `extracted_data` directly by design.
3. Full closure still needs the later query-layer extraction and broader endpoint regression coverage.
