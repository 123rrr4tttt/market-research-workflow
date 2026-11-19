from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.resource_pool.search_capabilities import make_search_candidate
from app.services.resource_pool.search_capabilities import normalize_match_text
from app.services.resource_pool.search_capabilities import select_search_candidates


class ResourcePoolSearchCapabilitiesUnitTestCase(unittest.TestCase):
    def test_normalize_match_text_collapses_punctuation(self) -> None:
        self.assertEqual(normalize_match_text("Meta Ray-Ban"), "meta ray ban")

    def test_select_search_candidates_prefers_article_over_search_self_link(self) -> None:
        candidates = [
            make_search_candidate(
                url="https://example.com/search?q=Humane+AI+Pin",
                strategy="search_template",
                title="Skip to content",
                text="Skip to content",
                source_url="https://example.com/search?q=Humane+AI+Pin",
                entry_domain="example.com",
            ),
            make_search_candidate(
                url="https://example.com/posts/humane-ai-pin-review",
                strategy="search_template",
                title="Humane AI Pin review",
                text="Humane AI Pin review",
                source_url="https://example.com/search?q=Humane+AI+Pin",
                entry_domain="example.com",
            ),
        ]

        selected, used_fallback = select_search_candidates(
            [item for item in candidates if item is not None],
            ["Humane AI Pin"],
            allow_fallback=False,
        )

        self.assertFalse(used_fallback)
        self.assertEqual([item.url for item in selected], ["https://example.com/posts/humane-ai-pin-review"])
        self.assertEqual(selected[0].matched_by, "title")
        self.assertTrue(selected[0].usable_for_search)

    def test_select_search_candidates_uses_rss_title_match(self) -> None:
        candidates = [
            make_search_candidate(
                url="https://example.com/posts/123",
                strategy="rss",
                title="Humane AI Pin review",
                text="Latest wearable coverage",
                source_url="https://example.com/feed",
                entry_domain="example.com",
            ),
            make_search_candidate(
                url="https://example.com/posts/456",
                strategy="rss",
                title="Weekly roundup",
                text="General news",
                source_url="https://example.com/feed",
                entry_domain="example.com",
            ),
        ]

        selected, used_fallback = select_search_candidates(
            [item for item in candidates if item is not None],
            ["Humane AI Pin"],
            allow_fallback=False,
        )

        self.assertFalse(used_fallback)
        self.assertEqual([item.url for item in selected], ["https://example.com/posts/123"])
        self.assertEqual(selected[0].matched_by, "title")

    def test_select_search_candidates_uses_sitemap_title_hint(self) -> None:
        candidates = [
            make_search_candidate(
                url="https://example.com/posts/humane-ai-pin-review",
                strategy="sitemap",
                source_url="https://example.com/sitemap.xml",
                entry_domain="example.com",
            ),
            make_search_candidate(
                url="https://example.com/posts/weekly-roundup",
                strategy="sitemap",
                source_url="https://example.com/sitemap.xml",
                entry_domain="example.com",
            ),
        ]

        selected, used_fallback = select_search_candidates(
            [item for item in candidates if item is not None],
            ["Humane AI Pin"],
            allow_fallback=False,
        )

        self.assertFalse(used_fallback)
        self.assertEqual([item.url for item in selected], ["https://example.com/posts/humane-ai-pin-review"])
        self.assertEqual(selected[0].matched_by, "title_hint")

    def test_make_search_candidate_infers_generic_route_kind(self) -> None:
        candidate = make_search_candidate(
            url="https://example.com/topic/ai",
            strategy="search_template",
            title="AI",
            source_url="https://example.com/search?q=ai",
            entry_domain="example.com",
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.extra["route_kind"], "section")

    def test_select_search_candidates_applies_route_kind_bonus(self) -> None:
        candidates = [
            make_search_candidate(
                url="https://example.com/topic/openai",
                strategy="search_template",
                title="OpenAI",
                text="OpenAI",
                source_url="https://example.com/search?q=openai",
                entry_domain="example.com",
            ),
            make_search_candidate(
                url="https://example.com/news/2026/03/24/openai-update",
                strategy="search_template",
                title="OpenAI",
                text="OpenAI",
                source_url="https://example.com/search?q=openai",
                entry_domain="example.com",
            ),
        ]

        selected, used_fallback = select_search_candidates(
            [item for item in candidates if item is not None],
            ["OpenAI"],
            allow_fallback=False,
        )

        self.assertFalse(used_fallback)
        self.assertEqual(selected[0].route_kind, "article")
        self.assertGreater(selected[0].score, selected[1].score)

    def test_select_search_candidates_accepts_json_scoring_config(self) -> None:
        candidates = [
            make_search_candidate(
                url="https://example.com/topic/openai",
                strategy="search_template",
                title="OpenAI",
                text="OpenAI",
                source_url="https://example.com/search?q=openai",
                entry_domain="example.com",
            ),
            make_search_candidate(
                url="https://example.com/news/2026/03/24/openai-update",
                strategy="search_template",
                title="OpenAI",
                text="OpenAI",
                source_url="https://example.com/search?q=openai",
                entry_domain="example.com",
            ),
        ]

        selected, used_fallback = select_search_candidates(
            [item for item in candidates if item is not None],
            ["OpenAI"],
            allow_fallback=False,
            scoring_config='{"route_kind_bonus":{"section":0.3,"article":0.0}}',
        )

        self.assertFalse(used_fallback)
        self.assertEqual(selected[0].route_kind, "section")
        self.assertGreater(selected[0].score, selected[1].score)

    def test_select_search_candidates_accepts_threshold_override(self) -> None:
        candidates = [
            make_search_candidate(
                url="https://example.com/topic/openai",
                strategy="search_template",
                title="OpenAI",
                text="OpenAI",
                source_url="https://example.com/search?q=openai",
                entry_domain="example.com",
            )
        ]

        selected, used_fallback = select_search_candidates(
            [item for item in candidates if item is not None],
            ["OpenAI"],
            allow_fallback=False,
            scoring_config={"thresholds": {"search_template": 1.05}},
        )

        self.assertTrue(used_fallback)
        self.assertEqual(selected, [])


if __name__ == "__main__":
    unittest.main()
