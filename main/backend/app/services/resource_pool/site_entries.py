"""List and upsert resource pool site entries with scope (shared/project/effective)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select

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


def simplify_site_entries(
    *,
    scope: str,
    project_key: str | None = None,
    domain: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Merge obvious duplicate site entries to keep the pool smaller.
    Conservative strategy:
    - domain_root/rss/sitemap merge by (domain, entry_type)
    - search_template / official_api merge only when template matches
    """
    if scope not in {"shared", "project"}:
        raise ValueError("scope must be 'shared' or 'project'")
    if scope == "project" and not project_key:
        raise ValueError("project_key is required for project scope")

    model = SharedResourcePoolSiteEntry if scope == "shared" else ResourcePoolSiteEntry
    ctx = bind_schema("public") if scope == "shared" else bind_project(project_key)

    def _group_key(row) -> tuple[str, ...]:
        d = (row.domain or "").strip().lower()
        et = (row.entry_type or "domain_root").strip().lower()
        if et in {"domain_root", "rss", "sitemap"}:
            return (d, et)
        tpl = (row.template or "").strip()
        return (d, et, tpl or row.site_url)

    def _row_score(row) -> tuple:
        url = (row.site_url or "").lower()
        return (
            1 if bool(row.enabled) else 0,
            1 if url.startswith("https://") else 0,
            1 if (row.source or "") == "manual" else 0,
            1 if (row.entry_type or "") == "search_template" else 0,
            int(getattr(row, "updated_at", None).timestamp()) if getattr(row, "updated_at", None) else 0,
            int(row.id or 0),
        )

    with ctx:
        with SessionLocal() as session:
            query = select(model)
            if domain:
                query = query.where(model.domain.ilike(f"%{domain}%"))
            rows = session.execute(query.order_by(model.created_at.desc())).scalars().all()
            groups: dict[tuple[str, ...], list[Any]] = {}
            for row in rows:
                groups.setdefault(_group_key(row), []).append(row)

            merged_groups = 0
            deleted_rows = 0
            kept_rows = 0
            samples: list[dict[str, Any]] = []

            for key, members in groups.items():
                if len(members) <= 1:
                    continue
                members = sorted(members, key=_row_score, reverse=True)
                keeper = members[0]
                dupes = members[1:]
                kept_rows += 1
                merged_groups += 1
                deleted_rows += len(dupes)

                merged_tags: list[str] = []
                merged_urls: list[str] = []
                merged_source_refs: list[Any] = []
                merged_caps: dict[str, Any] = dict(keeper.capabilities or {})
                for m in members:
                    for t in (m.tags or []):
                        if t not in merged_tags:
                            merged_tags.append(t)
                    if m.site_url and m.site_url not in merged_urls:
                        merged_urls.append(m.site_url)
                    if m.source_ref and m.source_ref not in merged_source_refs:
                        merged_source_refs.append(m.source_ref)
                    for ck, cv in (m.capabilities or {}).items():
                        if isinstance(cv, bool):
                            merged_caps[ck] = bool(merged_caps.get(ck)) or cv
                        elif cv is not None and ck not in merged_caps:
                            merged_caps[ck] = cv

                sample = {
                    "group_key": list(key),
                    "keeper_id": keeper.id,
                    "keeper_site_url": keeper.site_url,
                    "merged_count": len(dupes),
                    "merged_site_urls": merged_urls,
                }
                if len(samples) < 20:
                    samples.append(sample)

                if dry_run:
                    continue

                extra = dict(keeper.extra or {})
                extra["merged_site_urls"] = merged_urls
                extra["simplified_duplicate_count"] = len(dupes)
                if merged_source_refs:
                    extra["merged_source_refs"] = merged_source_refs[:50]
                keeper.tags = merged_tags
                keeper.capabilities = merged_caps
                keeper.source_ref = keeper.source_ref or {}
                keeper.extra = extra

                dup_ids = [d.id for d in dupes if d.id is not None]
                if dup_ids:
                    session.execute(delete(model).where(model.id.in_(dup_ids)))

            if not dry_run:
                session.commit()

            return {
                "scope": scope,
                "project_key": project_key if scope == "project" else None,
                "dry_run": bool(dry_run),
                "groups_merged": merged_groups,
                "rows_deleted": deleted_rows,
                "rows_kept": kept_rows,
                "samples": samples,
            }
