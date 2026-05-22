from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from app.services.llm.platformization import (
    build_trace_audit_record,
    evaluate_agent_permission_boundary,
    resolve_consumer_adapter_boundary,
    resolve_request_identity,
    resolve_routing_decision,
)

from .contracts import AgentCoreRequest, AgentCoreRunResult, CoreEvent, CoreToolResult
from .registry import CoreToolRegistry


AGENT_CORE_PLATFORM_CONSUMER = "agent_core.tool_dispatch"
AGENT_CORE_PLATFORM_CONTRACT_VERSION = "agent_core.platform_contract.v1"
AGENT_CORE_RUNTIME_DISPATCH_CONTRACT_VERSION = "agent_core.runtime_dispatch.v1"
AGENT_CORE_PLATFORM_EVIDENCE_CONTRACT_VERSION = "agent_core.platform_evidence.v1"


def build_agent_core_platform_contract(
    *,
    request: AgentCoreRequest,
    registry: CoreToolRegistry,
    result: AgentCoreRunResult,
    service_name: str = "agent_core.runtime_dispatcher",
) -> dict[str, Any]:
    """Build the deterministic audit envelope for AgentCore as an LLM-platform consumer.

    The envelope intentionally avoids raw event ids and timestamps. Those fields
    remain in AgentCore events, while this contract keeps only stable dispatch
    facts needed for platform validation and framework-fit comparisons.
    """

    context = dict(request.context or {})
    boundary = resolve_consumer_adapter_boundary(AGENT_CORE_PLATFORM_CONSUMER)
    identity = resolve_request_identity(
        consumer=boundary.consumer,
        trace_id=_text_or_none(context.get("trace_id")),
        request_id=_text_or_none(context.get("request_id")),
        project_key=request.project_key,
        actor_id=_text_or_none(context.get("actor_id")),
        trace_fallback_seed=request.turn_id,
    )
    routing = resolve_routing_decision(
        service_name=service_name,
        capability=boundary.capability,
        request_overrides=_mapping_or_none(context.get("llm_request_overrides") or context.get("llm_overrides")),
        service_config=_mapping_or_none(context.get("llm_service_config")),
        default_provider=_text_or_none(context.get("default_provider")),
        default_model=_text_or_none(context.get("default_model")),
    )
    requested_permissions = _permission_list(context.get("requested_permissions"))
    permission_boundary = evaluate_agent_permission_boundary(
        consumer=boundary.consumer,
        agent_role=_text_or_none(context.get("agent_role")),
        requested_permissions=requested_permissions,
    )
    status = _audit_status(result)
    trace_audit = build_trace_audit_record(
        identity=identity,
        routing=routing,
        status=status,
        degraded=status != "ok",
        error_code=_first_tool_error_code(result),
        error_detail=_first_tool_error_detail(result),
    )
    return {
        "contract_version": AGENT_CORE_PLATFORM_CONTRACT_VERSION,
        "consumer": boundary.consumer,
        "request_identity": identity.to_dict(),
        "consumer_boundary": boundary.to_observability(),
        "agent_permission_boundary": permission_boundary.to_observability(),
        "routing": routing.to_observability(),
        "tool_schema_inventory": registry.schema_inventory(),
        "runtime_dispatch": _runtime_dispatch_contract(result),
        "evidence_envelope": {
            "contract_version": AGENT_CORE_PLATFORM_EVIDENCE_CONTRACT_VERSION,
            "trace_audit": trace_audit,
            "event_type_counts": _event_type_counts(result.events),
            "tool_result_status_counts": _tool_result_status_counts(result.tool_results),
        },
    }


def _runtime_dispatch_contract(result: AgentCoreRunResult) -> dict[str, Any]:
    return {
        "contract_version": AGENT_CORE_RUNTIME_DISPATCH_CONTRACT_VERSION,
        "session_id": result.session_id,
        "turn_id": result.turn_id,
        "stop_reason": result.stop_reason,
        "tool_event_sequence": [_tool_event_snapshot(event) for event in result.events if _is_tool_event(event)],
        "tool_results": [tool_result.to_dict() for tool_result in result.tool_results],
        "permission_request": result.permission_request.to_dict() if result.permission_request else None,
    }


def _tool_event_snapshot(event: CoreEvent) -> dict[str, Any]:
    payload = dict(event.payload or {})
    tool_call = payload.get("tool_call") if isinstance(payload.get("tool_call"), dict) else {}
    tool_spec = payload.get("tool_spec") if isinstance(payload.get("tool_spec"), dict) else {}
    return {
        "event_type": event.event_type,
        "call_id": event.call_id,
        "tool_name": tool_call.get("tool_name") or payload.get("tool_name") or tool_spec.get("name"),
        "permission": payload.get("permission"),
        "status": payload.get("status"),
        "validation": payload.get("validation"),
    }


def _is_tool_event(event: CoreEvent) -> bool:
    return event.event_type in {
        "tool_call_requested",
        "permission_requested",
        "tool_call_started",
        "tool_progress",
        "tool_result",
    }


def _event_type_counts(events: tuple[CoreEvent, ...]) -> dict[str, int]:
    counts = Counter(event.event_type for event in events)
    return {name: counts[name] for name in sorted(counts)}


def _tool_result_status_counts(results: tuple[CoreToolResult, ...]) -> dict[str, int]:
    counts = Counter(result.status for result in results)
    return {name: counts[name] for name in sorted(counts)}


def _audit_status(result: AgentCoreRunResult) -> str:
    if result.permission_request is not None:
        return "needs_approval"
    if any(item.status == "failed" for item in result.tool_results):
        return "failed"
    if any(item.status in {"canceled", "deferred", "needs_approval"} for item in result.tool_results):
        return "partial"
    if result.stop_reason != "final_answer":
        return "partial"
    return "ok"


def _first_tool_error_code(result: AgentCoreRunResult) -> str | None:
    for item in result.tool_results:
        if item.error:
            return _text_or_none(item.error.get("code"))
    return None


def _first_tool_error_detail(result: AgentCoreRunResult) -> str | None:
    for item in result.tool_results:
        if item.error:
            return _text_or_none(item.error.get("message"))
    return None


def _permission_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item or "").strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return ["llm.invoke", "project.read"]


def _mapping_or_none(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _text_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
