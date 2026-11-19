from __future__ import annotations

from copy import deepcopy
from typing import Annotated, TypeGuard

from .external_project import build_external_project_summary, get_external_project_manifest
from ..crawlers.base import is_crawler_dispatch_acknowledged
from .types import (
    SourceMode,
    TerminalCollectResult,
    TerminalErrorView,
    TerminalOutputDto,
    TerminalRecordView,
    TerminalStatsView,
    TerminalStatus,
    TerminalTimeWindowView,
    TerminalPagingView,
    TerminalLimitsView,
)

CONTRACT_VERSION = "source_library.terminal_output.v1"
PROVIDER_HANDOFF_CONTRACT_VERSION = "source_library.provider_handoff.v1"
def to_terminal_output_dto(result_payload: dict[str, object] | None) -> TerminalOutputDto:
    payload = dict(result_payload) if isinstance(result_payload, dict) else {}
    result = _object(payload.get("result"))
    execution_request = _object(result.get("execution_request"))

    source_mode = _resolve_source_mode(payload=payload, result=result, execution_request=execution_request)
    params = _optional_object(execution_request.get("params"))
    if params is None:
        params = _optional_object(payload.get("params")) or {}
    normalized_params = params

    errors = _collect_errors(result)
    records = _build_clean_records(payload=payload, result=result)
    stats = _build_stats(source_mode=source_mode, result=result, params=normalized_params, errors=errors, records=records)
    readback = _extract_terminal_readback(payload=payload, result=result)
    status: TerminalStatus = _resolve_status(
        stats,
        payload=payload,
        result=result,
        readback=readback,
    )
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

    outcome_unknown = _build_outcome_unknown(readback)
    if outcome_unknown is not None and status in {"ok", "empty", "unknown"}:
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
            "reason_code": _resolve_reason_code(
                stats=stats,
                errors=errors,
                records=records,
                result=result,
                status=status,
                outcome_unknown=outcome_unknown,
            ),
            "retryable": bool(result.get("retryable")),
            "provider": _nullable_str(result.get("provider") or payload.get("provider")),
            "provider_job_id": _nullable_str(result.get("provider_job_id") or payload.get("provider_job_id")),
            "trace_id": _nullable_str(result.get("trace_id") or payload.get("trace_id")),
            "warnings": _string_list(execution_request.get("warnings")),
            "provider_handoff": provider_handoff,
            "frontdoor_route_profile": frontdoor_route_profile,
            "frontdoor_router_contract": frontdoor_router_contract,
            "terminal_readback": readback,
            "outcome_unknown": outcome_unknown,
            "raw_result_keys": sorted(result.keys()),
        },
        "raw_snapshot": deepcopy(payload),
    }


def build_terminal_output_dto(result_payload: dict[str, object] | None) -> Annotated[
    TerminalOutputDto,
    "kit:non-authoritative derived_as=view fact_source=source_library.raw_result witness=test:test_derived_service_annotations_match_fact_sources",
]:
    return to_terminal_output_dto(result_payload)


def build_source_library_terminal_output(
    *,
    result_payload: dict[str, object] | None,
    collect_result: TerminalCollectResult,
) -> Annotated[
    TerminalOutputDto,
    "kit:non-authoritative derived_as=view fact_source=source_library.raw_result witness=test:test_derived_service_annotations_match_fact_sources",
]:
    dto = to_terminal_output_dto(result_payload)
    # Preserve an explicit collect-runtime ACK when the legacy payload omitted
    # its status.  The typed result remains the source of truth for terminality.
    collect_status = str(collect_result.status or "").strip().lower()
    payload = result_payload if isinstance(result_payload, dict) else {}
    known_collect_status = _terminal_status(collect_status)
    if known_collect_status in {"accepted", "cancelled", "failed"} and not any(
        key in payload for key in ("status", "terminal_readback")
    ):
        dto["status"] = known_collect_status
    return dto


