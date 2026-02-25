from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable


@dataclass(slots=True)
class MarketRecord:
    state: str
    date: date
    sales_volume: float | None = None
    revenue: float | None = None
    jackpot: float | None = None
    ticket_price: float | None = None
    source_name: str | None = None
    uri: str | None = None
    game: str | None = None
    draw_number: str | None = None
    extra: dict[str, Any] | None = None


class MarketAdapter:
    """Base class for market data adapters."""

    def __init__(self, state: str):
        self.state = state

    def fetch_records(self) -> Iterable[MarketRecord]:
        raise NotImplementedError


