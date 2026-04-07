from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...contracts.schemas.writing import LlmActionHistoryItem, LlmActionRequest, LlmActionResponse
from ...settings.config import settings
from ..llm.platformization import (
    build_trace_audit_record,
    evaluate_agent_permission_boundary,
    normalize_agent_role,
    resolve_consumer_adapter_boundary,
    resolve_request_identity,
    resolve_routing_decision,
)
from ..job_logger import complete_job, fail_job, list_jobs, start_job

_WRITING_JOB_TYPE = "wr_action"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_capability_truth(*, action_id: str, route_kind: str, status: str) -> dict[str, Any]:
    resolved_route_kind = str(route_kind or "").strip().lower() or "unknown"
    resolved_status = str(status or "").strip().lower() or "completed"
    return {
        "contract_version": "writing.llm_action.capability_truth.v1",
        "declared_capability": "writing_action",
        "action_id": str(action_id or "").strip(),
        "implementation_kind": "rule_template_action",
        "real_model_path": False,
        "fallback_path": True,
        "route_kind": resolved_route_kind,
        "status": resolved_status,
        "semantic_warning": "current implementation is rule/template-driven and should not be interpreted as a guaranteed real-model execution path",
    }


def _build_action_result(payload: LlmActionRequest) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if payload.action_id == "outline_generate":
        headings = [line.strip("# ").strip() for line in payload.input_markdown.splitlines() if line.startswith("#")]
        if not headings:
            headings = ["Introduction", "Key Findings", "Next Steps"]
            warnings.append("outline_generated_from_fallback")
        content = "\n".join(f"- {item}" for item in headings[:8])
    elif payload.action_id == "section_expand":
        content = f"{payload.input_markdown.rstrip()}\n\nExpanded note: add supporting evidence and citation anchors."
    elif payload.action_id == "selection_rewrite":
        rewritten = str(payload.selection_text or payload.input_markdown or "").strip()
        content = rewritten if rewritten else "No selection text provided."
        if not rewritten:
            warnings.append("selection_missing")
    else:
        snippet = str(payload.selection_text or payload.input_markdown or "").strip()
        content = snippet[:500]
        if not snippet:
            warnings.append("evidence_missing")
    return content, warnings


