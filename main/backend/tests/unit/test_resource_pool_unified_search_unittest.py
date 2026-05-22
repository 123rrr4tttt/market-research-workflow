from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.resource_pool.unified_search import _normalize_search_template_placeholders
from app.services.resource_pool.unified_search import _filter_link_candidates_by_terms_with_fallback
from app.services.resource_pool.unified_search import _entry_keyword_mode
from app.services.resource_pool.unified_search import _entry_supports_query_terms
from app.services.resource_pool.unified_search import _resolve_search_template_pagination
from app.services.resource_pool.unified_search import unified_search_by_item_payload


class ResourcePoolUnifiedSearchUnitTestCase(unittest.TestCase):
    def test_normalize_search_template_placeholders_decodes_encoded_markers(self) -> None:
        raw = "https://example.com/search?q=%7B%7Bq%7D%7D&page=%7B%7Bpage%7D%7D"
        normalized = _normalize_search_template_placeholders(raw)
        self.assertEqual(normalized, "https://example.com/search?q={{q}}&page={{page}}")

    def test_filter_link_candidates_matches_anchor_text_when_url_has_no_term(self) -> None:
        candidates = [
            {
                "url": "https://example.com/posts/123",
                "text": "Hands-on with Humane AI Pin",
                "title": "",
            },
            {
                "url": "https://example.com/posts/456",
                "text": "Weekly newsletter",
                "title": "",
            },
        ]

        filtered, used_fallback = _filter_link_candidates_by_terms_with_fallback(
            candidates,
            ["Humane AI Pin"],
            allow_fallback=False,
        )

        self.assertFalse(used_fallback)
        self.assertEqual(filtered, [candidates[0]])

    def test_resolve_search_template_pagination_uses_defaults(self) -> None:
        start_page, max_pages = _resolve_search_template_pagination({})
        self.assertEqual(start_page, 1)
        self.assertEqual(max_pages, 1)

    def test_resolve_search_template_pagination_clamps_values(self) -> None:
        start_page, max_pages = _resolve_search_template_pagination({"page": -3, "max_pages": 999})
        self.assertEqual(start_page, 1)
        self.assertEqual(max_pages, 50)

    def test_entry_keyword_capabilities_fill_missing_fields_from_entry_type(self) -> None:
        entry = {
            "entry_type": "rss",
            "channel_key": "generic_web.rss",
            "capabilities": {"supports_query_terms": True},
        }

        self.assertTrue(_entry_supports_query_terms(entry, "rss"))
        self.assertEqual(_entry_keyword_mode(entry, "rss"), "filter")

    def test_unified_search_payload_keeps_rss_entries_with_filter_mode(self) -> None:
        item = {
            "item_key": "rss-item",
            "params": {
                "site_entries": ["https://example.com/feed.xml"],
            },
        }
        rss_xml = """
        <rss version="2.0">
          <channel>
            <item>
              <title>Humane AI Pin review</title>
              <description>Hands-on coverage</description>
              <link>https://example.com/posts/humane-ai-pin-review</link>
            </item>
          </channel>
        </rss>
        """

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/feed.xml",
                    "domain": "example.com",
                    "entry_type": "rss",
                    "channel_key": "generic_web.rss",
                    "capabilities": {"supports_query_terms": True},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_feed_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/posts/humane-ai-pin-review",
                            matched_by="text",
                            route_kind="article",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.95,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ),
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["Humane AI Pin"],
                allow_term_fallback=False,
            )

        self.assertEqual(result.candidates, ["https://example.com/posts/humane-ai-pin-review"])
        self.assertEqual(len(result.site_entries_used), 1)
        self.assertEqual(result.site_entries_used[0]["entry_type"], "rss")

    def test_unified_search_payload_uses_shared_feed_probe(self) -> None:
        item = {
            "item_key": "rss-item",
            "params": {
                "site_entries": ["https://example.com/feed.xml"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/feed.xml",
                    "domain": "example.com",
                    "entry_type": "rss",
                    "channel_key": "generic_web.rss",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "filter"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_feed_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/posts/rss-guide",
                            matched_by="text",
                            route_kind="article",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.8,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ) as execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        execute.assert_called_once()
        self.assertEqual(result.candidates, ["https://example.com/posts/rss-guide"])

    def test_unified_search_payload_writes_granular_source_ref_to_pool(self) -> None:
        item = {
            "item_key": "rss-item",
            "params": {
                "site_entries": ["https://example.com/feed.xml"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/feed.xml",
                    "domain": "example.com",
                    "entry_type": "rss",
                    "channel_key": "generic_web.rss",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "filter"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_feed_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/posts/rss-guide",
                            matched_by="text",
                            route_kind="article",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.8,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ),
            patch("app.services.resource_pool.unified_search.append_url", return_value=True) as append,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
                write_to_pool=True,
            )

        self.assertEqual(result.written, {"urls_new": 1, "urls_skipped": 0})
        append.assert_called_once()
        source_ref = append.call_args.kwargs["source_ref"]
        self.assertEqual(source_ref["item_key"], "rss-item")
        self.assertEqual(source_ref["query_terms"], ["robotics"])
        self.assertEqual(source_ref["site_entry_url"], "https://example.com/feed.xml")
        self.assertEqual(source_ref["entry_type"], "rss")
        self.assertEqual(source_ref["domain"], "example.com")

    def test_unified_search_payload_passes_candidate_scoring_config_to_search_template(self) -> None:
        item = {
            "item_key": "search-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
                "candidate_scoring_config": {
                    "route_kind_bonus": {"section": 0.2},
                    "thresholds": {"search_template": 0.55},
                },
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://example.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/topic/openai",
                            matched_by="title",
                            route_kind="section",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=1.2,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
                ),
            ) as execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["OpenAI"],
                allow_term_fallback=False,
            )

        execute.assert_called_once()
        passed_params = execute.call_args.kwargs["params"]
        self.assertEqual(passed_params["candidate_scoring_config"]["route_kind_bonus"]["section"], 0.2)
        self.assertEqual(passed_params["candidate_scoring_config"]["thresholds"]["search_template"], 0.55)
        self.assertEqual(result.candidates, ["https://example.com/topic/openai"])

    def test_unified_search_payload_applies_entry_type_target_mix(self) -> None:
        item = {
            "item_key": "mixed-item",
            "params": {
                "site_entries": [
                    "https://example.com/search?q={{q}}",
                    "https://example.com/feed.xml",
                    "https://example.com/sitemap.xml",
                ],
                "candidate_target_config": {
                    "bucket_by": "entry_type",
                    "target_total": 4,
                    "ratios": {
                        "search_template": 0.25,
                        "rss": 0.25,
                        "sitemap": 0.5,
                    },
                },
            },
        }

        def _site_entry(*_: object, **kwargs: object) -> dict[str, object]:
            url = str(kwargs.get("site_url") or "")
            if url.endswith("feed.xml"):
                return {
                    "site_url": url,
                    "domain": "example.com",
                    "entry_type": "rss",
                    "channel_key": "generic_web.rss",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "filter"},
                }
            if url.endswith("sitemap.xml"):
                return {
                    "site_url": url,
                    "domain": "example.com",
                    "entry_type": "sitemap",
                    "channel_key": "generic_web.sitemap",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "filter"},
                }
            return {
                "site_url": url,
                "domain": "example.com",
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": url,
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
            }

        with (
            patch("app.services.resource_pool.unified_search.get_site_entry_by_url", side_effect=_site_entry),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(url="https://example.com/news/a1", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.99),
                        SimpleNamespace(url="https://example.com/news/a2", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.98),
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
                ),
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_feed_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(url="https://example.com/rss/r1", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.97),
                        SimpleNamespace(url="https://example.com/rss/r2", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.96),
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_sitemap_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(url="https://example.com/site/s1", matched_by="title_hint", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.95),
                        SimpleNamespace(url="https://example.com/site/s2", matched_by="title_hint", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.94),
                        SimpleNamespace(url="https://example.com/site/s3", matched_by="title_hint", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.93),
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ),
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["OpenAI"],
                allow_term_fallback=False,
                max_candidates=4,
            )

        self.assertEqual(len(result.candidates), 4)
        counts = {"search_template": 0, "rss": 0, "sitemap": 0}
        for url in result.candidates:
            # recover source from result ordering through known URL prefixes
            if "/news/" in url:
                counts["search_template"] += 1
            elif "/rss/" in url:
                counts["rss"] += 1
            elif "/site/" in url:
                counts["sitemap"] += 1
        self.assertEqual(counts, {"search_template": 1, "rss": 1, "sitemap": 2})

    def test_unified_search_payload_applies_route_kind_target_mix(self) -> None:
        item = {
            "item_key": "route-mix-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
                "candidate_target_config": {
                    "bucket_by": "route_kind",
                    "target_total": 4,
                    "ratios": {
                        "article": 0.5,
                        "section": 0.5,
                    },
                },
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://example.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(url="https://example.com/news/a1", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.99),
                        SimpleNamespace(url="https://example.com/news/a2", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.98),
                        SimpleNamespace(url="https://example.com/topic/t1", matched_by="title", route_kind="section", candidate_quality="high", usable_for_search=True, score=0.97),
                        SimpleNamespace(url="https://example.com/topic/t2", matched_by="title", route_kind="section", candidate_quality="high", usable_for_search=True, score=0.96),
                        SimpleNamespace(url="https://example.com/topic/t3", matched_by="title", route_kind="section", candidate_quality="high", usable_for_search=True, score=0.95),
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
                ),
            ),
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["OpenAI"],
                allow_term_fallback=False,
                max_candidates=4,
            )

        article_count = sum(1 for url in result.candidates if "/news/" in url)
        section_count = sum(1 for url in result.candidates if "/topic/" in url)
        self.assertEqual(article_count, 2)
        self.assertEqual(section_count, 2)

    def test_unified_search_payload_supports_equal_bucket_allocation(self) -> None:
        item = {
            "item_key": "equal-mix-item",
            "params": {
                "site_entries": [
                    "https://example.com/search?q={{q}}",
                    "https://example.com/feed.xml",
                    "https://example.com/sitemap.xml",
                ],
                "candidate_target_config": {
                    "bucket_by": "entry_type",
                    "allocation_mode": "equal",
                    "target_total": 6,
                },
            },
        }

        def _site_entry(*_: object, **kwargs: object) -> dict[str, object]:
            url = str(kwargs.get("site_url") or "")
            if url.endswith("feed.xml"):
                return {
                    "site_url": url,
                    "domain": "example.com",
                    "entry_type": "rss",
                    "channel_key": "generic_web.rss",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "filter"},
                }
            if url.endswith("sitemap.xml"):
                return {
                    "site_url": url,
                    "domain": "example.com",
                    "entry_type": "sitemap",
                    "channel_key": "generic_web.sitemap",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "filter"},
                }
            return {
                "site_url": url,
                "domain": "example.com",
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": url,
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
            }

        with (
            patch("app.services.resource_pool.unified_search.get_site_entry_by_url", side_effect=_site_entry),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(url="https://example.com/news/a1", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.99),
                        SimpleNamespace(url="https://example.com/news/a2", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.98),
                        SimpleNamespace(url="https://example.com/news/a3", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.97),
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
                ),
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_feed_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(url="https://example.com/rss/r1", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.96),
                        SimpleNamespace(url="https://example.com/rss/r2", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.95),
                        SimpleNamespace(url="https://example.com/rss/r3", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.94),
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_sitemap_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(url="https://example.com/site/s1", matched_by="title_hint", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.93),
                        SimpleNamespace(url="https://example.com/site/s2", matched_by="title_hint", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.92),
                        SimpleNamespace(url="https://example.com/site/s3", matched_by="title_hint", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.91),
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ),
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["OpenAI"],
                allow_term_fallback=False,
                max_candidates=6,
            )

        counts = {"search_template": 0, "rss": 0, "sitemap": 0}
        for url in result.candidates:
            if "/news/" in url:
                counts["search_template"] += 1
            elif "/rss/" in url:
                counts["rss"] += 1
            elif "/site/" in url:
                counts["sitemap"] += 1
        self.assertEqual(counts, {"search_template": 2, "rss": 2, "sitemap": 2})

    def test_unified_search_payload_supports_target_per_bucket(self) -> None:
        item = {
            "item_key": "per-bucket-item",
            "params": {
                "site_entries": [
                    "https://example.com/search?q={{q}}",
                    "https://example.com/feed.xml",
                    "https://example.com/sitemap.xml",
                ],
                "candidate_target_config": {
                    "bucket_by": "entry_type",
                    "target_per_bucket": 1,
                },
            },
        }

        def _site_entry(*_: object, **kwargs: object) -> dict[str, object]:
            url = str(kwargs.get("site_url") or "")
            if url.endswith("feed.xml"):
                return {
                    "site_url": url,
                    "domain": "example.com",
                    "entry_type": "rss",
                    "channel_key": "generic_web.rss",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "filter"},
                }
            if url.endswith("sitemap.xml"):
                return {
                    "site_url": url,
                    "domain": "example.com",
                    "entry_type": "sitemap",
                    "channel_key": "generic_web.sitemap",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "filter"},
                }
            return {
                "site_url": url,
                "domain": "example.com",
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": url,
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
            }

        with (
            patch("app.services.resource_pool.unified_search.get_site_entry_by_url", side_effect=_site_entry),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(url="https://example.com/news/a1", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.99),
                        SimpleNamespace(url="https://example.com/news/a2", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.98),
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
                ),
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_feed_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(url="https://example.com/rss/r1", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.97),
                        SimpleNamespace(url="https://example.com/rss/r2", matched_by="title", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.96),
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_sitemap_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(url="https://example.com/site/s1", matched_by="title_hint", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.95),
                        SimpleNamespace(url="https://example.com/site/s2", matched_by="title_hint", route_kind="article", candidate_quality="high", usable_for_search=True, score=0.94),
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ),
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["OpenAI"],
                allow_term_fallback=False,
                max_candidates=10,
            )

        self.assertEqual(len(result.candidates), 3)
        counts = {"search_template": 0, "rss": 0, "sitemap": 0}
        for url in result.candidates:
            if "/news/" in url:
                counts["search_template"] += 1
            elif "/rss/" in url:
                counts["rss"] += 1
            elif "/site/" in url:
                counts["sitemap"] += 1
        self.assertEqual(counts, {"search_template": 1, "rss": 1, "sitemap": 1})

    def test_unified_search_payload_defaults_to_equal_domain_mix_across_waves(self) -> None:
        item = {
            "item_key": "default-equal-domain-mix-item",
            "params": {
                "site_entries": [
                    "https://arxiv.org/search?q={{q}}",
                    "https://help.openai.com/search?q={{q}}",
                    "https://github.com/search?q={{q}}",
                ],
            },
        }

        def _site_entry(*_: object, **kwargs: object) -> dict[str, object]:
            url = str(kwargs.get("site_url") or "")
            domain = url.split("/")[2]
            return {
                "site_url": url,
                "domain": domain,
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": url,
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
            }

        def _search_result(prefix: str, score_start: float) -> SimpleNamespace:
            return SimpleNamespace(
                selected_candidates=[
                    SimpleNamespace(
                        url=f"https://{prefix}/posts/1",
                        matched_by="title",
                        route_kind="article",
                        candidate_quality="high",
                        usable_for_search=True,
                        score=score_start,
                    ),
                    SimpleNamespace(
                        url=f"https://{prefix}/posts/2",
                        matched_by="title",
                        route_kind="article",
                        candidate_quality="high",
                        usable_for_search=True,
                        score=score_start - 0.01,
                    ),
                    SimpleNamespace(
                        url=f"https://{prefix}/posts/3",
                        matched_by="title",
                        route_kind="article",
                        candidate_quality="high",
                        usable_for_search=True,
                        score=score_start - 0.02,
                    ),
                ],
                used_term_fallback=False,
                errors=[],
                diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
            )

        def _execute_search_template(*, template: str, **_: object) -> SimpleNamespace:
            if "help.openai.com" in template:
                return _search_result("help.openai.com", 0.97)
            return _search_result("github.com", 0.96)

        with (
            patch("app.services.resource_pool.unified_search.get_site_entry_by_url", side_effect=_site_entry),
            patch(
                "app.services.resource_pool.unified_search.resolve_site_search_policy_for_entry",
                side_effect=lambda site_url, entry: SimpleNamespace(
                    category="api_preferred" if "arxiv.org" in site_url else "keep",
                    reason="test_policy",
                    preferred_search_service="basic",
                    implementation_hint=None,
                    parser_profile=None,
                    provider_key="arxiv" if "arxiv.org" in site_url else None,
                ),
            ),
            patch(
                "app.services.resource_pool.unified_search.handle_official_access_api",
                return_value={
                    "candidates": [
                        "https://arxiv.org/abs/2501.00001",
                        "https://arxiv.org/abs/2501.00002",
                        "https://arxiv.org/abs/2501.00003",
                    ],
                    "errors": [],
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                side_effect=_execute_search_template,
            ),
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["OpenAI"],
                allow_term_fallback=False,
                max_candidates=6,
            )

        counts = {"arxiv.org": 0, "help.openai.com": 0, "github.com": 0}
        for url in result.candidates:
            if "arxiv.org" in url:
                counts["arxiv.org"] += 1
            elif "help.openai.com" in url:
                counts["help.openai.com"] += 1
            elif "github.com" in url:
                counts["github.com"] += 1
        self.assertEqual(counts, {"arxiv.org": 2, "help.openai.com": 2, "github.com": 2})

    def test_unified_search_payload_uses_shared_sitemap_probe(self) -> None:
        item = {
            "item_key": "sitemap-item",
            "params": {
                "site_entries": ["https://example.com/sitemap.xml"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/sitemap.xml",
                    "domain": "example.com",
                    "entry_type": "sitemap",
                    "channel_key": "generic_web.sitemap",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "filter"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_sitemap_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/posts/sitemap-guide",
                            matched_by="url",
                            route_kind="article",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.7,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ) as execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        execute.assert_called_once()
        self.assertEqual(result.candidates, ["https://example.com/posts/sitemap-guide"])

    def test_unified_search_policy_skips_api_preferred_sites(self) -> None:
        item = {
            "item_key": "arxiv-search",
            "params": {
                "site_entries": ["https://arxiv.org/search?q={{q}}"],
            },
        }

        with patch(
            "app.services.resource_pool.unified_search.get_site_entry_by_url",
            return_value={
                "site_url": "https://arxiv.org/search?q={{q}}",
                "domain": "arxiv.org",
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": "https://arxiv.org/search?q={{q}}",
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
            },
        ), patch("app.services.resource_pool.unified_search.handle_official_access_api") as official, patch(
            "app.services.resource_pool.unified_search.execute_search_template"
        ) as execute:
            official.return_value = {
                "candidates": ["https://arxiv.org/abs/2501.00001"],
                "errors": [],
            }
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        execute.assert_not_called()
        official.assert_called_once()
        self.assertEqual(result.candidates, ["https://arxiv.org/abs/2501.00001"])
        self.assertEqual(result.runtime_diagnostics[0]["search_service"], "official_api")

    def test_unified_search_payload_reads_official_access_site_entries(self) -> None:
        item = {
            "item_key": "arxiv-search",
            "params": {
                "site_entries": [],
                "official_access_site_entries": ["https://arxiv.org/search?q={{q}}"],
            },
        }

        with patch(
            "app.services.resource_pool.unified_search.get_site_entry_by_url",
            return_value={
                "site_url": "https://arxiv.org/search?q={{q}}",
                "domain": "arxiv.org",
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": "https://arxiv.org/search?q={{q}}",
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
            },
        ), patch("app.services.resource_pool.unified_search.handle_official_access_api") as official, patch(
            "app.services.resource_pool.unified_search.execute_search_template"
        ) as execute:
            official.return_value = {
                "candidates": ["https://arxiv.org/abs/2501.00002"],
                "errors": [],
            }
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        execute.assert_not_called()
        official.assert_called_once()
        self.assertEqual(result.candidates, ["https://arxiv.org/abs/2501.00002"])
        self.assertEqual(result.runtime_diagnostics[0]["search_service"], "official_api")

    def test_unified_search_forwards_parser_profile_to_search_template(self) -> None:
        item = {
            "item_key": "search-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
            },
        }

        with patch(
            "app.services.resource_pool.unified_search.get_site_entry_by_url",
            return_value={
                "site_url": "https://example.com/search?q={{q}}",
                "domain": "example.com",
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": "https://example.com/search?q={{q}}",
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                "extra": {"remediation": {"parser_profile": "fallback_anchor_only"}},
            },
        ), patch(
            "app.services.resource_pool.unified_search.execute_search_template",
            return_value=SimpleNamespace(selected_candidates=[], used_term_fallback=False, errors=[], diagnostics={}),
        ) as execute:
            unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        self.assertEqual(execute.call_args.kwargs["params"]["parser_profile"], "fallback_anchor_only")

    def test_unified_search_marks_anchor_only_parser_candidates_for_review(self) -> None:
        item = {
            "item_key": "search-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
            },
        }

        with patch(
            "app.services.resource_pool.unified_search.get_site_entry_by_url",
            return_value={
                "site_url": "https://example.com/search?q={{q}}",
                "domain": "example.com",
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": "https://example.com/search?q={{q}}",
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                "extra": {"remediation": {"parser_profile": "fallback_anchor_only"}},
            },
        ), patch(
            "app.services.resource_pool.unified_search.execute_search_template",
            return_value=SimpleNamespace(
                selected_candidates=[
                    SimpleNamespace(
                        url="https://example.com/posts/robotics-review",
                        matched_by="title",
                        candidate_quality="high",
                        usable_for_search=True,
                        score=0.9,
                        route_kind="article",
                    )
                ],
                used_term_fallback=False,
                errors=[],
                diagnostics={"search_service": "basic"},
            ),
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        self.assertEqual(result.candidates, ["https://example.com/posts/robotics-review"])
        self.assertEqual(result.runtime_diagnostics[0]["adapter_capability_status"], "review")
        self.assertTrue(result.runtime_diagnostics[0]["relevance_review_required"])
        self.assertEqual(result.runtime_diagnostics[0]["parser_profile_resolved"], "fallback_anchor_only")

    def test_unified_search_policy_skips_social_sites(self) -> None:
        item = {
            "item_key": "reddit-search",
            "params": {
                "site_entries": ["https://reddit.com/search?q={{q}}"],
            },
        }

        with patch(
            "app.services.resource_pool.unified_search.get_site_entry_by_url",
            return_value={
                "site_url": "https://reddit.com/search?q={{q}}",
                "domain": "reddit.com",
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": "https://reddit.com/search?q={{q}}",
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
            },
        ), patch("app.services.resource_pool.unified_search.execute_search_template") as execute:
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        execute.assert_not_called()
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.errors[0]["error"], "site_policy_social_skip")

    def test_unified_search_policy_skips_deprioritized_by_default(self) -> None:
        item = {
            "item_key": "news-search",
            "params": {
                "site_entries": ["https://news.google.com/search?q={{q}}"],
            },
        }

        with patch(
            "app.services.resource_pool.unified_search.get_site_entry_by_url",
            return_value={
                "site_url": "https://news.google.com/search?q={{q}}",
                "domain": "news.google.com",
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": "https://news.google.com/search?q={{q}}",
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
            },
        ), patch("app.services.resource_pool.unified_search.execute_search_template") as execute:
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        execute.assert_not_called()
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.errors[0]["error"], "site_policy_deprioritized_skip")

    def test_unified_search_policy_allows_deprioritized_override(self) -> None:
        item = {
            "item_key": "news-search",
            "params": {
                "site_entries": ["https://news.google.com/search?q={{q}}"],
                "allow_deprioritized_site_entries": True,
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://news.google.com/search?q={{q}}",
                    "domain": "news.google.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://news.google.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://news.google.com/articles/override",
                            matched_by="text",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.9,
                        )
                    ],
                    used_term_fallback=False,
                    diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
                    errors=[],
                ),
            ) as execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        execute.assert_called_once()
        self.assertEqual(result.candidates, ["https://news.google.com/articles/override"])

    def test_unified_search_policy_routes_finextra_search_templates_to_external_search(self) -> None:
        item = {
            "item_key": "finextra-search",
            "params": {
                "site_entries": ["https://www.finextra.com/searchresults.aspx?query={{q}}"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://www.finextra.com/searchresults.aspx?query={{q}}",
                    "domain": "finextra.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://www.finextra.com/searchresults.aspx?query={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch("app.services.resource_pool.unified_search.execute_search_template") as execute_template,
            patch(
                "app.services.resource_pool.unified_search.execute_external_site_search",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://www.finextra.com/blogposting/12345/example-hit",
                            matched_by="text",
                            route_kind="article",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.89,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "external_search", "search_service_fallbacks": 0},
                ),
            ) as execute_external,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["openai api"],
                allow_term_fallback=False,
            )

        execute_template.assert_not_called()
        execute_external.assert_called_once()
        self.assertEqual(result.candidates, ["https://www.finextra.com/blogposting/12345/example-hit"])
        self.assertEqual(result.runtime_diagnostics[0]["site_policy"], "external_preferred")
        self.assertEqual(result.runtime_diagnostics[0]["search_service"], "external_search")

    def test_unified_search_stops_after_priority_wave_reaches_candidate_quota(self) -> None:
        item = {
            "item_key": "priority-wave-search",
            "params": {
                "site_entries": [
                    "https://arxiv.org/search?q={{q}}",
                    "https://www.pymnts.com/?s={{q}}",
                ],
            },
        }

        def _entry_lookup(*, scope: str, project_key: str, site_url: str):
            if "arxiv.org" in site_url:
                return {
                    "site_url": "https://arxiv.org/search?q={{q}}",
                    "domain": "arxiv.org",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://arxiv.org/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                }
            return {
                "site_url": "https://www.pymnts.com/?s={{q}}",
                "domain": "pymnts.com",
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": "https://www.pymnts.com/?s={{q}}",
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
            }

        with (
            patch("app.services.resource_pool.unified_search.get_site_entry_by_url", side_effect=_entry_lookup),
            patch(
                "app.services.resource_pool.unified_search.handle_official_access_api",
                return_value={
                    "candidates": [
                        "https://arxiv.org/abs/2501.00001",
                        "https://arxiv.org/abs/2501.00002",
                    ],
                    "errors": [],
                },
            ) as official,
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://www.pymnts.com/news/artificial-intelligence/2026/03/15/openai-rolls-out-new-agent-tools/",
                            matched_by="title",
                            route_kind="article",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.95,
                        ),
                        SimpleNamespace(
                            url="https://www.pymnts.com/news/artificial-intelligence/2026/03/14/another-openai-api-update/",
                            matched_by="title",
                            route_kind="article",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.94,
                        ),
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
                ),
            ) as execute_template,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["openai api"],
                max_candidates=2,
                allow_term_fallback=False,
            )

        official.assert_called_once()
        execute_template.assert_called_once()
        self.assertEqual(
            result.candidates,
            [
                "https://arxiv.org/abs/2501.00001",
                "https://www.pymnts.com/news/artificial-intelligence/2026/03/15/openai-rolls-out-new-agent-tools/",
            ],
        )

    def test_unified_search_skips_search_template_without_query_placeholder(self) -> None:
        item = {
            "item_key": "broken-search-template",
            "params": {
                "site_entries": ["https://example.com/search"],
                "enable_external_search_fallback": False,
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/search",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://example.com/search",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch("app.services.resource_pool.unified_search.execute_search_template") as execute_template,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["openai api"],
                allow_term_fallback=False,
            )

        execute_template.assert_not_called()
        self.assertEqual(result.candidates, [])
        self.assertEqual(result.errors[0]["error"], "search_template_missing_query_placeholder")
        self.assertEqual(result.errors[0]["error_class"], "invalid_configuration")

    def test_unified_search_external_preferred_degrades_to_browser_candidate_when_empty(self) -> None:
        item = {
            "item_key": "finextra-search",
            "params": {
                "site_entries": ["https://www.finextra.com/searchresults.aspx?query={{q}}"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://www.finextra.com/searchresults.aspx?query={{q}}",
                    "domain": "finextra.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://www.finextra.com/searchresults.aspx?query={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch("app.services.resource_pool.unified_search.execute_search_template") as execute_template,
            patch(
                "app.services.resource_pool.unified_search.execute_external_site_search",
                return_value=SimpleNamespace(
                    selected_candidates=[],
                    used_term_fallback=False,
                    errors=[
                        {
                            "error": "Failed to fetch external_search:site:finextra.com openai api",
                            "error_class": "transport_failure",
                            "recommended_search_service": "browser_candidate",
                        }
                    ],
                    diagnostics={"search_service": "external_search_slowlane", "search_service_fallbacks": 0},
                ),
            ) as execute_external,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["openai api"],
                allow_term_fallback=False,
            )

        execute_template.assert_not_called()
        execute_external.assert_called_once()
        transport_error = result.errors[0]
        self.assertEqual(transport_error["recommended_search_service"], "browser_candidate")
        self.assertTrue(result.runtime_diagnostics[0]["browser_candidate_deferred"])
        self.assertEqual(result.errors[-1]["error"], "browser_candidate_required")
        self.assertEqual(result.errors[-1]["recommended_search_service"], "browser_candidate_deferred")

    def test_unified_search_policy_prefers_entry_remediation_override(self) -> None:
        item = {
            "item_key": "reddit-search",
            "params": {
                "site_entries": ["https://reddit.com/search?q={{q}}"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://reddit.com/search?q={{q}}",
                    "domain": "reddit.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://reddit.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                    "extra": {
                        "remediation": {
                            "status": "parser_enhance",
                            "reason": "Manual remediation keeps site in search pipeline.",
                            "preferred_search_service": "resilient",
                            "implementation_hint": "search_template_parser_enhance",
                        }
                    },
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://reddit.com/r/example/comments/1",
                            matched_by="text",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.85,
                        )
                    ],
                    used_term_fallback=False,
                    diagnostics={"search_service": "resilient", "search_service_fallbacks": 0},
                    errors=[],
                ),
            ) as execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        execute.assert_called_once()
        self.assertEqual(result.candidates, ["https://reddit.com/r/example/comments/1"])
        self.assertEqual(result.runtime_diagnostics[0]["site_policy"], "parser_enhance")
        self.assertEqual(result.runtime_diagnostics[0]["search_service"], "resilient")

    def test_unified_search_search_template_uses_domain_adapter_overrides(self) -> None:
        item = {
            "item_key": "pymnts-search",
            "params": {
                "site_entries": ["https://www.pymnts.com/?s={{q}}"],
                "enable_external_search_fallback": True,
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://www.pymnts.com/?s={{q}}",
                    "domain": "pymnts.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://www.pymnts.com/?s={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://www.pymnts.com/news/artificial-intelligence/2026/03/15/openai-rolls-out-new-agent-tools/",
                            matched_by="text",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.92,
                            route_kind="article",
                        )
                    ],
                    used_term_fallback=False,
                    diagnostics={"search_service": "resilient", "search_service_fallbacks": 0},
                    errors=[],
                ),
            ) as execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["openai api"],
                allow_term_fallback=False,
            )

        self.assertEqual(result.candidates, ["https://www.pymnts.com/news/artificial-intelligence/2026/03/15/openai-rolls-out-new-agent-tools/"])
        self.assertEqual(execute.call_args.kwargs["params"]["parser_profile"], "site_adaptive.pymnts_card")
        self.assertEqual(execute.call_args.kwargs["params"]["search_service"], "resilient")
        self.assertFalse(execute.call_args.kwargs["params"]["enable_external_search_fallback"])
        self.assertEqual(result.runtime_diagnostics[0]["search_template_adapter"], "search_template.pymnts_card")

    def test_unified_search_payload_uses_shared_search_template_service(self) -> None:
        item = {
            "item_key": "search-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
                "enable_external_search_fallback": False,
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://example.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    template="https://example.com/search?q={{q}}",
                    search_urls=["https://example.com/search?q=robotics"],
                    pages_scanned=1,
                    raw_candidates=[],
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/posts/robotics-guide",
                            matched_by="text",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.92,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"pages_scanned": 1},
                ),
            ) as execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        execute.assert_called_once()
        self.assertEqual(result.candidates, ["https://example.com/posts/robotics-guide"])
        self.assertEqual(len(result.site_entries_used), 1)

    def test_unified_search_payload_exposes_search_template_parser_diagnostics(self) -> None:
        item = {
            "item_key": "search-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
                "enable_external_search_fallback": False,
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://example.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    template="https://example.com/search?q={{q}}",
                    search_urls=["https://example.com/search?q=robotics"],
                    pages_scanned=1,
                    raw_candidates=[],
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/posts/robotics-guide",
                            matched_by="text",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.92,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={
                        "pages_scanned": 1,
                        "search_service": "basic",
                        "parser_container_hit": 3,
                        "parser_structured_hit": 1,
                        "parser_json_ld_hit": 2,
                        "parser_global_anchor_hit": 4,
                        "parser_candidate_rejected_low_value": 7,
                    },
                ),
            ),
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        entry = result.runtime_diagnostics[0]
        self.assertEqual(entry["parser_container_hit"], 3)
        self.assertEqual(entry["parser_structured_hit"], 1)
        self.assertEqual(entry["parser_json_ld_hit"], 2)
        self.assertEqual(entry["parser_global_anchor_hit"], 4)
        self.assertEqual(entry["parser_candidate_rejected_low_value"], 7)
        self.assertEqual(result.site_entries_used[0]["entry_type"], "search_template")
        self.assertNotIn("parser_container_hit", result.site_entries_used[0])

    def test_unified_search_prefers_persisted_search_contract_profile(self) -> None:
        item = {
            "item_key": "search-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://example.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                    "extra": {
                        "search_contract_profile": {
                            "best_template": "https://example.com/?s={{q}}",
                            "best_suffix": "pricing",
                        }
                    },
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    template="https://example.com/?s={{q}}",
                    search_urls=["https://example.com/?s=robotics+pricing"],
                    pages_scanned=1,
                    raw_candidates=[],
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/posts/pricing-guide",
                            matched_by="text",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.95,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
                ),
            ) as execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        self.assertEqual(result.candidates, ["https://example.com/posts/pricing-guide"])
        self.assertEqual(execute.call_args.kwargs["template"], "https://example.com/?s={{q}}")
        self.assertEqual(execute.call_args.kwargs["query_terms"], ["robotics pricing"])

    def test_unified_search_payload_uses_external_search_fallback_for_keep_sites(self) -> None:
        item = {
            "item_key": "search-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://example.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    template="https://example.com/search?q={{q}}",
                    search_urls=["https://example.com/search?q=robotics"],
                    pages_scanned=1,
                    raw_candidates=[],
                    selected_candidates=[],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
                ),
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_external_site_search",
                return_value=SimpleNamespace(
                    template="external_search:site:example.com robotics",
                    search_urls=["external_search:site:example.com robotics"],
                    pages_scanned=1,
                    raw_candidates=[],
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/posts/external-hit",
                            matched_by="text",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.91,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "external_search", "search_service_fallbacks": 0},
                ),
            ) as external_execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        external_execute.assert_called_once()
        self.assertEqual(result.candidates, ["https://example.com/posts/external-hit"])
        self.assertEqual(result.runtime_diagnostics[0]["search_service"], "external_search")
        self.assertEqual(result.errors[0]["error"], "external_search_fallback_used")

    def test_unified_search_marks_browser_candidate_deferred_when_keep_site_still_empty(self) -> None:
        item = {
            "item_key": "search-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://example.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    template="https://example.com/search?q={{q}}",
                    search_urls=["https://example.com/search?q=robotics"],
                    pages_scanned=1,
                    raw_candidates=[],
                    selected_candidates=[],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
                ),
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_external_site_search",
                return_value=SimpleNamespace(
                    template="external_search:site:example.com robotics",
                    search_urls=["external_search:site:example.com robotics"],
                    pages_scanned=1,
                    raw_candidates=[],
                    selected_candidates=[],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "external_search_slowlane", "search_service_fallbacks": 0},
                ),
            ),
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        self.assertEqual(result.candidates, [])
        self.assertTrue(result.runtime_diagnostics[0]["browser_candidate_deferred"])
        self.assertEqual(result.errors[-1]["error"], "browser_candidate_required")
        self.assertEqual(result.errors[-1]["next_step"], "slow_lane_deferred")

    def test_unified_search_payload_applies_policy_preferred_search_service(self) -> None:
        item = {
            "item_key": "news-search",
            "params": {
                "site_entries": ["https://news.google.com/search?q={{q}}"],
                "allow_deprioritized_site_entries": True,
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://news.google.com/search?q={{q}}",
                    "domain": "news.google.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://news.google.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    template="https://news.google.com/search?q={{q}}",
                    search_urls=["https://news.google.com/search?q=robotics"],
                    pages_scanned=1,
                    raw_candidates=[],
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://news.google.com/articles/override",
                            matched_by="text",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.9,
                        )
                    ],
                    used_term_fallback=False,
                    diagnostics={"search_service": "resilient", "search_service_fallbacks": 0},
                    errors=[],
                ),
            ) as execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        self.assertEqual(result.candidates, ["https://news.google.com/articles/override"])
        self.assertEqual(result.runtime_diagnostics[0]["search_service"], "resilient")
        self.assertEqual(execute.call_args.kwargs["params"]["search_service"], "resilient")

    def test_unified_search_payload_preserves_structured_search_template_errors(self) -> None:
        item = {
            "item_key": "search-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
                "enable_external_search_fallback": False,
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://example.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    template="https://example.com/search?q={{q}}",
                    search_urls=["https://example.com/search?q=robotics"],
                    pages_scanned=1,
                    raw_candidates=[],
                    selected_candidates=[],
                    used_term_fallback=False,
                    diagnostics={"search_service": "resilient", "search_service_fallbacks": 1},
                    errors=[
                        {
                            "error": "429 Client Error",
                            "error_class": "transport_failure",
                            "search_url": "https://example.com/search?q=robotics",
                            "recommended_search_service": "resilient",
                        }
                    ],
                ),
            ),
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        transport_error = next(row for row in result.errors if row.get("error") == "429 Client Error")
        self.assertEqual(transport_error["error_class"], "transport_failure")
        self.assertEqual(transport_error["search_service_used"], "resilient")
        self.assertEqual(transport_error["recommended_search_service"], "resilient")

    def test_unified_search_payload_uses_shared_feed_probe(self) -> None:
        item = {
            "item_key": "rss-item",
            "params": {
                "site_entries": ["https://example.com/feed.xml"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/feed.xml",
                    "domain": "example.com",
                    "entry_type": "rss",
                    "channel_key": "generic_web.rss",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "filter"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_feed_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/posts/rss-guide",
                            matched_by="text",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.88,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ) as execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        execute.assert_called_once()
        self.assertEqual(result.candidates, ["https://example.com/posts/rss-guide"])

    def test_unified_search_payload_uses_shared_sitemap_probe(self) -> None:
        item = {
            "item_key": "sitemap-item",
            "params": {
                "site_entries": ["https://example.com/sitemap.xml"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/sitemap.xml",
                    "domain": "example.com",
                    "entry_type": "sitemap",
                    "channel_key": "generic_web.sitemap",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "filter"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_sitemap_probe",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/posts/sitemap-guide",
                            matched_by="title_hint",
                            candidate_quality="medium",
                            usable_for_search=True,
                            score=0.71,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                ),
            ) as execute,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=False,
            )

        execute.assert_called_once()
        self.assertEqual(result.candidates, ["https://example.com/posts/sitemap-guide"])

    def test_unified_search_payload_write_to_pool_backfills_traceable_source_ref_fields(self) -> None:
        item = {
            "item_key": "pool-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_type": "search_template",
                    "channel_key": "generic_web.search_template",
                    "template": "https://example.com/search?q={{q}}",
                    "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                },
            ),
            patch(
                "app.services.resource_pool.unified_search.execute_search_template",
                return_value=SimpleNamespace(
                    selected_candidates=[
                        SimpleNamespace(
                            url="https://example.com/posts/openai-market-map",
                            matched_by="title",
                            route_kind="article",
                            candidate_quality="high",
                            usable_for_search=True,
                            score=0.93,
                        )
                    ],
                    used_term_fallback=False,
                    errors=[],
                    diagnostics={"search_service": "basic", "search_service_fallbacks": 0},
                ),
            ),
            patch("app.services.resource_pool.unified_search.append_url", return_value=True) as append,
        ):
            result = unified_search_by_item_payload(
                project_key="demo",
                item=item,
                query_terms=["OpenAI market map"],
                write_to_pool=True,
            )

        self.assertEqual(result.written, {"urls_new": 1, "urls_skipped": 0})
        append.assert_called_once()
        source_ref = append.call_args.kwargs["source_ref"]
        self.assertEqual(source_ref["item_key"], "pool-item")
        self.assertEqual(source_ref["query_terms"], ["OpenAI market map"])
        self.assertEqual(source_ref["site_entry_url"], "https://example.com/search?q={{q}}")
        self.assertEqual(source_ref["entry_type"], "search_template")
        self.assertEqual(source_ref["entry_domain"], "example.com")
        self.assertEqual(source_ref["domain"], "example.com")


if __name__ == "__main__":
    unittest.main()
