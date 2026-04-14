"""List resource pool URLs with scope (shared/project/effective)."""

from __future__ import annotations

from sqlalchemy import func, select

from ...models.base import SessionLocal
from ...models.entities import ResourcePoolUrl, SharedResourcePoolUrl
from ..projects import bind_project, bind_schema


def list_urls(
    *,
    scope: str = "effective",
    project_key: str | None = None,
    source: str | None = None,
    domain: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """
    List resource pool URLs. Returns (items, total).
    scope: shared | project | effective
    """
    page_size = min(max(1, page_size), 100)
    offset = (max(1, page) - 1) * page_size

    items: list[dict] = []
    total = 0

    def _row_to_item(row: ResourcePoolUrl | SharedResourcePoolUrl, s: str) -> dict:
        return {
            "id": row.id,
            "url": row.url,
            "domain": row.domain,
            "source": row.source,
            "source_ref": row.source_ref or {},
            "scope": s,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    if scope == "shared":
        with bind_schema("public"):
            with SessionLocal() as session:
                query = select(SharedResourcePoolUrl)
                count_query = select(func.count(SharedResourcePoolUrl.id))
                if source:
                    query = query.where(SharedResourcePoolUrl.source == source)
                    count_query = count_query.where(SharedResourcePoolUrl.source == source)
                if domain:
                    query = query.where(SharedResourcePoolUrl.domain.ilike(f"%{domain}%"))
                    count_query = count_query.where(SharedResourcePoolUrl.domain.ilike(f"%{domain}%"))
                total = session.execute(count_query).scalar() or 0
                query = query.order_by(SharedResourcePoolUrl.created_at.desc()).offset(offset).limit(page_size)
                rows = session.execute(query).scalars().all()
                items = [_row_to_item(r, "shared") for r in rows]
        return items, total

    if scope == "project":
        if not project_key:
            return [], 0
        with bind_project(project_key):
            with SessionLocal() as session:
                query = select(ResourcePoolUrl)
                count_query = select(func.count(ResourcePoolUrl.id))
                if source:
                    query = query.where(ResourcePoolUrl.source == source)
                    count_query = count_query.where(ResourcePoolUrl.source == source)
                if domain:
                    query = query.where(ResourcePoolUrl.domain.ilike(f"%{domain}%"))
                    count_query = count_query.where(ResourcePoolUrl.domain.ilike(f"%{domain}%"))
                total = session.execute(count_query).scalar() or 0
                query = query.order_by(ResourcePoolUrl.created_at.desc()).offset(offset).limit(page_size)
                rows = session.execute(query).scalars().all()
                items = [_row_to_item(r, "project") for r in rows]
        return items, total

    # effective: merge shared + project, project overrides on same url
    seen_urls: set[str] = set()
    all_items: list[dict] = []
    if project_key:
        with bind_project(project_key):
            with SessionLocal() as session:
                query = select(ResourcePoolUrl)
                if source:
                    query = query.where(ResourcePoolUrl.source == source)
                if domain:
                    query = query.where(ResourcePoolUrl.domain.ilike(f"%{domain}%"))
                query = query.order_by(ResourcePoolUrl.created_at.desc())
                rows = session.execute(query).scalars().all()
                for r in rows:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        all_items.append(_row_to_item(r, "project"))
    with bind_schema("public"):
        with SessionLocal() as session:
            query = select(SharedResourcePoolUrl)
            if source:
                query = query.where(SharedResourcePoolUrl.source == source)
            if domain:
                query = query.where(SharedResourcePoolUrl.domain.ilike(f"%{domain}%"))
            query = query.order_by(SharedResourcePoolUrl.created_at.desc())
            rows = session.execute(query).scalars().all()
            for r in rows:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    all_items.append(_row_to_item(r, "shared"))
    total = len(all_items)
    items = all_items[offset : offset + page_size]
    return items, total
