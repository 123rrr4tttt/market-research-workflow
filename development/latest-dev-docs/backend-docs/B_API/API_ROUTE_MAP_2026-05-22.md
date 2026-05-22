# Backend API Route Map (Current)

> Status: CURRENT as of 2026-05-22. Generated from `main/backend/app/api/*.py` by AST static parsing in the `codex/devdocs-backend-docs-route-map` lane.
>
> Scope: FastAPI routers mounted through `main/backend/app/api/__init__.py` and `main/backend/app/main.py` with `/api/v1`. This route map does not include application-level routes defined directly in `main.py` such as `/metrics`, `/api/v1/health`, map assets, static files, or HTML page routes.

## Summary

- Current API router routes: **250**.
- Previous route snapshot `API_ROUTE_INVENTORY_2026-02-27.md`: **135** routes, now historical/stale for current routing decisions.
- Net surface increase since the old snapshot baseline: **+115** route decorators.
- API modules with routes: **30**.
- Method distribution: `DELETE` 9, `GET` 115, `PATCH` 3, `POST` 117, `PUT` 6.
- Newly represented modules versus the old snapshot family: `agent_batch.py`, `agent_chat.py`, `agent_sessions.py`, `codex_auth.py`, `crawler.py`, `keywords.py`, `llm_report.py`, `skills.py`, `stats.py`, `workflow_graph.py`, `writing.py`.
- Notable expanded modules needing consumer-facing contract review: `admin.py`, `ingest.py`, `process.py`, `projects.py`, `resource_pool.py`, `source_library.py`.

## Staleness Decision

| Document | Status | Action |
|---|---|---|
| `API_ROUTE_INVENTORY_2026-02-27.md` | Outdated route snapshot | Keep as historical evidence; do not use as current API source. |
| `FRONTEND_MODERNIZATION_API_MAP_2026-02-27.md` | Partially stale frontend contract map | Keep P0 migration intent, but validate route availability against this file before implementation. |
| `接口层调查文档.md` | Architecture survey with stale counts | Keep architecture notes; update counts from this file when making current-state claims. |
| `main/MERGED_BACKEND_DOCS.md` | Needs current route count pointer | Updated to reference this route map as current source. |

## Module Route Counts

| Module | Prefix | Tags | Routes |
|---|---|---|---:|
| `admin.py` | `/admin` | `admin` | 17 |
| `agent_batch.py` | `/agent-batch` | `agent_batch` | 16 |
| `agent_chat.py` | `/agent-chat` | `agent_chat` | 4 |
| `agent_sessions.py` | `(none)` | `agent_sessions` | 16 |
| `codex_auth.py` | `/codex-auth` | `codex-auth` | 5 |
| `config.py` | `/config` | `config` | 4 |
| `crawler.py` | `/crawler` | `crawler` | 8 |
| `dashboard.py` | `/dashboard` | `dashboard` | 10 |
| `discovery.py` | `/discovery` | `discovery` | 5 |
| `governance.py` | `/governance` | `governance` | 2 |
| `indexer.py` | `/indexer` | `indexer` | 1 |
| `ingest.py` | `/ingest` | `ingest` | 19 |
| `keywords.py` | `/keywords` | `keywords` | 5 |
| `llm_config.py` | `/llm-config` | `llm-config` | 14 |
| `llm_report.py` | `/llm-report` | `llm-report` | 1 |
| `market.py` | `/market` | `market` | 2 |
| `policies.py` | `/policies` | `policies` | 4 |
| `process.py` | `/process` | `process` | 7 |
| `products.py` | `/products` | `products` | 4 |
| `project_customization.py` | `/project-customization` | `project-customization` | 8 |
| `projects.py` | `/projects` | `projects` | 9 |
| `reports.py` | `/reports` | `reports` | 1 |
| `resource_pool.py` | `/resource_pool` | `resource_pool` | 19 |
| `search.py` | `/search` | `search` | 2 |
| `skills.py` | `/skills` | `skills` | 2 |
| `source_library.py` | `/source_library` | `source_library` | 11 |
| `stats.py` | `/stats` | `stats` | 4 |
| `topics.py` | `/topics` | `topics` | 4 |
| `workflow_graph.py` | `/workflow-graph` | `workflow-graph` | 28 |
| `writing.py` | `/writing` | `writing` | 18 |

## Full Route Inventory

Line numbers are source line numbers from the current worktree and should be treated as navigation aids, not stable API identifiers.

