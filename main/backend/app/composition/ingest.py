"""Composition root for legacy ingest provider adapters."""

from __future__ import annotations

from app.services.ingest.adapters.base import PolicyAdapter
from app.services.ingest.adapters.ca_legislature import CaliforniaLegislatureAdapter
from app.services.ingest.adapters.legiscan_api import LegiScanApiAdapter
from app.services.ingest.adapters.news_google import GoogleNewsAdapter
from app.services.ingest.adapters.social_reddit import RedditAdapter
from app.services.ingest.provider_ports import set_ingest_adapter_providers


def _resolve_policy_adapter(state: str, source_hint: str | None) -> PolicyAdapter:
    state_key = state.upper()
    if source_hint and source_hint.lower() == "legiscan":
        return LegiScanApiAdapter(state_key)
    if state_key != "CA":
        raise ValueError(f"暂无州 {state_key} 的政策适配器；可尝试设置 source_hint=legiscan")
    return CaliforniaLegislatureAdapter(state_key)


def configure_ingest_adapters() -> None:
    set_ingest_adapter_providers(
        policy_resolver=_resolve_policy_adapter,
        reddit_factory=RedditAdapter,
        google_news_factory=GoogleNewsAdapter,
    )
