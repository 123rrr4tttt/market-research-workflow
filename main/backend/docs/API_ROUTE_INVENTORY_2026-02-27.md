# API Route Inventory (Auto-Parsed)

Generated on 2026-02-27 from `main/backend/app/api/*.py` via AST static parsing.

Total routes: **135**

## admin.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/admin/content-graph` | `get_content_graph` |  |
| POST | `/api/v1/admin/documents/bulk/extracted-data` | `bulk_update_document_extracted_data` |  |
| POST | `/api/v1/admin/documents/delete` | `delete_documents` |  |
| POST | `/api/v1/admin/documents/list` | `list_documents` |  |
| POST | `/api/v1/admin/documents/raw-import` | `raw_import_documents` |  |
| POST | `/api/v1/admin/documents/re-extract` | `re_extract_documents` |  |
| POST | `/api/v1/admin/documents/topic-extract` | `topic_extract_documents` |  |
| GET | `/api/v1/admin/documents/{doc_id}` | `get_document` |  |
| POST | `/api/v1/admin/documents/{doc_id}/extracted-data` | `update_document_extracted_data` |  |
| GET | `/api/v1/admin/export-graph` | `export_graph` |  |
| GET | `/api/v1/admin/market-graph` | `get_market_graph` |  |
| POST | `/api/v1/admin/market-stats/list` | `list_market_stats` |  |
| GET | `/api/v1/admin/policy-graph` | `get_policy_graph` |  |
| GET | `/api/v1/admin/search-history` | `get_search_history` |  |
| POST | `/api/v1/admin/social-data/list` | `list_social_data` |  |
| POST | `/api/v1/admin/sources/list` | `list_sources` |  |
| GET | `/api/v1/admin/stats` | `get_stats` |  |
## config.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/config` | `get_config` |  |
| GET | `/api/v1/config/env` | `get_env_settings` |  |
| POST | `/api/v1/config/env` | `update_env` |  |
| POST | `/api/v1/config/reload` | `reload_env_settings` |  |
## dashboard.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/dashboard/commodity-trends` | `get_commodity_trends` |  |
| GET | `/api/v1/dashboard/document-analysis` | `get_document_analysis` |  |
| GET | `/api/v1/dashboard/ecom-price-trends` | `get_ecom_price_trends` |  |
| GET | `/api/v1/dashboard/global/stats` | `get_global_stats` |  |
| GET | `/api/v1/dashboard/market-trends` | `get_market_trends` |  |
| GET | `/api/v1/dashboard/search-analytics` | `get_search_analytics` |  |
| GET | `/api/v1/dashboard/sentiment-analysis` | `get_sentiment_analysis` |  |
| GET | `/api/v1/dashboard/sentiment-sources` | `get_sentiment_sources` |  |
| GET | `/api/v1/dashboard/stats` | `get_dashboard_stats` |  |
| GET | `/api/v1/dashboard/task-monitoring` | `get_task_monitoring` |  |
## discovery.py

| Method | Path | Handler | Status |
|---|---|---|---|
| POST | `/api/v1/discovery/deep` | `discovery_deep` |  |
| POST | `/api/v1/discovery/generate-keywords` | `generate_keywords_api` |  |
| POST | `/api/v1/discovery/generate-subreddit-keywords` | `generate_subreddit_keywords_api` |  |
| POST | `/api/v1/discovery/search` | `discovery_search` |  |
| POST | `/api/v1/discovery/smart` | `discovery_smart` |  |
## governance.py

| Method | Path | Handler | Status |
|---|---|---|---|
| POST | `/api/v1/governance/aggregator/sync` | `sync_aggregator` |  |
| POST | `/api/v1/governance/cleanup` | `cleanup` |  |
## indexer.py

| Method | Path | Handler | Status |
|---|---|---|---|
| POST | `/api/v1/indexer/policy` | `reindex_policy` |  |
## ingest.py