def _resolve_source_mode(
    *,
    payload: dict[str, object],
    result: dict[str, object],
    execution_request: dict[str, object],
) -> SourceMode:
    source_mode = str(execution_request.get("source_mode") or "").strip().lower()
    known_source_mode = _source_mode(source_mode)
    if known_source_mode is not None:
        return known_source_mode

    channel_key = str(payload.get("channel_key") or "").strip().lower()
    if isinstance(result.get("by_url"), list):
        return "url_execution"
    if channel_key == "handler.cluster" or _optional_object(result.get("routing_result")) is not None:
        return "site_search"
    if channel_key.startswith("crawler."):
        return "provider_harvest"
    return "protocol_search"


def _normalize_query_terms(params: dict[str, object]) -> list[str]:
    raw = params.get("query_terms")
    if raw is None:
        raw = params.get("keywords")
    if raw is None:
        raw = params.get("query")
    if raw is None:
        raw = params.get("q")

    raw_values = _object_list(raw)
    if raw_values:
        return [str(item).strip() for item in raw_values if str(item).strip()]
    if isinstance(raw, str) and raw.strip():
        if "," in raw:
            return [segment.strip() for segment in raw.split(",") if segment.strip()]
        return [raw.strip()]
    return []


def _is_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _optional_object(value: object) -> dict[str, object] | None:
    return dict(value) if _is_object(value) else None


def _object(value: object) -> dict[str, object]:
    return dict(value) if _is_object(value) else {}


def _object_list(value: object) -> list[object]:
    return list(value) if _is_object_list(value) else []


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _source_mode(value: str) -> SourceMode | None:
    if value == "protocol_search":
        return "protocol_search"
    if value == "provider_harvest":
        return "provider_harvest"
    if value == "site_search":
        return "site_search"
    if value == "url_execution":
        return "url_execution"
    return None


def _terminal_status(value: str) -> TerminalStatus | None:
    if value == "ok":
        return "ok"
    if value == "partial":
        return "partial"
    if value == "error":
        return "error"
    if value == "accepted":
        return "accepted"
    if value == "completed":
        return "completed"
    if value == "failed":
        return "failed"
    if value == "cancelled":
        return "cancelled"
    return None


def _string_list(value: object) -> list[str]:
    return [item for item in _object_list(value) if isinstance(item, str)]


def _normalize_time_window(params: dict[str, object]) -> TerminalTimeWindowView:
    return {
        "days_back": _to_optional_int(params.get("days_back")),
        "start_time": _nullable_str(params.get("start_time") or params.get("start_at") or params.get("start_date") or params.get("since")),
        "end_time": _nullable_str(params.get("end_time") or params.get("end_at") or params.get("end_date") or params.get("until")),
    }


def _normalize_paging(params: dict[str, object]) -> TerminalPagingView:
    return {
        "page": _to_optional_int(params.get("page")),
        "start_offset": _to_optional_int(params.get("start_offset") or params.get("offset")),
        "cursor": _nullable_str(params.get("cursor")),
    }


def _normalize_limits(params: dict[str, object]) -> TerminalLimitsView:
    return {
        "limit": _to_optional_int(params.get("limit")),
        "max_items": _to_optional_int(params.get("max_items")),
        "per_keyword_limit": _to_optional_int(params.get("per_keyword_limit")),
        "max_candidates": _to_optional_int(params.get("max_candidates")),
        "ingest_limit": _to_optional_int(params.get("ingest_limit")),
    }


def _collect_errors(result: dict[str, object]) -> list[TerminalErrorView]:
    out: list[TerminalErrorView] = []

    for message in _object_list(result.get("errors")):
        text = str(message).strip()
        if text:
            out.append({"source": "result.errors", "message": text})

    for raw_row in _object_list(result.get("by_url")):
        row = _object(raw_row)
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

    for raw_detail in _object_list(result.get("error_details")):
        detail = _object(raw_detail)
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
    result: dict[str, object],
    params: dict[str, object],
    errors: list[TerminalErrorView],
    records: list[TerminalRecordView],
) -> TerminalStatsView:
    normalized = len(records)
    fetched = 0
    by_url = _object_list(result.get("by_url"))
    candidates = _object_list(result.get("candidates"))

    if source_mode == "url_execution":
        fetched = len(by_url)
    elif source_mode == "site_search":
        fetched = len(candidates) if candidates else len(by_url)
    elif normalized > 0:
        fetched = normalized
    if fetched <= 0:
        maybe_urls = _object_list(params.get("urls"))
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


