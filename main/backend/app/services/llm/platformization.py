from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


CapabilityName = Literal[
    "general_chat",
    "agent_tool_dispatch",
    "writing_action",
    "report_generation",
    "workflow_llm_call",
]
ValueSource = Literal["request", "config", "default", "derived"]
AgentRole = Literal["user_facing_assistant", "orchestration_runtime", "business_capability_wrapper"]
AgentPermission = Literal[
    "llm.invoke",
    "project.read",
    "project.write",
    "provider.route_override",
    "cross_consumer.invoke",
]

_KNOWN_CAPABILITIES = frozenset(
    {
        "general_chat",
        "agent_tool_dispatch",
        "writing_action",
        "report_generation",
        "workflow_llm_call",
    }
)
_KNOWN_AGENT_ROLES = frozenset(
    {
        "user_facing_assistant",
        "orchestration_runtime",
        "business_capability_wrapper",
    }
)
_KNOWN_AGENT_PERMISSIONS = frozenset(
    {
        "llm.invoke",
        "project.read",
        "project.write",
        "provider.route_override",
        "cross_consumer.invoke",
    }
)


@dataclass(frozen=True)
class LlmConsumerAdapterBoundary:
    consumer: str
    capability: CapabilityName
    adapter_kind: str
    business_validation_owner: str
    routing_owner: str
    observability_owner: str
    default_agent_role: AgentRole
    allowed_agent_roles: tuple[AgentRole, ...]
    allowed_permissions: tuple[AgentPermission, ...]

    def to_observability(self) -> dict[str, Any]:
        return {
            "consumer": self.consumer,
            "capability": self.capability,
            "adapter_kind": self.adapter_kind,
            "business_validation_owner": self.business_validation_owner,
            "routing_owner": self.routing_owner,
            "observability_owner": self.observability_owner,
            "default_agent_role": self.default_agent_role,
            "allowed_agent_roles": list(self.allowed_agent_roles),
            "allowed_permissions": list(self.allowed_permissions),
        }


@dataclass(frozen=True)
class AgentBoundaryDecision:
    consumer: str
    agent_role: AgentRole
    allowed: bool
    denied_reasons: tuple[str, ...]
    requested_permissions: tuple[AgentPermission, ...]
    denied_permissions: tuple[AgentPermission, ...]
    unknown_permissions: tuple[str, ...] = ()

    def to_observability(self) -> dict[str, Any]:
        return {
            "consumer": self.consumer,
            "agent_role": self.agent_role,
            "allowed": self.allowed,
            "denied_reasons": list(self.denied_reasons),
            "requested_permissions": list(self.requested_permissions),
            "denied_permissions": list(self.denied_permissions),
            "unknown_permissions": list(self.unknown_permissions),
        }


_CONSUMER_BOUNDARY_TABLE: dict[str, LlmConsumerAdapterBoundary] = {
    "agent_core.tool_dispatch": LlmConsumerAdapterBoundary(
        consumer="agent_core.tool_dispatch",
        capability="agent_tool_dispatch",
        adapter_kind="orchestration_adapter",
        business_validation_owner="agent_core.schema_validation",
        routing_owner="agent_core.runtime_dispatcher",
        observability_owner="agent_core.events_and_tool_results",
        default_agent_role="orchestration_runtime",
        allowed_agent_roles=("orchestration_runtime", "user_facing_assistant"),
        allowed_permissions=("llm.invoke", "project.read", "project.write", "provider.route_override"),
    ),
    "writing.llm_action": LlmConsumerAdapterBoundary(
        consumer="writing.llm_action",
        capability="writing_action",
        adapter_kind="business_adapter",
        business_validation_owner="writing.api_and_service",
        routing_owner="llm.platformization_routing",
        observability_owner="writing.llm_action_service",
        default_agent_role="business_capability_wrapper",
        allowed_agent_roles=("business_capability_wrapper",),
        allowed_permissions=("llm.invoke", "project.read", "project.write"),
    ),
    "llm_report.generate": LlmConsumerAdapterBoundary(
        consumer="llm_report.generate",
        capability="report_generation",
        adapter_kind="business_adapter",
        business_validation_owner="llm_report.api_and_generator",
        routing_owner="llm.platformization_routing",
        observability_owner="llm_report.api",
        default_agent_role="business_capability_wrapper",
        allowed_agent_roles=("business_capability_wrapper",),
        allowed_permissions=("llm.invoke", "project.read"),
    ),
    "workflow_graph.llm_call": LlmConsumerAdapterBoundary(
        consumer="workflow_graph.llm_call",
        capability="workflow_llm_call",
        adapter_kind="orchestration_adapter",
        business_validation_owner="workflow_graph.executor",
        routing_owner="llm.platformization_routing",
        observability_owner="workflow_graph.executor",
        default_agent_role="orchestration_runtime",
        allowed_agent_roles=("orchestration_runtime", "user_facing_assistant"),
        allowed_permissions=("llm.invoke", "project.read", "provider.route_override"),
    ),
}


