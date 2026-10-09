from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from hashlib import sha256
from typing import Annotated, Literal, NoReturn, TypedDict, TypeGuard

from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import (
    source_library_contract_failures,
)

from ..resource_pool.url_utils import domain_from_url
from ..source_library.types import (
    SourceMode,
    TerminalOutputDto,
    TerminalRecordView,
)


CONTRACT_VERSION = "frontdoor.ingress.v1"
_ALLOWED_INGRESS_TYPES = {"source_library", "raw_import", "discovery"}

FrontdoorSourceMode = SourceMode | Literal["raw_import", "discovery", "unknown"]
FrontdoorObject = dict[str, object]


class FrontdoorMeta(TypedDict):
    trace_id: str | None
    retryable: bool
    reason_code: str
    payload_hash: str


class FrontdoorIngressEnvelope(TypedDict):
    contract_version: str
    ingress_type: str
    project_key: str | None
    entrypoint: str
    source_mode: str
    source_ref: FrontdoorObject
    collection_payload: FrontdoorObject
    raw_snapshot: FrontdoorObject
    meta: FrontdoorMeta


class TerminalContext(TypedDict):
    platform: str
    ingestion_entrypoint: str
    source_mode: str
    article_extraction: FrontdoorObject


class DeferredDispatchPlan(TypedDict):
    run_extraction: Literal[False]
    run_writer: Literal[False]
    reason: str


class SourceLibraryTerminalPayload(TypedDict):
    terminal_output: TerminalOutputDto
    records: list[TerminalRecordView]
    source_artifacts: list[FrontdoorObject]
    provider_handoff: FrontdoorObject | None
    frontdoor_route_profile: FrontdoorObject | None
    frontdoor_router_contract: FrontdoorObject | None
    legacy_result: FrontdoorObject | None
    dispatch_plan: DeferredDispatchPlan


class MaterializedTerminalPayload(TypedDict):
    document_candidate: FrontdoorObject
    records: list[TerminalRecordView]
    source_artifacts: list[FrontdoorObject]
    terminal_context: TerminalContext
    extraction_plan: dict[str, bool]
    dispatch_plan: DeferredDispatchPlan


def _frontdoor_contract_failure(
    message: str,
    *,
    ingress_type: str,
    entrypoint: str,
    project_key: str | None,
    site: str,
) -> Failure:
    return source_library_contract_failures.fail(
        "frontdoor_entrypoint_rejected",
        message,
        {
            "item_key": None,
            "channel_key": str(ingress_type or "").strip() or None,
            "project_key": str(project_key or "").strip() or None,
            "entrypoint": str(entrypoint or "").strip() or None,
            "site": site,
            "public_exception": "ValueError",
            "public_message": message,
            "witness": "test:test_ingest_service_a_failure_lifts",
        },
    )


def _raise_frontdoor_contract_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    required = {"item_key", "channel_key", "project_key", "entrypoint", "site", "public_exception", "public_message", "witness"}
    if (
        not source_library_contract_failures.matches(failure)
        or required - set(context)
        or context.get("public_exception") != "ValueError"
    ):
        # kit:boundary owner=ingest.frontdoor.contract_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_ingest_service_a_failure_lifts
        raise TypeError("frontdoor contract lift context is incomplete or inconsistent")
    # kit:boundary owner=ingest.frontdoor.contract_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.contract_failure witness=test:test_ingest_service_a_failure_lifts
    raise ValueError(str(context["public_message"]))


