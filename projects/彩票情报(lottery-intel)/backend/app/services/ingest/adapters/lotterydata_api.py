from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Iterable, Mapping

from ...http.client import default_http_client
from ....settings.config import settings
from .market_base import MarketAdapter, MarketRecord


logger = logging.getLogger(__name__)


class LotteryDataCaliforniaAdapter(MarketAdapter):
    """Fetch draw information from LotteryData.io for California games."""

    RESULTS_ENDPOINT = "https://www.lotterydata.io/api/v1/results"

    DEFAULT_GAMES: Mapping[str, str] = {
        "SuperLotto Plus": "CA_SUPER_LOTTO_PLUS",
        "Powerball": "CA_POWERBALL",
        "Mega Millions": "CA_MEGA_MILLIONS",
    }

    def __init__(self, state: str, game_codes: Mapping[str, str] | None = None):
        super().__init__(state)
        self._game_codes: Mapping[str, str] = game_codes or self.DEFAULT_GAMES

    def fetch_records(self) -> Iterable[MarketRecord]:
        api_key = settings.lotterydata_api_key
        if not api_key:
            logger.info("LotteryDataCaliforniaAdapter skipped: missing api key")
            return []

        headers = {"x-api-key": api_key}
        records: list[MarketRecord] = []

        for game_name, code in self._game_codes.items():
            params = {"game": code, "limit": "1"}
            try:
                payload = default_http_client.get_json(self.RESULTS_ENDPOINT, params=params, headers=headers)
            except Exception:  # noqa: BLE001
                logger.warning("lotterydata fetch failed", exc_info=True, extra={"game": code})
                continue

            latest = self._extract_latest(payload)
            if latest is None:
                continue

            draw_date = self._parse_date(latest)
            if draw_date is None:
                continue

            sales = _parse_float(latest.get("sales") or latest.get("sales_amount"))
            jackpot = _parse_float(latest.get("jackpot") or latest.get("current_jackpot"))

            record = MarketRecord(
                state=self.state,
                game=game_name,
                date=draw_date,
                sales_volume=sales,
                revenue=sales,
                jackpot=jackpot,
                source_name="LotteryData.io",
                uri=self.RESULTS_ENDPOINT,
                extra={"raw": latest, "game_code": code},
            )
            records.append(record)

        return records

    @staticmethod
    def _extract_latest(payload: Dict[str, object] | None) -> Dict[str, object] | None:
        if not payload or not isinstance(payload, dict):
            return None
        items = payload.get("results") or payload.get("data")
        if isinstance(items, list) and items:
            item = items[0]
            if isinstance(item, dict):
                return item
        if isinstance(payload.get("result"), dict):
            return payload["result"]  # type: ignore[index]
        return None

    @staticmethod
    def _parse_date(result: Mapping[str, object]) -> datetime.date | None:
        candidates = [
            result.get("draw_date"),
            result.get("draw"),
            result.get("date"),
        ]
        for raw in candidates:
            if not isinstance(raw, str):
                continue
            text = raw.strip()
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
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


