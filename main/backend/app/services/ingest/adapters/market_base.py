from __future__ import annotations

from collections.abc import Iterable

from ..provider_ports import MarketRecord

class MarketAdapter:
    """Base class for market data adapters."""

    def __init__(self, state: str):
        self.state = state

    def fetch_records(self) -> Iterable[MarketRecord]:
        raise NotImplementedError