### `admin.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/admin/content-graph` | `get_content_graph` | `main/backend/app/api/admin.py:1790` |
| POST | `/api/v1/admin/documents/bulk/extracted-data` | `bulk_update_document_extracted_data` | `main/backend/app/api/admin.py:1117` |
| POST | `/api/v1/admin/documents/delete` | `delete_documents` | `main/backend/app/api/admin.py:1167` |
| POST | `/api/v1/admin/documents/list` | `list_documents` | `main/backend/app/api/admin.py:900` |
| POST | `/api/v1/admin/documents/raw-import` | `raw_import_documents` | `main/backend/app/api/admin.py:882` |
| POST | `/api/v1/admin/documents/re-extract` | `re_extract_documents` | `main/backend/app/api/admin.py:1184` |
| POST | `/api/v1/admin/documents/topic-extract` | `topic_extract_documents` | `main/backend/app/api/admin.py:1295` |
| GET | `/api/v1/admin/documents/{doc_id}` | `get_document` | `main/backend/app/api/admin.py:1052` |
| POST | `/api/v1/admin/documents/{doc_id}/extracted-data` | `update_document_extracted_data` | `main/backend/app/api/admin.py:1091` |
| GET | `/api/v1/admin/export-graph` | `export_graph` | `main/backend/app/api/admin.py:1740` |
| GET | `/api/v1/admin/market-graph` | `get_market_graph` | `main/backend/app/api/admin.py:1914` |
| POST | `/api/v1/admin/market-stats/list` | `list_market_stats` | `main/backend/app/api/admin.py:1537` |
| GET | `/api/v1/admin/policy-graph` | `get_policy_graph` | `main/backend/app/api/admin.py:2074` |
| GET | `/api/v1/admin/search-history` | `get_search_history` | `main/backend/app/api/admin.py:2219` |
| POST | `/api/v1/admin/social-data/list` | `list_social_data` | `main/backend/app/api/admin.py:1635` |
| POST | `/api/v1/admin/sources/list` | `list_sources` | `main/backend/app/api/admin.py:1447` |
| GET | `/api/v1/admin/stats` | `get_stats` | `main/backend/app/api/admin.py:824` |

### `agent_batch.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| POST | `/api/v1/agent-batch/approvals/request` | `create_agent_batch_approval` | `main/backend/app/api/agent_batch.py:1612` |
| POST | `/api/v1/agent-batch/approvals/{approval_token}/resolve` | `resolve_agent_batch_approval` | `main/backend/app/api/agent_batch.py:1650` |
| GET | `/api/v1/agent-batch/executor/health` | `get_agent_batch_executor_health` | `main/backend/app/api/agent_batch.py:1752` |
| POST | `/api/v1/agent-batch/jobs` | `submit_agent_batch_job` | `main/backend/app/api/agent_batch.py:1075` |
| GET | `/api/v1/agent-batch/jobs/{job_id}` | `get_agent_batch_job` | `main/backend/app/api/agent_batch.py:1234` |
| GET | `/api/v1/agent-batch/jobs/{job_id}/events` | `get_agent_batch_events` | `main/backend/app/api/agent_batch.py:1380` |
| GET | `/api/v1/agent-batch/jobs/{job_id}/items` | `list_agent_batch_items` | `main/backend/app/api/agent_batch.py:1277` |
| POST | `/api/v1/agent-batch/jobs/{job_id}/retry` | `retry_agent_batch_job` | `main/backend/app/api/agent_batch.py:1316` |
| GET | `/api/v1/agent-batch/jobs/{job_id}/workflow-handoffs` | `list_agent_batch_job_workflow_handoffs` | `main/backend/app/api/agent_batch.py:1547` |
| GET | `/api/v1/agent-batch/metrics/search-policy` | `get_agent_batch_search_policy_metrics` | `main/backend/app/api/agent_batch.py:1532` |
| GET | `/api/v1/agent-batch/metrics/search-policy/benchmark-pack` | `get_agent_batch_search_policy_benchmark_pack` | `main/backend/app/api/agent_batch.py:1537` |
| GET | `/api/v1/agent-batch/metrics/search-policy/gate` | `get_agent_batch_search_policy_gate` | `main/backend/app/api/agent_batch.py:1542` |
| POST | `/api/v1/agent-batch/nl-command` | `run_agent_batch_nl_command` | `main/backend/app/api/agent_batch.py:1701` |
| POST | `/api/v1/agent-batch/nl-command/direct` | `run_agent_batch_nl_command_direct` | `main/backend/app/api/agent_batch.py:1746` |
| GET | `/api/v1/agent-batch/observability/failure-reasons` | `get_agent_batch_failure_reasons` | `main/backend/app/api/agent_batch.py:1607` |
| POST | `/api/v1/agent-batch/rule-sets/validate` | `validate_agent_batch_rule_set` | `main/backend/app/api/agent_batch.py:1671` |

### `agent_chat.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| POST | `/api/v1/agent-chat/approvals/{approval_id}/continue` | `continue_agent_chat_approval` | `main/backend/app/api/agent_chat.py:1455` |
| GET | `/api/v1/agent-chat/capabilities` | `list_agent_chat_capabilities` | `main/backend/app/api/agent_chat.py:1385` |
| POST | `/api/v1/agent-chat/turn` | `run_agent_chat_turn` | `main/backend/app/api/agent_chat.py:1400` |
| POST | `/api/v1/agent-chat/turn/stream` | `stream_agent_chat_turn` | `main/backend/app/api/agent_chat.py:1409` |

