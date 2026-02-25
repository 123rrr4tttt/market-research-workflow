from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services.governance import cleanup_old_data
from ..services.aggregator import sync_project_data_to_aggregator
from ..services.tasks import task_sync_aggregator


router = APIRouter(prefix="/governance", tags=["governance"])


class CleanupPayload(BaseModel):
    retention_days: int = Field(default=90, ge=1, le=3650)


class AggregatorPayload(BaseModel):
    async_mode: bool = Field(default=True)


@router.post("/cleanup")
def cleanup(payload: CleanupPayload) -> dict:
    result = cleanup_old_data(retention_days=payload.retention_days)
    return {"retention_days": payload.retention_days, **result}


@router.post("/aggregator/sync")
def sync_aggregator(payload: AggregatorPayload) -> dict:
    if payload.async_mode:
        task = task_sync_aggregator.delay()
        return {"task_id": task.id, "async": True}
    result = sync_project_data_to_aggregator()
    return {"async": False, **result}
