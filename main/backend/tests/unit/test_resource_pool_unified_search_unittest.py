from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.resource_pool.unified_search import _normalize_search_template_placeholders
from app.services.resource_pool.unified_search import _filter_link_candidates_by_terms_with_fallback


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


if __name__ == "__main__":
    unittest.main()
