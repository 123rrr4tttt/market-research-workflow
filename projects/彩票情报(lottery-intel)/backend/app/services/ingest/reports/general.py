from __future__ import annotations

import logging
from typing import Iterable

from ..job_logger import start_job, complete_job, fail_job
from ...models.base import SessionLocal
from ...models.entities import Document, Source
from ..search.web import search_sources


logger = logging.getLogger(__name__)


def collect_weekly_market_reports(limit: int = 10) -> dict:
    job_id = start_job("weekly_market_reports", {"limit": limit})
    try:
        keywords = [
            "NASPL weekly lottery sales report",
            "California Lottery Second Chance winners",
            "Lottery retailer weekly reference guide",
        ]
        results = []
        for keyword in keywords:
            results.extend(search_sources(keyword, language="en", max_results=limit))
        result = _store_documents(results, doc_type="weekly_report", limit=limit)
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_weekly_market_reports failed")
        fail_job(job_id, str(exc))
        raise


def collect_monthly_financial_reports(limit: int = 8) -> dict:
    job_id = start_job("monthly_financial_reports", {"limit": limit})
    try:
        keywords = [
            "California Lottery monthly financial report PDF",
            "California education lottery allocation report",
            "NASPL monthly market analysis",
        ]
        results = []
        for keyword in keywords:
            results.extend(search_sources(keyword, language="en", max_results=limit))
        result = _store_documents(results, doc_type="monthly_report", limit=limit)
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_monthly_financial_reports failed")
        fail_job(job_id, str(exc))
        raise


def _store_documents(results: Iterable[dict], doc_type: str, limit: int) -> dict:
    inserted = 0
    skipped = 0
    stored_links: list[str] = []

    with SessionLocal() as session:
        for item in list(results)[: max(limit, 0)]:
            link = (item.get("link") or "").strip()
            if not link:
                continue
            stored_links.append(link)
            existed = session.query(Document).filter(Document.uri == link).one_or_none()
            if existed:
                skipped += 1
                continue

            domain = (item.get("domain") or "").strip() or None
            source = _ensure_source(session, domain or item.get("source") or "external", domain)

            document = Document(
                source_id=source.id,
                state="CA",
                doc_type=doc_type,
                title=item.get("title"),
                summary=item.get("snippet"),
                uri=link,
            )
            session.add(document)
            inserted += 1

        session.commit()

    return {"inserted": inserted, "skipped": skipped, "doc_type": doc_type, "links": stored_links}


def _ensure_source(session, name: str | None, base_url: str | None) -> Source:
    label = name or "external"
    source = (
        session.query(Source)
        .filter(Source.name == label, Source.kind == "report")
        .one_or_none()
    )
    if source:
        return source

    source = Source(name=label, kind="report", base_url=base_url)
    session.add(source)
    session.flush()
    return source


