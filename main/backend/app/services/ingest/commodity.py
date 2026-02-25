from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from typing import Iterable

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import MarketMetricPoint
from ..http.client import default_http_client
from ..job_logger import complete_job, fail_job, start_job


DEFAULT_SYMBOLS: dict[str, str] = {
    "commodity.crude_oil.wti": "cl.f",
    "commodity.gold.spot": "gc.f",
    "commodity.copper.future": "hg.f",
}


def _fetch_stooq_rows(symbol: str) -> Iterable[dict[str, str]]:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    text = default_http_client.get_text(url)
    reader = csv.DictReader(StringIO(text))
    for row in reader:
        yield row


def ingest_commodity_metrics(symbols: dict[str, str] | None = None, limit: int = 30) -> dict:
    job_id = start_job("commodity_metrics", {"limit": limit})
    symbols = symbols or DEFAULT_SYMBOLS

    inserted = 0
    updated = 0
    skipped = 0

    try:
        with SessionLocal() as session:
            for metric_key, symbol in symbols.items():
                rows = list(_fetch_stooq_rows(symbol))[-max(1, limit):]
                for row in rows:
                    dt_text = (row.get("Date") or "").strip()
                    close_text = (row.get("Close") or "").strip()
                    if not dt_text or not close_text:
                        skipped += 1
                        continue
                    try:
                        metric_date = date.fromisoformat(dt_text)
                        value = Decimal(close_text)
                    except Exception:
                        skipped += 1
                        continue

                    source_uri = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
                    existed = session.execute(
                        select(MarketMetricPoint).where(
                            MarketMetricPoint.metric_key == metric_key,
                            MarketMetricPoint.date == metric_date,
                            MarketMetricPoint.source_uri == source_uri,
                        )
                    ).scalar_one_or_none()

                    if existed:
                        if Decimal(str(existed.value)) != value:
                            existed.value = value
                            updated += 1
                        else:
                            skipped += 1
                        continue

                    session.add(
                        MarketMetricPoint(
                            metric_key=metric_key,
                            date=metric_date,
                            value=value,
                            unit="price",
                            currency="USD",
                            source_name="stooq",
                            source_uri=source_uri,
                            extra={"symbol": symbol},
                        )
                    )
                    inserted += 1
            session.commit()
        result = {"inserted": inserted, "updated": updated, "skipped": skipped}
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        raise
