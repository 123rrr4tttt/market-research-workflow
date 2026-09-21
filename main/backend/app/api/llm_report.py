from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from ..contracts import ErrorCode, error_response
from ..contracts.responses import ok
from ..services.job_logger import complete_job, fail_job, start_job
from ..services.llm.config_loader import get_llm_config
from ..services.llm.platformization import (
    build_trace_audit_record,
    evaluate_agent_permission_boundary,
    normalize_agent_role,
    resolve_consumer_adapter_boundary,
    resolve_request_identity,
    resolve_routing_decision,
)
from ..services.llm_report_generator import (
    build_report_capability_truth,
    build_structured_report,
    evaluate_report_gate,
    export_quality_gate_metrics,
    render_markdown,
)
from ..services.llm_report_export import (
    LlmReportExportTokenError,
    build_llm_report_export_artifact,
    export_gate_from_token_payload,
    render_markdown_export,
    verify_llm_report_export_token,
)
from ..services.llm_report_export_audit import record_llm_report_export_audit_event
from ..services.llm_report_export_token_state import claim_llm_report_export_token_use
from ..services.llm_report_source_enrichment import resolve_report_sources
from ..services.llm_report_trends import (
    build_export_trend_metric,
    build_quality_trend_metric,
    list_quality_trend_records,
    record_quality_trend_metric,
    summarize_quality_trends,
)
from ..services.request_identity import RequestActorContext, resolve_request_actor_context
from ..settings.config import settings


router = APIRouter(prefix="/llm-report", tags=["llm-report"])
_LLM_REPORT_JOB_TYPE = "llm_report_gen"
_VALID_GATE_MODES = {"off", "warn", "strict"}
_UI_READ_ONLY_CONTEXT_SCOPE = "ui_read_only_evidence_context"
_UI_READ_ONLY_CONTEXT_REASON = "reset_telemetry_boundary_context_rendered_as_read_only_export_boundary_note"


