from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select

from ..models.base import run_with_session_retry
from ..models.llm_report_export_audit import LlmReportExportAuditEvent

MAX_EXPORT_AUDIT_MEMORY_RECORDS = 200
_LLM_REPORT_EXPORT_AUDIT_EVENTS: list[dict[str, Any]] = []
_UI_READ_ONLY_CONTEXT_SCOPE = "ui_read_only_evidence_context"
_UI_READ_ONLY_CONTEXT_REASON = "reset_telemetry_boundary_context_rendered_as_read_only_export_boundary_note"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "trusted", "pass", "success"}
    return bool(value)


def _as_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_str_or_none(value: Any, *, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length] if max_length else text


def _parse_recorded_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _nested_ui_read_only_context_value(payload: dict[str, Any], key: str) -> Any:
    if key in payload:
        return payload.get(key)
    audit_event = _as_mapping(payload.get("audit_event"))
    if key in audit_event:
        return audit_event.get(key)
    governance = _as_mapping(payload.get("governance"))
    governance_context = _as_mapping(governance.get("ui_read_only_context"))
    return governance_context.get(key)


def _normalized_ui_read_only_context_fields(payload: dict[str, Any]) -> dict[str, Any]:
    if not _as_bool(_nested_ui_read_only_context_value(payload, "ui_read_only_context_included")):
        return {}
    scope = _as_str_or_none(
        _nested_ui_read_only_context_value(payload, "ui_read_only_context_scope"),
        max_length=128,
    )
    if scope != _UI_READ_ONLY_CONTEXT_SCOPE:
        return {}
    fields = {
        "ui_read_only_context_included": True,
        "ui_read_only_context_scope": scope,
        "ui_read_only_context_reason": _as_str_or_none(
            _nested_ui_read_only_context_value(payload, "ui_read_only_context_reason"),
            max_length=256,
        )
        or _UI_READ_ONLY_CONTEXT_REASON,
    }
    source = _as_str_or_none(
        _nested_ui_read_only_context_value(payload, "ui_read_only_context_source"),
        max_length=256,
    )
    if source:
        fields["ui_read_only_context_source"] = source
    return fields


def _normalized_source_ref(payload: dict[str, Any]) -> dict[str, Any]:
    source_ref = _as_mapping(payload.get("source_ref"))
    if source_ref:
        return {
            "contract_version": source_ref.get("contract_version") or "llm_report.export_source_ref.v1",
            **source_ref,
        }
    source_ref_id = (
        _as_str_or_none(payload.get("artifact_id"))
        or _as_str_or_none(payload.get("source_trace_id"))
        or _as_str_or_none(payload.get("request_id"))
        or _as_str_or_none(payload.get("trace_id"))
        or "llm_report_export"
    )
    return {
        "contract_version": "llm_report.export_source_ref.v1",
        "id": source_ref_id,
        "kind": "llm_report_export_artifact",
        "source_trace_id": _as_str_or_none(payload.get("source_trace_id"), max_length=128),
        "request_id": _as_str_or_none(payload.get("request_id"), max_length=128),
        "project_key": _as_str_or_none(payload.get("project_key"), max_length=64),
        "job_id": _as_int_or_none(payload.get("job_id")),
        "artifact_id": _as_str_or_none(payload.get("artifact_id"), max_length=128),
        "export_format": (_as_str_or_none(payload.get("export_format"), max_length=32) or "unknown").lower(),
        "filename": _as_str_or_none(payload.get("filename")),
    }


def _normalized_quality_gate(payload: dict[str, Any]) -> dict[str, Any]:
    quality_gate = _as_mapping(payload.get("quality_gate"))
    decision = _as_str_or_none(
        quality_gate.get("decision") or payload.get("quality_gate_decision") or payload.get("decision"),
        max_length=32,
    )
    mode = _as_str_or_none(quality_gate.get("mode") or payload.get("quality_gate_mode") or payload.get("gate_mode"))
    return {
        "contract_version": quality_gate.get("contract_version") or "llm_report.export_quality_gate_ref.v1",
        **quality_gate,
        "decision": (decision or "fail").lower(),
        "mode": mode,
        "mode_raw": quality_gate.get("mode_raw") or payload.get("quality_gate_mode_raw") or payload.get("gate_mode_raw"),
        "mode_fallback": _as_bool(
            quality_gate.get("mode_fallback")
            if quality_gate.get("mode_fallback") is not None
            else payload.get("quality_gate_mode_fallback", payload.get("gate_mode_fallback"))
        ),
        "strict_gate_blocks_export": _as_bool(
            quality_gate.get("strict_gate_blocks_export") or payload.get("strict_gate_blocks_export")
        ),
    }


