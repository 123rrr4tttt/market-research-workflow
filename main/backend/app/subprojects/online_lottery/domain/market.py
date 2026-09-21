from __future__ import annotations

from typing import Callable, Dict

from ....services.ingest.provider_ports import MarketAdapterPort

AdapterFactory = Callable[[str], MarketAdapterPort]
SupportedMarketAdapters = Dict[str, AdapterFactory]
