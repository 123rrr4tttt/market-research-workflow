from __future__ import annotations

from datetime import datetime
from typing import Iterable

from selectolax.parser import HTMLParser

from ...http.client import HttpClient
from .market_base import MarketAdapter, MarketRecord


class USPowerballAdapter(MarketAdapter):
    """Fetch recent national Powerball results from powerball.com."""

    RECENT_URL = "https://www.powerball.com/api/v1/numbers/powerball/recent?_format=json"
    SOURCE_NAME = "Powerball.com Recent Results"

    def __init__(self, state: str):
        super().__init__(state)
        self.http_client = HttpClient()

    def fetch_records(self, limit: int = 10) -> Iterable[MarketRecord]:
        headers = {"X-Requested-With": "XMLHttpRequest"}
        html = self.http_client.get_text(self.RECENT_URL, headers=headers, follow_redirects=True)
        tree = HTMLParser(html)

        cards = tree.css("a.card")
        for card in cards[:limit]:
            title_node = card.css_first("h5.card-title")
            if not title_node:
                continue

            date_text = title_node.text(strip=True)
            try:
                draw_date = datetime.strptime(date_text, "%a, %b %d, %Y").date()
            except ValueError:
                continue

            white_balls = [n.text(strip=True) for n in card.css(".white-balls")]
            powerball_node = card.css_first(".powerball")
            powerball_num = powerball_node.text(strip=True) if powerball_node else None

            multiplier = None
            multiplier_node = card.css_first(".power-play .multiplier")
            if multiplier_node:
                multiplier = multiplier_node.text(strip=True)

            extra = {
                "white_balls": white_balls,
                "powerball": powerball_num,
                "multiplier": multiplier,
            }

            yield MarketRecord(
                state=self.state,
                date=draw_date,
                game="Powerball US",
                jackpot=None,
                sales_volume=None,
                revenue=None,
                ticket_price=None,
                draw_number=None,
                extra=extra,
                source_name=self.SOURCE_NAME,
                uri=card.attributes.get("href"),
            )