def _normalized_governance_fields(payload: dict[str, Any], *, trace_id: str, outcome: str) -> dict[str, Any]:
    source_ref = _normalized_source_ref(payload)
    quality_gate = _normalized_quality_gate(payload)
    export_format = (_as_str_or_none(payload.get("export_format"), max_length=32) or "unknown").lower()
    readiness = (_as_str_or_none(payload.get("readiness"), max_length=32) or "unknown").lower()
    ui_read_only_context_fields = _normalized_ui_read_only_context_fields(payload)
    audit_event = {
        "contract_version": "llm_report.export_audit_event_ref.v1",
        **_as_mapping(payload.get("audit_event")),
        "type": "llm_report_export",
        "trace_id": trace_id,
        "source_trace_id": source_ref.get("source_trace_id"),
        "outcome": outcome,
        "error_code": _as_str_or_none(payload.get("error_code"), max_length=128),
        "strict_gate_blocked": bool(quality_gate.get("strict_gate_blocks_export")) and outcome == "blocked",
        "compatible_quality_gate_path": quality_gate.get("mode") in {"off", "warn"} and outcome == "success",
        "token_invalid": outcome == "token_invalid",
        **ui_read_only_context_fields,
    }
    governance = {
        "contract_version": "llm_report.export_governance.v1",
        **_as_mapping(payload.get("governance")),
        "trace_id": trace_id,
        "source_trace_id": source_ref.get("source_trace_id"),
        "request_id": source_ref.get("request_id"),
        "project_key": source_ref.get("project_key"),
        "job_id": source_ref.get("job_id"),
        "format": export_format,
        "readiness": readiness,
        "outcome": outcome,
        "quality_gate": quality_gate,
        "source_ref": source_ref,
        "audit_event": audit_event,
    }
    if ui_read_only_context_fields:
        governance["ui_read_only_context"] = ui_read_only_context_fields
    header_snapshot = {
        "contract_version": "llm_report.export_header_snapshot.v1",
        **_as_mapping(payload.get("header_snapshot") or payload.get("export_header_snapshot")),
        "format": export_format,
        "readiness": readiness,
        "quality_gate_decision": quality_gate.get("decision"),
        "quality_gate_mode": quality_gate.get("mode"),
        "source_ref": source_ref.get("id"),
        "source_trace_id": source_ref.get("source_trace_id"),
        "project_key": source_ref.get("project_key"),
        "job_id": source_ref.get("job_id"),
        "content_type": _as_str_or_none(payload.get("content_type"), max_length=128),
    }
    return {
        "source_ref": source_ref,
        "quality_gate": quality_gate,
        "audit_event": audit_event,
        "governance": governance,
        "header_snapshot": header_snapshot,
        "export_header_snapshot": header_snapshot,
    }


