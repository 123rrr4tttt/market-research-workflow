from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.source_library.adapters.generic_web import (
    handle_generic_web_rss,
    handle_generic_web_search_template,
    handle_generic_web_sitemap,
)

pytestmark = pytest.mark.unit


class GenericWebSearchTemplateAdapterUnitTestCase(unittest.TestCase):
    def test_rss_adapter_delegates_to_shared_feed_probe(self) -> None:
        with patch("app.services.source_library.adapters.generic_web.execute_feed_probe") as execute:
            execute.return_value = SimpleNamespace(
                selected_candidates=[type("Decision", (), {"url": "https://example.com/posts/rss-item"})()],
                used_term_fallback=False,
                pages_scanned=1,
                diagnostics={"raw_candidates": 1},
                errors=[],
            )
            result = handle_generic_web_rss(
                {
                    "feed_url": "https://example.com/feed.xml",
                    "query_terms": ["robotics"],
                },
                project_key=None,
            )

        execute.assert_called_once()
        self.assertEqual(result["candidates"], ["https://example.com/posts/rss-item"])

    def test_sitemap_adapter_delegates_to_shared_sitemap_probe(self) -> None:
        with patch("app.services.source_library.adapters.generic_web.execute_sitemap_probe") as execute:
            execute.return_value = SimpleNamespace(
                selected_candidates=[type("Decision", (), {"url": "https://example.com/posts/sitemap-item"})()],
                used_term_fallback=False,
                pages_scanned=1,
                diagnostics={"raw_candidates": 1},
                errors=[],
            )
            result = handle_generic_web_sitemap(
                {
                    "sitemap_url": "https://example.com/sitemap.xml",
                    "query_terms": ["robotics"],
                },
                project_key=None,
            )

        execute.assert_called_once()
        self.assertEqual(result["candidates"], ["https://example.com/posts/sitemap-item"])

    def test_search_template_uses_text_matching_and_multi_page_fetch(self) -> None:
        with patch("app.services.source_library.adapters.generic_web.execute_search_template") as execute:
            execute.return_value = SimpleNamespace(
                template="https://example.com/search?query={{q}}",
                search_urls=[
                    "https://example.com/search?query=Alpha+Beta",
                    "https://example.com/search?query=Alpha+Beta&page=2",
                ],
                pages_scanned=2,
                raw_candidates=[],
                selected_candidates=[
                    type("Decision", (), {"url": "https://example.com/posts/123"})(),
                    type("Decision", (), {"url": "https://example.com/posts/456"})(),
                ],
                used_term_fallback=False,
                errors=[],
                diagnostics={"pages_scanned": 2},
            )
            result = handle_generic_web_search_template(
                {
                    "template": "https://example.com/search?query={{q}}",
                    "query_terms": ["Alpha", "Beta"],
                    "page": 1,
                    "max_pages": 2,
                },
                project_key=None,
            )

        execute.assert_called_once()
        self.assertEqual(
            set(result["candidates"]),
            {
                "https://example.com/posts/123",
                "https://example.com/posts/456",
            },
        )
        self.assertFalse(result["used_term_fallback"])
        self.assertEqual(result["pages_scanned"], 2)

    def test_search_template_returns_empty_when_fallback_disabled_and_no_match(self) -> None:
        with patch("app.services.source_library.adapters.generic_web.execute_search_template") as execute:
            execute.return_value = SimpleNamespace(
                template="https://example.com/search?q={{q}}",
                search_urls=["https://example.com/search?q=robotics"],
                pages_scanned=1,
                raw_candidates=[],
                selected_candidates=[],
                used_term_fallback=True,
                errors=[],
                diagnostics={"raw_candidates": 0},
            )
            result = handle_generic_web_search_template(
                {
                    "template": "https://example.com/search?q={{q}}",
                    "query_terms": ["robotics"],
                    "allow_term_fallback": False,
                },
                project_key=None,
            )

        execute.assert_called_once()
        self.assertEqual(result["candidates"], [])
        self.assertTrue(result["used_term_fallback"])
        self.assertEqual(result["pages_scanned"], 1)

    def test_write_to_pool_uses_traceable_source_ref_shape(self) -> None:
        with (
            patch("app.services.source_library.adapters.generic_web.execute_search_template") as execute,
            patch("app.services.source_library.adapters.generic_web.append_url", return_value=True) as append,
        ):
            execute.return_value = SimpleNamespace(
                template="https://example.com/search?q={{q}}",
                search_urls=["https://example.com/search?q=robotics"],
                pages_scanned=1,
                raw_candidates=[],
                selected_candidates=[type("Decision", (), {"url": "https://example.com/posts/robotics-1"})()],
                used_term_fallback=False,
                errors=[],
                diagnostics={"raw_candidates": 1},
            )
            handle_generic_web_search_template(
                {
                    "template": "https://example.com/search?q={{q}}",
                    "query_terms": ["robotics"],
                    "write_to_pool": True,
                    "_source_library_item": {
                        "item_key": "handler.cluster.search_template",
                        "channel_key": "handler.cluster",
                        "item_type": "service_aggregated",
                        "managed_by": "system",
                        "extra": {"expected_entry_type": "search_template"},
                    },
                },
                project_key="demo_proj",
            )

        source_ref = append.call_args.kwargs["source_ref"]
        self.assertEqual(source_ref["tool"], "generic_web_search_template")
        self.assertEqual(source_ref["query_terms"], ["robotics"])
        self.assertEqual(source_ref["locator"], "https://example.com/posts/robotics-1")
        self.assertEqual(source_ref["url"], "https://example.com/posts/robotics-1")
        self.assertEqual(source_ref["domain"], "example.com")
        self.assertEqual(source_ref["entrypoint"], "source_library.generic_web_search_template")
        self.assertEqual(source_ref["source_mode"], "generic_web_search_template")
        self.assertEqual(source_ref["project_key"], "demo_proj")
        self.assertEqual(source_ref["item_key"], "handler.cluster.search_template")
        self.assertEqual(source_ref["channel_key"], "handler.cluster")
        self.assertEqual(source_ref["item_type"], "service_aggregated")
        self.assertEqual(source_ref["managed_by"], "system")
        self.assertEqual(source_ref["entry_type"], "search_template")
        self.assertEqual(source_ref["source_family"], "generic_web")

    def test_search_template_reports_capability_profile_and_taxonomy(self) -> None:
        with patch("app.services.source_library.adapters.generic_web.execute_search_template") as execute:
            execute.return_value = SimpleNamespace(
                template="https://example.com/search?q={{q}}",
                search_urls=["https://example.com/search?q=robotics"],
                pages_scanned=1,
                raw_candidates=[],
                selected_candidates=[type("Decision", (), {"url": "https://example.com/posts/robotics-1"})()],
                used_term_fallback=False,
                errors=[],
                diagnostics={"raw_candidates": 1},
            )
            result = handle_generic_web_search_template(
                {
                    "template": "https://example.com/search?q={{q}}",
                    "query_terms": ["robotics"],
                    "_source_library_item": {
                        "item_key": "handler.cluster.search_template",
                        "item_type": "service_aggregated",
                        "managed_by": "system",
                    },
                },
                project_key="demo_proj",
            )

        self.assertEqual(result["source_mode"], "site_search")
        self.assertEqual(result["capability_profile"]["entry_type"], "search_template")
        self.assertTrue(result["capability_profile"]["supports_pagination"])
        self.assertEqual(result["adapter_taxonomy"]["lane"], "site_search_internal_adapter")
        self.assertTrue(result["adapter_taxonomy"]["internal_adapter_only"])
        self.assertEqual(result["adapter_taxonomy"]["item_type"], "service_aggregated")
        self.assertEqual(result["capability_profile"]["fallback_policy"], "term_match_then_search_template_fallback")

    def test_search_template_surfaces_filter_fallback_diagnostics(self) -> None:
        with patch("app.services.source_library.adapters.generic_web.execute_search_template") as execute:
            execute.return_value = SimpleNamespace(
                template="https://example.com/search?q={{q}}",
                search_urls=["https://example.com/search?q=robotics"],
                pages_scanned=1,
                raw_candidates=[],
                selected_candidates=[],
                used_term_fallback=True,
                errors=[],
                diagnostics={
                    "raw_candidates": 1,
                    "selected_candidates": 0,
                    "fallback_allowed": False,
                    "used_term_fallback": True,
                    "candidate_filter_state": "term_filter_empty_no_fallback",
                },
            )
            result = handle_generic_web_search_template(
                {
                    "template": "https://example.com/search?q={{q}}",
                    "query_terms": ["robotics"],
                    "allow_term_fallback": False,
                },
                project_key=None,
            )

        execute.assert_called_once()
        self.assertEqual(result["candidates"], [])
        self.assertTrue(result["used_term_fallback"])
        self.assertEqual(result["diagnostics"]["candidate_filter_state"], "term_filter_empty_no_fallback")
        self.assertFalse(result["diagnostics"]["fallback_allowed"])


if __name__ == "__main__":
    unittest.main()
