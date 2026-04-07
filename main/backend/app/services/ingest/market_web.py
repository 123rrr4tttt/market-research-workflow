"""Generic market info collection via search API (default: Google Custom Search)."""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy.orm import Session

from ..job_logger import start_job, complete_job, fail_job
from ..collect_runtime.display_meta import build_display_meta
from ..collect_runtime.contracts import CollectRequest, CollectResult
from ..projects import current_project_key
from ..search.web import search_sources
from ...models.base import SessionLocal
from ...models.entities import Document, Source
from .doc_type_mapper import normalize_doc_type
from .frontdoor_ingress import build_frontdoor_ingress_envelope
from .postprocess_frontdoor import run_postprocess_frontdoor
from .adapters.http_utils import fetch_html
from .url_pool import collect_urls_from_list
from .url_pool import _extract_text_from_html

logger = logging.getLogger(__name__)
BATCH_COMMIT_SIZE = 100


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
        routed_for_body_fetch: List[str] = []
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
                if not str(content or "").strip():
                    routed_for_body_fetch.append(link)
                    continue

                extracted_data = {
                    "platform": item.get("source") or provider,
                    "keyword": item.get("keyword"),
                }

                ingress_envelope = build_frontdoor_ingress_envelope(
                    ingress_type="discovery",
                    entrypoint="ingest.market_web",
                    source_mode="protocol_search",
                    project_key=(current_project_key() or "").strip() or None,
                    source_ref={"url": link, "locator": link},
                    collection_payload={
                        "document_candidate": {
                            "source_name": "Search API Market",
                            "source_kind": "search",
                            "source_base_url": "search",
                            "state": None,
                            "doc_type": normalized_doc_type,
                            "title": title,
                            "summary": snippet,
                            "publish_date": None,
                            "content": content,
                            "text_hash": None,
                            "uri": link,
                            "status": None,
                            "extracted_data_base": extracted_data,
                        },
                        "terminal_context": {
                            "platform": item.get("source") or provider or "market_search",
                            "ingestion_entrypoint": "ingest.market_web",
                            "source_mode": "protocol_search",
                            "quality_score": 0.0,
                            "degradation_flags": [],
                            "http_status": None,
                            "capability_profile": {},
                            "light_filter": {},
                        },
                        "extraction_plan": {
                            "enabled": bool(enable_extraction),
                            "include_market": True,
                            "include_policy": False,
                            "include_sentiment": False,
                            "include_company": True,
                            "include_product": True,
                            "include_operation": True,
                        },
                    },
                    raw_snapshot={"item": dict(item or {}), "link": link},
                )
                frontdoor_result = run_postprocess_frontdoor(
                    ingress_envelope=ingress_envelope,
                    run_writer=True,
                )
                writer_result = (frontdoor_result.get("data") or {}).get("writer_result") if isinstance(frontdoor_result.get("data"), dict) else {}
                inserted += int((writer_result or {}).get("inserted") or 0)
                skipped += int((writer_result or {}).get("skipped") or 0)

            if pending_inserts > 0:
                session.commit()

        routed_result = {
            "inserted": 0,
            "inserted_valid": 0,
            "skipped": 0,
            "queued": 0,
        }
        if routed_for_body_fetch:
            routed_result = collect_urls_from_list(
                routed_for_body_fetch,
                project_key=(current_project_key() or "").strip() or None,
                query_terms=list(keywords or []),
                extra_params={
                    "dispatch_mode": "inline",
                    "url_routing_frontdoor_enabled": True,
                    "front_door_owner": "ingest.market_web",
                    "frontdoor_route_decision": "front_door_url_routing",
                    "frontdoor_write_mode": "front_door_url_routing",
                    "frontdoor_execution_mode": "url_routing",
                },
                enable_extraction=enable_extraction,
            )
            inserted += int(routed_result.get("inserted") or 0)
            skipped += int(routed_result.get("skipped") or 0)

        result = {
            "inserted": inserted,
            "inserted_valid": inserted,
            "skipped": skipped,
            "links": links,
            "doc_type": normalized_doc_type,
            "body_fetch_routed_urls": len(routed_for_body_fetch),
            "body_fetch_inserted": int(routed_result.get("inserted") or 0),
            "body_fetch_skipped": int(routed_result.get("skipped") or 0),
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