def _normalize_event(record: dict[str, Any]) -> dict[str, Any]:
    payload = record if isinstance(record, dict) else {}
    trace_id = _as_str_or_none(payload.get("trace_id"), max_length=128)
    if not trace_id:
        source = _as_str_or_none(payload.get("source_trace_id") or payload.get("artifact_id"), max_length=72) or "export"
        trace_id = f"{source}:export_audit:{uuid4().hex[:12]}"[:128]
    recorded_at = _parse_recorded_at(payload.get("recorded_at"))
    outcome = payload.get("outcome", payload.get("export_outcome"))
    integrity_mode = payload.get("integrity_mode", payload.get("export_integrity_mode"))
    integrity_trusted = payload.get("integrity_trusted", payload.get("export_integrity_trusted"))
    normalized_outcome = (_as_str_or_none(outcome, max_length=32) or "unknown").lower()
    governance_fields = _normalized_governance_fields(payload, trace_id=trace_id, outcome=normalized_outcome)
    ui_read_only_context_fields = _normalized_ui_read_only_context_fields(payload)
    return {
        **payload,
        "contract_version": payload.get("contract_version") or "llm_report.export_audit_event.v1",
        "event_type": "llm_report_export",
        "record_source": "export_audit",
        "trace_id": trace_id,
        "source_trace_id": _as_str_or_none(payload.get("source_trace_id"), max_length=128),
        "request_id": _as_str_or_none(payload.get("request_id"), max_length=128),
        "project_key": _as_str_or_none(payload.get("project_key"), max_length=64),
        "job_id": _as_int_or_none(payload.get("job_id")),
        "export_format": (_as_str_or_none(payload.get("export_format"), max_length=32) or "unknown").lower(),
        "export_outcome": normalized_outcome,
        "outcome": normalized_outcome,
        "readiness": governance_fields["header_snapshot"]["readiness"],
        "quality_gate_decision": governance_fields["header_snapshot"]["quality_gate_decision"],
        "quality_gate_mode": governance_fields["header_snapshot"]["quality_gate_mode"],
        "quality_gate_mode_raw": governance_fields["quality_gate"].get("mode_raw"),
        "quality_gate_mode_fallback": bool(governance_fields["quality_gate"].get("mode_fallback")),
        "strict_gate_blocks_export": bool(governance_fields["quality_gate"].get("strict_gate_blocks_export")),
        "export_integrity_mode": _as_str_or_none(integrity_mode, max_length=64),
        "integrity_mode": _as_str_or_none(integrity_mode, max_length=64),
        "export_integrity_trusted": _as_bool(integrity_trusted),
        "integrity_trusted": _as_bool(integrity_trusted),
        "actor_id": _as_str_or_none(payload.get("actor_id"), max_length=128),
        "artifact_id": _as_str_or_none(payload.get("artifact_id"), max_length=128),
        "artifact_sha256": _as_str_or_none(payload.get("artifact_sha256"), max_length=64),
        "filename": _as_str_or_none(payload.get("filename")),
        "content_type": _as_str_or_none(payload.get("content_type"), max_length=128),
        "content_size_bytes": _as_int_or_none(payload.get("content_size_bytes")),
        "error_code": _as_str_or_none(payload.get("error_code"), max_length=128),
        "recorded_at": recorded_at.isoformat(),
        **ui_read_only_context_fields,
        **governance_fields,
    }


def _apply_record_to_row(row: LlmReportExportAuditEvent, record: dict[str, Any]) -> None:
    row.trace_id = _as_str_or_none(record.get("trace_id"), max_length=128)
    row.source_trace_id = _as_str_or_none(record.get("source_trace_id"), max_length=128)
    row.request_id = _as_str_or_none(record.get("request_id"), max_length=128)
    row.project_key = _as_str_or_none(record.get("project_key"), max_length=64)
    row.job_id = _as_int_or_none(record.get("job_id"))
    row.export_format = (_as_str_or_none(record.get("export_format"), max_length=32) or "unknown").lower()
    row.outcome = (_as_str_or_none(record.get("outcome"), max_length=32) or "unknown").lower()
    row.integrity_mode = _as_str_or_none(record.get("integrity_mode"), max_length=64)
    row.integrity_trusted = _as_bool(record.get("integrity_trusted"))
    row.actor_id = _as_str_or_none(record.get("actor_id"), max_length=128)
    row.artifact_id = _as_str_or_none(record.get("artifact_id"), max_length=128)
    row.artifact_sha256 = _as_str_or_none(record.get("artifact_sha256"), max_length=64)
    row.filename = _as_str_or_none(record.get("filename"))
    row.content_type = _as_str_or_none(record.get("content_type"), max_length=128)
    row.content_size_bytes = _as_int_or_none(record.get("content_size_bytes"))
    row.error_code = _as_str_or_none(record.get("error_code"), max_length=128)
    row.recorded_at = _parse_recorded_at(record.get("recorded_at"))
    row.payload = dict(record)


