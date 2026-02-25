from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .http_utils import fetch_html, make_html_parser
from .market_base import MarketAdapter, MarketRecord


class CaliforniaLotteryMarketAdapter(MarketAdapter):
    """Scrape the SuperLotto Plus landing page for last draw metrics."""

    PAGE_URL = "https://www.calottery.com/en/draw-games/superlotto-plus"
    GAME = "SuperLotto Plus"

    def fetch_records(self) -> Iterable[MarketRecord]:
        html, _ = fetch_html(self.PAGE_URL)
        parser = make_html_parser(html)

        card = parser.css_first("#winningNumbers8")
        if card is None:
            raise RuntimeError("未找到加州超级乐透开奖信息模块")

        date_node = card.css_first(".draw-cards--draw-date")
        draw_date = self._parse_date(date_node.text(strip=True) if date_node else "")
        if draw_date is None:
            return []

        table = parser.css_first("table.table-last-draw")
        jackpot = None
        total_payout = 0.0
        if table is not None:
            for row in table.css("tbody tr"):
                cells = [cell.text(strip=True) for cell in row.css("td")]
                if len(cells) != 3:
                    continue
                tier, tickets_raw, prize_raw = cells
                prize_value = self._parse_money(prize_raw)
                tickets_value = self._parse_int(tickets_raw)
                if jackpot is None and tier.lower().startswith("5"):
                    jackpot = prize_value
                if prize_value is not None and tickets_value is not None:
                    total_payout += prize_value * tickets_value

        revenue = total_payout if total_payout > 0 else None

        yield MarketRecord(
            state=self.state,
            date=draw_date,
            revenue=revenue,
            jackpot=jackpot,
            ticket_price=1.0,
            source_name="California Lottery - SuperLotto Plus",
            uri=self.PAGE_URL,
            game=self.GAME,
        )

    @staticmethod
    def _parse_date(value: str) -> datetime.date | None:
        if not value:
            return None
        if "/" in value:
            parts = value.split("/", 1)
            value = parts[1] if len(parts) > 1 else parts[0]
        value = value.replace("\xa0", " ").strip()
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


