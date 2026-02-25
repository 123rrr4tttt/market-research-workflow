from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Iterable, Mapping

from ...http.client import default_http_client
from ....settings.config import settings
from .market_base import MarketAdapter, MarketRecord


logger = logging.getLogger(__name__)


class MagayoCaliforniaAdapter(MarketAdapter):
    """Fetch California draw information via Magayo Lottery API."""

    RESULTS_ENDPOINT = "https://api.magayo.com/api/results.php"

    DEFAULT_GAMES: Mapping[str, str] = {
        "SuperLotto Plus": "us_ca_lotto",
        "Powerball": "us_powerball",
        "Mega Millions": "us_mega_millions",
        "Daily 4": "us_ca_daily4",
        "Fantasy 5": "us_ca_fantasy",
        "Daily 3 Midday": "us_ca_daily3_mid",
        "Daily 3 Evening": "us_ca_daily3_eve",
    }

    def __init__(self, state: str, game_codes: Mapping[str, str] | None = None):
        super().__init__(state)
        self._game_codes: Mapping[str, str] = game_codes or self.DEFAULT_GAMES

    def fetch_records(self) -> Iterable[MarketRecord]:
        api_key = settings.magayo_api_key
        if not api_key:
            logger.info("MagayoCaliforniaAdapter skipped: missing api key")
            return []

        records: list[MarketRecord] = []
        for game_name, code in self._game_codes.items():
            params = {"api_key": api_key, "game": code}
            try:
                payload = default_http_client.get_json(self.RESULTS_ENDPOINT, params=params)
            except Exception:  # noqa: BLE001
                logger.warning("magayo fetch failed", exc_info=True, extra={"game": code})
                continue

            latest = self._extract_latest(payload)
            if latest is None:
                continue

            draw_date = self._parse_date(latest)
            if draw_date is None:
                continue

            jackpot = _parse_float(latest.get("jackpot") or latest.get("next_jackpot"))
            sales = _parse_float(latest.get("sales") or latest.get("sale"))

            record = MarketRecord(
                state=self.state,
                game=game_name,
                date=draw_date,
                sales_volume=sales,
                revenue=sales,
                jackpot=jackpot,
                source_name="Magayo Lottery API",
                uri=self.RESULTS_ENDPOINT,
                extra={"raw": latest, "game_code": code},
            )
            records.append(record)

        return records

    @staticmethod
    def _extract_latest(payload: Dict[str, object] | None) -> Dict[str, object] | None:
        if not payload or not isinstance(payload, dict):
            return None
        if payload.get("error") not in (None, "0", 0):
            logger.info("magayo payload indicates error", extra={"error": payload.get("error")})
            return None
        results = payload.get("results")
        if isinstance(results, list) and results:
            item = results[0]
            if isinstance(item, dict):
                return item
        return None

    @staticmethod
    def _parse_date(result: Mapping[str, object]) -> datetime.date | None:
        candidates = [
            result.get("draw"),
            result.get("draw_date"),
            result.get("date"),
        ]
        for raw in candidates:
            if not isinstance(raw, str):
                continue
            text = raw.strip()
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(text, fmt).date()
                except ValueError:
                    continue
        return None


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        try:
            return float(text)
        except ValueError:
            return None
    return None


