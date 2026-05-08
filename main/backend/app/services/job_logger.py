from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError

from ..models.base import SessionLocal, run_with_session_retry
from ..models.entities import EtlJobRun


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fit_job_type(job_type: str, max_len: int = 16) -> str:
    """Fit job_type into DB column length without collisions."""
    if len(job_type) <= max_len:
        return job_type
    digest = hashlib.sha1(
        job_type.encode("utf-8", errors="ignore"),
        usedforsecurity=False,
    ).hexdigest()[:4]
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

    def _op(session) -> int:
        job = EtlJobRun(
            job_type=stored_job_type,
            params=payload,
            status="running",
            external_job_id=external_job_id,
            external_provider=external_provider,
            retry_count=retry_count,
            started_at=_utcnow(),
        )
        session.add(job)
        session.flush()
        return job.id

    return run_with_session_retry(_op, log_context={"operation": "start_job", "job_type": stored_job_type})


def complete_job(
    job_id: int,
    status: str = "completed",
    result: Dict[str, Any] | None = None,
    *,
    external_job_id: str | None = None,
    external_provider: str | None = None,
    retry_count: int | None = None,
) -> None:

    def _op(session) -> None:
        job = session.get(EtlJobRun, job_id)
        if not job:
            return
        job.status = status
        job.finished_at = _utcnow()
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

    run_with_session_retry(_op, log_context={"operation": "complete_job", "job_id": job_id})


def fail_job(
    job_id: int,
    error: str,
    *,
    external_job_id: str | None = None,
    external_provider: str | None = None,
    retry_count: int | None = None,
) -> None:

    def _op(session) -> None:
        job = session.get(EtlJobRun, job_id)
        if not job:
            return
        job.status = "failed"
        job.finished_at = _utcnow()
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

    run_with_session_retry(_op, log_context={"operation": "fail_job", "job_id": job_id})


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

    def _op(session) -> None:
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
                job.finished_at = _utcnow()
        if result:
            params = dict(job.params or {})
            params.update(result)
            job.params = params
        if error is not None:
            job.error = error[:2000]

    run_with_session_retry(_op, log_context={"operation": "update_job_tracking", "job_id": job_id})


def list_jobs(limit: int = 20) -> List[dict[str, Any]]:
    with SessionLocal() as session:
        stmt = (
            select(EtlJobRun)
            .order_by(EtlJobRun.started_at.desc().nullslast())
            .limit(limit)
        )
        try:
            rows = session.execute(stmt).all()
        except ProgrammingError as exc:
            # Cold/local environments may not have ETL history table yet.
            # Gracefully degrade to empty history instead of surfacing 5xx.
            msg = str(exc).lower()
            if "does not exist" in msg and "etl_job_runs" in msg:
                return []
            raise
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
