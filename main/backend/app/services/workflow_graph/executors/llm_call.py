from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TypeGuard

from functorial_kit import Failure

from ...llm.config_loader import get_llm_config
from ...llm.platformization import (
    build_trace_audit_record,
    evaluate_agent_permission_boundary,
    normalize_agent_role,
    resolve_consumer_adapter_boundary,
    resolve_request_identity,
    resolve_routing_decision,
)
from ....settings.config import settings
from .kernel import (
    NodeExecutionContext,
    NodeEffectFailure,
    NodeEffectResult,
    WorkflowJsonObject,
    node_degraded,
    node_failed,
    node_success,
)
from ..contracts import WorkflowGraphCompileError, raise_workflow_graph_legacy, workflow_graph_failure
from ..schema import try_parse_workflow_json_object


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _mapping_value(value: object, key: str) -> object:
    if not _is_object_mapping(value):
        return None
    for raw_key, raw_value in value.items():
        if raw_key == key:
            return raw_value
    return None


def _json_object(value: object, *, field: str) -> WorkflowJsonObject:
    parsed = try_parse_workflow_json_object(value, field=field)
    if isinstance(parsed, Failure):
        message = f"{field} must be a JSON object"
        raise_workflow_graph_legacy(
            workflow_graph_failure(
                "contract_invalid",
                message,
                owner="workflow_graph.executors.llm_call",
                public_exception=WorkflowGraphCompileError,
                public_message=message,
                field=field,
                index=-1,
            )
        )
    return parsed


def _invoke_llm(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    top_p: float | None = None,
    extra: WorkflowJsonObject | None = None,
) -> str:
    from app.services.llm.ports import ChatModelOptions, resolve_llm_provider

    chat = resolve_llm_provider(settings.llm_provider or "").get_chat_model(
        ChatModelOptions(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            extra=dict(extra or {}),
        )
    )
    resp = chat.invoke(prompt)
    if isinstance(resp, str):
        return resp
    content = getattr(resp, "content", None)
    if content is not None:
        return str(content)
    mapping_content = _mapping_value(resp, "content")
    if mapping_content is not None:
        return str(mapping_content)
    return str(resp)


def invoke_workflow_llm_call_skill(payload: object) -> WorkflowJsonObject:
    normalized_payload = _json_object(payload, field="workflow.llm_call.payload")
    prompt = str(normalized_payload.get("prompt") or "").strip()
    if not prompt:
        raise_workflow_graph_legacy(workflow_graph_failure("contract_invalid", "prompt is required", owner="workflow_graph.executors.llm_call", public_exception=WorkflowGraphCompileError, public_message="prompt is required", field="prompt", index=-1))

    text = _invoke_llm(
        prompt,
        model=_as_str_or_none(normalized_payload.get("model")),
        temperature=_to_float(normalized_payload.get("temperature"), default=0.0),
        max_tokens=_to_int_or_none(normalized_payload.get("max_tokens")),
        top_p=_to_float_or_none(normalized_payload.get("top_p")),
        extra=_json_object(normalized_payload.get("extra") or {}, field="workflow.llm_call.extra"),
    )
    return {"text": text}


def _invoke_llm_via_skill(
    prompt: str,
    *,
    model: str | None,
    temperature: float,
    max_tokens: int | None,
    top_p: float | None,
    extra: WorkflowJsonObject,
    trace_id: str | None,
) -> str:
    from app.services.skill_runtime import invoke_skill

    invoked = invoke_skill(
        skill_id="workflow.llm_call",
        payload={
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "extra": dict(extra or {}),
        },
        context={
            "actor_role": "orchestration_runtime",
            "permissions": ["workflow.llm_call"],
            "trace_id": str(trace_id or "").strip() or "workflow-graph.workflow.llm_call",
            "consumer": "workflow_graph.llm_call.executor",
        },
    )
    result = _mapping_value(invoked, "result")
    text = _mapping_value(result, "text")
    if text is not None:
        return str(text)
    return str(result)


