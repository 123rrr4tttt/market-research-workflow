from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.resource_pool import unified_search

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class UnifiedSearchEntryTypeFallbackUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"unified_search tests require backend dependencies: {_IMPORT_ERROR}")

    def test_entry_type_mismatch_uses_fallback_by_default(self):
        item = {
            "item_key": "handler.cluster.search_template",
            "params": {
                "site_entries": ["https://example.com/sitemap.xml"],
                "expected_entry_type": "search_template",
            },
        }

        with (
            patch(
                "app.services.resource_pool.unified_search.get_site_entry_by_url",
                return_value={
                    "site_url": "https://example.com/sitemap.xml",
                    "domain": "example.com",
                    "entry_type": "sitemap",
                },
            ),
            patch(
                "app.services.resource_pool.unified_search._collect_sitemap_urls",
                return_value=[
                    "https://example.com/news/ai-launch",
                    "https://example.com/login",
                ],
            ),
            patch(
                "app.services.resource_pool.unified_search._filter_urls_by_terms_with_fallback",
                return_value=(["https://example.com/news/ai-launch", "https://example.com/login"], False),
            ),
        ):
            result = unified_search.unified_search_by_item_payload(
                project_key="demo_proj",
                item=item,
                query_terms=["ai"],
                allow_entry_type_fallback=True,
            )

        self.assertEqual(result.candidates, ["https://example.com/news/ai-launch"])
        self.assertEqual(int(result.stats.get("entry_type_mismatch") or 0), 1)
        self.assertEqual(int(result.stats.get("entry_type_mismatch_fallback_used") or 0), 1)
        self.assertEqual(int(result.stats.get("low_value_drop") or 0), 1)

    def test_entry_type_mismatch_respects_strict_mode(self):
        item = {
            "item_key": "handler.cluster.search_template",
            "params": {
                "site_entries": ["https://example.com/sitemap.xml"],
                "expected_entry_type": "search_template",
            },
        }

        with patch(
            "app.services.resource_pool.unified_search.get_site_entry_by_url",
            return_value={
                "site_url": "https://example.com/sitemap.xml",
                "domain": "example.com",
                "entry_type": "sitemap",
            },
        ):
            result = unified_search.unified_search_by_item_payload(
                project_key="demo_proj",
                item=item,
                query_terms=["ai"],
                allow_entry_type_fallback=False,
            )

        self.assertEqual(result.candidates, [])
        self.assertEqual(int(result.stats.get("entry_type_mismatch") or 0), 1)
        self.assertEqual(int(result.stats.get("entry_type_mismatch_fallback_used") or 0), 0)
        self.assertTrue(any("entry_type mismatch" in str(err.get("error") or "") for err in result.errors))


if __name__ == "__main__":
    unittest.main()