### `agent_sessions.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/agent-approvals` | `list_agent_approvals` | `main/backend/app/api/agent_sessions.py:198` |
| POST | `/api/v1/agent-approvals/{approval_id}/resolve` | `resolve_agent_approval` | `main/backend/app/api/agent_sessions.py:286` |
| GET | `/api/v1/agent-sessions` | `list_agent_sessions` | `main/backend/app/api/agent_sessions.py:130` |
| POST | `/api/v1/agent-sessions` | `create_agent_session` | `main/backend/app/api/agent_sessions.py:110` |
| GET | `/api/v1/agent-sessions/{session_id}` | `get_agent_session` | `main/backend/app/api/agent_sessions.py:136` |
| POST | `/api/v1/agent-sessions/{session_id}/actions/cancel` | `cancel_agent_session` | `main/backend/app/api/agent_sessions.py:240` |
| POST | `/api/v1/agent-sessions/{session_id}/actions/coordinator-pass` | `run_agent_session_coordinator_pass` | `main/backend/app/api/agent_sessions.py:260` |
| POST | `/api/v1/agent-sessions/{session_id}/actions/reclaim-expired` | `reclaim_agent_session_expired_tasks` | `main/backend/app/api/agent_sessions.py:250` |
| POST | `/api/v1/agent-sessions/{session_id}/actions/request-approval` | `request_agent_session_approval` | `main/backend/app/api/agent_sessions.py:270` |
| POST | `/api/v1/agent-sessions/{session_id}/actions/retry-task` | `retry_agent_session_task` | `main/backend/app/api/agent_sessions.py:228` |
| GET | `/api/v1/agent-sessions/{session_id}/artifacts` | `get_agent_session_artifacts` | `main/backend/app/api/agent_sessions.py:163` |
| GET | `/api/v1/agent-sessions/{session_id}/events` | `get_agent_session_events` | `main/backend/app/api/agent_sessions.py:154` |
| GET | `/api/v1/agent-sessions/{session_id}/messages` | `get_agent_session_messages` | `main/backend/app/api/agent_sessions.py:172` |
| POST | `/api/v1/agent-sessions/{session_id}/messages` | `create_agent_session_message` | `main/backend/app/api/agent_sessions.py:181` |
| GET | `/api/v1/agent-sessions/{session_id}/stream` | `stream_agent_session_events` | `main/backend/app/api/agent_sessions.py:204` |
| GET | `/api/v1/agent-sessions/{session_id}/tasks` | `get_agent_session_tasks` | `main/backend/app/api/agent_sessions.py:145` |

### `codex_auth.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/codex-auth/callback` | `codex_auth_callback` | `main/backend/app/api/codex_auth.py:87` |
| POST | `/api/v1/codex-auth/cli/bootstrap` | `codex_cli_bootstrap` | `main/backend/app/api/codex_auth.py:157` |
| GET | `/api/v1/codex-auth/login` | `codex_auth_login` | `main/backend/app/api/codex_auth.py:56` |
| POST | `/api/v1/codex-auth/logout` | `codex_auth_logout` | `main/backend/app/api/codex_auth.py:149` |
| GET | `/api/v1/codex-auth/status` | `codex_auth_status` | `main/backend/app/api/codex_auth.py:124` |

### `config.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/config` | `get_config` | `main/backend/app/api/config.py:35` |
| GET | `/api/v1/config/env` | `get_env_settings` | `main/backend/app/api/config.py:86` |
| POST | `/api/v1/config/env` | `update_env` | `main/backend/app/api/config.py:94` |
| POST | `/api/v1/config/reload` | `reload_env_settings` | `main/backend/app/api/config.py:108` |

### `crawler.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/crawler/deploy-runs` | `list_crawler_deploy_runs_api` | `main/backend/app/api/crawler.py:189` |
| GET | `/api/v1/crawler/deploy-runs/{run_id}` | `get_crawler_deploy_run_api` | `main/backend/app/api/crawler.py:178` |
| GET | `/api/v1/crawler/projects` | `list_crawler_projects_api` | `main/backend/app/api/crawler.py:103` |
| POST | `/api/v1/crawler/projects/import` | `import_crawler_project_api` | `main/backend/app/api/crawler.py:94` |
| GET | `/api/v1/crawler/projects/{project_key}` | `get_crawler_project_api` | `main/backend/app/api/crawler.py:125` |
| POST | `/api/v1/crawler/projects/{project_key}/deploy` | `deploy_crawler_project_api` | `main/backend/app/api/crawler.py:136` |
| GET | `/api/v1/crawler/projects/{project_key}/deploy-runs` | `list_crawler_project_deploy_runs_api` | `main/backend/app/api/crawler.py:202` |
| POST | `/api/v1/crawler/projects/{project_key}/rollback` | `rollback_crawler_project_api` | `main/backend/app/api/crawler.py:157` |