class SourceInput(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    title: str = Field(..., min_length=1, max_length=300)
    url: AnyHttpUrl
    publisher: str | None = Field(default=None, max_length=120)
    published_at: str | None = Field(default=None, max_length=64)
    retrieved_at: str | None = Field(default=None, max_length=64)
    evidence: str | None = Field(default=None, max_length=2000)


class GenerateReportRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    section_titles: list[str] = Field(default_factory=list, max_length=12)
    sources: list[SourceInput] = Field(default_factory=list, max_length=100)

    @field_validator("topic")
    @classmethod
    def _topic_must_not_be_blank(cls, value: str) -> str:
        if not str(value or "").strip():
            raise ValueError("topic cannot be blank")
        return value

    @field_validator("section_titles")
    @classmethod
    def _section_titles_must_be_valid(cls, value: list[str]) -> list[str]:
        for idx, item in enumerate(value, start=1):
            title = str(item or "").strip()
            if not title:
                raise ValueError(f"section_titles[{idx}] cannot be blank")
            if len(title) > 120:
                raise ValueError(f"section_titles[{idx}] exceeds max length 120")
        return value


class ExportMarkdownRequest(BaseModel):
    markdown: str = Field(..., min_length=1, max_length=2_000_000)
    quality_gate: dict[str, Any] = Field(default_factory=dict)
    quality_gate_mode: str | None = Field(default=None, max_length=24)
    filename: str | None = Field(default=None, max_length=180)
    project_key: str | None = Field(default=None, max_length=64)
    artifact_token: str | None = Field(default=None, max_length=12000)
    artifact_sha256: str | None = Field(default=None, max_length=128)
    reset_telemetry_boundary_context: dict[str, Any] | None = Field(default=None)

    @field_validator("markdown")
    @classmethod
    def _markdown_must_not_be_blank(cls, value: str) -> str:
        if not str(value or "").strip():
            raise ValueError("markdown cannot be blank")
        return value


def _resolve_gate_mode(raw_mode: str | None) -> tuple[str, str, bool]:
    normalized_raw_mode = str(raw_mode or "").strip().lower()
    if not normalized_raw_mode:
        return "strict", "strict", False
    if normalized_raw_mode == "compatible":
        return "warn", "compatible", False
    if normalized_raw_mode in _VALID_GATE_MODES:
        return normalized_raw_mode, normalized_raw_mode, False
    return "strict", normalized_raw_mode, True


def _safe_export_filename(value: str | None, *, extension: str = "md") -> str:
    suffix = str(extension or "md").strip().lower().lstrip(".") or "md"
    raw = str(value or "").strip() or f"llm-report.{suffix}"
    raw = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip(".-")
    if not raw:
        raw = f"llm-report.{suffix}"
    raw = re.sub(r"\.(md|pdf|docx)$", "", raw, flags=re.IGNORECASE).strip(".-") or "llm-report"
    if not raw.lower().endswith(f".{suffix}"):
        raw = f"{raw}.{suffix}"
    return raw[:180]


def _resolve_auto_source_target_count(raw_value: int | None) -> int:
    try:
        value = int(raw_value or 0)
    except Exception:  # noqa: BLE001
        value = 0
    if value <= 0:
        return 6
    return min(value, 20)


def _normalize_quality_gate_for_export(value: dict[str, Any] | None) -> dict[str, Any]:
    gate = dict(value or {})
    decision = str(gate.get("decision") or "fail").strip().lower()
    if decision not in {"pass", "warn", "fail"}:
        decision = "fail"
    gate["decision"] = decision
    for key in ("hard_failures", "soft_failures", "missing_items"):
        if not isinstance(gate.get(key), list):
            gate[key] = []
    return gate


def _resolve_ui_read_only_context_trace(
    payload: ExportMarkdownRequest,
    *,
    export_format: str,
    outcome: str,
) -> dict[str, Any]:
    if outcome != "success" or str(export_format or "").strip().lower() not in {"pdf", "docx"}:
        return {}
    context = payload.reset_telemetry_boundary_context
    if not isinstance(context, dict):
        return {}
    scope = str(context.get("scope") or "").strip()
    if scope != _UI_READ_ONLY_CONTEXT_SCOPE:
        return {}
    source = str(context.get("source") or "").strip()
    trace = {
        "ui_read_only_context_included": True,
        "ui_read_only_context_scope": scope,
        "ui_read_only_context_reason": _UI_READ_ONLY_CONTEXT_REASON,
    }
    if source:
        trace["ui_read_only_context_source"] = source
    return trace


def _request_actor_id(request: Request | None) -> str:
    return resolve_request_actor_context(request).actor_id


def _request_actor_context(request: Request | None) -> RequestActorContext:
    return resolve_request_actor_context(request)


def _resolve_export_gate_context(
    payload: ExportMarkdownRequest,
    *,
    export_format: str,
    request: Request | None = None,
) -> tuple[dict[str, Any], str, str, bool, dict[str, Any] | None, dict[str, Any]]:
    actor_context = _request_actor_context(request)
    actor_observability = actor_context.to_observability()
    if payload.artifact_token:
        try:
            token_payload = verify_llm_report_export_token(
                payload.artifact_token,
                markdown=payload.markdown,
                token_secret=settings.llm_report_export_token_secret,
                actor_id=actor_context.actor_id,
                enforce_one_time_use=bool(getattr(settings, "llm_report_export_one_time_use_enabled", True)),
            )
        except LlmReportExportTokenError as exc:
            integrity = {
                "contract_version": "llm_report.export_integrity.v1",
                "mode": "artifact_token",
                "trusted": False,
                "gate_source": "server_signed_artifact_token",
                "error_code": "LLM_REPORT_EXPORT_TOKEN_INVALID",
                "error_reason": str(exc),
                **actor_observability,
            }
            export_readiness = {
                "contract_version": "llm_report.export_readiness.v1",
                "format": export_format,
                "readiness": "blocked",
                "quality_gate_decision": "fail",
                "quality_gate_mode": "strict",
                "quality_gate_mode_raw": "strict",
                "quality_gate_mode_fallback": False,
                "strict_gate_blocks_export": True,
                "export_allowed": False,
                "file_exportable": False,
                "content_type": "application/octet-stream",
                "next_action": "regenerate_report_before_export",
            }
            _record_export_audit_event(
                payload=payload,
                export_format=export_format,
                outcome="token_invalid",
                gate={"decision": "fail", "hard_failures": ["invalid_export_token"], "soft_failures": []},
                export_readiness=export_readiness,
                integrity=integrity,
                token_payload=None,
                filename=_safe_export_filename(payload.filename, extension=export_format),
                content_type=None,
                error_code="LLM_REPORT_EXPORT_TOKEN_INVALID",
            )
            _raise_http_error(
                403,
                ErrorCode.INVALID_INPUT,
                "invalid llm report export token",
                details={
                    "error_code": "LLM_REPORT_EXPORT_TOKEN_INVALID",
                    "reason": str(exc),
                    "next_action": "regenerate_report_before_export",
                },
            )
        gate = _normalize_quality_gate_for_export(export_gate_from_token_payload(token_payload))
        gate_mode, gate_mode_raw, gate_mode_fallback = _resolve_gate_mode(str(token_payload.get("gate_mode") or "strict"))
        integrity = {
            "contract_version": "llm_report.export_integrity.v1",
            "mode": "artifact_token",
            "trusted": True,
            "artifact_id": token_payload.get("artifact_id"),
            "markdown_sha256": token_payload.get("markdown_sha256"),
            "trace_id": token_payload.get("trace_id"),
            "request_id": token_payload.get("request_id"),
            "project_key": token_payload.get("project_key"),
            "job_id": token_payload.get("job_id"),
            "actor_id": token_payload.get("actor_id"),
            "actor_source": actor_context.actor_source,
            "actor_trusted": actor_context.actor_trusted,
            "actor_auth_mode": actor_context.actor_auth_mode,
            "legacy_actor_id": actor_context.legacy_actor_id,
            "expires_at": token_payload.get("expires_at"),
            "one_time_use": bool(token_payload.get("one_time_use", True)),
            "gate_source": "server_signed_artifact_token",
            "client_gate_ignored": bool(payload.quality_gate),
            "client_gate_mode_ignored": bool(payload.quality_gate_mode),
        }
        return gate, gate_mode, gate_mode_raw, gate_mode_fallback, token_payload, integrity

    if settings.llm_report_export_require_artifact_token:
        gate = _normalize_quality_gate_for_export(
            {
                "decision": "fail",
                "hard_failures": ["missing_export_artifact_token"],
                "soft_failures": [],
                "missing_items": ["artifact_token"],
            }
        )
        integrity = {
            "contract_version": "llm_report.export_integrity.v1",
            "mode": "legacy_payload_gate_blocked",
            "trusted": False,
            "gate_source": "server_fail_closed_missing_artifact_token",
            "error_code": "LLM_REPORT_EXPORT_TOKEN_REQUIRED",
            "next_action": "regenerate_report_to_receive_signed_export_artifact",
            "client_gate_ignored": bool(payload.quality_gate),
            "client_gate_mode_ignored": bool(payload.quality_gate_mode),
            **actor_observability,
        }
        export_readiness = {
            "contract_version": "llm_report.export_readiness.v1",
            "format": export_format,
            "supported_formats": ["markdown", "pdf", "docx"],
            "markdown_exportable": bool(payload.markdown),
            "file_exportable": False,
            "export_allowed": False,
            "content_type": "application/octet-stream",
            "readiness": "blocked",
            "quality_gate_decision": "fail",
            "quality_gate_mode": "strict",
            "quality_gate_mode_raw": "strict",
            "quality_gate_mode_fallback": False,
            "strict_gate_blocks_export": True,
            "hard_failure_count": 1,
            "soft_failure_count": 0,
            "missing_items_count": 1,
            "blocking_next_action": "regenerate_report_to_receive_signed_export_artifact",
            "warning_next_action": None,
            "next_action": "regenerate_report_to_receive_signed_export_artifact",
        }
        _record_export_audit_event(
            payload=payload,
            export_format=export_format,
            outcome="blocked",
            gate=gate,
            export_readiness=export_readiness,
            integrity=integrity,
            token_payload=None,
            filename=_safe_export_filename(payload.filename, extension=export_format),
            content_type=None,
            error_code="LLM_REPORT_EXPORT_TOKEN_REQUIRED",
        )
        _raise_http_error(
            422,
            ErrorCode.INVALID_INPUT,
            "llm report export artifact token is required",
            details={
                "error_code": "LLM_REPORT_EXPORT_TOKEN_REQUIRED",
                "export_readiness": export_readiness,
                "export_integrity": integrity,
                "quality_gate": gate,
                "next_action": "regenerate_report_to_receive_signed_export_artifact",
            },
        )

    gate_mode, gate_mode_raw, gate_mode_fallback = _resolve_gate_mode(
        payload.quality_gate_mode or settings.llm_report_gate_mode
    )
    integrity = {
        "contract_version": "llm_report.export_integrity.v1",
        "mode": "legacy_payload_gate",
        "trusted": False,
        "gate_source": "client_payload_legacy_compat",
        "next_action": "regenerate_report_to_receive_signed_export_artifact",
        **actor_observability,
    }
    return (
        _normalize_quality_gate_for_export(payload.quality_gate),
        gate_mode,
        gate_mode_raw,
        gate_mode_fallback,
        None,
        integrity,
    )


def _record_export_audit_event(
    *,
    payload: ExportMarkdownRequest,
    export_format: str,
    outcome: str,
    gate: dict[str, Any],
    export_readiness: dict[str, Any],
    integrity: dict[str, Any],
    token_payload: dict[str, Any] | None,
    filename: str | None,
    content_type: str | None,
    content_size_bytes: int | None = None,
    error_code: str | None = None,
) -> dict[str, Any] | None:
    try:
        event = build_export_trend_metric(
            export_format=export_format,
            outcome=outcome,
            gate=gate,
            export_readiness=export_readiness,
            integrity=integrity,
            project_key=(token_payload.get("project_key") if token_payload else payload.project_key),
            request_id=token_payload.get("request_id") if token_payload else None,
            job_id=token_payload.get("job_id") if token_payload else None,
            artifact_id=token_payload.get("artifact_id") if token_payload else integrity.get("artifact_id"),
            artifact_sha256=token_payload.get("markdown_sha256") if token_payload else payload.artifact_sha256,
            filename=filename,
            content_type=content_type,
            content_size_bytes=content_size_bytes,
            error_code=error_code,
            ui_read_only_context_trace=_resolve_ui_read_only_context_trace(
                payload,
                export_format=export_format,
                outcome=outcome,
            ),
        )
        event.update(
            {
                "actor_source": integrity.get("actor_source"),
                "actor_trusted": bool(integrity.get("actor_trusted")),
                "actor_auth_mode": integrity.get("actor_auth_mode"),
                "legacy_actor_id": integrity.get("legacy_actor_id"),
            }
        )
        recorded_event = record_llm_report_export_audit_event(event)
        record_quality_trend_metric(
            recorded_event,
            job_id=recorded_event.get("job_id"),
            topic=f"llm_report_export:{export_format}",
            job_status="completed" if outcome == "success" else "failed",
            source="export",
        )
        return recorded_event
    except Exception:  # noqa: BLE001
        return None


def _build_export_response_headers(
    *,
    filename: str,
    content_type: str,
    integrity: dict[str, Any],
    audit_event: dict[str, Any] | None,
    export_format: str,
    export_readiness: dict[str, Any],
) -> dict[str, str]:
    header_snapshot = audit_event.get("header_snapshot") if isinstance(audit_event, dict) else {}
    if not isinstance(header_snapshot, dict):
        header_snapshot = {}
    source_ref = audit_event.get("source_ref") if isinstance(audit_event, dict) else {}
    if not isinstance(source_ref, dict):
        source_ref = {}
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "X-LLM-Report-Export-Readiness": str(header_snapshot.get("readiness") or export_readiness["readiness"]),
        "X-LLM-Report-Export-Format": str(header_snapshot.get("format") or export_format),
        "X-LLM-Report-Export-Integrity": str(integrity["mode"]),
        "X-Quality-Gate-Decision": str(
            header_snapshot.get("quality_gate_decision") or export_readiness["quality_gate_decision"]
        ),
        "X-Quality-Gate-Mode": str(header_snapshot.get("quality_gate_mode") or export_readiness["quality_gate_mode"]),
        "X-LLM-Report-Source-Ref": str(source_ref.get("id") or header_snapshot.get("source_ref") or ""),
        "X-Actor-Source": str(integrity.get("actor_source") or "unknown"),
        "X-Actor-Trusted": "true" if bool(integrity.get("actor_trusted")) else "false",
        "X-Actor-Auth-Mode": str(integrity.get("actor_auth_mode") or "unknown"),
    }
    project_key = header_snapshot.get("project_key")
    if project_key:
        headers["X-Project-Key"] = str(project_key)
    source_trace_id = header_snapshot.get("source_trace_id")
    if source_trace_id:
        headers["X-LLM-Report-Source-Trace-Id"] = str(source_trace_id)
    job_id = header_snapshot.get("job_id")
    if job_id is not None:
        headers["X-LLM-Report-Job-Id"] = str(job_id)
    if content_type:
        headers["X-LLM-Report-Audit-Content-Type"] = content_type
    return headers