def _norm_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def normalize_capability(value: str | None) -> CapabilityName:
    candidate = (_norm_text(value) or "general_chat").lower()
    if candidate in _KNOWN_CAPABILITIES:
        return candidate  # type: ignore[return-value]
    return "general_chat"


def resolve_consumer_adapter_boundary(consumer: str | None) -> LlmConsumerAdapterBoundary:
    normalized_consumer = _norm_text(consumer) or "general_chat.consumer"
    known = _CONSUMER_BOUNDARY_TABLE.get(normalized_consumer)
    if known is not None:
        return known
    return LlmConsumerAdapterBoundary(
        consumer=normalized_consumer,
        capability="general_chat",
        adapter_kind="business_adapter",
        business_validation_owner="consumer_adapter",
        routing_owner="llm.platformization_routing",
        observability_owner="consumer_adapter",
        default_agent_role="business_capability_wrapper",
        allowed_agent_roles=("business_capability_wrapper",),
        allowed_permissions=("llm.invoke", "project.read"),
    )


def normalize_agent_role(value: str | None, *, consumer: str | None = None) -> AgentRole:
    candidate = (_norm_text(value) or "").lower()
    if candidate in _KNOWN_AGENT_ROLES:
        return candidate  # type: ignore[return-value]
    return resolve_consumer_adapter_boundary(consumer).default_agent_role


def evaluate_agent_permission_boundary(
    *,
    consumer: str,
    agent_role: str | None,
    requested_permissions: list[str] | tuple[str, ...] | set[str] | None,
) -> AgentBoundaryDecision:
    boundary = resolve_consumer_adapter_boundary(consumer)
    resolved_role = normalize_agent_role(agent_role, consumer=consumer)
    requested, unknown = _normalize_permissions(requested_permissions)
    requested = tuple(requested)
    unknown_permissions = tuple(unknown)
    denied_reasons: list[str] = []
    denied_permissions: list[AgentPermission] = []
    if resolved_role not in boundary.allowed_agent_roles:
        denied_reasons.append("agent_role_not_allowed_for_consumer")
    if unknown_permissions:
        denied_reasons.append("unknown_permission_requested")
    for permission in requested:
        if permission not in boundary.allowed_permissions:
            denied_permissions.append(permission)
    if denied_permissions:
        denied_reasons.append("permission_not_allowed_for_consumer")
    return AgentBoundaryDecision(
        consumer=boundary.consumer,
        agent_role=resolved_role,
        allowed=not denied_reasons,
        denied_reasons=tuple(denied_reasons),
        requested_permissions=requested,
        denied_permissions=tuple(denied_permissions),
        unknown_permissions=unknown_permissions,
    )


@dataclass(frozen=True)
class LlmRequestIdentity:
    consumer: str
    project_key: str | None
    trace_id: str
    request_id: str | None
    actor_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "consumer": self.consumer,
            "project_key": self.project_key,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "actor_id": self.actor_id,
        }


@dataclass(frozen=True)
class LlmRoutingDecision:
    service_name: str
    capability: CapabilityName
    provider: str | None
    model: str | None
    temperature: float | None
    max_tokens: int | None
    top_p: float | None
    route_kind: str
    field_sources: dict[str, ValueSource]
    provider_hint_unapplied: bool

    def invoke_options(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
        }

    def to_observability(self) -> dict[str, Any]:
        return {
            "service_name": self.service_name,
            "capability": self.capability,
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "route_kind": self.route_kind,
            "field_sources": dict(self.field_sources),
            "provider_hint_unapplied": self.provider_hint_unapplied,
        }


def resolve_request_identity(
    *,
    consumer: str,
    trace_id: str | None,
    request_id: str | None,
    project_key: str | None = None,
    actor_id: str | None = None,
    trace_fallback_seed: str | None = None,
) -> LlmRequestIdentity:
    normalized_request_id = _norm_text(request_id)
    resolved_trace_id = _norm_text(trace_id) or normalized_request_id or _norm_text(trace_fallback_seed) or f"{consumer}-auto"
    return LlmRequestIdentity(
        consumer=consumer,
        project_key=_norm_text(project_key),
        trace_id=resolved_trace_id,
        request_id=normalized_request_id,
        actor_id=_norm_text(actor_id),
    )