### `dashboard.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/dashboard/commodity-trends` | `get_commodity_trends` | `main/backend/app/api/dashboard.py:835` |
| GET | `/api/v1/dashboard/document-analysis` | `get_document_analysis` | `main/backend/app/api/dashboard.py:392` |
| GET | `/api/v1/dashboard/ecom-price-trends` | `get_ecom_price_trends` | `main/backend/app/api/dashboard.py:908` |
| GET | `/api/v1/dashboard/global/stats` | `get_global_stats` | `main/backend/app/api/dashboard.py:115` |
| GET | `/api/v1/dashboard/market-trends` | `get_market_trends` | `main/backend/app/api/dashboard.py:263` |
| GET | `/api/v1/dashboard/search-analytics` | `get_search_analytics` | `main/backend/app/api/dashboard.py:792` |
| GET | `/api/v1/dashboard/sentiment-analysis` | `get_sentiment_analysis` | `main/backend/app/api/dashboard.py:496` |
| GET | `/api/v1/dashboard/sentiment-sources` | `get_sentiment_sources` | `main/backend/app/api/dashboard.py:637` |
| GET | `/api/v1/dashboard/stats` | `get_dashboard_stats` | `main/backend/app/api/dashboard.py:141` |
| GET | `/api/v1/dashboard/task-monitoring` | `get_task_monitoring` | `main/backend/app/api/dashboard.py:730` |

### `discovery.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| POST | `/api/v1/discovery/deep` | `discovery_deep` | `main/backend/app/api/discovery.py:181` |
| POST | `/api/v1/discovery/generate-keywords` | `generate_keywords_api` | `main/backend/app/api/discovery.py:228` |
| POST | `/api/v1/discovery/generate-subreddit-keywords` | `generate_subreddit_keywords_api` | `main/backend/app/api/discovery.py:327` |
| POST | `/api/v1/discovery/search` | `discovery_search` | `main/backend/app/api/discovery.py:77` |
| POST | `/api/v1/discovery/smart` | `discovery_smart` | `main/backend/app/api/discovery.py:130` |

### `governance.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| POST | `/api/v1/governance/aggregator/sync` | `sync_aggregator` | `main/backend/app/api/governance.py:45` |
| POST | `/api/v1/governance/cleanup` | `cleanup` | `main/backend/app/api/governance.py:36` |

### `indexer.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| POST | `/api/v1/indexer/policy` | `reindex_policy` | `main/backend/app/api/indexer.py:49` |

### `ingest.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| POST | `/api/v1/ingest/commodity/metrics` | `ingest_commodity` | `main/backend/app/api/ingest.py:1903` |
| GET | `/api/v1/ingest/config` | `get_ingest_config_endpoint` | `main/backend/app/api/ingest.py:321` |
| POST | `/api/v1/ingest/config` | `post_ingest_config_endpoint` | `main/backend/app/api/ingest.py:334` |
| POST | `/api/v1/ingest/data-api` | `ingest_data_api` | `main/backend/app/api/ingest.py:1578` |
| POST | `/api/v1/ingest/ecom/prices` | `ingest_ecom_prices` | `main/backend/app/api/ingest.py:1923` |
| POST | `/api/v1/ingest/graph/structured-search` | `ingest_graph_structured_search` | `main/backend/app/api/ingest.py:1623` |
| GET | `/api/v1/ingest/history` | `ingest_history` | `main/backend/app/api/ingest.py:588` |
| POST | `/api/v1/ingest/market` | `ingest_market` | `main/backend/app/api/ingest.py:431` |
| GET | `/api/v1/ingest/news-resources` | `list_news_resources` | `main/backend/app/api/ingest.py:965` |
| POST | `/api/v1/ingest/news/resource/{resource_id}` | `ingest_news_resource` | `main/backend/app/api/ingest.py:994` |
| POST | `/api/v1/ingest/policy/regulation` | `ingest_policy_regulation` | `main/backend/app/api/ingest.py:1852` |
| POST | `/api/v1/ingest/reports/california` | `ingest_california_reports` | `main/backend/app/api/ingest.py:616` |
| POST | `/api/v1/ingest/reports/monthly` | `ingest_monthly_reports` | `main/backend/app/api/ingest.py:1059` |
| POST | `/api/v1/ingest/reports/weekly` | `ingest_weekly_reports` | `main/backend/app/api/ingest.py:1039` |
| POST | `/api/v1/ingest/social/reddit` | `ingest_reddit` | `main/backend/app/api/ingest.py:1019` |
| POST | `/api/v1/ingest/source-library/run` | `ingest_source_library_run` | `main/backend/app/api/ingest.py:872` |
| POST | `/api/v1/ingest/source-library/sync` | `ingest_source_library_sync` | `main/backend/app/api/ingest.py:954` |
| POST | `/api/v1/ingest/subprojects/{subproject_key}/news/{resource_id}` | `ingest_subproject_news_resource` | `main/backend/app/api/ingest.py:1000` |
| POST | `/api/v1/ingest/url/single` | `ingest_url_single` | `main/backend/app/api/ingest.py:483` |

