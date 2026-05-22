# API Route Inventory (Runtime APIRoute Snapshot)

> Generated on 2026-05-22 from `app.main.app.routes` using FastAPI `APIRoute`. This replaces the stale 2026-02-27 AST snapshot for current route/API drift checks; the old file remains historical evidence.

Total `/api/v1` routes: **253**
Endpoint modules with `/api/v1` routes: **32**
Aggregated `app.api` router modules: **30**

## Drift Checks Captured

- `project_customization.py` is mounted at `/api/v1/project-customization/*`; the underscore path is not current.
- Source-library execution is mounted at `POST /api/v1/ingest/source-library/run`; `POST /api/v1/source_library/items/{item_key}/run` is not present in the current APIRoute table.
- `POST /api/v1/ingest/graph/structured-search` and `POST /api/v1/projects/auto-create` are present and were missing from the older 2026-02 route inventory.

## Module Summary

| Module | Route Count | Prefixes |
|---|---:|---|
| `admin.py` | 17 | `/api/v1/admin` |
| `agent_batch.py` | 16 | `/api/v1/agent-batch` |
| `agent_chat.py` | 4 | `/api/v1/agent-chat` |
| `agent_sessions.py` | 16 | `/api/v1/agent-approvals`, `/api/v1/agent-sessions` |
| `codex_auth.py` | 5 | `/api/v1/codex-auth` |
| `config.py` | 4 | `/api/v1/config` |
| `crawler.py` | 8 | `/api/v1/crawler` |
| `dashboard.py` | 10 | `/api/v1/dashboard` |
| `discovery.py` | 5 | `/api/v1/discovery` |
| `governance.py` | 2 | `/api/v1/governance` |
| `indexer.py` | 1 | `/api/v1/indexer` |
| `ingest.py` | 19 | `/api/v1/ingest` |
| `keywords.py` | 5 | `/api/v1/keywords` |
| `llm_config.py` | 14 | `/api/v1/llm-config` |
| `llm_report.py` | 1 | `/api/v1/llm-report` |
| `main.py` | 2 | `/api/v1/health` |
| `market.py` | 2 | `/api/v1/market` |
| `policies.py` | 4 | `/api/v1/policies` |
| `process.py` | 7 | `/api/v1/process` |
| `products.py` | 4 | `/api/v1/products` |
| `project_customization.py` | 8 | `/api/v1/project-customization` |
| `projects.py` | 9 | `/api/v1/projects` |
| `reports.py` | 1 | `/api/v1/reports` |
| `resource_pool.py` | 19 | `/api/v1/resource_pool` |
| `search.py` | 2 | `/api/v1/search` |
| `skills.py` | 2 | `/api/v1/skills` |
| `source_library.py` | 11 | `/api/v1/source_library` |
| `stats.py` | 4 | `/api/v1/stats` |
| `topics.py` | 4 | `/api/v1/topics` |
| `web_ui_routes.py` | 1 | `/api/v1/maps` |
| `workflow_graph.py` | 28 | `/api/v1/workflow-graph` |
| `writing.py` | 18 | `/api/v1/writing` |

## Routes

### admin.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/admin/content-graph` | `get_content_graph` |
| POST | `/api/v1/admin/documents/bulk/extracted-data` | `bulk_update_document_extracted_data` |
| POST | `/api/v1/admin/documents/delete` | `delete_documents` |
| POST | `/api/v1/admin/documents/list` | `list_documents` |
| POST | `/api/v1/admin/documents/raw-import` | `raw_import_documents` |
| POST | `/api/v1/admin/documents/re-extract` | `re_extract_documents` |
| POST | `/api/v1/admin/documents/topic-extract` | `topic_extract_documents` |
| GET | `/api/v1/admin/documents/{doc_id}` | `get_document` |
| POST | `/api/v1/admin/documents/{doc_id}/extracted-data` | `update_document_extracted_data` |
| GET | `/api/v1/admin/export-graph` | `export_graph` |
| GET | `/api/v1/admin/market-graph` | `get_market_graph` |
| POST | `/api/v1/admin/market-stats/list` | `list_market_stats` |
| GET | `/api/v1/admin/policy-graph` | `get_policy_graph` |
| GET | `/api/v1/admin/search-history` | `get_search_history` |
| POST | `/api/v1/admin/social-data/list` | `list_social_data` |
| POST | `/api/v1/admin/sources/list` | `list_sources` |
| GET | `/api/v1/admin/stats` | `get_stats` |

