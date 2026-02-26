"""URL pool channel: fetch URLs from channel or resource pool and ingest as documents."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ...models.base import SessionLocal
from ...models.entities import Document, Source
from ..job_logger import complete_job, fail_job, start_job
from ..collect_runtime.display_meta import build_display_meta
from ..collect_runtime.contracts import CollectRequest, CollectResult
from ..resource_pool import list_urls
from .adapters.http_utils import fetch_html, make_html_parser

logger = logging.getLogger(__name__)

_SOURCE_NAME = "url_pool"
_SOURCE_KIND = "url_fetch"
_DOC_TYPE = "url_fetch"
_DEFAULT_LIMIT = 50


def _normalize_url_list(urls: Any) -> List[str]:
    """Extract and normalize URL list from channel/params."""
    if isinstance(urls, list):
        return [str(u).strip() for u in urls if u and str(u).strip().startswith(("http://", "https://"))]
    return []


def _extract_text_from_html(html: str) -> str:
    """Extract main text from HTML for storage."""
    try:
        parser = make_html_parser(html)
        body = parser.body
        if body:
            return (body.text(separator=" ", strip=True) or "")[:50000]
        return ""
    except Exception:  # noqa: BLE001
        return ""


def _get_or_create_source(session, name: str, kind: str, base_url: Optional[str] = None) -> Source:
    row = (
        session.query(Source)
        .filter(Source.name == name, Source.kind == kind)
        .first()
    )
    if row:
        return row
    source = Source(name=name, kind=kind, base_url=base_url or "")
    session.add(source)
    session.flush()
    return source


def collect_urls_from_list(
    urls: List[str],
    *,
    project_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch a given list of URLs and store as Document.
    Returns { inserted, skipped, urls }.
    """
    urls = _normalize_url_list(urls)
    if not urls:
        return {"inserted": 0, "skipped": 0, "urls": 0}

    job_id = start_job("url_pool_fetch", {"url_count": len(urls)})
    try:
        inserted = 0
        skipped = 0

        with SessionLocal() as session:
            src = _get_or_create_source(session, _SOURCE_NAME, _SOURCE_KIND)
            source_id = src.id

            for url in urls:
                existed = session.query(Document).filter(Document.uri == url).first()
                if existed:
                    skipped += 1
                    continue
                try:
                    html, _ = fetch_html(url, timeout=15.0)
                    content = _extract_text_from_html(html)
                    parsed = urlparse(url)
                    domain_str = parsed.netloc or parsed.path[:50] or "unknown"
                    doc = Document(
                        source_id=source_id,
                        doc_type=_DOC_TYPE,
                        title=domain_str,
                        content=content[:50000] if content else None,
                        uri=url,
                    )
                    session.add(doc)
                    inserted += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("url_pool fetch failed for %s: %s", url[:80], exc)
                    skipped += 1

            session.commit()

        result = {"inserted": inserted, "skipped": skipped, "urls": len(urls)}
        result["display_meta"] = build_display_meta(
            CollectRequest(
                channel="url_pool",
                project_key=project_key,
                urls=list(urls),
                limit=len(urls),
                source_context={"summary": "URL 池抓取并写入文档"},
            ),
            CollectResult(channel="url_pool", inserted=inserted, skipped=skipped, updated=0, status="completed"),
            summary="URL 池抓取并写入文档",
        )
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        raise


def collect_urls_from_pool(
    *,
    scope: str = "effective",
    project_key: Optional[str] = None,
    domain: Optional[str] = None,
    source_filter: Optional[str] = None,
    limit: int = _DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """
    Fetch URLs from resource pool, fetch each, store as Document.
    Returns { inserted, skipped, urls }.
    Ensures schema isolation when project_key is set.
    """
    from ..projects import bind_project

    job_id = start_job(
        "url_pool_fetch",
        {"scope": scope, "domain": domain, "source": source_filter, "limit": limit},
    )
    try:
        items, _ = list_urls(
            scope=scope,
            project_key=project_key,
            source=source_filter,
            domain=domain,
            page=1,
            page_size=min(limit, 100),
        )
        urls = [x.get("url") for x in items if x.get("url")]
        inserted = 0
        skipped = 0

        ctx = bind_project(project_key) if project_key else nullcontext()
        with ctx:
            with SessionLocal() as session:
                src = _get_or_create_source(session, _SOURCE_NAME, _SOURCE_KIND)
                source_id = src.id

                for url in urls:
                    if not url or not url.strip().startswith(("http://", "https://")):
                        skipped += 1
                        continue
                    existed = session.query(Document).filter(Document.uri == url).first()
                    if existed:
                        skipped += 1
                        continue
                    try:
                        html, _ = fetch_html(url, timeout=15.0)
                        content = _extract_text_from_html(html)
                        parsed = urlparse(url)
                        domain_str = parsed.netloc or parsed.path[:50] or "unknown"
                        doc = Document(
                            source_id=source_id,
                            doc_type=_DOC_TYPE,
                            title=domain_str,
                            content=content[:50000] if content else None,
                            uri=url,
                        )
                        session.add(doc)
                        inserted += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("url_pool fetch failed for %s: %s", url[:80], exc)
                        skipped += 1

                session.commit()

        result = {"inserted": inserted, "skipped": skipped, "urls": len(urls)}
        result["display_meta"] = build_display_meta(
            CollectRequest(
                channel="url_pool",
                project_key=project_key,
                urls=list(urls),
                scope=scope,
                limit=limit,
                source_context={"summary": "URL 池抓取并写入文档"},
            ),
            CollectResult(channel="url_pool", inserted=inserted, skipped=skipped, updated=0, status="completed"),
            summary="URL 池抓取并写入文档",
        )
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        raise
