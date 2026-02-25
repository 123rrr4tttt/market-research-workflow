from __future__ import annotations

from contextlib import nullcontext
from typing import Any, Dict, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..models.base import SessionLocal
from ..models.entities import SourceLibraryItem
from ..services.projects import bind_project
from ..services.source_library import (
    list_effective_channels,
    list_effective_items,
    run_item_by_key,
    sync_shared_library_from_files,
)
from ..services.tasks import task_run_source_library_item

ScopeType = Literal["shared", "project", "effective"]

router = APIRouter(prefix="/source_library", tags=["source_library"])


class SourceLibraryItemUpsertPayload(BaseModel):
    item_key: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    channel_key: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    params: Dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    schedule: str | None = None
    extends_item_key: str | None = None
    enabled: bool = True
    extra: Dict[str, Any] = Field(default_factory=dict)


class RunItemPayload(BaseModel):
    project_key: str | None = None
    async_mode: bool = False
    override_params: Dict[str, Any] = Field(default_factory=dict)


@router.get("/channels")
def list_channels(
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> dict:
    try:
        items = list_effective_channels(scope=scope, project_key=project_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": items, "scope": scope, "project_key": project_key}


@router.get("/items")
def list_items(
    scope: ScopeType = Query(default="effective"),
    project_key: str | None = Query(default=None),
) -> dict:
    try:
        items = list_effective_items(scope=scope, project_key=project_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": items, "scope": scope, "project_key": project_key}


@router.post("/items")
def upsert_project_item(payload: SourceLibraryItemUpsertPayload, project_key: str) -> dict:
    try:
        with bind_project(project_key):
            with SessionLocal() as session:
                row = session.execute(
                    select(SourceLibraryItem).where(SourceLibraryItem.item_key == payload.item_key)
                ).scalar_one_or_none()
                if row is None:
                    row = SourceLibraryItem(item_key=payload.item_key)
                    session.add(row)

                row.name = payload.name
                row.channel_key = payload.channel_key
                row.description = payload.description
                row.params = payload.params
                row.tags = payload.tags
                row.schedule = payload.schedule
                row.extends_item_key = payload.extends_item_key
                row.enabled = payload.enabled
                row.extra = payload.extra
                session.commit()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"item_key": payload.item_key, "project_key": project_key, "ok": True}


@router.post("/items/{item_key}/run")
def run_item(item_key: str, payload: RunItemPayload) -> dict:
    try:
        project_key = (payload.project_key or "").strip()
        if not project_key:
            raise HTTPException(status_code=400, detail="project_key is required. Please select a project first.")
        if payload.async_mode:
            task = task_run_source_library_item.delay(
                item_key,
                project_key,
                payload.override_params or {},
            )
            return {"task_id": task.id, "async": True, "item_key": item_key}

        result = run_item_by_key(
            item_key=item_key,
            project_key=project_key,
            override_params=payload.override_params or {},
        )
        return {"async": False, **result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync_shared_from_files")
def sync_shared_from_files(project_key: str | None = None) -> dict:
    try:
        with (bind_project(project_key) if project_key else nullcontext()):
            result = sync_shared_library_from_files()
            return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

