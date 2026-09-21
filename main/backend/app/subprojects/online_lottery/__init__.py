from .domain import (
    CALOTTERY_NEWS_URL,
    CALOTTERY_RETAILER_URL,
    DEFAULT_REDDIT_SUBREDDIT,
    LOTTERY_TOKENS,
)
from .extraction_adapter import OnlineLotteryExtractionAdapter
from typing import NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import online_lottery_compatibility_failures

PROJECT_KEY = "online_lottery"
PROJECT_KEY_PREFIX_ALIASES: list[str] = []
PROJECT_EXTRACTION_ADAPTER_CLASS = OnlineLotteryExtractionAdapter

_ONLINE_LOTTERY_FAILURE_WITNESS = "test:test_w01_project_identity_failures"
_ONLINE_LOTTERY_FAILURE_CONTEXT_KEYS = frozenset(
    {
        "boundary_class",
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
)


def _compatibility_failure(name: str) -> Failure:
    return online_lottery_compatibility_failures.fail(
        "attribute_not_found",
        name,
        {
            "boundary_class": "PURE_CONTRACT_FAILURE",
            "failure_family": online_lottery_compatibility_failures.name,
            "operation": "online_lottery.__getattr__",
            "owner": "app.subprojects.online_lottery.__getattr__",
            "public_exception": "AttributeError",
            "public_message": name,
            "site": "app.subprojects.online_lottery.__getattr__",
            "witness": _ONLINE_LOTTERY_FAILURE_WITNESS,
        },
    )


def _raise_compatibility_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    if (
        not online_lottery_compatibility_failures.matches(failure)
        or _ONLINE_LOTTERY_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("public_exception") != "AttributeError"
    ):
        # kit:boundary owner=online_lottery.compatibility.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_online_lottery_dynamic_getattr_preserves_attribute_error
        raise TypeError("online lottery compatibility failure lift context is incomplete")
    # kit:boundary owner=online_lottery.compatibility.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=online_lottery.compatibility.failure witness=test:test_w01_online_lottery_dynamic_getattr_preserves_attribute_error
    raise AttributeError(str(context["public_message"]))

__all__ = [
    "PROJECT_KEY",
    "PROJECT_KEY_PREFIX_ALIASES",
    "PROJECT_EXTRACTION_ADAPTER_CLASS",
    "CALOTTERY_NEWS_URL",
    "CALOTTERY_RETAILER_URL",
    "DEFAULT_REDDIT_SUBREDDIT",
    "LOTTERY_TOKENS",
    "collect_calottery_news_for_project",
    "collect_calottery_retailer_updates_for_project",
    "collect_reddit_discussions_for_project",
    "ingest_lottery_stats",
    "OnlineLotteryExtractionAdapter",
]


def __getattr__(name: str):
    if name in {
        "collect_calottery_news_for_project",
        "collect_calottery_retailer_updates_for_project",
        "collect_reddit_discussions_for_project",
        "ingest_lottery_stats",
    }:
        from . import services as _services

        return getattr(_services, name)
    _raise_compatibility_failure(_compatibility_failure(name))
