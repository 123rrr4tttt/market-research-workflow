from __future__ import annotations

import logging
from urllib.parse import urlparse

from ....models.base import SessionLocal
from ....models.entities import Document, Source
from ...job_logger import start_job, complete_job, fail_job
from ...search.web import search_sources


logger = logging.getLogger(__name__)


PDF_KEYWORDS = ["pdf", ".pdf"]


def collect_california_sales_reports(limit: int = 3) -> dict:
    job_id = start_job("ca_reports", {"limit": limit})

    try:
        results = search_sources("California Lottery sales report PDF", language="en", max_results=20)
        pdf_links = []
        for item in results:
            link = (item.get("link") or "").strip()
            if not link:
                continue
            normalized = link.lower()
            if any(keyword in normalized for keyword in PDF_KEYWORDS):
                pdf_links.append(item)

        stored = 0
        skipped = 0

        with SessionLocal() as session:
            for item in pdf_links[: limit or 0]:
                link = item.get("link")
                if not link:
                    continue

                existing = session.query(Document).filter(Document.uri == link).one_or_none()
                if existing:
                    skipped += 1
                    continue

                domain = urlparse(link).netloc
                source = session.query(Source).filter(Source.base_url == domain).one_or_none()
                if not source:
                    source = Source(name=domain or "unknown", kind="web", base_url=domain)
                    session.add(source)
                    session.flush()

                title = item.get("title") or "California Lottery Report"
                summary = item.get("snippet")

                document = Document(
                    source_id=source.id,
                    state="CA",
                    doc_type="market_report",
                    title=title,
                    summary=summary,
                    uri=link,
                )
                session.add(document)
                stored += 1

            session.commit()

        result = {"inserted": stored, "updated": 0, "skipped": skipped, "state": "CA"}
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("collect_california_sales_reports failed")
        fail_job(job_id, str(exc))
        raise


