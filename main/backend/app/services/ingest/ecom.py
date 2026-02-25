from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import PriceObservation, Product
from .adapters.http_utils import fetch_html
from ..job_logger import complete_job, fail_job, start_job


_PRICE_RE = re.compile(r"([0-9]+(?:\.[0-9]{1,2})?)")


def _extract_price_from_html(html: str) -> tuple[Decimal | None, str | None, str | None]:
    # Try JSON-LD first.
    script_matches = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for raw in script_matches:
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            offers = item.get("offers") if isinstance(item, dict) else None
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if isinstance(offers, dict):
                price = offers.get("price")
                currency = offers.get("priceCurrency")
                availability = offers.get("availability")
                if price:
                    try:
                        return Decimal(str(price)), currency, availability
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
                if not product.source_uri:
                    skipped += 1
                    continue
                try:
                    html, _ = fetch_html(product.source_uri)
                except Exception:
                    skipped += 1
                    continue

                price, currency, availability = _extract_price_from_html(html)
                if price is None:
                    skipped += 1
                    continue

                obs = PriceObservation(
                    product_id=product.id,
                    price=price,
                    currency=currency or product.currency,
                    availability=availability,
                    source_uri=product.source_uri,
                    extra={"collector": "jsonld_or_regex"},
                )
                session.add(obs)
                inserted += 1

            session.commit()

        result = {"inserted": inserted, "skipped": skipped}
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        raise
