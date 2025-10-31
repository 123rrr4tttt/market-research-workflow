from __future__ import annotations

from datetime import datetime
from typing import Iterable

import httpx

from .market_base import MarketAdapter, MarketRecord


class NewYorkLotteryMarketAdapter(MarketAdapter):
    API_URL = "https://data.ny.gov/resource/5xaw-6ayf.json"

    def fetch_records(self) -> Iterable[MarketRecord]:
        params = {
            "$limit": 500,
            "$order": "draw_date DESC",
            "game_name": "MEGA MILLIONS",
        }
        response = httpx.get(self.API_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        for item in payload:
            if item.get("game_name") and item["game_name"].upper() != "MEGA MILLIONS":
                continue
            draw_date = None
            if item.get("draw_date"):
                try:
                    draw_date = datetime.strptime(item["draw_date"], "%Y-%m-%dT%H:%M:%S.%f").date()
                except ValueError:
                    draw_date = None
            if draw_date is None:
                continue

            jackpot = _parse_amount(item.get("jackpot"))
            revenue = _parse_amount(item.get("payout"))

            yield MarketRecord(
                state=self.state,
                date=draw_date,
                sales_volume=None,
                revenue=revenue,
                jackpot=jackpot,
                ticket_price=2.0,
                source_name="New York Lottery - Winning Numbers (Open Data)",
                uri="https://data.ny.gov/Lottery/Lottery-Winning-Numbers/5xaw-6ayf",
                game="Mega Millions",
            )


def _parse_amount(value):
    if value is None:
        return None
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except ValueError:
        return None

