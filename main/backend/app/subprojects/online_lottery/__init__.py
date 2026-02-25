from .domain import (
    ADAPTERS,
    CA_GAME_MAP,
    CALOTTERY_NEWS_URL,
    CALOTTERY_RETAILER_URL,
    DEFAULT_REDDIT_SUBREDDIT,
    LOTTERY_TOKENS,
)
from .services import (
    collect_calottery_news_for_project,
    collect_calottery_retailer_updates_for_project,
    collect_reddit_discussions_for_project,
    ingest_lottery_stats,
    resolve_market_adapters,
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
