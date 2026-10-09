from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Protocol, TypeGuard, runtime_checkable

from sqlalchemy import select

from ...models.base import SessionLocal
from ...models.entities import Document
from ..job_logger import complete_job, fail_job, start_job
from ..resource_pool.http_port import fetch_html, make_html_parser
from .content_extraction import locate_main_text_from_html
from .frontdoor_ingress import build_raw_import_ingress_envelope
from .material_ingress import MaterialSourceContext, MaterialTargetSpec, build_material_frontdoor_payload
from .material_input import FetchedResource, GivenContent, PreparedMaterial, ResourceRef, prepare_material
from .postprocess_frontdoor import run_postprocess_frontdoor
from .structured_extraction import build_structured_summary
from .terminal_writer import get_or_create_source

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>()\"']+")
RawObject = dict[str, object]


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object_view(value: object) -> RawObject:
    if not _is_object_dict(value):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_int(value: object, default: int = 0) -> int:
    if not isinstance(value, (str, bytes, int, float)):
        return default
    try:
        return int(value)
    except (OverflowError, TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    if not isinstance(value, (str, bytes, int, float)):
        return default
    try:
        return float(value)
    except (OverflowError, TypeError, ValueError):
        return default


@runtime_checkable
class _HeaderItems(Protocol):
    def items(self) -> Iterable[tuple[object, object]]: ...


def _is_none(value: object) -> bool:
    return value is None


def _deep_merge_json(base: object, incoming: object) -> object:
    if _is_object_dict(base) and _is_object_dict(incoming):
        out: RawObject = {str(key): value for key, value in base.items()}
        for raw_key, value in incoming.items():
            key = str(raw_key)
            if key in out:
                out[key] = _deep_merge_json(out[key], value)
            else:
                out[key] = value
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


def _normalize_uri_list(item: Mapping[str, object], infer_from_text: bool) -> list[str]:
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
    if _is_object_list(uris):
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
        return locate_main_text_from_html(
            html,
            selectors=("article", "main article", "[role='main'] article", "main"),
            transform=lambda text: text[:50000],
        )
    except Exception:
        return ""
    return ""


def _extract_title_from_html(html: str) -> str:
    try:
        parser = make_html_parser(html)
        node = parser.css_first("title")
        if _is_none(node):
            return ""
        return str(node.text(strip=True) or "").strip()
    except Exception:
        return ""


def _response_mime_type(response: object) -> str:
    headers = getattr(response, "headers", None)
    if not isinstance(headers, _HeaderItems):
        return ""
    try:
        for name, value in headers.items():
            if str(name).lower() == "content-type":
                return str(value)
        return ""
    except Exception:
        return ""


def _is_explicit_text_mime(mime_type: str) -> bool:
    normalized = str(mime_type or "").split(";", 1)[0].strip().lower()
    return normalized in {"text/plain", "text/markdown"}


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


def merge_extracted_batch(parts: list[RawObject]) -> RawObject:
    merged: RawObject = {}
    all_entities: list[object] = []
    all_relations: list[object] = []

    def _entity_key(entity: object) -> str:
        if not _is_object_dict(entity):
            return str(entity)
        return f"{str(entity.get('text') or '').strip().lower()}::{str(entity.get('type') or '').strip().lower()}"

    def _rel_key(rel: object) -> str:
        if not _is_object_dict(rel):
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
        dynamic_part: object = part
        if not _is_object_dict(dynamic_part):
            continue
        merged = _object_view(_deep_merge_json(merged, part))
        er = part.get("entities_relations")
        if _is_object_dict(er):
            entities = er.get("entities")
            for entity in entities if _is_object_list(entities) else []:
                key = _entity_key(entity)
                if key and key not in seen_entities:
                    seen_entities.add(key)
                    all_entities.append(entity)
            relations = er.get("relations")
            for rel in relations if _is_object_list(relations) else []:
                key = _rel_key(rel)
                if key and key not in seen_relations:
                    seen_relations.add(key)
                    all_relations.append(rel)
        top_entities = part.get("entities")
        for entity in top_entities if _is_object_list(top_entities) else []:
            key = _entity_key(entity)
            if key and key not in seen_entities:
                seen_entities.add(key)
                all_entities.append(entity)
    if all_entities or all_relations:
        merged["entities_relations"] = {"entities": all_entities[:50], "relations": all_relations[:50]}
        if "entities" in merged and _is_object_list(merged.get("entities")):
            merged["entities"] = all_entities[:50]
    return merged


def _normalize_iso_date(value: object) -> date | None:
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


def _resolve_extraction_flags(extraction_mode: str, doc_type: str) -> dict[str, object]:
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
        "mode": mode,
        "include_policy": include_policy,
        "include_market": include_market,
        "include_sentiment": include_sentiment,
        "include_company": include_company,
        "include_product": include_product,
        "include_operation": include_operation,
    }


