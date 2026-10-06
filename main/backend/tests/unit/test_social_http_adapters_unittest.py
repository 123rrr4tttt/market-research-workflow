from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.ingest.adapters import social_nitter, social_reddit
from app.services.ingest.adapters.http_utils import RequestOutcome
from app.services.ingest.retry_policy import make_request_failure

pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code


def _ok(text: str, status_code: int = 200) -> RequestOutcome:
    return RequestOutcome(text=text, response=_FakeResponse(status_code), attempts=1)


class SocialHttpAdapterUnitTestCase(unittest.TestCase):
    def test_reddit_uses_explicit_scope_gate_and_preserves_posts(self):
        payload = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Policy migration",
                            "permalink": "/r/example/comments/abc/policy_migration/",
                            "author": "alice",
                            "ups": 4,
                            "num_comments": 2,
                            "selftext": "body",
                            "created_utc": 1_700_000_000,
                        }
                    }
                ]
            }
        }
        calls: list[tuple[dict[str, object], dict[str, object]]] = []

        def request_html(url: str, **kwargs: object) -> RequestOutcome:
            calls.append(({"url": url}, dict(kwargs)))
            return _ok(json.dumps(payload))

        with (
            patch.object(social_reddit, "request_html", request_html),
            patch.object(social_reddit, "get_library_keywords", return_value=[]),
        ):
            posts = list(social_reddit.RedditAdapter().fetch_posts("example", limit=5))

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].title, "Policy migration")
        self.assertEqual(posts[0].subreddit, "example")
        self.assertEqual(len(calls), 1)
        kwargs = calls[0][1]
        self.assertEqual(kwargs["scope"], social_reddit._REQUEST_SCOPE)
        self.assertEqual(kwargs["scope"].provider, "reddit")
        self.assertIs(kwargs["retry_gate"], social_reddit._RATE_GATE)

    def test_reddit_429_failure_uses_public_policy_failure_projection(self):
        scope = social_reddit._REQUEST_SCOPE
        failure = make_request_failure(
            reason_code="rate_limited",
            status_code=429,
            scope=scope,
            retryable=True,
            retry_after_seconds=7.0,
            attempt=2,
        )

        def request_html(url: str, **kwargs: object) -> RequestOutcome:
            return RequestOutcome(
                response=_FakeResponse(429),
                failures=(failure,),
                attempts=3,
            )

        with patch.object(social_reddit, "request_html", request_html):
            posts = list(social_reddit.RedditAdapter().fetch_posts("example"))

        self.assertEqual(posts, [])
        self.assertEqual(failure.code, "RATE_LIMITED")
        self.assertEqual(failure.context.get("retry_after_seconds"), 7.0)
        self.assertEqual(failure.context.get("provider"), "reddit")

    def test_nitter_uses_shared_gate_and_json_result(self):
        payload = {
            "tweets": [
                {"id": "abc", "text": "timeline item", "date": "Wed, 01 Nov 2023 12:00:00 GMT"}
            ]
        }
        outcomes = [_ok("instance"), _ok(json.dumps(payload))]
        calls: list[dict[str, object]] = []

        def request_html(
            self: social_nitter.NitterAdapter,
            url: str,
            headers: dict[str, str],
            *,
            timeout: float,
            retries: int = 3,
        ) -> RequestOutcome:
            calls.append(
                {
                    "url": url,
                    "scope": self._REQUEST_SCOPE,
                    "gate": self._RATE_GATE,
                    "timeout": timeout,
                    "retries": retries,
                }
            )
            return outcomes.pop(0)

        with patch.object(social_nitter.NitterAdapter, "_request_html", request_html):
            posts = list(social_nitter.NitterAdapter().fetch_user_tweets("example"))

        self.assertEqual([post.text for post in posts], ["timeline item"])
        self.assertEqual(calls[0]["retries"], 1)
        self.assertEqual(calls[1]["retries"], 3)
        self.assertIs(calls[0]["scope"], calls[1]["scope"])
        self.assertIs(calls[0]["gate"], calls[1]["gate"])
        self.assertEqual(calls[0]["scope"].provider, "nitter")

    def test_social_adapters_do_not_keep_duplicate_business_sleeps(self):
        source_files = {
            "twitter": Path(__file__).parents[2]
            / "app/services/ingest/adapters/social_twitter.py",
            "reddit": Path(__file__).parents[2]
            / "app/services/ingest/adapters/social_reddit.py",
            "nitter": Path(__file__).parents[2]
            / "app/services/ingest/adapters/social_nitter.py",
        }
        sleep_counts = {
            name: source_file.read_text(encoding="utf-8").count("time.sleep(")
            for name, source_file in source_files.items()
        }
        self.assertEqual(sleep_counts["twitter"], 0)
        self.assertEqual(sleep_counts["reddit"], 0)
        self.assertEqual(sleep_counts["nitter"], 0)
