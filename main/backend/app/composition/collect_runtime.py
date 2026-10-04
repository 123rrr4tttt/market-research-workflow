"""Composition root for concrete collect adapters.

This shell module owns concrete adapter construction so the collect runtime can
depend only on the ``CollectAdapter`` port and ordered execution semantics.
"""

from __future__ import annotations

from app.services.collect_runtime.adapters.crawler_scrapy import CrawlerScrapyAdapter
from app.services.collect_runtime.adapters.search_market import SearchMarketAdapter
from app.services.collect_runtime.adapters.search_policy import SearchPolicyAdapter
from app.services.collect_runtime.adapters.source_library import (
    SourceLibraryAdapter,
    to_source_library_response,
)
from app.services.collect_runtime.adapters.url_pool import UrlPoolAdapter
from app.services.collect_runtime.contracts import CollectAdapter, CollectRequest, CollectResult
from app.services.collect_runtime.runtime import (
    register_collect_adapters,
    register_successor_collect_effect_gateway,
    register_source_library_compat_projector,
    run_collect,
    run_source_library_item_compat,
)

_CONFIGURED = False


def default_collect_adapters() -> dict[str, CollectAdapter]:
    return {
        "search.market": SearchMarketAdapter(),
        "search.policy": SearchPolicyAdapter(),
        "source_library": SourceLibraryAdapter(),
        "url_pool": UrlPoolAdapter(),
        "crawler.scrapy": CrawlerScrapyAdapter(),
    }


def configure_default_collect_adapters(*, force: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED and not force:
        return
    adapters = default_collect_adapters()
    register_collect_adapters(adapters)
    register_source_library_compat_projector(to_source_library_response)

    def run_successor_effect(request: CollectRequest) -> CollectResult:
        # C3 owns ordering and outcome interpretation; the existing channel
        # adapter remains the explicit effect owner. Unknown channels fail
        # closed instead of falling back to legacy dispatch.
        adapter = adapters.get(str(request.channel or "").strip())
        if adapter is None:
            return CollectResult(
                flow=request.flow,
                channel=request.channel,
                status="failed",
                errors=[{
                    "code": "collect_effect_not_registered",
                    "message": f"no successor collect effect is registered for {request.channel!r}",
                }],
            )
        return adapter.run(request)

    register_successor_collect_effect_gateway(run_successor_effect)
    _CONFIGURED = True


def run_default_collect(request: CollectRequest) -> CollectResult:
    configure_default_collect_adapters()
    return run_collect(request)


__all__ = [
    "configure_default_collect_adapters",
    "default_collect_adapters",
    "run_default_collect",
    "run_source_library_item_compat",
]
