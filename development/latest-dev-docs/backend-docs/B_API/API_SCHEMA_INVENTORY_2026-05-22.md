# Backend API Schema Inventory (Current)

> Status: CURRENT as of 2026-05-22. Generated from the running FastAPI app OpenAPI surface by `main/backend/scripts/generate_api_schema_inventory.py`.
>
> Scope: every `/api/v1` OpenAPI operation exposed by `app.main.app`, including the 256 router operations covered by `API_ROUTE_MAP_2026-05-22.md` plus 3 non-`app.api` operations (`/api/v1/health`, `/api/v1/health/deep`, `/api/v1/maps/usa`).
>
> Drift guard: `main/backend/tests/contract/test_api_schema_inventory_contract_unittest.py` regenerates this document from the current FastAPI OpenAPI schema and compares it byte-for-byte.

## Summary

- OpenAPI `/api/v1` operations: **259**.
- API router operations also covered by `API_ROUTE_MAP_2026-05-22.md`: **256**.
- App-level `/api/v1` operations outside `main/backend/app/api/*.py`: **3**.
- Component schemas advertised by OpenAPI: **238**.
- Method distribution: `DELETE` 9, `GET` 120, `PATCH` 3, `POST` 121, `PUT` 6.
- Operations with JSON request bodies: **118**.
- Operations with explicit FastAPI `response_model`: **254**.
- Operations whose OpenAPI 200 response schema is still untyped: **0**.
- 200 response schema distribution: `ApiEnvelope_Any_` 38, `ApiEnvelope_ClueChainCloseData_` 1, `ApiEnvelope_ClueChainDecisionResponseData_` 1, `ApiEnvelope_ClueChainDetailData_` 2, `ApiEnvelope_ClueChainExpansionData_` 1, `ApiEnvelope_ClueChainListData_` 1, `ApiEnvelope_CopyLlmConfigsData_` 1, `ApiEnvelope_CrawlerDeployActionData_` 2, `ApiEnvelope_CrawlerDeployRunData_` 1, `ApiEnvelope_CrawlerDeployRunsData_` 2, `ApiEnvelope_CrawlerProjectData_` 2, `ApiEnvelope_CrawlerProjectsData_` 1, `ApiEnvelope_EnvSettingsUpdateData_` 1, `ApiEnvelope_KeywordCardDetailResponse_` 1, `ApiEnvelope_KeywordCardListResponse_` 1, `ApiEnvelope_KeywordCardPreviewResponse_` 1, `ApiEnvelope_KeywordHistoryData_` 1, `ApiEnvelope_KeywordPriorUpsertData_` 1, `ApiEnvelope_KeywordPriorsData_` 1, `ApiEnvelope_KeywordVectorizationCandidatesData_` 1, `ApiEnvelope_LlmActionHistoryItem_` 1, `ApiEnvelope_LlmActionHistoryListData_` 1, `ApiEnvelope_LlmActionResponse_` 1, `ApiEnvelope_LlmConfigMessageData_` 2, `ApiEnvelope_LlmServiceConfigResponse_` 5, `ApiEnvelope_PoliciesListData_` 1, `ApiEnvelope_PolicyDetail_` 1, `ApiEnvelope_PolicyStateDetail_` 1, `ApiEnvelope_PolicyStats_` 1, `ApiEnvelope_ProjectLlmConfigItemData_` 3, `ApiEnvelope_ProjectLlmConfigListData_` 1, `ApiEnvelope_ProjectLlmConfigMessageData_` 1, `ApiEnvelope_PromptTimeDensityCloudData_` 1, `ApiEnvelope_PromptTimeDensityData_` 1, `ApiEnvelope_PromptTimeDensityPriorityData_` 1, `ApiEnvelope_PromptTimeDensityWindowSelectionData_` 1, `ApiEnvelope_ReloadConfigData_` 1, `ApiEnvelope_RuntimeConfigData_` 1, `ApiEnvelope_SuggestResponse_` 1, `ApiEnvelope_TemplateValidateResponse_` 1, `ApiEnvelope_WorkflowGraphAuditListData_` 1, `ApiEnvelope_WorkflowGraphCuratedStateData_` 5, `ApiEnvelope_WorkflowGraphEvidencePackData_` 1, `ApiEnvelope_WorkflowGraphHandoffData_` 2, `ApiEnvelope_WorkflowGraphHandoffListData_` 1, `ApiEnvelope_WorkflowGraphHandoffReplayData_` 1, `ApiEnvelope_WritingCitationListData_` 2, `ApiEnvelope_WritingDocumentData_` 3, `ApiEnvelope_WritingDocumentDeleteData_` 1, `ApiEnvelope_WritingDocumentDraftData_` 1, `ApiEnvelope_WritingDocumentListData_` 1, `ApiEnvelope_WritingTemplateListData_` 1, `ApiEnvelope_dict_str__Any__` 86, `ApiEnvelope_list_LlmServiceConfigResponse__` 1, `missing` 2, `non-json` 3, `object` 59.

## Contract Meaning

This inventory records the request-body models, visible response models, OpenAPI 200-response schema labels, parameters, operation IDs, and response status-code sets that clients can infer from the current FastAPI application.

It does not prove runtime envelope conformance for every handler. A typed OpenAPI surface can still use conservative `dict[str, Any]`, `Any`, `object`, `non-json`, or `missing` response labels where handlers return legacy payloads, redirects, static/non-JSON content, or status-code-specific responses. Tightening those internals needs per-route runtime envelope tests beyond this schema-surface inventory.

## Source Summary

| Source Module | Operations | Request Bodies | Explicit Response Models | Untyped 200 Schemas |
|---|---:|---:|---:|---:|
| admin.py | 17 | 10 | 17 | 0 |
| agent_batch.py | 16 | 7 | 16 | 0 |
| agent_chat.py | 4 | 3 | 3 | 0 |
| agent_sessions.py | 16 | 5 | 15 | 0 |
| app.web_ui_routes | 1 | 0 | 1 | 0 |
| clue_chains.py | 6 | 4 | 6 | 0 |
| codex_auth.py | 5 | 0 | 3 | 0 |
| config.py | 4 | 1 | 4 | 0 |
| crawler.py | 8 | 3 | 8 | 0 |
| dashboard.py | 10 | 0 | 10 | 0 |
| discovery.py | 5 | 5 | 5 | 0 |
| governance.py | 2 | 2 | 2 | 0 |
| indexer.py | 1 | 1 | 1 | 0 |
| ingest.py | 19 | 16 | 19 | 0 |
| keywords.py | 5 | 1 | 5 | 0 |
| llm_config.py | 14 | 6 | 14 | 0 |
| llm_report.py | 1 | 1 | 1 | 0 |
| main.py | 2 | 0 | 2 | 0 |
| market.py | 2 | 0 | 2 | 0 |
| policies.py | 4 | 0 | 4 | 0 |
| process.py | 7 | 0 | 7 | 0 |
| products.py | 4 | 2 | 4 | 0 |
| project_customization.py | 8 | 2 | 8 | 0 |
| projects.py | 9 | 4 | 9 | 0 |
| reports.py | 1 | 1 | 1 | 0 |
| resource_pool.py | 19 | 13 | 19 | 0 |
| search.py | 2 | 0 | 2 | 0 |
| skills.py | 2 | 1 | 2 | 0 |
| source_library.py | 11 | 5 | 11 | 0 |
| stats.py | 4 | 0 | 4 | 0 |
| topics.py | 4 | 2 | 4 | 0 |
| workflow_graph.py | 28 | 14 | 28 | 0 |
| writing.py | 18 | 9 | 17 | 0 |

