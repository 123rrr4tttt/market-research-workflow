from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..contracts import ErrorCode, error_response
from ..contracts.responses import ok
from ..contracts.errors import map_exception_to_error
from ..services.governance import cleanup_old_data
from ..services.aggregator import sync_project_data_to_aggregator
from ..services.tasks import task_sync_aggregator
from fastapi import HTTPException


router = APIRouter(prefix="/governance", tags=["governance"])


def _raise_mapped_error(exc: Exception) -> None:
    code, message, details = map_exception_to_error(exc)
    status_code = 400 if code == ErrorCode.INVALID_INPUT else 404 if code == ErrorCode.NOT_FOUND else 429 if code == ErrorCode.RATE_LIMITED else 502 if code in {ErrorCode.UPSTREAM_ERROR, ErrorCode.PARSE_ERROR} else 500
    raise HTTPException(
        status_code=status_code,
        detail=error_response(code, message, details=details),
    ) from exc


class CleanupPayload(BaseModel):
    retention_days: int = Field(default=90, ge=1, le=3650)


class AggregatorPayload(BaseModel):
    async_mode: bool = Field(default=True)


@router.post("/cleanup")
def cleanup(payload: CleanupPayload) -> dict:
    try:
        result = cleanup_old_data(retention_days=payload.retention_days)
        return ok({"retention_days": payload.retention_days, **result})
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)


@router.post("/aggregator/sync")
def sync_aggregator(payload: AggregatorPayload) -> dict:
    try:
        if payload.async_mode:
            task = task_sync_aggregator.delay()
            return ok({"task_id": task.id, "async": True})
        result = sync_project_data_to_aggregator()
        return ok({"async": False, **result})
    except Exception as exc:  # noqa: BLE001
        _raise_mapped_error(exc)