def _row_to_record(row: LlmReportExportAuditEvent) -> dict[str, Any]:
    payload = row.payload if isinstance(row.payload, dict) else {}
    return {
        **payload,
        "contract_version": payload.get("contract_version") or "llm_report.export_audit_event.v1",
        "event_type": "llm_report_export",
        "record_source": "export_audit",
        "trace_id": row.trace_id,
        "source_trace_id": row.source_trace_id,
        "request_id": row.request_id,
        "project_key": row.project_key,
        "job_id": row.job_id,
        "export_format": row.export_format,
        "export_outcome": row.outcome,
        "outcome": row.outcome,
        "export_integrity_mode": row.integrity_mode,
        "integrity_mode": row.integrity_mode,
        "export_integrity_trusted": bool(row.integrity_trusted),
        "integrity_trusted": bool(row.integrity_trusted),
        "actor_id": row.actor_id,
        "artifact_id": row.artifact_id,
        "artifact_sha256": row.artifact_sha256,
        "filename": row.filename,
        "content_type": row.content_type,
        "content_size_bytes": row.content_size_bytes,
        "error_code": row.error_code,
        "recorded_at": _parse_recorded_at(row.recorded_at).isoformat(),
    }


def _persist_export_audit_event(record: dict[str, Any]) -> bool:
    def _operation(session):
        row = None
        trace_id = _as_str_or_none(record.get("trace_id"), max_length=128)
        if trace_id:
            row = session.execute(
                select(LlmReportExportAuditEvent).where(LlmReportExportAuditEvent.trace_id == trace_id)
            ).scalar_one_or_none()
        if row is None:
            row = LlmReportExportAuditEvent()
            session.add(row)
        _apply_record_to_row(row, record)
        return True

    try:
        return bool(
            run_with_session_retry(
                _operation,
                log_context={
                    "component": "llm_report_export_audit",
                    "operation": "persist_export_audit_event",
                    "trace_id": record.get("trace_id"),
                },
            )
        )
    except Exception:  # noqa: BLE001
        return False


def _remember_event(record: dict[str, Any]) -> None:
    _LLM_REPORT_EXPORT_AUDIT_EVENTS.append(dict(record))
    if len(_LLM_REPORT_EXPORT_AUDIT_EVENTS) > MAX_EXPORT_AUDIT_MEMORY_RECORDS:
        del _LLM_REPORT_EXPORT_AUDIT_EVENTS[
            : len(_LLM_REPORT_EXPORT_AUDIT_EVENTS) - MAX_EXPORT_AUDIT_MEMORY_RECORDS
        ]


def record_llm_report_export_audit_event(record: dict[str, Any]) -> dict[str, Any]:
    enriched = _normalize_event(record)
    _remember_event(enriched)
    if not _persist_export_audit_event(enriched):
        enriched = {
            **enriched,
            "export_audit_store_degraded": True,
            "audit_store_degraded": True,
            "degraded": True,
            "degraded_reason": "llm_report_export_audit_db_unavailable",
        }
        _LLM_REPORT_EXPORT_AUDIT_EVENTS[-1] = dict(enriched)
    return enriched


def clear_llm_report_export_audit_memory() -> None:
    _LLM_REPORT_EXPORT_AUDIT_EVENTS.clear()


def _event_key(record: dict[str, Any]) -> str:
    trace_id = str(record.get("trace_id") or "").strip()
    if trace_id:
        return f"trace:{trace_id}"
    artifact_id = str(record.get("artifact_id") or "").strip()
    recorded_at = str(record.get("recorded_at") or "").strip()
    return f"artifact:{artifact_id}:{recorded_at}"


def _matches_filters(
    record: dict[str, Any],
    *,
    project_key: str | None,
    actor_id: str | None,
    export_format: str | None,
    outcome: str | None,
) -> bool:
    if project_key and str(record.get("project_key") or "") != project_key:
        return False
    if actor_id and str(record.get("actor_id") or "") != actor_id:
        return False
    if export_format and str(record.get("export_format") or "").strip().lower() != export_format.strip().lower():
        return False
    if outcome and str(record.get("outcome") or "").strip().lower() != outcome.strip().lower():
        return False
    return True


