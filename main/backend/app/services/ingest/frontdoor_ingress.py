from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

from ..resource_pool.url_utils import domain_from_url


CONTRACT_VERSION = "frontdoor.ingress.v1"
_ALLOWED_INGRESS_TYPES = {"source_library", "raw_import", "discovery"}


def build_frontdoor_ingress_envelope(
    *,
    ingress_type: str,
    entrypoint: str,
    source_mode: str,
    project_key: str | None,
    source_ref: dict[str, Any] | None = None,
    collection_payload: dict[str, Any] | None = None,
    raw_snapshot: dict[str, Any] | None = None,
    trace_id: str | None = None,
    retryable: bool = False,
    reason_code: str = "ok",
) -> dict[str, Any]:
    normalized_type = str(ingress_type or "").strip().lower()
    if normalized_type not in _ALLOWED_INGRESS_TYPES:
        raise ValueError(f"unsupported ingress_type: {ingress_type}")
    normalized_entrypoint = str(entrypoint or "").strip()
    if not normalized_entrypoint:
        raise ValueError("entrypoint is required")
    normalized_source_mode = str(source_mode or "").strip().lower() or "unknown"
    payload = dict(collection_payload or {})
    snapshot = deepcopy(raw_snapshot if isinstance(raw_snapshot, dict) else payload)
    return {
        "contract_version": CONTRACT_VERSION,
        "ingress_type": normalized_type,
        "project_key": str(project_key or "").strip() or None,
        "entrypoint": normalized_entrypoint,
        "source_mode": normalized_source_mode,
        "source_ref": _normalize_source_ref(
            source_ref,
            ingress_type=normalized_type,
            entrypoint=normalized_entrypoint,
            source_mode=normalized_source_mode,
            project_key=str(project_key or "").strip() or None,
        ),
        "collection_payload": payload,
        "raw_snapshot": snapshot,
        "meta": {
            "trace_id": str(trace_id or "").strip() or None,
            "retryable": bool(retryable),
            "reason_code": str(reason_code or "ok").strip().lower() or "ok",
            "payload_hash": _payload_hash(snapshot),
        },
    }


