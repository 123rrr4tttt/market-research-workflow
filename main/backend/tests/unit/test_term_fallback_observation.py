from unittest.mock import patch

import pytest

from app.services.resource_pool.search_template_service import (
    execute_external_site_search,
    execute_feed_probe,
    execute_search_template,
    execute_sitemap_probe,
)
from app.services.resource_pool.unified_search import unified_search_by_item_payload


pytestmark = pytest.mark.unit


HTML = """
<html><body><a href="/posts/market-outlook">Market outlook</a></body></html>
"""

MATCH_HTML = """
<html><body><a href="/posts/robotics-guide">Robotics guide</a></body></html>
"""

EMPTY_HTML = "<html><body></body></html>"

FEED = """
<rss><channel>
  <item><title>Market outlook</title><link>https://example.com/posts/market-outlook</link></item>
</channel></rss>
"""

EMPTY_FEED = '<rss><channel></channel></rss>'

FEED_MATCH = """
<rss><channel>
  <item><title>Robotics Weekly</title><link>https://example.com/posts/robotics-weekly</link></item>
</channel></rss>
"""

SITEMAP = """
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/posts/market-outlook</loc></url>
</urlset>
"""

EMPTY_SITEMAP = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'

SITEMAP_MATCH = """
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/posts/robotics-guide</loc></url>
</urlset>
"""

EXTERNAL_RESULTS = [{"title": "Market outlook", "link": "https://example.com/posts/market-outlook"}]
EXTERNAL_MATCH = [{"title": "Robotics guide", "link": "https://example.com/posts/robotics-guide"}]


def _assert_observation(result, *, expected_used: bool, expected_state: str) -> None:
    assert result.used_term_fallback is expected_used
    assert result.diagnostics["used_term_fallback"] is expected_used
    assert result.diagnostics["candidate_filter_state"] == expected_state


ROUTE_DATA = {
    "search_template": (HTML, MATCH_HTML, EMPTY_HTML, "robotics-guide"),
    "external_search": (EXTERNAL_RESULTS, EXTERNAL_MATCH, [], "robotics-guide"),
    "rss": (FEED, FEED_MATCH, EMPTY_FEED, "robotics-weekly"),
    "sitemap": (SITEMAP, SITEMAP_MATCH, EMPTY_SITEMAP, "robotics-guide"),
}

OBSERVATION_CASES = [
    (False, "matched", False, "selected"),
    (True, "matched", False, "selected"),
    (False, "unmatched", False, "term_filter_empty_no_fallback"),
    (True, "unmatched", True, "term_filter_empty_fallback_used"),
    (False, "empty", False, "empty_no_raw_candidates"),
    (True, "empty", False, "empty_no_raw_candidates"),
]


def _source_payload(route: str, case: str):
    return ROUTE_DATA[route][{"unmatched": 0, "matched": 1, "empty": 2}[case]]


def _expected_urls(route: str, *, allow: bool, case: str) -> list[str]:
    if case == "matched":
        return [f"https://example.com/posts/{ROUTE_DATA[route][3]}"]
    if allow and case == "unmatched":
        return ["https://example.com/posts/market-outlook"]
    return []


@pytest.mark.parametrize("route", ROUTE_DATA)
@pytest.mark.parametrize("allow,case,expected_used,expected_state", OBSERVATION_CASES)
def test_query_execution_reports_actual_term_fallback(
    route: str, allow: bool, case: str, expected_used: bool, expected_state: str,
) -> None:
    params = {
        "enable_external_search_slowlane": False,
    }
    common = dict(query_terms=["robotics"], probe_timeout=0.1, allow_term_fallback=allow, params=params)
    payload = _source_payload(route, case)
    with (
        patch("app.services.resource_pool.search_template_service.fetch_html", return_value=(payload, object())),
        patch("app.services.search.web.search_sources", return_value=payload),
    ):
        if route == "search_template":
            result = execute_search_template(
                template="https://example.com/search?q={{q}}", entry_domain="example.com", **common,
            )
        elif route == "external_search":
            result = execute_external_site_search(entry_domain="example.com", **common)
        elif route == "rss":
            result = execute_feed_probe(feed_url="https://example.com/feed.xml", **common)
        else:
            result = execute_sitemap_probe(
                sitemap_url="https://example.com/sitemap.xml", max_depth=1, max_sitemaps=1, **common,
            )

    assert [item.url for item in result.selected_candidates] == _expected_urls(route, allow=allow, case=case)
    _assert_observation(result, expected_used=expected_used, expected_state=expected_state)


@pytest.mark.parametrize("route", ["search_template", "rss", "sitemap"])
@pytest.mark.parametrize("allow,case,expected_used,expected_state", OBSERVATION_CASES)
def test_unified_search_preserves_filter_diagnostics_without_false_fallback_review(
    route: str, allow: bool, case: str, expected_used: bool, expected_state: str,
) -> None:
    site_url = {
        "search_template": "https://example.com/search?q={{q}}",
        "rss": "https://example.com/feed.xml",
        "sitemap": "https://example.com/sitemap.xml",
    }[route]
    entry = {
        "site_url": site_url,
        "domain": "example.com",
        "entry_type": route,
        "template": site_url if route == "search_template" else None,
        "capabilities": {
            "supports_query_terms": True,
            "keyword_mode": "search" if route == "search_template" else "filter",
        },
    }
    item = {
        "item_key": "fallback-observation",
        "params": {
            "site_entries": [site_url],
            "enable_external_search_fallback": False,
        },
    }
    with (
        patch("app.services.resource_pool.unified_search.get_site_entry_by_url", return_value=entry),
        patch("app.services.resource_pool.search_template_service.fetch_html", return_value=(_source_payload(route, case), object())),
        patch("app.services.resource_pool.unified_search.execute_external_site_search") as external,
    ):
        result = unified_search_by_item_payload(
            project_key="demo", item=item, query_terms=["robotics"], allow_term_fallback=allow,
        )

    external.assert_not_called()
    assert result.candidates == _expected_urls(route, allow=allow, case=case)
    errors = {row["error"] for row in result.errors}
    assert ("url_term_filter_empty_fallback_used" in errors) is expected_used
    expected_no_fallback = expected_state == "term_filter_empty_no_fallback" or (case == "empty" and not allow)
    assert ("url_term_filter_empty_no_fallback" in errors) is expected_no_fallback
    runtime = result.runtime_diagnostics[0]
    assert (runtime.get("relevance_review_reason") == "term_fallback_candidates") is (route == "search_template" and expected_used)
    if not expected_used:
        assert not runtime.get("relevance_review_required")