def _load_database_export_audit_events(
    *,
    limit: int,
    project_key: str | None,
    actor_id: str | None,
    export_format: str | None,
    outcome: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    def _operation(session):
        query = select(LlmReportExportAuditEvent)
        if project_key:
            query = query.where(LlmReportExportAuditEvent.project_key == project_key)
        if actor_id:
            query = query.where(LlmReportExportAuditEvent.actor_id == actor_id)
        if export_format:
            query = query.where(LlmReportExportAuditEvent.export_format == export_format.strip().lower())
        if outcome:
            query = query.where(LlmReportExportAuditEvent.outcome == outcome.strip().lower())
        query = query.order_by(
            LlmReportExportAuditEvent.recorded_at.desc(),
            LlmReportExportAuditEvent.id.desc(),
        ).limit(max(1, int(limit)))
        return [_row_to_record(row) for row in session.execute(query).scalars().all()]

    try:
        records = run_with_session_retry(
            _operation,
            log_context={
                "component": "llm_report_export_audit",
                "operation": "load_export_audit_events",
                "project_key": project_key,
                "actor_id": actor_id,
                "export_format": export_format,
                "outcome": outcome,
            },
        )
        return records, False
    except Exception:  # noqa: BLE001
        return [], True


def list_recent_llm_report_export_audit_events(
    limit: int = 10,
    project_key: str | None = None,
    actor_id: str | None = None,
    export_format: str | None = None,
    outcome: str | None = None,
) -> list[dict[str, Any]]:
    safe_limit = max(1, int(limit or 10))
    database_records, database_degraded = _load_database_export_audit_events(
        limit=safe_limit,
        project_key=project_key,
        actor_id=actor_id,
        export_format=export_format,
        outcome=outcome,
    )
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in list(_LLM_REPORT_EXPORT_AUDIT_EVENTS) + database_records:
        if not _matches_filters(
            record,
            project_key=project_key,
            actor_id=actor_id,
            export_format=export_format,
            outcome=outcome,
        ):
            continue
        key = _event_key(record)
        if key in seen:
            continue
        seen.add(key)
        degraded = bool(record.get("audit_store_degraded") or record.get("export_audit_store_degraded")) or database_degraded
        merged.append(
            {
                **record,
                "export_audit_store_degraded": degraded,
                "audit_store_degraded": degraded,
            }
        )
    merged.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
    return merged[:safe_limit]


def _matches_trace(record: dict[str, Any], *, trace_id: str, project_key: str | None) -> bool:
    if project_key and str(record.get("project_key") or "") != project_key:
        return False
    candidates = {
        str(record.get("trace_id") or "").strip(),
        str(record.get("source_trace_id") or "").strip(),
    }
    return trace_id in candidates


def _load_database_export_audit_events_by_trace_id(
    *,
    trace_id: str,
    limit: int,
    project_key: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    def _operation(session):
        query = select(LlmReportExportAuditEvent).where(
            or_(
                LlmReportExportAuditEvent.trace_id == trace_id,
                LlmReportExportAuditEvent.source_trace_id == trace_id,
            )
        )
        if project_key:
            query = query.where(LlmReportExportAuditEvent.project_key == project_key)
        query = query.order_by(
            LlmReportExportAuditEvent.recorded_at.desc(),
            LlmReportExportAuditEvent.id.desc(),
        ).limit(max(1, int(limit)))
        return [_row_to_record(row) for row in session.execute(query).scalars().all()]

    try:
        records = run_with_session_retry(
            _operation,
            log_context={
                "component": "llm_report_export_audit",
                "operation": "load_export_audit_events_by_trace_id",
                "trace_id": trace_id,
                "project_key": project_key,
            },
        )
        return records, False
    except Exception:  # noqa: BLE001
        return [], True


def list_llm_report_export_audit_events_for_trace(
    *,
    trace_id: str,
    project_key: str | None = None,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalized_trace_id = str(trace_id or "").strip()
    safe_limit = max(1, min(int(limit or 10), 100))
    if not normalized_trace_id:
        return [], {
            "contract_version": "llm_report.export_audit_detail_storage.v1",
            "table": "llm_report_export_audit_events",
            "memory_count": len(_LLM_REPORT_EXPORT_AUDIT_EVENTS),
            "database_count": 0,
            "merged_count": 0,
            "degraded": False,
            "degraded_reason": None,
        }

    database_records, database_degraded = _load_database_export_audit_events_by_trace_id(
        trace_id=normalized_trace_id,
        limit=safe_limit,
        project_key=project_key,
    )
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in list(_LLM_REPORT_EXPORT_AUDIT_EVENTS) + database_records:
        if not _matches_trace(record, trace_id=normalized_trace_id, project_key=project_key):
            continue
        key = _event_key(record)
        if key in seen:
            continue
        seen.add(key)
        degraded = bool(record.get("audit_store_degraded") or record.get("export_audit_store_degraded")) or database_degraded
        merged.append(
            {
                **record,
                "export_audit_store_degraded": degraded,
                "audit_store_degraded": degraded,
            }
        )
    merged.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
    return merged[:safe_limit], {
        "contract_version": "llm_report.export_audit_detail_storage.v1",
        "table": "llm_report_export_audit_events",
        "memory_count": len(_LLM_REPORT_EXPORT_AUDIT_EVENTS),
        "database_count": len(database_records),
        "merged_count": len(merged),
        "degraded": database_degraded,
        "database_degraded": database_degraded,
        "degraded_reason": "llm_report_export_audit_db_unavailable" if database_degraded else None,
    }


def summarize_llm_report_export_audit_events(records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    source_records = records if records is not None else list_recent_llm_report_export_audit_events(limit=100)
    by_format: dict[str, int] = {}
    by_outcome: dict[str, int] = {}
    by_integrity_mode: dict[str, int] = {}
    by_project_key: dict[str, int] = {}
    success_count = 0
    blocked_count = 0
    token_invalid_count = 0
    failed_count = 0
    trusted_count = 0
    legacy_count = 0
    degraded_count = 0
    ui_read_only_context_included_count = 0
    total_size_bytes = 0
    for record in source_records:
        export_format = str(record.get("export_format") or "unknown").strip().lower() or "unknown"
        outcome = str(record.get("outcome") or "unknown").strip().lower() or "unknown"
        integrity_mode = str(record.get("integrity_mode") or "unknown").strip().lower() or "unknown"
        project_key = str(record.get("project_key") or "unknown").strip() or "unknown"
        by_format[export_format] = by_format.get(export_format, 0) + 1
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        by_integrity_mode[integrity_mode] = by_integrity_mode.get(integrity_mode, 0) + 1
        by_project_key[project_key] = by_project_key.get(project_key, 0) + 1
        if outcome == "success":
            success_count += 1
        elif outcome == "blocked":
            blocked_count += 1
        elif outcome == "token_invalid":
            token_invalid_count += 1
        elif outcome == "failed":
            failed_count += 1
        if bool(record.get("integrity_trusted")):
            trusted_count += 1
        if integrity_mode == "legacy_payload_gate":
            legacy_count += 1
        if bool(record.get("audit_store_degraded") or record.get("degraded")):
            degraded_count += 1
        if record.get("ui_read_only_context_included") is True:
            ui_read_only_context_included_count += 1
        size = _as_int_or_none(record.get("content_size_bytes"))
        if size is not None and size > 0:
            total_size_bytes += size
    return {
        "contract_version": "llm_report.export_audit_summary.v1",
        "total": len(source_records),
        "success": success_count,
        "blocked": blocked_count,
        "token_invalid": token_invalid_count,
        "failed": failed_count,
        "legacy": legacy_count,
        "trusted": trusted_count,
        "degraded": degraded_count > 0,
        "degraded_count": degraded_count,
        "ui_read_only_context_included_count": ui_read_only_context_included_count,
        "by_format": by_format,
        "by_outcome": by_outcome,
        "by_integrity_mode": by_integrity_mode,
        "by_project_key": by_project_key,
        "total_size_bytes": total_size_bytes,
        "generated_at": _utcnow_iso(),
    }