### agent_batch.py

| Method | Path | Handler |
|---|---|---|
| POST | `/api/v1/agent-batch/approvals/request` | `create_agent_batch_approval` |
| POST | `/api/v1/agent-batch/approvals/{approval_token}/resolve` | `resolve_agent_batch_approval` |
| GET | `/api/v1/agent-batch/executor/health` | `get_agent_batch_executor_health` |
| POST | `/api/v1/agent-batch/jobs` | `submit_agent_batch_job` |
| GET | `/api/v1/agent-batch/jobs/{job_id}` | `get_agent_batch_job` |
| GET | `/api/v1/agent-batch/jobs/{job_id}/events` | `get_agent_batch_events` |
| GET | `/api/v1/agent-batch/jobs/{job_id}/items` | `list_agent_batch_items` |
| POST | `/api/v1/agent-batch/jobs/{job_id}/retry` | `retry_agent_batch_job` |
| GET | `/api/v1/agent-batch/jobs/{job_id}/workflow-handoffs` | `list_agent_batch_job_workflow_handoffs` |
| GET | `/api/v1/agent-batch/metrics/search-policy` | `get_agent_batch_search_policy_metrics` |
| GET | `/api/v1/agent-batch/metrics/search-policy/benchmark-pack` | `get_agent_batch_search_policy_benchmark_pack` |
| GET | `/api/v1/agent-batch/metrics/search-policy/gate` | `get_agent_batch_search_policy_gate` |
| POST | `/api/v1/agent-batch/nl-command` | `run_agent_batch_nl_command` |
| POST | `/api/v1/agent-batch/nl-command/direct` | `run_agent_batch_nl_command_direct` |
| GET | `/api/v1/agent-batch/observability/failure-reasons` | `get_agent_batch_failure_reasons` |
| POST | `/api/v1/agent-batch/rule-sets/validate` | `validate_agent_batch_rule_set` |

### agent_chat.py

| Method | Path | Handler |
|---|---|---|
| POST | `/api/v1/agent-chat/approvals/{approval_id}/continue` | `continue_agent_chat_approval` |
| GET | `/api/v1/agent-chat/capabilities` | `list_agent_chat_capabilities` |
| POST | `/api/v1/agent-chat/turn` | `run_agent_chat_turn` |
| POST | `/api/v1/agent-chat/turn/stream` | `stream_agent_chat_turn` |

### agent_sessions.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/agent-approvals` | `list_agent_approvals` |
| POST | `/api/v1/agent-approvals/{approval_id}/resolve` | `resolve_agent_approval` |
| GET | `/api/v1/agent-sessions` | `list_agent_sessions` |
| POST | `/api/v1/agent-sessions` | `create_agent_session` |
| GET | `/api/v1/agent-sessions/{session_id}` | `get_agent_session` |
| POST | `/api/v1/agent-sessions/{session_id}/actions/cancel` | `cancel_agent_session` |
| POST | `/api/v1/agent-sessions/{session_id}/actions/coordinator-pass` | `run_agent_session_coordinator_pass` |
| POST | `/api/v1/agent-sessions/{session_id}/actions/reclaim-expired` | `reclaim_agent_session_expired_tasks` |
| POST | `/api/v1/agent-sessions/{session_id}/actions/request-approval` | `request_agent_session_approval` |
| POST | `/api/v1/agent-sessions/{session_id}/actions/retry-task` | `retry_agent_session_task` |
| GET | `/api/v1/agent-sessions/{session_id}/artifacts` | `get_agent_session_artifacts` |
| GET | `/api/v1/agent-sessions/{session_id}/events` | `get_agent_session_events` |
| GET | `/api/v1/agent-sessions/{session_id}/messages` | `get_agent_session_messages` |
| POST | `/api/v1/agent-sessions/{session_id}/messages` | `create_agent_session_message` |
| GET | `/api/v1/agent-sessions/{session_id}/stream` | `stream_agent_session_events` |
| GET | `/api/v1/agent-sessions/{session_id}/tasks` | `get_agent_session_tasks` |

### codex_auth.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/codex-auth/callback` | `codex_auth_callback` |
| POST | `/api/v1/codex-auth/cli/bootstrap` | `codex_cli_bootstrap` |
| GET | `/api/v1/codex-auth/login` | `codex_auth_login` |
| POST | `/api/v1/codex-auth/logout` | `codex_auth_logout` |
| GET | `/api/v1/codex-auth/status` | `codex_auth_status` |