def derive_publish_date_from_extracted(extracted_data: Mapping[str, object]) -> date | None:
    policy = extracted_data.get("policy")
    if _is_object_dict(policy):
        derived = _normalize_iso_date(policy.get("effective_date"))
        if derived:
            return derived
    market = extracted_data.get("market")
    if _is_object_dict(market):
        derived = _normalize_iso_date(market.get("report_date"))
        if derived:
            return derived
    return None


def run_raw_import_documents(payload: RawObject, project_key: str) -> RawObject:
    now = datetime.now()

    source_name = str(payload.get("source_name") or "raw_import").strip() or "raw_import"
    source_kind = str(payload.get("source_kind") or "manual").strip() or "manual"
    infer_from_links = bool(payload.get("infer_from_links", True))
    enable_extraction = bool(payload.get("enable_extraction", True))
    default_doc_type = str(payload.get("default_doc_type") or "raw_note")
    extraction_mode = str(payload.get("extraction_mode") or "auto").strip().lower()
    overwrite_on_uri = bool(payload.get("overwrite_on_uri", False))
    chunk_size = _safe_int(payload.get("chunk_size") or 2800, 2800)
    chunk_overlap = _safe_int(payload.get("chunk_overlap") or 200, 200)
    max_chunks = _safe_int(payload.get("max_chunks") or 8, 8)
    fetch_url_when_text_empty = bool(payload.get("fetch_url_when_text_empty", True))
    fetch_url_also_when_text_present = bool(payload.get("fetch_url_also_when_text_present", True))
    url_fetch_timeout = _safe_float(payload.get("url_fetch_timeout") or 8.0, 8.0)
    url_to_market = bool(payload.get("url_to_market", True))
    raw_items: object = payload.get("items")
    items = raw_items if _is_object_list(raw_items) else []

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
            inserted = 0
            updated = 0
            skipped = 0
            errors: list[RawObject] = []
            item_results: list[RawObject] = []

            for idx, raw_item in enumerate(items):
                item = _object_view(raw_item)
                try:
                    given_text = str(item.get("text") or "")
                    text = given_text.strip()
                    uri_list = _normalize_uri_list(item, infer_from_links)
                    uri = uri_list[0] if uri_list else None
                    fetched_from_url = False
                    fetched_url_error = None
                    fetched_url_status = None
                    fetched_title = ""
                    prepared_resource: PreparedMaterial | None = None
                    given_only = str(item.get("material_input_kind") or "").strip().lower() == "given"
                    should_fetch_url = bool(
                        uri
                        and not given_only
                        and (
                            (not text and fetch_url_when_text_empty)
                            or (bool(text) and fetch_url_also_when_text_present)
                        )
                    )
                    if should_fetch_url and uri is not None:
                        try:
                            html, response = fetch_html(uri, timeout=url_fetch_timeout, retries=1)
                            fetched_url_status = _safe_int(getattr(response, "status_code", 0) or 0)
                            response_mime = _response_mime_type(response)
                            if _is_explicit_text_mime(response_mime):
                                # ResourceRef owns the locator, while this callback only
                                # transfers bytes already returned by the single fetch.
                                url_prepared = prepare_material(
                                    ResourceRef(uri),
                                    fetch_resource=lambda _url: FetchedResource(
                                        raw_bytes=response.content,
                                        mime_type=response_mime,
                                        final_url=str(getattr(response, "final_url", "") or uri),
                                    ),
                                )
                                if given_text.strip():
                                    text = _merge_raw_and_url_text(given_text, url_prepared.text)
                                else:
                                    prepared_resource = url_prepared
                                    text = prepared_resource.text
                                fetched_from_url = True
                            else:
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

                    # A supplied text body is already available. Keep the old
                    # mixed text/URL path until it has a separate fetch witness.
                    prepared_given = (
                        prepare_material(GivenContent.from_text(given_text, source_locator=uri))
                        if given_text.strip() and prepared_resource is None and not fetched_from_url
                        else None
                    )
                    prepared_material = prepared_resource or prepared_given

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
                    if item_doc_type is not None and not isinstance(item_doc_type, str):
                        error = "doc_type must be a string or null"
                        logger.warning("raw_import failed idx=%s err=%s", idx, error)
                        errors.append({"index": idx, "error": error})
                        continue
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
                    if doc and not overwrite_on_uri and not (
                        getattr(doc, "status", None) == "reference_only"
                        and not getattr(doc, "content", None)
                    ):
                        skipped += 1
                        item_results.append(
                            {
                                "index": idx,
                                "doc_id": getattr(doc, "id", None),
                                "status": "skipped_exists",
                                "uri": getattr(doc, "uri", None),
                            }
                        )
                        continue

                    if doc is None:
                        pass
                    else:
                        source = get_or_create_source(
                            session,
                            name=source_name,
                            kind=source_kind,
                            base_url=None,
                        )
                        setattr(doc, "source_id", getattr(source, "id", None))
                        setattr(doc, "state", item.get("state") or getattr(doc, "state", None))
                        setattr(doc, "doc_type", doc_type or getattr(doc, "doc_type", None))
                        setattr(doc, "title", title or getattr(doc, "title", None))
                        setattr(doc, "publish_date", publish_date_value or getattr(doc, "publish_date", None))
                        setattr(doc, "content", text)
                        if getattr(doc, "status", None) == "reference_only":
                            setattr(doc, "status", None)
                        setattr(doc, "summary", summary or getattr(doc, "summary", None))
                        setattr(doc, "text_hash", text_hash)
                        setattr(doc, "uri", uri or getattr(doc, "uri", None))
                        setattr(doc, "updated_at", now)
                        updated += 1

                    chunks, truncated = _chunk_text_for_extraction(
                        text,
                        chunk_size=chunk_size,
                        overlap=chunk_overlap,
                        max_chunks=max_chunks,
                    )
                    raw_meta: RawObject = {
                        "uris": uri_list,
                        "uri_count": len(uri_list),
                        "fetched_from_url": fetched_from_url,
                        "fetch_url_status": fetched_url_status,
                        "fetch_url_error": fetched_url_error,
                        "chunk_count": len(chunks),
                        "chunk_size": chunk_size,
                        "chunk_overlap": chunk_overlap,
                        "truncated_for_extraction": truncated,
                    }
                    if prepared_material is not None:
                        raw_meta["material_input"] = {
                            "kind": prepared_material.input_kind,
                            "raw_content_digest": prepared_material.raw_content_digest,
                            "mime_type": prepared_material.mime_type,
                        }
                    extracted_base = _object_view(
                        getattr(doc, "extracted_data", None) if doc is not None else None
                    )
                    raw_input = _object_view(
                        _deep_merge_json(extracted_base.get("_raw_input", {}), raw_meta)
                    )
                    extracted_base["_raw_input"] = raw_input
                    if prepared_material is None:
                        raw_input.pop("material_input", None)

                    extraction_flags = _resolve_extraction_flags(extraction_mode, doc_type)
                    mode = str(extraction_flags.get("mode") or extraction_mode)
                    extracted_base["_structured_summary"] = build_structured_summary(
                        extracted_base,
                        extraction_enabled=enable_extraction,
                        chunks_used=len(chunks),
                        extraction_mode=mode,
                    )

                    frontdoor_item: RawObject = {
                        **item,
                        "state": item.get("state") or None,
                        "doc_type": doc_type,
                        "title": title,
                        "publish_date": publish_date_value.isoformat() if publish_date_value else None,
                        "content": text,
                        "summary": summary,
                        "text_hash": text_hash,
                        "uri": uri,
                        "source_name": source_name,
                        "source_kind": source_kind,
                        "source_base_url": None,
                        "extracted_data_base": extracted_base,
                    }
                    ingress_envelope = build_raw_import_ingress_envelope(
                        project_key=project_key,
                        payload=payload,
                        item=frontdoor_item,
                    )
                    dynamic_collection_payload: object = ingress_envelope.get("collection_payload")
                    collection_payload = _object_view(dynamic_collection_payload)
                    ingress_envelope["collection_payload"] = collection_payload
                    if prepared_material is not None:
                        collection_payload.update(
                            build_material_frontdoor_payload(
                                prepared_material,
                                target=MaterialTargetSpec(
                                    doc_type=doc_type,
                                    title=title,
                                    summary=summary,
                                    publish_date=publish_date_value,
                                    state=item.get("state") or None,
                                    extraction_enabled=bool(enable_extraction),
                                    extraction_mode=mode,
                                    chunks=tuple(chunks),
                                    extraction_flags=extraction_flags,
                                ),
                                source=MaterialSourceContext(
                                    source_name=source_name,
                                    source_kind=source_kind,
                                    uri=uri,
                                    platform="raw_import",
                                    entrypoint="ingest.raw_import",
                                    source_mode="raw_import",
                                    http_status=fetched_url_status,
                                ),
                                extracted_data_base=extracted_base,
                            )
                        )
                    else:
                        collection_payload["document_candidate"] = {
                            "source_name": source_name,
                            "source_kind": source_kind,
                            "source_base_url": None,
                            "state": item.get("state") or None,
                            "doc_type": doc_type,
                            "title": title,
                            "publish_date": publish_date_value,
                            "content": text,
                            "summary": summary,
                            "text_hash": text_hash,
                            "uri": uri,
                            "status": None,
                            "extracted_data_base": extracted_base,
                        }
                        collection_payload["terminal_context"] = {
                            "platform": "raw_import",
                            "ingestion_entrypoint": "ingest.raw_import",
                            "source_mode": "raw_import",
                            "quality_score": 0.0,
                            "degradation_flags": [],
                            "http_status": fetched_url_status,
                            "capability_profile": {},
                            "light_filter": {},
                        }
                        collection_payload["extraction_plan"] = {
                            "enabled": bool(enable_extraction),
                            "mode": mode,
                            "chunks": list(chunks),
                            "include_policy": bool(extraction_flags.get("include_policy")),
                            "include_market": bool(extraction_flags.get("include_market")),
                            "include_sentiment": bool(extraction_flags.get("include_sentiment")),
                            "include_company": bool(extraction_flags.get("include_company")),
                            "include_product": bool(extraction_flags.get("include_product")),
                            "include_operation": bool(extraction_flags.get("include_operation")),
                        }

                    if doc is None:
                        frontdoor_result = run_postprocess_frontdoor(
                            ingress_envelope=ingress_envelope,
                            run_writer=True,
                        )
                        dynamic_frontdoor_data: object = frontdoor_result.get("data")
                        frontdoor_data = _object_view(dynamic_frontdoor_data)
                        writer_result = _object_view(frontdoor_data.get("writer_result"))
                        writer_inserted = _safe_int(writer_result.get("inserted") or 0)
                        inserted += writer_inserted
                        skipped += _safe_int(writer_result.get("skipped") or 0)
                        item_results.append(
                            {
                                "index": idx,
                                "doc_id": writer_result.get("doc_id"),
                                "status": "ok" if writer_inserted > 0 else str(writer_result.get("reason") or "skipped"),
                                "uri": uri,
                                "uris": uri_list,
                                "fetched_from_url": fetched_from_url,
                                "doc_type": doc_type,
                            }
                        )
                    else:
                        frontdoor_result = run_postprocess_frontdoor(
                            ingress_envelope=ingress_envelope,
                            run_writer=False,
                        )
                        dynamic_frontdoor_data = frontdoor_result.get("data")
                        frontdoor_data = _object_view(dynamic_frontdoor_data)
                        normalized_payload = _object_view(frontdoor_data.get("normalized_payload"))
                        normalized_extracted = normalized_payload.get("extracted_data", extracted_base)
                        setattr(doc, "extracted_data", normalized_extracted)
                        normalized_publish_date = normalized_payload.get("publish_date")
                        if normalized_publish_date and getattr(doc, "publish_date", None) is None:
                            setattr(
                                doc,
                                "publish_date",
                                _normalize_iso_date(normalized_publish_date)
                                or getattr(doc, "publish_date", None),
                            )
                        item_results.append(
                            {
                                "index": idx,
                                "doc_id": getattr(doc, "id", None),
                                "status": "ok",
                                "uri": getattr(doc, "uri", None),
                                "uris": uri_list,
                                "fetched_from_url": fetched_from_url,
                                "doc_type": getattr(doc, "doc_type", None),
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("raw_import failed idx=%s err=%s", idx, exc)
                    errors.append({"index": idx, "error": str(exc)})

            session.commit()
            result: RawObject = {
                "inserted": inserted,
                "updated": updated,
                "skipped": skipped,
                "error_count": len(errors),
                "errors": errors[:20],
                "items": item_results[:50],
                "source_name": source_name,
                "project_key": project_key,
            }
            job_status = "failed" if items and len(errors) == len(items) else "completed"
            complete_job(job_id, status=job_status, result=result)
            return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        # kit:boundary owner=ingest.raw_import class=SHELL_BOUNDARY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_latest_service_a_ingest_shell_boundaries_reraise_original_errors
        raise


_merge_extracted_batch = merge_extracted_batch
_derive_publish_date_from_extracted = derive_publish_date_from_extracted

__all__ = [
    "derive_publish_date_from_extracted",
    "merge_extracted_batch",
    "run_raw_import_documents",
]
