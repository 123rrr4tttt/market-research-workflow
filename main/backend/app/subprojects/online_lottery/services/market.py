from __future__ import annotations

from typing import Any, Dict

from ....services.ingest.provider_ports import MarketAdapterPort, get_market_adapters


def resolve_market_adapters(
    state: str,
    source_hint: str | None = None,
    inject_params: Dict[str, Any] | None = None,
) -> list[MarketAdapterPort]:
    """Resolve adapters through the market port installed by composition."""
    return get_market_adapters(state, source_hint, inject_params)
