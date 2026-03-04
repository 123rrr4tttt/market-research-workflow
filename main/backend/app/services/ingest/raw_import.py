from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import logging
import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import Document, Source
from ..extraction.application import ExtractionApplicationService
from ..job_logger import complete_job, fail_job, start_job
from .adapters.http_utils import fetch_html, make_html_parser
from .structured_extraction import build_structured_summary
from .timestamp_resolver import resolve_document_temporal_fields

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>()\"']+")


def _deep_merge_json(base: Any, incoming: Any) -> Any:
    if isinstance(base, dict) and isinstance(incoming, dict):
        out: dict[str, Any] = dict(base)
        for k, v in incoming.items():
            if k in out:
                out[k] = _deep_merge_json(out[k], v)
            else:
                out[k] = v
        return out
    return incoming


def _normalize_doc_type_for_raw(dt: str | None, default_doc_type: str) -> str:
    key = (dt or "").strip().lower()
    allowed = {
        "market",
        "market_info",
        "policy",
        "policy_regulation",
        "social_sentiment",
        "social_feed",
        "news",
        "raw_note",
    }
    if key in allowed:
        return key
    return default_doc_type


def _all_urls_in_text(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(".,;)]")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _normalize_uri_list(item: dict[str, Any], infer_from_text: bool) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    candidates: list[str] = []
    url = item.get("url")
    if url:
        candidates.append(str(url))
    uri = item.get("uri")
    if uri:
        candidates.append(str(uri))
    uris = item.get("uris")
    if isinstance(uris, list):
        candidates.extend([str(x) for x in uris if x])
    if infer_from_text:
        candidates.extend(_all_urls_in_text(str(item.get("text") or "")))
    for raw in candidates:
        normalized = raw.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
    return urls


def _extract_text_from_html(html: str) -> str:
    try:
        parser = make_html_parser(html)
        for selector in ("article", "main article", "[role='main'] article", "main"):
            node = parser.css_first(selector)
            if node is None:
                continue
            text = str(node.text(separator="\n", strip=True) or "").strip()
            if len(text) >= 120:
                return text[:50000]
        body = parser.body
        if body:
            text = str(body.text(separator="\n", strip=True) or "").strip()
            return text[:50000]
    except Exception:
        return ""
    return ""


def _extract_title_from_html(html: str) -> str:
    try:
        parser = make_html_parser(html)
        node = parser.css_first("title")
        if node is None:
            return ""
        return str(node.text(strip=True) or "").strip()
    except Exception:
        return ""


def _merge_raw_and_url_text(raw_text: str, url_text: str) -> str:
    left = str(raw_text or "").strip()
    right = str(url_text or "").strip()
    if not left:
        return right
    if not right:
        return left
    if right in left:
        return left
    if left in right:
        return right
    return f"{left}\n\n[URL_CONTENT]\n{right}"


def _chunk_text_for_extraction(text: str, chunk_size: int, overlap: int, max_chunks: int) -> tuple[list[str], bool]:
    source = str(text or "").strip()
    if not source:
        return [], False
    if len(source) <= chunk_size:
        return [source], False
    step = max(1, chunk_size - overlap)
    chunks: list[str] = []
    idx = 0
    truncated = False
    while idx < len(source):
        if len(chunks) >= max_chunks:
            truncated = True
            break
        part = source[idx : idx + chunk_size].strip()
        if part:
            chunks.append(part)
        idx += step
    return (chunks or [source[:chunk_size]], truncated)


def _merge_extracted_batch(parts: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    all_entities: list[dict[str, Any]] = []
    all_relations: list[dict[str, Any]] = []

    def _entity_key(entity: Any) -> str:
        if not isinstance(entity, dict):
            return str(entity)
        return f"{str(entity.get('text') or '').strip().lower()}::{str(entity.get('type') or '').strip().lower()}"

    def _rel_key(rel: Any) -> str:
        if not isinstance(rel, dict):
            return str(rel)
        return "::".join(
            [
                str(rel.get("subject") or "").strip().lower(),
                str(rel.get("predicate") or "").strip().lower(),
                str(rel.get("object") or "").strip().lower(),
            ]
        )

    seen_entities: set[str] = set()
    seen_relations: set[str] = set()
    for part in parts:
        if not isinstance(part, dict):
            continue
        merged = _deep_merge_json(merged, part)
        er = part.get("entities_relations")
        if isinstance(er, dict):
            for entity in (er.get("entities") or []):
                key = _entity_key(entity)
                if key and key not in seen_entities:
                    seen_entities.add(key)
                    all_entities.append(entity)
            for rel in (er.get("relations") or []):
                key = _rel_key(rel)
                if key and key not in seen_relations:
                    seen_relations.add(key)
                    all_relations.append(rel)
        for entity in (part.get("entities") or []):
            key = _entity_key(entity)
            if key and key not in seen_entities:
                seen_entities.add(key)
                all_entities.append(entity)
    if all_entities or all_relations:
        merged["entities_relations"] = {"entities": all_entities[:50], "relations": all_relations[:50]}
        if "entities" in merged and isinstance(merged.get("entities"), list):
            merged["entities"] = all_entities[:50]
    return merged


def _normalize_iso_date(value: Any) -> date | None:
    if not value:
        return None
    raw = str(value)
    try:
        return datetime.fromisoformat(raw).date()
    except Exception:
        try:
            return date.fromisoformat(raw)
        except Exception:
            return None


def _domain_of_uri(uri: str | None) -> str | None:
    raw = str(uri or "").strip()
    if not raw:
        return None
    try:
        return str(urlparse(raw).netloc or "").strip().lower() or None
    except Exception:
        return None


def _resolve_extraction_flags(extraction_mode: str, doc_type: str) -> dict[str, bool]:
    mode = (extraction_mode or "auto").strip().lower()
    dtype = (doc_type or "").strip().lower()
    if mode == "auto":
        if dtype in {"market", "market_info"}:
            mode = "market"
        elif dtype in {"policy", "policy_regulation"}:
            mode = "policy"
        elif dtype in {"social_sentiment", "social_feed"}:
            mode = "social"
        else:
            # raw_note/news should maximize structure at write-time.
            mode = "comprehensive"

    include_policy = mode in {"policy", "comprehensive"}
    include_market = mode in {"market", "comprehensive"}
    include_sentiment = mode in {"social", "comprehensive"}

    # Topic-oriented extraction is always enabled to enrich graph/read models.
    include_company = True
    include_product = True
    include_operation = True

    return {
        "mode": mode,  # type: ignore[typeddict-item]
        "include_policy": include_policy,
        "include_market": include_market,
        "include_sentiment": include_sentiment,
        "include_company": include_company,
        "include_product": include_product,
        "include_operation": include_operation,
    }


def _derive_publish_date_from_extracted(extracted_data: dict[str, Any]) -> date | None:
    policy = extracted_data.get("policy")
    if isinstance(policy, dict):
        derived = _normalize_iso_date(policy.get("effective_date"))
        if derived:
            return derived
    market = extracted_data.get("market")
    if isinstance(market, dict):
        derived = _normalize_iso_date(market.get("report_date"))
        if derived:
            return derived
    return None


def run_raw_import_documents(payload: dict[str, Any], project_key: str) -> dict[str, Any]:
    extraction_app = ExtractionApplicationService()
    now = datetime.now(timezone.utc)

    source_name = str(payload.get("source_name") or "raw_import").strip() or "raw_import"
    source_kind = str(payload.get("source_kind") or "manual").strip() or "manual"
    infer_from_links = bool(payload.get("infer_from_links", True))
    enable_extraction = bool(payload.get("enable_extraction", True))
    default_doc_type = str(payload.get("default_doc_type") or "raw_note")
    extraction_mode = str(payload.get("extraction_mode") or "auto").strip().lower()
    overwrite_on_uri = bool(payload.get("overwrite_on_uri", False))
    chunk_size = int(payload.get("chunk_size") or 2800)
    chunk_overlap = int(payload.get("chunk_overlap") or 200)
    max_chunks = int(payload.get("max_chunks") or 8)
    fetch_url_when_text_empty = bool(payload.get("fetch_url_when_text_empty", True))
    fetch_url_also_when_text_present = bool(payload.get("fetch_url_also_when_text_present", True))
    url_fetch_timeout = float(payload.get("url_fetch_timeout") or 8.0)
    url_to_market = bool(payload.get("url_to_market", True))
    items = payload.get("items") or []
    if not isinstance(items, list):
        items = []

    job_id = start_job(
        "raw_import",
        {
            "project_key": project_key,
            "source_name": source_name,
            "items_total": len(items),
            "fetch_url_when_text_empty": fetch_url_when_text_empty,
            "fetch_url_also_when_text_present": fetch_url_also_when_text_present,
            "url_to_market": url_to_market,
        },
    )

    try:
        with SessionLocal() as session:
            source = session.execute(select(Source).where(Source.name == source_name)).scalar_one_or_none()
            if source is None:
                source = Source(name=source_name, kind=source_kind, base_url=None, enabled=True)
                session.add(source)
                session.flush()

            inserted = 0
            updated = 0
            skipped = 0
            errors: list[dict[str, Any]] = []
            item_results: list[dict[str, Any]] = []

            for idx, raw_item in enumerate(items):
                item = raw_item if isinstance(raw_item, dict) else {}
                try:
                    text = str(item.get("text") or "").strip()
                    uri_list = _normalize_uri_list(item, infer_from_links)
                    uri = uri_list[0] if uri_list else None
                    fetched_from_url = False
                    fetched_url_error = None
                    fetched_url_status = None
                    fetched_title = ""
                    should_fetch_url = bool(
                        uri
                        and (
                            (not text and fetch_url_when_text_empty)
                            or (bool(text) and fetch_url_also_when_text_present)
                        )
                    )
                    if should_fetch_url:
                        try:
                            html, response = fetch_html(uri, timeout=float(url_fetch_timeout), retries=1)
                            fetched_url_status = int(getattr(response, "status_code", 0) or 0)
                            fetched_text = _extract_text_from_html(html)
                            if fetched_text:
                                fetched_from_url = True
                                fetched_title = _extract_title_from_html(html)
                                text = _merge_raw_and_url_text(text, fetched_text)
                        except Exception as exc:  # noqa: BLE001
                            fetched_url_error = str(exc)
                    if not text:
                        skipped += 1
                        item_results.append(
                            {
                                "index": idx,
                                "status": "skipped_empty_text",
                                "uri": uri,
                                "fetch_url_attempted": bool(should_fetch_url),
                                "fetch_url_error": fetched_url_error,
                            }
                        )
                        continue

                    title = str(item.get("title") or "").strip() or None
                    if not title:
                        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
                        title = first_line[:240] if first_line else None
                    if not title and fetched_title:
                        title = fetched_title[:240]
                    summary = str(item.get("summary") or "").strip() or None
                    if not summary:
                        summary = text[:400] if len(text) > 400 else None

                    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    item_doc_type = item.get("doc_type")
                    doc_type = _normalize_doc_type_for_raw(item_doc_type, default_doc_type)
                    if fetched_from_url and url_to_market and not str(item_doc_type or "").strip():
                        doc_type = "market_info"
                    publish_date_value = _normalize_iso_date(item.get("publish_date"))

                    existing = None
                    if uri:
                        existing = session.execute(select(Document).where(Document.uri == uri)).scalar_one_or_none()
                    if existing is None:
                        existing = session.execute(select(Document).where(Document.text_hash == text_hash)).scalar_one_or_none()

                    doc = existing
                    if doc and not overwrite_on_uri:
                        skipped += 1
                        item_results.append({"index": idx, "doc_id": doc.id, "status": "skipped_exists", "uri": doc.uri})
                        continue

                    if doc is None:
                        doc = Document(
                            source_id=source.id,
                            state=item.get("state") or None,
                            doc_type=doc_type,
                            title=title,
                            publish_date=publish_date_value,
                            content=text,
                            summary=summary,
                            text_hash=text_hash,
                            uri=uri,
                            source_domain=_domain_of_uri(uri),
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(doc)
                        session.flush()
                        inserted += 1
                    else:
                        doc.source_id = source.id
                        doc.state = item.get("state") or doc.state
                        doc.doc_type = doc_type or doc.doc_type
                        doc.title = title or doc.title
                        doc.publish_date = publish_date_value or doc.publish_date
                        doc.content = text
                        doc.summary = summary or doc.summary
                        doc.text_hash = text_hash
                        doc.uri = uri or doc.uri
                        doc.source_domain = _domain_of_uri(uri) or doc.source_domain
                        doc.updated_at = now
                        updated += 1

                    chunks, truncated = _chunk_text_for_extraction(
                        text,
                        chunk_size=int(chunk_size),
                        overlap=int(chunk_overlap),
                        max_chunks=int(max_chunks),
                    )
                    raw_meta = {
                        "uris": uri_list,
                        "uri_count": len(uri_list),
                        "fetched_from_url": fetched_from_url,
                        "fetch_url_status": fetched_url_status,
                        "fetch_url_error": fetched_url_error,
                        "chunk_count": len(chunks),
                        "chunk_size": int(chunk_size),
                        "chunk_overlap": int(chunk_overlap),
                        "truncated_for_extraction": truncated,
                    }
                    extracted_base = doc.extracted_data if isinstance(doc.extracted_data, dict) else {}
                    extracted_base["_raw_input"] = _deep_merge_json(extracted_base.get("_raw_input", {}), raw_meta)

                    mode = extraction_mode
                    if enable_extraction:
                        extraction_flags = _resolve_extraction_flags(extraction_mode, doc_type)
                        mode = str(extraction_flags.get("mode") or extraction_mode)

                        extracted_parts: list[dict[str, Any]] = []
                        for chunk in chunks:
                            extracted = extraction_app.extract_structured_enriched(
                                chunk,
                                include_policy=bool(extraction_flags.get("include_policy")),
                                include_market=bool(extraction_flags.get("include_market")),
                                include_sentiment=bool(extraction_flags.get("include_sentiment")),
                                include_company=bool(extraction_flags.get("include_company")),
                                include_product=bool(extraction_flags.get("include_product")),
                                include_operation=bool(extraction_flags.get("include_operation")),
                            )
                            if isinstance(extracted, dict) and extracted:
                                extracted_parts.append(extracted)

                        if extracted_parts:
                            extracted_base = _deep_merge_json(extracted_base, _merge_extracted_batch(extracted_parts))
                            if doc.publish_date is None:
                                derived = _derive_publish_date_from_extracted(extracted_base)
                                if derived:
                                    doc.publish_date = derived

                    extracted_base["_structured_summary"] = build_structured_summary(
                        extracted_base,
                        extraction_enabled=enable_extraction,
                        chunks_used=len(chunks),
                        extraction_mode=mode,
                    )
                    temporal_metadata = {
                        "item": {
                            "publish_date": item.get("publish_date"),
                            "source_time": item.get("source_time"),
                            "effective_time": item.get("effective_time"),
                            "ingested_at": item.get("ingested_at"),
                            "created_at": item.get("created_at"),
                            "updated_at": item.get("updated_at"),
                        },
                        "extracted_data": extracted_base,
                        "publish_date": str(doc.publish_date) if doc.publish_date else None,
                    }
                    temporal_fields = resolve_document_temporal_fields(
                        source_domain=_domain_of_uri(doc.uri),
                        metadata=temporal_metadata,
                        content_excerpt=text[:3000],
                        ingested_at=doc.created_at if isinstance(doc.created_at, datetime) else now,
                    )
                    doc.source_domain = temporal_fields.get("source_domain") or doc.source_domain
                    doc.source_time = temporal_fields.get("source_time")
                    doc.effective_time = temporal_fields.get("effective_time")
                    doc.time_confidence = temporal_fields.get("time_confidence")
                    doc.time_provenance = temporal_fields.get("time_provenance")
                    extracted_base["time_parse_version"] = temporal_fields.get("time_parse_version")
                    extracted_base["time_provenance"] = temporal_fields.get("time_provenance")
                    extracted_base["time_confidence"] = temporal_fields.get("time_confidence")
                    extracted_base["effective_time"] = (
                        temporal_fields["effective_time"].isoformat()
                        if temporal_fields.get("effective_time")
                        else None
                    )
                    extracted_base["source_time"] = (
                        temporal_fields["source_time"].isoformat()
                        if temporal_fields.get("source_time")
                        else None
                    )
                    extracted_base["ingested_at"] = (
                        temporal_fields["ingested_at"].isoformat()
                        if temporal_fields.get("ingested_at")
                        else None
                    )

                    doc.extracted_data = extracted_base
                    item_results.append(
                        {
                            "index": idx,
                            "doc_id": doc.id,
                            "status": "ok",
                            "uri": doc.uri,
                            "uris": uri_list,
                            "fetched_from_url": fetched_from_url,
                            "doc_type": doc.doc_type,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("raw_import failed idx=%s err=%s", idx, exc)
                    errors.append({"index": idx, "error": str(exc)})

            session.commit()
            result = {
                "inserted": inserted,
                "updated": updated,
                "skipped": skipped,
                "error_count": len(errors),
                "errors": errors[:20],
                "items": item_results[:50],
                "source_name": source.name,
                "project_key": project_key,
            }
            complete_job(job_id, result=result)
            return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        raise