### `keywords.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/keywords/history` | `get_keyword_history` | `main/backend/app/api/keywords.py:51` |
| GET | `/api/v1/keywords/priors` | `get_keyword_priors` | `main/backend/app/api/keywords.py:82` |
| POST | `/api/v1/keywords/priors/upsert` | `post_keyword_prior_upsert` | `main/backend/app/api/keywords.py:110` |
| GET | `/api/v1/keywords/stats` | `get_keyword_memory_stats` | `main/backend/app/api/keywords.py:43` |
| GET | `/api/v1/keywords/vectorization/candidates` | `get_vectorization_candidates` | `main/backend/app/api/keywords.py:140` |

### `llm_config.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/llm-config` | `list_llm_configs` | `main/backend/app/api/llm_config.py:179` |
| POST | `/api/v1/llm-config` | `create_llm_config` | `main/backend/app/api/llm_config.py:195` |
| GET | `/api/v1/llm-config/projects/{project_key}` | `list_llm_configs_by_project` | `main/backend/app/api/llm_config.py:231` |
| POST | `/api/v1/llm-config/projects/{project_key}` | `create_llm_config_by_project` | `main/backend/app/api/llm_config.py:261` |
| POST | `/api/v1/llm-config/projects/{project_key}/copy-from` | `copy_llm_configs_to_project` | `main/backend/app/api/llm_config.py:309` |
| DELETE | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `delete_llm_config_by_project` | `main/backend/app/api/llm_config.py:292` |
| GET | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `get_llm_config_by_project` | `main/backend/app/api/llm_config.py:245` |
| PUT | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `upsert_llm_config_by_project` | `main/backend/app/api/llm_config.py:278` |
| DELETE | `/api/v1/llm-config/service/{service_name}` | `delete_llm_config` | `main/backend/app/api/llm_config.py:221` |
| GET | `/api/v1/llm-config/service/{service_name}` | `get_llm_config` | `main/backend/app/api/llm_config.py:186` |
| PUT | `/api/v1/llm-config/service/{service_name}` | `update_llm_config` | `main/backend/app/api/llm_config.py:206` |
| DELETE | `/api/v1/llm-config/{service_name}` | `delete_llm_config_legacy` | `main/backend/app/api/llm_config.py:330` |
| GET | `/api/v1/llm-config/{service_name}` | `get_llm_config_legacy` | `main/backend/app/api/llm_config.py:320` |
| PUT | `/api/v1/llm-config/{service_name}` | `update_llm_config_legacy` | `main/backend/app/api/llm_config.py:325` |

### `llm_report.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| POST | `/api/v1/llm-report/generate` | `generate_llm_report` | `main/backend/app/api/llm_report.py:107` |

### `market.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/market` | `market_stats` | `main/backend/app/api/market.py:47` |
| GET | `/api/v1/market/games` | `market_games` | `main/backend/app/api/market.py:127` |

### `policies.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/policies` | `list_policies` | `main/backend/app/api/policies.py:84` |
| GET | `/api/v1/policies/state/{state}` | `get_state_policies` | `main/backend/app/api/policies.py:294` |
| GET | `/api/v1/policies/stats` | `get_policy_stats` | `main/backend/app/api/policies.py:202` |
| GET | `/api/v1/policies/{policy_id}` | `get_policy_detail` | `main/backend/app/api/policies.py:386` |

### `process.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/process/history` | `get_task_history` | `main/backend/app/api/process.py:473` |
| GET | `/api/v1/process/list` | `list_tasks` | `main/backend/app/api/process.py:225` |
| GET | `/api/v1/process/stats` | `get_task_stats` | `main/backend/app/api/process.py:426` |
| GET | `/api/v1/process/{task_id}` | `get_task_info` | `main/backend/app/api/process.py:690` |
| POST | `/api/v1/process/{task_id}/cancel` | `cancel_task` | `main/backend/app/api/process.py:580` |
| GET | `/api/v1/process/{task_id}/logs` | `get_task_logs` | `main/backend/app/api/process.py:850` |
| POST | `/api/v1/process/{task_id}/retry` | `retry_task` | `main/backend/app/api/process.py:748` |

### `products.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/products` | `list_products` | `main/backend/app/api/products.py:27` |
| POST | `/api/v1/products` | `create_product` | `main/backend/app/api/products.py:51` |
| DELETE | `/api/v1/products/{product_id}` | `delete_product` | `main/backend/app/api/products.py:92` |
| PUT | `/api/v1/products/{product_id}` | `update_product` | `main/backend/app/api/products.py:69` |

### `project_customization.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/project-customization/graph-config` | `get_graph_config` | `main/backend/app/api/project_customization.py:391` |
| GET | `/api/v1/project-customization/llm-mapping` | `get_llm_mapping` | `main/backend/app/api/project_customization.py:380` |
| GET | `/api/v1/project-customization/menu` | `get_menu_config` | `main/backend/app/api/project_customization.py:183` |
| GET | `/api/v1/project-customization/workflows` | `list_workflows` | `main/backend/app/api/project_customization.py:194` |
| POST | `/api/v1/project-customization/workflows/{workflow_name}/run` | `run_workflow` | `main/backend/app/api/project_customization.py:409` |
| DELETE | `/api/v1/project-customization/workflows/{workflow_name}/template` | `delete_workflow_template` | `main/backend/app/api/project_customization.py:337` |
| GET | `/api/v1/project-customization/workflows/{workflow_name}/template` | `get_workflow_template` | `main/backend/app/api/project_customization.py:254` |
| POST | `/api/v1/project-customization/workflows/{workflow_name}/template` | `upsert_workflow_template` | `main/backend/app/api/project_customization.py:268` |

