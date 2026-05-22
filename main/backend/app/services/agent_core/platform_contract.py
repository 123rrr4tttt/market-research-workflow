from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal, Mapping

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
AGENT_CORE_PROVIDER_CAPABILITY_MATRIX_CONTRACT_VERSION = "agent_core.provider_capability_matrix.v1"
AGENT_CORE_EXTERNAL_FRAMEWORK_BOUNDARY_CONTRACT_VERSION = "agent_core.external_framework_boundary.v1"

ProviderCapabilityStatus = Literal[
    "repo_native_supported",
    "missing_config",
    "blocked_permissions",
    "deferred_external_framework",
]


@dataclass(frozen=True)
class ProviderCapabilityMatrixEntry:
    provider_key: str
    provider_path: str
    capability: str
    status: ProviderCapabilityStatus
    repo_native: bool
    live_provider_claim: bool
    config_keys_required: tuple[str, ...] = ()
    missing_config_keys: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()
    denied_permissions: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_key": self.provider_key,
            "provider_path": self.provider_path,
            "capability": self.capability,
            "status": self.status,
            "repo_native": self.repo_native,
            "live_provider_claim": self.live_provider_claim,
            "config_keys_required": list(self.config_keys_required),
            "missing_config_keys": list(self.missing_config_keys),
            "required_permissions": list(self.required_permissions),
            "denied_permissions": list(self.denied_permissions),
            "evidence": list(self.evidence),
            "notes": self.notes,
        }


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
        "provider_capability_matrix": build_provider_capability_matrix(
            context=context,
            capability=boundary.capability,
            consumer=boundary.consumer,
            agent_role=permission_boundary.agent_role,
        ),
        "evidence_envelope": {
            "contract_version": AGENT_CORE_PLATFORM_EVIDENCE_CONTRACT_VERSION,
            "trace_audit": trace_audit,
            "event_type_counts": _event_type_counts(result.events),
            "tool_result_status_counts": _tool_result_status_counts(result.tool_results),
        },
    }


def build_provider_capability_matrix(
    *,
    context: Mapping[str, Any] | None,
    capability: str = "agent_tool_dispatch",
    consumer: str = AGENT_CORE_PLATFORM_CONSUMER,
    agent_role: str | None = "orchestration_runtime",
) -> dict[str, Any]:
    """Build the static AgentCore provider capability and framework boundary matrix.

    This is a contract inventory, not a live provider health probe. It records
    which repo-native paths are supported by deterministic code, which paths
    still need runtime configuration, which requests the AgentCore permission
    boundary blocks, and why external framework adoption remains deferred.
    """

    raw_context = dict(context or {})
    provider_config = _provider_config_map(raw_context.get("provider_capability_config"))
    entries: list[ProviderCapabilityMatrixEntry] = [
        ProviderCapabilityMatrixEntry(
            provider_key="fake_core_provider",
            provider_path="app.services.agent_core.fake_provider.FakeCoreProvider",
            capability=capability,
            status="repo_native_supported",
            repo_native=True,
            live_provider_claim=False,
            required_permissions=("llm.invoke", "project.read"),
            evidence=(
                "deterministic CoreModelStep.tools fixture",
                "CoreToolRegistry.schema_inventory",
                "AgentCore runtime_dispatch event sequence",
            ),
            notes="Repo-native deterministic provider for contract validation only.",
        )
    ]

    json_missing = _missing_config_keys(
        provider_config=provider_config,
        provider_key="json_core_provider",
        required=("llm_provider", "model"),
    )
    entries.append(
        ProviderCapabilityMatrixEntry(
            provider_key="json_core_provider",
            provider_path="app.services.agent_core.json_provider.JsonCoreProvider",
            capability=capability,
            status="missing_config" if json_missing else "repo_native_supported",
            repo_native=True,
            live_provider_claim=False,
            config_keys_required=("llm_provider", "model"),
            missing_config_keys=json_missing,
            required_permissions=("llm.invoke", "project.read"),
            evidence=("JSON tool-call protocol adapter exists in repo",),
            notes="Static config sufficiency only; this row does not assert a live model call.",
        )
    )

    native_missing = _missing_config_keys(
        provider_config=provider_config,
        provider_key="native_tool_calling_provider",
        required=("llm_provider", "model", "tool_calling"),
    )
    entries.append(
        ProviderCapabilityMatrixEntry(
            provider_key="native_tool_calling_provider",
            provider_path="app.services.agent_core.native_provider.NativeToolCallingCoreProvider",
            capability=capability,
            status="missing_config" if native_missing else "repo_native_supported",
            repo_native=True,
            live_provider_claim=False,
            config_keys_required=("llm_provider", "model", "tool_calling"),
            missing_config_keys=native_missing,
            required_permissions=("llm.invoke", "project.read"),
            evidence=("native bind_tools adapter with JSON fallback exists in repo",),
            notes="Requires a configured chat model that exposes tool-calling semantics.",
        )
    )

    blocked_decision = evaluate_agent_permission_boundary(
        consumer=consumer,
        agent_role=agent_role,
        requested_permissions=["llm.invoke", "project.read", "cross_consumer.invoke"],
    )
    entries.append(
        ProviderCapabilityMatrixEntry(
            provider_key="agent_core.permission_boundary",
            provider_path="app.services.llm.platformization.evaluate_agent_permission_boundary",
            capability="cross_consumer.invoke",
            status="blocked_permissions",
            repo_native=True,
            live_provider_claim=False,
            required_permissions=tuple(blocked_decision.requested_permissions),
            denied_permissions=tuple(blocked_decision.denied_permissions),
            evidence=tuple(blocked_decision.denied_reasons),
            notes="Cross-consumer execution is not part of the AgentCore provider baseline.",
        )
    )

    for framework in _external_framework_candidates(raw_context.get("external_framework_candidates")):
        entries.append(
            ProviderCapabilityMatrixEntry(
                provider_key=framework,
                provider_path="external_framework.evaluate_only",
                capability=capability,
                status="deferred_external_framework",
                repo_native=False,
                live_provider_claim=False,
                evidence=("agent_core.external_framework_boundary.v1",),
                notes="No external framework dependency is adopted until it proves a gap beyond the repo-native contract.",
            )
        )

    serialized = [entry.to_dict() for entry in entries]
    return {
        "contract_version": AGENT_CORE_PROVIDER_CAPABILITY_MATRIX_CONTRACT_VERSION,
        "evaluation_mode": "static_contract_not_live_probe",
        "live_provider_claims": any(bool(entry["live_provider_claim"]) for entry in serialized),
        "summary": {
            "by_status": _count_by_key(serialized, "status"),
            "by_repo_native": _count_bool_by_key(serialized, "repo_native"),
        },
        "entries": serialized,
        "external_framework_boundary": build_external_framework_boundary(),
    }