def resolve_routing_decision(
    *,
    service_name: str,
    capability: str | None,
    request_overrides: Mapping[str, Any] | None,
    service_config: Mapping[str, Any] | None,
    default_provider: str | None,
    default_model: str | None,
) -> LlmRoutingDecision:
    req = dict(request_overrides or {})
    cfg = dict(service_config or {})
    field_sources: dict[str, ValueSource] = {}

    provider, provider_source = _pick_value(
        request_value=req.get("provider"),
        config_value=cfg.get("provider"),
        default_value=default_provider,
    )
    field_sources["provider"] = provider_source

    model, model_source = _pick_value(
        request_value=req.get("model"),
        config_value=cfg.get("model"),
        default_value=default_model,
    )
    field_sources["model"] = model_source

    temperature, temperature_source = _pick_float(
        request_value=req.get("temperature"),
        config_value=cfg.get("temperature"),
        default_value=None,
    )
    field_sources["temperature"] = temperature_source

    max_tokens, max_tokens_source = _pick_int(
        request_value=req.get("max_tokens"),
        config_value=cfg.get("max_tokens"),
        default_value=None,
    )
    field_sources["max_tokens"] = max_tokens_source

    top_p, top_p_source = _pick_float(
        request_value=req.get("top_p"),
        config_value=cfg.get("top_p"),
        default_value=None,
    )
    field_sources["top_p"] = top_p_source

    if "request" in field_sources.values():
        route_kind = "request_override"
    elif "config" in field_sources.values():
        route_kind = "service_config"
    else:
        route_kind = "provider_default"

    return LlmRoutingDecision(
        service_name=str(_norm_text(service_name) or "default"),
        capability=normalize_capability(capability),
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        route_kind=route_kind,
        field_sources=field_sources,
        provider_hint_unapplied=bool(_norm_text(req.get("provider")) and _norm_text(req.get("provider")) != _norm_text(default_provider)),
    )


def build_trace_audit_record(
    *,
    identity: LlmRequestIdentity,
    routing: LlmRoutingDecision,
    status: str,
    degraded: bool,
    error_code: str | None = None,
    error_detail: str | None = None,
) -> dict[str, Any]:
    return {
        "consumer": identity.consumer,
        "project_key": identity.project_key,
        "trace_id": identity.trace_id,
        "request_id": identity.request_id,
        "actor_id": identity.actor_id,
        "service_name": routing.service_name,
        "capability": routing.capability,
        "route_kind": routing.route_kind,
        "model": routing.model,
        "provider": routing.provider,
        "status": status,
        "degraded": degraded,
        "error_code": _norm_text(error_code),
        "error_detail": _norm_text(error_detail),
    }


def _normalize_permissions(
    permissions: list[str] | tuple[str, ...] | set[str] | None,
) -> tuple[list[AgentPermission], list[str]]:
    out: list[AgentPermission] = []
    unknown: list[str] = []
    for item in permissions or []:
        normalized = str(item or "").strip().lower()
        if normalized in _KNOWN_AGENT_PERMISSIONS:
            out.append(normalized)  # type: ignore[arg-type]
        elif normalized:
            unknown.append(normalized)
    # Keep deterministic order while preserving first-seen semantic.
    deduped: list[AgentPermission] = []
    seen: set[str] = set()
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    deduped_unknown: list[str] = []
    seen_unknown: set[str] = set()
    for item in unknown:
        if item in seen_unknown:
            continue
        seen_unknown.add(item)
        deduped_unknown.append(item)
    return deduped, deduped_unknown


def _pick_value(*, request_value: Any, config_value: Any, default_value: Any) -> tuple[str | None, ValueSource]:
    req = _norm_text(request_value)
    if req is not None:
        return req, "request"
    cfg = _norm_text(config_value)
    if cfg is not None:
        return cfg, "config"
    default = _norm_text(default_value)
    if default is not None:
        return default, "default"
    return None, "derived"


def _pick_float(*, request_value: Any, config_value: Any, default_value: float | None) -> tuple[float | None, ValueSource]:
    raw_req = _norm_text(request_value)
    if raw_req is not None:
        try:
            return float(raw_req), "request"
        except Exception:  # noqa: BLE001
            pass

    raw_cfg = _norm_text(config_value)
    if raw_cfg is not None:
        try:
            return float(raw_cfg), "config"
        except Exception:  # noqa: BLE001
            pass

    if default_value is not None:
        return float(default_value), "default"
    return None, "derived"


def _pick_int(*, request_value: Any, config_value: Any, default_value: int | None) -> tuple[int | None, ValueSource]:
    raw_req = _norm_text(request_value)
    if raw_req is not None:
        try:
            return int(raw_req), "request"
        except Exception:  # noqa: BLE001
            pass

    raw_cfg = _norm_text(config_value)
    if raw_cfg is not None:
        try:
            return int(raw_cfg), "config"
        except Exception:  # noqa: BLE001
            pass

    if default_value is not None:
        return int(default_value), "default"
    return None, "derived"
