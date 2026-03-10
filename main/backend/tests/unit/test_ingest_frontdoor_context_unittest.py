from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest import market_web as market_web_module
    from app.services.ingest import news as news_module

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _FakeQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return None


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def query(self, *_args, **_kwargs):
        return _FakeQuery()

    def add(self, *_args, **_kwargs):
        return None

    def flush(self):
        return None

    def commit(self):
        return None

    def expunge_all(self):
        return None


class IngestFrontdoorContextUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest frontdoor context tests require backend dependencies: {_IMPORT_ERROR}")

    def test_news_dispatch_links_to_single_url_enables_frontdoor_by_default(self):
        captured: dict = {}

        def _fake_collect(urls, *, project_key=None, query_terms=None, extra_params=None, enable_extraction=True):
            captured["urls"] = list(urls)
            captured["project_key"] = project_key
            captured["query_terms"] = list(query_terms or [])
            captured["extra_params"] = dict(extra_params or {})
            captured["enable_extraction"] = bool(enable_extraction)
            return {"inserted": 1, "inserted_valid": 1, "skipped": 0, "queued": 0}

        with patch("app.services.ingest.url_pool.collect_urls_from_list", side_effect=_fake_collect), patch.object(
            news_module, "current_project_key", return_value="demo_proj"
        ):
            result = news_module._dispatch_links_to_single_url(
                links=["https://example.com/news/1"],
                query_terms=["market"],
            )

        self.assertEqual(result.get("inserted"), 1)
        self.assertEqual(captured["project_key"], "demo_proj")
        self.assertEqual(captured["query_terms"], ["market"])
        self.assertTrue(captured["enable_extraction"])
        self.assertEqual(captured["extra_params"].get("single_url_frontdoor_enabled"), True)
        self.assertEqual(captured["extra_params"].get("front_door_owner"), "ingest.news")
        self.assertEqual(captured["extra_params"].get("frontdoor_route_decision"), "front_door_url_routing")
        self.assertEqual(captured["extra_params"].get("frontdoor_write_mode"), "front_door_url_routing")
        self.assertEqual(captured["extra_params"].get("frontdoor_execution_mode"), "url_routing")

    def test_market_web_routed_fetch_enables_frontdoor_and_passes_route_context(self):
        captured: dict = {}

        def _fake_collect(urls, *, project_key=None, query_terms=None, extra_params=None, enable_extraction=True):
            captured["urls"] = list(urls)
            captured["project_key"] = project_key
            captured["query_terms"] = list(query_terms or [])
            captured["extra_params"] = dict(extra_params or {})
            captured["enable_extraction"] = bool(enable_extraction)
            return {"inserted": 0, "inserted_valid": 0, "skipped": 1, "queued": 0}

        with patch.object(market_web_module, "start_job", return_value=1), patch.object(
            market_web_module, "complete_job"
        ), patch.object(
            market_web_module, "search_sources", return_value=[{"link": "https://example.com/post/1", "title": "t", "snippet": "s"}]
        ), patch.object(
            market_web_module, "fetch_html", return_value=("<html><body></body></html>", None)
        ), patch.object(
            market_web_module, "_extract_text_from_html", return_value=""
        ), patch.object(
            market_web_module, "SessionLocal", return_value=_FakeSession()
        ), patch.object(
            market_web_module, "_get_or_create_source", return_value=SimpleNamespace(id=123)
        ), patch.object(
            market_web_module, "collect_urls_from_list", side_effect=_fake_collect
        ), patch.object(
            market_web_module, "current_project_key", return_value="demo_proj"
        ), patch.object(
            market_web_module, "build_display_meta", return_value={}
        ):
            result = market_web_module.collect_market_info(
                keywords=["ev"],
                limit=1,
                enable_extraction=False,
            )

        self.assertEqual(result.get("body_fetch_routed_urls"), 1)
        self.assertEqual(captured["project_key"], "demo_proj")
        self.assertEqual(captured["query_terms"], ["ev"])
        self.assertEqual(captured["enable_extraction"], False)
        self.assertEqual(captured["extra_params"].get("single_url_frontdoor_enabled"), True)
        self.assertEqual(captured["extra_params"].get("front_door_owner"), "ingest.market_web")
        self.assertEqual(captured["extra_params"].get("frontdoor_route_decision"), "front_door_url_routing")
        self.assertEqual(captured["extra_params"].get("frontdoor_write_mode"), "front_door_url_routing")
        self.assertEqual(captured["extra_params"].get("frontdoor_execution_mode"), "url_routing")


if __name__ == "__main__":
    unittest.main()
