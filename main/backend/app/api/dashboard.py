"""仪表盘数据API"""
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Any, Mapping, Optional
from uuid import uuid4
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.exc import OperationalError, DatabaseError
from datetime import datetime, date, timedelta
import logging
import re

from ..contracts import ApiEnvelope, ErrorCode, error_response
from ..contracts.responses import ok
from ..models.base import SessionLocal
from ..models.entities import (
    Document,
    Source,
    MarketStat,
    SearchHistory,
    EtlJobRun,
    MarketMetricPoint,
    Product,
    PriceObservation,
)
from ..services.graph.doc_types import resolve_graph_doc_types
from ..services import document_queries
from ..services.document_views import (
    get_social_platform_label,
    get_social_sentiment_orientation,
    get_social_sentiment_terms,
)
from ..services.llm_report_export import build_llm_report_export_artifact
from ..services.llm_report_export_audit import (
    list_llm_report_export_audit_events_for_trace,
    list_recent_llm_report_export_audit_events,
    summarize_llm_report_export_audit_events,
)
from ..services.llm_report_trends import (
    list_quality_trend_records,
    list_quality_trend_records_for_trace_ids,
    record_quality_trend_metric,
    summarize_quality_trends,
)
from ..services.projects import bind_project
from ..services.projects.context import _normalize_project_key
from ..services.request_identity import resolve_request_actor_context
from ..services.writing import create_document
from ..settings.config import settings
from ._error_responses import error_json_response as _error_json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FRONTDOOR_TRI_STATE_STATUSES = ("success", "degraded_success", "failed")


class DashboardReportFromFilterRequest(BaseModel):
    request_type: str = Field(default="report_from_dashboard_filter", max_length=80)
    project_key: str | None = Field(default=None, max_length=64)
    dashboard: dict[str, Any] = Field(default_factory=dict)
    report_options: dict[str, Any] = Field(default_factory=dict)
    quality_gate_mode: str | None = Field(default=None, max_length=24)
    fail_on_quality_gate: bool | None = Field(default=None)


def _dashboard_source_query(
    card: str,
    *,
    table: str,
    metrics: list[str],
    filters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "scope": "dashboard.stats",
        "card": card,
        "table": table,
        "metrics": metrics,
        "filters": dict(filters or {}),
    }


def _dashboard_source_ref(
    ref_id: str,
    *,
    table: str,
    columns: list[str],
    detail: str | None = None,
) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "id": f"dashboard.stats.{ref_id}",
        "kind": "sql_table",
        "table": table,
        "columns": columns,
    }
    if detail:
        ref["detail"] = detail
    return ref


def _with_dashboard_sources(
    payload: dict[str, Any],
    card: str,
    *,
    table: str,
    metrics: list[str],
    columns: list[str],
    filters: Mapping[str, Any] | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        **payload,
        "source_query": _dashboard_source_query(
            card,
            table=table,
            metrics=metrics,
            filters=filters,
        ),
        "source_refs": [
            _dashboard_source_ref(
                card,
                table=table,
                columns=columns,
                detail=detail,
            )
        ],
    }


def _dashboard_llm_report_quality_summary(limit: int = 50) -> dict[str, Any]:
    records, storage = list_quality_trend_records(limit=limit)
    summary = summarize_quality_trends(records)
    export_records = list_recent_llm_report_export_audit_events(limit=min(limit, 50))
    export_audit_summary = summarize_llm_report_export_audit_events(export_records)
    summary["export_events"] = export_audit_summary
    storage = {
        **storage,
        "export_audit": {
            "contract_version": "llm_report.export_audit_storage.v1",
            "table": "llm_report_export_audit_events",
            "record_count": len(export_records),
            "degraded": any(bool(record.get("export_audit_store_degraded")) for record in export_records),
        },
    }
    has_blocked_exports = (
        int(export_audit_summary.get("blocked") or 0) > 0
        or int(export_audit_summary.get("token_invalid") or 0) > 0
        or int(export_audit_summary.get("failed") or 0) > 0
    )
    return _with_dashboard_sources(
        {
            "contract_version": "dashboard.llm_report_quality.v1",
            "trend_contract_version": "llm_report.quality_trends.v1",
            "summary": summary,
            "recent_records": records[: min(limit, 10)],
            "recent_export_events": export_records[: min(limit, 10)],
            "storage": storage,
            "actionability": {
                "has_blocked_exports": summary.get("decisions", {}).get("fail", 0) > 0
                or summary.get("readiness", {}).get("blocked", 0) > 0
                or has_blocked_exports,
                "has_blocked_export_audit_events": has_blocked_exports,
                "has_review_required_exports": summary.get("readiness", {}).get("review_required", 0) > 0,
                "next_action": (
                    "review_blocked_or_failed_report_quality_samples"
                    if summary.get("decisions", {}).get("fail", 0) > 0
                    or summary.get("readiness", {}).get("blocked", 0) > 0
                    or has_blocked_exports
                    else "monitor_report_quality_trend"
                ),
            },
        },
        "llm_report_quality",
        table="llm_report_export_audit_events",
        metrics=[
            "quality_trend_total",
            "by_decision",
            "avg_citation_coverage",
            "avg_evidence_coverage",
            "export_events",
        ],
        columns=[
            "id",
            "trace_id",
            "source_trace_id",
            "project_key",
            "actor_id",
            "export_format",
            "outcome",
            "integrity_mode",
            "artifact_id",
            "error_code",
            "recorded_at",
        ],
        filters={"event_type": "llm_report_export", "source": "dedicated_export_audit_table"},
        detail="llm report export audit events from dedicated structured table; quality trend records remain in recent_records",
    )