| Method | Path | Handler | Status |
|---|---|---|---|
| POST | `/api/v1/ingest/commodity/metrics` | `ingest_commodity` |  |
| GET | `/api/v1/ingest/config` | `get_ingest_config_endpoint` |  |
| POST | `/api/v1/ingest/config` | `post_ingest_config_endpoint` |  |
| POST | `/api/v1/ingest/ecom/prices` | `ingest_ecom_prices` |  |
| GET | `/api/v1/ingest/history` | `ingest_history` |  |
| POST | `/api/v1/ingest/market` | `ingest_market` |  |
| GET | `/api/v1/ingest/news-resources` | `list_news_resources` |  |
| POST | `/api/v1/ingest/news/resource/{resource_id}` | `ingest_news_resource` |  |
| POST | `/api/v1/ingest/subprojects/{subproject_key}/news/{resource_id}` | `ingest_subproject_news_resource` |  |
| POST | `/api/v1/ingest/policy` | `ingest_policy` |  |
| POST | `/api/v1/ingest/policy/regulation` | `ingest_policy_regulation` |  |
| POST | `/api/v1/ingest/reports/california` | `ingest_california_reports` |  |
| POST | `/api/v1/ingest/reports/monthly` | `ingest_monthly_reports` |  |
| POST | `/api/v1/ingest/reports/weekly` | `ingest_weekly_reports` |  |
| POST | `/api/v1/ingest/social/reddit` | `ingest_reddit` |  |
| POST | `/api/v1/ingest/social/sentiment` | `ingest_social_sentiment` |  |
| POST | `/api/v1/ingest/source-library/run` | `ingest_source_library_run` |  |
| POST | `/api/v1/ingest/source-library/sync` | `ingest_source_library_sync` |  |
## llm_config.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/llm-config` | `list_llm_configs` |  |
| POST | `/api/v1/llm-config` | `create_llm_config` |  |
| GET | `/api/v1/llm-config/projects/{project_key}` | `list_llm_configs_by_project` |  |
| POST | `/api/v1/llm-config/projects/{project_key}` | `create_llm_config_by_project` |  |
| POST | `/api/v1/llm-config/projects/{project_key}/copy-from` | `copy_llm_configs_to_project` |  |
| DELETE | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `delete_llm_config_by_project` |  |
| GET | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `get_llm_config_by_project` |  |
| PUT | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `upsert_llm_config_by_project` |  |
| DELETE | `/api/v1/llm-config/service/{service_name}` | `delete_llm_config` |  |
| GET | `/api/v1/llm-config/service/{service_name}` | `get_llm_config` |  |
| PUT | `/api/v1/llm-config/service/{service_name}` | `update_llm_config` |  |
| DELETE | `/api/v1/llm-config/{service_name}` | `delete_llm_config_legacy` |  |
| GET | `/api/v1/llm-config/{service_name}` | `get_llm_config_legacy` |  |
| PUT | `/api/v1/llm-config/{service_name}` | `update_llm_config_legacy` |  |
## market.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/market` | `market_stats` |  |
| GET | `/api/v1/market/games` | `market_games` |  |
## policies.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/policies` | `list_policies` |  |
| GET | `/api/v1/policies/state/{state}` | `get_state_policies` |  |
| GET | `/api/v1/policies/stats` | `get_policy_stats` |  |
| GET | `/api/v1/policies/{policy_id}` | `get_policy_detail` |  |
## process.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/process/history` | `get_task_history` |  |
| GET | `/api/v1/process/list` | `list_tasks` |  |
| GET | `/api/v1/process/stats` | `get_task_stats` |  |
| GET | `/api/v1/process/{task_id}` | `get_task_info` |  |
| POST | `/api/v1/process/{task_id}/cancel` | `cancel_task` |  |
| GET | `/api/v1/process/{task_id}/logs` | `get_task_logs` |  |
## products.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/products` | `list_products` |  |
| POST | `/api/v1/products` | `create_product` |  |
| DELETE | `/api/v1/products/{product_id}` | `delete_product` |  |
| PUT | `/api/v1/products/{product_id}` | `update_product` |  |
## project_customization.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/project-customization/graph-config` | `get_graph_config` |  |
| GET | `/api/v1/project-customization/llm-mapping` | `get_llm_mapping` |  |
| GET | `/api/v1/project-customization/menu` | `get_menu_config` |  |
| GET | `/api/v1/project-customization/workflows` | `list_workflows` |  |
| POST | `/api/v1/project-customization/workflows/{workflow_name}/run` | `run_workflow` |  |
| DELETE | `/api/v1/project-customization/workflows/{workflow_name}/template` | `delete_workflow_template` |  |
| GET | `/api/v1/project-customization/workflows/{workflow_name}/template` | `get_workflow_template` |  |
| POST | `/api/v1/project-customization/workflows/{workflow_name}/template` | `upsert_workflow_template` |  |
## projects.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/projects` | `list_projects` |  |
| POST | `/api/v1/projects` | `create_project` |  |
| POST | `/api/v1/projects/inject-initial` | `inject_initial_project` |  |
| DELETE | `/api/v1/projects/{project_key}` | `delete_project` |  |
| PATCH | `/api/v1/projects/{project_key}` | `update_project` |  |
| POST | `/api/v1/projects/{project_key}/activate` | `activate_project` |  |
| POST | `/api/v1/projects/{project_key}/archive` | `archive_project` |  |
| POST | `/api/v1/projects/{project_key}/restore` | `restore_project` |  |
## reports.py

