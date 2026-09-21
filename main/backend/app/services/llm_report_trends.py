from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import uuid4

from sqlalchemy import select

from ..models.base import run_with_session_retry
from ..models.llm_report_trends import LlmReportQualityTrend
from .job_logger import list_jobs

LLM_REPORT_JOB_TYPE = "llm_report_gen"
MAX_QUALITY_TREND_MEMORY_RECORDS = 200
_LLM_REPORT_QUALITY_TRENDS: list[dict[str, Any]] = []
_UI_READ_ONLY_CONTEXT_SCOPE = "ui_read_only_evidence_context"
_UI_READ_ONLY_CONTEXT_REASON = "reset_telemetry_boundary_context_rendered_as_read_only_export_boundary_note"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_decimal(value: Any) -> Decimal:
    return Decimal(str(_as_float(value)))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pass"}
    return bool(value)


def _as_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_export_format(value: Any) -> str:
    return str(value or "unknown").strip().lower() or "unknown"


def _normalize_export_outcome(value: Any) -> str:
    outcome = str(value or "unknown").strip().lower() or "unknown"
    return outcome if outcome in {"success", "blocked", "token_invalid", "failed"} else outcome


def _ui_read_only_context_fields(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict) or not _as_bool(value.get("ui_read_only_context_included")):
        return {}
    scope = _as_str_or_none(value.get("ui_read_only_context_scope"))
    if scope != _UI_READ_ONLY_CONTEXT_SCOPE:
        return {}
    fields = {
        "ui_read_only_context_included": True,
        "ui_read_only_context_scope": scope,
        "ui_read_only_context_reason": _as_str_or_none(value.get("ui_read_only_context_reason"))
        or _UI_READ_ONLY_CONTEXT_REASON,
    }
    source = _as_str_or_none(value.get("ui_read_only_context_source"))
    if source:
        fields["ui_read_only_context_source"] = source
    return fields


def _export_source_ref(
    *,
    export_format: str,
    integrity: dict[str, Any],
    project_key: str | None,
    request_id: str | None,
    job_id: int | None,
    artifact_id: str | None,
    filename: str | None,
) -> dict[str, Any]:
    source_trace_id = _as_str_or_none(integrity.get("trace_id"))
    normalized_project_key = _as_str_or_none(project_key or integrity.get("project_key"))
    normalized_request_id = _as_str_or_none(request_id or integrity.get("request_id"))
    normalized_job_id = job_id if job_id is not None else integrity.get("job_id")
    normalized_artifact_id = _as_str_or_none(artifact_id or integrity.get("artifact_id"))
    source_ref_id = (
        normalized_artifact_id
        or source_trace_id
        or normalized_request_id
        or (f"{normalized_project_key}:{normalized_job_id}" if normalized_project_key and normalized_job_id else None)
        or f"llm_report_export:{export_format}"
    )
    return {
        "contract_version": "llm_report.export_source_ref.v1",
        "id": source_ref_id,
        "kind": "llm_report_export_artifact",
        "source_trace_id": source_trace_id,
        "request_id": normalized_request_id,
        "project_key": normalized_project_key,
        "job_id": normalized_job_id,
        "artifact_id": normalized_artifact_id,
        "export_format": export_format,
        "filename": filename,
    }


def _export_quality_gate_ref(*, gate: dict[str, Any], export_readiness: dict[str, Any]) -> dict[str, Any]:
    decision = str(gate.get("decision") or export_readiness.get("quality_gate_decision") or "fail").strip().lower()
    return {
        "contract_version": "llm_report.export_quality_gate_ref.v1",
        "decision": decision if decision in {"pass", "warn", "fail"} else "fail",
        "mode": export_readiness.get("quality_gate_mode"),
        "mode_raw": export_readiness.get("quality_gate_mode_raw"),
        "mode_fallback": bool(export_readiness.get("quality_gate_mode_fallback")),
        "strict_gate_blocks_export": bool(export_readiness.get("strict_gate_blocks_export")),
        "hard_failure_count": len(gate.get("hard_failures") if isinstance(gate.get("hard_failures"), list) else []),
        "soft_failure_count": len(gate.get("soft_failures") if isinstance(gate.get("soft_failures"), list) else []),
        "missing_items_count": len(gate.get("missing_items") if isinstance(gate.get("missing_items"), list) else []),
    }