def _resolve_status(
    stats: TerminalStatsView,
    *,
    payload: dict[str, object],
    result: dict[str, object],
    readback: dict[str, object] | None,
) -> TerminalStatus:
    # A typed provider readback is authoritative for crawler terminality.
    if readback is not None:
        kind = str(readback.get("kind") or "").strip().lower()
        if kind == "terminal":
            terminal_status = _terminal_status(
                str(_object(readback.get("readback")).get("terminal_status") or "").strip().lower()
            )
            if terminal_status in {"completed", "failed", "cancelled"}:
                return terminal_status
        if kind in {"waiting", "unavailable"}:
            if _has_acknowledgement(payload=payload, result=result):
                return "accepted"
            return "error"

    explicit = _explicit_statuses(payload=payload, result=result)
    for candidate in explicit:
        if candidate == "completed" and _has_provider_signal(payload=payload, result=result):
            # A provider's dispatch label is an acknowledgement until C2.3
            # supplies a terminal readback.
            continue
        known_status = _terminal_status(candidate)
        if known_status in {"failed", "cancelled", "completed"}:
            return known_status
    if "accepted" in explicit:
        return "accepted"
    # Provider status ``completed`` is only an acknowledgement without a
    # typed readback.  It must not be promoted to terminal completion.
    if _has_acknowledgement(payload=payload, result=result):
        return "accepted"

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


def _explicit_statuses(*, payload: dict[str, object], result: dict[str, object]) -> list[str]:
    values: list[str] = []
    for value in (payload.get("status"), result.get("status")):
        normalized = str(value or "").strip().lower()
        if normalized in {"completed", "failed", "cancelled", "accepted"}:
            values.append(normalized)
    for value in (payload.get("provider_status"), result.get("provider_status")):
        normalized = str(value or "").strip().lower()
        if normalized in {"failed", "cancelled"}:
            values.append(normalized)
    for row in _iter_by_url_rows(result):
        nested = _object(row.get("result"))
        normalized = str(nested.get("status") or row.get("status") or "").strip().lower()
        if normalized in {"completed", "failed", "cancelled", "accepted"}:
            values.append(normalized)
        normalized_provider = str(nested.get("provider_status") or row.get("provider_status") or "").strip().lower()
        if normalized_provider in {"failed", "cancelled"}:
            values.append(normalized_provider)
    return values


def _has_acknowledgement(*, payload: dict[str, object], result: dict[str, object]) -> bool:
    provider_signal = _has_provider_signal(payload=payload, result=result)
    for value in (payload.get("status"), result.get("status"), payload.get("provider_status"), result.get("provider_status")):
        normalized = str(value or "").strip().lower()
        if normalized == "accepted" or (provider_signal and is_crawler_dispatch_acknowledged(normalized)):
            return True
    for row in _iter_by_url_rows(result):
        nested = _object(row.get("result"))
        for value in (row.get("status"), nested.get("status"), row.get("provider_status"), nested.get("provider_status")):
            normalized = str(value or "").strip().lower()
            if normalized == "accepted" or (provider_signal and is_crawler_dispatch_acknowledged(normalized)):
                return True
    return False


def _has_provider_signal(*, payload: dict[str, object], result: dict[str, object]) -> bool:
    keys = ("provider_status", "provider_job_id", "provider_type", "provider_handoff", "terminal_readback")
    if any(payload.get(key) not in (None, "", {}, []) for key in keys):
        return True
    if any(result.get(key) not in (None, "", {}, []) for key in keys):
        return True
    for row in _iter_by_url_rows(result):
        nested = _object(row.get("result"))
        if any(row.get(key) not in (None, "", {}, []) for key in keys):
            return True
        if any(nested.get(key) not in (None, "", {}, []) for key in keys):
            return True
    return False


