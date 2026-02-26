"""Extract URLs from documents and persist to resource pool."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.base import SessionLocal
from ...models.entities import Document, EtlJobRun, ResourcePoolUrl, SharedResourcePoolUrl
from ..projects import bind_project, bind_schema
from .url_utils import domain_from_url, extract_urls_from_json, extract_urls_from_text, normalize_url


def _append_urls(
    session: Session,
    urls: list[str],
    *,
    source: str,
    source_ref: dict,
    scope: str,
    project_key: str | None,
) -> tuple[int, int]:
    """Append URLs to pool. Returns (new_count, duplicate_count)."""
    new_count = 0
    dup_count = 0
    for raw in urls:
        norm = normalize_url(raw)
        if not norm:
            continue
        domain = domain_from_url(norm) or ""

        if scope == "shared":
            existing = session.execute(
                select(SharedResourcePoolUrl).where(SharedResourcePoolUrl.url == norm)
            ).scalar_one_or_none()
            if existing:
                dup_count += 1
                continue
            row = SharedResourcePoolUrl(
                url=norm,
                domain=domain[:255] if domain else None,
                source=source[:32],
                source_ref=source_ref,
            )
            session.add(row)
            new_count += 1
        else:
            existing = session.execute(
                select(ResourcePoolUrl).where(ResourcePoolUrl.url == norm)
            ).scalar_one_or_none()
            if existing:
                dup_count += 1
                continue
            row = ResourcePoolUrl(
                url=norm,
                domain=domain[:255] if domain else None,
                source=source[:32],
                source_ref=source_ref,
                project_key=project_key,
            )
            session.add(row)
            new_count += 1
    return new_count, dup_count


def extract_from_documents(
    *,
    project_key: str,
    scope: str = "project",
    doc_type: list[str] | None = None,
    state: list[str] | None = None,
    document_ids: list[int] | None = None,
    limit: int = 500,
) -> dict:
    """
    Extract URLs from Document content/extracted_data/uri and write to resource pool.
    scope: "project" | "shared"
    """
    if scope not in ("project", "shared"):
        scope = "project"

    urls_seen: set[str] = set()
    url_refs: list[tuple[str, dict]] = []  # (url, source_ref)
    doc_count = 0

    def _collect(doc: Document) -> None:
        ref = {"document_id": doc.id}
        if doc.uri:
            norm = normalize_url(doc.uri)
            if norm and norm not in urls_seen:
                urls_seen.add(norm)
                url_refs.append((norm, ref))
        if doc.content:
            for u in extract_urls_from_text(doc.content):
                norm = normalize_url(u)
                if norm and norm not in urls_seen:
                    urls_seen.add(norm)
                    url_refs.append((norm, ref))
        if doc.extracted_data:
            for u in extract_urls_from_json(doc.extracted_data):
                if u not in urls_seen:
                    urls_seen.add(u)
                    url_refs.append((u, ref))

    with bind_project(project_key):
        with SessionLocal() as session:
            query = select(Document)
            if document_ids:
                query = query.where(Document.id.in_(document_ids))
            else:
                if doc_type:
                    query = query.where(Document.doc_type.in_(doc_type))
                if state:
                    query = query.where(Document.state.in_(state))
            query = query.limit(limit)
            rows = session.execute(query).scalars().all()
            doc_count = len(rows)
            for doc in rows:
                _collect(doc)

    if scope == "shared":
        with bind_schema("public"):
            with SessionLocal() as session:
                new, dup = _append_urls_batch(session, url_refs, "document", "shared", None)
                session.commit()
    else:
        with bind_project(project_key):
            with SessionLocal() as session:
                new, dup = _append_urls_batch(session, url_refs, "document", "project", project_key)
                session.commit()

    return {
        "documents_scanned": doc_count,
        "urls_extracted": len(url_refs),
        "urls_new": new,
        "urls_duplicate": dup,
        "scope": scope,
    }


def append_url(
    url: str,
    source: str,
    source_ref: dict,
    *,
    scope: str,
    project_key: str,
) -> bool:
    """
    Append a single URL to resource pool. Returns True if appended, False if duplicate/skipped.
    scope: "project" | "shared". For shared, project_key can be empty; for project it is required.
    """
    if scope not in ("project", "shared"):
        scope = "project"
    url_refs = [(url, source_ref)]
    if scope == "shared":
        with bind_schema("public"):
            with SessionLocal() as session:
                new, dup = _append_urls_batch(session, url_refs, source, "shared", None)
                session.commit()
                return new > 0
    with bind_project(project_key):
        with SessionLocal() as session:
            new, dup = _append_urls_batch(session, url_refs, source, "project", project_key)
            session.commit()
            return new > 0


def _append_urls_batch(
    session: Session,
    url_refs: list[tuple[str, dict]],
    source: str,
    scope: str,
    project_key: str | None,
) -> tuple[int, int]:
    """Append URLs with per-url source_ref. Returns (new_count, duplicate_count)."""
    new_count = 0
    dup_count = 0
    for raw, ref in url_refs:
        norm = normalize_url(raw)
        if not norm:
            continue
        domain = domain_from_url(norm) or ""

        if scope == "shared":
            existing = session.execute(
                select(SharedResourcePoolUrl).where(SharedResourcePoolUrl.url == norm)
            ).scalar_one_or_none()
            if existing:
                dup_count += 1
                continue
            session.add(
                SharedResourcePoolUrl(
                    url=norm,
                    domain=domain[:255] if domain else None,
                    source=source[:32],
                    source_ref=ref,
                )
            )
            new_count += 1
        else:
            existing = session.execute(
                select(ResourcePoolUrl).where(ResourcePoolUrl.url == norm)
            ).scalar_one_or_none()
            if existing:
                dup_count += 1
                continue
            session.add(
                ResourcePoolUrl(
                    url=norm,
                    domain=domain[:255] if domain else None,
                    source=source[:32],
                    source_ref=ref,
                    project_key=project_key,
                )
            )
            new_count += 1
    return new_count, dup_count


def extract_from_tasks(
    *,
    project_key: str,
    scope: str = "project",
    task_ids: list[int] | None = None,
    job_type: str | None = None,
    since: datetime | str | None = None,
    limit: int = 100,
) -> dict:
    """
    Extract URLs from EtlJobRun.params (merged with result) and write to resource pool.
    task_ids: EtlJobRun.id list. job_type: filter by job_type. since: started_at >= since.
    """
    if scope not in ("project", "shared"):
        scope = "project"

    url_refs: list[tuple[str, dict]] = []
    tasks_scanned = 0

    with bind_project(project_key):
        with SessionLocal() as session:
            query = select(EtlJobRun).where(EtlJobRun.status == "completed")
            if task_ids:
                query = query.where(EtlJobRun.id.in_(task_ids))
            if job_type:
                query = query.where(EtlJobRun.job_type == job_type)
            if since:
                if isinstance(since, str):
                    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                else:
                    since_dt = since
                query = query.where(EtlJobRun.started_at >= since_dt)
            query = query.order_by(EtlJobRun.started_at.desc()).limit(limit)
            rows = session.execute(query).scalars().all()
            tasks_scanned = len(rows)

            for (job,) in rows:
                params = job.params or {}
                ref = {"task_id": job.id, "job_type": job.job_type}
                links = params.get("links")
                if isinstance(links, list):
                    for u in links:
                        if isinstance(u, str):
                            url_refs.append((u, ref))
                for u in extract_urls_from_json(params):
                    url_refs.append((u, ref))

    seen: set[str] = set()
    deduped: list[tuple[str, dict]] = []
    for u, ref in url_refs:
        norm = normalize_url(u)
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append((u, ref))

    if scope == "shared":
        with bind_schema("public"):
            with SessionLocal() as session:
                new, dup = _append_urls_batch(session, deduped, "task", "shared", None)
                session.commit()
    else:
        with bind_project(project_key):
            with SessionLocal() as session:
                new, dup = _append_urls_batch(session, deduped, "task", "project", project_key)
                session.commit()

    return {
        "tasks_scanned": tasks_scanned,
        "urls_extracted": len(deduped),
        "urls_new": new,
        "urls_duplicate": dup,
        "scope": scope,
    }
