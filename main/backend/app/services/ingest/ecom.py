from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Iterable, Protocol, runtime_checkable, TypeGuard

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import PriceObservation, Product
from ..extraction.numeric_general import extract_numeric_general
from ..resource_pool.http_port import fetch_html
from ..job_logger import complete_job, fail_job, start_job


_PRICE_RE = re.compile(r"([0-9]+(?:\.[0-9]{1,2})?)")
MIN_NUMERIC_QUALITY_SCORE = 60.0


def _is_string_key(value: object) -> bool:
    return isinstance(value, str)


@runtime_checkable
class _StringKeyInspectable(Protocol):
    def keys(self) -> Iterable[object]: ...


def _has_only_string_keys(value: object) -> bool:
    if not isinstance(value, _StringKeyInspectable):
        return False
    return all(map(_is_string_key, value.keys()))


def _is_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not _has_only_string_keys(value):
        return False
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _model_value(row: object, field: str) -> object:
    return getattr(row, field, None)


def _extract_price_from_html(html: str) -> tuple[Decimal | None, str | None, str | None]:
    # Try JSON-LD first.
    script_matches = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for raw in script_matches:
        try:
            payload: object = json.loads(raw)
        except Exception:
            continue
        items = payload if _is_object_list(payload) else [payload]
        for item in items:
            offers = item.get("offers") if _is_object_dict(item) else None
            if _is_object_list(offers) and offers:
                offers = offers[0]
            if _is_object_dict(offers):
                price = offers.get("price")
                currency = offers.get("priceCurrency")
                availability = offers.get("availability")
                if price:
                    try:
                        return (
                            Decimal(str(price)),
                            str(currency) if currency is not None else None,
                            str(availability) if availability is not None else None,
                        )
                    except Exception:
                        pass

    # Fallback regex.
    m = _PRICE_RE.search(html)
    if m:
        try:
            return Decimal(m.group(1)), None, None
        except Exception:
            return None, None, None
    return None, None, None


def _build_numeric_quality(*, raw_value: Any, scope: str, source: str) -> tuple[Decimal | None, dict[str, Any]]:
    parsed = extract_numeric_general(raw_value, scope=scope)
    value = parsed.get("value")
    quality_score = float(parsed.get("quality_score", 0.0))
    status = "ok" if parsed.get("parsed") else "parse_failed"
    issues: list[str] = [] if parsed.get("parsed") else [f"price:{parsed.get('error_code', 'NUMERIC_PARSE_FAILED')}"]
    quality: dict[str, object] = {
        "scope": scope,
        "data_class": "project_extension",
        "parsed_fields": {
            "price": {
                "status": status,
                "metadata": parsed.get("meta", {}),
                "error_code": parsed.get("error_code"),
            }
        },
        "issues": issues,
        "quality_score": quality_score,
        "source": source,
    }
    if not parsed.get("parsed") or value is None:
        return None, quality
    if quality_score < MIN_NUMERIC_QUALITY_SCORE:
        issues.append("price:low_quality")
        return None, quality
    return Decimal(str(value)), quality


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


def collect_ecom_price_observations(limit: int = 100) -> dict[str, Any]:
    job_id = start_job("ecom_price_observations", {"limit": limit})
    inserted = 0
    skipped = 0

    try:
        with SessionLocal() as session:
            products = session.execute(
                select(Product).where(Product.enabled == True).order_by(Product.id.asc()).limit(limit)
            ).scalars().all()

            for product in products:
                source_uri = str(_model_value(product, "source_uri") or "").strip()
                if not source_uri:
                    skipped += 1
                    continue
                try:
                    html, _ = fetch_html(source_uri)
                except Exception:
                    skipped += 1
                    continue

                price, currency, availability = _extract_price_from_html(html)
                if price is None:
                    skipped += 1
                    continue
                normalized_price, quality = _build_numeric_quality(
                    raw_value=price,
                    scope="ecom.price",
                    source="ingest_ecom_normalize",
                )
                if normalized_price is None:
                    skipped += 1
                    continue

                obs = PriceObservation()
                setattr(obs, "product_id", _model_value(product, "id"))
                setattr(obs, "price", normalized_price)
                setattr(obs, "currency", currency or _model_value(product, "currency"))
                setattr(obs, "availability", availability)
                setattr(obs, "source_uri", source_uri)
                setattr(obs, "extra", _merge_numeric_quality({"collector": "jsonld_or_regex"}, quality))
                session.add(obs)
                inserted += 1

            session.commit()

        result = {"inserted": inserted, "skipped": skipped}
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        # kit:boundary owner=ingest.ecom class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_ingest_service_a_failure_lifts
        raise
