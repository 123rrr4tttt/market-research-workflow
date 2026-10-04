from __future__ import annotations

from typing import get_args

import pytest

from mrw_functorial_kit.core.provider_port_failures import (
    CollectRuntimeFailureCode,
    CrawlerRegistryContractFailureCode,
    CrawlerRuntimeFailureCode,
    IndexerPolicyFailureCode,
    IngestGoogleNewsFailureCode,
    IngestLongCycleFailureCode,
    IngestOperationFailureCode,
    IngestPolicyFailureCode,
    IngestRedditFailureCode,
    JobHistoryFailureCode,
    ResourcePoolContractFailureCode,
    ResourcePoolHttpFetchFailureCode,
    collect_runtime_failures,
    crawler_registry_contract_failures,
    crawler_runtime_failures,
    indexer_policy_failures,
    ingest_google_news_failures,
    ingest_long_cycle_failures,
    ingest_operation_failures,
    ingest_policy_failures,
    ingest_reddit_failures,
    job_history_failures,
    resource_pool_contract_failures,
    resource_pool_http_fetch_failures,
)

_EXPECTED_CODES: dict[str, tuple[str, ...]] = {
    "collect.runtime.failure": (
        "skill_id_required",
        "collect_adapter_contract_invalid",
        "compat_projector_contract_invalid",
        "collect_channel_unsupported",
        "auto_batch_execution_failed",
        "product_mode_unsupported",
        "successor_effect_gateway_invalid",
    ),
    "ingest.policy.failure": (
        "policy_adapter_not_configured",
        "policy_provider_iteration_failed",
        "policy_persistence_failed",
        "policy_indexing_failed",
    ),
    "ingest.reddit.failure": (
        "reddit_adapter_not_configured",
        "reddit_collection_failed",
    ),
    "ingest.google_news.failure": (
        "google_news_adapter_not_configured",
        "google_news_collection_failed",
    ),
    "resource_pool.http_fetch.failure": (
        "port_not_configured",
        "transport",
        "http_status",
        "response_invalid",
    ),
    "crawler.runtime.failure": (
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
    ),
    "crawler.registry.contract_failure": ("provider_key_required",),
    "ingest.operation.failure": (
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
    ),
    "ingest.long_cycle.failure": (
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
    ),
    "resource_pool.contract.failure": (
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
    ),
    "indexer.policy.failure": (
        "vector_contract_missing_fields",
        "vector_contract_not_vectorizable",
        "embedding_provider_not_configured",
        "index_execution_failed",
        "embedding_dimension_invalid",
    ),
    "job.history.failure": ("history_read_failed",),
}


def test_FAILURE_PRESERVED__w03_literal_aliases_match_exact_families() -> None:
    aliases: dict[str, tuple[str, ...]] = {
        "collect.runtime.failure": get_args(CollectRuntimeFailureCode),
        "ingest.policy.failure": get_args(IngestPolicyFailureCode),
        "ingest.reddit.failure": get_args(IngestRedditFailureCode),
        "ingest.google_news.failure": get_args(IngestGoogleNewsFailureCode),
        "resource_pool.http_fetch.failure": get_args(
            ResourcePoolHttpFetchFailureCode
        ),
        "crawler.runtime.failure": get_args(CrawlerRuntimeFailureCode),
        "crawler.registry.contract_failure": get_args(CrawlerRegistryContractFailureCode),
        "ingest.operation.failure": get_args(IngestOperationFailureCode),
        "ingest.long_cycle.failure": get_args(IngestLongCycleFailureCode),
        "resource_pool.contract.failure": get_args(ResourcePoolContractFailureCode),
        "indexer.policy.failure": get_args(IndexerPolicyFailureCode),
        "job.history.failure": get_args(JobHistoryFailureCode),
    }

    assert set(aliases) == set(_EXPECTED_CODES)
    assert aliases == _EXPECTED_CODES


def test_FAILURE_PRESERVED__w03_preexisting_codes_are_not_removed() -> None:
    assert collect_runtime_failures.codes[:3] == (
        "skill_id_required",
        "collect_adapter_contract_invalid",
        "compat_projector_contract_invalid",
    )
    assert ingest_policy_failures.codes[:2] == (
        "policy_adapter_not_configured",
        "policy_provider_iteration_failed",
    )
    assert ingest_reddit_failures.codes[:1] == ("reddit_adapter_not_configured",)
    assert ingest_google_news_failures.codes[:1] == (
        "google_news_adapter_not_configured",
    )
    assert resource_pool_http_fetch_failures.codes[:3] == (
        "port_not_configured",
        "transport",
        "http_status",
    )


def test_FAILURE_PRESERVED__w03_members_are_closed_and_unknown_codes_rejected() -> (
    None
):
    families = {
        collect_runtime_failures.name: collect_runtime_failures,
        ingest_policy_failures.name: ingest_policy_failures,
        ingest_reddit_failures.name: ingest_reddit_failures,
        ingest_google_news_failures.name: ingest_google_news_failures,
        resource_pool_http_fetch_failures.name: resource_pool_http_fetch_failures,
        crawler_runtime_failures.name: crawler_runtime_failures,
        crawler_registry_contract_failures.name: crawler_registry_contract_failures,
        ingest_operation_failures.name: ingest_operation_failures,
        ingest_long_cycle_failures.name: ingest_long_cycle_failures,
        resource_pool_contract_failures.name: resource_pool_contract_failures,
        indexer_policy_failures.name: indexer_policy_failures,
        job_history_failures.name: job_history_failures,
    }

    assert set(families) == set(_EXPECTED_CODES)
    for name, family in families.items():
        assert family.codes == _EXPECTED_CODES[name]
        assert len(set(family.codes)) == len(family.codes)
        for code in family.codes:
            failure = family.fail(code, f"closed member {code}")
            assert failure.family == name
            assert failure.code == code
            assert family.matches(failure)

        with pytest.raises(ValueError, match="unknown code"):
            family.fail("unregistered", "outside the closed family")
