"""Persistence adapter for the ingest submission registry.

The API layer owns HTTP/request orchestration.  This module owns project-bound
database sessions, row projection, and transaction boundaries.
"""

from __future__ import annotations

import hashlib
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime
from typing import NoReturn, Protocol, TypeAlias, TypeGuard, runtime_checkable

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ....models.base import SessionLocal
from ....models.ingest_registry import IngestSubmissionRegistry
from ...projects import bind_project

SubmissionJsonObject: TypeAlias = dict[str, object]


class MaterialIngestRegistryError(RuntimeError):
    """Base typed failure for product ingest submission persistence."""

    def __init__(
        self,
        message: str,
        *,
        registry_key: str | None = None,
        request_hash: str | None = None,
    ) -> None:
        super().__init__(message)
        self.registry_key = registry_key
        self.request_hash = request_hash


class MaterialIngestRegistryConflictError(MaterialIngestRegistryError):
    """A submission key is already bound to different request content."""


class MaterialIngestRegistryBackendUnavailableError(MaterialIngestRegistryError):
    """The submission backend could not answer the request."""


@runtime_checkable
class _IngestSubmissionRow(Protocol):
    submission_id: str
    idempotency_key: str
    trigger_type: str
    project_key: str
    registry_key: str
    request_hash: str

    @property
    def request_payload(self) -> object: ...

    @property
    def subject_payload(self) -> object: ...

    @property
    def response_payload(self) -> object: ...

    status: str | None
    task_id: str | None
    created_at: datetime | None
    updated_at: datetime | None


def _row(row: object) -> _IngestSubmissionRow:
    if not isinstance(row, _IngestSubmissionRow):
        raise TypeError("ingest submission registry returned an invalid row")
    required_text: tuple[object, ...] = tuple(
        getattr(row, field_name, None)
        for field_name in (
            "submission_id",
            "idempotency_key",
            "trigger_type",
            "project_key",
            "registry_key",
            "request_hash",
        )
    )
    if not all(isinstance(value, str) and value for value in required_text):
        raise TypeError("ingest submission registry row identity is invalid")
    status: object = getattr(row, "status", None)
    task_id: object = getattr(row, "task_id", None)
    created_at: object = getattr(row, "created_at", None)
    updated_at: object = getattr(row, "updated_at", None)
    if status is not None and not isinstance(status, str):
        raise TypeError("ingest submission registry row status is invalid")
    if task_id is not None and not isinstance(task_id, str):
        raise TypeError("ingest submission registry row task_id is invalid")
    if created_at is not None and not isinstance(created_at, datetime):
        raise TypeError("ingest submission registry row created_at is invalid")
    if updated_at is not None and not isinstance(updated_at, datetime):
        raise TypeError("ingest submission registry row updated_at is invalid")
    return row


def _raise_hash_conflict(*, registry_key: str, request_hash: str) -> NoReturn:
    raise MaterialIngestRegistryConflictError(
        "registry_key already exists with a different request_hash",
        registry_key=registry_key,
        request_hash=request_hash,
    )


def _raise_backend_unavailable(
    *, registry_key: str, request_hash: str, cause: SQLAlchemyError
) -> NoReturn:
    raise MaterialIngestRegistryBackendUnavailableError(
        str(cause) or cause.__class__.__name__,
        registry_key=registry_key,
        request_hash=request_hash,
    ) from cause


def _existing_submission(
    raw_row: object,
    *,
    registry_key: str,
    request_hash: str,
) -> tuple[SubmissionJsonObject, bool]:
    existing = _row(raw_row)
    if existing.request_hash != request_hash:
        _raise_hash_conflict(registry_key=registry_key, request_hash=request_hash)
    return row_to_submission(existing), True


def submission_id_for_key(registry_key: str) -> str:
    return f"sub_{hashlib.sha256(registry_key.encode('utf-8')).hexdigest()[:20]}"


def project_key_from_registry_key(registry_key: str) -> str | None:
    parts = str(registry_key or "").split(":", 2)
    if len(parts) >= 3 and parts[1].strip():
        return parts[1].strip()
    return None


def row_to_submission(raw_row: object) -> SubmissionJsonObject:
    row = _row(raw_row)
    response_payload = _string_key_object_dict(row.response_payload)
    subject_payload = _string_key_object_dict(row.subject_payload) or {}
    submission: SubmissionJsonObject = {
        "submission_id": row.submission_id,
        "idempotency_key": row.idempotency_key,
        "trigger_type": row.trigger_type,
        "project_key": row.project_key,
        "registry_key": row.registry_key,
        "request_hash": row.request_hash,
        "subject": dict(subject_payload),
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


def _string_key_object_dict(value: object) -> SubmissionJsonObject | None:
    if not _is_object_dict(value):
        return None
    result: SubmissionJsonObject = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("ingest submission registry JSON objects must use string keys")
        result[key] = item
    return result


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def reserve_submission_db(
    *,
    registry_key: str,
    project_key: str,
    idempotency_key: str,
    trigger_type: str,
    subject: SubmissionJsonObject,
    request_payload: SubmissionJsonObject,
    request_hash: str,
) -> tuple[SubmissionJsonObject, bool]:
    try:
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
                    return _existing_submission(
                        existing,
                        registry_key=registry_key,
                        request_hash=request_hash,
                    )

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
                    return _existing_submission(
                        existing,
                        registry_key=registry_key,
                        request_hash=request_hash,
                    )
                session.refresh(row)
                return row_to_submission(row), False
    except MaterialIngestRegistryConflictError:
        raise
    except SQLAlchemyError as exc:
        _raise_backend_unavailable(
            registry_key=registry_key,
            request_hash=request_hash,
            cause=exc,
        )


def complete_submission_db(*, registry_key: str, response_payload: SubmissionJsonObject) -> None:
    project_key = project_key_from_registry_key(registry_key)
    context = bind_project(project_key) if project_key else nullcontext()
    with context:
        with SessionLocal() as session:
            raw_row = session.execute(
                select(IngestSubmissionRegistry).where(
                    IngestSubmissionRegistry.registry_key == registry_key
                )
            ).scalar_one_or_none()
            if raw_row is None:
                return
            _row(raw_row)
            raw_row.response_payload = deepcopy(response_payload)
            if response_payload.get("task_id") is not None:
                raw_row.task_id = str(response_payload.get("task_id"))
            if response_payload.get("status") is not None:
                raw_row.status = str(response_payload.get("status"))
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


def list_recent_submissions_db(limit: int) -> list[SubmissionJsonObject]:
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
