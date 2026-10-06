"""Twitter/X official API adapter with explicit request-policy attribution."""
from __future__ import annotations

import importlib
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Protocol, TypeGuard, runtime_checkable
from urllib.parse import unquote

from functorial_kit import Failure

from ..retry_policy import RateGate, RequestScope, make_request_failure, parse_retry_after_seconds

logger = logging.getLogger(__name__)


@runtime_checkable
class _TweepyModule(Protocol):
    def Client(
        self,
        *,
        bearer_token: str | None = None,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        access_token: str | None = None,
        access_token_secret: str | None = None,
        wait_on_rate_limit: bool,
    ) -> object: ...


try:
    _raw_tweepy: object = importlib.import_module("tweepy")
except ImportError:
    _tweepy = None
    logger.warning("tweepy library not installed. Install it with: pip install tweepy")
else:
    _tweepy = _raw_tweepy if isinstance(_raw_tweepy, _TweepyModule) else None

TWEEPY_AVAILABLE = _tweepy is not None


@dataclass(slots=True)
class TwitterPost:
    title: str
    link: str
    summary: Optional[str] = None
    timestamp: Optional[datetime] = None
    username: Optional[str] = None
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    text: Optional[str] = None


@dataclass(frozen=True, slots=True)
class _NativeTweet:
    id: str
    text: str
    created_at: datetime | None
    author_id: str | None
    likes: int
    retweets: int
    replies: int


@dataclass(frozen=True, slots=True)
class _NativeUser:
    id: str
    username: str


@runtime_checkable
class _TwitterClient(Protocol):
    def search_recent_tweets(
        self,
        *,
        query: str,
        max_results: int,
        tweet_fields: Sequence[str],
        expansions: Sequence[str],
        user_fields: Sequence[str],
    ) -> object: ...

    def get_user(self, *, username: str) -> object: ...

    def get_users_tweets(
        self,
        *,
        id: str,
        max_results: int,
        tweet_fields: Sequence[str],
    ) -> object: ...


@runtime_checkable
class _ResponseShape(Protocol):
    data: object


@runtime_checkable
class _SearchResponseShape(Protocol):
    data: object
    includes: object


@runtime_checkable
class _TweetShape(Protocol):
    id: object
    text: object


@runtime_checkable
class _TweetCreatedShape(Protocol):
    created_at: object


@runtime_checkable
class _TweetAuthorShape(Protocol):
    author_id: object


@runtime_checkable
class _TweetMetricsShape(Protocol):
    public_metrics: object


@runtime_checkable
class _UserShape(Protocol):
    id: object
    username: object


@runtime_checkable
class _ExceptionResponseShape(Protocol):
    response: object


@runtime_checkable
class _HttpResponseShape(Protocol):
    status_code: object
    headers: object


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _object_mapping(value: object) -> dict[str, object]:
    if not _is_object_dict(value):
        return {}
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(key, str):
            result[key] = item
    return result