def _extract_terminal_readback(*, payload: dict[str, object], result: dict[str, object]) -> dict[str, object] | None:
    candidates: list[object] = [payload.get("terminal_readback"), result.get("terminal_readback"), result.get("readback")]
    for row in _iter_by_url_rows(result):
        candidates.extend([row.get("terminal_readback"), row.get("readback")])
        nested = _object(row.get("result"))
        candidates.extend([nested.get("terminal_readback"), nested.get("readback")])
    for candidate in candidates:
        normalized = _optional_object(candidate)
        if normalized is not None and normalized.get("kind"):
            return normalized
    return None


def _build_outcome_unknown(readback: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(readback, dict) or str(readback.get("kind") or "").strip().lower() not in {"waiting", "unavailable"}:
        return None
    attempt_ref = str(readback.get("attempt_ref") or "attempt:unknown")
    reason = str(readback.get("reason") or ("readback waiting" if readback.get("kind") == "waiting" else "readback unavailable"))
    try:
        from ...successor_runtime.capabilities.source_contracts import OutcomeUnknownProviderEffect

        plain = OutcomeUnknownProviderEffect(attempt_ref=attempt_ref, reason=reason).to_plain()
        return dict(plain)
    except Exception:  # pragma: no cover - optional successor runtime dependency
        return {"kind": "outcome_unknown", "attempt_ref": attempt_ref, "reason": reason}


def _resolve_reason_code(
    *,
    stats: TerminalStatsView,
    errors: list[TerminalErrorView],
    records: list[TerminalRecordView],
    result: dict[str, object],
    status: str | None = None,
    outcome_unknown: dict[str, object] | None = None,
) -> str:
    if outcome_unknown is not None:
        return "outcome_unknown"
    if str(status or "").strip().lower() == "accepted":
        return "accepted_pending_readback"
    if str(status or "").strip().lower() in {"failed", "cancelled"}:
        return f"provider_terminal_{str(status).strip().lower()}"
    if not records:
        query_contract = _object(result.get("query_contract"))
        query_reasons = _string_list(query_contract.get("reason_codes"))
        query_statuses = _string_list(query_contract.get("statuses"))
        if "budget_exhausted" in query_statuses or "query_discovery_budget_exhausted" in query_reasons:
            return "query_discovery_budget_exhausted"
        query_discovery_reason = next(
            (reason for reason in query_reasons if reason not in {"verified_query_results"}),
            "",
        )
        if query_discovery_reason:
            return (
                query_discovery_reason
                if query_discovery_reason.startswith("query_discovery_")
                else f"query_discovery_{query_discovery_reason}"
            )
    if errors:
        return "fetch_errors"
    if not records:
        return "empty"
    if errors:
        return "fetch_errors"
    if int(stats.get("dropped") or 0) > 0:
        return "partial_records"
    return "ok"


def _build_clean_records(*, payload: dict[str, object], result: dict[str, object]) -> list[TerminalRecordView]:
    direct_value = result.get("records")
    direct = _object_list(direct_value)
    if isinstance(direct_value, list):
        normalized = [_normalize_record(_object(row)) for row in direct]
        return [row for row in normalized if row]

    records: list[TerminalRecordView] = []
    seen_keys: set[str] = set()
    by_url = _object_list(result.get("by_url"))
    for index, row in enumerate(by_url):
        normalized = _record_from_by_url_row(row=row, fallback_item_key=str(payload.get("item_key") or ""), index=index)
        if not normalized:
            continue
        dedupe_key = str(normalized.get("url") or normalized.get("record_id") or f"row:{index}")
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        records.append(normalized)

    candidates = _object_list(result.get("candidates"))
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


def _record_from_by_url_row(*, row: object, fallback_item_key: str, index: int) -> TerminalRecordView | None:
    if not _is_object(row):
        return None
    url = _nullable_str(row.get("url"))
    result = _object(row.get("result"))
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
                "provider_handoff": _optional_object(row.get("provider_handoff")),
                "frontdoor_route_profile": _optional_object(row.get("frontdoor_route_profile")),
            },
            "raw_ref": {"source": "result.by_url", "url": url},
        }
    )


