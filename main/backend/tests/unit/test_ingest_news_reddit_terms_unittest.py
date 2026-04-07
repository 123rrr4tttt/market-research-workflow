from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.ingest import news
from app.services.ingest.adapters.news_google import GoogleNewsItem
from app.services.ingest.adapters.social_reddit import RedditPost


class IngestNewsRedditTermsUnitTestCase(unittest.TestCase):
    def test_persist_reddit_items_prefers_user_query_terms_over_subreddit(self) -> None:
        posts = [
            RedditPost(
                title="A",
                link="https://example.com/a",
                subreddit="machinelearning",
            )
        ]
        captured: dict[str, list[str]] = {}

        def _fake_dispatch_links(*, links, query_terms, extra_params=None):  # noqa: ANN001
            captured["query_terms"] = list(query_terms or [])
            return {"inserted": len(links), "inserted_valid": len(links), "skipped": 0, "queued": 0}

        with patch("app.services.ingest.news._dispatch_links_via_source_library_frontdoor", side_effect=_fake_dispatch_links):
            news._persist_reddit_items(  # noqa: SLF001
                posts=posts,
                doc_type="social_feed",
                source_name="reddit",
                base_url="reddit.com",
                default_state="CA",
                job_type=None,
                query_terms_override=["chip export control"],
            )

        self.assertEqual(captured.get("query_terms"), ["chip export control"])

    def test_persist_google_news_items_predecode_routes_decoded_urls_to_dispatch(self) -> None:
        items = [
            types.SimpleNamespace(link="https://news.google.com/rss/articles/a1", keyword="robotics"),
            types.SimpleNamespace(link="https://news.google.com/rss/articles/a2", keyword="robotics"),
            types.SimpleNamespace(link="https://example.com/direct", keyword="robotics"),
        ]

        decode_side_effect = [
            {"url": "https://publisher.example.com/story-1", "changed": True, "reason": "ok", "retryable": False},
            {"url": "https://news.google.com/rss/articles/a2", "changed": False, "reason": "rate_limited", "retryable": True},
            {"url": "https://example.com/direct", "changed": False, "reason": "ok", "retryable": False},
        ]
        calls: list[dict[str, object]] = []

        def _fake_dispatch_links(*, links, query_terms, extra_params=None):  # noqa: ANN001
            calls.append(
                {
                    "links": list(links or []),
                    "query_terms": list(query_terms or []),
                    "extra_params": dict(extra_params or {}),
                }
            )
            return {"inserted": 2, "inserted_valid": 2, "skipped": 0, "queued": 0}

        with (
            patch("app.services.ingest.news.decode_google_news_url_for_dispatch", side_effect=decode_side_effect),
            patch("app.services.ingest.news._dispatch_links_via_source_library_frontdoor", side_effect=_fake_dispatch_links),
        ):
            result = news._persist_google_news_items(  # noqa: SLF001
                items=items,
                doc_type="news",
                source_name="Google News",
                base_url="news.google.com",
                default_state=None,
                job_type="google_news",
            )

        self.assertGreaterEqual(len(calls), 1)
        self.assertEqual(
            calls[0]["links"],
            ["https://publisher.example.com/story-1", "https://example.com/direct"],
        )
        self.assertEqual(calls[0]["query_terms"], ["robotics", "robotics", "robotics"])
        self.assertEqual(int(result.get("decode_failed") or 0), 1)
        self.assertEqual(int(result.get("retryable_queued") or 0), 1)
        self.assertEqual(int((result.get("decode_breakdown") or {}).get("rate_limited") or 0), 1)

    def test_persist_google_news_items_rate_limited_reasons_are_counted_and_queued(self) -> None:
        items = [
            types.SimpleNamespace(link="https://news.google.com/rss/articles/b1", keyword="ai"),
            types.SimpleNamespace(link="https://news.google.com/rss/articles/b2", keyword="ai"),
        ]

        with (
            patch(
                "app.services.ingest.news.decode_google_news_url_for_dispatch",
                side_effect=[
                    {"url": "https://news.google.com/rss/articles/b1", "changed": False, "reason": "rate_limited", "retryable": True},
                    {"url": "https://news.google.com/rss/articles/b2", "changed": False, "reason": "too_many_requests", "retryable": False},
                ],
            ),
            patch(
                "app.services.ingest.news._dispatch_links_via_source_library_frontdoor",
                return_value={"inserted": 0, "inserted_valid": 0, "skipped": 0, "queued": 0},
            ),
        ):
            result = news._persist_google_news_items(  # noqa: SLF001
                items=items,
                doc_type="news",
                source_name="Google News",
                base_url="news.google.com",
                default_state=None,
                job_type="google_news",
            )

        self.assertEqual(int(result.get("queued") or 0), 2)
        self.assertEqual(int(result.get("retryable_queued") or 0), 2)
        self.assertEqual(int((result.get("decode_breakdown") or {}).get("rate_limited") or 0), 2)

    def test_persist_google_news_items_decode_before_dispatch_with_rate_limited_queue(self) -> None:
        items = [
            GoogleNewsItem(title="A", link="https://news.google.com/rss/articles/a?oc=5", keyword="ai"),
            GoogleNewsItem(title="B", link="https://news.google.com/rss/articles/b?oc=5", keyword="ai"),
            GoogleNewsItem(title="C", link="https://news.google.com/rss/articles/c?oc=5", keyword="robot"),
        ]
        calls: list[dict[str, object]] = []

        def _fake_decode(url: str) -> dict:  # noqa: ANN001
            if url.endswith("a?oc=5"):
                return {
                    "url": "https://publisher.example.com/a",
                    "changed": True,
                    "reason": "ok",
                    "retryable": False,
                }
            if url.endswith("b?oc=5"):
                return {
                    "url": url,
                    "changed": False,
                    "reason": "rate_limited",
                    "retryable": True,
                }
            return {
                "url": url,
                "changed": False,
                "reason": "google_news_batch_parse_failed",
                "retryable": False,
            }

        def _fake_dispatch_links(*, links, query_terms, extra_params=None):  # noqa: ANN001
            calls.append(
                {
                    "links": list(links or []),
                    "query_terms": list(query_terms or []),
                    "extra_params": dict(extra_params or {}),
                }
            )
            return {"inserted": 1, "inserted_valid": 1, "skipped": 0, "queued": 0}

        with (
            patch("app.services.ingest.news.decode_google_news_url_for_dispatch", side_effect=_fake_decode),
            patch("app.services.ingest.news._dispatch_links_via_source_library_frontdoor", side_effect=_fake_dispatch_links),
        ):
            result = news._persist_google_news_items(  # noqa: SLF001
                items=items,
                doc_type="news",
                source_name="Google News",
                base_url="news.google.com",
                default_state=None,
                job_type=None,
            )

        self.assertGreaterEqual(len(calls), 1)
        self.assertEqual(calls[0]["links"], ["https://publisher.example.com/a"])
        self.assertEqual(calls[0]["query_terms"], ["ai", "ai", "robot"])
        self.assertEqual(result.get("queued"), 1)
        self.assertEqual(result.get("retryable"), True)
        self.assertEqual(result.get("retryable_queued"), 1)
        self.assertEqual(result.get("skipped"), 1)
        self.assertEqual(
            result.get("breakdown"),
            {"rate_limited": 1, "google_news_batch_parse_failed": 1},
        )

    def test_persist_google_news_items_uses_publisher_seed_fallback_when_decode_rate_limited(self) -> None:
        item = types.SimpleNamespace(
            title="OpenAI launches new enterprise model",
            link="https://news.google.com/rss/articles/z1",
            keyword="OpenAI",
            source_url="https://www.cnbc.com",
        )
        calls: list[dict] = []

        def _fake_dispatch_links(*, links, query_terms, extra_params=None):  # noqa: ANN001
            calls.append(
                {
                    "links": list(links or []),
                    "query_terms": list(query_terms or []),
                    "extra_params": dict(extra_params or {}),
                }
            )
            if extra_params and extra_params.get("url_target_mode") == "site_only":
                return {"inserted": 1, "inserted_valid": 1, "skipped": 0, "queued": 0}
            return {"inserted": 0, "inserted_valid": 0, "skipped": 0, "queued": 0}

        with (
            patch(
                "app.services.ingest.news.decode_google_news_url_for_dispatch",
                return_value={"url": item.link, "changed": False, "reason": "rate_limited", "retryable": True},
            ),
            patch("app.services.ingest.news._dispatch_links_via_source_library_frontdoor", side_effect=_fake_dispatch_links),
        ):
            result = news._persist_google_news_items(  # noqa: SLF001
                items=[item],
                doc_type="news",
                source_name="Google News",
                base_url="news.google.com",
                default_state=None,
                job_type=None,
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["links"], ["https://www.cnbc.com/"])
        self.assertEqual(calls[1]["extra_params"].get("url_target_mode"), "site_only")
        self.assertIn("publisher_seed_fallback", result.get("decode_breakdown") or {})
        self.assertEqual(int(result.get("inserted") or 0), 1)


if __name__ == "__main__":
    unittest.main()