def _claim_export_token_or_raise(
    *,
    payload: ExportMarkdownRequest,
    export_format: str,
    gate: dict[str, Any],
    export_readiness: dict[str, Any],
    integrity: dict[str, Any],
    token_payload: dict[str, Any] | None,
    filename: str | None,
    content_type: str | None,
) -> None:
    if not token_payload:
        return
    if not bool(getattr(settings, "llm_report_export_one_time_use_enabled", True)):
        return
    if not bool(token_payload.get("one_time_use", True)):
        return
    claim = claim_llm_report_export_token_use(token_payload)
    if bool(claim.get("claimed")):
        return
    reason = "export_token_revoked" if bool(claim.get("revoked")) else "export_token_already_used"
    blocked_integrity = {
        **integrity,
        "trusted": False,
        "error_code": "LLM_REPORT_EXPORT_TOKEN_INVALID",
        "error_reason": reason,
        "token_state": {
            "claimed": False,
            "already_used": bool(claim.get("already_used")),
            "revoked": bool(claim.get("revoked")),
            "degraded": bool(claim.get("token_state_store_degraded") or claim.get("degraded")),
        },
    }
    _record_export_audit_event(
        payload=payload,
        export_format=export_format,
        outcome="token_invalid",
        gate=gate,
        export_readiness={**export_readiness, "export_allowed": False, "file_exportable": False},
        integrity=blocked_integrity,
        token_payload=token_payload,
        filename=filename,
        content_type=content_type,
        error_code="LLM_REPORT_EXPORT_TOKEN_INVALID",
    )
    _raise_http_error(
        403,
        ErrorCode.INVALID_INPUT,
        "invalid llm report export token",
        details={
            "error_code": "LLM_REPORT_EXPORT_TOKEN_INVALID",
            "reason": reason,
            "next_action": "regenerate_report_before_export",
        },
    )


