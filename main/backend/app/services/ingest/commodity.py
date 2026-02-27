from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from typing import Any, Iterable

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import MarketMetricPoint
from ..extraction.numeric_general import extract_numeric_general
from ..http.client import default_http_client
from ..job_logger import complete_job, fail_job, start_job


DEFAULT_SYMBOLS: dict[str, str] = {
    "commodity.crude_oil.wti": "cl.f",
    "commodity.gold.spot": "gc.f",
    "commodity.copper.future": "hg.f",
}
MIN_NUMERIC_QUALITY_SCORE = 60.0


def _fetch_stooq_rows(symbol: str) -> Iterable[dict[str, str]]:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    text = default_http_client.get_text(url)
    reader = csv.DictReader(StringIO(text))
    for row in reader:
        yield row


def _build_numeric_quality(*, raw_value: Any, scope: str, source: str) -> tuple[float | None, dict[str, Any]]:
    parsed = extract_numeric_general(raw_value, scope=scope)
    value = parsed.get("value")
    quality_score = float(parsed.get("quality_score", 0.0))
    status = "ok" if parsed.get("parsed") else "parse_failed"
    quality = {
        "scope": scope,
        "data_class": "project_extension",
        "parsed_fields": {
            "value": {
                "status": status,
                "metadata": parsed.get("meta", {}),
                "error_code": parsed.get("error_code"),
            }
        },
        "issues": [] if parsed.get("parsed") else [f"value:{parsed.get('error_code', 'NUMERIC_PARSE_FAILED')}"],
        "quality_score": quality_score,
        "source": source,
    }
    if not parsed.get("parsed") or value is None:
        return None, quality
    if quality_score < MIN_NUMERIC_QUALITY_SCORE:
        quality["issues"].append("value:low_quality")
        return None, quality
    return float(value), quality


def _merge_numeric_quality(extra: dict[str, Any] | None, quality: dict[str, Any]) -> dict[str, Any]:
    payload = dict(extra) if isinstance(extra, dict) else {}
    existing = payload.get("numeric_quality")
    if isinstance(existing, dict):
        payload["numeric_quality"] = {
            "source": existing,
            "ingest": quality,
        }
    else:
        payload["numeric_quality"] = quality
    return payload


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
                    except Exception:
                        skipped += 1
                        continue
                    normalized_value, quality = _build_numeric_quality(
                        raw_value=close_text,
                        scope="commodity.metric",
                        source="ingest_commodity_normalize",
                    )
                    if normalized_value is None:
                        skipped += 1
                        continue
                    value = Decimal(str(normalized_value))

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
                            existed.extra = _merge_numeric_quality(existed.extra, quality)
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
                            extra=_merge_numeric_quality({"symbol": symbol}, quality),
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
