from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.services.ingest.adapters.social_twitter import TwitterAdapter
from app.services.ingest.retry_policy import RateGate

pytestmark = pytest.mark.unit


@dataclass(slots=True)
class _Tweet:
    id: str
    text: str
    created_at: datetime | None
    author_id: str | None
    public_metrics: dict[str, int]


@dataclass(slots=True)
class _UserTweet:
    id: str
    text: str
    created_at: datetime | None
    public_metrics: dict[str, int]


@dataclass(slots=True)
class _User:
    id: str
    username: str


@dataclass(slots=True)
class _Response:
    data: object
    includes: object = None


@dataclass(slots=True)
class _ErrorResponse:
    status_code: int
    headers: dict[str, str]


class TooManyRequests(RuntimeError):
    def __init__(self, retry_after: str) -> None:
        super().__init__("rate limited")
        self.response = _ErrorResponse(429, {"Retry-After": retry_after})


class _FakeClient:
    def __init__(self, search_results: list[object], user_tweets: object = None) -> None:
        self.search_results = list(search_results)
        self.user_tweets = user_tweets
        self.queries: list[str] = []

    def search_recent_tweets(
        self,
        *,
        query: str,
        max_results: int,
        tweet_fields: Sequence[str],
        expansions: Sequence[str],
        user_fields: Sequence[str],
    ) -> object:
        self.queries.append(query)
        result = self.search_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def get_user(self, *, username: str) -> object:
        return _Response(_User("u-1", username))

    def get_users_tweets(
        self,
        *,
        id: str,
        max_results: int,
        tweet_fields: Sequence[str],
    ) -> object:
        return _Response(self.user_tweets)


def _gate(sleeps: list[float]) -> RateGate:
    return RateGate(
        rate_limit_interval_seconds=1.0,
        backoff_base_seconds=1.5,
        backoff_max_seconds=60.0,
        clock=lambda: 0.0,
        sleeper=sleeps.append,
    )


def _tweet_response(tweet_id: str, text: str) -> _Response:
    return _Response(
        [
            _Tweet(
                id=tweet_id,
                text=text,
                created_at=datetime(2026, 10, 6, tzinfo=UTC),
                author_id="u-1",
                public_metrics={"like_count": 3, "retweet_count": 2, "reply_count": 1},
            )
        ],
        {"users": [_User("u-1", "alice")]},
    )


def test_twitter_native_result_keeps_tweet_user_and_metrics_associated() -> None:
    client = _FakeClient([_tweet_response("t-1", "typed result")])
    adapter = TwitterAdapter(client=client)
    sleeps: list[float] = []
    adapter._RATE_GATE = _gate(sleeps)

    posts = adapter.search_tweets("typed")

    assert [(post.link, post.username, post.likes, post.retweets, post.replies) for post in posts] == [
        ("https://twitter.com/alice/status/t-1", "alice", 3, 2, 1)
    ]
    assert adapter.last_failures == ()
    assert client.queries == ["typed"]
    assert sleeps == []


def test_twitter_429_preserves_scope_and_retry_after() -> None:
    adapter = TwitterAdapter(client=_FakeClient([TooManyRequests("7")]))
    adapter._RATE_GATE = _gate([])

    assert adapter.search_tweets("limited") == []

    assert len(adapter.last_failures) == 1
    failure = adapter.last_failures[0]
    assert failure.code == "RATE_LIMITED"
    assert failure.context is not None
    assert failure.context["provider"] == "twitter"
    assert failure.context["status_code"] == 429
    assert failure.context["retry_after_seconds"] == 7.0


def test_twitter_user_tweets_keep_native_post_without_author_expansion() -> None:
    client = _FakeClient(
        [],
        [
            _UserTweet(
                id="t-2",
                text="user timeline",
                created_at=None,
                public_metrics={"like_count": 4},
            )
        ],
    )
    adapter = TwitterAdapter(client=client)
    adapter._RATE_GATE = _gate([])

    posts = adapter.get_user_tweets("alice")

    assert [(post.link, post.username, post.likes) for post in posts] == [
        ("https://twitter.com/alice/status/t-2", "alice", 4)
    ]


def test_twitter_multiple_queries_preserves_order_and_partial_failure() -> None:
    client = _FakeClient([_tweet_response("t-1", "first"), TooManyRequests("3")])
    adapter = TwitterAdapter(client=client)
    sleeps: list[float] = []
    adapter._RATE_GATE = _gate(sleeps)

    posts = adapter.search_multiple_queries(["one", "two"])

    assert [post.text for post in posts] == ["first"]
    assert client.queries == ["one", "two"]
    assert sleeps == [1.0]
    assert len(adapter.last_failures) == 1
    assert adapter.last_failures[0].context is not None
    assert adapter.last_failures[0].context["retry_after_seconds"] == 3.0