def _raise_http_error(
    status_code: int,
    code: ErrorCode,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail=error_response(
            code,
            message,
            details=details,
        ),
    )


def _resolve_quality_next_action(gate: dict[str, Any], gate_mode: str, *, export_format: str = "markdown") -> str:
    decision = str(gate.get("decision") or "fail").lower()
    if decision == "pass":
        return f"export_{export_format}"
    if decision == "warn":
        return "review_quality_gate_warnings_before_export"
    if gate_mode == "strict":
        return "fix_quality_gate_blockers_before_export"
    if gate_mode == "off":
        return "quality_gate_off_review_before_export"
    return "review_quality_gate_failures_before_export"


def _build_export_readiness(
    *,
    gate: dict[str, Any],
    gate_mode: str,
    gate_mode_raw: str,
    gate_mode_fallback: bool,
    markdown: str,
    export_format: str = "markdown",
) -> dict[str, Any]:
    decision = str(gate.get("decision") or "fail").lower()
    hard_failures = gate.get("hard_failures") if isinstance(gate.get("hard_failures"), list) else []
    soft_failures = gate.get("soft_failures") if isinstance(gate.get("soft_failures"), list) else []
    missing_items = gate.get("missing_items") if isinstance(gate.get("missing_items"), list) else []
    normalized_format = str(export_format or "markdown").strip().lower() or "markdown"
    content_type_by_format = {
        "markdown": "text/markdown; charset=utf-8",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    next_action = _resolve_quality_next_action(gate, gate_mode, export_format=normalized_format)
    readiness = "ready"
    if decision == "warn" or soft_failures:
        readiness = "review_required"
    if decision == "fail":
        readiness = "blocked" if gate_mode == "strict" else "review_required"
    return {
        "contract_version": "llm_report.export_readiness.v1",
        "format": normalized_format,
        "supported_formats": ["markdown", "pdf", "docx"],
        "markdown_exportable": bool(markdown),
        "file_exportable": bool(markdown) and not (gate_mode == "strict" and decision == "fail"),
        "export_allowed": bool(markdown) and not (gate_mode == "strict" and decision == "fail"),
        "content_type": content_type_by_format.get(normalized_format, "application/octet-stream"),
        "readiness": readiness,
        "quality_gate_decision": decision,
        "quality_gate_mode": gate_mode,
        "quality_gate_mode_raw": gate_mode_raw,
        "quality_gate_mode_fallback": gate_mode_fallback,
        "strict_gate_blocks_export": gate_mode == "strict" and decision == "fail",
        "hard_failure_count": len(hard_failures),
        "soft_failure_count": len(soft_failures),
        "missing_items_count": len(missing_items),
        "blocking_next_action": next_action if readiness == "blocked" else None,
        "warning_next_action": next_action if readiness == "review_required" else None,
        "next_action": next_action,
    }


@router.post("/generate")
def generate_llm_report(payload: GenerateReportRequest, request: Request) -> dict[str, Any]:
    if not settings.llm_report_enabled:
        _raise_http_error(
            503,
            ErrorCode.CONFIG_ERROR,
            "llm report is temporarily disabled by config",
        )

    header_request_id = None
    header_project_key = None
    header_trace_id = None
    actor_context = _request_actor_context(request)
    if request is not None:
        header_request_id = (request.headers.get("X-Request-Id") or "").strip() or None
        header_trace_id = (request.headers.get("X-Trace-Id") or "").strip() or None
        header_project_key = (request.headers.get("X-Project-Key") or "").strip() or None
    identity = resolve_request_identity(
        consumer="llm_report.generate",
        trace_id=header_trace_id,
        request_id=header_request_id,
        project_key=header_project_key,
        actor_id=actor_context.actor_id,
        trace_fallback_seed=f"llm-report:{payload.topic[:32]}",
    )
    boundary = resolve_consumer_adapter_boundary(identity.consumer)
    agent_boundary = evaluate_agent_permission_boundary(
        consumer=identity.consumer,
        agent_role=normalize_agent_role(None, consumer=identity.consumer),
        requested_permissions=["llm.invoke", "project.read"],
    )
    routing = resolve_routing_decision(
        service_name="llm_report_generation",
        capability="report_generation",
        request_overrides={},
        service_config=get_llm_config("llm_report_generation"),
        default_provider=settings.llm_provider,
        default_model=None,
    )
    trace_id = identity.trace_id

    gate_mode, gate_mode_raw, gate_mode_fallback = _resolve_gate_mode(settings.llm_report_gate_mode)
    requested_sources = [item.model_dump() for item in payload.sources]
    source_count_requested = len(requested_sources)
    job_id: int | None = None
    job_finalized = False
    try:
        auto_source_enabled = bool(getattr(settings, "llm_report_auto_source_enabled", True))
        auto_source_target_count = _resolve_auto_source_target_count(
            getattr(settings, "llm_report_auto_source_target_count", 6)
        )
        if requested_sources or not auto_source_enabled:
            resolved_sources = requested_sources
        else:
            resolved_sources = resolve_report_sources(
                payload.topic,
                requested_sources,
                target_count=auto_source_target_count,
            )
        source_count_resolved = len(resolved_sources)
        capability_truth = build_report_capability_truth(
            route_kind=routing.route_kind,
            auto_source_enabled=auto_source_enabled,
        )
        job_id = start_job(
            _LLM_REPORT_JOB_TYPE,
            {
                "topic": payload.topic,
                "source_count_requested": source_count_requested,
                "source_count_resolved": source_count_resolved,
                "auto_source_enabled": auto_source_enabled,
                "auto_source_target_count": auto_source_target_count,
                "gate_mode": gate_mode,
                "gate_mode_raw": gate_mode_raw,
                "gate_mode_fallback": gate_mode_fallback,
                "trace_id": trace_id,
                "request_id": identity.request_id,
                "project_key": identity.project_key,
                "consumer": identity.consumer,
                "service_name": routing.service_name,
                "capability": routing.capability,
                "capability_truth": capability_truth,
                "route_kind": routing.route_kind,
                "adapter_boundary": boundary.to_observability(),
                "agent_boundary": agent_boundary.to_observability(),
            },
        )
        report = build_structured_report(
            topic=payload.topic,
            sources=resolved_sources,
            section_titles=payload.section_titles or None,
        )
        markdown = render_markdown(report)
        gate = evaluate_report_gate(report)
        export_artifact = build_llm_report_export_artifact(
            markdown=markdown,
            gate=gate,
            gate_mode=gate_mode,
            trace_id=trace_id,
            request_id=identity.request_id,
            project_key=identity.project_key,
            job_id=job_id,
            topic=payload.topic,
            token_secret=settings.llm_report_export_token_secret,
            actor_id=identity.actor_id,
            ttl_seconds=getattr(settings, "llm_report_export_token_ttl_seconds", 3600),
            one_time_use=bool(getattr(settings, "llm_report_export_one_time_use_enabled", True)),
        )
        export_artifact["actor_context"] = actor_context.to_observability()
        quality_gate_metrics = export_quality_gate_metrics(gate)
        export_readiness = _build_export_readiness(
            gate=gate,
            gate_mode=gate_mode,
            gate_mode_raw=gate_mode_raw,
            gate_mode_fallback=gate_mode_fallback,
            markdown=markdown,
        )
        export_contract = {
            **export_readiness,
            "contract_version": "llm_report.export_contract.v1",
            "artifact": export_artifact,
            "integrity": {
                "contract_version": "llm_report.export_integrity.v1",
                "mode": "artifact_token",
                "trusted": True,
                "gate_source": "server_signed_artifact_token",
                **actor_context.to_observability(),
            },
        }
        quality_gate_trend_record = build_quality_trend_metric(
            gate=gate,
            quality_gate_metrics=quality_gate_metrics,
            gate_mode=gate_mode,
            gate_mode_raw=gate_mode_raw,
            gate_mode_fallback=gate_mode_fallback,
            trace_id=trace_id,
            request_id=identity.request_id,
            project_key=identity.project_key,
            source_count_requested=source_count_requested,
            source_count_resolved=source_count_resolved,
            export_readiness=export_readiness,
        )
        quality_gate_trend_record = record_quality_trend_metric(
            quality_gate_trend_record,
            job_id=job_id,
            topic=payload.topic,
            job_status="failed" if gate_mode == "strict" and gate["decision"] == "fail" else "completed",
        )

        gate_result = {
            **quality_gate_metrics,
            "trace_id": trace_id,
            "request_id": identity.request_id,
            "project_key": identity.project_key,
            "gate_mode": gate_mode,
            "gate_mode_raw": gate_mode_raw,
            "gate_mode_fallback": gate_mode_fallback,
            "hard_failures": gate["hard_failures"],
            "soft_failures": gate["soft_failures"],
            "missing_items": gate["missing_items"],
            "export_contract": export_contract,
            "export_readiness": export_readiness,
            "quality_gate_trend_record": quality_gate_trend_record,
            "report_quality_trend_metric": quality_gate_trend_record,
            "export_artifact": export_artifact,
            "artifact": export_artifact,
            "rules": gate["rules"],
            "observability": gate["observability"],
        }
        if gate_mode == "strict" and gate["decision"] == "fail":
            complete_job(
                job_id,
                status="failed",
                result={
                    **gate_result,
                    "error_code": "QUALITY_GATE_BLOCKED",
                    "gate_blocked": True,
                },
            )
            job_finalized = True
            _raise_http_error(
                422,
                ErrorCode.INVALID_INPUT,
                "quality gate blocked report generation in strict mode",
                details={
                    "quality_gate": gate,
                    "quality_gate_metrics": quality_gate_metrics,
                    "export_contract": export_contract,
                    "export_readiness": export_readiness,
                    "export_artifact": export_artifact,
                    "artifact": export_artifact,
                    "quality_gate_trend_record": quality_gate_trend_record,
                    "report_quality_trend_metric": quality_gate_trend_record,
                    "next_action": export_readiness["next_action"],
                    "capability_truth": capability_truth,
                    "observability": {
                        "job_id": job_id,
                        "trace_id": trace_id,
                        "request_id": identity.request_id,
                        "project_key": identity.project_key,
                        "gate_mode": gate_mode,
                        "identity": identity.to_dict(),
                        "actor_context": actor_context.to_observability(),
                        "consumer_boundary": boundary.to_observability(),
                        "agent_boundary": agent_boundary.to_observability(),
                        "routing": routing.to_observability(),
                        "audit": build_trace_audit_record(
                            identity=identity,
                            routing=routing,
                            status="blocked",
                            degraded=False,
                            error_code="QUALITY_GATE_BLOCKED",
                        ),
                    },
                },
            )

        complete_job(job_id, result=gate_result)
        job_finalized = True
        return ok(
            {
                "report": report.to_dict(),
                "markdown": markdown,
                "quality_gate": gate,
                "quality_gate_metrics": quality_gate_metrics,
                "export_contract": export_contract,
                "export_readiness": export_readiness,
                "export_artifact": export_artifact,
                "artifact": export_artifact,
                "quality_gate_trend_record": quality_gate_trend_record,
                "report_quality_trend_metric": quality_gate_trend_record,
                "capability_truth": capability_truth,
                "observability": {
                    "job_id": job_id,
                    "trace_id": trace_id,
                    "request_id": identity.request_id,
                    "project_key": identity.project_key,
                    "gate_mode": gate_mode,
                    "gate_mode_raw": gate_mode_raw,
                    "gate_mode_fallback": gate_mode_fallback,
                    "identity": identity.to_dict(),
                    "actor_context": actor_context.to_observability(),
                    "consumer_boundary": boundary.to_observability(),
                    "agent_boundary": agent_boundary.to_observability(),
                    "routing": routing.to_observability(),
                    "audit": build_trace_audit_record(
                        identity=identity,
                        routing=routing,
                        status="succeeded",
                        degraded=False,
                    ),
                },
            }
        )

    except HTTPException as exc:
        if not job_finalized and job_id is not None:
            fail_job(job_id, str(getattr(exc, "detail", exc)))
        raise
    except Exception as exc:  # noqa: BLE001
        if not job_finalized and job_id is not None:
            fail_job(job_id, str(exc))
        _raise_http_error(
            500,
            ErrorCode.INTERNAL_ERROR,
            "failed to generate llm report",
            details={
                "error_code": "LLM_REPORT_INTERNAL_ERROR",
                "trace_id": trace_id,
                "request_id": identity.request_id,
                "project_key": identity.project_key,
                "job_id": job_id,
                "capability_truth": build_report_capability_truth(
                    route_kind=routing.route_kind,
                    auto_source_enabled=bool(getattr(settings, "llm_report_auto_source_enabled", True)),
                ),
                "routing": routing.to_observability(),
                "audit": build_trace_audit_record(
                    identity=identity,
                    routing=routing,
                    status="failed",
                    degraded=False,
                    error_code="LLM_REPORT_INTERNAL_ERROR",
                    error_detail=str(exc),
                ),
            },
        )


@router.get("/quality-trends")
def list_llm_report_quality_trends(
    project_key: str | None = Query(default=None, max_length=64),
    decision: str | None = Query(default=None, max_length=12),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    records, storage = list_quality_trend_records(
        limit=limit,
        project_key=project_key,
        decision=decision,
    )
    return ok(
        {
            "contract_version": "llm_report.quality_trends.v1",
            "records": records,
            "summary": summarize_quality_trends(records),
            "storage": storage,
            "filters": {
                "project_key": project_key,
                "decision": decision,
                "limit": limit,
            },
        }
    )


@router.post(
    "/export/markdown",
    response_model=None,
    response_class=Response,
    responses={200: {"content": {"text/markdown": {"schema": {"type": "string"}}}}},
)
def export_llm_report_markdown(payload: ExportMarkdownRequest, request: Request) -> Response:
    gate, gate_mode, gate_mode_raw, gate_mode_fallback, token_payload, integrity = _resolve_export_gate_context(
        payload,
        export_format="markdown",
        request=request,
    )
    export_readiness = _build_export_readiness(
        gate=gate,
        gate_mode=gate_mode,
        gate_mode_raw=gate_mode_raw,
        gate_mode_fallback=gate_mode_fallback,
        markdown=payload.markdown,
    )
    if export_readiness["strict_gate_blocks_export"]:
        _record_export_audit_event(
            payload=payload,
            export_format="markdown",
            outcome="blocked",
            gate=gate,
            export_readiness=export_readiness,
            integrity=integrity,
            token_payload=token_payload,
            filename=_safe_export_filename(payload.filename),
            content_type="text/markdown; charset=utf-8",
            error_code="QUALITY_GATE_BLOCKED",
        )
        _raise_http_error(
            422,
            ErrorCode.INVALID_INPUT,
            "quality gate blocked markdown export in strict mode",
            details={
                "export_readiness": export_readiness,
                "export_integrity": integrity,
                "quality_gate": gate,
                "next_action": export_readiness["next_action"],
            },
        )
    filename = _safe_export_filename(payload.filename)
    content_type = "text/markdown; charset=utf-8"
    _claim_export_token_or_raise(
        payload=payload,
        export_format="markdown",
        gate=gate,
        export_readiness=export_readiness,
        integrity=integrity,
        token_payload=token_payload,
        filename=filename,
        content_type=content_type,
    )
    audit_event = _record_export_audit_event(
        payload=payload,
        export_format="markdown",
        outcome="success",
        gate=gate,
        export_readiness=export_readiness,
        integrity=integrity,
        token_payload=token_payload,
        filename=filename,
        content_type=content_type,
        content_size_bytes=len(payload.markdown.encode("utf-8")),
    )
    headers = _build_export_response_headers(
        filename=filename,
        content_type=content_type,
        integrity=integrity,
        audit_event=audit_event,
        export_format="markdown",
        export_readiness=export_readiness,
    )
    return Response(
        content=payload.markdown,
        media_type="text/markdown",
        headers=headers,
    )


def _export_llm_report_binary(payload: ExportMarkdownRequest, *, export_format: str, request: Request) -> Response:
    gate, gate_mode, gate_mode_raw, gate_mode_fallback, token_payload, integrity = _resolve_export_gate_context(
        payload,
        export_format=export_format,
        request=request,
    )
    export_readiness = _build_export_readiness(
        gate=gate,
        gate_mode=gate_mode,
        gate_mode_raw=gate_mode_raw,
        gate_mode_fallback=gate_mode_fallback,
        markdown=payload.markdown,
        export_format=export_format,
    )
    if export_readiness["strict_gate_blocks_export"]:
        _record_export_audit_event(
            payload=payload,
            export_format=export_format,
            outcome="blocked",
            gate=gate,
            export_readiness=export_readiness,
            integrity=integrity,
            token_payload=token_payload,
            filename=_safe_export_filename(payload.filename, extension=export_format),
            content_type=export_readiness.get("content_type"),
            error_code="QUALITY_GATE_BLOCKED",
        )
        _raise_http_error(
            422,
            ErrorCode.INVALID_INPUT,
            f"quality gate blocked {export_format} export in strict mode",
            details={
                "export_readiness": export_readiness,
                "export_integrity": integrity,
                "quality_gate": gate,
                "next_action": export_readiness["next_action"],
            },
    )
    _claim_export_token_or_raise(
        payload=payload,
        export_format=export_format,
        gate=gate,
        export_readiness=export_readiness,
        integrity=integrity,
        token_payload=token_payload,
        filename=_safe_export_filename(payload.filename, extension=export_format),
        content_type=export_readiness.get("content_type"),
    )
    artifact = render_markdown_export(
        payload.markdown,
        export_format,  # type: ignore[arg-type]
        reset_telemetry_boundary_context=payload.reset_telemetry_boundary_context,
    )
    filename = _safe_export_filename(payload.filename, extension=artifact.extension)
    audit_event = _record_export_audit_event(
        payload=payload,
        export_format=export_format,
        outcome="success",
        gate=gate,
        export_readiness=export_readiness,
        integrity=integrity,
        token_payload=token_payload,
        filename=filename,
        content_type=artifact.media_type,
        content_size_bytes=len(artifact.content),
    )
    headers = _build_export_response_headers(
        filename=filename,
        content_type=artifact.media_type,
        integrity=integrity,
        audit_event=audit_event,
        export_format=export_format,
        export_readiness=export_readiness,
    )
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers=headers,
    )


@router.post(
    "/export/pdf",
    response_model=None,
    response_class=Response,
    responses={200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
)
def export_llm_report_pdf(payload: ExportMarkdownRequest, request: Request) -> Response:
    return _export_llm_report_binary(payload, export_format="pdf", request=request)


@router.post(
    "/export/docx",
    response_model=None,
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
                    "schema": {"type": "string", "format": "binary"}
                }
            }
        }
    },
)
def export_llm_report_docx(payload: ExportMarkdownRequest, request: Request) -> Response:
    return _export_llm_report_binary(payload, export_format="docx", request=request)
