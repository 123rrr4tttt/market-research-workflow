from .domain import (
    ADAPTERS,
    CA_GAME_MAP,
    CALOTTERY_NEWS_URL,
    CALOTTERY_RETAILER_URL,
    DEFAULT_REDDIT_SUBREDDIT,
    LOTTERY_TOKENS,
)
from .extraction_adapter import OnlineLotteryExtractionAdapter
PROJECT_KEY = "online_lottery"
PROJECT_KEY_PREFIX_ALIASES: list[str] = []
PROJECT_EXTRACTION_ADAPTER_CLASS = OnlineLotteryExtractionAdapter

__all__ = [
    "PROJECT_KEY",
    "PROJECT_KEY_PREFIX_ALIASES",
    "PROJECT_EXTRACTION_ADAPTER_CLASS",
    "ADAPTERS",
    "CA_GAME_MAP",
    "CALOTTERY_NEWS_URL",
    "CALOTTERY_RETAILER_URL",
    "DEFAULT_REDDIT_SUBREDDIT",
    "LOTTERY_TOKENS",
    "collect_calottery_news_for_project",
    "collect_calottery_retailer_updates_for_project",
    "collect_reddit_discussions_for_project",
    "ingest_lottery_stats",
    "resolve_market_adapters",
    "OnlineLotteryExtractionAdapter",
]


def __getattr__(name: str):
    if name in {
        "collect_calottery_news_for_project",
        "collect_calottery_retailer_updates_for_project",
        "collect_reddit_discussions_for_project",
        "ingest_lottery_stats",
        "resolve_market_adapters",
    }:
        from . import services as _services

        return getattr(_services, name)
    raise AttributeError(name)