def build_frontdoor_ingress_envelope(
    *,
    ingress_type: str,
    entrypoint: str,
    source_mode: str,
    project_key: str | None,
    source_ref: Mapping[str, object] | None = None,
    collection_payload: Mapping[str, object] | None = None,
    raw_snapshot: Mapping[str, object] | None = None,
    trace_id: str | None = None,
    retryable: bool = False,
    reason_code: str = "ok",
) -> Annotated[
    FrontdoorIngressEnvelope,
    "kit:non-authoritative derived_as=view fact_source=ingress_inputs+normalized_source_ref witness=test:test_w03_ingest_ports_authority_metadata",
]:
    normalized_type = str(ingress_type or "").strip().lower()
    if normalized_type not in _ALLOWED_INGRESS_TYPES:
        _raise_frontdoor_contract_failure(
            _frontdoor_contract_failure(
                f"unsupported ingress_type: {ingress_type}",
                ingress_type=ingress_type,
                entrypoint=entrypoint,
                project_key=project_key,
                site="build_frontdoor_ingress_envelope.ingress_type",
            )
        )
    normalized_entrypoint = str(entrypoint or "").strip()
    if not normalized_entrypoint:
        _raise_frontdoor_contract_failure(
            _frontdoor_contract_failure(
                "entrypoint is required",
                ingress_type=normalized_type,
                entrypoint=entrypoint,
                project_key=project_key,
                site="build_frontdoor_ingress_envelope.entrypoint",
            )
        )
    normalized_source_mode = str(source_mode or "").strip().lower() or "unknown"
    payload = _copy_payload(collection_payload)
    snapshot = _copy_payload(raw_snapshot) if raw_snapshot is not None else deepcopy(payload)
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
    terminal_output: TerminalOutputDto,
    legacy_result: FrontdoorObject | None = None,
) -> Annotated[
    FrontdoorIngressEnvelope,
    "kit:non-authoritative derived_as=view fact_source=terminal_output+legacy_result+frontdoor_route_inputs witness=test:test_w03_ingest_ports_authority_metadata",
]:
    terminal_view = _object_view(terminal_output)
    item = _object_view(terminal_view.get("item"))
    meta = _object_view(terminal_view.get("meta"))
    request = _object_view(terminal_view.get("request"))
    results = _object_view(terminal_view.get("results"))
    provider_handoff = _object_view(meta.get("provider_handoff")) or None
    route_profile = _object_view(meta.get("frontdoor_route_profile")) or None
    router_contract = _object_view(meta.get("frontdoor_router_contract")) or None
    if router_contract is None:
        router_contract = _object_view(route_profile.get("router_contract") if route_profile is not None else None) or None
    if router_contract is None:
        router_contract = _object_view(provider_handoff.get("router_contract") if provider_handoff is not None else None) or None
    external_manifest = _object_view(item.get("external_manifest"))
    records = _normalize_terminal_records(results.get("records"))
    source_mode = str(terminal_view.get("source_mode") or "protocol_search").strip().lower() or "protocol_search"
    source_artifacts = _collect_source_artifacts(records)
    article_body_record = _select_article_body_record(records, external_manifest)
    collection_payload: MaterializedTerminalPayload | SourceLibraryTerminalPayload
    if article_body_record is not None:
        collection_payload = {
            "document_candidate": _build_document_candidate_from_record(article_body_record, external_manifest=external_manifest),
            "records": list(records or []),
            "source_artifacts": source_artifacts,
            "terminal_context": {
                "platform": "source_library",
                "ingestion_entrypoint": "ingest.source_library.run",
                "source_mode": source_mode,
                "article_extraction": _object_view(
                    article_body_record["record_meta"].get("article_extraction")
                ),
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
            "terminal_output": terminal_output,
            "records": list(records),
            "source_artifacts": source_artifacts,
            "provider_handoff": deepcopy(provider_handoff) if provider_handoff is not None else None,
            "frontdoor_route_profile": deepcopy(route_profile) if route_profile is not None else None,
            "frontdoor_router_contract": deepcopy(router_contract) if router_contract is not None else None,
            "legacy_result": deepcopy(legacy_result) if legacy_result is not None else None,
            "dispatch_plan": {
                "run_extraction": False,
                "run_writer": False,
                "reason": "records_require_downstream_url_execution",
            },
        }
    return build_frontdoor_ingress_envelope(
        ingress_type="source_library",
        entrypoint="ingest.source_library.run",
        source_mode=source_mode,
        project_key=str(request.get("project_key") or "").strip() or None,
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
            "provider_type": provider_handoff.get("provider_type") if provider_handoff is not None else None,
            "provider_job_id": provider_handoff.get("provider_job_id") if provider_handoff is not None else None,
            "provider_dispatch": provider_handoff.get("provider_dispatch") if provider_handoff is not None else None,
            "frontdoor_route_hint": _first_object(route_profile, provider_handoff, "route_hint"),
            "fetch_strategy": _first_object(route_profile, provider_handoff, "fetch_strategy"),
            "render_required": True if bool(_first_object(route_profile, provider_handoff, "render_required")) else None,
            "router_state": router_contract.get("router_state") if router_contract is not None else None,
            "router_reason_code": router_contract.get("reason_code") if router_contract is not None else None,
        },
        collection_payload=collection_payload,
        raw_snapshot=terminal_output,
        trace_id=str(meta.get("trace_id") or "").strip() or None,
        retryable=bool(meta.get("retryable")),
        reason_code=str(meta.get("reason_code") or "ok").strip().lower() or "ok",
    )


def build_raw_import_ingress_envelope(
    *,
    project_key: str | None,
    payload: FrontdoorObject,
    item: FrontdoorObject,
) -> Annotated[
    FrontdoorIngressEnvelope,
    "kit:non-authoritative derived_as=view fact_source=raw_import_payload+item witness=test:test_w03_ingest_ports_authority_metadata",
]:
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
    item: FrontdoorObject,
) -> Annotated[
    FrontdoorIngressEnvelope,
    "kit:non-authoritative derived_as=view fact_source=discovery_item witness=test:test_w03_ingest_ports_authority_metadata",
]:
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
    value: Mapping[str, object] | None,
    *,
    ingress_type: str | None = None,
    entrypoint: str | None = None,
    source_mode: str | None = None,
    project_key: str | None = None,
) -> FrontdoorObject:
    source_ref = _copy_payload(value)
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
    out: FrontdoorObject = {}
    for key, raw in source_ref.items():
        if raw is None:
            continue
        text: object
        if _is_object_dict(raw) or _is_object_list(raw):
            text = raw
        else:
            text = str(raw).strip()
        if text == "":
            continue
        out[str(key)] = text
    return out