### config.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/config` | `get_config` |
| GET | `/api/v1/config/env` | `get_env_settings` |
| POST | `/api/v1/config/env` | `update_env` |
| POST | `/api/v1/config/reload` | `reload_env_settings` |

### crawler.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/crawler/deploy-runs` | `list_crawler_deploy_runs_api` |
| GET | `/api/v1/crawler/deploy-runs/{run_id}` | `get_crawler_deploy_run_api` |
| GET | `/api/v1/crawler/projects` | `list_crawler_projects_api` |
| POST | `/api/v1/crawler/projects/import` | `import_crawler_project_api` |
| GET | `/api/v1/crawler/projects/{project_key}` | `get_crawler_project_api` |
| POST | `/api/v1/crawler/projects/{project_key}/deploy` | `deploy_crawler_project_api` |
| GET | `/api/v1/crawler/projects/{project_key}/deploy-runs` | `list_crawler_project_deploy_runs_api` |
| POST | `/api/v1/crawler/projects/{project_key}/rollback` | `rollback_crawler_project_api` |

### dashboard.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/dashboard/commodity-trends` | `get_commodity_trends` |
| GET | `/api/v1/dashboard/document-analysis` | `get_document_analysis` |
| GET | `/api/v1/dashboard/ecom-price-trends` | `get_ecom_price_trends` |
| GET | `/api/v1/dashboard/global/stats` | `get_global_stats` |
| GET | `/api/v1/dashboard/market-trends` | `get_market_trends` |
| GET | `/api/v1/dashboard/search-analytics` | `get_search_analytics` |
| GET | `/api/v1/dashboard/sentiment-analysis` | `get_sentiment_analysis` |
| GET | `/api/v1/dashboard/sentiment-sources` | `get_sentiment_sources` |
| GET | `/api/v1/dashboard/stats` | `get_dashboard_stats` |
| GET | `/api/v1/dashboard/task-monitoring` | `get_task_monitoring` |

### discovery.py

| Method | Path | Handler |
|---|---|---|
| POST | `/api/v1/discovery/deep` | `discovery_deep` |
| POST | `/api/v1/discovery/generate-keywords` | `generate_keywords_api` |
| POST | `/api/v1/discovery/generate-subreddit-keywords` | `generate_subreddit_keywords_api` |
| POST | `/api/v1/discovery/search` | `discovery_search` |
| POST | `/api/v1/discovery/smart` | `discovery_smart` |

### governance.py

| Method | Path | Handler |
|---|---|---|
| POST | `/api/v1/governance/aggregator/sync` | `sync_aggregator` |
| POST | `/api/v1/governance/cleanup` | `cleanup` |

### indexer.py

| Method | Path | Handler |
|---|---|---|
| POST | `/api/v1/indexer/policy` | `reindex_policy` |

### ingest.py

| Method | Path | Handler |
|---|---|---|
| POST | `/api/v1/ingest/commodity/metrics` | `ingest_commodity` |
| GET | `/api/v1/ingest/config` | `get_ingest_config_endpoint` |
| POST | `/api/v1/ingest/config` | `post_ingest_config_endpoint` |
| POST | `/api/v1/ingest/data-api` | `ingest_data_api` |
| POST | `/api/v1/ingest/ecom/prices` | `ingest_ecom_prices` |
| POST | `/api/v1/ingest/graph/structured-search` | `ingest_graph_structured_search` |
| GET | `/api/v1/ingest/history` | `ingest_history` |
| POST | `/api/v1/ingest/market` | `ingest_market` |
| GET | `/api/v1/ingest/news-resources` | `list_news_resources` |
| POST | `/api/v1/ingest/news/resource/{resource_id}` | `ingest_news_resource` |
| POST | `/api/v1/ingest/policy/regulation` | `ingest_policy_regulation` |
| POST | `/api/v1/ingest/reports/california` | `ingest_california_reports` |
| POST | `/api/v1/ingest/reports/monthly` | `ingest_monthly_reports` |
| POST | `/api/v1/ingest/reports/weekly` | `ingest_weekly_reports` |
| POST | `/api/v1/ingest/social/reddit` | `ingest_reddit` |
| POST | `/api/v1/ingest/source-library/run` | `ingest_source_library_run` |
| POST | `/api/v1/ingest/source-library/sync` | `ingest_source_library_sync` |
| POST | `/api/v1/ingest/subprojects/{subproject_key}/news/{resource_id}` | `ingest_subproject_news_resource` |
| POST | `/api/v1/ingest/url/single` | `ingest_url_single` |

