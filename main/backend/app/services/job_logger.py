from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import select

from ..models.base import SessionLocal
from ..models.entities import EtlJobRun


def _fit_job_type(job_type: str, max_len: int = 16) -> str:
    """Fit job_type into DB column length without collisions."""
    if len(job_type) <= max_len:
        return job_type
    digest = hashlib.sha1(job_type.encode("utf-8", errors="ignore")).hexdigest()[:4]
    prefix_len = max_len - 5  # reserve "_" + 4 hex chars
    return f"{job_type[:prefix_len]}_{digest}"


def start_job(
    job_type: str,
    params: Dict[str, Any] | None = None,
    *,
    external_job_id: str | None = None,
    external_provider: str | None = None,
    retry_count: int | None = None,
) -> int:
    stored_job_type = _fit_job_type(job_type)
    payload = dict(params or {})
    if stored_job_type != job_type:
        payload.setdefault("job_type_full", job_type)
    with SessionLocal() as session:
        job = EtlJobRun(
            job_type=stored_job_type,
            params=payload,
            status="running",
            external_job_id=external_job_id,
            external_provider=external_provider,
            retry_count=retry_count,
            started_at=datetime.utcnow(),
        )
        session.add(job)
        session.commit()
        return job.id


def complete_job(
    job_id: int,
    status: str = "completed",
    result: Dict[str, Any] | None = None,
    *,
    external_job_id: str | None = None,
    external_provider: str | None = None,
    retry_count: int | None = None,
) -> None:
    with SessionLocal() as session:
        job = session.get(EtlJobRun, job_id)
        if not job:
            return
        job.status = status
        job.finished_at = datetime.utcnow()
        if external_job_id is not None:
            job.external_job_id = external_job_id
        if external_provider is not None:
            job.external_provider = external_provider
        if retry_count is not None:
            job.retry_count = retry_count
        if result:
            params = dict(job.params or {})
            params.update(result)
            job.params = params
        session.commit()


def fail_job(
    job_id: int,
    error: str,
    *,
    external_job_id: str | None = None,
    external_provider: str | None = None,
    retry_count: int | None = None,
) -> None:
    with SessionLocal() as session:
        job = session.get(EtlJobRun, job_id)
        if not job:
            return
        job.status = "failed"
        job.finished_at = datetime.utcnow()
        job.error = error[:2000]
        params = dict(job.params or {})
        # Keep a stable machine-readable fallback for process observability.
        params.setdefault("error_code", "TASK_FAILED")
        job.params = params
        if external_job_id is not None:
            job.external_job_id = external_job_id
        if external_provider is not None:
            job.external_provider = external_provider
        if retry_count is not None:
            job.retry_count = retry_count
        session.commit()


def update_job_tracking(
    job_id: int,
    *,
    external_job_id: str | None = None,
    external_provider: str | None = None,
    retry_count: int | None = None,
    status: str | None = None,
    result: Dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    with SessionLocal() as session:
        job = session.get(EtlJobRun, job_id)
        if not job:
            return
        if external_job_id is not None:
            job.external_job_id = external_job_id
        if external_provider is not None:
            job.external_provider = external_provider
        if retry_count is not None:
            job.retry_count = retry_count
        if status is not None:
            job.status = status
            if status in {"completed", "failed", "cancelled"} and not job.finished_at:
                job.finished_at = datetime.utcnow()
        if result:
            params = dict(job.params or {})
            params.update(result)
            job.params = params
        if error is not None:
            job.error = error[:2000]
        session.commit()


def list_jobs(limit: int = 20) -> List[dict[str, Any]]:
    with SessionLocal() as session:
        stmt = (
            select(EtlJobRun)
            .order_by(EtlJobRun.started_at.desc().nullslast())
            .limit(limit)
        )
        rows = session.execute(stmt).all()
        result: List[dict[str, Any]] = []
        for (job,) in rows:
            result.append(
                {
                    "id": job.id,
                    "job_type": job.job_type,
                    "status": job.status,
                    "params": job.params,
                    "external_job_id": job.external_job_id,
                    "external_provider": job.external_provider,
                    "retry_count": job.retry_count,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                    "error": job.error,
                }
            )
        return result
