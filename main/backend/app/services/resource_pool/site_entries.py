"""List and upsert resource pool site entries with scope (shared/project/effective)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from ...models.base import SessionLocal
from ...models.entities import ResourcePoolSiteEntry, SharedResourcePoolSiteEntry
from ..projects import bind_project, bind_schema
from .url_utils import domain_from_url, normalize_url

ScopeType = str


def _row_to_item(
    row: ResourcePoolSiteEntry | SharedResourcePoolSiteEntry,
    scope: str,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "site_url": row.site_url,
        "domain": row.domain,
        "entry_type": row.entry_type,
        "template": row.template,
        "name": row.name,
        "capabilities": row.capabilities or {},
        "source": row.source,
        "source_ref": row.source_ref or {},
        "tags": row.tags or [],
        "enabled": bool(row.enabled),
        "project_key": getattr(row, "project_key", None),
        "extra": row.extra or {},
        "scope": scope,
        "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
        "updated_at": row.updated_at.isoformat() if getattr(row, "updated_at", None) else None,
    }


def list_site_entries(
    *,
    scope: ScopeType = "effective",
    project_key: str | None = None,
    domain: str | None = None,
    entry_type: str | None = None,
    enabled: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """
    List site entries. Returns (items, total).
    scope: shared | project | effective
    """
    page_size = min(max(1, int(page_size)), 100)
    offset = (max(1, int(page)) - 1) * page_size

    def _apply_filters(query, model):
        if domain:
            query = query.where(model.domain.ilike(f"%{domain}%"))
        if entry_type:
            query = query.where(model.entry_type == entry_type)
        if enabled is not None:
            query = query.where(model.enabled.is_(enabled))
        return query

    if scope == "shared":
        with bind_schema("public"):
            with SessionLocal() as session:
                query = _apply_filters(select(SharedResourcePoolSiteEntry), SharedResourcePoolSiteEntry)
                count_query = _apply_filters(
                    select(func.count(SharedResourcePoolSiteEntry.id)),
                    SharedResourcePoolSiteEntry,
                )
                total = session.execute(count_query).scalar() or 0
                rows = (
                    session.execute(
                        query.order_by(SharedResourcePoolSiteEntry.created_at.desc()).offset(offset).limit(page_size)
                    )
                    .scalars()
                    .all()
                )
                return ([_row_to_item(r, "shared") for r in rows], total)

    if scope == "project":
        if not project_key:
            return [], 0
        with bind_project(project_key):
            with SessionLocal() as session:
                query = _apply_filters(select(ResourcePoolSiteEntry), ResourcePoolSiteEntry)
                count_query = _apply_filters(select(func.count(ResourcePoolSiteEntry.id)), ResourcePoolSiteEntry)
                total = session.execute(count_query).scalar() or 0
                rows = (
                    session.execute(
                        query.order_by(ResourcePoolSiteEntry.created_at.desc()).offset(offset).limit(page_size)
                    )
                    .scalars()
                    .all()
                )
                return ([_row_to_item(r, "project") for r in rows], total)

    # effective: merge project + shared, project overrides on same site_url
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []

    if project_key:
        with bind_project(project_key):
            with SessionLocal() as session:
                query = _apply_filters(select(ResourcePoolSiteEntry), ResourcePoolSiteEntry).order_by(
                    ResourcePoolSiteEntry.created_at.desc()
                )
                rows = session.execute(query).scalars().all()
                for r in rows:
                    if r.site_url not in seen:
                        seen.add(r.site_url)
                        merged.append(_row_to_item(r, "project"))

    with bind_schema("public"):
        with SessionLocal() as session:
            query = _apply_filters(select(SharedResourcePoolSiteEntry), SharedResourcePoolSiteEntry).order_by(
                SharedResourcePoolSiteEntry.created_at.desc()
            )
            rows = session.execute(query).scalars().all()
            for r in rows:
                if r.site_url not in seen:
                    seen.add(r.site_url)
                    merged.append(_row_to_item(r, "shared"))

    total = len(merged)
    return merged[offset : offset + page_size], total


def upsert_site_entry(
    *,
    scope: str,
    project_key: str | None,
    site_url: str,
    entry_type: str = "domain_root",
    template: str | None = None,
    name: str | None = None,
    domain: str | None = None,
    capabilities: dict[str, Any] | None = None,
    source: str = "manual",
    source_ref: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    enabled: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scope = (scope or "").strip()
    if scope not in {"shared", "project"}:
        raise ValueError("scope must be 'shared' or 'project'")

    normalized_url = normalize_url(site_url)
    if not normalized_url:
        raise ValueError("site_url is required")
    site_url = normalized_url

    if not domain:
        domain = domain_from_url(site_url)

    if scope == "shared":
        with bind_schema("public"):
            with SessionLocal() as session:
                row = session.execute(
                    select(SharedResourcePoolSiteEntry).where(SharedResourcePoolSiteEntry.site_url == site_url)
                ).scalar_one_or_none()
                if row is None:
                    row = SharedResourcePoolSiteEntry(site_url=site_url)
                    session.add(row)
                row.domain = domain
                row.entry_type = (entry_type or "domain_root").strip()
                row.template = template
                row.name = name
                row.capabilities = capabilities or {}
                row.source = (source or "manual").strip()
                row.source_ref = source_ref or {}
                row.tags = tags or []
                row.enabled = bool(enabled)
                row.extra = extra or {}
                session.commit()
                session.refresh(row)
                return _row_to_item(row, "shared")

    if not project_key:
        raise ValueError("project_key is required for project scope")

    with bind_project(project_key):
        with SessionLocal() as session:
            row = session.execute(
                select(ResourcePoolSiteEntry).where(ResourcePoolSiteEntry.site_url == site_url)
            ).scalar_one_or_none()
            if row is None:
                row = ResourcePoolSiteEntry(site_url=site_url)
                session.add(row)
            row.domain = domain
            row.entry_type = (entry_type or "domain_root").strip()
            row.template = template
            row.name = name
            row.capabilities = capabilities or {}
            row.source = (source or "manual").strip()
            row.source_ref = source_ref or {}
            row.tags = tags or []
            row.enabled = bool(enabled)
            row.project_key = project_key
            row.extra = extra or {}
            session.commit()
            session.refresh(row)
            return _row_to_item(row, "project")


def get_site_entry_by_url(
    *,
    scope: ScopeType = "effective",
    project_key: str | None = None,
    site_url: str,
) -> dict[str, Any] | None:
    """Get a site entry by site_url. Effective = project overrides shared."""
    norm = normalize_url(site_url)
    if not norm:
        return None
    site_url = norm

    if scope == "shared":
        with bind_schema("public"):
            with SessionLocal() as session:
                row = session.execute(
                    select(SharedResourcePoolSiteEntry).where(SharedResourcePoolSiteEntry.site_url == site_url)
                ).scalar_one_or_none()
                return _row_to_item(row, "shared") if row else None

    if scope == "project":
        if not project_key:
            return None
        with bind_project(project_key):
            with SessionLocal() as session:
                row = session.execute(
                    select(ResourcePoolSiteEntry).where(ResourcePoolSiteEntry.site_url == site_url)
                ).scalar_one_or_none()
                return _row_to_item(row, "project") if row else None

    # effective
    if project_key:
        with bind_project(project_key):
            with SessionLocal() as session:
                row = session.execute(
                    select(ResourcePoolSiteEntry).where(ResourcePoolSiteEntry.site_url == site_url)
                ).scalar_one_or_none()
                if row is not None:
                    return _row_to_item(row, "project")

    with bind_schema("public"):
        with SessionLocal() as session:
            row = session.execute(
                select(SharedResourcePoolSiteEntry).where(SharedResourcePoolSiteEntry.site_url == site_url)
            ).scalar_one_or_none()
            return _row_to_item(row, "shared") if row else None