def dispatch_action(payload: LlmActionRequest) -> LlmActionResponse:
    identity = resolve_request_identity(
        consumer="writing.llm_action",
        trace_id=payload.trace_id,
        request_id=payload.request_id,
        project_key=payload.project_key,
        actor_id=payload.actor_id,
        trace_fallback_seed=f"writing-{payload.action_id}",
    )
    boundary = resolve_consumer_adapter_boundary(identity.consumer)
    agent_boundary = evaluate_agent_permission_boundary(
        consumer=identity.consumer,
        agent_role=normalize_agent_role(payload.agent_role, consumer=identity.consumer),
        requested_permissions=["llm.invoke", "project.read", "project.write"],
    )
    routing = resolve_routing_decision(
        service_name=payload.template_key or payload.action_id,
        capability="writing_action",
        request_overrides={},
        service_config=None,
        default_provider=settings.llm_provider,
        default_model=None,
    )
    trace_id = identity.trace_id
    job_id = start_job(
        _WRITING_JOB_TYPE,
        {
            "project_key": payload.project_key,
            "action_id": payload.action_id,
            "template_key": payload.template_key,
            "template_version": payload.template_version,
            "document_id": payload.document_id,
            "trace_id": trace_id,
            "request_id": identity.request_id,
            "consumer": identity.consumer,
            "service_name": routing.service_name,
            "capability": routing.capability,
            "route_kind": routing.route_kind,
            "route_field_sources": dict(routing.field_sources),
            "adapter_boundary": boundary.to_observability(),
            "agent_boundary": agent_boundary.to_observability(),
            "requested_async": payload.async_mode,
            "consumer_boundary_capability": boundary.capability,
            "agent_boundary_allowed": agent_boundary.allowed,
        },
    )
    try:
        dependency_gate = {
            "contract_version": "writing.cross_theme_gate.e8.v1",
            "topology": ["writing<->graph", "writing<->llm", "writing<->frontend"],
            "llm": {
                "consumer": identity.consumer,
                "capability": boundary.capability,
                "adapter_kind": boundary.adapter_kind,
            },
            "graph": {"mode": "optional_consume_only"},
            "frontend": {"surface": "writing.workbench", "mode": "placement_boundary_only"},
        }
        if not agent_boundary.allowed:
            status = "rejected"
            capability_truth = _build_capability_truth(
                action_id=payload.action_id,
                route_kind=routing.route_kind,
                status=status,
            )
            warnings = list(agent_boundary.denied_reasons) or ["agent_boundary_rejected"]
            result = {
                "trace_id": trace_id,
                "action_id": payload.action_id,
                "template_key": payload.template_key,
                "template_version": payload.template_version,
                "completed_at": _utcnow_iso(),
                "warning_count": len(warnings),
                "request_id": identity.request_id,
                "route_kind": routing.route_kind,
                "agent_boundary_allowed": False,
                "capability_truth": capability_truth,
                "error_code": "AGENT_BOUNDARY_REJECTED",
            }
            complete_job(job_id, status=status, result=result)
            return LlmActionResponse(
                content="",
                sources=[],
                mode=payload.action_id,
                warnings=warnings,
                trace_id=trace_id,
                job_id=job_id,
                status=status,
                capability_truth=capability_truth,
                observability={
                    "job_id": job_id,
                    "trace_id": trace_id,
                    "request_id": identity.request_id,
                    "project_key": identity.project_key,
                    "requested_async": payload.async_mode,
                    "gate_mode": payload.gate_mode,
                    "template_version": payload.template_version,
                    "identity": identity.to_dict(),
                    "consumer_boundary": boundary.to_observability(),
                    "agent_boundary": agent_boundary.to_observability(),
                    "routing": routing.to_observability(),
                    "audit": build_trace_audit_record(
                        identity=identity,
                        routing=routing,
                        status=status,
                        degraded=True,
                    ),
                },
                action_boundary={
                    "consumer_boundary": boundary.to_observability(),
                    "agent_boundary": agent_boundary.to_observability(),
                },
                dependency_gate={**dependency_gate, "passed": False, "reasons": warnings},
            )

        content, warnings = _build_action_result(payload)
        status = "queued" if payload.async_mode else "completed"
        capability_truth = _build_capability_truth(
            action_id=payload.action_id,
            route_kind=routing.route_kind,
            status=status,
        )
        result = {
            "trace_id": trace_id,
            "action_id": payload.action_id,
            "template_key": payload.template_key,
            "template_version": payload.template_version,
            "completed_at": _utcnow_iso(),
            "warning_count": len(warnings),
            "request_id": identity.request_id,
            "route_kind": routing.route_kind,
            "agent_boundary_allowed": True,
            "capability_truth": capability_truth,
        }
        complete_job(job_id, result=result)
        return LlmActionResponse(
            content="" if payload.async_mode else content,
            sources=[],
            mode=payload.action_id,
            warnings=warnings,
            trace_id=trace_id,
            job_id=job_id,
            status=status,
            capability_truth=capability_truth,
            observability={
                "job_id": job_id,
                "trace_id": trace_id,
                "request_id": identity.request_id,
                "project_key": identity.project_key,
                "requested_async": payload.async_mode,
                "gate_mode": payload.gate_mode,
                "template_version": payload.template_version,
                "identity": identity.to_dict(),
                "consumer_boundary": boundary.to_observability(),
                "agent_boundary": agent_boundary.to_observability(),
                "routing": routing.to_observability(),
                "audit": build_trace_audit_record(
                    identity=identity,
                    routing=routing,
                    status=status,
                    degraded=False,
                ),
            },
            action_boundary={
                "consumer_boundary": boundary.to_observability(),
                "agent_boundary": agent_boundary.to_observability(),
            },
            dependency_gate={**dependency_gate, "passed": True},
        )
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        raise


def _job_to_history_item(job: dict[str, Any]) -> LlmActionHistoryItem | None:
    if str(job.get("job_type") or "") != _WRITING_JOB_TYPE:
        return None
    params = job.get("params") if isinstance(job.get("params"), dict) else {}
    started_at = str(job.get("started_at") or "")
    finished_at = str(job.get("finished_at") or "")
    duration_ms: int | None = None
    if started_at and finished_at:
        try:
            start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
        except Exception:
            duration_ms = None
    return LlmActionHistoryItem(
        job_id=int(job["id"]),
        job_type=str(job.get("job_type") or ""),
        status=str(job.get("status") or ""),
        project_key=str(params.get("project_key") or "") or None,
        action_id=str(params.get("action_id") or "") or None,
        template_key=str(params.get("template_key") or "") or None,
        template_version=str(params.get("template_version") or "") or None,
        request_meta={"document_id": params.get("document_id"), "requested_async": params.get("requested_async")},
        actor_id=None,
        trace_id=str(params.get("trace_id") or "") or None,
        created_at=started_at or None,
        duration_ms=duration_ms,
        result_summary={
            "warning_count": params.get("warning_count"),
            "completed_at": params.get("completed_at"),
            "error_code": params.get("error_code"),
        },
    )


def get_action_history(*, limit: int = 20, project_key: str | None = None) -> list[LlmActionHistoryItem]:
    items: list[LlmActionHistoryItem] = []
    for job in list_jobs(limit=limit * 4):
        item = _job_to_history_item(job)
        if item is None:
            continue
        if project_key and item.project_key != project_key:
            continue
        items.append(item)
        if len(items) >= limit:
            break
    return items


def get_action_detail(job_id: int, *, project_key: str | None = None) -> LlmActionHistoryItem:
    for item in get_action_history(limit=200, project_key=project_key):
        if item.job_id == job_id:
            return item
    raise KeyError(f"action history not found: {job_id}")