def _string(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _count(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _native_tweet(value: object) -> _NativeTweet | None:
    if not isinstance(value, _TweetShape):
        return None
    tweet_id = _string(value.id)
    text = _string(value.text)
    if tweet_id is None or text is None:
        return None
    metrics = _object_mapping(value.public_metrics) if isinstance(value, _TweetMetricsShape) else {}
    return _NativeTweet(
        id=tweet_id,
        text=text,
        created_at=(
            value.created_at
            if isinstance(value, _TweetCreatedShape) and isinstance(value.created_at, datetime)
            else None
        ),
        author_id=_string(value.author_id) if isinstance(value, _TweetAuthorShape) else None,
        likes=_count(metrics.get("like_count")),
        retweets=_count(metrics.get("retweet_count")),
        replies=_count(metrics.get("reply_count")),
    )


def _native_user(value: object) -> _NativeUser | None:
    if not isinstance(value, _UserShape):
        return None
    user_id = _string(value.id)
    username = _string(value.username)
    if user_id is None or username is None:
        return None
    return _NativeUser(id=user_id, username=username)


def _tweet_data(response: object) -> list[_NativeTweet]:
    if not isinstance(response, _ResponseShape) or not _is_object_list(response.data):
        return []
    tweets: list[_NativeTweet] = []
    for item in response.data:
        tweet = _native_tweet(item)
        if tweet is not None:
            tweets.append(tweet)
    return tweets


def _included_users(response: object) -> dict[str, _NativeUser]:
    if not isinstance(response, _SearchResponseShape):
        return {}
    values = _object_mapping(response.includes).get("users")
    if not _is_object_list(values):
        return {}
    users: dict[str, _NativeUser] = {}
    for value in values:
        user = _native_user(value)
        if user is not None:
            users[user.id] = user
    return users


def _lookup_user(response: object) -> _NativeUser | None:
    return _native_user(response.data) if isinstance(response, _ResponseShape) else None


def _clean_keywords(keywords: list[str] | None) -> list[str]:
    return [value for keyword in (keywords or []) if (value := keyword.lower().strip())]


def _matches_keywords(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    normalized = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower()))
    return any(keyword in normalized for keyword in keywords)


def _exception_status_and_headers(exc: Exception) -> tuple[int | None, dict[str, str]]:
    status_code: int | None = None
    headers: dict[str, str] = {}
    if isinstance(exc, _ExceptionResponseShape) and isinstance(exc.response, _HttpResponseShape):
        raw_status = exc.response.status_code
        if isinstance(raw_status, int) and not isinstance(raw_status, bool):
            status_code = raw_status
        raw_headers = exc.response.headers
        if _is_object_mapping(raw_headers):
            for key, value in raw_headers.items():
                headers[str(key).lower()] = str(value)
    if status_code is None:
        status_code = {
            "TooManyRequests": 429,
            "Unauthorized": 401,
            "Forbidden": 403,
            "NotFound": 404,
        }.get(type(exc).__name__)
    return status_code, headers


def _require_client(value: object) -> _TwitterClient:
    if not isinstance(value, _TwitterClient):
        raise TypeError("Twitter client does not implement the required read API")
    return value


def _new_tweepy_client(
    *,
    api_key: str | None,
    api_secret: str | None,
    bearer_token: str | None,
    access_token: str | None,
    access_token_secret: str | None,
) -> _TwitterClient:
    if _tweepy is None:
        raise ImportError("tweepy library is required. Install it with: pip install tweepy")
    raw_client: object
    if api_key and api_secret and access_token and access_token_secret:
        raw_client = _tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            wait_on_rate_limit=False,
        )
    elif bearer_token:
        raw_client = _tweepy.Client(
            bearer_token=unquote(bearer_token),
            wait_on_rate_limit=False,
        )
    else:
        raise ValueError("Insufficient Twitter API credentials provided")
    return _require_client(raw_client)


