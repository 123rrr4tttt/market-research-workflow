from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from .external_project import build_external_project_summary, get_external_project_manifest

CONTRACT_VERSION = "source_library.terminal_output.v1"
PROVIDER_HANDOFF_CONTRACT_VERSION = "source_library.provider_handoff.v1"
_ALLOWED_SOURCE_MODES = {"protocol_search", "provider_harvest", "site_search", "url_execution"}


def to_terminal_output_dto(result_payload: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = result_payload if isinstance(result_payload, dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    execution_request = result.get("execution_request") if isinstance(result.get("execution_request"), dict) else {}

    source_mode = _resolve_source_mode(payload=payload, result=result, execution_request=execution_request)
    params = execution_request.get("params") if isinstance(execution_request.get("params"), dict) else payload.get("params")
    normalized_params = params if isinstance(params, dict) else {}

    errors = _collect_errors(result)
    records = _build_clean_records(payload=payload, result=result)
    stats = _build_stats(source_mode=source_mode, result=result, params=normalized_params, errors=errors, records=records)
    status = _resolve_status(stats)
    provider_handoff = _resolve_provider_handoff(payload=payload, result=result)
    frontdoor_route_profile = _resolve_frontdoor_route_profile(
        params=normalized_params,
        provider_handoff=provider_handoff,
    )
    frontdoor_router_contract = _resolve_frontdoor_router_contract(
        params=normalized_params,
        provider_handoff=provider_handoff,
        route_profile=frontdoor_route_profile,
    )

    # Empty/invalid payload should be safe and observable in terminal output.
    if not payload and not errors:
        errors.append({"source": "payload", "message": "empty payload"})
        stats["errors"] = max(int(stats.get("errors") or 0), 1)
        status = "error"

    return {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "source_mode": source_mode,
        "item": {
            "item_key": str(payload.get("item_key") or execution_request.get("item_key") or ""),
            "item_type": _nullable_str(payload.get("item_type") or _as_dict(payload.get("extra")).get("item_type")),
            "managed_by": _nullable_str(payload.get("managed_by") or _as_dict(payload.get("extra")).get("managed_by")),
            "external_manifest": _resolve_external_manifest_summary(payload),
        },
        "request": {
            "project_key": _nullable_str(execution_request.get("project_key") or payload.get("project_key")),
            "query_terms": _normalize_query_terms(normalized_params),
            "time_window": _normalize_time_window(normalized_params),
            "paging": _normalize_paging(normalized_params),
            "limits": _normalize_limits(normalized_params),
        },
        "results": {
            "records": records,
            "stats": stats,
        },
        "errors": errors,
        "meta": {
            "reason_code": _resolve_reason_code(stats=stats, errors=errors, records=records),
            "retryable": bool(result.get("retryable")),
            "provider": _nullable_str(result.get("provider") or payload.get("provider")),
            "provider_job_id": _nullable_str(result.get("provider_job_id") or payload.get("provider_job_id")),
            "trace_id": _nullable_str(result.get("trace_id") or payload.get("trace_id")),
            "warnings": list(execution_request.get("warnings") or []),
            "provider_handoff": provider_handoff,
            "frontdoor_route_profile": frontdoor_route_profile,
            "frontdoor_router_contract": frontdoor_router_contract,
            "raw_result_keys": sorted(result.keys()),
        },
        "raw_snapshot": deepcopy(payload),
    }


def build_terminal_output_dto(result_payload: Dict[str, Any] | None) -> Dict[str, Any]:
    return to_terminal_output_dto(result_payload)


def build_source_library_terminal_output(
    *,
    result_payload: Dict[str, Any] | None,
    collect_result: Any,
) -> Dict[str, Any]:
    # `collect_result` is reserved for compatibility fallback; the main path maps from result payload.
    _ = collect_result
    return to_terminal_output_dto(result_payload)


def _resolve_source_mode(*, payload: Dict[str, Any], result: Dict[str, Any], execution_request: Dict[str, Any]) -> str:
    source_mode = str(execution_request.get("source_mode") or "").strip().lower()
    if source_mode in _ALLOWED_SOURCE_MODES:
        return source_mode

    channel_key = str(payload.get("channel_key") or "").strip().lower()
    if isinstance(result.get("by_url"), list):
        return "url_execution"
    if channel_key == "handler.cluster" or isinstance(result.get("routing_result"), dict):
        return "site_search"
    if channel_key.startswith("crawler."):
        return "provider_harvest"
    return "protocol_search"


def _normalize_query_terms(params: Dict[str, Any]) -> List[str]:
    raw = params.get("query_terms")
    if raw is None:
        raw = params.get("keywords")
    if raw is None:
        raw = params.get("query")
    if raw is None:
        raw = params.get("q")

    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        if "," in raw:
            return [segment.strip() for segment in raw.split(",") if segment.strip()]
        return [raw.strip()]
    return []


def _normalize_time_window(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "days_back": _to_optional_int(params.get("days_back")),
        "start_time": _nullable_str(params.get("start_time") or params.get("start_at") or params.get("start_date") or params.get("since")),
        "end_time": _nullable_str(params.get("end_time") or params.get("end_at") or params.get("end_date") or params.get("until")),
    }


def _normalize_paging(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "page": _to_optional_int(params.get("page")),
        "start_offset": _to_optional_int(params.get("start_offset") or params.get("offset")),
        "cursor": _nullable_str(params.get("cursor")),
    }


def _normalize_limits(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "limit": _to_optional_int(params.get("limit")),
        "max_items": _to_optional_int(params.get("max_items")),
        "per_keyword_limit": _to_optional_int(params.get("per_keyword_limit")),
        "max_candidates": _to_optional_int(params.get("max_candidates")),
        "ingest_limit": _to_optional_int(params.get("ingest_limit")),
    }


def _collect_errors(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for message in result.get("errors") or []:
        text = str(message).strip()
        if text:
            out.append({"source": "result.errors", "message": text})

    for row in result.get("by_url") or []:
        if not isinstance(row, dict):
            continue
        text = str(row.get("error") or "").strip()
        if text:
            out.append(
                {
                    "source": "result.by_url",
                    "message": text,
                    "url": _nullable_str(row.get("url")),
                    "channel_key": _nullable_str(row.get("channel_key")),
                }
            )

    for detail in result.get("error_details") or []:
        if not isinstance(detail, dict):
            continue
        text = str(detail.get("error") or "").strip()
        if text:
            out.append(
                {
                    "source": "result.error_details",
                    "message": text,
                    "url": _nullable_str(detail.get("url")),
                    "channel_key": _nullable_str(detail.get("channel_key")),
                }
            )

    return out


def _build_stats(
    *,
    source_mode: str,
    result: Dict[str, Any],
    params: Dict[str, Any],
    errors: List[Dict[str, Any]],
    records: List[Dict[str, Any]],
) -> Dict[str, int]:
    normalized = len(records)
    fetched = 0
    by_url = result.get("by_url") if isinstance(result.get("by_url"), list) else []
    candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []

    if source_mode == "url_execution":
        fetched = len(by_url)
    elif source_mode == "site_search":
        fetched = len(candidates) if candidates else len(by_url)
    elif normalized > 0:
        fetched = normalized
    if fetched <= 0:
        maybe_urls = params.get("urls") if isinstance(params.get("urls"), list) else []
        fetched = len(maybe_urls)
    if fetched <= 0 and normalized > 0:
        fetched = normalized
    dropped = max(fetched - normalized, 0)

    return {
        "fetched": max(fetched, 0),
        "normalized": max(normalized, 0),
        "dropped": max(dropped, 0),
        "errors": max(len(errors), 0),
    }


def _resolve_status(stats: Dict[str, int]) -> str:
    normalized = int(stats.get("normalized") or 0)
    dropped = int(stats.get("dropped") or 0)
    error_count = int(stats.get("errors") or 0)

    if normalized > 0 and error_count <= 0 and dropped <= 0:
        return "ok"
    if normalized > 0 and (error_count > 0 or dropped > 0):
        return "partial"
    if normalized <= 0 and error_count > 0:
        return "error"
    if normalized <= 0 and dropped > 0:
        return "partial"
    return "ok"


def _resolve_reason_code(
    *,
    stats: Dict[str, int],
    errors: List[Dict[str, Any]],
    records: List[Dict[str, Any]],
) -> str:
    if errors:
        return "fetch_errors"
    if not records:
        return "empty"
    if int(stats.get("dropped") or 0) > 0:
        return "partial_records"
    return "ok"


def _build_clean_records(*, payload: Dict[str, Any], result: Dict[str, Any]) -> List[Dict[str, Any]]:
    direct = result.get("records")
    if isinstance(direct, list):
        normalized = [_normalize_record(row) for row in direct if isinstance(row, dict)]
        return [row for row in normalized if row]

    records: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    by_url = result.get("by_url") if isinstance(result.get("by_url"), list) else []
    for index, row in enumerate(by_url):
        normalized = _record_from_by_url_row(row=row, fallback_item_key=str(payload.get("item_key") or ""), index=index)
        if not normalized:
            continue
        dedupe_key = str(normalized.get("url") or normalized.get("record_id") or f"row:{index}")
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        records.append(normalized)

    candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
    for index, candidate in enumerate(candidates):
        url = str(candidate or "").strip()
        if not url:
            continue
        if url in seen_keys:
            continue
        seen_keys.add(url)
        records.append(
            {
                "record_id": f"candidate:{index}:{url}",
                "url": url,
                "title": None,
                "content_text": None,
                "summary": None,
                "published_at": None,
                "author": None,
                "language": None,
                "source_label": "candidate_url",
                "record_meta": {"origin": "result.candidates"},
                "raw_ref": {"source": "result.candidates", "index": index},
            }
        )
    return records


def _record_from_by_url_row(*, row: Any, fallback_item_key: str, index: int) -> Dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    url = _nullable_str(row.get("url"))
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    if row.get("error") and not result:
        return None
    return _normalize_record(
        {
            "record_id": result.get("record_id") or f"{fallback_item_key or 'source'}:{index}",
            "url": url,
            "title": result.get("title"),
            "content_text": result.get("content_text") or result.get("content_preview") or result.get("excerpt"),
            "summary": result.get("summary"),
            "published_at": result.get("published_at"),
            "author": result.get("author"),
            "language": result.get("language"),
            "source_label": result.get("source_label") or row.get("channel_key"),
            "record_meta": {
                "channel_key": _nullable_str(row.get("channel_key")),
                "status": _nullable_str(result.get("status")),
                "http_status": result.get("http_status"),
                "execution_layer": result.get("execution_layer"),
                "fallback_from_channel_key": _nullable_str(row.get("fallback_from_channel_key")),
                "fallback_reason": _nullable_str(row.get("fallback_reason")),
                "provider_handoff": dict(row.get("provider_handoff") or {})
                if isinstance(row.get("provider_handoff"), dict)
                else None,
                "frontdoor_route_profile": dict(row.get("frontdoor_route_profile") or {})
                if isinstance(row.get("frontdoor_route_profile"), dict)
                else None,
            },
            "raw_ref": {"source": "result.by_url", "url": url},
        }
    )


def _normalize_record(row: Dict[str, Any]) -> Dict[str, Any] | None:
    url = _nullable_str(row.get("url"))
    title = _nullable_str(row.get("title"))
    content_text = _nullable_str(row.get("content_text"))
    summary = _nullable_str(row.get("summary"))
    if not url and not title and not content_text:
        return None
    return {
        "record_id": str(row.get("record_id") or url or title or "record"),
        "url": url,
        "title": title,
        "content_text": content_text,
        "summary": summary,
        "published_at": _nullable_str(row.get("published_at")),
        "author": _nullable_str(row.get("author")),
        "language": _nullable_str(row.get("language")),
        "source_label": _nullable_str(row.get("source_label")),
        "record_meta": _as_dict(row.get("record_meta")),
        "raw_ref": row.get("raw_ref") if isinstance(row.get("raw_ref"), dict) else {},
    }


def _resolve_provider_handoff(*, payload: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any] | None:
    direct = result.get("provider_handoff")
    if isinstance(direct, dict):
        return _clean_provider_handoff(direct)

    for row in _iter_by_url_rows(result):
        candidate = row.get("provider_handoff")
        if isinstance(candidate, dict):
            return _clean_provider_handoff(candidate)

    provider_type = _nullable_str(result.get("provider_type") or payload.get("provider_type"))
    provider_job_id = _nullable_str(result.get("provider_job_id") or payload.get("provider_job_id"))
    provider_status = _nullable_str(result.get("provider_status") or payload.get("provider_status"))
    runtime_channel = result.get("runtime_channel") if isinstance(result.get("runtime_channel"), dict) else {}
    layer_boundary = (
        runtime_channel.get("layer_boundary")
        if isinstance(runtime_channel.get("layer_boundary"), dict)
        else {}
    )
    if not (provider_type or provider_job_id or provider_status or runtime_channel):
        return None
    return _clean_provider_handoff(
        {
            "contract_version": PROVIDER_HANDOFF_CONTRACT_VERSION,
            "handoff_kind": "provider_harvest",
            "channel_key": payload.get("channel_key"),
            "provider": result.get("provider") or payload.get("provider"),
            "provider_type": provider_type,
            "provider_dispatch": layer_boundary.get("provider_dispatch"),
            "downstream_handoff": layer_boundary.get("downstream_handoff") or "ingest",
            "provider_job_id": provider_job_id,
            "provider_status": provider_status,
            "attempt_count": result.get("attempt_count") or payload.get("attempt_count"),
        }
    )


def _iter_by_url_rows(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    direct_rows = result.get("by_url") if isinstance(result.get("by_url"), list) else []
    rows.extend(row for row in direct_rows if isinstance(row, dict))
    routing_result = result.get("routing_result") if isinstance(result.get("routing_result"), dict) else {}
    nested_rows = routing_result.get("by_url") if isinstance(routing_result.get("by_url"), list) else []
    rows.extend(row for row in nested_rows if isinstance(row, dict))
    return rows


def _clean_provider_handoff(value: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(value or {})
    out.setdefault("contract_version", PROVIDER_HANDOFF_CONTRACT_VERSION)
    return {str(key): raw for key, raw in out.items() if raw not in (None, "", [], {})}


def _resolve_frontdoor_route_profile(
    *,
    params: Dict[str, Any],
    provider_handoff: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    handoff_profile = (
        provider_handoff.get("frontdoor_route_profile")
        if isinstance(provider_handoff, dict) and isinstance(provider_handoff.get("frontdoor_route_profile"), dict)
        else None
    )
    if isinstance(handoff_profile, dict):
        return dict(handoff_profile)
    params_profile = params.get("frontdoor_route_profile")
    if isinstance(params_profile, dict):
        return dict(params_profile)
    route_hint = _nullable_str(params.get("frontdoor_route_hint"))
    fetch_strategy = _nullable_str(params.get("frontdoor_fetch_strategy"))
    render_required = params.get("frontdoor_render_required")
    if not (route_hint or fetch_strategy or render_required is not None):
        return None
    out: Dict[str, Any] = {
        "route_hint": route_hint,
        "fetch_strategy": fetch_strategy,
        "render_required": bool(render_required),
    }
    return {key: value for key, value in out.items() if value is not None}


def _resolve_frontdoor_router_contract(
    *,
    params: Dict[str, Any],
    provider_handoff: Dict[str, Any] | None,
    route_profile: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    if isinstance(route_profile, dict) and isinstance(route_profile.get("router_contract"), dict):
        return dict(route_profile.get("router_contract") or {})
    if isinstance(provider_handoff, dict) and isinstance(provider_handoff.get("router_contract"), dict):
        return dict(provider_handoff.get("router_contract") or {})
    params_contract = params.get("frontdoor_router_contract")
    if isinstance(params_contract, dict):
        return dict(params_contract)
    return None


def _nullable_str(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _to_optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _to_non_negative_int(value: Any) -> int:
    number = _to_optional_int(value)
    if number is None:
        return 0
    return max(number, 0)


def _resolve_external_manifest_summary(payload: Dict[str, Any]) -> Dict[str, Any] | None:
    extra = _as_dict(payload.get("extra"))
    manifest = get_external_project_manifest(
        extra,
        item_key=_nullable_str(payload.get("item_key")),
        display_name=_nullable_str(payload.get("name")),
    )
    return build_external_project_summary(manifest)


__all__ = [
    "CONTRACT_VERSION",
    "build_source_library_terminal_output",
    "build_terminal_output_dto",
    "to_terminal_output_dto",
]
