from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin
from typing import Iterable

from .http_utils import fetch_html, make_html_parser
from .market_base import MarketAdapter, MarketRecord


class TexasLotteryMarketAdapter(MarketAdapter):
    """Scrape Powerball draw information from Texas Lottery site."""

    PAGE_URL = "https://www.texaslottery.com/export/sites/lottery/Games/Powerball/index.html"
    MAX_ROWS = 30

    def fetch_records(self) -> Iterable[MarketRecord]:
        html, _ = fetch_html(self.PAGE_URL)
        parser = make_html_parser(html)

        table = parser.css_first("#PastResults table tbody")
        if table is None:
            raise RuntimeError("未找到德州 Powerball 历史开奖表格")

        count = 0
        for row in table.css("tr"):
            cells = [cell.text(strip=True) for cell in row.css("td")]
            if len(cells) < 5:
                continue

            date = self._parse_date(cells[0])
            if date is None:
                continue

            jackpot = self._parse_money(cells[4])

            link_node = row.css_first("a.detailsLink")
            href = link_node.attributes.get("href") if link_node else None
            uri = urljoin(self.PAGE_URL, href) if href else self.PAGE_URL

            yield MarketRecord(
                state=self.state,
                date=date,
                jackpot=jackpot,
                ticket_price=2.0,
                source_name="Texas Lottery - Powerball",
                uri=uri,
                game="Powerball",
            )

            count += 1
            if count >= self.MAX_ROWS:
                break

    @staticmethod
    def _parse_date(value: str) -> datetime.date | None:
        try:
            return datetime.strptime(value, "%m/%d/%Y").date()
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