def build_source_library_ingress_envelope(
    *,
    terminal_output: dict[str, Any],
    legacy_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = terminal_output.get("item") if isinstance(terminal_output.get("item"), dict) else {}
    meta = terminal_output.get("meta") if isinstance(terminal_output.get("meta"), dict) else {}
    provider_handoff = meta.get("provider_handoff") if isinstance(meta.get("provider_handoff"), dict) else None
    route_profile = meta.get("frontdoor_route_profile") if isinstance(meta.get("frontdoor_route_profile"), dict) else None
    router_contract = meta.get("frontdoor_router_contract") if isinstance(meta.get("frontdoor_router_contract"), dict) else None
    if router_contract is None and isinstance((route_profile or {}).get("router_contract"), dict):
        router_contract = (route_profile or {}).get("router_contract")
    if router_contract is None and isinstance((provider_handoff or {}).get("router_contract"), dict):
        router_contract = (provider_handoff or {}).get("router_contract")
    external_manifest = item.get("external_manifest") if isinstance(item.get("external_manifest"), dict) else {}
    records = ((terminal_output.get("results") or {}).get("records") if isinstance(terminal_output.get("results"), dict) else [])
    source_artifacts = _collect_source_artifacts(records)
    article_body_record = _select_article_body_record(records, external_manifest)
    if article_body_record is not None:
        collection_payload = {
            "document_candidate": _build_document_candidate_from_record(article_body_record, external_manifest=external_manifest),
            "records": list(records or []),
            "source_artifacts": source_artifacts,
            "terminal_context": {
                "platform": "source_library",
                "ingestion_entrypoint": "ingest.source_library.run",
                "source_mode": str(terminal_output.get("source_mode") or "protocol_search"),
                "article_extraction": _record_article_extraction_meta(article_body_record),
            },
            "extraction_plan": {"enabled": False},
            "dispatch_plan": {
                "run_extraction": False,
                "run_writer": False,
                "reason": "external_project_article_body_materialized",
            },
        }
    else:
        collection_payload = {
            "terminal_output": dict(terminal_output or {}),
            "records": list(records or []),
            "source_artifacts": source_artifacts,
            "provider_handoff": dict(provider_handoff or {}) if provider_handoff else None,
            "frontdoor_route_profile": dict(route_profile or {}) if route_profile else None,
            "frontdoor_router_contract": dict(router_contract or {}) if router_contract else None,
            "legacy_result": dict(legacy_result or {}) if isinstance(legacy_result, dict) else None,
            "dispatch_plan": {
                "run_extraction": False,
                "run_writer": False,
                "reason": "records_require_downstream_url_execution",
            },
        }
    return build_frontdoor_ingress_envelope(
        ingress_type="source_library",
        entrypoint="ingest.source_library.run",
        source_mode=str(terminal_output.get("source_mode") or "protocol_search"),
        project_key=((terminal_output.get("request") or {}).get("project_key") if isinstance(terminal_output.get("request"), dict) else None),
        source_ref={
            "item_key": item.get("item_key"),
            "item_type": item.get("item_type"),
            "managed_by": item.get("managed_by"),
            "locator": item.get("item_key"),
            "url": _first_record_url(records),
            "project_link": external_manifest.get("project_link"),
            "source_kind": external_manifest.get("source_kind"),
            "execution_mode": external_manifest.get("execution_mode"),
            "runner_ref": external_manifest.get("runner_ref"),
            "provider_type": (provider_handoff or {}).get("provider_type"),
            "provider_job_id": (provider_handoff or {}).get("provider_job_id"),
            "provider_dispatch": (provider_handoff or {}).get("provider_dispatch"),
            "frontdoor_route_hint": (route_profile or provider_handoff or {}).get("route_hint"),
            "fetch_strategy": (route_profile or provider_handoff or {}).get("fetch_strategy"),
            "render_required": True if bool((route_profile or provider_handoff or {}).get("render_required")) else None,
            "router_state": (router_contract or {}).get("router_state"),
            "router_reason_code": (router_contract or {}).get("reason_code"),
        },
        collection_payload=collection_payload,
        raw_snapshot=terminal_output,
        trace_id=meta.get("trace_id"),
        retryable=bool(meta.get("retryable")),
        reason_code=str(meta.get("reason_code") or "ok"),
    )


def build_raw_import_ingress_envelope(
    *,
    project_key: str | None,
    payload: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    return build_frontdoor_ingress_envelope(
        ingress_type="raw_import",
        entrypoint="ingest.raw_import",
        source_mode="raw_import",
        project_key=project_key,
        source_ref={"locator": str(item.get("uri") or item.get("title") or item.get("index") or "")},
        collection_payload={"raw_import_payload": dict(payload or {}), "item": dict(item or {})},
        raw_snapshot={"payload": dict(payload or {}), "item": dict(item or {})},
    )


def build_discovery_ingress_envelope(
    *,
    project_key: str | None,
    item: dict[str, Any],
) -> dict[str, Any]:
    return build_frontdoor_ingress_envelope(
        ingress_type="discovery",
        entrypoint="discovery.store",
        source_mode="discovery",
        project_key=project_key,
        source_ref={"url": item.get("uri"), "locator": item.get("uri")},
        collection_payload={"document_candidate": dict(item or {})},
        raw_snapshot=dict(item or {}),
    )


def _normalize_source_ref(
    value: dict[str, Any] | None,
    *,
    ingress_type: str | None = None,
    entrypoint: str | None = None,
    source_mode: str | None = None,
    project_key: str | None = None,
) -> dict[str, Any]:
    source_ref = dict(value or {})
    url = str(source_ref.get("url") or source_ref.get("site_entry_url") or "").strip() or None
    locator = str(source_ref.get("locator") or url or entrypoint or "").strip() or None
    domain = (
        str(source_ref.get("domain") or source_ref.get("entry_domain") or domain_from_url(url or "") or "").strip().lower()
        or None
    )
    if locator:
        source_ref.setdefault("locator", locator)
    if url:
        source_ref.setdefault("url", url)
    if domain:
        source_ref.setdefault("domain", domain)
    if ingress_type:
        source_ref.setdefault("ingress_type", ingress_type)
    if entrypoint:
        source_ref.setdefault("entrypoint", entrypoint)
    if source_mode:
        source_ref.setdefault("source_mode", source_mode)
    if project_key:
        source_ref.setdefault("project_key", project_key)
    out: dict[str, Any] = {}
    for key, raw in source_ref.items():
        if raw is None:
            continue
        text = str(raw).strip() if not isinstance(raw, (dict, list)) else raw
        if text == "":
            continue
        out[str(key)] = text
    return out


def _payload_hash(payload: dict[str, Any]) -> str:
    return sha256(repr(sorted(payload.items())).encode("utf-8", "ignore")).hexdigest()


def _first_record_url(records: Any) -> str | None:
    if not isinstance(records, list):
        return None
    for row in records:
        if isinstance(row, dict):
            url = str(row.get("url") or "").strip()
            if url:
                return url
    return None


def _select_article_body_record(records: Any, external_manifest: Any) -> dict[str, Any] | None:
    if not isinstance(records, list) or not isinstance(external_manifest, dict):
        return None
    capabilities = external_manifest.get("capabilities") if isinstance(external_manifest.get("capabilities"), dict) else {}
    normalization = external_manifest.get("normalization") if isinstance(external_manifest.get("normalization"), dict) else {}
    if not bool(capabilities.get("article_body")):
        return None
    if str(normalization.get("frontdoor_strategy") or "").strip().lower() == "records_only_defer":
        return None
    for row in records:
        if not isinstance(row, dict):
            continue
        if str(row.get("content_text") or "").strip():
            return dict(row)
    return None


def _record_article_extraction_meta(record: dict[str, Any]) -> dict[str, Any]:
    record_meta = record.get("record_meta") if isinstance(record.get("record_meta"), dict) else {}
    article_extraction = record_meta.get("article_extraction")
    return dict(article_extraction or {}) if isinstance(article_extraction, dict) else {}


def _build_document_candidate_from_record(record: dict[str, Any], *, external_manifest: dict[str, Any]) -> dict[str, Any]:
    url = str(record.get("url") or "").strip()
    record_meta = dict(record.get("record_meta") or {}) if isinstance(record.get("record_meta"), dict) else {}
    external_summary = record_meta.get("external_project") if isinstance(record_meta.get("external_project"), dict) else {}
    return {
        "source_name": str(record.get("source_label") or external_manifest.get("display_name") or "source_library"),
        "source_kind": str(external_manifest.get("source_kind") or "source_library"),
        "source_base_url": str(external_manifest.get("project_link") or "").strip() or None,
        "state": None,
        "doc_type": "source_library_article",
        "title": str(record.get("title") or "").strip() or None,
        "summary": str(record.get("summary") or "").strip() or None,
        "publish_date": record.get("published_at"),
        "content": str(record.get("content_text") or "").strip(),
        "text_hash": None,
        "uri": url or None,
        "status": None,
        "extracted_data_base": {
            "source_label": record.get("source_label"),
            "record_meta": record_meta,
            "external_project": external_summary or {
                "project_link": external_manifest.get("project_link"),
                "execution_mode": external_manifest.get("execution_mode"),
                "runner_ref": external_manifest.get("runner_ref"),
            },
        },
    }


def _collect_source_artifacts(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in records:
        if not isinstance(row, dict):
            continue
        record_url = str(row.get("url") or "").strip() or None
        record_meta = row.get("record_meta") if isinstance(row.get("record_meta"), dict) else {}
        candidates: list[dict[str, Any]] = []
        artifact_ref = record_meta.get("artifact_ref")
        if isinstance(artifact_ref, dict):
            candidates.append(dict(artifact_ref))
        for artifact in record_meta.get("source_artifacts") or []:
            if isinstance(artifact, dict):
                candidates.append(dict(artifact))
        for artifact in candidates:
            locator = str(artifact.get("source_locator") or artifact.get("url") or "").strip()
            if not locator or locator in seen:
                continue
            seen.add(locator)
            if record_url:
                artifact.setdefault("parent_url", record_url)
            out.append({str(key): value for key, value in artifact.items() if value not in (None, "", [], {})})
    return out


__all__ = [
    "CONTRACT_VERSION",
    "build_discovery_ingress_envelope",
    "build_frontdoor_ingress_envelope",
    "build_raw_import_ingress_envelope",
    "build_source_library_ingress_envelope",
]