def build_external_framework_boundary() -> dict[str, Any]:
    return {
        "contract_version": AGENT_CORE_EXTERNAL_FRAMEWORK_BOUNDARY_CONTRACT_VERSION,
        "adoption_status": "deferred",
        "defer_rule": "adopt only after a written delta proves additive capability beyond AgentCore plus workflow graph",
        "entry_criteria": [
            "preserve CoreToolRegistry schema inventory or prove a stronger inspectable schema contract",
            "preserve tool_call_requested -> tool_call_started -> tool_result dispatch evidence or an equivalent ordered audit trail",
            "preserve AgentCore permission decisions before execution, including blocked cross-consumer permissions",
            "preserve trace_audit fields for consumer, project_key, trace_id, request_id, capability, provider, model, status, and errors",
            "keep deterministic checker coverage green without importing the external framework as a runtime dependency",
        ],
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


def _provider_config_map(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for raw_key, raw_config in value.items():
        key = _text_or_none(raw_key)
        if not key or not isinstance(raw_config, Mapping):
            continue
        out[key] = dict(raw_config)
    return out


def _missing_config_keys(
    *,
    provider_config: Mapping[str, Mapping[str, Any]],
    provider_key: str,
    required: tuple[str, ...],
) -> tuple[str, ...]:
    config = dict(provider_config.get(provider_key) or {})
    missing: list[str] = []
    for key in required:
        raw = config.get(key)
        if isinstance(raw, bool):
            if not raw:
                missing.append(key)
            continue
        if _text_or_none(raw) is None:
            missing.append(key)
    return tuple(missing)


def _external_framework_candidates(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple, set)):
        candidates = [_text_or_none(item) for item in value]
    else:
        candidates = []
    normalized = [item for item in candidates if item]
    if not normalized:
        normalized = ["langgraph_runtime", "semantic_kernel_agent", "crewai_agent"]
    return tuple(dict.fromkeys(normalized))


def _count_by_key(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        name = _text_or_none(item.get(key)) or "unknown"
        counts[name] += 1
    return {name: counts[name] for name in sorted(counts)}


def _count_bool_by_key(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter("true" if bool(item.get(key)) else "false" for item in items)
    return {name: counts[name] for name in sorted(counts)}