def _export_audit_governance_fields(
    *,
    trace_id: str,
    export_format: str,
    outcome: str,
    gate: dict[str, Any],
    export_readiness: dict[str, Any],
    integrity: dict[str, Any],
    source_ref: dict[str, Any],
    content_type: str | None,
    error_code: str | None,
    ui_read_only_context_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality_gate = _export_quality_gate_ref(gate=gate, export_readiness=export_readiness)
    readiness = str(export_readiness.get("readiness") or "unknown").strip().lower() or "unknown"
    ui_read_only_context_fields = _ui_read_only_context_fields(ui_read_only_context_trace)
    audit_event = {
        "contract_version": "llm_report.export_audit_event_ref.v1",
        "type": "llm_report_export",
        "trace_id": trace_id,
        "source_trace_id": source_ref.get("source_trace_id"),
        "outcome": outcome,
        "error_code": error_code,
        "strict_gate_blocked": bool(quality_gate.get("strict_gate_blocks_export")) and outcome == "blocked",
        "compatible_quality_gate_path": quality_gate.get("mode") in {"off", "warn"} and outcome == "success",
        "token_invalid": outcome == "token_invalid",
        **ui_read_only_context_fields,
    }
    governance = {
        "contract_version": "llm_report.export_governance.v1",
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
        "integrity": {
            "mode": integrity.get("mode"),
            "trusted": bool(integrity.get("trusted")),
            "actor_id": integrity.get("actor_id"),
            "actor_source": integrity.get("actor_source"),
            "actor_trusted": bool(integrity.get("actor_trusted")),
            "actor_auth_mode": integrity.get("actor_auth_mode"),
        },
    }
    if ui_read_only_context_fields:
        governance["ui_read_only_context"] = ui_read_only_context_fields
    header_snapshot = {
        "contract_version": "llm_report.export_header_snapshot.v1",
        "format": export_format,
        "readiness": readiness,
        "quality_gate_decision": quality_gate.get("decision"),
        "quality_gate_mode": quality_gate.get("mode"),
        "source_ref": source_ref.get("id"),
        "source_trace_id": source_ref.get("source_trace_id"),
        "project_key": source_ref.get("project_key"),
        "job_id": source_ref.get("job_id"),
        "content_type": content_type,
    }
    return {
        "source_ref": source_ref,
        "quality_gate": quality_gate,
        "audit_event": audit_event,
        "governance": governance,
        "header_snapshot": header_snapshot,
        "export_header_snapshot": header_snapshot,
    }


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


def build_quality_trend_metric(
    *,
    gate: dict[str, Any],
    quality_gate_metrics: dict[str, Any],
    gate_mode: str,
    gate_mode_raw: str,
    gate_mode_fallback: bool,
    trace_id: str,
    request_id: str | None,
    project_key: str | None,
    source_count_requested: int,
    source_count_resolved: int,
    export_readiness: dict[str, Any],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=llm.report_quality_gate witness=test:test_w01_meta",
]:
    missing_items = gate.get("missing_items") if isinstance(gate.get("missing_items"), list) else []
    hard_failures = gate.get("hard_failures") if isinstance(gate.get("hard_failures"), list) else []
    soft_failures = gate.get("soft_failures") if isinstance(gate.get("soft_failures"), list) else []
    return {
        "contract_version": "llm_report.quality_trend_metric.v1",
        "trace_id": trace_id,
        "request_id": request_id,
        "project_key": project_key,
        "decision": str(quality_gate_metrics.get("decision") or gate.get("decision") or "fail"),
        "pass": bool(quality_gate_metrics.get("pass", False)),
        "gate_mode": gate_mode,
        "gate_mode_raw": gate_mode_raw,
        "gate_mode_fallback": gate_mode_fallback,
        "citation_coverage": float(quality_gate_metrics.get("citation_coverage") or 0.0),
        "evidence_coverage": float(quality_gate_metrics.get("evidence_coverage") or 0.0),
        "source_count": int(quality_gate_metrics.get("source_count") or 0),
        "source_count_requested": source_count_requested,
        "source_count_resolved": source_count_resolved,
        "missing_items_count": len(missing_items),
        "hard_failure_count": len(hard_failures),
        "soft_failure_count": len(soft_failures),
        "hard_failures": hard_failures,
        "soft_failures": soft_failures,
        "readiness": export_readiness["readiness"],
        "next_action": export_readiness["next_action"],
    }


def build_export_trend_metric(
    *,
    export_format: str,
    outcome: str,
    gate: dict[str, Any],
    export_readiness: dict[str, Any],
    integrity: dict[str, Any],
    project_key: str | None,
    request_id: str | None,
    job_id: int | None,
    artifact_id: str | None,
    artifact_sha256: str | None,
    filename: str | None,
    content_type: str | None,
    content_size_bytes: int | None = None,
    error_code: str | None = None,
    ui_read_only_context_trace: dict[str, Any] | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence fact_source=llm.report_export witness=test:test_w01_meta",
]:
    normalized_format = _normalize_export_format(export_format)
    normalized_outcome = _normalize_export_outcome(outcome)
    base_trace = str(integrity.get("trace_id") or artifact_id or "export").strip()[:72] or "export"
    trace_id = f"{base_trace}:export:{uuid4().hex[:12]}"[:128]
    hard_failures = gate.get("hard_failures") if isinstance(gate.get("hard_failures"), list) else []
    soft_failures = gate.get("soft_failures") if isinstance(gate.get("soft_failures"), list) else []
    missing_items = gate.get("missing_items") if isinstance(gate.get("missing_items"), list) else []
    decision = str(gate.get("decision") or export_readiness.get("quality_gate_decision") or "fail").strip().lower()
    source_ref = _export_source_ref(
        export_format=normalized_format,
        integrity=integrity,
        project_key=project_key,
        request_id=request_id,
        job_id=job_id,
        artifact_id=artifact_id,
        filename=filename,
    )
    governance_fields = _export_audit_governance_fields(
        trace_id=trace_id,
        export_format=normalized_format,
        outcome=normalized_outcome,
        gate=gate,
        export_readiness=export_readiness,
        integrity=integrity,
        source_ref=source_ref,
        content_type=content_type,
        error_code=error_code,
        ui_read_only_context_trace=ui_read_only_context_trace,
    )
    ui_read_only_context_fields = _ui_read_only_context_fields(ui_read_only_context_trace)
    return {
        "contract_version": "llm_report.export_trend_metric.v1",
        "event_type": "llm_report_export",
        "trace_id": trace_id,
        "source_trace_id": integrity.get("trace_id"),
        "request_id": request_id or integrity.get("request_id"),
        "project_key": project_key or integrity.get("project_key"),
        "job_id": job_id or integrity.get("job_id"),
        "decision": decision if decision in {"pass", "warn", "fail"} else "fail",
        "pass": decision == "pass",
        "gate_mode": export_readiness.get("quality_gate_mode"),
        "gate_mode_raw": export_readiness.get("quality_gate_mode_raw"),
        "gate_mode_fallback": bool(export_readiness.get("quality_gate_mode_fallback")),
        "citation_coverage": 0.0,
        "evidence_coverage": 0.0,
        "source_count": 0,
        "source_count_requested": 0,
        "source_count_resolved": 0,
        "missing_items_count": len(missing_items),
        "hard_failure_count": len(hard_failures),
        "soft_failure_count": len(soft_failures),
        "hard_failures": hard_failures,
        "soft_failures": soft_failures,
        "readiness": export_readiness.get("readiness") or "unknown",
        "next_action": export_readiness.get("next_action"),
        "export_format": normalized_format,
        "export_outcome": normalized_outcome,
        "export_integrity_mode": integrity.get("mode"),
        "export_integrity_trusted": bool(integrity.get("trusted")),
        "actor_id": integrity.get("actor_id"),
        "artifact_id": artifact_id or integrity.get("artifact_id"),
        "artifact_sha256": artifact_sha256 or integrity.get("markdown_sha256"),
        "filename": filename,
        "content_type": content_type,
        "content_size_bytes": content_size_bytes,
        "error_code": error_code,
        **ui_read_only_context_fields,
        **governance_fields,
    }


def _apply_record_to_row(row: LlmReportQualityTrend, record: dict[str, Any]) -> None:
    row.trace_id = _as_str_or_none(record.get("trace_id"))
    row.request_id = _as_str_or_none(record.get("request_id"))
    row.project_key = _as_str_or_none(record.get("project_key"))
    row.job_id = _as_int(record.get("job_id")) if record.get("job_id") is not None else None
    row.job_status = _as_str_or_none(record.get("job_status"))
    row.topic = _as_str_or_none(record.get("topic"))
    row.decision = str(record.get("decision") or "fail").strip().lower() or "fail"
    row.passed = _as_bool(record.get("pass"))
    row.gate_mode = _as_str_or_none(record.get("gate_mode"))
    row.gate_mode_raw = _as_str_or_none(record.get("gate_mode_raw"))
    row.gate_mode_fallback = _as_bool(record.get("gate_mode_fallback"))
    row.citation_coverage = _as_decimal(record.get("citation_coverage"))
    row.evidence_coverage = _as_decimal(record.get("evidence_coverage"))
    row.source_count = _as_int(record.get("source_count"))
    row.source_count_requested = _as_int(record.get("source_count_requested"))
    row.source_count_resolved = _as_int(record.get("source_count_resolved"))
    row.missing_items_count = _as_int(record.get("missing_items_count"))
    row.hard_failure_count = _as_int(record.get("hard_failure_count"))
    row.soft_failure_count = _as_int(record.get("soft_failure_count"))
    row.readiness = _as_str_or_none(record.get("readiness"))
    row.next_action = _as_str_or_none(record.get("next_action"))
    row.record_source = str(record.get("record_source") or "generate").strip() or "generate"
    row.recorded_at = _parse_recorded_at(record.get("recorded_at"))
    row.payload = dict(record)


def _persist_quality_trend(record: dict[str, Any]) -> bool:
    def _operation(session):
        row = None
        trace_id = _as_str_or_none(record.get("trace_id"))
        if trace_id:
            row = session.execute(
                select(LlmReportQualityTrend).where(LlmReportQualityTrend.trace_id == trace_id)
            ).scalar_one_or_none()
        if row is None:
            row = LlmReportQualityTrend()
            session.add(row)
        _apply_record_to_row(row, record)
        return True

    try:
        return bool(
            run_with_session_retry(
                _operation,
                log_context={
                    "component": "llm_report_quality_trends",
                    "operation": "persist_quality_trend",
                    "trace_id": record.get("trace_id"),
                },
            )
        )
    except Exception:  # noqa: BLE001
        return False


def record_quality_trend_metric(
    record: dict[str, Any],
    *,
    job_id: int | None,
    topic: str,
    job_status: str,
    source: str = "generate",
) -> dict[str, Any]:
    enriched = {
        **record,
        "job_id": job_id,
        "job_status": job_status,
        "topic": topic,
        "recorded_at": _utcnow_iso(),
        "record_source": source,
    }
    _LLM_REPORT_QUALITY_TRENDS.append(enriched)
    if len(_LLM_REPORT_QUALITY_TRENDS) > MAX_QUALITY_TREND_MEMORY_RECORDS:
        del _LLM_REPORT_QUALITY_TRENDS[: len(_LLM_REPORT_QUALITY_TRENDS) - MAX_QUALITY_TREND_MEMORY_RECORDS]
    if not _persist_quality_trend(enriched):
        enriched["trend_store_degraded"] = True
    return enriched


def clear_quality_trend_memory() -> None:
    _LLM_REPORT_QUALITY_TRENDS.clear()


def _quality_trend_key(record: dict[str, Any]) -> str:
    trace_id = str(record.get("trace_id") or "").strip()
    if trace_id:
        return f"trace:{trace_id}"
    job_id = str(record.get("job_id") or "").strip()
    recorded_at = str(record.get("recorded_at") or "").strip()
    return f"job:{job_id}:{recorded_at}"


def _trend_model_to_record(row: LlmReportQualityTrend) -> dict[str, Any]:
    payload = row.payload if isinstance(row.payload, dict) else {}
    return {
        **payload,
        "contract_version": payload.get("contract_version") or "llm_report.quality_trend_metric.v1",
        "trace_id": row.trace_id,
        "request_id": row.request_id,
        "project_key": row.project_key,
        "job_id": row.job_id,
        "job_status": row.job_status,
        "topic": row.topic,
        "decision": row.decision,
        "pass": bool(row.passed),
        "gate_mode": row.gate_mode,
        "gate_mode_raw": row.gate_mode_raw,
        "gate_mode_fallback": bool(row.gate_mode_fallback),
        "citation_coverage": _as_float(row.citation_coverage),
        "evidence_coverage": _as_float(row.evidence_coverage),
        "source_count": _as_int(row.source_count),
        "source_count_requested": _as_int(row.source_count_requested),
        "source_count_resolved": _as_int(row.source_count_resolved),
        "missing_items_count": _as_int(row.missing_items_count),
        "hard_failure_count": _as_int(row.hard_failure_count),
        "soft_failure_count": _as_int(row.soft_failure_count),
        "readiness": row.readiness,
        "next_action": row.next_action,
        "record_source": row.record_source or "trend_table",
        "recorded_at": _parse_recorded_at(row.recorded_at).isoformat(),
    }


def _load_database_quality_trends(
    *,
    limit: int,
    project_key: str | None = None,
    decision: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    def _operation(session):
        query = select(LlmReportQualityTrend)
        if project_key:
            query = query.where(LlmReportQualityTrend.project_key == project_key)
        if decision:
            query = query.where(LlmReportQualityTrend.decision == decision.strip().lower())
        query = query.order_by(LlmReportQualityTrend.recorded_at.desc(), LlmReportQualityTrend.id.desc()).limit(
            max(1, int(limit))
        )
        return [_trend_model_to_record(row) for row in session.execute(query).scalars().all()]

    try:
        records = run_with_session_retry(
            _operation,
            log_context={
                "component": "llm_report_quality_trends",
                "operation": "load_quality_trends",
                "project_key": project_key,
                "decision": decision,
            },
        )
        return records, False
    except Exception:  # noqa: BLE001
        return [], True


def _load_persisted_quality_trends(limit: int) -> tuple[list[dict[str, Any]], bool]:
    try:
        jobs = list_jobs(limit=min(max(limit * 4, 20), 300))
    except Exception:  # noqa: BLE001
        return [], True
    records: list[dict[str, Any]] = []
    for job in jobs:
        if str(job.get("job_type") or "") != LLM_REPORT_JOB_TYPE:
            continue
        params = job.get("params") if isinstance(job.get("params"), dict) else {}
        trend = params.get("report_quality_trend_metric") or params.get("quality_gate_trend_record")
        if not isinstance(trend, dict):
            continue
        records.append(
            {
                **trend,
                "job_id": job.get("id"),
                "topic": params.get("topic"),
                "recorded_at": job.get("finished_at") or job.get("started_at"),
                "record_source": "job_log",
                "job_status": job.get("status"),
            }
        )
        if len(records) >= limit:
            break
    return records, False


def _first_mapping(*values: Any) -> dict[str, Any] | None:
    for value in values:
        if isinstance(value, dict):
            return dict(value)
    return None


def _first_list(*values: Any) -> list[Any] | None:
    for value in values:
        if isinstance(value, list):
            return list(value)
    return None


def _job_context_from_params(params: dict[str, Any]) -> dict[str, Any]:
    export_contract = params.get("export_contract") if isinstance(params.get("export_contract"), dict) else {}
    report = params.get("report") if isinstance(params.get("report"), dict) else {}
    quality_gate = _first_mapping(params.get("quality_gate"), params.get("report_quality_gate"))
    export_artifact = _first_mapping(
        params.get("export_artifact"),
        params.get("artifact"),
        export_contract.get("artifact") if isinstance(export_contract, dict) else None,
    )
    source_refs = _first_list(
        params.get("source_refs"),
        params.get("sources"),
        report.get("sources") if isinstance(report, dict) else None,
    )
    source_query = _first_mapping(params.get("source_query"), params.get("query"), params.get("source_request"))
    repair_context = _first_mapping(
        params.get("repair_context"),
        params.get("quality_repair_context"),
        params.get("report_repair_context"),
    )
    context: dict[str, Any] = {
        "contract_version": "llm_report.quality_detail_job_context.v1",
        "source_refs": source_refs or [],
        "source_query": source_query or {},
        "report_artifact": export_artifact or {},
        "quality_gate": quality_gate or {},
        "quality_gate_metrics": _first_mapping(params.get("quality_gate_metrics")),
        "export_readiness": _first_mapping(params.get("export_readiness")),
        "repair_context": repair_context or {},
    }
    if report:
        sections = report.get("sections") if isinstance(report.get("sections"), list) else []
        sources = report.get("sources") if isinstance(report.get("sources"), list) else []
        context["report_summary"] = {
            "topic": report.get("topic"),
            "template_version": report.get("template_version"),
            "generated_at": report.get("generated_at"),
            "section_count": len(sections),
            "source_count": len(sources),
        }
    return context


def _job_trace_candidates(job: dict[str, Any]) -> set[str]:
    params = job.get("params") if isinstance(job.get("params"), dict) else {}
    candidates = {
        str(params.get("trace_id") or "").strip(),
        str((params.get("observability") or {}).get("trace_id") if isinstance(params.get("observability"), dict) else "").strip(),
    }
    for key in ("report_quality_trend_metric", "quality_gate_trend_record"):
        trend = params.get(key)
        if isinstance(trend, dict):
            candidates.add(str(trend.get("trace_id") or "").strip())
            candidates.add(str(trend.get("source_trace_id") or "").strip())
    return {candidate for candidate in candidates if candidate}


def _job_quality_record(job: dict[str, Any]) -> dict[str, Any] | None:
    params = job.get("params") if isinstance(job.get("params"), dict) else {}
    trend = params.get("report_quality_trend_metric") or params.get("quality_gate_trend_record")
    if not isinstance(trend, dict):
        return None
    return {
        **trend,
        "job_id": job.get("id"),
        "topic": params.get("topic"),
        "recorded_at": job.get("finished_at") or job.get("started_at"),
        "record_source": "job_log",
        "job_status": job.get("status"),
        "job_context": _job_context_from_params(params),
    }


def _load_persisted_quality_trends_for_trace_ids(
    *,
    trace_ids: set[str],
    limit: int,
    project_key: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    try:
        jobs = list_jobs(limit=min(max(limit * 12, 100), 500))
    except Exception:  # noqa: BLE001
        return [], True
    records: list[dict[str, Any]] = []
    for job in jobs:
        if str(job.get("job_type") or "") != LLM_REPORT_JOB_TYPE:
            continue
        if not (_job_trace_candidates(job) & trace_ids):
            continue
        record = _job_quality_record(job)
        if not record:
            continue
        if project_key and str(record.get("project_key") or "") != project_key:
            continue
        records.append(record)
        if len(records) >= limit:
            break
    return records, False


def _load_database_quality_trends_for_trace_ids(
    *,
    trace_ids: set[str],
    limit: int,
    project_key: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    def _operation(session):
        query = select(LlmReportQualityTrend).where(LlmReportQualityTrend.trace_id.in_(trace_ids))
        if project_key:
            query = query.where(LlmReportQualityTrend.project_key == project_key)
        query = query.order_by(LlmReportQualityTrend.recorded_at.desc(), LlmReportQualityTrend.id.desc()).limit(
            max(1, int(limit))
        )
        return [_trend_model_to_record(row) for row in session.execute(query).scalars().all()]

    try:
        records = run_with_session_retry(
            _operation,
            log_context={
                "component": "llm_report_quality_trends",
                "operation": "load_quality_trends_for_trace_ids",
                "trace_ids": sorted(trace_ids),
                "project_key": project_key,
            },
        )
        return records, False
    except Exception:  # noqa: BLE001
        return [], True


def list_quality_trend_records_for_trace_ids(
    *,
    trace_ids: list[str],
    limit: int = 10,
    project_key: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalized_trace_ids = {str(trace_id or "").strip() for trace_id in trace_ids if str(trace_id or "").strip()}
    safe_limit = max(1, min(int(limit or 10), 100))
    if not normalized_trace_ids:
        return [], {
            "contract_version": "llm_report.quality_detail_storage.v1",
            "table": "llm_report_quality_trends",
            "memory_count": len(_LLM_REPORT_QUALITY_TRENDS),
            "database_count": 0,
            "job_log_count": 0,
            "merged_count": 0,
            "degraded": False,
            "degraded_reason": None,
        }

    database_records, database_degraded = _load_database_quality_trends_for_trace_ids(
        trace_ids=normalized_trace_ids,
        limit=safe_limit,
        project_key=project_key,
    )
    persisted_records, persisted_degraded = _load_persisted_quality_trends_for_trace_ids(
        trace_ids=normalized_trace_ids,
        limit=safe_limit,
        project_key=project_key,
    )
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in list(_LLM_REPORT_QUALITY_TRENDS) + database_records + persisted_records:
        record_trace_id = str(record.get("trace_id") or "").strip()
        source_trace_id = str(record.get("source_trace_id") or "").strip()
        if record_trace_id not in normalized_trace_ids and source_trace_id not in normalized_trace_ids:
            continue
        if project_key and str(record.get("project_key") or "") != project_key:
            continue
        key = _quality_trend_key(record)
        if key in seen:
            continue
        seen.add(key)
        merged.append(record)
    merged.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
    degraded = database_degraded or persisted_degraded or any(bool(record.get("trend_store_degraded")) for record in merged)
    return merged[:safe_limit], {
        "contract_version": "llm_report.quality_detail_storage.v1",
        "table": "llm_report_quality_trends",
        "memory_count": len(_LLM_REPORT_QUALITY_TRENDS),
        "database_count": len(database_records),
        "job_log_count": len(persisted_records),
        "merged_count": len(merged),
        "degraded": degraded,
        "database_degraded": database_degraded,
        "job_log_degraded": persisted_degraded,
        "degraded_reason": "llm_report_quality_detail_storage_degraded" if degraded else None,
    }


def summarize_quality_trends(records: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = {"pass": 0, "warn": 0, "fail": 0}
    readiness: dict[str, int] = {}
    project_keys: dict[str, int] = {}
    export_events = {
        "total": 0,
        "success": 0,
        "blocked": 0,
        "token_invalid": 0,
        "failed": 0,
        "legacy": 0,
        "trusted": 0,
        "ui_read_only_context_included_count": 0,
        "by_format": {},
        "by_integrity_mode": {},
    }
    citation_values: list[float] = []
    evidence_values: list[float] = []
    for record in records:
        decision = str(record.get("decision") or "fail").strip().lower()
        decisions[decision if decision in decisions else "fail"] += 1
        readiness_key = str(record.get("readiness") or "unknown").strip().lower() or "unknown"
        readiness[readiness_key] = readiness.get(readiness_key, 0) + 1
        project_key = str(record.get("project_key") or "unknown").strip() or "unknown"
        project_keys[project_key] = project_keys.get(project_key, 0) + 1
        if str(record.get("event_type") or "").strip().lower() == "llm_report_export" or str(
            record.get("record_source") or ""
        ).strip().lower() == "export":
            export_events["total"] += 1
            export_format = str(record.get("export_format") or "unknown").strip().lower() or "unknown"
            outcome = str(record.get("export_outcome") or record.get("outcome") or "unknown").strip().lower()
            integrity_mode = str(record.get("export_integrity_mode") or record.get("integrity_mode") or "unknown").strip().lower()
            export_events["by_format"][export_format] = export_events["by_format"].get(export_format, 0) + 1
            export_events["by_integrity_mode"][integrity_mode] = (
                export_events["by_integrity_mode"].get(integrity_mode, 0) + 1
            )
            if outcome in {"success", "blocked", "token_invalid", "failed"}:
                export_events[outcome] += 1
            else:
                export_events["failed"] += 1
            if integrity_mode == "legacy_payload_gate":
                export_events["legacy"] += 1
            if bool(record.get("export_integrity_trusted") or record.get("integrity_trusted")):
                export_events["trusted"] += 1
            if record.get("ui_read_only_context_included") is True:
                export_events["ui_read_only_context_included_count"] += 1
        try:
            citation_values.append(float(record.get("citation_coverage") or 0.0))
        except (TypeError, ValueError):
            pass
        try:
            evidence_values.append(float(record.get("evidence_coverage") or 0.0))
        except (TypeError, ValueError):
            pass
    return {
        "total": len(records),
        "decisions": decisions,
        "by_decision": decisions,
        "readiness": readiness,
        "project_keys": project_keys,
        "export_events": export_events,
        "avg_citation_coverage": sum(citation_values) / len(citation_values) if citation_values else 0.0,
        "avg_evidence_coverage": sum(evidence_values) / len(evidence_values) if evidence_values else 0.0,
    }


def list_quality_trend_records(
    *,
    limit: int,
    project_key: str | None = None,
    decision: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    database_records, database_degraded = _load_database_quality_trends(
        limit=limit,
        project_key=project_key,
        decision=decision,
    )
    persisted_records, persisted_degraded = _load_persisted_quality_trends(limit)
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in list(_LLM_REPORT_QUALITY_TRENDS) + database_records + persisted_records:
        key = _quality_trend_key(record)
        if key in seen:
            continue
        seen.add(key)
        merged.append(record)
    if project_key:
        merged = [record for record in merged if str(record.get("project_key") or "") == project_key]
    if decision:
        normalized_decision = decision.strip().lower()
        merged = [record for record in merged if str(record.get("decision") or "").strip().lower() == normalized_decision]
    merged.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
    records = merged[:limit]
    storage = {
        "contract_version": "llm_report.quality_trend_storage.v1",
        "memory_count": len(_LLM_REPORT_QUALITY_TRENDS),
        "persisted_count": len(database_records) + len(persisted_records),
        "persisted_degraded": database_degraded or persisted_degraded,
        "database_count": len(database_records),
        "database_degraded": database_degraded,
        "job_log_count": len(persisted_records),
        "job_log_degraded": persisted_degraded,
        "merged_count": len(merged),
    }
    return records, storage
