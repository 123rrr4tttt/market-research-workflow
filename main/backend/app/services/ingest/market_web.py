"""Generic market info collection via search API (default: Google Custom Search)."""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy.orm import Session

from ..job_logger import start_job, complete_job, fail_job
from ..collect_runtime.display_meta import build_display_meta
from ..collect_runtime.contracts import CollectRequest, CollectResult
from ..search.web import search_sources
from ..extraction.numeric import normalize_market_payload
from ...models.base import SessionLocal
from ...models.entities import Document, Source
from .doc_type_mapper import normalize_doc_type
from ..llm.extraction import extract_market_info
from ..extraction.application import ExtractionApplicationService
from .adapters.http_utils import fetch_html
from .url_pool import _extract_text_from_html

logger = logging.getLogger(__name__)
BATCH_COMMIT_SIZE = 100
_EXTRACTION_APP = ExtractionApplicationService()


def _get_or_create_source(session: Session, name: str, kind: str, base_url: str) -> Source:
    source = (
        session.query(Source)
        .filter(Source.name == name, Source.kind == kind)
        .first()
    )
    if source:
        return source
    source = Source(name=name, kind=kind, base_url=base_url)
    session.add(source)
    session.flush()
    return source


def collect_market_info(
    keywords: List[str],
    limit: int = 20,
    enable_extraction: bool = True,
    provider: str = "auto",
    start_offset: int | None = None,
    days_back: int | None = None,
    language: str = "en",
) -> dict:
    """
    Collect market-related info via search API.
    Default: auto (Serper -> Google -> Serpstack -> SerpAPI -> DDG).
    """
    job_id = start_job("market_info", {"keywords": keywords, "limit": limit, "provider": provider})

    try:
        normalized_doc_type = normalize_doc_type("market_info")
        results = search_sources(
            topic=" ".join(keywords),
            max_results=limit,
            provider=provider,
            exclude_existing=False,
            start_offset=start_offset,
            days_back=days_back,
            language=language,
        )

        inserted = 0
        skipped = 0
        links: List[str] = []
        pending_inserts = 0

        with SessionLocal() as session:
            source = _get_or_create_source(session, "Search API Market", "search", "search")
            source_id = source.id

            for item in results:
                link = (item.get("link") or "").strip()
                if not link:
                    continue
                links.append(link)

                existed = session.query(Document).filter(Document.uri == link).first()
                if existed:
                    skipped += 1
                    continue

                title = item.get("title") or ""
                snippet = item.get("snippet") or ""
                content = None
                try:
                    # Disable snippet-only quick-save: try fetching正文 before入库.
                    html, _ = fetch_html(link, timeout=8.0, retries=1)
                    text = (_extract_text_from_html(html) or "").strip()
                    if text:
                        content = text
                except Exception:
                    content = None

                extracted_data = {
                    "platform": item.get("source") or provider,
                    "keyword": item.get("keyword"),
                }
                if enable_extraction:
                    text_to_extract = "\n\n".join([x for x in [title.strip(), snippet.strip(), (content or "").strip()] if x])
                    enriched = _EXTRACTION_APP.extract_structured_enriched(text_to_extract, include_market=True)
                    if enriched:
                        market_raw = enriched.get("market")
                        if isinstance(market_raw, dict):
                            try:
                                market_norm, market_quality = normalize_market_payload(
                                    market_raw,
                                    scope="lottery.market",
                                )
                                market_norm["numeric_quality"] = market_quality
                                enriched["market"] = market_norm
                            except Exception as e:
                                logger.warning("collect_market_info: market normalization failed: %s", e)
                        extracted_data.update(enriched)
                    elif (market_info := extract_market_info(text_to_extract)):
                        try:
                            market_norm, market_quality = normalize_market_payload(
                                market_info,
                                scope="lottery.market",
                            )
                            market_norm["numeric_quality"] = market_quality
                            extracted_data["market"] = market_norm
                        except Exception as e:
                            logger.warning("collect_market_info: market normalization fallback failed: %s", e)

                document = Document(
                    source_id=source_id,
                    state=None,
                    doc_type=normalized_doc_type,
                    title=title,
                    summary=snippet,
                    publish_date=None,
                    content=content,
                    uri=link,
                    extracted_data=extracted_data,
                )
                session.add(document)
                inserted += 1
                pending_inserts += 1
                if pending_inserts >= BATCH_COMMIT_SIZE:
                    session.commit()
                    session.expunge_all()
                    pending_inserts = 0

            if pending_inserts > 0:
                session.commit()

        result = {
            "inserted": inserted,
            "skipped": skipped,
            "links": links,
            "doc_type": normalized_doc_type,
        }
        result["display_meta"] = build_display_meta(
            CollectRequest(
                channel="search.market",
                query_terms=list(keywords or []),
                limit=limit,
                provider=provider,
                language=language,
                source_context={"summary": "市场信息采集"},
            ),
            CollectResult(
                channel="search.market",
                inserted=inserted,
                skipped=skipped,
                updated=0,
                status="completed",
            ),
            summary="市场信息采集",
        )
        complete_job(job_id, result=result)
        return result

    except Exception as exc:
        logger.exception("collect_market_info failed")
        fail_job(job_id, str(exc))
        raise
