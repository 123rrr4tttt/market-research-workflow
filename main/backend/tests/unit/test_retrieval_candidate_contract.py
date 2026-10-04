from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.search import web
from app.services.search.candidate_contracts import CandidateSearchRequest
from app.services.search.candidate_search import discover_candidates

pytestmark = pytest.mark.unit


def test_explicit_provider_keeps_duplicate_discoveries_and_partial_failure() -> None:
    request = CandidateSearchRequest(
        topic="robotics",
        provider="serper",
        keywords=("robotics market", "robotics policy"),
        exclude_existing=False,
        max_results=6,
        facet_ref="facet:technology.v1",
    )
    first = [
        {"title": "Market", "link": "https://example.com/a?utm_source=one", "snippet": "market", "source": "serper"},
        {"title": "Duplicate", "link": "https://example.com/a?utm_medium=two", "snippet": "same URL", "source": "serper"},
    ]
    with patch.dict("os.environ", {"SERPER_API_KEY": "test-key"}):
        with patch.object(web, "_serper_search", side_effect=[first, TimeoutError("provider timed out")]):
            bundle = discover_candidates(request)

    assert [candidate.resource_uri for candidate in bundle.candidates] == ["https://example.com/a"]
    assert [row.keyword for row in bundle.occurrences] == ["robotics market", "robotics market"]
    assert [row.original_rank for row in bundle.occurrences] == [1, 2]
    assert [row.retained for row in bundle.occurrences] == [True, False]
    assert all(row.facet_ref == "facet:technology.v1" for row in bundle.occurrences)
    assert [(row.status, row.failure_kind) for row in bundle.observations] == [
        ("completed", None), ("failed", "timeout")
    ]
    assert bundle.partial is True
    assert bundle.stop_reason == "candidates_observed"
    assert bundle.legacy_list()[0]["link"] == "https://example.com/a"


def test_config_gap_and_empty_success_have_distinct_observations() -> None:
    request = CandidateSearchRequest(topic="robotics", provider="serper", keywords=("robotics",), exclude_existing=False)
    with patch.dict("os.environ", {"SERPER_API_KEY": ""}):
        with patch("app.settings.config.settings", SimpleNamespace(serper_api_key=None)):
            missing = discover_candidates(request)
    assert missing.candidates == ()
    assert missing.observations[0].status == "not_configured"
    assert missing.observations[0].failure_kind == "not_configured"
    assert missing.stop_reason == "no_candidates_observed"

    with patch.dict("os.environ", {"SERPER_API_KEY": "test-key"}):
        with patch.object(web, "_serper_search", return_value=[]):
            empty = discover_candidates(request)
    assert empty.candidates == ()
    assert empty.observations[0].status == "completed"
    assert empty.observations[0].returned_count == 0
    assert empty.stop_reason == "no_candidates_observed"


def test_old_auto_order_and_dedup_are_preserved_by_typed_projection() -> None:
    results = [
        {"title": "General", "link": "https://example.net/general", "snippet": "overview", "source": "serper"},
        {"title": "Robotics revenue 2026", "link": "https://example.net/revenue?utm_campaign=x", "snippet": "robotics market data", "source": "serper"},
        {"title": "Duplicate", "link": "https://example.net/revenue?utm_campaign=y", "snippet": "copy", "source": "serper"},
    ]
    request = CandidateSearchRequest(topic="robotics", provider="auto", keywords=("robotics",), exclude_existing=False, max_results=5)
    with patch.dict("os.environ", {"SERPER_API_KEY": "test-key", "SERPAPI_KEY": "", "SERPAPI_API_KEY": "", "GOOGLE_SEARCH_CSE_ID": ""}):
        with patch("app.settings.config.settings", SimpleNamespace(
            serpapi_key=None,
            google_search_api_key=None,
            google_search_cse_id=None,
            serpstack_key=None,
            serper_api_key="test-key",
        )):
            with patch.object(web, "_serper_search", return_value=results):
                bundle = discover_candidates(request)
    assert [row["link"] for row in bundle.legacy_list()] == [
        "https://example.net/revenue", "https://example.net/general"
    ]
    assert [candidate.result_rank for candidate in bundle.candidates] == [1, 2]
    assert len(bundle.occurrences) == 3
    assert [row.retained for row in bundle.occurrences] == [True, True, False]
    assert bundle.observations[0].provider == "serper"
