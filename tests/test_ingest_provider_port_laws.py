from __future__ import annotations

from datetime import date

from functorial_kit import Idempotent, Ordered, PortLawSpec, port_laws

from app.services.ingest.provider_ports import MarketRecord, PolicyDocument


class InMemoryMarketAdapterPort:
    def __init__(self) -> None:
        self.states: list[str] = []

    def fetch_records(self) -> list[MarketRecord]:
        self.states.append("CA")
        return [
            MarketRecord(
                state="CA",
                date=date(2026, 1, 1),
                revenue=1.0,
            )
        ]


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


TestMarketAdapterPort = port_laws(
    "MarketAdapterPort",
    InMemoryMarketAdapterPort,
    PortLawSpec(
        idempotent=[Idempotent("market fetch is deterministic", lambda port: port.fetch_records())],
    ),
)

TestPolicyAdapterPort = port_laws(
    "PolicyAdapterPort",
    InMemoryPolicyAdapterPort,
    PortLawSpec(
        idempotent=[Idempotent("policy fetch is deterministic", lambda port: port.fetch_documents())],
    ),
)

TestRedditPort = port_laws(
    "RedditPort",
    InMemoryRedditPort,
    PortLawSpec(
        idempotent=[
            Idempotent(
                "reddit single subreddit fetch is deterministic",
                lambda port: port.fetch_posts("stocks", ["ai"], 2),
            )
        ],
        ordered=[
            Ordered(
                "reddit query order is preserved",
                first=lambda port: port.fetch_posts("stocks", ["ai"], 2),
                second=lambda port: port.fetch_posts("economics", ["ai"], 2),
                observe=lambda port: list(port.queries),
                commutes=False,
            )
        ],
    ),
)

TestGoogleNewsPort = port_laws(
    "GoogleNewsPort",
    InMemoryGoogleNewsPort,
    PortLawSpec(
        idempotent=[
            Idempotent(
                "google news query is deterministic",
                lambda port: port.search_multiple_keywords(["ai"], 2),
            )
        ],
        ordered=[
            Ordered(
                "google news keyword order is preserved",
                first=lambda port: port.search_multiple_keywords(["ai"], 2),
                second=lambda port: port.search_multiple_keywords(["policy"], 2),
                observe=lambda port: list(port.queries),
                commutes=False,
            )
        ],
    ),
)