### keywords.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/keywords/history` | `get_keyword_history` |
| GET | `/api/v1/keywords/priors` | `get_keyword_priors` |
| POST | `/api/v1/keywords/priors/upsert` | `post_keyword_prior_upsert` |
| GET | `/api/v1/keywords/stats` | `get_keyword_memory_stats` |
| GET | `/api/v1/keywords/vectorization/candidates` | `get_vectorization_candidates` |

### llm_config.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/llm-config` | `list_llm_configs` |
| POST | `/api/v1/llm-config` | `create_llm_config` |
| GET | `/api/v1/llm-config/projects/{project_key}` | `list_llm_configs_by_project` |
| POST | `/api/v1/llm-config/projects/{project_key}` | `create_llm_config_by_project` |
| POST | `/api/v1/llm-config/projects/{project_key}/copy-from` | `copy_llm_configs_to_project` |
| DELETE | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `delete_llm_config_by_project` |
| GET | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `get_llm_config_by_project` |
| PUT | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `upsert_llm_config_by_project` |
| DELETE | `/api/v1/llm-config/service/{service_name}` | `delete_llm_config` |
| GET | `/api/v1/llm-config/service/{service_name}` | `get_llm_config` |
| PUT | `/api/v1/llm-config/service/{service_name}` | `update_llm_config` |
| DELETE | `/api/v1/llm-config/{service_name}` | `delete_llm_config_legacy` |
| GET | `/api/v1/llm-config/{service_name}` | `get_llm_config_legacy` |
| PUT | `/api/v1/llm-config/{service_name}` | `update_llm_config_legacy` |

### llm_report.py

| Method | Path | Handler |
|---|---|---|
| POST | `/api/v1/llm-report/generate` | `generate_llm_report` |

### main.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/health` | `health_check` |
| GET | `/api/v1/health/deep` | `deep_health_check` |

### market.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/market` | `market_stats` |
| GET | `/api/v1/market/games` | `market_games` |

### policies.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/policies` | `list_policies` |
| GET | `/api/v1/policies/state/{state}` | `get_state_policies` |
| GET | `/api/v1/policies/stats` | `get_policy_stats` |
| GET | `/api/v1/policies/{policy_id}` | `get_policy_detail` |

### process.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/process/history` | `get_task_history` |
| GET | `/api/v1/process/list` | `list_tasks` |
| GET | `/api/v1/process/stats` | `get_task_stats` |
| GET | `/api/v1/process/{task_id}` | `get_task_info` |
| POST | `/api/v1/process/{task_id}/cancel` | `cancel_task` |
| GET | `/api/v1/process/{task_id}/logs` | `get_task_logs` |
| POST | `/api/v1/process/{task_id}/retry` | `retry_task` |

### products.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/products` | `list_products` |
| POST | `/api/v1/products` | `create_product` |
| DELETE | `/api/v1/products/{product_id}` | `delete_product` |
| PUT | `/api/v1/products/{product_id}` | `update_product` |

### project_customization.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/project-customization/graph-config` | `get_graph_config` |
| GET | `/api/v1/project-customization/llm-mapping` | `get_llm_mapping` |
| GET | `/api/v1/project-customization/menu` | `get_menu_config` |
| GET | `/api/v1/project-customization/workflows` | `list_workflows` |
| POST | `/api/v1/project-customization/workflows/{workflow_name}/run` | `run_workflow` |
| DELETE | `/api/v1/project-customization/workflows/{workflow_name}/template` | `delete_workflow_template` |
| GET | `/api/v1/project-customization/workflows/{workflow_name}/template` | `get_workflow_template` |
| POST | `/api/v1/project-customization/workflows/{workflow_name}/template` | `upsert_workflow_template` |

### projects.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/projects` | `list_projects` |
| POST | `/api/v1/projects` | `create_project` |
| POST | `/api/v1/projects/auto-create` | `auto_create_project` |
| POST | `/api/v1/projects/inject-initial` | `inject_initial_project` |
| DELETE | `/api/v1/projects/{project_key}` | `delete_project` |
| PATCH | `/api/v1/projects/{project_key}` | `update_project` |
| POST | `/api/v1/projects/{project_key}/activate` | `activate_project` |
| POST | `/api/v1/projects/{project_key}/archive` | `archive_project` |
| POST | `/api/v1/projects/{project_key}/restore` | `restore_project` |

