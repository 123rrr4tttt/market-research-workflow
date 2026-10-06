from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from io import StringIO
from typing import NoReturn, Protocol, TypedDict, TypeGuard

from functorial_kit import Failure
from sqlalchemy import select

from mrw_functorial_kit.core.provider_port_failures import ingest_operation_failures

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
_COMMODITY_FAILURE_WITNESS = (
    "test:test_FAILURE_PRESERVED__commodity_failure_lift_preserves_original_exception"
)


class CommodityIngestResult(TypedDict):
    inserted: int
    updated: int
    skipped: int


class NumericFieldQuality(TypedDict):
    status: str
    metadata: object
    error_code: object


class NumericQualityPayload(TypedDict):
    scope: str
    data_class: str
    parsed_fields: dict[str, NumericFieldQuality]
    issues: list[str]
    quality_score: float
    source: str


class _MarketMetricPointRow(Protocol):
    metric_key: str
    date: date
    value: Decimal
    unit: str | None
    currency: str | None
    source_name: str | None
    source_uri: str | None
    extra: dict[str, object] | None


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_market_metric_point_row(value: object) -> TypeGuard[_MarketMetricPointRow]:
    return isinstance(value, MarketMetricPoint)


def _commodity_failure(
    message: str,
    *,
    operation: str,
    site: str,
    public_exception: str,
    **details: object,
) -> Failure:
    context: dict[str, object] = {
        "boundary_class": "SHELL_BOUNDARY_EXCEPTION",
        "failure_family": ingest_operation_failures.name,
        "operation": operation,
        "owner": site,
        "public_exception": public_exception,
        "public_message": message,
        "site": site,
        "witness": _COMMODITY_FAILURE_WITNESS,
    }
    context.update(details)
    return ingest_operation_failures.fail("commodity_collection_failed", message, context)


def _raise_commodity_failure(
    failure: Failure,
    cause: Exception | None = None,
) -> NoReturn:
    context = failure.context or {}
    required = {
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
    if (
        not ingest_operation_failures.matches(failure)
        or failure.code != "commodity_collection_failed"
        or required - set(context)
        or context.get("failure_family") != ingest_operation_failures.name
        or (
            cause is None
            and context.get("public_exception") != "TypeError"
        )
        or (
            cause is not None
            and (
                context.get("public_exception") != cause.__class__.__name__
                or context.get("public_message") != str(cause)
            )
        )
    ):
        # kit:boundary owner=ingest.commodity.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_FAILURE_PRESERVED__commodity_failure_lift_preserves_original_exception
        raise TypeError("commodity failure lift context is incomplete or inconsistent")
    if cause is None:
        public_message = str(context["public_message"])
        original = TypeError(failure.message)
        # kit:boundary owner=ingest.commodity.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_FAILURE_PRESERVED__report_and_commodity_contract_branches_are_observable
        raise TypeError(public_message) from original
    # kit:boundary owner=ingest.commodity.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_FAILURE_PRESERVED__commodity_failure_lift_preserves_original_exception
    raise cause


def _fetch_stooq_rows(symbol: str) -> Iterable[dict[str, str]]:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    text = default_http_client.get_text(url)
    reader = csv.DictReader(StringIO(text))
    for row in reader:
        yield row


def _build_numeric_quality(
    *,
    raw_value: object,
    scope: str,
    source: str,
) -> tuple[float | None, NumericQualityPayload]:
    parsed: Mapping[str, object] = extract_numeric_general(raw_value, scope=scope)
    value = parsed.get("value")
    quality_score = float(parsed.get("quality_score", 0.0))
    parsed_ok = bool(parsed.get("parsed"))
    status = "ok" if parsed_ok else "parse_failed"
    error_code = parsed.get("error_code")
    issues = [] if parsed_ok else [f"value:{error_code or 'NUMERIC_PARSE_FAILED'}"]
    quality = NumericQualityPayload(
        scope=scope,
        data_class="project_extension",
        parsed_fields={
            "value": NumericFieldQuality(
                status=status,
                metadata=parsed.get("meta", {}),
                error_code=error_code,
            )
        },
        issues=issues,
        quality_score=quality_score,
        source=source,
    )
    if not parsed_ok or value is None:
        return None, quality
    if quality_score < MIN_NUMERIC_QUALITY_SCORE:
        quality["issues"].append("value:low_quality")
        return None, quality
    return float(value), quality


def _merge_numeric_quality(
    extra: object,
    quality: NumericQualityPayload,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    if _is_object_mapping(extra):
        for key, item in extra.items():
            if isinstance(key, str):
                payload[key] = item
    existing = payload.get("numeric_quality")
    if isinstance(existing, dict):
        payload["numeric_quality"] = {
            "source": existing,
            "ingest": quality,
        }
    else:
        payload["numeric_quality"] = quality
    return payload


def ingest_commodity_metrics(
    symbols: dict[str, str] | None = None,
    limit: int = 30,
) -> CommodityIngestResult:
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

                    if existed is not None:
                        if not _is_market_metric_point_row(existed):
                            message = "MarketMetricPoint query returned an invalid row"
                            _raise_commodity_failure(
                                _commodity_failure(
                                    message,
                                    operation="query_metric_point",
                                    site="app.services.ingest.commodity.ingest_commodity_metrics",
                                    public_exception="TypeError",
                                ),
                            )
                        if Decimal(str(existed.value)) != value:
                            existed.value = value
                            existed.extra = _merge_numeric_quality(existed.extra, quality)
                            updated += 1
                        else:
                            skipped += 1
                        continue

                    point_candidate: object = MarketMetricPoint()
                    if not _is_market_metric_point_row(point_candidate):
                        message = "MarketMetricPoint ORM row does not expose commodity fields"
                        _raise_commodity_failure(
                            _commodity_failure(
                                message,
                                operation="construct_metric_point",
                                site="app.services.ingest.commodity.ingest_commodity_metrics",
                                public_exception="TypeError",
                            ),
                        )
                    point_candidate.metric_key = metric_key
                    point_candidate.date = metric_date
                    point_candidate.value = value
                    point_candidate.unit = "price"
                    point_candidate.currency = "USD"
                    point_candidate.source_name = "stooq"
                    point_candidate.source_uri = source_uri
                    point_candidate.extra = _merge_numeric_quality({"symbol": symbol}, quality)
                    session.add(point_candidate)
                    inserted += 1
            session.commit()
        result = CommodityIngestResult(inserted=inserted, updated=updated, skipped=skipped)
        complete_job(job_id, result=dict(result))
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        _raise_commodity_failure(
            _commodity_failure(
                str(exc),
                operation="ingest_commodity_metrics",
                site="app.services.ingest.commodity.ingest_commodity_metrics",
                public_exception=exc.__class__.__name__,
            ),
            exc,
        )