### `projects.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/projects` | `list_projects` | `main/backend/app/api/projects.py:523` |
| POST | `/api/v1/projects` | `create_project` | `main/backend/app/api/projects.py:552` |
| POST | `/api/v1/projects/auto-create` | `auto_create_project` | `main/backend/app/api/projects.py:708` |
| POST | `/api/v1/projects/inject-initial` | `inject_initial_project` | `main/backend/app/api/projects.py:584` |
| DELETE | `/api/v1/projects/{project_key}` | `delete_project` | `main/backend/app/api/projects.py:884` |
| PATCH | `/api/v1/projects/{project_key}` | `update_project` | `main/backend/app/api/projects.py:762` |
| POST | `/api/v1/projects/{project_key}/activate` | `activate_project` | `main/backend/app/api/projects.py:863` |
| POST | `/api/v1/projects/{project_key}/archive` | `archive_project` | `main/backend/app/api/projects.py:813` |
| POST | `/api/v1/projects/{project_key}/restore` | `restore_project` | `main/backend/app/api/projects.py:848` |

### `reports.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| POST | `/api/v1/reports` | `create_report` | `main/backend/app/api/reports.py:20` |

### `resource_pool.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| POST | `/api/v1/resource_pool/capture/enable` | `capture_enable_api` | `main/backend/app/api/resource_pool.py:299` |
| POST | `/api/v1/resource_pool/capture/from-tasks` | `capture_from_tasks_api` | `main/backend/app/api/resource_pool.py:316` |
| POST | `/api/v1/resource_pool/discover/search-contract` | `discover_search_contract_api` | `main/backend/app/api/resource_pool.py:524` |
| POST | `/api/v1/resource_pool/discover/site-entries` | `discover_site_entries_api` | `main/backend/app/api/resource_pool.py:571` |
| POST | `/api/v1/resource_pool/extract/from-documents` | `extract_from_documents_api` | `main/backend/app/api/resource_pool.py:147` |
| POST | `/api/v1/resource_pool/import/open-source-presets` | `import_open_source_presets_api` | `main/backend/app/api/resource_pool.py:269` |
| GET | `/api/v1/resource_pool/open-source-presets` | `list_open_source_presets_api` | `main/backend/app/api/resource_pool.py:264` |
| GET | `/api/v1/resource_pool/site-entries` | `list_site_entries_api` | `main/backend/app/api/resource_pool.py:381` |
| POST | `/api/v1/resource_pool/site-entries` | `upsert_site_entry_api` | `main/backend/app/api/resource_pool.py:459` |
| GET | `/api/v1/resource_pool/site-entries/grouped` | `group_site_entries_api` | `main/backend/app/api/resource_pool.py:421` |
| GET | `/api/v1/resource_pool/site_entries` | `list_site_entries_api` | `main/backend/app/api/resource_pool.py:381` |
| POST | `/api/v1/resource_pool/site_entries` | `upsert_site_entry_api` | `main/backend/app/api/resource_pool.py:459` |
| GET | `/api/v1/resource_pool/site_entries/grouped` | `group_site_entries_api` | `main/backend/app/api/resource_pool.py:421` |
| POST | `/api/v1/resource_pool/site_entries/recommend` | `recommend_site_entry_api` | `main/backend/app/api/resource_pool.py:712` |
| POST | `/api/v1/resource_pool/site_entries/recommend-batch` | `recommend_site_entries_batch_api` | `main/backend/app/api/resource_pool.py:739` |
| POST | `/api/v1/resource_pool/site_entries/simplify` | `simplify_site_entries_api` | `main/backend/app/api/resource_pool.py:680` |
| POST | `/api/v1/resource_pool/source-library/collect` | `source_library_collect_api` | `main/backend/app/api/resource_pool.py:878` |
| POST | `/api/v1/resource_pool/unified-search` | `unified_search_api` | `main/backend/app/api/resource_pool.py:843` |
| GET | `/api/v1/resource_pool/urls` | `list_urls_api` | `main/backend/app/api/resource_pool.py:202` |

### `search.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/search` | `search` | `main/backend/app/api/search.py:37` |
| POST | `/api/v1/search/_init` | `init_search_indices` | `main/backend/app/api/search.py:91` |

### `skills.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/skills` | `list_skills` | `main/backend/app/api/skills.py:48` |
| POST | `/api/v1/skills/invoke` | `invoke_skill_api` | `main/backend/app/api/skills.py:53` |