def _dashboard_detail_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _dashboard_detail_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _dashboard_detail_job_context(record: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        return {}
    return _dashboard_detail_mapping(record.get("job_context"))


def _dashboard_detail_without_secret(value: Mapping[str, Any]) -> dict[str, Any]:
    blocked_keys = {"artifact_token", "token", "signed_token", "secret", "signature"}
    return {str(key): item for key, item in value.items() if str(key).lower() not in blocked_keys}


def _dashboard_detail_artifact_summary(
    quality_record: Mapping[str, Any] | None,
    export_events: list[dict[str, Any]],
) -> dict[str, Any]:
    context = _dashboard_detail_job_context(quality_record)
    artifact = _dashboard_detail_mapping(context.get("report_artifact"))
    if not artifact and isinstance(quality_record, Mapping):
        artifact = _dashboard_detail_mapping(
            quality_record.get("report_artifact") or quality_record.get("artifact")
        )
    if artifact:
        summary = _dashboard_detail_without_secret(artifact)
        summary.setdefault("source", "quality_job_context")
        return summary
    if export_events:
        event = export_events[0]
        return {
            "contract_version": "dashboard.llm_report_detail.artifact_summary.v1",
            "source": "export_audit_event",
            "artifact_id": event.get("artifact_id"),
            "artifact_sha256": event.get("artifact_sha256"),
            "filename": event.get("filename"),
            "content_type": event.get("content_type"),
            "content_size_bytes": event.get("content_size_bytes"),
            "export_format": event.get("export_format"),
            "outcome": event.get("outcome"),
            "recorded_at": event.get("recorded_at"),
        }
    return {}


def _dashboard_detail_quality_gate(quality_record: Mapping[str, Any] | None) -> dict[str, Any]:
    context = _dashboard_detail_job_context(quality_record)
    quality_gate = _dashboard_detail_mapping(context.get("quality_gate"))
    if not quality_gate and isinstance(quality_record, Mapping):
        quality_gate = _dashboard_detail_mapping(
            quality_record.get("quality_gate") or quality_record.get("report_quality_gate")
        )
    if quality_gate:
        return quality_gate
    if not isinstance(quality_record, Mapping):
        return {}
    return {
        "contract_version": "dashboard.llm_report_detail.quality_gate_summary.v1",
        "decision": quality_record.get("decision"),
        "pass": bool(quality_record.get("pass")),
        "gate_mode": quality_record.get("gate_mode"),
        "gate_mode_raw": quality_record.get("gate_mode_raw"),
        "gate_mode_fallback": bool(quality_record.get("gate_mode_fallback")),
        "citation_coverage": quality_record.get("citation_coverage"),
        "evidence_coverage": quality_record.get("evidence_coverage"),
        "source_count": quality_record.get("source_count"),
        "source_count_requested": quality_record.get("source_count_requested"),
        "source_count_resolved": quality_record.get("source_count_resolved"),
        "hard_failures": _dashboard_detail_list(quality_record.get("hard_failures")),
        "soft_failures": _dashboard_detail_list(quality_record.get("soft_failures")),
        "readiness": quality_record.get("readiness"),
        "next_action": quality_record.get("next_action"),
    }


def _dashboard_detail_source_refs(quality_record: Mapping[str, Any] | None) -> list[Any]:
    context = _dashboard_detail_job_context(quality_record)
    source_refs = _dashboard_detail_list(context.get("source_refs"))
    if source_refs:
        return source_refs
    if isinstance(quality_record, Mapping):
        return _dashboard_detail_list(quality_record.get("source_refs"))
    return []


def _dashboard_detail_source_query(
    *,
    trace_id: str,
    project_key: str | None,
    limit: int,
    quality_record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    context = _dashboard_detail_job_context(quality_record)
    source_query = _dashboard_detail_mapping(context.get("source_query"))
    if not source_query and isinstance(quality_record, Mapping):
        source_query = _dashboard_detail_mapping(quality_record.get("source_query"))
    if source_query:
        return source_query
    return {
        "scope": "dashboard.llm_report_detail",
        "table": "llm_report_quality_trends,llm_report_export_audit_events,etl_job_runs",
        "filters": {
            "trace_id": trace_id,
            "project_key": project_key,
            "limit": limit,
        },
    }


def _dashboard_detail_repair_context(
    *,
    trace_id: str,
    quality_record: Mapping[str, Any] | None,
    export_events: list[dict[str, Any]],
    source_refs: list[Any],
) -> dict[str, Any]:
    context = _dashboard_detail_job_context(quality_record)
    repair_context = _dashboard_detail_mapping(context.get("repair_context"))
    if repair_context:
        repair_context.setdefault("available", True)
        repair_context.setdefault("trace_id", trace_id)
        repair_context.setdefault("source_refs", source_refs)
        return repair_context
    quality_gate = _dashboard_detail_quality_gate(quality_record)
    error_codes = sorted(
        {
            str(event.get("error_code") or "").strip()
            for event in export_events
            if str(event.get("error_code") or "").strip()
        }
    )
    next_action = (
        (quality_record.get("next_action") if isinstance(quality_record, Mapping) else None)
        or quality_gate.get("next_action")
        or ("regenerate_report_before_export" if error_codes else "refresh_llm_report_quality_trends")
    )
    return {
        "contract_version": "dashboard.llm_report_detail.repair_context.v1",
        "trace_id": trace_id,
        "available": bool(quality_gate or error_codes),
        "source_refs": source_refs,
        "hard_failures": _dashboard_detail_list(quality_gate.get("hard_failures")),
        "soft_failures": _dashboard_detail_list(quality_gate.get("soft_failures")),
        "error_codes": error_codes,
        "next_action": next_action,
        "message": f"LLM report detail trace_id={trace_id} requires follow-up: {next_action}",
    }


def _dashboard_detail_prefer_quality_record(records: list[dict[str, Any]], requested_trace_id: str) -> dict[str, Any] | None:
    if not records:
        return None
    non_export_records = [
        record
        for record in records
        if str(record.get("event_type") or "").strip().lower() != "llm_report_export"
        and str(record.get("record_source") or "").strip().lower() != "export"
    ]
    exact_non_export = [
        record for record in non_export_records if str(record.get("trace_id") or "").strip() == requested_trace_id
    ]
    if exact_non_export:
        return exact_non_export[0]
    if non_export_records:
        return non_export_records[0]
    return records[0]


def _dashboard_detail_storage(
    *,
    quality_storage: Mapping[str, Any],
    export_storage: Mapping[str, Any],
) -> dict[str, Any]:
    degraded = bool(quality_storage.get("degraded") or export_storage.get("degraded"))
    return {
        "contract_version": "dashboard.llm_report_detail.storage.v1",
        "degraded": degraded,
        "quality": dict(quality_storage),
        "export_audit": dict(export_storage),
    }


def _dashboard_detail_actionability(
    *,
    found: bool,
    storage: Mapping[str, Any],
    quality_record: Mapping[str, Any] | None,
    export_events: list[dict[str, Any]],
) -> dict[str, Any]:
    decision = str((quality_record or {}).get("decision") or "").strip().lower()
    has_failed_export = any(
        str(event.get("outcome") or event.get("export_outcome") or "").strip().lower()
        in {"blocked", "failed", "token_invalid"}
        for event in export_events
    )
    requires_repair = decision == "fail" or has_failed_export
    if not found:
        next_action = "refresh_llm_report_quality_trends"
    elif requires_repair:
        next_action = (
            (quality_record or {}).get("next_action")
            or "repair_report_quality_or_regenerate_export_artifact"
        )
    elif bool(storage.get("degraded")):
        next_action = "retry_detail_query_or_inspect_process_history_by_trace_id"
    else:
        next_action = "review_llm_report_detail"
    return {
        "found": found,
        "has_quality_record": bool(quality_record),
        "has_export_events": bool(export_events),
        "has_failed_export": has_failed_export,
        "requires_repair": requires_repair,
        "next_action": next_action,
    }


def _dashboard_detail_record_matches_trace(record: Mapping[str, Any], trace_id: str) -> bool:
    return (
        str(record.get("trace_id") or "").strip() == trace_id
        or str(record.get("source_trace_id") or "").strip() == trace_id
    )


def _dashboard_detail_record_matches_project(record: Mapping[str, Any], project_key: str | None) -> bool:
    return not project_key or str(record.get("project_key") or "") == project_key


def _dashboard_detail_filter_recent_records(
    records: list[dict[str, Any]],
    *,
    trace_ids: set[str],
    project_key: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for record in records:
        if not any(_dashboard_detail_record_matches_trace(record, trace_id) for trace_id in trace_ids):
            continue
        if not _dashboard_detail_record_matches_project(record, project_key):
            continue
        filtered.append(record)
    return filtered[:limit]


def _dashboard_detail_export_events(
    *,
    trace_id: str,
    project_key: str | None,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events, storage = list_llm_report_export_audit_events_for_trace(
        trace_id=trace_id,
        project_key=project_key,
        limit=limit,
    )
    if events or not storage.get("degraded"):
        return events, storage
    fallback = _dashboard_detail_filter_recent_records(
        list_recent_llm_report_export_audit_events(limit=max(limit, 50), project_key=project_key),
        trace_ids={trace_id},
        project_key=project_key,
        limit=limit,
    )
    if fallback:
        return fallback, {
            **storage,
            "fallback_source": "recent_export_audit_events",
            "fallback_count": len(fallback),
        }
    return events, storage


def _dashboard_detail_export_events_summary(export_events: list[dict[str, Any]]) -> dict[str, Any]:
    by_outcome: dict[str, int] = {}
    by_format: dict[str, int] = {}
    summary = {
        "contract_version": "dashboard.llm_report_detail.export_events_summary.v1",
        "total": 0,
        "success": 0,
        "blocked": 0,
        "token_invalid": 0,
        "failed": 0,
        "ui_read_only_context_included_count": 0,
    }
    for event in export_events:
        summary["total"] += 1
        outcome = str(event.get("outcome") or event.get("export_outcome") or "unknown").strip().lower() or "unknown"
        export_format = str(event.get("export_format") or "unknown").strip().lower() or "unknown"
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        by_format[export_format] = by_format.get(export_format, 0) + 1
        if outcome in {"success", "blocked", "token_invalid", "failed"}:
            summary[outcome] += 1
        else:
            summary["failed"] += 1
        if event.get("ui_read_only_context_included") is True:
            summary["ui_read_only_context_included_count"] += 1
    return {
        "contract_version": summary["contract_version"],
        "total": summary["total"],
        "success": summary["success"],
        "blocked": summary["blocked"],
        "token_invalid": summary["token_invalid"],
        "failed": summary["failed"],
        "ui_read_only_context_included_count": summary["ui_read_only_context_included_count"],
        "by_outcome": by_outcome,
        "by_format": by_format,
        "read_only_context_semantics": (
            "ui_read_only_context_included_count is detail observability only; it is not report proof, "
            "not quality gate input, not scheduled_run_evidence proof, and does not change export audit outcome."
        ),
    }


def _dashboard_detail_quality_records(
    *,
    trace_ids: set[str],
    project_key: str | None,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records, storage = list_quality_trend_records_for_trace_ids(
        trace_ids=sorted(trace_ids),
        project_key=project_key,
        limit=limit,
    )
    if records or not storage.get("degraded"):
        return records, storage
    recent_records, recent_storage = list_quality_trend_records(
        limit=max(limit, 50),
        project_key=project_key,
    )
    fallback = _dashboard_detail_filter_recent_records(
        recent_records,
        trace_ids=trace_ids,
        project_key=project_key,
        limit=limit,
    )
    if fallback:
        return fallback, {
            **storage,
            "fallback_source": "recent_quality_trend_records",
            "fallback_count": len(fallback),
            "recent_storage": recent_storage,
        }
    return records, storage


@router.get("/llm-report-detail", response_model=ApiEnvelope[dict[str, Any]])
def get_dashboard_llm_report_detail(
    trace_id: str = Query("", max_length=128, description="LLM report trace_id or export trace_id"),
    project_key: Optional[str] = Query(None, max_length=64, description="Optional project key filter"),
    limit: int = Query(10, ge=1, le=50, description="Maximum matching records/events to inspect"),
):
    """Return a trace-oriented LLM report detail contract without failing closed on missing records."""
    normalized_trace_id = str(trace_id or "").strip()
    if not normalized_trace_id:
        return _error_json(
            422,
            ErrorCode.INVALID_INPUT,
            "trace_id is required",
            details={
                "reason_code": "DASHBOARD_LLM_REPORT_TRACE_ID_REQUIRED",
                "field": "trace_id",
                "value": trace_id,
            },
        )
    normalized_project_key = _normalize_project_key(project_key) if str(project_key or "").strip() else None
    try:
        export_events, export_storage = _dashboard_detail_export_events(
            trace_id=normalized_trace_id,
            project_key=normalized_project_key,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        export_events = []
        export_storage = {
            "contract_version": "llm_report.export_audit_detail_storage.v1",
            "table": "llm_report_export_audit_events",
            "memory_count": 0,
            "database_count": 0,
            "merged_count": 0,
            "degraded": True,
            "degraded_reason": "llm_report_export_audit_service_unavailable",
            "exception_type": exc.__class__.__name__,
        }

    trace_ids = {normalized_trace_id}
    trace_ids.update(str(event.get("trace_id") or "").strip() for event in export_events)
    trace_ids.update(str(event.get("source_trace_id") or "").strip() for event in export_events)
    trace_ids = {item for item in trace_ids if item}
    try:
        quality_records, quality_storage = _dashboard_detail_quality_records(
            trace_ids=trace_ids,
            project_key=normalized_project_key,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        quality_records = []
        quality_storage = {
            "contract_version": "llm_report.quality_detail_storage.v1",
            "table": "llm_report_quality_trends",
            "memory_count": 0,
            "database_count": 0,
            "job_log_count": 0,
            "merged_count": 0,
            "degraded": True,
            "degraded_reason": "llm_report_quality_detail_service_unavailable",
            "exception_type": exc.__class__.__name__,
        }

    quality_record = _dashboard_detail_prefer_quality_record(quality_records, normalized_trace_id)
    found = bool(quality_record or export_events)
    storage = _dashboard_detail_storage(quality_storage=quality_storage, export_storage=export_storage)
    resolved_project_key = (
        normalized_project_key
        or (quality_record.get("project_key") if isinstance(quality_record, Mapping) else None)
        or (export_events[0].get("project_key") if export_events else None)
    )
    source_refs = _dashboard_detail_source_refs(quality_record)
    report_artifact = _dashboard_detail_artifact_summary(quality_record, export_events)
    quality_gate = _dashboard_detail_quality_gate(quality_record)
    export_events_summary = _dashboard_detail_export_events_summary(export_events)
    repair_context = _dashboard_detail_repair_context(
        trace_id=normalized_trace_id,
        quality_record=quality_record,
        export_events=export_events,
        source_refs=source_refs,
    )
    actionability = _dashboard_detail_actionability(
        found=found,
        storage=storage,
        quality_record=quality_record,
        export_events=export_events,
    )
    data = {
        "contract_version": "dashboard.llm_report_detail.v1",
        "found": found,
        "trace_id": normalized_trace_id,
        "project_key": resolved_project_key,
        "quality_record": quality_record,
        "quality_records": quality_records,
        "export_events": export_events,
        "export_audit": {
            "contract_version": "dashboard.llm_report_detail.export_audit.v1",
            "events": export_events,
            "summary": export_events_summary,
            "storage": dict(export_storage),
        },
        "export_events_summary": export_events_summary,
        "source_refs": source_refs,
        "source_query": _dashboard_detail_source_query(
            trace_id=normalized_trace_id,
            project_key=resolved_project_key,
            limit=limit,
            quality_record=quality_record,
        ),
        "report_artifact": report_artifact,
        "artifact": report_artifact,
        "quality_gate": quality_gate,
        "report_quality_gate": quality_gate,
        "repair_context": repair_context,
        "storage": storage,
        "actionability": actionability,
    }
    return ok(data)


def _dashboard_project_key_from_request(
    request: Request,
    explicit_project_key: str | None = None,
) -> str:
    candidate = str(explicit_project_key or "").strip()
    if not candidate:
        source = str(getattr(getattr(request, "state", None), "project_key_source", "") or "").strip().lower()
        resolved = str(getattr(getattr(request, "state", None), "project_key_resolved", "") or "").strip()
        if source in {"header", "query"} and resolved:
            candidate = resolved
    if not candidate:
        candidate = (request.headers.get("X-Project-Key") or request.query_params.get("project_key") or "").strip()
    return _normalize_project_key(candidate or settings.active_project_key or "default")


def _dashboard_actor_id_from_request(request: Request | None) -> str:
    return resolve_request_actor_context(request).actor_id


def _dashboard_report_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _normalize_dashboard_report_source_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, str):
            ref = {"id": item.strip()}
        elif isinstance(item, Mapping):
            ref = dict(item)
            ref["id"] = str(ref.get("id") or ref.get("source_ref") or ref.get("detail") or "").strip()
        else:
            continue
        ref_id = str(ref.get("id") or "").strip()
        if not ref_id or ref_id in seen:
            continue
        seen.add(ref_id)
        refs.append(ref)
    return refs


def _dashboard_report_json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _dashboard_report_title(dashboard: Mapping[str, Any]) -> str:
    label = str(dashboard.get("selected_label") or "").strip()
    metric = str(dashboard.get("selected_metric") or dashboard.get("selected_source_ref") or "").strip()
    base = label or metric or "Dashboard filter"
    return f"Dashboard report draft - {base}"[:500]


def _dashboard_report_checklist(
    *,
    filters: Mapping[str, Any],
    source_refs: list[dict[str, Any]],
    source_query: Mapping[str, Any],
    sample_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": "filters_preserved",
            "status": "pass",
            "detail": f"{len(filters)} dashboard filter key(s) preserved",
        },
        {
            "id": "source_refs_preserved",
            "status": "pass" if source_refs else "fail",
            "detail": f"{len(source_refs)} dashboard source_ref(s) preserved",
        },
        {
            "id": "source_query_preserved",
            "status": "pass" if source_query else "warn",
            "detail": "dashboard source_query preserved" if source_query else "dashboard source_query is empty",
        },
        {
            "id": "sample_rows_attached",
            "status": "pass" if sample_rows else "warn",
            "detail": f"{len(sample_rows)} dashboard sample row(s) attached",
        },
    ]


def _dashboard_report_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dashboard_report_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dashboard_report_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on", "strict"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "compatible"}:
            return False
    return default


def _dashboard_report_quality_gate_mode(
    payload: DashboardReportFromFilterRequest,
    report_options: Mapping[str, Any],
) -> str:
    raw_mode = (
        payload.quality_gate_mode
        or report_options.get("quality_gate_mode")
        or report_options.get("report_quality_gate_mode")
        or report_options.get("quality_mode")
    )
    normalized_mode = str(raw_mode or "").strip().lower()
    strict_requested = normalized_mode == "strict" or _dashboard_report_bool(payload.fail_on_quality_gate)
    strict_requested = strict_requested or _dashboard_report_bool(report_options.get("fail_on_quality_gate"))
    strict_requested = strict_requested or _dashboard_report_bool(report_options.get("strict_quality_gate"))
    return "strict" if strict_requested else "compatible"


def _dashboard_report_quality_next_action(report_quality_gate: Mapping[str, Any]) -> str:
    status = str(report_quality_gate.get("status") or "").strip().lower()
    if status == "blocked":
        return "fix_blocking_quality_gate_reasons_before_generating_report"
    if status == "warn":
        return "review_quality_gate_warnings_before_export"
    return "continue_to_draft_generation"


def _dashboard_report_gate_for_export(report_quality_gate: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report_quality_gate.get("status") or "").strip().lower()
    decision = "pass" if status == "pass" else ("warn" if status == "warn" else "fail")
    blocking_reasons = report_quality_gate.get("blocking_reasons")
    warnings = report_quality_gate.get("warnings")
    missing_items = report_quality_gate.get("missing_items")
    return {
        "decision": decision,
        "gate_version": "dashboard.report_quality_gate.v1",
        "hard_failures": blocking_reasons if isinstance(blocking_reasons, list) else [],
        "soft_failures": warnings if isinstance(warnings, list) else [],
        "missing_items": missing_items if isinstance(missing_items, list) else [],
    }


def _dashboard_report_gate_mode_for_export(quality_gate_mode: str) -> str:
    return "strict" if str(quality_gate_mode or "").strip().lower() == "strict" else "warn"


def _dashboard_report_trace_id() -> str:
    return f"dashboard-report:{uuid4().hex}"


def _dashboard_report_quality_trend_record(
    *,
    trace_id: str,
    request_id: str | None,
    project_key: str,
    title: str,
    source_refs: list[dict[str, Any]],
    source_query: Mapping[str, Any],
    report_quality_gate: Mapping[str, Any],
    quality_gate_mode: str,
    next_action: str,
    export_artifact: Mapping[str, Any],
    document: Mapping[str, Any],
) -> dict[str, Any]:
    gate = _dashboard_report_gate_for_export(report_quality_gate)
    decision = str(gate.get("decision") or "fail").strip().lower() or "fail"
    evidence = report_quality_gate.get("evidence") if isinstance(report_quality_gate.get("evidence"), Mapping) else {}
    sanitized_artifact = _dashboard_detail_without_secret(export_artifact)
    sanitized_artifact["document_id"] = document.get("id")
    return {
        "contract_version": "llm_report.quality_trend_metric.v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "project_key": project_key,
        "decision": decision,
        "pass": decision == "pass",
        "gate_mode": _dashboard_report_gate_mode_for_export(quality_gate_mode),
        "gate_mode_raw": quality_gate_mode,
        "gate_mode_fallback": False,
        "citation_coverage": float(report_quality_gate.get("source_ref_coverage") or 0.0),
        "evidence_coverage": float(report_quality_gate.get("source_ref_coverage") or 0.0),
        "source_count": len(source_refs),
        "source_count_requested": max(len(source_refs), len(evidence.get("expected_source_refs") or [])),
        "source_count_resolved": len(source_refs),
        "missing_items_count": len(gate.get("missing_items") or []),
        "hard_failure_count": len(gate.get("hard_failures") or []),
        "soft_failure_count": len(gate.get("soft_failures") or []),
        "hard_failures": gate.get("hard_failures") or [],
        "soft_failures": gate.get("soft_failures") or [],
        "readiness": "blocked" if decision == "fail" else ("review_required" if decision == "warn" else "ready"),
        "next_action": next_action,
        "source_refs": source_refs,
        "source_query": dict(source_query),
        "report_artifact": sanitized_artifact,
        "artifact": sanitized_artifact,
        "quality_gate": dict(report_quality_gate),
        "report_quality_gate": dict(report_quality_gate),
        "draft": {
            "id": document.get("id"),
            "title": document.get("title") or title,
            "status": document.get("status") or "draft",
            "version": document.get("version") or document.get("head_version"),
        },
    }


def _dashboard_report_source_ref_ids(value: Any) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    ids: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if isinstance(item, Mapping):
            ref_id = str(item.get("id") or item.get("source_ref") or "").strip()
        else:
            ref_id = str(item or "").strip()
        if ref_id and ref_id not in seen:
            seen.add(ref_id)
            ids.append(ref_id)
    return ids


def _dashboard_report_expected_source_ref_ids(
    dashboard: Mapping[str, Any],
    source_refs: list[dict[str, Any]],
) -> list[str]:
    expected: list[str] = []
    for key in (
        "expected_source_refs",
        "required_source_refs",
        "selected_source_refs",
        "selected_source_ref",
        "source_refs_required",
    ):
        for ref_id in _dashboard_report_source_ref_ids(dashboard.get(key)):
            if ref_id not in expected:
                expected.append(ref_id)
    if expected:
        return expected
    return [ref["id"] for ref in source_refs if ref.get("id")]


def _dashboard_report_ref_date(ref: Mapping[str, Any]) -> date | None:
    for key in (
        "published_at",
        "publish_date",
        "retrieved_at",
        "collected_at",
        "updated_at",
        "last_seen_at",
        "source_updated_at",
    ):
        raw_value = ref.get(key)
        if isinstance(raw_value, datetime):
            return raw_value.date()
        if isinstance(raw_value, date):
            return raw_value
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if not value:
            continue
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            if _DATE_RE.match(value[:10]):
                try:
                    return date.fromisoformat(value[:10])
                except ValueError:
                    continue
    return None


def _dashboard_report_trust_score(ref: Mapping[str, Any]) -> float | None:
    for key in ("trust_score", "credibility", "confidence", "reliability_score", "source_quality_score"):
        raw_value = ref.get(key)
        if raw_value is None:
            continue
        try:
            score = float(raw_value)
        except (TypeError, ValueError):
            continue
        if score > 1.0:
            score = score / 100.0
        return max(0.0, min(1.0, score))
    level = str(ref.get("trust_level") or ref.get("credibility_level") or ref.get("source_tier") or "").strip().lower()
    if level in {"low", "untrusted", "unsafe", "poor", "tier3", "tier_3"}:
        return 0.0
    if level in {"high", "trusted", "authoritative", "good", "tier1", "tier_1"}:
        return 1.0
    return None


def _build_dashboard_report_quality_gate(
    *,
    dashboard: Mapping[str, Any],
    source_refs: list[dict[str, Any]],
    report_options: Mapping[str, Any],
) -> dict[str, Any]:
    total_refs = len(source_refs)
    provided_ids = {str(ref.get("id") or "").strip() for ref in source_refs if str(ref.get("id") or "").strip()}
    expected_ids = _dashboard_report_expected_source_ref_ids(dashboard, source_refs)
    covered_ids = [ref_id for ref_id in expected_ids if ref_id in provided_ids]
    coverage = (len(covered_ids) / len(expected_ids)) if expected_ids else (1.0 if source_refs else 0.0)

    as_of = _dashboard_report_ref_date({"published_at": report_options.get("as_of_date")}) or date.today()
    max_source_age_days = _dashboard_report_int(report_options.get("max_source_age_days"), 365)
    min_source_refs = max(1, _dashboard_report_int(report_options.get("min_source_refs"), 1))
    min_coverage = max(0.0, min(1.0, _dashboard_report_float(report_options.get("min_source_ref_coverage"), 1.0)))
    max_stale_ratio = max(0.0, min(1.0, _dashboard_report_float(report_options.get("max_stale_source_ratio"), 0.0)))
    max_low_trust_ratio = max(0.0, min(1.0, _dashboard_report_float(report_options.get("max_low_trust_source_ratio"), 0.0)))
    min_trust_score = max(0.0, min(1.0, _dashboard_report_float(report_options.get("min_source_trust_score"), 0.6)))

    stale_ids: list[str] = []
    low_trust_ids: list[str] = []
    for ref in source_refs:
        ref_id = str(ref.get("id") or "").strip()
        ref_date = _dashboard_report_ref_date(ref)
        is_stale = bool(ref.get("is_stale") or ref.get("stale"))
        if ref_date is not None and max_source_age_days >= 0:
            is_stale = is_stale or (as_of - ref_date).days > max_source_age_days
        if is_stale:
            stale_ids.append(ref_id or f"source_ref[{len(stale_ids)}]")

        trust_score = _dashboard_report_trust_score(ref)
        if trust_score is not None and trust_score < min_trust_score:
            low_trust_ids.append(ref_id or f"source_ref[{len(low_trust_ids)}]")

    stale_ratio = (len(stale_ids) / total_refs) if total_refs else 0.0
    low_trust_ratio = (len(low_trust_ids) / total_refs) if total_refs else 0.0

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    blocking_reasons: list[str] = []

    def add_check(
        check_id: str,
        *,
        metric: str,
        value: float | int,
        threshold: float | int,
        status: str,
        detail: str,
    ) -> None:
        checks.append(
            {
                "id": check_id,
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "status": status,
                "detail": detail,
            }
        )
        if status == "fail":
            blocking_reasons.append(check_id)
        elif status == "warn":
            warnings.append(check_id)

    add_check(
        "source_ref_coverage",
        metric="source_ref_coverage",
        value=round(coverage, 4),
        threshold=min_coverage,
        status="pass" if source_refs and coverage >= min_coverage else "fail",
        detail=f"{len(covered_ids)}/{len(expected_ids)} expected source_ref(s) covered",
    )
    add_check(
        "source_ref_count",
        metric="source_ref_count",
        value=total_refs,
        threshold=min_source_refs,
        status="pass" if total_refs >= min_source_refs else "warn",
        detail=f"{total_refs} source_ref(s) provided; minimum recommended is {min_source_refs}",
    )
    add_check(
        "stale_source_ratio",
        metric="stale_source_ratio",
        value=round(stale_ratio, 4),
        threshold=max_stale_ratio,
        status="pass" if stale_ratio <= max_stale_ratio else "warn",
        detail=f"{len(stale_ids)}/{total_refs} source_ref(s) are stale",
    )
    add_check(
        "low_trust_source_ratio",
        metric="low_trust_source_ratio",
        value=round(low_trust_ratio, 4),
        threshold=max_low_trust_ratio,
        status="pass" if low_trust_ratio <= max_low_trust_ratio else "warn",
        detail=f"{len(low_trust_ids)}/{total_refs} source_ref(s) are below trust threshold",
    )

    status = "blocked" if blocking_reasons else ("warn" if warnings else "pass")
    return {
        "status": status,
        "pass": status == "pass",
        "fail": status == "blocked",
        "source_ref_coverage": round(coverage, 4),
        "stale_source_ratio": round(stale_ratio, 4),
        "low_trust_source_ratio": round(low_trust_ratio, 4),
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
        "checks": checks,
        "thresholds": {
            "min_source_ref_coverage": min_coverage,
            "min_source_refs": min_source_refs,
            "max_source_age_days": max_source_age_days,
            "max_stale_source_ratio": max_stale_ratio,
            "min_source_trust_score": min_trust_score,
            "max_low_trust_source_ratio": max_low_trust_ratio,
        },
        "evidence": {
            "expected_source_refs": expected_ids,
            "covered_source_refs": covered_ids,
            "stale_source_refs": stale_ids,
            "low_trust_source_refs": low_trust_ids,
        },
    }


def _render_dashboard_report_body(
    *,
    title: str,
    project_key: str,
    dashboard: Mapping[str, Any],
    filters: Mapping[str, Any],
    source_refs: list[dict[str, Any]],
    source_query: Mapping[str, Any],
    sample_rows: list[dict[str, Any]],
    checklist: list[dict[str, Any]],
    report_quality_gate: Mapping[str, Any],
) -> str:
    source_ref_lines = [
        f"- `{ref.get('id')}`"
        + (f" table={ref.get('table')}" if ref.get("table") else "")
        + (f" detail={ref.get('detail')}" if ref.get("detail") else "")
        for ref in source_refs
    ]
    checklist_lines = [
        f"- [{'x' if item.get('status') == 'pass' else ' '}] {item.get('id')}: {item.get('detail')}"
        for item in checklist
    ]
    selection = {
        "project_key": project_key,
        "variant": dashboard.get("variant"),
        "selected_label": dashboard.get("selected_label"),
        "selected_metric": dashboard.get("selected_metric"),
        "selected_source_ref": dashboard.get("selected_source_ref"),
        "pending_action_id": dashboard.get("pending_action_id"),
    }
    return "\n".join(
        [
            f"# {title}",
            "",
            "This draft was generated from a Dashboard report-from-filter request.",
            "",
            "## Dashboard Selection",
            "```json",
            _dashboard_report_json(selection),
            "```",
            "",
            "## Filters",
            "```json",
            _dashboard_report_json(filters),
            "```",
            "",
            "## Source Query",
            "```json",
            _dashboard_report_json(source_query),
            "```",
            "",
            "## Source Refs",
            *(source_ref_lines or ["- No source refs were provided."]),
            "",
            "## Sample Rows",
            "```json",
            _dashboard_report_json(sample_rows[:10]),
            "```",
            "",
            "## Quality Checklist",
            *checklist_lines,
            "",
            "## Report Quality Gate",
            "```json",
            _dashboard_report_json(report_quality_gate),
            "```",
            "",
            "## Draft Notes",
            "- Expand this outline into narrative analysis after validating the cited dashboard rows.",
            "- Keep the filters, source_query, and source_refs metadata attached when editing.",
        ]
    ).strip()


def _dashboard_pending_action(
    action_id: str,
    action_type: str,
    *,
    severity: str,
    title: str,
    detail: str,
    source_metric: str,
    source_ref: str,
    filters: Mapping[str, Any] | None = None,
    suggested_action: str | None = None,
) -> dict[str, Any]:
    return {
        "id": action_id,
        "type": action_type,
        "status": "open",
        "severity": severity,
        "title": title,
        "detail": detail,
        "source_metric": source_metric,
        "filters": dict(filters or {}),
        "suggested_action": suggested_action,
        "source_refs": [source_ref],
    }


def _build_dashboard_pending_actions(
    *,
    doc_total: int,
    doc_with_extracted: int,
    source_total: int,
    source_enabled: int,
    task_failed: int,
    frontdoor_tri_state: Mapping[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    tri_counts = _as_mapping(frontdoor_tri_state.get("counts"))
    degraded_count = int(tri_counts.get("degraded_success") or 0)
    frontdoor_failed_count = int(tri_counts.get("failed") or 0)
    if degraded_count or frontdoor_failed_count:
        actions.append(
            _dashboard_pending_action(
                "provider-degradation-frontdoor",
                "provider_degradation",
                severity="high" if frontdoor_failed_count else "medium",
                title="Provider degradation is visible in ingest frontdoor telemetry",
                detail=(
                    f"{degraded_count} degraded and {frontdoor_failed_count} failed "
                    "frontdoor outcomes require provider or fallback review."
                ),
                source_metric="tasks.frontdoor_tri_state",
                source_ref="dashboard.stats.tasks.frontdoor_tri_state",
                filters={"dashboard_status": ["degraded_success", "failed"]},
                suggested_action="Review failing providers and confirm fallback route coverage.",
            )
        )

    if source_total == 0:
        actions.append(
            _dashboard_pending_action(
                "config-missing-source-catalog",
                "config_missing",
                severity="high",
                title="No sources are configured",
                detail="Dashboard source coverage is empty; configure at least one source before relying on reports.",
                source_metric="sources.total",
                source_ref="dashboard.stats.sources",
                filters={"sources.total": 0},
                suggested_action="Create or import source catalog entries for this project.",
            )
        )
    elif source_enabled == 0:
        actions.append(
            _dashboard_pending_action(
                "config-missing-enabled-sources",
                "config_missing",
                severity="high",
                title="All configured sources are disabled",
                detail="Sources exist but none are enabled, so collection and report grounding cannot progress.",
                source_metric="sources.enabled",
                source_ref="dashboard.stats.sources",
                filters={"sources.enabled": 0},
                suggested_action="Enable at least one validated source or add a new active source.",
            )
        )

    disabled_sources = max(0, int(source_total or 0) - int(source_enabled or 0))
    if disabled_sources:
        actions.append(
            _dashboard_pending_action(
                "source-invalid-disabled",
                "source_invalid",
                severity="medium",
                title="Some sources are disabled or invalid",
                detail=f"{disabled_sources} configured source(s) are not enabled and should be reviewed.",
                source_metric="sources.enabled",
                source_ref="dashboard.stats.sources",
                filters={"enabled": False},
                suggested_action="Open the source library and re-enable, replace, or retire invalid entries.",
            )
        )

    docs_without_extracted_data = max(0, int(doc_total or 0) - int(doc_with_extracted or 0))
    if docs_without_extracted_data:
        actions.append(
            _dashboard_pending_action(
                "report-reference-gap-extracted-data",
                "report_reference_gap",
                severity="medium",
                title="Report grounding has insufficient extracted references",
                detail=(
                    f"{docs_without_extracted_data} document(s) do not expose extracted data, "
                    "which limits report citation and drilldown quality."
                ),
                source_metric="documents.extraction_rate",
                source_ref="dashboard.stats.documents",
                filters={"extracted_data": "missing"},
                suggested_action="Run extraction or enrich references before generating dashboard-filtered reports.",
            )
        )

    if task_failed:
        actions.append(
            _dashboard_pending_action(
                "task-failures-review",
                "task_failure",
                severity="medium",
                title="Failed dashboard tasks need review",
                detail=f"{task_failed} ETL task(s) are failed and may hide stale or missing dashboard rows.",
                source_metric="tasks.failed",
                source_ref="dashboard.stats.tasks",
                filters={"status": "failed"},
                suggested_action="Inspect failed task logs and rerun only the affected jobs.",
            )
        )

    return actions


def _decimal_to_float(value):
    """将Decimal转换为float"""
    if value is None:
        return None
    return float(value)


def _empty_frontdoor_tri_state_counts() -> dict[str, int]:
    return {status: 0 for status in _FRONTDOOR_TRI_STATE_STATUSES}


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _frontdoor_summary_from_params(params: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = params.get("frontdoor_status_summary")
    if isinstance(direct, Mapping):
        return direct
    for parent_key in ("meta", "debug"):
        parent = params.get(parent_key)
        if isinstance(parent, Mapping) and isinstance(parent.get("frontdoor_status_summary"), Mapping):
            return parent["frontdoor_status_summary"]
    return {}


def _build_frontdoor_tri_state_summary(rows: list[Any]) -> dict[str, Any]:
    counts = _empty_frontdoor_tri_state_counts()
    observed = 0
    for row in rows:
        params = _as_mapping(getattr(row, "params", None))
        summary = _frontdoor_summary_from_params(params)
        raw_counts = summary.get("dashboard_status_counts") if isinstance(summary, Mapping) else None
        if not isinstance(raw_counts, Mapping):
            continue
        for status in _FRONTDOOR_TRI_STATE_STATUSES:
            value = int(raw_counts.get(status) or 0)
            counts[status] += max(0, value)
            observed += max(0, value)
    return {
        "states": list(_FRONTDOOR_TRI_STATE_STATUSES),
        "counts": counts,
        "total": observed,
        "source": "etl_job_runs.params.frontdoor_status_summary.dashboard_status_counts",
        "source_query": _dashboard_source_query(
            "tasks.frontdoor_tri_state",
            table="etl_job_runs",
            metrics=["frontdoor_tri_state"],
            filters={"params.frontdoor_status_summary": "present"},
        ),
        "source_refs": [
            _dashboard_source_ref(
                "tasks.frontdoor_tri_state",
                table="etl_job_runs",
                columns=["params", "status"],
                detail="params.frontdoor_status_summary.dashboard_status_counts",
            )
        ],
    }


def _raise_invalid_input_422(message: str, *, field: str, value: str) -> None:
    raise HTTPException(
        status_code=422,
        detail=error_response(
            ErrorCode.INVALID_INPUT,
            message,
            details={
                "field": field,
                "value": value,
            },
        ),
    )


def _raise_upstream_error(message: str, *, details: dict | None = None) -> None:
    raise HTTPException(
        status_code=503,
        detail=error_response(
            ErrorCode.UPSTREAM_ERROR,
            message,
            details=details,
        ),
    )


def _raise_internal_error(message: str, *, details: dict | None = None) -> None:
    raise HTTPException(
        status_code=500,
        detail=error_response(
            ErrorCode.INTERNAL_ERROR,
            message,
            details=details,
        ),
    )


def _parse_ymd_date_param(value: Optional[str], *, field: str) -> Optional[date]:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if not _DATE_RE.match(raw):
        _raise_invalid_input_422(f"{field} must be YYYY-MM-DD", field=field, value=raw)
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        _raise_invalid_input_422(
            f"{field} must be a valid YYYY-MM-DD date",
            field=field,
            value=raw,
        )


def _parse_iso8601_datetime_param(value: Optional[str], *, field: str) -> Optional[datetime]:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        _raise_invalid_input_422(
            f"{field} must be ISO8601 datetime",
            field=field,
            value=raw,
        )
    if "T" not in raw and " " not in raw:
        _raise_invalid_input_422(f"{field} must be ISO8601 datetime", field=field, value=raw)
    return parsed


@router.get("/global/stats", response_model=ApiEnvelope[dict[str, Any]])
def get_global_stats():
    """总库汇总统计（aggregator schema）"""
    from sqlalchemy import text
    from ..models.base import engine

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM aggregator.documents_agg) AS documents_total,
                  (SELECT COUNT(*) FROM aggregator.market_metric_points_agg) AS metrics_total,
                  (SELECT COUNT(*) FROM aggregator.price_observations_agg) AS prices_total
                """
            )
        ).first()
        if not rows:
            return ok({"documents_total": 0, "metrics_total": 0, "prices_total": 0})
        return ok({
            "documents_total": int(rows.documents_total or 0),
            "metrics_total": int(rows.metrics_total or 0),
            "prices_total": int(rows.prices_total or 0),
        })


@router.get("/stats", response_model=ApiEnvelope[dict[str, Any]])
def get_dashboard_stats():
    """获取仪表盘概览统计数据"""
    try:
        with SessionLocal() as session:
            # 文档统计
            doc_total = session.execute(select(func.count(Document.id))).scalar() or 0
            today = datetime.now().date()
            doc_recent_today = session.execute(
                select(func.count(Document.id)).where(
                    func.date(Document.created_at) == today
                )
            ).scalar() or 0
            
            # 最近7天文档增长
            seven_days_ago = today - timedelta(days=7)
            doc_recent_7d = session.execute(
                select(func.count(Document.id)).where(
                    func.date(Document.created_at) >= seven_days_ago
                )
            ).scalar() or 0
            
            # 数据源统计
            source_total = session.execute(select(func.count(Source.id))).scalar() or 0
            source_enabled = session.execute(
                select(func.count(Source.id)).where(Source.enabled == True)
            ).scalar() or 0
            
            # 市场数据统计
            market_total = session.execute(select(func.count(MarketStat.id))).scalar() or 0
            
            # 覆盖的州数
            states_count = session.execute(
                select(func.count(func.distinct(MarketStat.state)))
            ).scalar() or 0
            
            # 搜索历史统计
            history_total = session.execute(select(func.count(SearchHistory.id))).scalar() or 0
            
            # ETL任务统计
            task_total = session.execute(select(func.count(EtlJobRun.id))).scalar() or 0
            task_running = session.execute(
                select(func.count(EtlJobRun.id)).where(EtlJobRun.status == "running")
            ).scalar() or 0
            task_completed = session.execute(
                select(func.count(EtlJobRun.id)).where(EtlJobRun.status == "completed")
            ).scalar() or 0
            task_failed = session.execute(
                select(func.count(EtlJobRun.id)).where(EtlJobRun.status == "failed")
            ).scalar() or 0
            
            # 文档类型分布
            doc_type_dist = session.execute(
                select(
                    Document.doc_type,
                    func.count(Document.id).label("count")
                ).group_by(Document.doc_type)
            ).all()
            doc_type_distribution = {row.doc_type: row.count for row in doc_type_dist}
            
            # 结构化数据提取率
            doc_with_extracted = session.execute(
                select(func.count(Document.id)).where(
                    document_queries.document_has_extracted_data_condition()
                )
            ).scalar() or 0
            extraction_rate = (doc_with_extracted / doc_total * 100) if doc_total > 0 else 0
            frontdoor_tri_state_rows = session.execute(
                select(EtlJobRun.params, EtlJobRun.status).where(EtlJobRun.params.isnot(None))
            ).all() or []
            frontdoor_tri_state = _build_frontdoor_tri_state_summary(frontdoor_tri_state_rows)
            pending_actions = _build_dashboard_pending_actions(
                doc_total=int(doc_total or 0),
                doc_with_extracted=int(doc_with_extracted or 0),
                source_total=int(source_total or 0),
                source_enabled=int(source_enabled or 0),
                task_failed=int(task_failed or 0),
                frontdoor_tri_state=frontdoor_tri_state,
            )
            
            return ok({
                "documents": _with_dashboard_sources(
                    {
                        "total": doc_total,
                        "recent_today": doc_recent_today,
                        "recent_7d": doc_recent_7d,
                        "type_distribution": doc_type_distribution,
                        "extraction_rate": round(extraction_rate, 2),
                    },
                    "documents",
                    table="documents",
                    metrics=[
                        "total",
                        "recent_today",
                        "recent_7d",
                        "type_distribution",
                        "extraction_rate",
                    ],
                    columns=["id", "created_at", "doc_type", "extracted_data"],
                    detail="document_has_extracted_data_condition",
                ),
                "sources": _with_dashboard_sources(
                    {
                        "total": source_total,
                        "enabled": source_enabled,
                    },
                    "sources",
                    table="sources",
                    metrics=["total", "enabled"],
                    columns=["id", "enabled"],
                ),
                "market_stats": _with_dashboard_sources(
                    {
                        "total": market_total,
                        "states_count": states_count,
                    },
                    "market_stats",
                    table="market_stats",
                    metrics=["total", "states_count"],
                    columns=["id", "state"],
                ),
                "search_history": _with_dashboard_sources(
                    {
                        "total": history_total,
                    },
                    "search_history",
                    table="search_history",
                    metrics=["total"],
                    columns=["id", "topic", "last_search_time"],
                ),
                "tasks": _with_dashboard_sources(
                    {
                        "total": task_total,
                        "running": task_running,
                        "completed": task_completed,
                        "failed": task_failed,
                        "frontdoor_tri_state": frontdoor_tri_state,
                    },
                    "tasks",
                    table="etl_job_runs",
                    metrics=["total", "running", "completed", "failed"],
                    columns=["id", "status", "params"],
                ),
                "llm_report_quality": _dashboard_llm_report_quality_summary(),
                "pending_actions": pending_actions,
            })
    except (OperationalError, DatabaseError) as e:
        logger.exception("数据库连接失败")
        _raise_upstream_error(
            "数据库服务不可用，请检查数据库服务是否已启动。",
            details={
                "category": "database",
                "exception_type": e.__class__.__name__,
                "retriable": True,
            },
        )
    except Exception as e:
        logger.exception("获取仪表盘统计数据失败")
        error_msg = str(e)
        if "Connection" in error_msg or "db" in error_msg.lower() or "database" in error_msg.lower() or "postgres" in error_msg.lower() or "timeout" in error_msg.lower():
            _raise_upstream_error(
                "数据库服务不可用，请检查数据库服务是否已启动。",
                details={
                    "category": "database",
                    "exception_type": e.__class__.__name__,
                    "retriable": True,
                },
            )
        _raise_internal_error(
            f"获取统计数据失败: {error_msg}",
            details={"exception_type": e.__class__.__name__},
        )


def _isoformat_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _serialize_document_drilldown_row(row: Any) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", None),
        "title": getattr(row, "title", None),
        "doc_type": getattr(row, "doc_type", None),
        "status": getattr(row, "status", None),
        "state": getattr(row, "state", None),
        "uri": getattr(row, "uri", None),
        "source_id": getattr(row, "source_id", None),
        "publish_date": _isoformat_or_none(getattr(row, "publish_date", None)),
        "created_at": _isoformat_or_none(getattr(row, "created_at", None)),
        "has_extracted_data": bool(getattr(row, "extracted_data", None)),
    }


def _serialize_source_drilldown_row(row: Any) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", None),
        "name": getattr(row, "name", None),
        "kind": getattr(row, "kind", None),
        "base_url": getattr(row, "base_url", None),
        "enabled": bool(getattr(row, "enabled", False)),
        "updated_at": _isoformat_or_none(getattr(row, "updated_at", None)),
    }


def _serialize_market_stat_drilldown_row(row: Any) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", None),
        "state": getattr(row, "state", None),
        "game": getattr(row, "game", None),
        "date": _isoformat_or_none(getattr(row, "date", None)),
        "revenue": _decimal_to_float(getattr(row, "revenue", None)),
        "sales_volume": _decimal_to_float(getattr(row, "sales_volume", None)),
        "source_name": getattr(row, "source_name", None),
        "source_uri": getattr(row, "source_uri", None),
    }


def _serialize_search_history_drilldown_row(row: Any) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", None),
        "topic": getattr(row, "topic", None),
        "last_search_time": _isoformat_or_none(getattr(row, "last_search_time", None)),
    }


def _serialize_task_drilldown_row(row: Any) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", None),
        "job_type": getattr(row, "job_type", None),
        "status": getattr(row, "status", None),
        "external_provider": getattr(row, "external_provider", None),
        "retry_count": getattr(row, "retry_count", None),
        "started_at": _isoformat_or_none(getattr(row, "started_at", None)),
        "finished_at": _isoformat_or_none(getattr(row, "finished_at", None)),
        "error": getattr(row, "error", None),
        "params": getattr(row, "params", None),
    }


_DASHBOARD_DRILLDOWN_ALIASES = {
    "documents": "documents",
    "documents.total": "documents",
    "documents.recent_today": "documents",
    "documents.recent_7d": "documents",
    "documents.type_distribution": "documents",
    "documents.extraction_rate": "documents",
    "sources": "sources",
    "sources.total": "sources",
    "sources.enabled": "sources",
    "market_stats": "market_stats",
    "market_stats.total": "market_stats",
    "market_stats.states_count": "market_stats",
    "search_history": "search_history",
    "search_history.total": "search_history",
    "tasks": "tasks",
    "tasks.total": "tasks",
    "tasks.running": "tasks",
    "tasks.completed": "tasks",
    "tasks.failed": "tasks",
    "tasks.frontdoor_tri_state": "tasks.frontdoor_tri_state",
}


def _normalize_dashboard_drilldown_key(value: str) -> str:
    raw = value.strip()
    if raw.startswith("dashboard.stats."):
        raw = raw.removeprefix("dashboard.stats.")
    key = _DASHBOARD_DRILLDOWN_ALIASES.get(raw)
    if not key:
        _raise_invalid_input_422(
            "metric or source_ref is not supported for dashboard drilldown",
            field="metric",
            value=value,
        )
    return key


def _dashboard_drilldown_config(metric: str) -> dict[str, Any]:
    if metric == "documents":
        return {
            "table": "documents",
            "columns": ["id", "title", "doc_type", "status", "state", "uri", "source_id", "created_at"],
            "base_filters": {},
            "query": select(Document).order_by(Document.created_at.desc(), Document.id.desc()),
            "serializer": _serialize_document_drilldown_row,
        }
    if metric == "sources":
        return {
            "table": "sources",
            "columns": ["id", "name", "kind", "base_url", "enabled", "updated_at"],
            "base_filters": {},
            "query": select(Source).order_by(Source.updated_at.desc(), Source.id.desc()),
            "serializer": _serialize_source_drilldown_row,
        }
    if metric == "market_stats":
        return {
            "table": "market_stats",
            "columns": ["id", "state", "game", "date", "revenue", "sales_volume", "source_uri"],
            "base_filters": {},
            "query": select(MarketStat).order_by(MarketStat.date.desc(), MarketStat.id.desc()),
            "serializer": _serialize_market_stat_drilldown_row,
        }
    if metric == "search_history":
        return {
            "table": "search_history",
            "columns": ["id", "topic", "last_search_time"],
            "base_filters": {},
            "query": select(SearchHistory).order_by(SearchHistory.last_search_time.desc(), SearchHistory.id.desc()),
            "serializer": _serialize_search_history_drilldown_row,
        }
    if metric == "tasks.frontdoor_tri_state":
        return {
            "table": "etl_job_runs",
            "columns": ["id", "job_type", "status", "external_provider", "params", "error"],
            "base_filters": {"params.frontdoor_status_summary": "present"},
            "query": select(EtlJobRun).where(EtlJobRun.params.isnot(None)).order_by(EtlJobRun.id.desc()),
            "serializer": _serialize_task_drilldown_row,
        }
    return {
        "table": "etl_job_runs",
        "columns": ["id", "job_type", "status", "external_provider", "params", "error"],
        "base_filters": {},
        "query": select(EtlJobRun).order_by(EtlJobRun.id.desc()),
        "serializer": _serialize_task_drilldown_row,
    }


@router.get("/drilldown", response_model=ApiEnvelope[dict[str, Any]])
def get_dashboard_drilldown(
    metric: Optional[str] = Query(None, description="Dashboard metric key, e.g. documents.total"),
    source_ref: Optional[str] = Query(None, description="Dashboard source ref id, e.g. dashboard.stats.documents"),
    limit: int = Query(10, ge=1, le=50, description="Maximum sample rows to return"),
):
    """Return sample rows and filters for a dashboard metric/source ref."""
    if not metric and not source_ref:
        _raise_invalid_input_422(
            "metric or source_ref is required",
            field="metric",
            value="",
        )
    normalized_metric = _normalize_dashboard_drilldown_key(metric or source_ref or "")
    if metric and source_ref:
        normalized_ref = _normalize_dashboard_drilldown_key(source_ref)
        if normalized_ref != normalized_metric:
            _raise_invalid_input_422(
                "metric and source_ref must point to the same dashboard source",
                field="source_ref",
                value=source_ref,
            )

    try:
        config = _dashboard_drilldown_config(normalized_metric)
        query = config["query"].limit(limit)
        with SessionLocal() as session:
            rows = session.execute(query).scalars().all()
        serializer = config["serializer"]
        sample_rows = [serializer(row) for row in rows]
        ref_id = f"dashboard.stats.{normalized_metric}"
        return ok({
            "metric": normalized_metric,
            "source_ref": ref_id,
            "filters": {
                **config["base_filters"],
                "limit": limit,
            },
            "sample_rows": sample_rows,
            "row_count": len(sample_rows),
            "source_query": _dashboard_source_query(
                normalized_metric,
                table=config["table"],
                metrics=[normalized_metric],
                filters=config["base_filters"],
            ),
            "source_refs": [
                _dashboard_source_ref(
                    normalized_metric,
                    table=config["table"],
                    columns=config["columns"],
                )
            ],
        })
    except (OperationalError, DatabaseError) as e:
        logger.exception("仪表盘下钻数据库连接失败")
        _raise_upstream_error(
            "数据库服务不可用，请检查数据库服务是否已启动。",
            details={
                "category": "database",
                "exception_type": e.__class__.__name__,
                "retriable": True,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取仪表盘下钻数据失败")
        _raise_internal_error(
            f"获取下钻数据失败: {e}",
            details={"exception_type": e.__class__.__name__},
        )


@router.post("/report-from-filter", response_model=ApiEnvelope[dict[str, Any]])
def create_dashboard_report_from_filter(payload: DashboardReportFromFilterRequest, request: Request):
    """Create a writing draft from Dashboard filters and source references."""
    dashboard = _dashboard_report_mapping(payload.dashboard)
    report_options = dict(payload.report_options or {})
    filters = _dashboard_report_mapping(dashboard.get("filters"))
    source_query = _dashboard_report_mapping(dashboard.get("source_query"))
    source_refs = _normalize_dashboard_report_source_refs(dashboard.get("source_refs"))
    raw_sample_rows = dashboard.get("sample_rows")
    sample_rows = [dict(item) for item in raw_sample_rows if isinstance(item, Mapping)] if isinstance(raw_sample_rows, list) else []
    checklist = _dashboard_report_checklist(
        filters=filters,
        source_refs=source_refs,
        source_query=source_query,
        sample_rows=sample_rows,
    )
    report_quality_gate = _build_dashboard_report_quality_gate(
        dashboard=dashboard,
        source_refs=source_refs,
        report_options=report_options,
    )
    quality_gate_mode = _dashboard_report_quality_gate_mode(payload, report_options)
    next_action = _dashboard_report_quality_next_action(report_quality_gate)
    quality = {
        "status": "ready" if source_refs else "blocked",
        "checklist": checklist,
        "report_quality_gate": report_quality_gate,
        "quality_gate_mode": quality_gate_mode,
        "next_action": next_action,
    }
    if not source_refs:
        return _error_json(
            422,
            ErrorCode.INVALID_INPUT,
            "dashboard source_refs are required to generate a report draft",
            details={
                "reason_code": "DASHBOARD_REPORT_SOURCE_REFS_REQUIRED",
                "quality": quality,
                "report_quality_gate": report_quality_gate,
                "blocking_reasons": report_quality_gate.get("blocking_reasons") or [],
                "next_action": next_action,
            },
        )

    if quality_gate_mode == "strict" and report_quality_gate.get("status") == "blocked":
        return _error_json(
            422,
            ErrorCode.INVALID_INPUT,
            "dashboard report quality gate blocked draft generation",
            details={
                "reason_code": "DASHBOARD_REPORT_QUALITY_GATE_BLOCKED",
                "quality_gate_mode": quality_gate_mode,
                "quality": quality,
                "report_quality_gate": report_quality_gate,
                "blocking_reasons": report_quality_gate.get("blocking_reasons") or [],
                "next_action": next_action,
            },
        )

    project_key = _dashboard_project_key_from_request(request, payload.project_key)
    title = _dashboard_report_title(dashboard)
    evidence_metadata = {
        "contract_version": "dashboard.report_from_filter.v1",
        "request_type": payload.request_type or "report_from_dashboard_filter",
        "project_key": project_key,
        "dashboard": {
            "variant": dashboard.get("variant"),
            "selected_label": dashboard.get("selected_label"),
            "selected_metric": dashboard.get("selected_metric"),
            "selected_source_ref": dashboard.get("selected_source_ref"),
            "pending_action_id": dashboard.get("pending_action_id"),
            "filters": filters,
            "action_filters": _dashboard_report_mapping(dashboard.get("action_filters")),
            "drilldown_filters": _dashboard_report_mapping(dashboard.get("drilldown_filters")),
            "source_query": source_query,
            "source_refs": source_refs,
            "sample_row_count": int(dashboard.get("sample_row_count") or len(sample_rows) or 0),
        },
        "report_options": report_options,
        "quality": quality,
        "report_quality_gate": report_quality_gate,
    }
    body_md = _render_dashboard_report_body(
        title=title,
        project_key=project_key,
        dashboard=dashboard,
        filters=filters,
        source_refs=source_refs,
        source_query=source_query,
        sample_rows=sample_rows,
        checklist=checklist,
        report_quality_gate=report_quality_gate,
    )
    actor_context = resolve_request_actor_context(request)
    report_trace_id = _dashboard_report_trace_id()
    report_request_id = str(request.headers.get("x-request-id") or "").strip() or None
    evidence_metadata["trace_id"] = report_trace_id
    evidence_metadata["request_id"] = report_request_id
    export_artifact = build_llm_report_export_artifact(
        markdown=body_md,
        gate=_dashboard_report_gate_for_export(report_quality_gate),
        gate_mode=_dashboard_report_gate_mode_for_export(quality_gate_mode),
        trace_id=report_trace_id,
        request_id=report_request_id,
        project_key=project_key,
        job_id=None,
        topic=title,
        token_secret=settings.llm_report_export_token_secret,
        actor_id=actor_context.actor_id,
        ttl_seconds=getattr(settings, "llm_report_export_token_ttl_seconds", 3600),
        one_time_use=bool(getattr(settings, "llm_report_export_one_time_use_enabled", True)),
    )
    export_artifact["actor_context"] = actor_context.to_observability()
    evidence_metadata["export_artifact"] = export_artifact
    try:
        with bind_project(project_key):
            document = create_document(
                project_key=project_key,
                title=title,
                body_md=body_md,
                updated_by_user_id="dashboard.report_from_filter",
                metadata_json=evidence_metadata,
            )
    except ValueError as exc:
        return _error_json(
            400,
            ErrorCode.INVALID_INPUT,
            str(exc) or "invalid dashboard report project context",
            details={"project_key": project_key, "exception_type": exc.__class__.__name__},
        )

    try:
        record_quality_trend_metric(
            _dashboard_report_quality_trend_record(
                trace_id=report_trace_id,
                request_id=report_request_id,
                project_key=project_key,
                title=title,
                source_refs=source_refs,
                source_query=source_query,
                report_quality_gate=report_quality_gate,
                quality_gate_mode=quality_gate_mode,
                next_action=next_action,
                export_artifact=export_artifact,
                document=document,
            ),
            job_id=None,
            topic=title,
            job_status="completed" if report_quality_gate.get("status") != "blocked" else "failed",
            source="dashboard_report_from_filter",
        )
    except Exception:  # noqa: BLE001
        logger.exception("记录 dashboard report quality trend 失败")

    report_id = f"writing_document:{document.get('id')}"
    return ok(
        {
            "contract_version": "dashboard.report_from_filter.v1",
            "report_id": report_id,
            "trace_id": report_trace_id,
            "request_id": report_request_id,
            "draft_id": document.get("id"),
            "document_id": document.get("id"),
            "title": document.get("title") or title,
            "status": document.get("status") or "draft",
            "filters": filters,
            "source_query": source_query,
            "source_refs": source_refs,
            "quality": quality,
            "report_quality_gate": report_quality_gate,
            "export_artifact": export_artifact,
            "artifact": export_artifact,
            "actor_context": actor_context.to_observability(),
            "draft": {
                "id": document.get("id"),
                "report_id": report_id,
                "title": document.get("title") or title,
                "status": document.get("status") or "draft",
                "version": document.get("version") or document.get("head_version"),
            },
            "document": document,
            "evidence_metadata": evidence_metadata,
        }
    )


@router.get("/market-trends", response_model=ApiEnvelope[dict[str, Any]])
def get_market_trends(
    state: Optional[str] = Query(None, description="州过滤"),
    game: Optional[str] = Query(None, description="游戏类型过滤"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    period: str = Query("daily", pattern="^(daily|monthly)$", description="聚合周期"),
):
    """获取市场趋势数据"""
    start = _parse_ymd_date_param(start_date, field="start_date")
    end = _parse_ymd_date_param(end_date, field="end_date")

    with SessionLocal() as session:
        query = select(MarketStat)
        
        conditions = []
        if state:
            conditions.append(MarketStat.state == state.upper())
        if game:
            conditions.append(MarketStat.game.ilike(f"%{game}%"))
        if start:
            conditions.append(MarketStat.date >= start)
        if end:
            conditions.append(MarketStat.date <= end)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        if period == "monthly":
            # 按月聚合
            rows = session.execute(
                select(
                    func.date_trunc("month", MarketStat.date).label("month"),
                    MarketStat.state,
                    MarketStat.game,
                    func.avg(MarketStat.revenue).label("avg_revenue"),
                    func.avg(MarketStat.sales_volume).label("avg_sales_volume"),
                    func.avg(MarketStat.jackpot).label("avg_jackpot"),
                    func.sum(MarketStat.revenue).label("total_revenue"),
                    func.sum(MarketStat.sales_volume).label("total_sales_volume"),
                )
                .where(and_(*conditions) if conditions else True)
                .group_by(
                    func.date_trunc("month", MarketStat.date),
                    MarketStat.state,
                    MarketStat.game,
                )
                .order_by(func.date_trunc("month", MarketStat.date))
            ).all()
            
            series = []
            for row in rows:
                series.append({
                    "date": row.month.date().isoformat() if row.month else None,
                    "state": row.state,
                    "game": row.game,
                    "revenue": _decimal_to_float(row.avg_revenue),
                    "sales_volume": _decimal_to_float(row.avg_sales_volume),
                    "jackpot": _decimal_to_float(row.avg_jackpot),
                    "total_revenue": _decimal_to_float(row.total_revenue),
                    "total_sales_volume": _decimal_to_float(row.total_sales_volume),
                })
        else:
            # 按日聚合
            rows = session.execute(
                query.order_by(MarketStat.date.asc())
            ).scalars().all()
            
            series = []
            for stat in rows:
                series.append({
                    "date": stat.date.isoformat() if stat.date else None,
                    "state": stat.state,
                    "game": stat.game,
                    "revenue": _decimal_to_float(stat.revenue),
                    "sales_volume": _decimal_to_float(stat.sales_volume),
                    "jackpot": _decimal_to_float(stat.jackpot),
                    "ticket_price": _decimal_to_float(stat.ticket_price),
                    "yoy": _decimal_to_float(stat.yoy),
                    "mom": _decimal_to_float(stat.mom),
                })
        
        # 州分布统计
        state_dist = session.execute(
            select(
                MarketStat.state,
                func.count(MarketStat.id).label("count"),
                func.sum(MarketStat.revenue).label("total_revenue"),
            )
            .where(and_(*conditions) if conditions else True)
            .group_by(MarketStat.state)
        ).all()
        state_distribution = [
            {
                "state": row.state,
                "count": row.count,
                "total_revenue": _decimal_to_float(row.total_revenue),
            }
            for row in state_dist
        ]
        
        # 游戏类型分布
        game_dist = session.execute(
            select(
                MarketStat.game,
                func.count(MarketStat.id).label("count"),
                func.avg(MarketStat.revenue).label("avg_revenue"),
            )
            .where(and_(*conditions) if conditions else True)
            .where(MarketStat.game.isnot(None))
            .group_by(MarketStat.game)
        ).all()
        game_distribution = [
            {
                "game": row.game,
                "count": row.count,
                "avg_revenue": _decimal_to_float(row.avg_revenue),
            }
            for row in game_dist
        ]
        
        return ok({
            "series": series,
            "state_distribution": state_distribution,
            "game_distribution": game_distribution,
            "period": period,
        })


@router.get("/document-analysis", response_model=ApiEnvelope[dict[str, Any]])
def get_document_analysis(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
):
    """获取文档分析数据"""
    start = _parse_ymd_date_param(start_date, field="start_date")
    end = _parse_ymd_date_param(end_date, field="end_date")

    with SessionLocal() as session:
        conditions = []
        if start:
            conditions.append(func.date(Document.created_at) >= start)
        if end:
            conditions.append(func.date(Document.created_at) <= end)
        
        # 文档类型分布
        type_query = select(
            Document.doc_type,
            func.count(Document.id).label("count")
        ).group_by(Document.doc_type)
        if conditions:
            type_query = type_query.where(and_(*conditions))
        type_dist = session.execute(type_query).all()
        type_distribution = [
            {"type": row.doc_type, "count": row.count}
            for row in type_dist
        ]
        
        # 文档增长趋势（按日期）
        growth_query = select(
            func.date(Document.created_at).label("date"),
            func.count(Document.id).label("count")
        ).group_by(func.date(Document.created_at))
        if conditions:
            growth_query = growth_query.where(and_(*conditions))
        growth_query = growth_query.order_by(func.date(Document.created_at))
        growth_data = session.execute(growth_query).all()
        growth_trend = [
            {
                "date": row.date.isoformat() if row.date else None,
                "count": row.count,
            }
            for row in growth_data
        ]
        
        # 州分布
        state_query = select(
            Document.state,
            func.count(Document.id).label("count")
        ).where(Document.state.isnot(None)).group_by(Document.state)
        if conditions:
            state_query = state_query.where(and_(*conditions))
        state_dist = session.execute(state_query).all()
        state_distribution = [
            {"state": row.state, "count": row.count}
            for row in state_dist
        ]
        
        # 数据源贡献度
        source_query = select(
            Source.name,
            Source.id,
            func.count(Document.id).label("count")
        ).join(Document, Source.id == Document.source_id, isouter=True)
        if conditions:
            source_query = source_query.where(and_(*conditions))
        source_query = source_query.group_by(Source.id, Source.name)
        source_dist = session.execute(source_query).all()
        source_contribution = [
            {"source_name": row.name or "未知", "count": row.count}
            for row in source_dist
        ]
        
        # 结构化数据提取率（按类型）
        extraction_query = select(
            Document.doc_type,
            func.count(Document.id).label("total"),
            func.sum(
                document_queries.document_extracted_data_present_case()
            ).label("with_extracted")
        ).group_by(Document.doc_type)
        if conditions:
            extraction_query = extraction_query.where(and_(*conditions))
        extraction_dist = session.execute(extraction_query).all()
        extraction_by_type = [
            {
                "type": row.doc_type,
                "total": row.total,
                "with_extracted": row.with_extracted,
                "rate": round((row.with_extracted / row.total * 100) if row.total > 0 else 0, 2),
            }
            for row in extraction_dist
        ]
        
        return ok({
            "type_distribution": type_distribution,
            "growth_trend": growth_trend,
            "state_distribution": state_distribution,
            "source_contribution": source_contribution,
            "extraction_by_type": extraction_by_type,
        })


@router.get("/sentiment-analysis", response_model=ApiEnvelope[dict[str, Any]])
def get_sentiment_analysis(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
):
    """获取社交媒体情感分析数据"""
    start = _parse_ymd_date_param(start_date, field="start_date")
    end = _parse_ymd_date_param(end_date, field="end_date")

    graph_doc_types = resolve_graph_doc_types()
    social_doc_types = graph_doc_types.get("social") or ["social_sentiment", "social_feed"]
    with SessionLocal() as session:
        conditions = [
            *document_queries.social_document_base_conditions(social_doc_types),
        ]
        
        if start:
            # 使用发布时间过滤，如果没有发布时间则使用创建时间
            conditions.append(
                or_(
                    Document.publish_date >= start,
                    and_(Document.publish_date.is_(None), func.date(Document.created_at) >= start)
                )
            )
        if end:
            # 使用发布时间过滤，如果没有发布时间则使用创建时间
            conditions.append(
                or_(
                    Document.publish_date <= end,
                    and_(Document.publish_date.is_(None), func.date(Document.created_at) <= end)
                )
            )
        
        query = select(Document).where(and_(*conditions))
        docs = session.execute(query).scalars().all()
        
        # 情感分布统计
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0, "unknown": 0}
        platform_counts = {}
        platform_sentiment = {}  # 每个平台的情感分布
        sentiment_trend = {}
        keyword_counts = {}  # 关键词统计
        
        for doc in docs:
            sentiment = get_social_sentiment_orientation(doc)
            if sentiment in ["positive", "negative", "neutral"]:
                sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
            else:
                sentiment_counts["unknown"] = sentiment_counts.get("unknown", 0) + 1
            
            # 平台统计
            platform = get_social_platform_label(doc)
            platform_counts[platform] = platform_counts.get(platform, 0) + 1
            
            # 平台情感分布统计
            if platform not in platform_sentiment:
                platform_sentiment[platform] = {"positive": 0, "negative": 0, "neutral": 0, "unknown": 0}
            if sentiment in ["positive", "negative", "neutral"]:
                platform_sentiment[platform][sentiment] = platform_sentiment[platform].get(sentiment, 0) + 1
            else:
                platform_sentiment[platform]["unknown"] = platform_sentiment[platform].get("unknown", 0) + 1
            
            # 情感趋势（按日期）- 使用发布时间，如果没有则使用创建时间
            date_for_trend = doc.publish_date if doc.publish_date else (doc.created_at.date() if doc.created_at else None)
            if date_for_trend:
                date_key = date_for_trend.isoformat() if isinstance(date_for_trend, date) else date_for_trend
                if date_key not in sentiment_trend:
                    sentiment_trend[date_key] = {"positive": 0, "negative": 0, "neutral": 0}
                if sentiment in ["positive", "negative", "neutral"]:
                    sentiment_trend[date_key][sentiment] = sentiment_trend[date_key].get(sentiment, 0) + 1
            
            # 关键词统计（从key_phrases、topic、sentiment_tags中提取）
            for term in get_social_sentiment_terms(doc):
                term_lower = term.lower().strip()
                if term_lower:
                    keyword_counts[term_lower] = keyword_counts.get(term_lower, 0) + 1
        
        # 转换趋势数据为列表格式
        trend_series = []
        for date_key in sorted(sentiment_trend.keys()):
            trend_series.append({
                "date": date_key,
                **sentiment_trend[date_key],
            })
        
        # 平台分布（包含情感数据）
        platform_distribution = []
        for platform, count in platform_counts.items():
            platform_distribution.append({
                "platform": platform,
                "count": count,
                "positive": platform_sentiment.get(platform, {}).get("positive", 0),
                "negative": platform_sentiment.get(platform, {}).get("negative", 0),
                "neutral": platform_sentiment.get(platform, {}).get("neutral", 0),
                "unknown": platform_sentiment.get(platform, {}).get("unknown", 0),
            })
        
        # 关键词排行（取前20个）
        keyword_ranking = sorted(
            keyword_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]
        keyword_ranking_list = [
            {"keyword": keyword, "count": count}
            for keyword, count in keyword_ranking
        ]
        
        return ok({
            "sentiment_distribution": sentiment_counts,
            "platform_distribution": platform_distribution,
            "sentiment_trend": trend_series,
            "keyword_ranking": keyword_ranking_list,
            "total_documents": len(docs),
        })


@router.get("/sentiment-sources", response_model=ApiEnvelope[dict[str, Any]])
def get_sentiment_sources(
    sentiment: Optional[str] = Query(None, description="情感类型: positive, negative, neutral, unknown"),
    platform: Optional[str] = Query(None, description="平台名称"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(default=50, ge=1, le=200, description="返回数量限制"),
):
    """根据筛选条件获取数据源列表"""
    start = _parse_ymd_date_param(start_date, field="start_date")
    end = _parse_ymd_date_param(end_date, field="end_date")

    graph_doc_types = resolve_graph_doc_types()
    social_doc_types = graph_doc_types.get("social") or ["social_sentiment", "social_feed"]
    with SessionLocal() as session:
        conditions = [
            *document_queries.social_document_base_conditions(social_doc_types),
        ]
        
        if start:
            # 使用发布时间过滤，如果没有发布时间则使用创建时间
            conditions.append(
                or_(
                    Document.publish_date >= start,
                    and_(Document.publish_date.is_(None), func.date(Document.created_at) >= start)
                )
            )
        if end:
            # 使用发布时间过滤，如果没有发布时间则使用创建时间
            conditions.append(
                or_(
                    Document.publish_date <= end,
                    and_(Document.publish_date.is_(None), func.date(Document.created_at) <= end)
                )
            )
        
        query = select(Document).where(and_(*conditions))
        docs = session.execute(query).scalars().all()
        
        # 根据情感和平台筛选
        filtered_docs = []
        for doc in docs:
            doc_sentiment = get_social_sentiment_orientation(doc)
            doc_platform = get_social_platform_label(doc)
            
            # 情感筛选
            if sentiment:
                if sentiment == "unknown":
                    if doc_sentiment not in ["positive", "negative", "neutral"]:
                        pass  # 匹配unknown
                    else:
                        continue
                elif doc_sentiment != sentiment:
                    continue
            
            # 平台筛选
            if platform and doc_platform != platform:
                continue
            
            filtered_docs.append(doc)
        
        # 限制数量
        filtered_docs = filtered_docs[:limit]
        
        # 构建返回数据
        sources = []
        for doc in filtered_docs:
            sources.append({
                "id": doc.id,
                "title": doc.title or "无标题",
                "uri": doc.uri,
                "platform": get_social_platform_label(doc),
                "sentiment": get_social_sentiment_orientation(doc, default="unknown"),
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "publish_date": doc.publish_date.isoformat() if doc.publish_date else None,
                "summary": doc.summary or "",
            })
        
        return ok({
            "sources": sources,
            "total": len(filtered_docs),
            "filters": {
                "sentiment": sentiment,
                "platform": platform,
                "start_date": start_date,
                "end_date": end_date,
            }
        })


@router.get("/task-monitoring", response_model=ApiEnvelope[dict[str, Any]])
def get_task_monitoring(
    limit: int = Query(default=50, ge=1, le=500),
    status: Optional[str] = Query(None, description="任务状态过滤"),
):
    """获取任务监控数据"""
    with SessionLocal() as session:
        query = select(EtlJobRun)
        
        if status:
            query = query.where(EtlJobRun.status == status)
        
        query = query.order_by(EtlJobRun.started_at.desc()).limit(limit)
        tasks = session.execute(query).scalars().all()
        
        # 任务类型分布
        type_query = select(
            EtlJobRun.job_type,
            func.count(EtlJobRun.id).label("count"),
            func.sum(
                case((EtlJobRun.status == "completed", 1), else_=0)
            ).label("completed"),
            func.sum(
                case((EtlJobRun.status == "failed", 1), else_=0)
            ).label("failed"),
        ).group_by(EtlJobRun.job_type)
        type_dist = session.execute(type_query).all()
        type_distribution = [
            {
                "job_type": row.job_type,
                "count": row.count,
                "completed": row.completed,
                "failed": row.failed,
            }
            for row in type_dist
        ]
        
        # 最近任务列表
        recent_tasks = []
        for task in tasks:
            duration = None
            if task.started_at and task.finished_at:
                duration = (task.finished_at - task.started_at).total_seconds()
            elif task.started_at:
                duration = (datetime.now(task.started_at.tzinfo) - task.started_at).total_seconds()
            
            recent_tasks.append({
                "id": task.id,
                "job_type": task.job_type,
                "status": task.status,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "finished_at": task.finished_at.isoformat() if task.finished_at else None,
                "duration_seconds": duration,
                "error": task.error,
            })
        
        return ok({
            "recent_tasks": recent_tasks,
            "type_distribution": type_distribution,
        })


@router.get("/search-analytics", response_model=ApiEnvelope[dict[str, Any]])
def get_search_analytics(limit: int = Query(default=50, ge=1, le=500)):
    """获取搜索行为分析数据"""
    with SessionLocal() as session:
        # 热门搜索主题
        query = select(SearchHistory).order_by(
            SearchHistory.last_search_time.desc()
        ).limit(limit)
        history = session.execute(query).scalars().all()
        
        # 统计每个主题的搜索次数（基于topic唯一性，实际是last_search_time）
        topic_counts = {}
        for h in history:
            topic_counts[h.topic] = topic_counts.get(h.topic, 0) + 1
        
        # 转换为列表并排序
        popular_topics = [
            {"topic": topic, "count": count}
            for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
        ]
        
        # 搜索频率趋势（按日期）
        trend_query = select(
            func.date(SearchHistory.last_search_time).label("date"),
            func.count(SearchHistory.id).label("count")
        ).group_by(func.date(SearchHistory.last_search_time)).order_by(
            func.date(SearchHistory.last_search_time)
        )
        trend_data = session.execute(trend_query).all()
        search_trend = [
            {
                "date": row.date.isoformat() if row.date else None,
                "count": row.count,
            }
            for row in trend_data
        ]
        
        return ok({
            "popular_topics": popular_topics[:20],  # 返回TOP 20
            "search_trend": search_trend,
        })


@router.get("/commodity-trends", response_model=ApiEnvelope[dict[str, Any]])
def get_commodity_trends(
    metric_key: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    period: str = Query("daily", pattern="^(daily|monthly)$"),
):
    start = _parse_ymd_date_param(start_date, field="start_date")
    end = _parse_ymd_date_param(end_date, field="end_date")

    with SessionLocal() as session:
        query = select(MarketMetricPoint)
        if metric_key:
            query = query.where(MarketMetricPoint.metric_key == metric_key)
        if start:
            query = query.where(MarketMetricPoint.date >= start)
        if end:
            query = query.where(MarketMetricPoint.date <= end)

        if period == "monthly":
            rows = session.execute(
                select(
                    func.date_trunc("month", MarketMetricPoint.date).label("month"),
                    MarketMetricPoint.metric_key,
                    func.avg(MarketMetricPoint.value).label("avg_value"),
                    func.count(MarketMetricPoint.id).label("count"),
                )
                .where(
                    MarketMetricPoint.metric_key == metric_key if metric_key else True
                )
                .group_by(func.date_trunc("month", MarketMetricPoint.date), MarketMetricPoint.metric_key)
                .order_by(func.date_trunc("month", MarketMetricPoint.date))
            ).all()
            series = [
                {
                    "date": row.month.date().isoformat() if row.month else None,
                    "metric_key": row.metric_key,
                    "value": _decimal_to_float(row.avg_value),
                    "count": row.count,
                }
                for row in rows
            ]
        else:
            rows = session.execute(query.order_by(MarketMetricPoint.date.asc())).scalars().all()
            series = [
                {
                    "date": row.date.isoformat() if row.date else None,
                    "metric_key": row.metric_key,
                    "value": _decimal_to_float(row.value),
                    "unit": row.unit,
                    "currency": row.currency,
                    "source_name": row.source_name,
                }
                for row in rows
            ]

        metric_distribution = session.execute(
            select(
                MarketMetricPoint.metric_key,
                func.count(MarketMetricPoint.id).label("count"),
            ).group_by(MarketMetricPoint.metric_key)
        ).all()

        return ok({
            "series": series,
            "metric_distribution": [
                {"metric_key": row.metric_key, "count": row.count}
                for row in metric_distribution
            ],
            "period": period,
        })


@router.get("/ecom-price-trends", response_model=ApiEnvelope[dict[str, Any]])
def get_ecom_price_trends(
    product_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None, description="开始时间 ISO8601"),
    end_date: Optional[str] = Query(None, description="结束时间 ISO8601"),
):
    start_dt = _parse_iso8601_datetime_param(start_date, field="start_date")
    end_dt = _parse_iso8601_datetime_param(end_date, field="end_date")

    with SessionLocal() as session:
        query = (
            select(PriceObservation, Product)
            .join(Product, Product.id == PriceObservation.product_id)
        )
        if product_id:
            query = query.where(PriceObservation.product_id == product_id)
        if start_dt:
            query = query.where(PriceObservation.captured_at >= start_dt)
        if end_dt:
            query = query.where(PriceObservation.captured_at <= end_dt)

        rows = session.execute(query.order_by(PriceObservation.captured_at.asc())).all()
        series = [
            {
                "product_id": p.id,
                "product_name": p.name,
                "captured_at": o.captured_at.isoformat() if o.captured_at else None,
                "price": _decimal_to_float(o.price),
                "currency": o.currency or p.currency,
                "availability": o.availability,
            }
            for o, p in rows
        ]

        product_distribution = session.execute(
            select(
                Product.id,
                Product.name,
                func.count(PriceObservation.id).label("count"),
                func.avg(PriceObservation.price).label("avg_price"),
            )
            .join(PriceObservation, PriceObservation.product_id == Product.id, isouter=True)
            .group_by(Product.id, Product.name)
        ).all()

        return ok({
            "series": series,
            "product_distribution": [
                {
                    "product_id": row.id,
                    "product_name": row.name,
                    "count": row.count,
                    "avg_price": _decimal_to_float(row.avg_price),
                }
                for row in product_distribution
            ],
        })