### reports.py

| Method | Path | Handler |
|---|---|---|
| POST | `/api/v1/reports` | `create_report` |

### resource_pool.py

| Method | Path | Handler |
|---|---|---|
| POST | `/api/v1/resource_pool/capture/enable` | `capture_enable_api` |
| POST | `/api/v1/resource_pool/capture/from-tasks` | `capture_from_tasks_api` |
| POST | `/api/v1/resource_pool/discover/search-contract` | `discover_search_contract_api` |
| POST | `/api/v1/resource_pool/discover/site-entries` | `discover_site_entries_api` |
| POST | `/api/v1/resource_pool/extract/from-documents` | `extract_from_documents_api` |
| POST | `/api/v1/resource_pool/import/open-source-presets` | `import_open_source_presets_api` |
| GET | `/api/v1/resource_pool/open-source-presets` | `list_open_source_presets_api` |
| GET | `/api/v1/resource_pool/site-entries` | `list_site_entries_api` |
| POST | `/api/v1/resource_pool/site-entries` | `upsert_site_entry_api` |
| GET | `/api/v1/resource_pool/site-entries/grouped` | `group_site_entries_api` |
| GET | `/api/v1/resource_pool/site_entries` | `list_site_entries_api` |
| POST | `/api/v1/resource_pool/site_entries` | `upsert_site_entry_api` |
| GET | `/api/v1/resource_pool/site_entries/grouped` | `group_site_entries_api` |
| POST | `/api/v1/resource_pool/site_entries/recommend` | `recommend_site_entry_api` |
| POST | `/api/v1/resource_pool/site_entries/recommend-batch` | `recommend_site_entries_batch_api` |
| POST | `/api/v1/resource_pool/site_entries/simplify` | `simplify_site_entries_api` |
| POST | `/api/v1/resource_pool/source-library/collect` | `source_library_collect_api` |
| POST | `/api/v1/resource_pool/unified-search` | `unified_search_api` |
| GET | `/api/v1/resource_pool/urls` | `list_urls_api` |

### search.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/search` | `search` |
| POST | `/api/v1/search/_init` | `init_search_indices` |

### skills.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/skills` | `list_skills` |
| POST | `/api/v1/skills/invoke` | `invoke_skill_api` |

### source_library.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/source_library/channels` | `list_channels` |
| GET | `/api/v1/source_library/channels/grouped` | `list_channels_grouped_api` |
| POST | `/api/v1/source_library/external-projects/register` | `register_external_project` |
| POST | `/api/v1/source_library/handler_clusters/sync` | `sync_handler_clusters` |
| GET | `/api/v1/source_library/items` | `list_items` |
| POST | `/api/v1/source_library/items` | `upsert_project_item` |
| GET | `/api/v1/source_library/items/by_symbol` | `list_items_by_symbol_api` |
| GET | `/api/v1/source_library/items/grouped` | `list_items_grouped_api` |
| PUT | `/api/v1/source_library/items/{item_key}` | `update_project_item` |
| POST | `/api/v1/source_library/items/{item_key}/refresh` | `refresh_item` |
| POST | `/api/v1/source_library/sync_shared_from_files` | `sync_shared_from_files` |

### stats.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/stats/prompt-time-density` | `get_prompt_time_density` |
| GET | `/api/v1/stats/prompt-time-density/cloud` | `get_prompt_time_density_cloud` |
| GET | `/api/v1/stats/prompt-time-density/priority` | `get_prompt_time_density_priority` |
| GET | `/api/v1/stats/prompt-time-density/select-windows` | `select_prompt_time_windows` |

### topics.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/topics` | `list_topics` |
| POST | `/api/v1/topics` | `create_topic` |
| DELETE | `/api/v1/topics/{topic_id}` | `delete_topic` |
| PUT | `/api/v1/topics/{topic_id}` | `update_topic` |

### web_ui_routes.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/maps/usa` | `get_usa_map` |

### workflow_graph.py