### `source_library.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/source_library/channels` | `list_channels` | `main/backend/app/api/source_library.py:272` |
| GET | `/api/v1/source_library/channels/grouped` | `list_channels_grouped_api` | `main/backend/app/api/source_library.py:350` |
| POST | `/api/v1/source_library/external-projects/register` | `register_external_project` | `main/backend/app/api/source_library.py:635` |
| POST | `/api/v1/source_library/handler_clusters/sync` | `sync_handler_clusters` | `main/backend/app/api/source_library.py:758` |
| GET | `/api/v1/source_library/items` | `list_items` | `main/backend/app/api/source_library.py:286` |
| POST | `/api/v1/source_library/items` | `upsert_project_item` | `main/backend/app/api/source_library.py:561` |
| GET | `/api/v1/source_library/items/by_symbol` | `list_items_by_symbol_api` | `main/backend/app/api/source_library.py:335` |
| GET | `/api/v1/source_library/items/grouped` | `list_items_grouped_api` | `main/backend/app/api/source_library.py:365` |
| PUT | `/api/v1/source_library/items/{item_key}` | `update_project_item` | `main/backend/app/api/source_library.py:702` |
| POST | `/api/v1/source_library/items/{item_key}/refresh` | `refresh_item` | `main/backend/app/api/source_library.py:721` |
| POST | `/api/v1/source_library/sync_shared_from_files` | `sync_shared_from_files` | `main/backend/app/api/source_library.py:867` |

### `stats.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/stats/prompt-time-density` | `get_prompt_time_density` | `main/backend/app/api/stats.py:76` |
| GET | `/api/v1/stats/prompt-time-density/cloud` | `get_prompt_time_density_cloud` | `main/backend/app/api/stats.py:116` |
| GET | `/api/v1/stats/prompt-time-density/priority` | `get_prompt_time_density_priority` | `main/backend/app/api/stats.py:162` |
| GET | `/api/v1/stats/prompt-time-density/select-windows` | `select_prompt_time_windows` | `main/backend/app/api/stats.py:211` |

### `topics.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/topics` | `list_topics` | `main/backend/app/api/topics.py:39` |
| POST | `/api/v1/topics` | `create_topic` | `main/backend/app/api/topics.py:63` |
| DELETE | `/api/v1/topics/{topic_id}` | `delete_topic` | `main/backend/app/api/topics.py:117` |
| PUT | `/api/v1/topics/{topic_id}` | `update_topic` | `main/backend/app/api/topics.py:87` |