def run_llm_call_kernel(context: NodeExecutionContext) -> NodeEffectResult:
    validation = _assert_prompt_template_inputs(params=dict(context.params), context=context)
    if validation is not None:
        return validation
    params = dict(context.params)
    prompt = _build_prompt(params=params, context=context)
    normalized = _normalize_provider_params(params)
    prompt_class = _as_str_or_none(params.get("prompt_class"))
    service_name = _as_str_or_none(params.get("service_name")) or prompt_class or "workflow_llm_call"
    identity = resolve_request_identity(
        consumer="workflow_graph.llm_call",
        trace_id=_as_str_or_none(context.inputs.get("trace_id")),
        request_id=_as_str_or_none(context.inputs.get("request_id")),
        project_key=_as_str_or_none(context.inputs.get("project_key")),
        actor_id=_as_str_or_none(context.inputs.get("actor_id")),
        trace_fallback_seed=f"{context.correlation_id}:{context.node_id}",
    )
    boundary = resolve_consumer_adapter_boundary(identity.consumer)
    requested_permissions = _collect_requested_permissions(params=params, context=context)
    agent_boundary = evaluate_agent_permission_boundary(
        consumer=identity.consumer,
        agent_role=normalize_agent_role(
            _as_str_or_none(params.get("agent_role")) or _as_str_or_none(context.inputs.get("agent_role")),
            consumer=identity.consumer,
        ),
        requested_permissions=requested_permissions,
    )
    routing = resolve_routing_decision(
        service_name=service_name,
        capability="workflow_llm_call",
        request_overrides={
            "provider": _as_str_or_none(normalized.get("provider")),
            "model": _as_str_or_none(normalized.get("model")),
            "temperature": normalized.get("temperature"),
            "max_tokens": normalized.get("max_tokens"),
            "top_p": normalized.get("top_p"),
        },
        service_config=get_llm_config(service_name),
        default_provider=settings.llm_provider,
        default_model=None,
    )
    invoke_opts = routing.invoke_options()
    model = _as_str_or_none(invoke_opts.get("model"))
    temperature = _to_float(invoke_opts.get("temperature"), default=0.0)
    max_tokens = _to_int_or_none(invoke_opts.get("max_tokens"))
    top_p = _to_float_or_none(invoke_opts.get("top_p"))
    provider = routing.provider
    failure_code = "LLM_CALL_DEGRADED"
    cause_type: str | None = None
    cause_message: str | None = None
    if not agent_boundary.allowed:
        failure_code = "AGENT_PERMISSION_DENIED"
        degraded = True
        reason = f"agent_permission_denied:{','.join(agent_boundary.denied_reasons)}"
        text = _fallback_text(prompt, context)
        audit = build_trace_audit_record(
            identity=identity,
            routing=routing,
            status="blocked",
            degraded=True,
            error_code="AGENT_PERMISSION_DENIED",
            error_detail=reason,
        )
    else:
        try:
            extra_payload = {
                key: value
                for key, value in normalized.items()
                if key
                not in {
                    "provider",
                    "model",
                    "temperature",
                    "top_p",
                    "max_tokens",
                    "prompt_class",
                    "prompt_template",
                    "prompt",
                    "input_vars",
                    "output_vars",
                }
            }
            text = _invoke_llm_via_skill(
                prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                extra=extra_payload,
                trace_id=identity.trace_id,
            )
            degraded = False
            reason = None
            audit = build_trace_audit_record(
                identity=identity,
                routing=routing,
                status="succeeded",
                degraded=False,
            )
        except Exception as exc:  # noqa: BLE001
            failure_code = "LLM_CALL_DEGRADED"
            degraded = True
            reason = str(exc)
            cause_type = type(exc).__name__
            cause_message = str(exc)
            text = _fallback_text(prompt, context)
            audit = build_trace_audit_record(
                identity=identity,
                routing=routing,
                status="degraded",
                degraded=True,
                error_code="LLM_CALL_DEGRADED",
                error_detail=reason,
            )

    payload: WorkflowJsonObject = {
            "node_type": "llm_call",
            "prompt": prompt,
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "prompt_class": prompt_class,
            "text": text,
            "degraded": degraded,
            "degraded_reason": reason,
            "trace_id": identity.trace_id,
            "request_id": identity.request_id,
            "project_key": identity.project_key,
            "service_name": routing.service_name,
            "capability": routing.capability,
            "route_kind": routing.route_kind,
            "meta": {
                "trace_id": identity.trace_id,
                "request_id": identity.request_id,
                "project_key": identity.project_key,
                "llm": {"identity": identity.to_dict(), "routing": routing.to_observability(), "audit": audit},
                "consumer_boundary": boundary.to_observability(),
                "agent_boundary": agent_boundary.to_observability(),
            },
    }
    if degraded:
        return node_degraded(
            context,
            payload,
            NodeEffectFailure(
                code=failure_code,
                message=str(reason),
                owner="workflow_graph.kernel.llm_call",
                details={},
                cause_type=cause_type,
                cause_message=cause_message,
            ),
        )
    return node_success(context, payload)


