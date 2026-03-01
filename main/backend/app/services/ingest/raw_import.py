from __future__ import annotations

from datetime import date, datetime
import hashlib
import logging
import re
from typing import Any

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import Document, Source
from ..extraction.application import ExtractionApplicationService
from ..job_logger import complete_job, fail_job, start_job

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


def run_raw_import_documents(payload: dict[str, Any], project_key: str) -> dict[str, Any]:
    extraction_app = ExtractionApplicationService()
    now = datetime.utcnow()

    source_name = str(payload.get("source_name") or "raw_import").strip() or "raw_import"
    source_kind = str(payload.get("source_kind") or "manual").strip() or "manual"
    infer_from_links = bool(payload.get("infer_from_links", True))
    enable_extraction = bool(payload.get("enable_extraction", True))
    default_doc_type = str(payload.get("default_doc_type") or "raw_note")
    extraction_mode = str(payload.get("extraction_mode") or "auto")
    overwrite_on_uri = bool(payload.get("overwrite_on_uri", False))
    chunk_size = int(payload.get("chunk_size") or 2800)
    chunk_overlap = int(payload.get("chunk_overlap") or 200)
    max_chunks = int(payload.get("max_chunks") or 8)
    items = payload.get("items") or []
    if not isinstance(items, list):
        items = []

    job_id = start_job(
        "raw_import",
        {
            "project_key": project_key,
            "source_name": source_name,
            "items_total": len(items),
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
                    if not text:
                        skipped += 1
                        continue

                    uri_list = _normalize_uri_list(item, infer_from_links)
                    uri = uri_list[0] if uri_list else None
                    title = str(item.get("title") or "").strip() or None
                    if not title:
                        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
                        title = first_line[:240] if first_line else None
                    summary = str(item.get("summary") or "").strip() or None
                    if not summary:
                        summary = text[:400] if len(text) > 400 else None

                    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    doc_type = _normalize_doc_type_for_raw(item.get("doc_type"), default_doc_type)
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
                        "chunk_count": len(chunks),
                        "chunk_size": int(chunk_size),
                        "chunk_overlap": int(chunk_overlap),
                        "truncated_for_extraction": truncated,
                    }
                    extracted_base = doc.extracted_data if isinstance(doc.extracted_data, dict) else {}
                    extracted_base["_raw_input"] = _deep_merge_json(extracted_base.get("_raw_input", {}), raw_meta)

                    if enable_extraction:
                        mode = extraction_mode
                        if mode == "auto":
                            if doc_type in {"market", "market_info"}:
                                mode = "market"
                            elif doc_type in {"policy", "policy_regulation"}:
                                mode = "policy"
                            elif doc_type in {"social_sentiment", "social_feed"}:
                                mode = "social"
                            else:
                                mode = "social"

                        extracted_parts: list[dict[str, Any]] = []
                        for chunk in chunks:
                            if mode == "market":
                                extracted = extraction_app.extract_structured_enriched(chunk, include_market=True)
                            elif mode == "policy":
                                extracted = extraction_app.extract_structured_enriched(chunk, include_policy=True)
                            elif mode == "social":
                                extracted = extraction_app.extract_structured_enriched(chunk, include_sentiment=True)
                            else:
                                extracted = extraction_app.extract_structured_enriched(chunk)
                            if isinstance(extracted, dict) and extracted:
                                extracted_parts.append(extracted)

                        if extracted_parts:
                            extracted_base = _deep_merge_json(extracted_base, _merge_extracted_batch(extracted_parts))

                    doc.extracted_data = extracted_base
                    item_results.append(
                        {
                            "index": idx,
                            "doc_id": doc.id,
                            "status": "ok",
                            "uri": doc.uri,
                            "uris": uri_list,
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
