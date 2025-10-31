from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import select

from ..models.base import SessionLocal
from ..models.entities import EtlJobRun


def start_job(job_type: str, params: Dict[str, Any] | None = None) -> int:
    with SessionLocal() as session:
        job = EtlJobRun(
            job_type=job_type,
            params=params or {},
            status="running",
            started_at=datetime.utcnow(),
        )
        session.add(job)
        session.commit()
        return job.id


def complete_job(job_id: int, status: str = "completed", result: Dict[str, Any] | None = None) -> None:
    with SessionLocal() as session:
        job = session.get(EtlJobRun, job_id)
        if not job:
            return
        job.status = status
        job.finished_at = datetime.utcnow()
        if result:
            params = dict(job.params or {})
            params.update(result)
            job.params = params
        session.commit()


def fail_job(job_id: int, error: str) -> None:
    with SessionLocal() as session:
        job = session.get(EtlJobRun, job_id)
        if not job:
            return
        job.status = "failed"
        job.finished_at = datetime.utcnow()
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
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                    "error": job.error,
                }
            )
        return result