| Method | Path | Handler | Status |
|---|---|---|---|
| POST | `/api/v1/reports` | `create_report` |  |
## resource_pool.py

| Method | Path | Handler | Status |
|---|---|---|---|
| POST | `/api/v1/resource_pool/capture/enable` | `capture_enable_api` |  |
| POST | `/api/v1/resource_pool/capture/from-tasks` | `capture_from_tasks_api` |  |
| POST | `/api/v1/resource_pool/discover/site-entries` | `discover_site_entries_api` |  |
| POST | `/api/v1/resource_pool/extract/from-documents` | `extract_from_documents_api` |  |
| GET | `/api/v1/resource_pool/site-entries` | `list_site_entries_api` |  |
| POST | `/api/v1/resource_pool/site-entries` | `upsert_site_entry_api` |  |
| GET | `/api/v1/resource_pool/site-entries/grouped` | `group_site_entries_api` |  |
| GET | `/api/v1/resource_pool/site_entries` | `list_site_entries_api` |  |
| POST | `/api/v1/resource_pool/site_entries` | `upsert_site_entry_api` |  |
| GET | `/api/v1/resource_pool/site_entries/grouped` | `group_site_entries_api` |  |
| POST | `/api/v1/resource_pool/site_entries/recommend` | `recommend_site_entry_api` |  |
| POST | `/api/v1/resource_pool/site_entries/recommend-batch` | `recommend_site_entries_batch_api` |  |
| POST | `/api/v1/resource_pool/site_entries/simplify` | `simplify_site_entries_api` |  |
| POST | `/api/v1/resource_pool/unified-search` | `unified_search_api` |  |
| GET | `/api/v1/resource_pool/urls` | `list_urls_api` |  |
## search.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/search` | `search` |  |
| POST | `/api/v1/search/_init` | `init_search_indices` |  |
## source_library.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/source_library/channels` | `list_channels` |  |
| GET | `/api/v1/source_library/channels/grouped` | `list_channels_grouped_api` |  |
| POST | `/api/v1/source_library/handler_clusters/sync` | `sync_handler_clusters` |  |
| GET | `/api/v1/source_library/items` | `list_items` |  |
| POST | `/api/v1/source_library/items` | `upsert_project_item` |  |
| GET | `/api/v1/source_library/items/by_symbol` | `list_items_by_symbol_api` |  |
| GET | `/api/v1/source_library/items/grouped` | `list_items_grouped_api` |  |
| POST | `/api/v1/source_library/items/{item_key}/refresh` | `refresh_item` |  |
| POST | `/api/v1/source_library/items/{item_key}/run` | `run_item` |  |
| POST | `/api/v1/source_library/sync_shared_from_files` | `sync_shared_from_files` |  |
## topics.py

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/v1/topics` | `list_topics` |  |
| POST | `/api/v1/topics` | `create_topic` |  |
| DELETE | `/api/v1/topics/{topic_id}` | `delete_topic` |  |
| PUT | `/api/v1/topics/{topic_id}` | `update_topic` |  |

## Notes

- This file captures route surface only, not full request/response schema.
- For payload contracts, inspect endpoint source modules and Pydantic models in `app/contracts/`.