def _build_prompt(*, params: WorkflowJsonObject, context: NodeExecutionContext) -> str:
    template = str(params.get("prompt_template") or "").strip()
    if template:
        scope = _build_prompt_scope(context=context, params=params)
        return _safe_format(template, scope)

    candidates = [params.get("prompt"), context.inputs.get("prompt"), context.inputs.get("query")]
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text

    if context.upstream_results:
        lines: list[str] = ["Summarize upstream workflow results."]
        for node_id, data in context.upstream_results.items():
            lines.append(f"- {node_id}: {str(data)[:300]}")
        return "\n".join(lines)

    return "Generate a concise response."


def _assert_prompt_template_inputs(
    *,
    params: WorkflowJsonObject,
    context: NodeExecutionContext,
) -> NodeEffectResult | None:
    template = str(params.get("prompt_template") or "").strip()
    if not template:
        return
    required = _extract_template_variables(template)
    missing = [name for name in required if name not in context.inputs]
    if missing:
        message = f"prompt_template_missing_inputs:{','.join(sorted(missing))}"
        return node_failed(
            context,
            "required_input_missing",
            message,
            owner="workflow_graph.kernel.llm_call",
            details={
                "field": "prompt_template",
                "index": -1,
                "missing": [name for name in sorted(missing)],
            },
        )
    return None


def _extract_template_variables(template: str) -> set[str]:
    names = set(re.findall(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", template))
    return {name for name in names if name not in {"run_id", "node_id", "prompt_class", "upstream"}}


def _normalize_provider_params(params: WorkflowJsonObject) -> WorkflowJsonObject:
    provider = str(params.get("provider") or "").strip().lower()
    normalized = dict(params)
    if provider in {"ollama", "local"}:
        # Keep generic keys for response contract, but allow provider-specific hints.
        if normalized.get("max_tokens") is not None and normalized.get("num_predict") is None:
            normalized["num_predict"] = normalized.get("max_tokens")
    return normalized


def _build_prompt_scope(*, context: NodeExecutionContext, params: WorkflowJsonObject) -> WorkflowJsonObject:
    scope: WorkflowJsonObject = {}
    scope.update(context.inputs)
    scope["node_id"] = context.node_id
    scope["run_id"] = context.correlation_id
    scope["prompt_class"] = params.get("prompt_class")
    scope["upstream"] = context.upstream_results
    for node_id, value in context.upstream_results.items():
        scope[f"upstream_{node_id}"] = value
    return scope


def _collect_requested_permissions(*, params: WorkflowJsonObject, context: NodeExecutionContext) -> list[str]:
    requested: list[str] = ["llm.invoke", "project.read"]
    if params.get("provider") or params.get("model"):
        requested.append("provider.route_override")
    raw_from_params = params.get("permission_scope")
    if isinstance(raw_from_params, list):
        requested.extend(str(item or "").strip() for item in raw_from_params)
    raw_from_inputs = context.inputs.get("permission_scope")
    if isinstance(raw_from_inputs, list):
        requested.extend(str(item or "").strip() for item in raw_from_inputs)
    return requested


def _safe_format(template: str, scope: WorkflowJsonObject) -> str:
    try:
        return template.format(**scope)
    except Exception:
        return template


def _fallback_text(prompt: str, context: NodeExecutionContext) -> str:
    upstream_keys = ", ".join(sorted(context.upstream_results.keys())) or "none"
    return (
        "[fallback-llm] "
        f"prompt={prompt[:120]} | "
        f"upstream={upstream_keys}"
    )


def _as_str_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _to_float(value: object, *, default: float) -> float:
    if not isinstance(value, str | int | float):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_float_or_none(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    if not isinstance(value, str | int | float):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None



def _to_int_or_none(value: object) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    if not isinstance(value, str | int | float):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None
