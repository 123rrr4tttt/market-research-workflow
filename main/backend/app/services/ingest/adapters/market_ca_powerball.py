from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .http_utils import fetch_html, make_html_parser
from .market_base import MarketAdapter, MarketRecord


class CaliforniaPowerballAdapter(MarketAdapter):
    PAGE_URL = "https://www.calottery.com/en/draw-games/powerball"
    GAME = "Powerball"

    def fetch_records(self) -> Iterable[MarketRecord]:
        html, _ = fetch_html(self.PAGE_URL)
        parser = make_html_parser(html)

        # Draw date at card header
        date_node = parser.css_first(".draw-cards--draw-date")
        draw_date = self._parse_date(date_node.text(strip=True) if date_node else "")
        if draw_date is None:
            return []

        # Last draw detail table
        table = parser.css_first("table.table-last-draw")
        jackpot = None
        total_payout = 0.0
        if table is not None:
            for row in table.css("tbody tr"):
                cells = [c.text(strip=True) for c in row.css("td")]
                if len(cells) != 3:
                    continue
                tier, winners_raw, prize_raw = cells
                prize_value = self._parse_money(prize_raw)
                winners = self._parse_int(winners_raw)
                if jackpot is None and tier.lower().startswith("5 +"):
                    jackpot = prize_value
                if prize_value is not None and winners is not None:
                    total_payout += prize_value * winners

        revenue = total_payout if total_payout > 0 else None

        yield MarketRecord(
            state=self.state,
            date=draw_date,
            revenue=revenue,
            jackpot=jackpot,
            ticket_price=2.0,
            source_name=f"California Lottery - {self.GAME}",
            uri=self.PAGE_URL,
            game=self.GAME,
        )

    @staticmethod
    def _parse_date(value: str):
        if not value:
            return None
        if "/" in value:
            value = value.split("/", 1)[-1].strip()
        try:
            return datetime.strptime(value, "%b %d, %Y").date()
        except ValueError:
            return None

    @staticmethod
    def _parse_money(raw: str | None) -> float | None:
        if not raw:
            return None
        text = raw.strip().lower().replace("$", "").replace(",", "")
        multiplier = 1.0
        if "million" in text:
            multiplier = 1_000_000.0
            text = text.replace("million", "").strip()
        if "billion" in text:
            multiplier = 1_000_000_000.0
            text = text.replace("billion", "").strip()
        try:
            return float(text) * multiplier
        except ValueError:
            return None

    @staticmethod
    def _parse_int(raw: str | None) -> int | None:
        if not raw:
            return None
        try:
            return int(raw.replace(",", ""))
        except ValueError:
            return None


