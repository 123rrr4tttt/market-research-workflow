from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_select_search_candidates_uses_llm_semantic_terms_when_literal_match_misses(self) -> None:
        candidates = [
            make_search_candidate(
                url="https://docs.github.com/en/copilot/concepts/agents/openai-codex",
                strategy="search_template",
                title="OpenAI Codex",
                text="Agent workflow in GitHub Copilot",
                source_url="https://docs.github.com/search?query=openai+api",
                entry_domain="docs.github.com",
            ),
            make_search_candidate(
                url="https://docs.github.com/en/rest/models/inference",
                strategy="search_template",
                title="REST API endpoints for models inference",
                text="Model inference endpoints",
                source_url="https://docs.github.com/search?query=openai+api",
                entry_domain="docs.github.com",
            ),
        ]

        with patch(
            "app.services.resource_pool.search_capabilities._expand_semantic_query_terms_with_llm",
            return_value=["openai codex", "model inference api"],
        ) as expand:
            selected, used_fallback = select_search_candidates(
                [item for item in candidates if item is not None],
                ["openai api"],
                allow_fallback=False,
            )

        expand.assert_called_once()
        self.assertFalse(used_fallback)
        self.assertEqual([item.url for item in selected], ["https://docs.github.com/en/copilot/concepts/agents/openai-codex"])
        self.assertEqual(selected[0].matched_by, "semantic_title")
        self.assertTrue(selected[0].usable_for_search)

    def test_select_search_candidates_skips_llm_semantic_expansion_when_literal_match_exists(self) -> None:
        candidates = [
            make_search_candidate(
                url="https://example.com/posts/openai-api-guide",
                strategy="search_template",
                title="OpenAI API guide",
                text="OpenAI API guide",
                source_url="https://example.com/search?q=openai+api",
                entry_domain="example.com",
            ),
        ]

        with patch(
            "app.services.resource_pool.search_capabilities._expand_semantic_query_terms_with_llm",
            return_value=["developer platform"],
        ) as expand:
            selected, used_fallback = select_search_candidates(
                [item for item in candidates if item is not None],
                ["openai api"],
                allow_fallback=False,
            )

        expand.assert_not_called()
        self.assertFalse(used_fallback)
        self.assertEqual([item.url for item in selected], ["https://example.com/posts/openai-api-guide"])
        self.assertEqual(selected[0].matched_by, "title")

    def test_select_search_candidates_uses_llm_candidate_selection_when_expansion_still_misses(self) -> None:
        candidates = [
            make_search_candidate(
                url="https://docs.github.com/en/copilot/concepts/agents/openai-codex",
                strategy="search_template",
                title="OpenAI Codex",
                text="Agent workflow in GitHub Copilot",
                source_url="https://docs.github.com/search?query=openai+api",
                entry_domain="docs.github.com",
            ),
            make_search_candidate(
                url="https://docs.github.com/en/rest/models/inference",
                strategy="search_template",
                title="REST API endpoints for models inference",
                text="Model inference endpoints",
                source_url="https://docs.github.com/search?query=openai+api",
                entry_domain="docs.github.com",
            ),
        ]

        with patch(
            "app.services.resource_pool.search_capabilities._expand_semantic_query_terms_with_llm",
            return_value=["openai api documentation", "openai api endpoints"],
        ) as expand, patch(
            "app.services.resource_pool.search_capabilities._select_candidates_with_llm",
        ) as llm_pick:
            llm_pick.side_effect = lambda **kwargs: [
                next(item for item in kwargs["scored_candidates"] if item.url.endswith("/openai-codex")).__class__(
                    url="https://docs.github.com/en/copilot/concepts/agents/openai-codex",
                    strategy="search_template",
                    fetchability="direct",
                    matched_by="llm_semantic",
                    route_kind="page",
                    candidate_quality="medium",
                    score=0.74,
                    usable_for_search=True,
                    reasons=("matched:llm_semantic",),
                    text="Agent workflow in GitHub Copilot",
                    title="OpenAI Codex",
                )
            ]
            selected, used_fallback = select_search_candidates(
                [item for item in candidates if item is not None],
                ["openai api"],
                allow_fallback=False,
            )

        expand.assert_called_once()
        llm_pick.assert_called_once()
        self.assertFalse(used_fallback)
        self.assertEqual([item.url for item in selected], ["https://docs.github.com/en/copilot/concepts/agents/openai-codex"])
        self.assertEqual(selected[0].matched_by, "llm_semantic")
        self.assertTrue(selected[0].usable_for_search)


if __name__ == "__main__":
    unittest.main()
