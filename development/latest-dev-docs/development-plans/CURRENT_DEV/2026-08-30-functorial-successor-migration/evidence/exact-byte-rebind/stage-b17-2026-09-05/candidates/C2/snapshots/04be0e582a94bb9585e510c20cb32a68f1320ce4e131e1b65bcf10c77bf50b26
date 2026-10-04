"""Closed failure projections for provider and crawler port boundaries."""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family


IngestMarketFailureCode = Literal[
    "market_adapter_not_configured",
    "market_provider_iteration_failed",
    "market_persistence_failed",
]
IngestPolicyFailureCode = Literal[
    "policy_adapter_not_configured",
    "policy_provider_iteration_failed",
    "policy_persistence_failed",
    "policy_indexing_failed",
]
IngestRedditFailureCode = Literal[
    "reddit_adapter_not_configured",
    "reddit_collection_failed",
]
IngestGoogleNewsFailureCode = Literal[
    "google_news_adapter_not_configured",
    "google_news_collection_failed",
]
ResourcePoolHttpFetchFailureCode = Literal[
    "port_not_configured",
    "transport",
    "http_status",
    "response_invalid",
]
ResourcePoolOfficialAccessFailureCode = Literal[
    "official_access_port_not_configured",
]
CollectRuntimeFailureCode = Literal[
    "skill_id_required",
    "collect_adapter_contract_invalid",
    "compat_projector_contract_invalid",
    "collect_channel_unsupported",
    "auto_batch_execution_failed",
]
SourceLibraryCrawlerProviderResolutionFailureCode = Literal[
    "resolver_not_configured",
    "provider_unavailable",
    "provider_unsupported",
]
CrawlerRegistryContractFailureCode = Literal["provider_key_required"]
CrawlerRuntimeFailureCode = Literal[
    "provider_not_registered",
    "provider_poll_unsupported",
    "poll_project_required",
    "scrapyd_base_url_required",
    "scrapyd_compose_file_missing",
    "scrapyd_compose_unavailable",
    "scrapyd_module_unavailable",
    "scrapyd_unavailable",
    "scrapyd_lazy_start_failed",
    "scrapyd_readiness_timeout",
    "scrapyd_transport",
    "scrapyd_http_status",
    "scrapyd_response_invalid",
    "bootstrap_project_name_invalid",
    "bootstrap_build_failed",
    "bootstrap_artifact_missing",
    "bootstrap_project_required",
    "bootstrap_deploy_failed",
]
IngestOperationFailureCode = Literal[
    "canary_readback_not_object",
    "commodity_collection_failed",
    "ecom_collection_failed",
    "official_news_collection_failed",
    "market_web_collection_failed",
    "raw_import_failed",
    "california_report_collection_failed",
    "weekly_report_collection_failed",
    "monthly_report_collection_failed",
    "social_sentiment_collection_failed",
    "policy_regulation_collection_failed",
    "url_pool_collection_failed",
]
IngestLongCycleFailureCode = Literal[
    "lifecycle_transition_invalid",
    "window_bounds_invalid",
    "candidate_window_invalid",
    "required_ref_missing",
    "task_state_invalid",
    "jsonl_invalid",
    "lifecycle_event_invalid",
    "live_enqueue_required",
    "queue_empty",
    "task_record_missing",
    "repository_type_invalid",
]
ResourcePoolContractFailureCode = Literal[
    "preset_pack_unknown",
    "query_terms_required",
    "search_template_invalid",
    "entry_domain_required",
    "scope_invalid",
    "site_url_required",
    "project_key_required",
    "item_key_required",
    "source_item_not_found",
    "item_payload_key_required",
    "site_entries_required",
]
IndexerPolicyFailureCode = Literal[
    "vector_contract_missing_fields",
    "vector_contract_not_vectorizable",
    "embedding_provider_not_configured",
    "index_execution_failed",
    "embedding_dimension_invalid",
]
JobHistoryFailureCode = Literal["history_read_failed"]

ingest_market_failures = define_failure_family(
    "ingest.market.failure",
    get_args(IngestMarketFailureCode),
)
ingest_policy_failures = define_failure_family(
    "ingest.policy.failure",
    get_args(IngestPolicyFailureCode),
)
ingest_reddit_failures = define_failure_family(
    "ingest.reddit.failure",
    get_args(IngestRedditFailureCode),
)
ingest_google_news_failures = define_failure_family(
    "ingest.google_news.failure",
    get_args(IngestGoogleNewsFailureCode),
)
resource_pool_http_fetch_failures = define_failure_family(
    "resource_pool.http_fetch.failure",
    get_args(ResourcePoolHttpFetchFailureCode),
)
resource_pool_official_access_failures = define_failure_family(
    "resource_pool.official_access.failure",
    get_args(ResourcePoolOfficialAccessFailureCode),
)
collect_runtime_failures = define_failure_family(
    "collect.runtime.failure",
    get_args(CollectRuntimeFailureCode),
)
source_library_crawler_provider_resolution_failures = define_failure_family(
    "source_library.crawler_provider_resolution.failure",
    get_args(SourceLibraryCrawlerProviderResolutionFailureCode),
)
crawler_registry_contract_failures = define_failure_family(
    "crawler.registry.contract_failure",
    get_args(CrawlerRegistryContractFailureCode),
)
crawler_runtime_failures = define_failure_family(
    "crawler.runtime.failure",
    get_args(CrawlerRuntimeFailureCode),
)
ingest_operation_failures = define_failure_family(
    "ingest.operation.failure",
    get_args(IngestOperationFailureCode),
)
ingest_long_cycle_failures = define_failure_family(
    "ingest.long_cycle.failure",
    get_args(IngestLongCycleFailureCode),
)
resource_pool_contract_failures = define_failure_family(
    "resource_pool.contract.failure",
    get_args(ResourcePoolContractFailureCode),
)
indexer_policy_failures = define_failure_family(
    "indexer.policy.failure",
    get_args(IndexerPolicyFailureCode),
)
job_history_failures = define_failure_family(
    "job.history.failure",
    get_args(JobHistoryFailureCode),
)


__all__ = [
    "collect_runtime_failures",
    "crawler_registry_contract_failures",
    "crawler_runtime_failures",
    "ingest_google_news_failures",
    "ingest_long_cycle_failures",
    "ingest_market_failures",
    "ingest_operation_failures",
    "ingest_policy_failures",
    "ingest_reddit_failures",
    "indexer_policy_failures",
    "job_history_failures",
    "resource_pool_http_fetch_failures",
    "resource_pool_contract_failures",
    "resource_pool_official_access_failures",
    "source_library_crawler_provider_resolution_failures",
]
