from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.resource_pool.search_contract_discovery import (
    QueryContractResolution,
    QueryDiscoveryBudget,
)
from app.services.resource_pool.search_template_service import (
    SearchTemplateExecutionResult,
    SearchTemplateRawCandidate,
)
from app.services.resource_pool.unified_search import unified_search_by_item_payload
from app.services.source_library import resolver as source_library_resolver
from app.services.source_library.terminal_output import to_terminal_output_dto


pytestmark = pytest.mark.unit


def _decision(url: str = "https://example.com/article-1") -> SimpleNamespace:
    return SimpleNamespace(
        url=url,
        matched_by="title",
        route_kind="article",
        candidate_quality="high",
        usable_for_search=True,
        score=0.95,
    )


def _execution(
    url: str = "https://example.com/article-1",
    *,
    errors: list[dict[str, object]] | None = None,
) -> SearchTemplateExecutionResult:
    return SearchTemplateExecutionResult(
        template="https://example.com/feed.xml",
        search_urls=["https://example.com/feed.xml"],
        pages_scanned=1,
        raw_candidates=[SearchTemplateRawCandidate(url=url)],
        selected_candidates=[_decision(url)],
        used_term_fallback=False,
        errors=errors or [],
        diagnostics={"search_service": "feed_native"},
    )


def _verified_resolution(entry_type: str = "rss") -> QueryContractResolution:
    template = "https://example.com/feed.xml"
    return QueryContractResolution(
        status="verified",
        entry={
            "site_url": template,
            "domain": "example.com",
            "entry_type": entry_type,
            "template": template if entry_type == "search_template" else None,
            "capabilities": {
                "supports_query_terms": True,
                "keyword_mode": "search" if entry_type == "search_template" else "filter",
            },
            "extra": {
                "query_contract_resolution": {
                    "contract_version": "resource_pool.query_contract_resolution.v1",
                    "transient": True,
                    "origin": "evidence_form",
                    "evidence_url": "https://example.com/",
                    "reason": "homepage evidence",
                    "selected_candidates": ["https://example.com/article-1"],
                }
            },
        },
        diagnostics={
            "reason_codes": ["verified_query_results"],
            "candidate_origins": ["evidence_form", "heuristic_path"],
            "budget": {"used_requests": 2, "remaining_requests": 2},
            "attempts": [{"phase": "query_probe", "status": "verified"}],
        },
        exploration_request=None,
        execution=_execution(),
    )


def _root_item(*, capabilities: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "item_key": "root-item",
        "params": {"site_entries": ["https://example.com"]},
    }


def _root_item_without_external_fallback() -> dict[str, object]:
    item = _root_item()
    item["params"] = {
        "site_entries": ["https://example.com"],
        "enable_external_search_fallback": False,
    }
    return item


def test_declared_domain_root_still_resolves_and_reuses_verified_execution() -> None:
    entry = {
        "site_url": "https://example.com",
        "domain": "example.com",
        "entry_type": "domain_root",
        "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
    }
    resolution = _verified_resolution()

    with (
        patch(
            "app.services.resource_pool.unified_search.get_site_entry_by_url",
            return_value=entry,
        ),
        patch(
            "app.services.resource_pool.search_contract_discovery.resolve_query_contract",
            return_value=resolution,
        ) as resolve,
        patch(
            "app.services.resource_pool.unified_search.execute_feed_probe",
        ) as feed_probe,
        patch(
            "app.services.resource_pool.unified_search.execute_search_template",
        ) as search_probe,
    ):
        result = unified_search_by_item_payload(
            project_key="demo",
            item=_root_item(),
            query_terms=["robotics"],
            allow_term_fallback=False,
        )

    resolve.assert_called_once()
    feed_probe.assert_not_called()
    search_probe.assert_not_called()
    assert result.candidates == ["https://example.com/article-1"]
    assert result.site_entries_used[0]["entry_type"] == "domain_root"
    runtime = result.runtime_diagnostics[0]
    assert runtime["query_contract"]["status"] == "verified"
    assert runtime["query_contract_reused_execution"] is True
    provenance = runtime["query_contract_selected_provenance"]
    assert provenance["origin"] == "evidence_form"
    assert provenance["evidence_url"] == "https://example.com/"
    assert result.query_discovery_budget["used_requests"] == 0
    assert result.query_discovery_budget["remaining_requests"] == 4