class TwitterAdapter:
    """Twitter/X official read adapter."""

    _REQUEST_SCOPE = RequestScope(provider="twitter")
    _RATE_GATE = RateGate(
        rate_limit_interval_seconds=1.0,
        backoff_base_seconds=1.5,
        backoff_max_seconds=60.0,
        sleeper=time.sleep,
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        bearer_token: Optional[str] = None,
        access_token: Optional[str] = None,
        access_token_secret: Optional[str] = None,
        *,
        client: _TwitterClient | None = None,
    ) -> None:
        if client is not None:
            self.client = client
        else:
            if not any((api_key, bearer_token)):
                from ....settings.config import settings

                api_key = api_key or settings.twitter_api_key
                api_secret = api_secret or settings.twitter_api_secret
                bearer_token = bearer_token or settings.twitter_bearer_token
                access_token = access_token or settings.twitter_access_token
                access_token_secret = access_token_secret or settings.twitter_access_token_secret
            if not bearer_token and not (
                api_key and api_secret and access_token and access_token_secret
            ):
                raise ValueError(
                    "Twitter API credentials are required. Provide either bearer_token "
                    "or (api_key, api_secret, access_token, access_token_secret)"
                )
            self.client = _new_tweepy_client(
                api_key=api_key,
                api_secret=api_secret,
                bearer_token=bearer_token,
                access_token=access_token,
                access_token_secret=access_token_secret,
            )
        self.last_failures: tuple[Failure, ...] = ()

    def _request(self, operation: Callable[[], object]) -> object | None:
        gate_decision = self._RATE_GATE.acquire(self._REQUEST_SCOPE)
        if not gate_decision.acquired:
            failure = make_request_failure(
                reason_code="rate_limited",
                scope=self._REQUEST_SCOPE,
                retryable=True,
                retry_after_seconds=gate_decision.retry_after_seconds,
            )
            self.last_failures = (failure,)
            return None
        try:
            result = operation()
        except Exception as exc:
            status_code, headers = _exception_status_and_headers(exc)
            retry_after = parse_retry_after_seconds(headers.get("retry-after"))
            rate_limited = status_code == 429
            failure = make_request_failure(
                reason_code="rate_limited" if rate_limited else "fetch_failed",
                status_code=status_code,
                scope=self._REQUEST_SCOPE,
                retryable=rate_limited or status_code is None or status_code >= 500,
                retry_after_seconds=retry_after,
                transport_error=status_code is None,
                message=str(exc) or type(exc).__name__,
            )
            if rate_limited:
                self._RATE_GATE.record_throttle(
                    self._REQUEST_SCOPE,
                    retry_after_seconds=retry_after,
                )
            self.last_failures = (failure,)
            logger.error("Twitter API request failed: %s", failure.message)
            return None
        self._RATE_GATE.record_success(self._REQUEST_SCOPE)
        self.last_failures = ()
        return result

    @staticmethod
    def _post(tweet: _NativeTweet, *, username: str | None) -> TwitterPost:
        link = (
            f"https://twitter.com/{username}/status/{tweet.id}"
            if username
            else f"https://twitter.com/i/web/status/{tweet.id}"
        )
        return TwitterPost(
            title=tweet.text[:200],
            link=link,
            summary=tweet.text,
            timestamp=tweet.created_at,
            username=username,
            likes=tweet.likes,
            retweets=tweet.retweets,
            replies=tweet.replies,
            text=tweet.text,
        )

    def search_tweets(
        self,
        query: str,
        keywords: Optional[List[str]] = None,
        limit: int = 20,
        max_results: int = 100,
    ) -> list[TwitterPost]:
        if not query or not query.strip():
            self.last_failures = ()
            return []
        response = self._request(
            lambda: self.client.search_recent_tweets(
                query=query,
                max_results=min(max_results, 100),
                tweet_fields=("created_at", "author_id", "public_metrics", "text"),
                expansions=("author_id",),
                user_fields=("username", "name"),
            )
        )
        if response is None:
            return []
        tweets = _tweet_data(response)
        users = _included_users(response)
        effective_keywords = _clean_keywords(keywords)
        posts: list[TwitterPost] = []
        for tweet in tweets:
            if not _matches_keywords(tweet.text, effective_keywords):
                continue
            user = users.get(tweet.author_id) if tweet.author_id is not None else None
            posts.append(self._post(tweet, username=user.username if user is not None else None))
            if len(posts) >= limit:
                break
        logger.info("Search %r: found %d tweets (from %d total)", query, len(posts), len(tweets))
        return posts

    def get_user_tweets(
        self,
        username: str,
        keywords: Optional[List[str]] = None,
        limit: int = 20,
        max_results: int = 100,
    ) -> list[TwitterPost]:
        user_response = self._request(lambda: self.client.get_user(username=username))
        if user_response is None:
            return []
        user = _lookup_user(user_response)
        if user is None:
            return []
        tweet_response = self._request(
            lambda: self.client.get_users_tweets(
                id=user.id,
                max_results=min(max_results, 100),
                tweet_fields=("created_at", "public_metrics", "text"),
            )
        )
        if tweet_response is None:
            return []
        tweets = _tweet_data(tweet_response)
        effective_keywords = _clean_keywords(keywords)
        posts = [
            self._post(tweet, username=user.username)
            for tweet in tweets
            if _matches_keywords(tweet.text, effective_keywords)
        ][:limit]
        logger.info("@%s: found %d tweets (from %d total)", username, len(posts), len(tweets))
        return posts

    def search_multiple_queries(
        self,
        queries: List[str],
        keywords: Optional[List[str]] = None,
        limit_per_query: int = 20,
    ) -> list[TwitterPost]:
        all_posts: list[TwitterPost] = []
        failures: list[Failure] = []
        for query in queries:
            posts = self.search_tweets(query, keywords, limit_per_query)
            all_posts.extend(posts)
            failures.extend(self.last_failures)
        self.last_failures = tuple(failures)
        return all_posts
