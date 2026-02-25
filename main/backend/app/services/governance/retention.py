from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete

from ...models.base import SessionLocal
from ...models.entities import Document, MarketMetricPoint, PriceObservation, EtlJobRun


def cleanup_old_data(retention_days: int = 90) -> dict[str, int]:
    cutoff_dt = datetime.utcnow() - timedelta(days=max(1, retention_days))
    cutoff_date = cutoff_dt.date()

    with SessionLocal() as session:
        res_docs = session.execute(
            delete(Document).where(Document.created_at < cutoff_dt)
        )
        res_metrics = session.execute(
            delete(MarketMetricPoint).where(MarketMetricPoint.date < cutoff_date)
        )
        res_prices = session.execute(
            delete(PriceObservation).where(PriceObservation.captured_at < cutoff_dt)
        )
        res_jobs = session.execute(
            delete(EtlJobRun).where(EtlJobRun.started_at < cutoff_dt)
        )
        session.commit()

    return {
        "documents_deleted": res_docs.rowcount or 0,
        "metrics_deleted": res_metrics.rowcount or 0,
        "prices_deleted": res_prices.rowcount or 0,
        "jobs_deleted": res_jobs.rowcount or 0,
    }
