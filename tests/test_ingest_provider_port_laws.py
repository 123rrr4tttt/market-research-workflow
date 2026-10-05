from __future__ import annotations

from functorial_kit import Idempotent, Ordered, PortLawSpec, port_laws

from app.services.ingest.provider_ports import PolicyDocument


class InMemoryPolicyAdapterPort:
    def __init__(self) -> None:
        self.states: list[str] = []

    def fetch_documents(self) -> list[PolicyDocument]:
        self.states.append("CA")
        return [
            PolicyDocument(
                state="CA",
                title="Policy",
                status="enacted",
                publish_date=None,
                summary=None,
                content="body",
            )
        ]


class InMemoryRedditPort:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple[str, ...]]] = []

    def fetch_posts(self, subreddit: str, keywords: list[str] | None, limit: int) -> list[dict[str, object]]:
        self.queries.append((subreddit, tuple(keywords or [])))
        return [{"subreddit": subreddit, "limit": limit}]

    def search_multiple_subreddits(
        self, subreddits: list[str], keywords: list[str] | None, limit: int
    ) -> list[dict[str, object]]:
        self.queries.extend((item, tuple(keywords or [])) for item in subreddits)
        return [{"subreddit": item, "limit": limit} for item in subreddits]

    def discover_subreddits(
        self, *, keywords: list[str], max_results: int, min_subscribers: int
    ) -> list[str]:
        return keywords[:max_results]


class InMemoryGoogleNewsPort:
    def __init__(self) -> None:
        self.queries: list[tuple[str, ...]] = []

    def search_multiple_keywords(self, keywords: list[str], limit: int) -> list[dict[str, object]]:
        self.queries.append(tuple(keywords))
        return [{"keyword": keyword, "limit": limit} for keyword in keywords]


_policy_idempotent: Idempotent[InMemoryPolicyAdapterPort] = Idempotent(
    "policy fetch is deterministic", lambda port: port.fetch_documents()
)
_policy_spec: PortLawSpec[InMemoryPolicyAdapterPort] = PortLawSpec(
    idempotent=[_policy_idempotent]
)
TestPolicyAdapterPort = port_laws(
    "PolicyAdapterPort", InMemoryPolicyAdapterPort, _policy_spec
)

_reddit_idempotent: Idempotent[InMemoryRedditPort] = Idempotent(
    "reddit single subreddit fetch is deterministic",
    lambda port: port.fetch_posts("stocks", ["ai"], 2),
)
_reddit_ordered: Ordered[InMemoryRedditPort] = Ordered(
    "reddit query order is preserved",
    first=lambda port: port.fetch_posts("stocks", ["ai"], 2),
    second=lambda port: port.fetch_posts("economics", ["ai"], 2),
    observe=lambda port: list(port.queries),
    commutes=False,
)
_reddit_spec: PortLawSpec[InMemoryRedditPort] = PortLawSpec(
    idempotent=[_reddit_idempotent], ordered=[_reddit_ordered]
)
TestRedditPort = port_laws("RedditPort", InMemoryRedditPort, _reddit_spec)

_google_news_idempotent: Idempotent[InMemoryGoogleNewsPort] = Idempotent(
    "google news query is deterministic",
    lambda port: port.search_multiple_keywords(["ai"], 2),
)
_google_news_ordered: Ordered[InMemoryGoogleNewsPort] = Ordered(
    "google news keyword order is preserved",
    first=lambda port: port.search_multiple_keywords(["ai"], 2),
    second=lambda port: port.search_multiple_keywords(["policy"], 2),
    observe=lambda port: list(port.queries),
    commutes=False,
)
_google_news_spec: PortLawSpec[InMemoryGoogleNewsPort] = PortLawSpec(
    idempotent=[_google_news_idempotent], ordered=[_google_news_ordered]
)
TestGoogleNewsPort = port_laws(
    "GoogleNewsPort", InMemoryGoogleNewsPort, _google_news_spec
)
