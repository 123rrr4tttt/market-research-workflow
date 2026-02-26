from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from ..models.base import SessionLocal, engine
from ..models.base import Base
from ..models.entities import (
    ConfigState,
    Document,
    Embedding,
    EtlJobRun,
    IngestChannel,
    LlmServiceConfig,
    MarketMetricPoint,
    MarketStat,
    PriceObservation,
    Product,
    Project,
    ResourcePoolUrl,
    ResourcePoolSiteEntry,
    SearchHistory,
    SourceLibraryItem,
    Source,
    Topic,
)
from ..services.projects.context import bind_schema, project_schema_name, _normalize_project_key


router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectPayload(BaseModel):
    project_key: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    enabled: bool = True


class UpdateProjectPayload(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None


TENANT_TABLES = [
    Source.__table__,
    Document.__table__,
    MarketStat.__table__,
    ConfigState.__table__,
    Embedding.__table__,
    EtlJobRun.__table__,
    SearchHistory.__table__,
    LlmServiceConfig.__table__,
    Topic.__table__,
    IngestChannel.__table__,
    SourceLibraryItem.__table__,
    MarketMetricPoint.__table__,
    Product.__table__,
    PriceObservation.__table__,
    ResourcePoolUrl.__table__,
    ResourcePoolSiteEntry.__table__,
]


@router.get("")
def list_projects() -> dict:
    # Control-plane data always read from public schema.
    with bind_schema("public"):
        with SessionLocal() as session:
            rows = session.execute(select(Project).order_by(Project.id.asc())).scalars().all()
            return {
                "items": [
                    {
                        "id": row.id,
                        "project_key": row.project_key,
                        "name": row.name,
                        "schema_name": row.schema_name,
                        "enabled": row.enabled,
                        "is_active": row.is_active,
                    }
                    for row in rows
                ]
            }


@router.post("")
def create_project(payload: CreateProjectPayload) -> dict:
    normalized_key = _normalize_project_key(payload.project_key)
    if normalized_key in ("public", "default"):
        raise HTTPException(status_code=409, detail="project_key is reserved")
    schema_name = project_schema_name(normalized_key)

    with bind_schema("public"):
        with SessionLocal() as session:
            existed = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if existed:
                raise HTTPException(status_code=409, detail="project_key already exists")

            row = Project(
                project_key=normalized_key,
                name=payload.name,
                schema_name=schema_name,
                enabled=payload.enabled,
                is_active=False,
            )
            session.add(row)
            session.commit()
            session.refresh(row)

    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        # Initialize tenant tables in target schema only.
        conn.execute(text(f'SET search_path TO "{schema_name}"'))
        Base.metadata.create_all(bind=conn, tables=TENANT_TABLES, checkfirst=True)

    return {"id": row.id, "schema_name": schema_name}


@router.patch("/{project_key}")
def update_project(project_key: str, payload: UpdateProjectPayload) -> dict:
    normalized_key = _normalize_project_key(project_key)
    with bind_schema("public"):
        with SessionLocal() as session:
            project = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if project is None:
                raise HTTPException(status_code=404, detail="project not found")

            changed = False
            if payload.name is not None:
                project.name = payload.name
                changed = True
            if payload.enabled is not None:
                project.enabled = bool(payload.enabled)
                if not project.enabled and project.is_active:
                    project.is_active = False
                changed = True

            if changed:
                session.commit()
                session.refresh(project)

            # If disabling an active project, pick a fallback active.
            if payload.enabled is False:
                active = session.execute(select(Project).where(Project.is_active == True)).scalar_one_or_none()  # noqa: E712
                if active is None:
                    fallback = (
                        session.execute(
                            select(Project)
                            .where(Project.enabled == True)  # noqa: E712
                            .order_by(Project.project_key.asc())
                        )
                        .scalars()
                        .first()
                    )
                    if fallback is not None:
                        fallback.is_active = True
                        session.commit()
                        return {"project_key": normalized_key, "fallback_active_project_key": fallback.project_key}

    return {"project_key": normalized_key}


@router.post("/{project_key}/archive")
def archive_project(project_key: str) -> dict:
    normalized_key = _normalize_project_key(project_key)
    with bind_schema("public"):
        with SessionLocal() as session:
            project = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if project is None:
                raise HTTPException(status_code=404, detail="project not found")

            project.enabled = False
            if project.is_active:
                project.is_active = False

            # Pick fallback active if needed.
            active = session.execute(select(Project).where(Project.is_active == True)).scalar_one_or_none()  # noqa: E712
            if active is None:
                fallback = (
                    session.execute(
                        select(Project)
                        .where(Project.enabled == True)  # noqa: E712
                        .order_by(Project.project_key.asc())
                    )
                    .scalars()
                    .first()
                )
                if fallback is not None:
                    fallback.is_active = True

            session.commit()

    return {"project_key": normalized_key, "archived": True}


@router.post("/{project_key}/restore")
def restore_project(project_key: str) -> dict:
    normalized_key = _normalize_project_key(project_key)
    with bind_schema("public"):
        with SessionLocal() as session:
            project = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if project is None:
                raise HTTPException(status_code=404, detail="project not found")
            project.enabled = True
            session.commit()
    return {"project_key": normalized_key, "archived": False}


@router.post("/{project_key}/activate")
def activate_project(project_key: str) -> dict:
    normalized_key = _normalize_project_key(project_key)
    with bind_schema("public"):
        with SessionLocal() as session:
            project = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if project is None:
                raise HTTPException(status_code=404, detail="project not found")
            if not project.enabled:
                raise HTTPException(status_code=409, detail="project is archived/disabled")

            all_rows = session.execute(select(Project)).scalars().all()
            for row in all_rows:
                row.is_active = row.project_key == normalized_key
            session.commit()

    return {"active_project_key": normalized_key}


@router.delete("/{project_key}")
def delete_project(project_key: str, hard: bool = Query(default=False)) -> dict:
    normalized_key = _normalize_project_key(project_key)
    if hard and normalized_key == "default":
        raise HTTPException(status_code=409, detail="default project cannot be hard-deleted")

    with bind_schema("public"):
        with SessionLocal() as session:
            project = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if project is None:
                raise HTTPException(status_code=404, detail="project not found")

            schema_name = project.schema_name
            was_active = bool(project.is_active)

            if not hard:
                # Soft-delete == archive
                project.enabled = False
                project.is_active = False
                if was_active:
                    fallback = (
                        session.execute(
                            select(Project)
                            .where(Project.enabled == True)  # noqa: E712
                            .where(Project.project_key != normalized_key)
                            .order_by(Project.project_key.asc())
                        )
                        .scalars()
                        .first()
                    )
                    if fallback is not None:
                        fallback.is_active = True
                session.commit()
                return {"project_key": normalized_key, "deleted": False, "archived": True}

            # Hard delete: remove control-plane row and drop schema
            if was_active:
                fallback = (
                    session.execute(
                        select(Project)
                        .where(Project.enabled == True)  # noqa: E712
                        .where(Project.project_key != normalized_key)
                        .order_by(Project.project_key.asc())
                    )
                    .scalars()
                    .first()
                )
                if fallback is not None:
                    fallback.is_active = True

            session.delete(project)
            session.commit()

    with engine.begin() as conn:
        # best-effort cleanup sync cursors
        conn.execute(text("DELETE FROM public.project_sync_state WHERE project_key = :k"), {"k": normalized_key})
        if schema_name:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))

    return {"project_key": normalized_key, "deleted": True, "hard": True}
