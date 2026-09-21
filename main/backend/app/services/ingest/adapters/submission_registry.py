"""Persistence adapter for the ingest submission registry.

The API layer owns HTTP/request orchestration.  This module owns project-bound
database sessions, row projection, and transaction boundaries.
"""

from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
import hashlib
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from ....models.base import SessionLocal
from ....models.ingest_registry import IngestSubmissionRegistry
from ...projects import bind_project


def submission_id_for_key(registry_key: str) -> str:
    return f"sub_{hashlib.sha256(registry_key.encode('utf-8')).hexdigest()[:20]}"


def project_key_from_registry_key(registry_key: str) -> str | None:
    parts = str(registry_key or "").split(":", 2)
    if len(parts) >= 3 and parts[1].strip():
        return parts[1].strip()
    return None


def row_to_submission(row: IngestSubmissionRegistry) -> dict[str, Any]:
    response_payload = row.response_payload if isinstance(row.response_payload, dict) else None
    submission: dict[str, Any] = {
        "submission_id": row.submission_id,
        "idempotency_key": row.idempotency_key,
        "trigger_type": row.trigger_type,
        "project_key": row.project_key,
        "registry_key": row.registry_key,
        "request_hash": row.request_hash,
        "subject": dict(row.subject_payload or {}),
        "submission_status": row.status or "submitted",
        "status": row.status or "submitted",
        "task_id": row.task_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "registry_backend": "db",
        "registry_degraded": False,
    }
    if response_payload is not None:
        submission["response"] = deepcopy(response_payload)
    return submission


def reserve_submission_db(
    *,
    registry_key: str,
    project_key: str,
    idempotency_key: str,
    trigger_type: str,
    subject: dict[str, Any],
    request_payload: dict[str, Any],
    request_hash: str,
) -> tuple[dict[str, Any], bool]:
    with bind_project(project_key):
        with SessionLocal() as session:
            existing = session.execute(
                select(IngestSubmissionRegistry).where(
                    IngestSubmissionRegistry.project_key == project_key,
                    IngestSubmissionRegistry.trigger_type == trigger_type,
                    IngestSubmissionRegistry.idempotency_key == idempotency_key,
                )
            ).scalar_one_or_none()
            if existing is not None:
                return row_to_submission(existing), True

            row = IngestSubmissionRegistry(
                project_key=project_key,
                trigger_type=trigger_type,
                registry_key=registry_key,
                idempotency_key=idempotency_key,
                submission_id=submission_id_for_key(registry_key),
                status="submitted",
                request_hash=request_hash,
                request_payload=deepcopy(request_payload),
                subject_payload=deepcopy(subject),
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.execute(
                    select(IngestSubmissionRegistry).where(
                        IngestSubmissionRegistry.project_key == project_key,
                        IngestSubmissionRegistry.trigger_type == trigger_type,
                        IngestSubmissionRegistry.idempotency_key == idempotency_key,
                    )
                ).scalar_one()
                return row_to_submission(existing), True
            session.refresh(row)
            return row_to_submission(row), False


def complete_submission_db(*, registry_key: str, response_payload: dict[str, Any]) -> None:
    project_key = project_key_from_registry_key(registry_key)
    context = bind_project(project_key) if project_key else nullcontext()
    with context:
        with SessionLocal() as session:
            row = session.execute(
                select(IngestSubmissionRegistry).where(
                    IngestSubmissionRegistry.registry_key == registry_key
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.response_payload = deepcopy(response_payload)
            if response_payload.get("task_id") is not None:
                row.task_id = str(response_payload.get("task_id"))
            if response_payload.get("status") is not None:
                row.status = str(response_payload.get("status"))
            session.commit()


def forget_submission_db(*, registry_key: str) -> None:
    project_key = project_key_from_registry_key(registry_key)
    context = bind_project(project_key) if project_key else nullcontext()
    with context:
        with SessionLocal() as session:
            session.execute(
                delete(IngestSubmissionRegistry).where(
                    IngestSubmissionRegistry.registry_key == registry_key
                )
            )
            session.commit()


def list_recent_submissions_db(limit: int) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = (
            session.execute(
                select(IngestSubmissionRegistry)
                .order_by(IngestSubmissionRegistry.updated_at.desc().nullslast())
                .limit(limit)
            )
            .scalars()
            .all()
        )
    return [row_to_submission(row) for row in rows]
