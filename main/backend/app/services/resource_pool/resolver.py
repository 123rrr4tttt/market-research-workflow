"""List resource pool URLs with scope (shared/project/effective)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from ...models.base import SessionLocal
from ...models.entities import ResourcePoolUrl, SharedResourcePoolUrl
from ..projects import bind_project, bind_schema


def _row_text(value: object) -> str:
    return value if isinstance(value, str) else str(value or "")


def _row_optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _row_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _row_datetime(value: object) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def list_urls(
    *,
    scope: str = "effective",
    project_key: str | None = None,
    source: str | None = None,
    domain: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, object]], int]:
    """
    List resource pool URLs. Returns (items, total).
    scope: shared | project | effective
    """
    page_size = min(max(1, page_size), 100)
    offset = (max(1, page) - 1) * page_size

    items: list[dict[str, object]] = []
    total = 0

    def _row_to_item(
        row: ResourcePoolUrl | SharedResourcePoolUrl,
        item_scope: str,
    ) -> dict[str, object]:
        source_ref_value: object = row.source_ref
        return {
            "id": _row_int(row.id),
            "url": _row_text(row.url),
            "domain": _row_optional_text(row.domain),
            "source": _row_text(row.source),
            "source_ref": source_ref_value or {},
            "scope": item_scope,
            "created_at": _row_datetime(row.created_at),
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
                count_value: object = session.execute(count_query).scalar()
                total = count_value if isinstance(count_value, int) else 0
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
                count_value = session.execute(count_query).scalar()
                total = count_value if isinstance(count_value, int) else 0
                query = query.order_by(ResourcePoolUrl.created_at.desc()).offset(offset).limit(page_size)
                rows = session.execute(query).scalars().all()
                items = [_row_to_item(r, "project") for r in rows]
        return items, total

    # effective: merge shared + project, project overrides on same url
    seen_urls: set[str] = set()
    all_items: list[dict[str, object]] = []
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
                    row_url = _row_text(r.url)
                    if row_url not in seen_urls:
                        seen_urls.add(row_url)
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
                row_url = _row_text(r.url)
                if row_url not in seen_urls:
                    seen_urls.add(row_url)
                    all_items.append(_row_to_item(r, "shared"))
    total = len(all_items)
    items = all_items[offset : offset + page_size]
    return items, total