def _normalize_record(row: dict[str, object]) -> TerminalRecordView | None:
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
        "raw_ref": _as_dict(row.get("raw_ref")),
    }


def _resolve_provider_handoff(*, payload: dict[str, object], result: dict[str, object]) -> dict[str, object] | None:
    direct = _optional_object(result.get("provider_handoff"))
    if direct is not None:
        return _clean_provider_handoff(direct)

    for row in _iter_by_url_rows(result):
        candidate = _optional_object(row.get("provider_handoff"))
        if candidate is not None:
            return _clean_provider_handoff(candidate)

    provider_type = _nullable_str(result.get("provider_type") or payload.get("provider_type"))
    provider_job_id = _nullable_str(result.get("provider_job_id") or payload.get("provider_job_id"))
    provider_status = _nullable_str(result.get("provider_status") or payload.get("provider_status"))
    runtime_channel = _object(result.get("runtime_channel"))
    layer_boundary = _object(runtime_channel.get("layer_boundary"))
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


def _iter_by_url_rows(result: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    rows.extend(_object(row) for row in _object_list(result.get("by_url")) if _is_object(row))
    routing_result = _object(result.get("routing_result"))
    rows.extend(_object(row) for row in _object_list(routing_result.get("by_url")) if _is_object(row))
    return rows


def _clean_provider_handoff(value: dict[str, object]) -> dict[str, object]:
    out = dict(value or {})
    out.setdefault("contract_version", PROVIDER_HANDOFF_CONTRACT_VERSION)
    return {str(key): raw for key, raw in out.items() if raw not in (None, "", [], {})}


def _resolve_frontdoor_route_profile(
    *,
    params: dict[str, object],
    provider_handoff: dict[str, object] | None,
) -> dict[str, object] | None:
    handoff_profile = (
        _optional_object(provider_handoff.get("frontdoor_route_profile"))
        if provider_handoff is not None
        else None
    )
    if handoff_profile is not None:
        return handoff_profile
    params_profile = _optional_object(params.get("frontdoor_route_profile"))
    if params_profile is not None:
        return params_profile
    route_hint = _nullable_str(params.get("frontdoor_route_hint"))
    fetch_strategy = _nullable_str(params.get("frontdoor_fetch_strategy"))
    render_required = params.get("frontdoor_render_required")
    if not (route_hint or fetch_strategy or render_required is not None):
        return None
    out: dict[str, object] = {
        "route_hint": route_hint,
        "fetch_strategy": fetch_strategy,
        "render_required": bool(render_required),
    }
    return {key: value for key, value in out.items() if value is not None}


def _resolve_frontdoor_router_contract(
    *,
    params: dict[str, object],
    provider_handoff: dict[str, object] | None,
    route_profile: dict[str, object] | None,
) -> dict[str, object] | None:
    if route_profile is not None:
        route_contract = _optional_object(route_profile.get("router_contract"))
        if route_contract is not None:
            return route_contract
    if provider_handoff is not None:
        handoff_contract = _optional_object(provider_handoff.get("router_contract"))
        if handoff_contract is not None:
            return handoff_contract
    params_contract = _optional_object(params.get("frontdoor_router_contract"))
    if params_contract is not None:
        return params_contract
    return None


def _nullable_str(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _as_dict(value: object) -> dict[str, object]:
    return _object(value)


def _to_optional_int(value: object) -> int | None:
    try:
        if value is None or value == "":
            return None
        if not isinstance(value, int | float | str):
            return None
        return int(value)
    except Exception:
        return None


def _resolve_external_manifest_summary(payload: dict[str, object]) -> dict[str, object] | None:
    extra = _as_dict(payload.get("extra"))
    manifest = get_external_project_manifest(
        extra,
        item_key=_nullable_str(payload.get("item_key")),
        display_name=_nullable_str(payload.get("name")),
    )
    summary = build_external_project_summary(manifest)
    return {str(key): value for key, value in summary.items()} if summary is not None else None


__all__ = [
    "CONTRACT_VERSION",
    "build_source_library_terminal_output",
    "build_terminal_output_dto",
    "to_terminal_output_dto",
]
