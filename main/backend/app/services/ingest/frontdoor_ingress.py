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
    external_manifest = item.get("external_manifest") if isinstance(item.get("external_manifest"), dict) else {}
    records = ((terminal_output.get("results") or {}).get("records") if isinstance(terminal_output.get("results"), dict) else [])
    source_artifacts = _collect_source_artifacts(records)
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
        },
        collection_payload={
            "terminal_output": dict(terminal_output or {}),
            "records": list(records or []),
            "source_artifacts": source_artifacts,
            "legacy_result": dict(legacy_result or {}) if isinstance(legacy_result, dict) else None,
            "dispatch_plan": {
                "run_extraction": False,
                "run_writer": False,
                "reason": "records_require_downstream_url_execution",
            },
        },
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