def test_discovery_budget_exhaustion_still_uses_authorized_external_fallback() -> None:
    entry = {
        "site_url": "https://example.com",
        "domain": "example.com",
        "entry_type": "domain_root",
        "capabilities": {"supports_query_terms": False, "keyword_mode": "none"},
    }
    resolution = QueryContractResolution(
        status="budget_exhausted",
        entry=None,
        diagnostics={"reason_codes": ["request_budget_exhausted"]},
        exploration_request={"status": "requested"},
    )

    with (
        patch(
            "app.services.resource_pool.unified_search.get_site_entry_by_url",
            return_value=entry,
        ),
        patch(
            "app.services.resource_pool.search_contract_discovery.resolve_query_contract",
            return_value=resolution,
        ),
        patch(
            "app.services.resource_pool.unified_search.execute_external_site_search",
            return_value=_execution("https://external.example/coverage"),
        ) as external,
    ):
        result = unified_search_by_item_payload(
            project_key="demo",
            item=_root_item(),
            query_terms=["robotics"],
            allow_term_fallback=False,
        )

    external.assert_called_once()
    assert result.candidates == ["https://external.example/coverage"]
    assert result.runtime_diagnostics[0]["query_contract_external_fallback"] is True


def test_missing_interface_without_fallback_is_explicit_query_gap() -> None:
    entry = {
        "site_url": "https://example.com",
        "domain": "example.com",
        "entry_type": "domain_root",
        "capabilities": {"supports_query_terms": False, "keyword_mode": "none"},
    }
    resolution = QueryContractResolution(
        status="unresolved",
        entry=None,
        diagnostics={"reason_codes": ["no_candidate_interface"]},
        exploration_request={"status": "requested"},
    )

    with (
        patch(
            "app.services.resource_pool.unified_search.get_site_entry_by_url",
            return_value=entry,
        ),
        patch(
            "app.services.resource_pool.search_contract_discovery.resolve_query_contract",
            return_value=resolution,
        ),
        patch(
            "app.services.resource_pool.unified_search.execute_external_site_search",
        ) as external,
    ):
        result = unified_search_by_item_payload(
            project_key="demo",
            item=_root_item_without_external_fallback(),
            query_terms=["robotics"],
            allow_term_fallback=False,
            write_to_pool=False,
            query_discovery_budget=QueryDiscoveryBudget(
                max_requests=0,
                max_templates=0,
                timeout_seconds=15,
            ),
        )

    external.assert_not_called()
    assert result.candidates == []
    assert result.errors[0]["error"] == "query_discovery_required"
    assert result.errors[0]["exploration_request_status"] == "requested"


def test_handler_run_builds_one_shared_budget_from_merged_runtime_params() -> None:
    captured = {}

    def _batch(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            site_entries_used=[],
            candidates=[],
            written={"urls_new": 0, "urls_skipped": 0},
            ingest_result={},
            errors=[],
            runtime_diagnostics=[],
            relevance_review_queue=None,
            query_discovery_budget=kwargs["query_discovery_budget"].diagnostics,
        )

    with patch.object(source_library_resolver, "_run_single_handler_search_batch", side_effect=_batch):
        result = source_library_resolver._run_handler_search_atom(
            item={"item_key": "root-item", "params": {"query_discovery_max_requests": 2}},
            params={"query_discovery_max_requests": 7, "query_discovery_max_templates": 1},
            query_terms=["robotics"],
            project_key="demo",
            candidate_limits=source_library_resolver.HandlerCandidateLimits(
                per_keyword_limit=3,
                global_max_candidates=7,
                global_ingest_limit=5,
                sitemap_max_depth=1,
                sitemap_max_sitemaps=3,
            ),
        )

    assert result is not None
    budget = captured["query_discovery_budget"]
    assert isinstance(budget, QueryDiscoveryBudget)
    assert budget.max_requests == 7
    assert budget.max_templates == 1
    assert captured["query_discovery_budget"] is budget


def test_terminal_keeps_provider_and_candidate_success_above_discovery_budget() -> None:
    dto = to_terminal_output_dto(
        {
            "channel_key": "handler.cluster",
            "result": {
                "records": [
                    {
                        "record_id": "record-1",
                        "url": "https://example.com/article-1",
                        "title": "Coverage",
                        "content_text": "Fetched text",
                    }
                ],
                "query_contract": {
                    "statuses": ["budget_exhausted"],
                    "reason_codes": ["request_budget_exhausted"],
                    "discovery_budget": {"remaining_requests": 0},
                },
                "execution_request": {"source_mode": "site_search"},
            },
        }
    )

    assert dto["status"] == "ok"
    assert dto["meta"]["reason_code"] == "ok"

    empty_dto = to_terminal_output_dto(
        {
            "channel_key": "handler.cluster",
            "result": {
                "records": [],
                "errors": ["query_discovery_required"],
                "query_contract": {
                    "statuses": ["budget_exhausted"],
                    "reason_codes": ["request_budget_exhausted"],
                    "discovery_budget": {"remaining_requests": 0},
                },
                "execution_request": {"source_mode": "site_search"},
            },
        }
    )
    assert empty_dto["status"] == "error"
    assert empty_dto["meta"]["reason_code"] == "query_discovery_budget_exhausted"
