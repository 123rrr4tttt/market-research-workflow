"""URL pool channel: fetch URLs from channel or resource pool and ingest as documents."""

from __future__ import annotations

import logging
import time
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
_DEBUG_MAX_URLS = 200
_DEBUG_MAX_POOL_ITEMS = 50
_DEBUG_MAX_ERRORS = 50


def _safe_exc(exc: Exception) -> str:
    msg = str(exc).strip()
    if not msg:
        msg = exc.__class__.__name__
    if exc.__class__.__name__ in msg:
        return msg
    return f"{exc.__class__.__name__}: {msg}"


def _detail(url: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"url": url}
    for k, v in extra.items():
        if v is not None:
            out[k] = v
    return out


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
    raw_count = len(urls) if isinstance(urls, list) else 0
    urls = _normalize_url_list(urls)
    normalized_count = len(urls)
    if not urls:
        return {
            "inserted": 0,
            "skipped": 0,
            "urls": 0,
            "debug": {
                "mode": "list",
                "raw_url_count": raw_count,
                "normalized_url_count": normalized_count,
                "filtered_out": max(0, raw_count - normalized_count),
                "note": "输入 URL 列表为空或全部被过滤（仅接受 http/https）",
            },
        }

    job_id = start_job(
        "url_pool_fetch",
        {
            "mode": "list",
            "url_count": len(urls),
            "raw_url_count": raw_count,
            "normalized_url_count": normalized_count,
            "filtered_out": max(0, raw_count - normalized_count),
        },
    )
    try:
        inserted = 0
        skipped = 0
        skipped_exists = 0
        skipped_fetch_error = 0
        details: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        with SessionLocal() as session:
            src = _get_or_create_source(session, _SOURCE_NAME, _SOURCE_KIND)
            source_id = src.id

            for url in urls:
                existed = session.query(Document).filter(Document.uri == url).first()
                if existed:
                    skipped += 1
                    skipped_exists += 1
                    if len(details) < _DEBUG_MAX_URLS:
                        details.append(_detail(url, action="skip_exists", document_id=existed.id))
                    continue
                try:
                    t0 = time.monotonic()
                    html, _ = fetch_html(url, timeout=15.0)
                    fetch_ms = int((time.monotonic() - t0) * 1000)
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
                    if len(details) < _DEBUG_MAX_URLS:
                        details.append(
                            _detail(
                                url,
                                action="inserted",
                                fetch_ms=fetch_ms,
                                html_chars=len(html) if html else 0,
                                content_chars=len(content) if content else 0,
                            )
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("url_pool fetch failed for %s: %s", url[:80], exc)
                    skipped += 1
                    skipped_fetch_error += 1
                    err = _safe_exc(exc)
                    if len(details) < _DEBUG_MAX_URLS:
                        details.append(_detail(url, action="skip_fetch_error", error=err))
                    if len(errors) < _DEBUG_MAX_ERRORS:
                        errors.append({"url": url, "error": err})

            session.commit()

        result: Dict[str, Any] = {
            "inserted": inserted,
            "skipped": skipped,
            "urls": len(urls),
            "skipped_exists": skipped_exists,
            "skipped_fetch_error": skipped_fetch_error,
            "debug": {
                "mode": "list",
                "raw_url_count": raw_count,
                "normalized_url_count": normalized_count,
                "filtered_out": max(0, raw_count - normalized_count),
                "url_details": details,
                "url_details_truncated": len(urls) > len(details),
                "errors": errors,
            },
        }
        result["display_meta"] = build_display_meta(
            CollectRequest(
                channel="url_pool",
                project_key=project_key,
                urls=list(urls),
                limit=len(urls),
                source_context={"summary": "URL 池抓取并写入文档"},
            ),
            CollectResult(
                channel="url_pool",
                inserted=inserted,
                skipped=skipped,
                updated=0,
                status="completed",
                errors=errors,
            ),
            summary="URL 池抓取并写入文档",
        )
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, _safe_exc(exc))
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
        items, total = list_urls(
            scope=scope,
            project_key=project_key,
            source=source_filter,
            domain=domain,
            page=1,
            page_size=min(limit, 100),
        )
        item_by_url = {x.get("url"): x for x in items if isinstance(x, dict) and x.get("url")}
        urls = [x.get("url") for x in items if x.get("url")]
        inserted = 0
        skipped = 0
        skipped_invalid_url = 0
        skipped_exists = 0
        skipped_fetch_error = 0
        details: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        ctx = bind_project(project_key) if project_key else nullcontext()
        with ctx:
            with SessionLocal() as session:
                src = _get_or_create_source(session, _SOURCE_NAME, _SOURCE_KIND)
                source_id = src.id

                for url in urls:
                    pool_item = item_by_url.get(url) or {}
                    if not url or not url.strip().startswith(("http://", "https://")):
                        skipped += 1
                        skipped_invalid_url += 1
                        if len(details) < _DEBUG_MAX_URLS:
                            details.append(
                                _detail(
                                    str(url or ""),
                                    action="skip_invalid_url",
                                    pool_scope=pool_item.get("scope"),
                                    pool_source=pool_item.get("source"),
                                    pool_domain=pool_item.get("domain"),
                                    pool_source_ref=pool_item.get("source_ref"),
                                )
                            )
                        continue
                    existed = session.query(Document).filter(Document.uri == url).first()
                    if existed:
                        skipped += 1
                        skipped_exists += 1
                        if len(details) < _DEBUG_MAX_URLS:
                            details.append(
                                _detail(
                                    url,
                                    action="skip_exists",
                                    document_id=existed.id,
                                    pool_scope=pool_item.get("scope"),
                                    pool_source=pool_item.get("source"),
                                    pool_domain=pool_item.get("domain"),
                                    pool_source_ref=pool_item.get("source_ref"),
                                )
                            )
                        continue
                    try:
                        t0 = time.monotonic()
                        html, _ = fetch_html(url, timeout=15.0)
                        fetch_ms = int((time.monotonic() - t0) * 1000)
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
                        if len(details) < _DEBUG_MAX_URLS:
                            details.append(
                                _detail(
                                    url,
                                    action="inserted",
                                    fetch_ms=fetch_ms,
                                    html_chars=len(html) if html else 0,
                                    content_chars=len(content) if content else 0,
                                    pool_scope=pool_item.get("scope"),
                                    pool_source=pool_item.get("source"),
                                    pool_domain=pool_item.get("domain"),
                                    pool_source_ref=pool_item.get("source_ref"),
                                )
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("url_pool fetch failed for %s: %s", url[:80], exc)
                        skipped += 1
                        skipped_fetch_error += 1
                        err = _safe_exc(exc)
                        if len(details) < _DEBUG_MAX_URLS:
                            details.append(
                                _detail(
                                    url,
                                    action="skip_fetch_error",
                                    error=err,
                                    pool_scope=pool_item.get("scope"),
                                    pool_source=pool_item.get("source"),
                                    pool_domain=pool_item.get("domain"),
                                    pool_source_ref=pool_item.get("source_ref"),
                                )
                            )
                        if len(errors) < _DEBUG_MAX_ERRORS:
                            errors.append({"url": url, "error": err})

                session.commit()

        result: Dict[str, Any] = {
            "inserted": inserted,
            "skipped": skipped,
            "urls": len(urls),
            "pool_total": int(total or 0),
            "pool_returned": len(items),
            "skipped_invalid_url": skipped_invalid_url,
            "skipped_exists": skipped_exists,
            "skipped_fetch_error": skipped_fetch_error,
            "debug": {
                "mode": "pool",
                "pool_total": int(total or 0),
                "pool_returned": len(items),
                "pool_items_sample": [
                    {
                        "id": x.get("id"),
                        "url": x.get("url"),
                        "scope": x.get("scope"),
                        "source": x.get("source"),
                        "domain": x.get("domain"),
                        "source_ref": x.get("source_ref"),
                    }
                    for x in (items[:_DEBUG_MAX_POOL_ITEMS] if items else [])
                ],
                "url_details": details,
                "url_details_truncated": len(urls) > len(details),
                "errors": errors,
            },
        }
        result["display_meta"] = build_display_meta(
            CollectRequest(
                channel="url_pool",
                project_key=project_key,
                urls=list(urls),
                scope=scope,
                limit=limit,
                source_context={"summary": "URL 池抓取并写入文档"},
            ),
            CollectResult(
                channel="url_pool",
                inserted=inserted,
                skipped=skipped,
                updated=0,
                status="completed",
                errors=errors,
            ),
            summary="URL 池抓取并写入文档",
        )
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, _safe_exc(exc))
        raise