### `workflow_graph.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| POST | `/api/v1/workflow-graph/compile` | `compile_workflow_graph` | `main/backend/app/api/workflow_graph.py:355` |
| GET | `/api/v1/workflow-graph/compiled/{graph_id}` | `get_workflow_graph_compiled` | `main/backend/app/api/workflow_graph.py:420` |
| GET | `/api/v1/workflow-graph/curated/{graph_id}` | `get_workflow_graph_curated_state` | `main/backend/app/api/workflow_graph.py:565` |
| GET | `/api/v1/workflow-graph/curated/{graph_id}/audit` | `list_workflow_graph_curated_audits` | `main/backend/app/api/workflow_graph.py:605` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/draft` | `save_workflow_graph_curated_draft` | `main/backend/app/api/workflow_graph.py:573` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/evidence-pack` | `build_workflow_graph_evidence_pack` | `main/backend/app/api/workflow_graph.py:613` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/handoff/reporting` | `build_workflow_graph_reporting_handoff` | `main/backend/app/api/workflow_graph.py:621` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/handoff/writing` | `build_workflow_graph_writing_handoff` | `main/backend/app/api/workflow_graph.py:632` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/rollback` | `rollback_workflow_graph_curated_state` | `main/backend/app/api/workflow_graph.py:597` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/submit` | `submit_workflow_graph_curated_draft` | `main/backend/app/api/workflow_graph.py:581` |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/sync` | `sync_workflow_graph_curated_state` | `main/backend/app/api/workflow_graph.py:589` |
| GET | `/api/v1/workflow-graph/observability/failure-reasons` | `get_workflow_graph_failure_reasons` | `main/backend/app/api/workflow_graph.py:669` |
| POST | `/api/v1/workflow-graph/run` | `run_workflow_graph` | `main/backend/app/api/workflow_graph.py:368` |
| GET | `/api/v1/workflow-graph/runs/{run_id}` | `get_workflow_graph_run` | `main/backend/app/api/workflow_graph.py:381` |
| GET | `/api/v1/workflow-graph/runs/{run_id}/agent-session` | `get_workflow_graph_run_agent_session` | `main/backend/app/api/workflow_graph.py:407` |
| GET | `/api/v1/workflow-graph/runs/{run_id}/events` | `get_workflow_graph_run_events` | `main/backend/app/api/workflow_graph.py:394` |
| GET | `/api/v1/workflow-graph/runs/{run_id}/handoff` | `list_workflow_graph_run_handoffs` | `main/backend/app/api/workflow_graph.py:643` |
| GET | `/api/v1/workflow-graph/runs/{run_id}/handoff/{handoff_id}/replay` | `replay_workflow_graph_handoff` | `main/backend/app/api/workflow_graph.py:656` |
| GET | `/api/v1/workflow-graph/runs/{run_id}/replay` | `replay_workflow_graph_run` | `main/backend/app/api/workflow_graph.py:433` |
| GET | `/api/v1/workflow-graph/templates` | `list_workflow_graph_templates` | `main/backend/app/api/workflow_graph.py:446` |
| POST | `/api/v1/workflow-graph/templates` | `create_workflow_graph_template` | `main/backend/app/api/workflow_graph.py:457` |
| DELETE | `/api/v1/workflow-graph/templates/{template_id}` | `delete_workflow_graph_template` | `main/backend/app/api/workflow_graph.py:496` |
| GET | `/api/v1/workflow-graph/templates/{template_id}` | `get_workflow_graph_template` | `main/backend/app/api/workflow_graph.py:470` |
| PATCH | `/api/v1/workflow-graph/templates/{template_id}` | `patch_workflow_graph_template` | `main/backend/app/api/workflow_graph.py:483` |
| GET | `/api/v1/workflow-graph/templates/{template_id}/versions` | `list_workflow_graph_template_versions` | `main/backend/app/api/workflow_graph.py:509` |
| POST | `/api/v1/workflow-graph/templates/{template_id}/versions` | `create_workflow_graph_template_version` | `main/backend/app/api/workflow_graph.py:522` |
| GET | `/api/v1/workflow-graph/templates/{template_id}/versions/{version_id}` | `get_workflow_graph_template_version` | `main/backend/app/api/workflow_graph.py:535` |
| POST | `/api/v1/workflow-graph/templates/{template_id}/versions/{version_id}/activate` | `activate_workflow_graph_template_version` | `main/backend/app/api/workflow_graph.py:548` |

### `writing.py`

| Method | Path | Handler | Source |
|---|---|---|---|
| GET | `/api/v1/writing/cards/{card_id}` | `get_writing_card_detail` | `main/backend/app/api/writing.py:304` |
| GET | `/api/v1/writing/documents` | `list_writing_documents` | `main/backend/app/api/writing.py:149` |
| POST | `/api/v1/writing/documents` | `create_writing_document` | `main/backend/app/api/writing.py:156` |
| DELETE | `/api/v1/writing/documents/{doc_id}` | `delete_writing_document` | `main/backend/app/api/writing.py:181` |
| GET | `/api/v1/writing/documents/{doc_id}` | `get_writing_document` | `main/backend/app/api/writing.py:171` |
| PATCH | `/api/v1/writing/documents/{doc_id}` | `patch_writing_document` | `main/backend/app/api/writing.py:200` |
| GET | `/api/v1/writing/documents/{doc_id}/citations` | `get_writing_document_citations` | `main/backend/app/api/writing.py:263` |
| POST | `/api/v1/writing/documents/{doc_id}/citations` | `post_writing_document_citations` | `main/backend/app/api/writing.py:245` |
| POST | `/api/v1/writing/documents/{doc_id}/draft` | `autosave_writing_document_draft` | `main/backend/app/api/writing.py:223` |
| POST | `/api/v1/writing/export/markdown` | `post_writing_export_markdown` | `main/backend/app/api/writing.py:382` |
| POST | `/api/v1/writing/keyword-cards` | `post_keyword_cards` | `main/backend/app/api/writing.py:285` |
| POST | `/api/v1/writing/keyword-cards/preview` | `post_keyword_card_preview` | `main/backend/app/api/writing.py:293` |
| POST | `/api/v1/writing/llm-actions` | `post_writing_llm_action` | `main/backend/app/api/writing.py:349` |
| GET | `/api/v1/writing/llm-actions/history` | `get_writing_llm_action_history` | `main/backend/app/api/writing.py:364` |
| GET | `/api/v1/writing/llm-actions/{job_id}` | `get_writing_llm_action_detail` | `main/backend/app/api/writing.py:372` |
| GET | `/api/v1/writing/suggest` | `get_writing_suggest` | `main/backend/app/api/writing.py:328` |
| GET | `/api/v1/writing/templates` | `get_writing_templates` | `main/backend/app/api/writing.py:273` |
| POST | `/api/v1/writing/templates/validate` | `post_writing_template_validate` | `main/backend/app/api/writing.py:278` |

## Follow-Up Contract Work

1. If a frontend lane consumes this route map, use `API_SCHEMA_INVENTORY_2026-05-22.md` or generate OpenAPI / typed clients from the running FastAPI app instead of copying tables by hand.
2. Re-check envelope consistency for expanded modules before declaring `API_CONTRACT_STANDARD.md` fully current; this route map plus the schema inventory prove advertised route/schema surface, not every runtime response shape.
3. Keep historical snapshots in `B_API/` but point new planning work to this file, `API_SCHEMA_INVENTORY_2026-05-22.md`, or a newer generated inventory.