| Method | Path | Handler |
|---|---|---|
| POST | `/api/v1/workflow-graph/compile` | `compile_workflow_graph` |
| GET | `/api/v1/workflow-graph/compiled/{graph_id}` | `get_workflow_graph_compiled` |
| GET | `/api/v1/workflow-graph/curated/{graph_id}` | `get_workflow_graph_curated_state` |
| GET | `/api/v1/workflow-graph/curated/{graph_id}/audit` | `list_workflow_graph_curated_audits` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/draft` | `save_workflow_graph_curated_draft` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/evidence-pack` | `build_workflow_graph_evidence_pack` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/handoff/reporting` | `build_workflow_graph_reporting_handoff` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/handoff/writing` | `build_workflow_graph_writing_handoff` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/rollback` | `rollback_workflow_graph_curated_state` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/submit` | `submit_workflow_graph_curated_draft` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/sync` | `sync_workflow_graph_curated_state` |
| GET | `/api/v1/workflow-graph/observability/failure-reasons` | `get_workflow_graph_failure_reasons` |
| POST | `/api/v1/workflow-graph/run` | `run_workflow_graph` |
| GET | `/api/v1/workflow-graph/runs/{run_id}` | `get_workflow_graph_run` |
| GET | `/api/v1/workflow-graph/runs/{run_id}/agent-session` | `get_workflow_graph_run_agent_session` |
| GET | `/api/v1/workflow-graph/runs/{run_id}/events` | `get_workflow_graph_run_events` |
| GET | `/api/v1/workflow-graph/runs/{run_id}/handoff` | `list_workflow_graph_run_handoffs` |
| GET | `/api/v1/workflow-graph/runs/{run_id}/handoff/{handoff_id}/replay` | `replay_workflow_graph_handoff` |
| GET | `/api/v1/workflow-graph/runs/{run_id}/replay` | `replay_workflow_graph_run` |
| GET | `/api/v1/workflow-graph/templates` | `list_workflow_graph_templates` |
| POST | `/api/v1/workflow-graph/templates` | `create_workflow_graph_template` |
| DELETE | `/api/v1/workflow-graph/templates/{template_id}` | `delete_workflow_graph_template` |
| GET | `/api/v1/workflow-graph/templates/{template_id}` | `get_workflow_graph_template` |
| PATCH | `/api/v1/workflow-graph/templates/{template_id}` | `patch_workflow_graph_template` |
| GET | `/api/v1/workflow-graph/templates/{template_id}/versions` | `list_workflow_graph_template_versions` |
| POST | `/api/v1/workflow-graph/templates/{template_id}/versions` | `create_workflow_graph_template_version` |
| GET | `/api/v1/workflow-graph/templates/{template_id}/versions/{version_id}` | `get_workflow_graph_template_version` |
| POST | `/api/v1/workflow-graph/templates/{template_id}/versions/{version_id}/activate` | `activate_workflow_graph_template_version` |

### writing.py

| Method | Path | Handler |
|---|---|---|
| GET | `/api/v1/writing/cards/{card_id}` | `get_writing_card_detail` |
| GET | `/api/v1/writing/documents` | `list_writing_documents` |
| POST | `/api/v1/writing/documents` | `create_writing_document` |
| DELETE | `/api/v1/writing/documents/{doc_id}` | `delete_writing_document` |
| GET | `/api/v1/writing/documents/{doc_id}` | `get_writing_document` |
| PATCH | `/api/v1/writing/documents/{doc_id}` | `patch_writing_document` |
| GET | `/api/v1/writing/documents/{doc_id}/citations` | `get_writing_document_citations` |
| POST | `/api/v1/writing/documents/{doc_id}/citations` | `post_writing_document_citations` |
| POST | `/api/v1/writing/documents/{doc_id}/draft` | `autosave_writing_document_draft` |
| POST | `/api/v1/writing/export/markdown` | `post_writing_export_markdown` |
| POST | `/api/v1/writing/keyword-cards` | `post_keyword_cards` |
| POST | `/api/v1/writing/keyword-cards/preview` | `post_keyword_card_preview` |
| POST | `/api/v1/writing/llm-actions` | `post_writing_llm_action` |
| GET | `/api/v1/writing/llm-actions/history` | `get_writing_llm_action_history` |
| GET | `/api/v1/writing/llm-actions/{job_id}` | `get_writing_llm_action_detail` |
| GET | `/api/v1/writing/suggest` | `get_writing_suggest` |
| GET | `/api/v1/writing/templates` | `get_writing_templates` |
| POST | `/api/v1/writing/templates/validate` | `post_writing_template_validate` |

## Notes

- This file captures route surface only, not full request/response schema.
- For payload contracts, inspect endpoint source modules and Pydantic models in `main/backend/app/contracts/`.
- Keep route-drift assertions in `main/backend/tests/contract/test_api_route_drift_contract_unittest.py` aligned with this snapshot when intentionally changing the public route surface.