def _payload_hash(payload: FrontdoorObject) -> str:
    return sha256(repr(sorted(payload.items())).encode("utf-8", "ignore")).hexdigest()


def _first_record_url(records: list[TerminalRecordView]) -> str | None:
    for row in records:
        url = str(row.get("url") or "").strip()
        if url:
            return url
    return None


def _select_article_body_record(
    records: list[TerminalRecordView], external_manifest: dict[str, object],
) -> TerminalRecordView | None:
    if not _is_runtime_list(records) or not _is_runtime_dict(external_manifest):
        return None
    capabilities = _object_view(external_manifest.get("capabilities"))
    normalization = _object_view(external_manifest.get("normalization"))
    if not bool(capabilities.get("article_body")):
        return None
    if str(normalization.get("frontdoor_strategy") or "").strip().lower() == "records_only_defer":
        return None
    for row in records:
        content_text = str(row.get("content_text") or "").strip()
        if content_text:
            return row
    return None


def _build_document_candidate_from_record(
    record: TerminalRecordView, *, external_manifest: dict[str, object],
) -> FrontdoorObject:
    url = str(record.get("url") or "").strip()
    record_meta = record["record_meta"]
    external_summary = _object_view(record_meta.get("external_project"))
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
            "external_project": external_summary if external_summary else {
                "project_link": external_manifest.get("project_link"),
                "execution_mode": external_manifest.get("execution_mode"),
                "runner_ref": external_manifest.get("runner_ref"),
            },
        },
    }


def _collect_source_artifacts(records: list[TerminalRecordView]) -> list[FrontdoorObject]:
    out: list[FrontdoorObject] = []
    seen: set[str] = set()
    for row in records:
        record_url = str(row.get("url") or "").strip() or None
        record_meta = row["record_meta"]
        candidates: list[FrontdoorObject] = []
        artifact_ref = _object_view(record_meta.get("artifact_ref"))
        if artifact_ref:
            candidates.append(artifact_ref)
        source_artifacts = record_meta.get("source_artifacts")
        if _is_object_list(source_artifacts):
            for artifact in source_artifacts:
                artifact_view = _object_view(artifact)
                if artifact_view:
                    candidates.append(artifact_view)
        for artifact in candidates:
            locator = str(artifact.get("source_locator") or artifact.get("url") or "").strip()
            if not locator or locator in seen:
                continue
            seen.add(locator)
            if record_url:
                artifact.setdefault("parent_url", record_url)
            out.append({str(key): value for key, value in artifact.items() if value not in (None, "", [], {})})
    return out


def _copy_payload(value: Mapping[str, object] | None) -> FrontdoorObject:
    if value is None:
        return {}
    return {str(key): deepcopy(item) for key, item in value.items()}


def _is_runtime_dict(value: object) -> bool:
    return isinstance(value, dict)


def _is_runtime_list(value: object) -> bool:
    return isinstance(value, list)


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object_view(value: object) -> FrontdoorObject:
    if not _is_object_dict(value):
        return {}
    return {str(key): item for key, item in value.items()}


def _normalize_terminal_records(value: object) -> list[TerminalRecordView]:
    if not _is_object_list(value):
        return []
    records: list[TerminalRecordView] = []
    for raw_record in value:
        record = _object_view(raw_record)
        records.append(
            {
                "record_id": str(record.get("record_id") or ""),
                "url": _optional_text(record.get("url")),
                "title": _optional_text(record.get("title")),
                "content_text": _optional_text(record.get("content_text")),
                "summary": _optional_text(record.get("summary")),
                "published_at": _optional_text(record.get("published_at")),
                "author": _optional_text(record.get("author")),
                "language": _optional_text(record.get("language")),
                "source_label": _optional_text(record.get("source_label")),
                "record_meta": _object_view(record.get("record_meta")),
                "raw_ref": _object_view(record.get("raw_ref")),
            }
        )
    return records


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _first_object(
    primary: FrontdoorObject | None,
    secondary: FrontdoorObject | None,
    key: str,
) -> object:
    if primary is not None and primary.get(key) is not None:
        return primary[key]
    if secondary is None:
        return None
    return secondary.get(key)


__all__ = [
    "CONTRACT_VERSION",
    "build_discovery_ingress_envelope",
    "build_frontdoor_ingress_envelope",
    "build_raw_import_ingress_envelope",
    "build_source_library_ingress_envelope",
]
