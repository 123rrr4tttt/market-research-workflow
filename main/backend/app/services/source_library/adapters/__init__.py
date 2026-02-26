"""Channel adapters: wrap ingest modules and register with handler_registry."""

from __future__ import annotations

from .base import ChannelHandlerProtocol
from .google_news import handle_google_news
from .generic_web import (
    handle_generic_web_rss,
    handle_generic_web_search_template,
    handle_generic_web_sitemap,
)
from .market import handle_market
from .official_access import handle_official_access_api
from .policy import handle_policy
from .reddit import handle_reddit
from .url_pool import handle_url_pool
from ..handler_registry import register


def _register_all() -> None:
    """Register all builtin handlers. Called on first import."""
    register("reddit", "social", handle_reddit)
    register("google_news", "news", handle_google_news)
    register("policy", "policy", handle_policy)
    register("market", "market", handle_market)
    register("url_pool", "urls", handle_url_pool)
    # Tool-type channels (Phase 4 compatibility layer)
    register("generic_web", "rss", handle_generic_web_rss)
    register("generic_web", "sitemap", handle_generic_web_sitemap)
    register("generic_web", "search_template", handle_generic_web_search_template)
    register("official_access", "api", handle_official_access_api)


_register_all()

__all__ = [
    "ChannelHandlerProtocol",
    "handle_google_news",
    "handle_generic_web_rss",
    "handle_generic_web_search_template",
    "handle_generic_web_sitemap",
    "handle_market",
    "handle_official_access_api",
    "handle_policy",
    "handle_reddit",
    "handle_url_pool",
]
