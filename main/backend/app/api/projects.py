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


class InjectInitialProjectPayload(BaseModel):
    project_key: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    source_project_key: str = Field(default="demo_proj", min_length=1, max_length=64)
    overwrite: bool = False
    activate: bool = True


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

# Seed/inject path uses a safe subset of tenant tables (exclude embeddings/vector + llm configs).
INITIAL_PROJECT_TABLES = [
    Source.__table__,
    Document.__table__,
    MarketStat.__table__,
    ConfigState.__table__,
    SearchHistory.__table__,
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


@router.post("/inject-initial")
def inject_initial_project(payload: InjectInitialProjectPayload) -> dict:
    source_key = _normalize_project_key(payload.source_project_key)
    if not source_key:
        raise HTTPException(status_code=400, detail="source_project_key is required")
    target_key = _normalize_project_key(payload.project_key or f"{source_key}_{int(__import__('time').time())}")
    if target_key in ("public", "default"):
        raise HTTPException(status_code=409, detail="project_key is reserved")
    source_schema = project_schema_name(source_key)
    target_schema = project_schema_name(target_key)
    target_name = (payload.name or f"{source_key}（初始注入）").strip()

    with engine.begin() as conn:
        source_exists = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name=:s)"),
            {"s": source_schema},
        ).scalar()
        if not source_exists:
            raise HTTPException(status_code=404, detail=f"source project schema not found: {source_schema}")

    with bind_schema("public"):
        with SessionLocal() as session:
            src_project = session.execute(select(Project).where(Project.project_key == source_key)).scalar_one_or_none()
            if src_project is None:
                raise HTTPException(status_code=404, detail=f"source project not found: {source_key}")

            existed = session.execute(select(Project).where(Project.project_key == target_key)).scalar_one_or_none()
            if existed and not payload.overwrite:
                raise HTTPException(status_code=409, detail="project_key already exists (set overwrite=true)")

            if existed and payload.overwrite:
                session.delete(existed)
                session.commit()
                with engine.begin() as conn:
                    conn.execute(text(f'DROP SCHEMA IF EXISTS "{target_schema}" CASCADE'))

            row = Project(
                project_key=target_key,
                name=target_name,
                schema_name=target_schema,
                enabled=True,
                is_active=False,
            )
            session.add(row)
            session.commit()
            session.refresh(row)

    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{target_schema}"'))
        conn.execute(text(f'SET search_path TO "{target_schema}"'))
        Base.metadata.create_all(bind=conn, tables=INITIAL_PROJECT_TABLES, checkfirst=True)

        copied_counts: dict[str, int] = {}
        # Copy only tables that exist in source schema.
        for table in INITIAL_PROJECT_TABLES:
            tname = table.name
            source_table_exists = conn.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema=:schema AND table_name=:table)"
                ),
                {"schema": source_schema, "table": tname},
            ).scalar()
            if not source_table_exists:
                copied_counts[tname] = 0
                continue
            conn.execute(text(f'TRUNCATE TABLE "{target_schema}"."{tname}" RESTART IDENTITY CASCADE'))
            inserted = conn.execute(
                text(f'INSERT INTO "{target_schema}"."{tname}" SELECT * FROM "{source_schema}"."{tname}"')
            )
            copied_counts[tname] = int(getattr(inserted, "rowcount", 0) or 0)
            # best-effort sequence alignment for id-based tables
            try:
                conn.execute(
                    text(
                        """
                        DO $$
                        DECLARE seq_name text;
                        BEGIN
                          SELECT pg_get_serial_sequence(format('%I.%I', :schema_name, :table_name), 'id') INTO seq_name;
                          IF seq_name IS NOT NULL THEN
                            EXECUTE format(
                              'SELECT setval(%L, COALESCE((SELECT MAX(id) FROM %I.%I), 0) + 1, false)',
                              seq_name, :schema_name, :table_name
                            );
                          END IF;
                        END$$;
                        """
                    ),
                    {"schema_name": target_schema, "table_name": tname},
                )
            except Exception:
                # not all copied tables have id sequences; ignore
                pass

    if payload.activate:
        with bind_schema("public"):
            with SessionLocal() as session:
                all_rows = session.execute(select(Project)).scalars().all()
                for p in all_rows:
                    p.is_active = p.project_key == target_key
                session.commit()

    return {
        "project_key": target_key,
        "name": target_name,
        "schema_name": target_schema,
        "source_project_key": source_key,
        "activated": bool(payload.activate),
        "copied_counts": copied_counts,
    }


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