## Operation Inventory

| Method | Path | Handler | Source | Path Params | Query Params | Request Body | Response Model | 200 Schema | Statuses |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/api/v1/health` | `health_check` | `main.py` | - | - | `-` | `dict` | `object` | 200 |
| GET | `/api/v1/health/deep` | `deep_health_check` | `main.py` | - | - | `-` | `dict` | `object` | 200 |
| GET | `/api/v1/maps/usa` | `get_usa_map` | `app.web_ui_routes` | - | - | `-` | `dict` | `object` | 200 |
| GET | `/api/v1/policies` | `list_policies` | `policies.py` | - | state?, policy_type?, status?, start?, end?, start_date?, end_date?, page?, page_size?, sort_by?, sort_order? | `-` | `ApiEnvelope[PoliciesListData]` | `ApiEnvelope_PoliciesListData_` | 200, 422 |
| GET | `/api/v1/policies/stats` | `get_policy_stats` | `policies.py` | - | start?, end?, start_date?, end_date? | `-` | `ApiEnvelope[PolicyStats]` | `ApiEnvelope_PolicyStats_` | 200, 422 |
| GET | `/api/v1/policies/state/{state}` | `get_state_policies` | `policies.py` | state | start?, end?, start_date?, end_date? | `-` | `ApiEnvelope[PolicyStateDetail]` | `ApiEnvelope_PolicyStateDetail_` | 200, 422 |
| GET | `/api/v1/policies/{policy_id}` | `get_policy_detail` | `policies.py` | policy_id | - | `-` | `ApiEnvelope[PolicyDetail]` | `ApiEnvelope_PolicyDetail_` | 200, 422 |
| GET | `/api/v1/market` | `market_stats` | `market.py` | - | state, period?, game? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/market/games` | `market_games` | `market.py` | - | state | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/search` | `search` | `search.py` | - | q?, state?, modality?, rank?, top_k? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/search/_init` | `init_search_indices` | `search.py` | - | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200 |
| POST | `/api/v1/reports` | `create_report` | `reports.py` | - | - | `ReportRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/config` | `get_config` | `config.py` | - | - | `-` | `ApiEnvelope[RuntimeConfigData]` | `ApiEnvelope_RuntimeConfigData_` | 200 |
| GET | `/api/v1/config/env` | `get_env_settings` | `config.py` | - | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200 |
| POST | `/api/v1/config/env` | `update_env` | `config.py` | - | - | `EnvSettingsPayload` | `ApiEnvelope[EnvSettingsUpdateData]` | `ApiEnvelope_EnvSettingsUpdateData_` | 200, 422 |
| POST | `/api/v1/config/reload` | `reload_env_settings` | `config.py` | - | - | `-` | `ApiEnvelope[ReloadConfigData]` | `ApiEnvelope_ReloadConfigData_` | 200 |
| GET | `/api/v1/ingest/config` | `get_ingest_config_endpoint` | `ingest.py` | - | project_key?, config_key | `-` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/config` | `post_ingest_config_endpoint` | `ingest.py` | - | - | `IngestConfigUpsertPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/market` | `ingest_market` | `ingest.py` | - | - | `MarketIngestRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/url/single` | `ingest_url_single` | `ingest.py` | - | - | `SingleUrlIngestRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| GET | `/api/v1/ingest/history` | `ingest_history` | `ingest.py` | - | limit? | `-` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/reports/california` | `ingest_california_reports` | `ingest.py` | - | - | `CaliforniaReportRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/source-library/run` | `ingest_source_library_run` | `ingest.py` | - | - | `SourceLibraryRunPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/source-library/sync` | `ingest_source_library_sync` | `ingest.py` | - | - | `SourceLibrarySyncPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| GET | `/api/v1/ingest/news-resources` | `list_news_resources` | `ingest.py` | - | project_key?, scope? | `-` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/news/resource/{resource_id}` | `ingest_news_resource` | `ingest.py` | resource_id | - | `NewsRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/subprojects/{subproject_key}/news/{resource_id}` | `ingest_subproject_news_resource` | `ingest.py` | subproject_key, resource_id | - | `NewsRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/social/reddit` | `ingest_reddit` | `ingest.py` | - | - | `RedditRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/reports/weekly` | `ingest_weekly_reports` | `ingest.py` | - | - | `NewsRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/reports/monthly` | `ingest_monthly_reports` | `ingest.py` | - | - | `NewsRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/data-api` | `ingest_data_api` | `ingest.py` | - | - | `DataApiRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/graph/structured-search` | `ingest_graph_structured_search` | `ingest.py` | - | - | `GraphStructuredSearchRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/policy/regulation` | `ingest_policy_regulation` | `ingest.py` | - | - | `PolicyRegulationRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/commodity/metrics` | `ingest_commodity` | `ingest.py` | - | - | `CommodityRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/ingest/ecom/prices` | `ingest_ecom_prices` | `ingest.py` | - | - | `EcomPriceRequest` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/discovery/search` | `discovery_search` | `discovery.py` | - | debug?, persist? | `DiscoveryRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 400, 404, 422, 429, 500, 502 |
| POST | `/api/v1/discovery/smart` | `discovery_smart` | `discovery.py` | - | persist? | `SmartDiscoveryRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 400, 404, 422, 429, 500, 502 |
| POST | `/api/v1/discovery/deep` | `discovery_deep` | `discovery.py` | - | persist? | `DeepDiscoveryRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 400, 404, 422, 429, 500, 502 |
| POST | `/api/v1/discovery/generate-keywords` | `generate_keywords_api` | `discovery.py` | - | - | `KeywordGenerationRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 400, 404, 422, 429, 500, 502 |
| POST | `/api/v1/discovery/generate-subreddit-keywords` | `generate_subreddit_keywords_api` | `discovery.py` | - | - | `SubredditKeywordGenerationRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 400, 404, 422, 429, 500, 502 |
| POST | `/api/v1/indexer/policy` | `reindex_policy` | `indexer.py` | - | - | `ReindexPolicyRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/admin/stats` | `get_stats` | `admin.py` | - | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200 |
| POST | `/api/v1/admin/documents/raw-import` | `raw_import_documents` | `admin.py` | - | - | `RawImportRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/admin/documents/list` | `list_documents` | `admin.py` | - | - | `DocumentListRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/admin/documents/{doc_id}` | `get_document` | `admin.py` | doc_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/admin/documents/{doc_id}/extracted-data` | `update_document_extracted_data` | `admin.py` | doc_id | - | `UpdateExtractedDataRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/admin/documents/bulk/extracted-data` | `bulk_update_document_extracted_data` | `admin.py` | - | - | `BulkUpdateExtractedDataRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/admin/documents/delete` | `delete_documents` | `admin.py` | - | - | `DeleteDocumentsRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/admin/documents/re-extract` | `re_extract_documents` | `admin.py` | - | - | `ReExtractRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/admin/documents/topic-extract` | `topic_extract_documents` | `admin.py` | - | - | `TopicExtractRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/admin/sources/list` | `list_sources` | `admin.py` | - | - | `SourceListRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/admin/market-stats/list` | `list_market_stats` | `admin.py` | - | - | `MarketStatsListRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/admin/social-data/list` | `list_social_data` | `admin.py` | - | - | `SocialDataListRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/admin/export-graph` | `export_graph` | `admin.py` | - | doc_ids | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/admin/content-graph` | `get_content_graph` | `admin.py` | - | start_date?, end_date?, platform?, topic?, limit? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/admin/market-graph` | `get_market_graph` | `admin.py` | - | start_date?, end_date?, state?, game?, view?, topic_scope?, limit? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/admin/policy-graph` | `get_policy_graph` | `admin.py` | - | start_date?, end_date?, state?, policy_type?, limit? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/admin/search-history` | `get_search_history` | `admin.py` | - | page?, page_size? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/dashboard/global/stats` | `get_global_stats` | `dashboard.py` | - | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200 |
| GET | `/api/v1/dashboard/stats` | `get_dashboard_stats` | `dashboard.py` | - | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200 |
| GET | `/api/v1/dashboard/market-trends` | `get_market_trends` | `dashboard.py` | - | state?, game?, start_date?, end_date?, period? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/dashboard/document-analysis` | `get_document_analysis` | `dashboard.py` | - | start_date?, end_date? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/dashboard/sentiment-analysis` | `get_sentiment_analysis` | `dashboard.py` | - | start_date?, end_date? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/dashboard/sentiment-sources` | `get_sentiment_sources` | `dashboard.py` | - | sentiment?, platform?, start_date?, end_date?, limit? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/dashboard/task-monitoring` | `get_task_monitoring` | `dashboard.py` | - | limit?, status? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/dashboard/search-analytics` | `get_search_analytics` | `dashboard.py` | - | limit? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/dashboard/commodity-trends` | `get_commodity_trends` | `dashboard.py` | - | metric_key?, start_date?, end_date?, period? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/dashboard/ecom-price-trends` | `get_ecom_price_trends` | `dashboard.py` | - | product_id?, start_date?, end_date? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/llm-config` | `list_llm_configs` | `llm_config.py` | - | - | `-` | `ApiEnvelope[list[LlmServiceConfigResponse]]` | `ApiEnvelope_list_LlmServiceConfigResponse__` | 200 |
| POST | `/api/v1/llm-config` | `create_llm_config` | `llm_config.py` | - | - | `LlmServiceConfigCreate` | `ApiEnvelope[LlmServiceConfigResponse]` | `ApiEnvelope_LlmServiceConfigResponse_` | 200, 422 |
| DELETE | `/api/v1/llm-config/service/{service_name}` | `delete_llm_config` | `llm_config.py` | service_name | - | `-` | `ApiEnvelope[LlmConfigMessageData]` | `ApiEnvelope_LlmConfigMessageData_` | 200, 422 |
| GET | `/api/v1/llm-config/service/{service_name}` | `get_llm_config` | `llm_config.py` | service_name | - | `-` | `ApiEnvelope[LlmServiceConfigResponse]` | `ApiEnvelope_LlmServiceConfigResponse_` | 200, 422 |
| PUT | `/api/v1/llm-config/service/{service_name}` | `update_llm_config` | `llm_config.py` | service_name | - | `LlmServiceConfigUpdate` | `ApiEnvelope[LlmServiceConfigResponse]` | `ApiEnvelope_LlmServiceConfigResponse_` | 200, 422 |
| GET | `/api/v1/llm-config/projects/{project_key}` | `list_llm_configs_by_project` | `llm_config.py` | project_key | - | `-` | `ApiEnvelope[ProjectLlmConfigListData]` | `ApiEnvelope_ProjectLlmConfigListData_` | 200, 422 |
| POST | `/api/v1/llm-config/projects/{project_key}` | `create_llm_config_by_project` | `llm_config.py` | project_key | - | `LlmServiceConfigCreate` | `ApiEnvelope[ProjectLlmConfigItemData]` | `ApiEnvelope_ProjectLlmConfigItemData_` | 200, 422 |
| DELETE | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `delete_llm_config_by_project` | `llm_config.py` | project_key, service_name | - | `-` | `ApiEnvelope[ProjectLlmConfigMessageData]` | `ApiEnvelope_ProjectLlmConfigMessageData_` | 200, 422 |
| GET | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `get_llm_config_by_project` | `llm_config.py` | project_key, service_name | - | `-` | `ApiEnvelope[ProjectLlmConfigItemData]` | `ApiEnvelope_ProjectLlmConfigItemData_` | 200, 422 |
| PUT | `/api/v1/llm-config/projects/{project_key}/{service_name}` | `upsert_llm_config_by_project` | `llm_config.py` | project_key, service_name | - | `LlmServiceConfigUpdate` | `ApiEnvelope[ProjectLlmConfigItemData]` | `ApiEnvelope_ProjectLlmConfigItemData_` | 200, 422 |
| POST | `/api/v1/llm-config/projects/{project_key}/copy-from` | `copy_llm_configs_to_project` | `llm_config.py` | project_key | - | `CopyLlmConfigsRequest` | `ApiEnvelope[CopyLlmConfigsData]` | `ApiEnvelope_CopyLlmConfigsData_` | 200, 422 |
| DELETE | `/api/v1/llm-config/{service_name}` | `delete_llm_config_legacy` | `llm_config.py` | service_name | - | `-` | `ApiEnvelope[LlmConfigMessageData]` | `ApiEnvelope_LlmConfigMessageData_` | 200, 422 |
| GET | `/api/v1/llm-config/{service_name}` | `get_llm_config_legacy` | `llm_config.py` | service_name | - | `-` | `ApiEnvelope[LlmServiceConfigResponse]` | `ApiEnvelope_LlmServiceConfigResponse_` | 200, 422 |
| PUT | `/api/v1/llm-config/{service_name}` | `update_llm_config_legacy` | `llm_config.py` | service_name | - | `LlmServiceConfigUpdate` | `ApiEnvelope[LlmServiceConfigResponse]` | `ApiEnvelope_LlmServiceConfigResponse_` | 200, 422 |
| GET | `/api/v1/process/list` | `list_tasks` | `process.py` | - | status_filter?, limit?, project_key? | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/process/stats` | `get_task_stats` | `process.py` | - | - | `-` | `dict` | `object` | 200 |
| GET | `/api/v1/process/history` | `get_task_history` | `process.py` | - | limit?, status?, job_type?, project_key? | `-` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/process/{task_id}/cancel` | `cancel_task` | `process.py` | task_id | terminate? | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/process/{task_id}` | `get_task_info` | `process.py` | task_id | - | `-` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/process/{task_id}/retry` | `retry_task` | `process.py` | task_id | - | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/process/{task_id}/logs` | `get_task_logs` | `process.py` | task_id | tail? | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/topics` | `list_topics` | `topics.py` | - | enabled? | `-` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/topics` | `create_topic` | `topics.py` | - | - | `TopicPayload` | `dict` | `object` | 200, 422 |
| DELETE | `/api/v1/topics/{topic_id}` | `delete_topic` | `topics.py` | topic_id | - | `-` | `dict` | `object` | 200, 422 |
| PUT | `/api/v1/topics/{topic_id}` | `update_topic` | `topics.py` | topic_id | - | `TopicPayload` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/projects` | `list_projects` | `projects.py` | - | - | `-` | `dict` | `object` | 200 |
| POST | `/api/v1/projects` | `create_project` | `projects.py` | - | - | `CreateProjectPayload` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/projects/inject-initial` | `inject_initial_project` | `projects.py` | - | - | `InjectInitialProjectPayload` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/projects/auto-create` | `auto_create_project` | `projects.py` | - | - | `AutoCreateProjectPayload` | `dict` | `object` | 200, 422 |
| DELETE | `/api/v1/projects/{project_key}` | `delete_project` | `projects.py` | project_key | hard? | `-` | `dict` | `object` | 200, 422 |
| PATCH | `/api/v1/projects/{project_key}` | `update_project` | `projects.py` | project_key | - | `UpdateProjectPayload` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/projects/{project_key}/archive` | `archive_project` | `projects.py` | project_key | - | `-` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/projects/{project_key}/restore` | `restore_project` | `projects.py` | project_key | - | `-` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/projects/{project_key}/activate` | `activate_project` | `projects.py` | project_key | - | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/products` | `list_products` | `products.py` | - | enabled? | `-` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/products` | `create_product` | `products.py` | - | - | `ProductPayload` | `dict` | `object` | 200, 422 |
| DELETE | `/api/v1/products/{product_id}` | `delete_product` | `products.py` | product_id | - | `-` | `dict` | `object` | 200, 422 |
| PUT | `/api/v1/products/{product_id}` | `update_product` | `products.py` | product_id | - | `ProductPayload` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/governance/cleanup` | `cleanup` | `governance.py` | - | - | `CleanupPayload` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/governance/aggregator/sync` | `sync_aggregator` | `governance.py` | - | - | `AggregatorPayload` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/source_library/channels` | `list_channels` | `source_library.py` | - | scope?, project_key? | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/source_library/items` | `list_items` | `source_library.py` | - | scope?, project_key?, item_type?, include_system?, include_execution_plan? | `-` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/source_library/items` | `upsert_project_item` | `source_library.py` | - | project_key? | `SourceLibraryItemUpsertPayload` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/source_library/items/by_symbol` | `list_items_by_symbol_api` | `source_library.py` | - | scope?, project_key? | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/source_library/channels/grouped` | `list_channels_grouped_api` | `source_library.py` | - | scope?, project_key? | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/source_library/items/grouped` | `list_items_grouped_api` | `source_library.py` | - | scope?, project_key? | `-` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/source_library/external-projects/register` | `register_external_project` | `source_library.py` | - | project_key? | `ExternalProjectRegistrationPayload` | `dict` | `object` | 200, 422 |
| PUT | `/api/v1/source_library/items/{item_key}` | `update_project_item` | `source_library.py` | item_key | project_key? | `SourceLibraryItemUpsertPayload` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/source_library/items/{item_key}/refresh` | `refresh_item` | `source_library.py` | item_key | - | `RefreshItemPayload` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/source_library/handler_clusters/sync` | `sync_handler_clusters` | `source_library.py` | - | - | `SyncHandlerClustersPayload` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/source_library/sync_shared_from_files` | `sync_shared_from_files` | `source_library.py` | - | project_key? | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/project-customization/menu` | `get_menu_config` | `project_customization.py` | - | project_key? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/project-customization/workflows` | `list_workflows` | `project_customization.py` | - | project_key? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| DELETE | `/api/v1/project-customization/workflows/{workflow_name}/template` | `delete_workflow_template` | `project_customization.py` | workflow_name | project_key? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/project-customization/workflows/{workflow_name}/template` | `get_workflow_template` | `project_customization.py` | workflow_name | project_key? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/project-customization/workflows/{workflow_name}/template` | `upsert_workflow_template` | `project_customization.py` | workflow_name | - | `WorkflowTemplatePayload` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/project-customization/llm-mapping` | `get_llm_mapping` | `project_customization.py` | - | project_key? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/project-customization/graph-config` | `get_graph_config` | `project_customization.py` | - | project_key? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/project-customization/workflows/{workflow_name}/run` | `run_workflow` | `project_customization.py` | workflow_name | - | `WorkflowRunPayload` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/resource_pool/extract/from-documents` | `extract_from_documents_api` | `resource_pool.py` | - | - | `ExtractFromDocumentsPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| GET | `/api/v1/resource_pool/urls` | `list_urls_api` | `resource_pool.py` | - | project_key?, scope?, page?, page_size?, source?, domain? | `-` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| GET | `/api/v1/resource_pool/open-source-presets` | `list_open_source_presets_api` | `resource_pool.py` | - | - | `-` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200 |
| POST | `/api/v1/resource_pool/import/open-source-presets` | `import_open_source_presets_api` | `resource_pool.py` | - | - | `ImportOpenSourcePresetPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/resource_pool/capture/enable` | `capture_enable_api` | `resource_pool.py` | - | - | `CaptureEnablePayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/resource_pool/capture/from-tasks` | `capture_from_tasks_api` | `resource_pool.py` | - | - | `CaptureFromTasksPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| GET | `/api/v1/resource_pool/site-entries` | `list_site_entries_api` | `resource_pool.py` | - | project_key?, scope?, page?, page_size?, domain?, entry_type?, enabled? | `-` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/resource_pool/site-entries` | `upsert_site_entry_api` | `resource_pool.py` | - | - | `UpsertSiteEntryPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| GET | `/api/v1/resource_pool/site_entries` | `list_site_entries_api` | `resource_pool.py` | - | project_key?, scope?, page?, page_size?, domain?, entry_type?, enabled? | `-` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/resource_pool/site_entries` | `upsert_site_entry_api` | `resource_pool.py` | - | - | `UpsertSiteEntryPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| GET | `/api/v1/resource_pool/site-entries/grouped` | `group_site_entries_api` | `resource_pool.py` | - | project_key?, scope?, enabled? | `-` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| GET | `/api/v1/resource_pool/site_entries/grouped` | `group_site_entries_api` | `resource_pool.py` | - | project_key?, scope?, enabled? | `-` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/resource_pool/discover/search-contract` | `discover_search_contract_api` | `resource_pool.py` | - | - | `DiscoverSearchContractPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/resource_pool/discover/site-entries` | `discover_site_entries_api` | `resource_pool.py` | - | - | `DiscoverSiteEntriesPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/resource_pool/site_entries/simplify` | `simplify_site_entries_api` | `resource_pool.py` | - | - | `SimplifySiteEntriesPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/resource_pool/site_entries/recommend` | `recommend_site_entry_api` | `resource_pool.py` | - | - | `RecommendSiteEntryPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/resource_pool/site_entries/recommend-batch` | `recommend_site_entries_batch_api` | `resource_pool.py` | - | - | `BatchRecommendSiteEntriesPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/resource_pool/unified-search` | `unified_search_api` | `resource_pool.py` | - | - | `UnifiedSearchPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/resource_pool/source-library/collect` | `source_library_collect_api` | `resource_pool.py` | - | - | `SourceLibraryCollectPayload` | `ApiEnvelope[Any]` | `ApiEnvelope_Any_` | 200, 422 |
| POST | `/api/v1/crawler/projects/import` | `import_crawler_project_api` | `crawler.py` | - | - | `ImportCrawlerProjectPayload` | `ApiEnvelope[CrawlerProjectData]` | `ApiEnvelope_CrawlerProjectData_` | 200, 422 |
| GET | `/api/v1/crawler/projects` | `list_crawler_projects_api` | `crawler.py` | - | page?, page_size? | `-` | `ApiEnvelope[CrawlerProjectsData]` | `ApiEnvelope_CrawlerProjectsData_` | 200, 422 |
| GET | `/api/v1/crawler/projects/{project_key}` | `get_crawler_project_api` | `crawler.py` | project_key | - | `-` | `ApiEnvelope[CrawlerProjectData]` | `ApiEnvelope_CrawlerProjectData_` | 200, 422 |
| POST | `/api/v1/crawler/projects/{project_key}/deploy` | `deploy_crawler_project_api` | `crawler.py` | project_key | - | `DeployCrawlerProjectPayload` | `ApiEnvelope[CrawlerDeployActionData]` | `ApiEnvelope_CrawlerDeployActionData_` | 200, 422 |
| POST | `/api/v1/crawler/projects/{project_key}/rollback` | `rollback_crawler_project_api` | `crawler.py` | project_key | - | `RollbackCrawlerProjectPayload` | `ApiEnvelope[CrawlerDeployActionData]` | `ApiEnvelope_CrawlerDeployActionData_` | 200, 422 |
| GET | `/api/v1/crawler/deploy-runs/{run_id}` | `get_crawler_deploy_run_api` | `crawler.py` | run_id | - | `-` | `ApiEnvelope[CrawlerDeployRunData]` | `ApiEnvelope_CrawlerDeployRunData_` | 200, 422 |
| GET | `/api/v1/crawler/deploy-runs` | `list_crawler_deploy_runs_api` | `crawler.py` | - | limit? | `-` | `ApiEnvelope[CrawlerDeployRunsData]` | `ApiEnvelope_CrawlerDeployRunsData_` | 200, 422 |
| GET | `/api/v1/crawler/projects/{project_key}/deploy-runs` | `list_crawler_project_deploy_runs_api` | `crawler.py` | project_key | limit? | `-` | `ApiEnvelope[CrawlerDeployRunsData]` | `ApiEnvelope_CrawlerDeployRunsData_` | 200, 422 |
| GET | `/api/v1/keywords/stats` | `get_keyword_memory_stats` | `keywords.py` | - | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200 |
| GET | `/api/v1/keywords/history` | `get_keyword_history` | `keywords.py` | - | limit?, q? | `-` | `ApiEnvelope[KeywordHistoryData]` | `ApiEnvelope_KeywordHistoryData_` | 200, 422 |
| GET | `/api/v1/keywords/priors` | `get_keyword_priors` | `keywords.py` | - | limit?, enabled_only? | `-` | `ApiEnvelope[KeywordPriorsData]` | `ApiEnvelope_KeywordPriorsData_` | 200, 422 |
| POST | `/api/v1/keywords/priors/upsert` | `post_keyword_prior_upsert` | `keywords.py` | - | - | `KeywordPriorUpsertPayload` | `ApiEnvelope[KeywordPriorUpsertData]` | `ApiEnvelope_KeywordPriorUpsertData_` | 200, 422 |
| GET | `/api/v1/keywords/vectorization/candidates` | `get_vectorization_candidates` | `keywords.py` | - | limit? | `-` | `ApiEnvelope[KeywordVectorizationCandidatesData]` | `ApiEnvelope_KeywordVectorizationCandidatesData_` | 200, 422 |
| POST | `/api/v1/llm-report/generate` | `generate_llm_report` | `llm_report.py` | - | - | `GenerateReportRequest` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/workflow-graph/compile` | `compile_workflow_graph` | `workflow_graph.py` | - | - | `object` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/workflow-graph/run` | `run_workflow_graph` | `workflow_graph.py` | - | - | `object` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/workflow-graph/runs/{run_id}` | `get_workflow_graph_run` | `workflow_graph.py` | run_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/workflow-graph/runs/{run_id}/events` | `get_workflow_graph_run_events` | `workflow_graph.py` | run_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/workflow-graph/runs/{run_id}/agent-session` | `get_workflow_graph_run_agent_session` | `workflow_graph.py` | run_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/workflow-graph/compiled/{graph_id}` | `get_workflow_graph_compiled` | `workflow_graph.py` | graph_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/workflow-graph/runs/{run_id}/replay` | `replay_workflow_graph_run` | `workflow_graph.py` | run_id | replay_mode? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/workflow-graph/templates` | `list_workflow_graph_templates` | `workflow_graph.py` | - | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200 |
| POST | `/api/v1/workflow-graph/templates` | `create_workflow_graph_template` | `workflow_graph.py` | - | - | `object` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| DELETE | `/api/v1/workflow-graph/templates/{template_id}` | `delete_workflow_graph_template` | `workflow_graph.py` | template_id | - | `anyOf[object,null] (optional)` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/workflow-graph/templates/{template_id}` | `get_workflow_graph_template` | `workflow_graph.py` | template_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| PATCH | `/api/v1/workflow-graph/templates/{template_id}` | `patch_workflow_graph_template` | `workflow_graph.py` | template_id | - | `object` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/workflow-graph/templates/{template_id}/versions` | `list_workflow_graph_template_versions` | `workflow_graph.py` | template_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/workflow-graph/templates/{template_id}/versions` | `create_workflow_graph_template_version` | `workflow_graph.py` | template_id | - | `object` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/workflow-graph/templates/{template_id}/versions/{version_id}` | `get_workflow_graph_template_version` | `workflow_graph.py` | template_id, version_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/workflow-graph/templates/{template_id}/versions/{version_id}/activate` | `activate_workflow_graph_template_version` | `workflow_graph.py` | template_id, version_id | - | `anyOf[object,null] (optional)` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/workflow-graph/curated/{graph_id}` | `get_workflow_graph_curated_state` | `workflow_graph.py` | graph_id | - | `-` | `ApiEnvelope[WorkflowGraphCuratedStateData]` | `ApiEnvelope_WorkflowGraphCuratedStateData_` | 200, 422 |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/draft` | `save_workflow_graph_curated_draft` | `workflow_graph.py` | graph_id | - | `object` | `ApiEnvelope[WorkflowGraphCuratedStateData]` | `ApiEnvelope_WorkflowGraphCuratedStateData_` | 200, 422 |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/submit` | `submit_workflow_graph_curated_draft` | `workflow_graph.py` | graph_id | - | `anyOf[object,null] (optional)` | `ApiEnvelope[WorkflowGraphCuratedStateData]` | `ApiEnvelope_WorkflowGraphCuratedStateData_` | 200, 422 |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/sync` | `sync_workflow_graph_curated_state` | `workflow_graph.py` | graph_id | - | `anyOf[object,null] (optional)` | `ApiEnvelope[WorkflowGraphCuratedStateData]` | `ApiEnvelope_WorkflowGraphCuratedStateData_` | 200, 422 |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/rollback` | `rollback_workflow_graph_curated_state` | `workflow_graph.py` | graph_id | - | `object` | `ApiEnvelope[WorkflowGraphCuratedStateData]` | `ApiEnvelope_WorkflowGraphCuratedStateData_` | 200, 422 |
| GET | `/api/v1/workflow-graph/curated/{graph_id}/audit` | `list_workflow_graph_curated_audits` | `workflow_graph.py` | graph_id | limit? | `-` | `ApiEnvelope[WorkflowGraphAuditListData]` | `ApiEnvelope_WorkflowGraphAuditListData_` | 200, 422 |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/evidence-pack` | `build_workflow_graph_evidence_pack` | `workflow_graph.py` | graph_id | - | `anyOf[object,null] (optional)` | `ApiEnvelope[WorkflowGraphEvidencePackData]` | `ApiEnvelope_WorkflowGraphEvidencePackData_` | 200, 422 |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/handoff/reporting` | `build_workflow_graph_reporting_handoff` | `workflow_graph.py` | graph_id | - | `object` | `ApiEnvelope[WorkflowGraphHandoffData]` | `ApiEnvelope_WorkflowGraphHandoffData_` | 200, 422 |
| POST | `/api/v1/workflow-graph/curated/{graph_id}/handoff/writing` | `build_workflow_graph_writing_handoff` | `workflow_graph.py` | graph_id | - | `object` | `ApiEnvelope[WorkflowGraphHandoffData]` | `ApiEnvelope_WorkflowGraphHandoffData_` | 200, 422 |
| GET | `/api/v1/workflow-graph/runs/{run_id}/handoff` | `list_workflow_graph_run_handoffs` | `workflow_graph.py` | run_id | handoff_mode? | `-` | `ApiEnvelope[WorkflowGraphHandoffListData]` | `ApiEnvelope_WorkflowGraphHandoffListData_` | 200, 422 |
| GET | `/api/v1/workflow-graph/runs/{run_id}/handoff/{handoff_id}/replay` | `replay_workflow_graph_handoff` | `workflow_graph.py` | run_id, handoff_id | - | `-` | `ApiEnvelope[WorkflowGraphHandoffReplayData]` | `ApiEnvelope_WorkflowGraphHandoffReplayData_` | 200, 422 |
| GET | `/api/v1/workflow-graph/observability/failure-reasons` | `get_workflow_graph_failure_reasons` | `workflow_graph.py` | - | limit? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/stats/prompt-time-density` | `get_prompt_time_density` | `stats.py` | - | start?, end?, time_window?, bucket?, source_domains?, noun_group_ids?, prompt_group_ids?, normalize? | `-` | `ApiEnvelope[PromptTimeDensityData]` | `ApiEnvelope_PromptTimeDensityData_` | 200, 422 |
| GET | `/api/v1/stats/prompt-time-density/cloud` | `get_prompt_time_density_cloud` | `stats.py` | - | keyword, start?, end?, time_window?, bucket?, source_domains?, noun_group_ids?, prompt_group_ids?, smoothing?, peak_percentile?, uncertainty?, normalize? | `-` | `ApiEnvelope[PromptTimeDensityCloudData]` | `ApiEnvelope_PromptTimeDensityCloudData_` | 200, 422 |
| GET | `/api/v1/stats/prompt-time-density/priority` | `get_prompt_time_density_priority` | `stats.py` | - | end?, candidate_windows?, source_domains?, noun_group_ids?, prompt_group_ids?, prefer_low_density?, exclude_high_dup?, min_overlap?, target_overlap?, eta?, delta_max?, tau?, avoid_peak? | `-` | `ApiEnvelope[PromptTimeDensityPriorityData]` | `ApiEnvelope_PromptTimeDensityPriorityData_` | 200, 422 |
| GET | `/api/v1/stats/prompt-time-density/select-windows` | `select_prompt_time_windows` | `stats.py` | - | end?, candidate_windows?, source_domains?, noun_group_ids?, prompt_group_ids?, max_windows?, prefer_low_density?, exclude_high_dup?, min_overlap?, target_overlap?, eta?, delta_max?, tau?, avoid_peak? | `-` | `ApiEnvelope[PromptTimeDensityWindowSelectionData]` | `ApiEnvelope_PromptTimeDensityWindowSelectionData_` | 200, 422 |
| GET | `/api/v1/writing/documents` | `list_writing_documents` | `writing.py` | - | project_key?, limit? | `-` | `ApiEnvelope[WritingDocumentListData]` | `ApiEnvelope_WritingDocumentListData_` | 200, 422 |
| POST | `/api/v1/writing/documents` | `create_writing_document` | `writing.py` | - | - | `WritingDocumentCreateRequest` | `ApiEnvelope[WritingDocumentData]` | `ApiEnvelope_WritingDocumentData_` | 200, 422 |
| DELETE | `/api/v1/writing/documents/{doc_id}` | `delete_writing_document` | `writing.py` | doc_id | project_key? | `-` | `ApiEnvelope[WritingDocumentDeleteData]` | `ApiEnvelope_WritingDocumentDeleteData_` | 200, 422 |
| GET | `/api/v1/writing/documents/{doc_id}` | `get_writing_document` | `writing.py` | doc_id | project_key? | `-` | `ApiEnvelope[WritingDocumentData]` | `ApiEnvelope_WritingDocumentData_` | 200, 422 |
| PATCH | `/api/v1/writing/documents/{doc_id}` | `patch_writing_document` | `writing.py` | doc_id | - | `WritingDocumentPatchRequest` | `ApiEnvelope[WritingDocumentData]` | `ApiEnvelope_WritingDocumentData_` | 200, 422 |
| POST | `/api/v1/writing/documents/{doc_id}/draft` | `autosave_writing_document_draft` | `writing.py` | doc_id | - | `WritingDraftAutosaveRequest` | `ApiEnvelope[WritingDocumentDraftData]` | `ApiEnvelope_WritingDocumentDraftData_` | 200, 422 |
| GET | `/api/v1/writing/documents/{doc_id}/citations` | `get_writing_document_citations` | `writing.py` | doc_id | project_key? | `-` | `ApiEnvelope[WritingCitationListData]` | `ApiEnvelope_WritingCitationListData_` | 200, 422 |
| POST | `/api/v1/writing/documents/{doc_id}/citations` | `post_writing_document_citations` | `writing.py` | doc_id | - | `WritingCitationUpsertRequest` | `ApiEnvelope[WritingCitationListData]` | `ApiEnvelope_WritingCitationListData_` | 200, 422 |
| GET | `/api/v1/writing/templates` | `get_writing_templates` | `writing.py` | - | - | `-` | `ApiEnvelope[WritingTemplateListData]` | `ApiEnvelope_WritingTemplateListData_` | 200 |
| POST | `/api/v1/writing/templates/validate` | `post_writing_template_validate` | `writing.py` | - | - | `TemplateValidateRequest` | `ApiEnvelope[TemplateValidateResponse]` | `ApiEnvelope_TemplateValidateResponse_` | 200, 422 |
| POST | `/api/v1/writing/keyword-cards` | `post_keyword_cards` | `writing.py` | - | - | `KeywordCardRequest` | `ApiEnvelope[KeywordCardListResponse]` | `ApiEnvelope_KeywordCardListResponse_` | 200, 422 |
| POST | `/api/v1/writing/keyword-cards/preview` | `post_keyword_card_preview` | `writing.py` | - | - | `KeywordCardPreviewRequest` | `ApiEnvelope[KeywordCardPreviewResponse]` | `ApiEnvelope_KeywordCardPreviewResponse_` | 200, 422 |
| GET | `/api/v1/writing/cards/{card_id}` | `get_writing_card_detail` | `writing.py` | card_id | project_key?, include_provenance?, max_provenance_items? | `-` | `ApiEnvelope[KeywordCardDetailResponse]` | `ApiEnvelope_KeywordCardDetailResponse_` | 200, 422 |
| GET | `/api/v1/writing/suggest` | `get_writing_suggest` | `writing.py` | - | query, mode?, project_key?, limit? | `-` | `ApiEnvelope[SuggestResponse]` | `ApiEnvelope_SuggestResponse_` | 200, 422 |
| POST | `/api/v1/writing/llm-actions` | `post_writing_llm_action` | `writing.py` | - | - | `LlmActionRequest` | `ApiEnvelope[LlmActionResponse]` | `ApiEnvelope_LlmActionResponse_` | 200, 422 |
| GET | `/api/v1/writing/llm-actions/history` | `get_writing_llm_action_history` | `writing.py` | - | project_key?, limit? | `-` | `ApiEnvelope[LlmActionHistoryListData]` | `ApiEnvelope_LlmActionHistoryListData_` | 200, 422 |
| GET | `/api/v1/writing/llm-actions/{job_id}` | `get_writing_llm_action_detail` | `writing.py` | job_id | project_key? | `-` | `ApiEnvelope[LlmActionHistoryItem]` | `ApiEnvelope_LlmActionHistoryItem_` | 200, 422 |
| POST | `/api/v1/writing/export/markdown` | `post_writing_export_markdown` | `writing.py` | - | - | `WritingExportMarkdownRequest` | `none` | `non-json` | 200, 422 |
| POST | `/api/v1/agent-batch/jobs` | `submit_agent_batch_job` | `agent_batch.py` | - | - | `AgentBatchSubmitRequest` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/agent-batch/jobs/{job_id}` | `get_agent_batch_job` | `agent_batch.py` | job_id | - | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/agent-batch/jobs/{job_id}/items` | `list_agent_batch_items` | `agent_batch.py` | job_id | - | `-` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/agent-batch/jobs/{job_id}/retry` | `retry_agent_batch_job` | `agent_batch.py` | job_id | - | `AgentBatchRetryRequest` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/agent-batch/jobs/{job_id}/events` | `get_agent_batch_events` | `agent_batch.py` | job_id | - | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/agent-batch/metrics/search-policy` | `get_agent_batch_search_policy_metrics` | `agent_batch.py` | - | - | `-` | `dict` | `object` | 200 |
| GET | `/api/v1/agent-batch/metrics/search-policy/benchmark-pack` | `get_agent_batch_search_policy_benchmark_pack` | `agent_batch.py` | - | - | `-` | `dict` | `object` | 200 |
| GET | `/api/v1/agent-batch/metrics/search-policy/gate` | `get_agent_batch_search_policy_gate` | `agent_batch.py` | - | - | `-` | `dict` | `object` | 200 |
| GET | `/api/v1/agent-batch/jobs/{job_id}/workflow-handoffs` | `list_agent_batch_job_workflow_handoffs` | `agent_batch.py` | job_id | handoff_mode? | `-` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/agent-batch/observability/failure-reasons` | `get_agent_batch_failure_reasons` | `agent_batch.py` | - | limit? | `-` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/agent-batch/approvals/request` | `create_agent_batch_approval` | `agent_batch.py` | - | - | `AgentBatchApprovalRequest` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/agent-batch/approvals/{approval_token}/resolve` | `resolve_agent_batch_approval` | `agent_batch.py` | approval_token | - | `AgentBatchApprovalResolveRequest` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/agent-batch/rule-sets/validate` | `validate_agent_batch_rule_set` | `agent_batch.py` | - | - | `RuleSetValidateRequest` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/agent-batch/nl-command` | `run_agent_batch_nl_command` | `agent_batch.py` | - | - | `AgentBatchNlCommandRequest` | `dict` | `object` | 200, 422 |
| POST | `/api/v1/agent-batch/nl-command/direct` | `run_agent_batch_nl_command_direct` | `agent_batch.py` | - | - | `AgentBatchNlCommandRequest` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/agent-batch/executor/health` | `get_agent_batch_executor_health` | `agent_batch.py` | - | - | `-` | `dict` | `object` | 200 |
| GET | `/api/v1/agent-chat/capabilities` | `list_agent_chat_capabilities` | `agent_chat.py` | - | project_key? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/agent-chat/turn` | `run_agent_chat_turn` | `agent_chat.py` | - | - | `AgentChatTurnRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/agent-chat/turn/stream` | `stream_agent_chat_turn` | `agent_chat.py` | - | - | `AgentChatTurnRequest` | `none` | `non-json` | 200, 422 |
| POST | `/api/v1/agent-chat/approvals/{approval_id}/continue` | `continue_agent_chat_approval` | `agent_chat.py` | approval_id | - | `AgentChatApprovalContinueRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/agent-sessions` | `list_agent_sessions` | `agent_sessions.py` | - | limit? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/agent-sessions` | `create_agent_session` | `agent_sessions.py` | - | - | `AgentSessionCreateRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/agent-sessions/{session_id}` | `get_agent_session` | `agent_sessions.py` | session_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/agent-sessions/{session_id}/tasks` | `get_agent_session_tasks` | `agent_sessions.py` | session_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/agent-sessions/{session_id}/events` | `get_agent_session_events` | `agent_sessions.py` | session_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/agent-sessions/{session_id}/artifacts` | `get_agent_session_artifacts` | `agent_sessions.py` | session_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/agent-sessions/{session_id}/messages` | `get_agent_session_messages` | `agent_sessions.py` | session_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/agent-sessions/{session_id}/messages` | `create_agent_session_message` | `agent_sessions.py` | session_id | - | `AgentMessageCreateRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/agent-approvals` | `list_agent_approvals` | `agent_sessions.py` | - | session_id? | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/agent-sessions/{session_id}/stream` | `stream_agent_session_events` | `agent_sessions.py` | session_id | since_seq?, poll_seconds?, max_seconds? | `-` | `none` | `non-json` | 200, 422 |
| POST | `/api/v1/agent-sessions/{session_id}/actions/retry-task` | `retry_agent_session_task` | `agent_sessions.py` | session_id | - | `AgentTaskRetryRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/agent-sessions/{session_id}/actions/cancel` | `cancel_agent_session` | `agent_sessions.py` | session_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/agent-sessions/{session_id}/actions/reclaim-expired` | `reclaim_agent_session_expired_tasks` | `agent_sessions.py` | session_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/agent-sessions/{session_id}/actions/coordinator-pass` | `run_agent_session_coordinator_pass` | `agent_sessions.py` | session_id | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/agent-sessions/{session_id}/actions/request-approval` | `request_agent_session_approval` | `agent_sessions.py` | session_id | - | `AgentApprovalRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| POST | `/api/v1/agent-approvals/{approval_id}/resolve` | `resolve_agent_approval` | `agent_sessions.py` | approval_id | - | `AgentApprovalResolveRequest` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200, 422 |
| GET | `/api/v1/skills` | `list_skills` | `skills.py` | - | - | `-` | `dict` | `object` | 200 |
| POST | `/api/v1/skills/invoke` | `invoke_skill_api` | `skills.py` | - | - | `SkillInvokeRequest` | `dict` | `object` | 200, 422 |
| GET | `/api/v1/codex-auth/login` | `codex_auth_login` | `codex_auth.py` | - | next_url?, force_oauth? | `-` | `none` | `missing` | 302, 400, 422 |
| GET | `/api/v1/codex-auth/callback` | `codex_auth_callback` | `codex_auth.py` | - | code?, state?, error? | `-` | `none` | `missing` | 302, 422 |
| GET | `/api/v1/codex-auth/status` | `codex_auth_status` | `codex_auth.py` | - | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200 |
| POST | `/api/v1/codex-auth/logout` | `codex_auth_logout` | `codex_auth.py` | - | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200 |
| POST | `/api/v1/codex-auth/cli/bootstrap` | `codex_cli_bootstrap` | `codex_auth.py` | - | - | `-` | `ApiEnvelope[dict[str, Any]]` | `ApiEnvelope_dict_str__Any__` | 200 |
| GET | `/api/v1/clue-chains` | `list_clue_chains` | `clue_chains.py` | - | project_key?, graph_id?, status?, limit? | `-` | `ApiEnvelope[ClueChainListData]` | `ApiEnvelope_ClueChainListData_` | 200, 422 |
| POST | `/api/v1/clue-chains` | `create_clue_chain` | `clue_chains.py` | - | - | `ClueChainCreateRequest` | `ApiEnvelope[ClueChainDetailData]` | `ApiEnvelope_ClueChainDetailData_` | 200, 422 |
| GET | `/api/v1/clue-chains/{chain_id}` | `get_clue_chain` | `clue_chains.py` | chain_id | - | `-` | `ApiEnvelope[ClueChainDetailData]` | `ApiEnvelope_ClueChainDetailData_` | 200, 422 |
| POST | `/api/v1/clue-chains/{chain_id}/expand` | `expand_clue_chain` | `clue_chains.py` | chain_id | - | `ClueChainExpandRequest` | `ApiEnvelope[ClueChainExpansionData]` | `ApiEnvelope_ClueChainExpansionData_` | 200, 422 |
| POST | `/api/v1/clue-chains/{chain_id}/candidates/{candidate_id}/decision` | `decide_clue_chain_candidate` | `clue_chains.py` | chain_id, candidate_id | - | `ClueChainDecisionRequest` | `ApiEnvelope[ClueChainDecisionResponseData]` | `ApiEnvelope_ClueChainDecisionResponseData_` | 200, 422 |
| POST | `/api/v1/clue-chains/{chain_id}/close` | `close_clue_chain` | `clue_chains.py` | chain_id | - | `ClueChainCloseRequest` | `ApiEnvelope[ClueChainCloseData]` | `ApiEnvelope_ClueChainCloseData_` | 200, 422 |
