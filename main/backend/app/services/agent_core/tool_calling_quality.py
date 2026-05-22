from __future__ import annotations

import json
from collections import Counter
from types import SimpleNamespace
from typing import Any, Mapping

from .contracts import (
    AGENT_CORE_TOOL_CALL_CONTRACT_VERSION,
    AgentCoreRequest,
    CoreModelStep,
    CoreProvider,
    CoreToolCall,
    CoreToolResult,
    CoreToolSpec,
    core_tool_call_contract_shape,
)
from .core import AgentCore
from .fake_provider import FakeCoreProvider
from .json_provider import JsonCoreProvider
from .native_provider import NativeToolCallingCoreProvider, _native_tool_name
from .registry import CoreToolRegistry
from .validation import validate_tool_arguments


AGENT_CORE_TOOL_CALLING_QUALITY_CONTRACT_VERSION = "agent_core.tool_calling_quality.v1"

_PROVIDER_KEYS = (
    "fake_core_provider",
    "json_core_provider",
    "native_tool_calling_provider",
)
_TOOL_NAME = "agent.tool_calling_quality.echo"


def build_agent_core_tool_calling_quality_contract() -> dict[str, Any]:
    """Build the deterministic AgentCore native tool-calling quality boundary.

    This contract uses local provider fixtures only. It proves that fake, JSON,
    and native provider adapters produce the same CoreToolCall shape and runtime
    dispatch envelope, while explicitly keeping live external provider quality
    outside the deterministic gate.
    """

    rows = [_provider_quality_row(provider_key=provider_key) for provider_key in _PROVIDER_KEYS]
    failures = [
        f"{row['provider_key']}: {failure}"
        for row in rows
        for failure in list(row.get("failures") or [])
    ]
    deterministic_ready = not failures and all(row.get("fixture_status") == "ready" for row in rows)
    external_gap = _external_provider_live_gap()
    unsupported_claims = _unsupported_closure_claims()
    return {
        "contract_version": AGENT_CORE_TOOL_CALLING_QUALITY_CONTRACT_VERSION,
        "status": "passed" if deterministic_ready else "failed",
        "readiness_state": (
            "deterministic_tool_calling_ready_external_provider_live_gap_open"
            if deterministic_ready
            else "deterministic_tool_calling_blocked"
        ),
        "scope": "agent_core_tool_calling_quality_no_external_model_call",
        "deterministic_tool_calling_ready": deterministic_ready,
        "quality_gate": {
            "deterministic_tool_calling_ready": deterministic_ready,
            "validated_providers": list(_PROVIDER_KEYS),
            "validated_contracts": [
                AGENT_CORE_TOOL_CALL_CONTRACT_VERSION,
                "agent_core.runtime_tool_event_shape.v1",
                "agent_core.tool_schema_validation.v1",
            ],
            "live_model_calls": 0,
            "quality_claim_allowed": False,
        },
        "provider_tool_call_contracts": rows,
        "external_provider_live_gap": external_gap,
        "unsupported_closure_claims": unsupported_claims,
        "failures": failures,
    }


def validate_agent_core_tool_calling_quality_contract(contract: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    _expect(
        contract.get("contract_version") == AGENT_CORE_TOOL_CALLING_QUALITY_CONTRACT_VERSION,
        errors,
        "unexpected AgentCore tool-calling quality contract version",
    )
    _expect(contract.get("status") in {"passed", "failed"}, errors, "invalid status")
    _expect(
        contract.get("scope") == "agent_core_tool_calling_quality_no_external_model_call",
        errors,
        "unexpected scope",
    )
    _expect(
        contract.get("deterministic_tool_calling_ready") is True,
        errors,
        "deterministic tool calling is not ready",
    )
    gate = contract.get("quality_gate") if isinstance(contract.get("quality_gate"), Mapping) else {}
    _expect(gate.get("live_model_calls") == 0, errors, "deterministic gate made a live model call")
    _expect(gate.get("quality_claim_allowed") is False, errors, "deterministic gate allowed live quality claim")
    rows = [row for row in contract.get("provider_tool_call_contracts") or [] if isinstance(row, Mapping)]
    by_provider = {str(row.get("provider_key") or ""): row for row in rows}
    for provider_key in _PROVIDER_KEYS:
        row = by_provider.get(provider_key)
        _expect(row is not None, errors, f"provider row missing: {provider_key}")
        if row is None:
            continue
        _expect(row.get("fixture_status") == "ready", errors, f"provider fixture not ready: {provider_key}")
        _expect(row.get("step_type") == "tool_calls", errors, f"provider step did not request tools: {provider_key}")
        shape = row.get("tool_call_contract") if isinstance(row.get("tool_call_contract"), Mapping) else {}
        _expect(
            shape.get("contract_version") == AGENT_CORE_TOOL_CALL_CONTRACT_VERSION,
            errors,
            f"tool-call shape version drift: {provider_key}",
        )
        _expect(shape.get("shape_status") == "valid", errors, f"tool-call shape invalid: {provider_key}")
        _expect(shape.get("tool_name") == _TOOL_NAME, errors, f"tool name was not canonicalized: {provider_key}")
        _expect(shape.get("arguments_type") == "object", errors, f"arguments are not an object: {provider_key}")
        schema = row.get("schema_validation") if isinstance(row.get("schema_validation"), Mapping) else {}
        _expect(schema.get("status") == "passed", errors, f"schema validation failed: {provider_key}")
        runtime = row.get("runtime_dispatch") if isinstance(row.get("runtime_dispatch"), Mapping) else {}
        _expect(runtime.get("stop_reason") == "final_answer", errors, f"runtime did not finish: {provider_key}")
        event_sequence = [
            item.get("event_type")
            for item in runtime.get("tool_event_sequence") or []
            if isinstance(item, Mapping)
        ]
        _expect(
            event_sequence == ["tool_call_requested", "tool_call_started", "tool_result"],
            errors,
            f"runtime tool event sequence drift for {provider_key}: {event_sequence}",
        )
        result_counts = runtime.get("tool_result_status_counts") or {}
        _expect(result_counts.get("completed", 0) >= 1, errors, f"tool result did not complete: {provider_key}")
    native_row = by_provider.get("native_tool_calling_provider") or {}
    native_wire = native_row.get("provider_wire_contract") if isinstance(native_row, Mapping) else {}
    _expect(
        (native_wire or {}).get("wire_protocol") == "native_bind_tools_function_call",
        errors,
        "native provider wire contract missing",
    )
    _expect(
        (native_wire or {}).get("canonical_tool_name") == _TOOL_NAME,
        errors,
        "native provider canonical tool map drift",
    )
    gap = contract.get("external_provider_live_gap")
    _expect(isinstance(gap, Mapping), errors, "external provider live gap missing")
    if isinstance(gap, Mapping):
        _expect(gap.get("state") == "external_provider_live_gap", errors, "external provider gap state drift")
        _expect(gap.get("quality_claim_allowed") is False, errors, "external provider gap allowed quality claim")
        _expect(gap.get("live_model_calls") == 0, errors, "external provider gap recorded live calls")
    claim_codes = {
        str(row.get("code") or "")
        for row in contract.get("unsupported_closure_claims") or []
        if isinstance(row, Mapping)
    }
    _expect(
        "deterministic_fixture_proves_external_provider_quality" in claim_codes,
        errors,
        "missing fixture/live unsupported claim",
    )
    return errors


def _provider_quality_row(*, provider_key: str) -> dict[str, Any]:
    spec = _fixture_tool_spec()
    expected_call = _fixture_tool_call(provider_key)
    failures: list[str] = []
    try:
        step = _provider_for(provider_key).next_step(
            request=_fixture_request(provider_key),
            tools=[spec],
            transcript=[],
            remaining_budget={"max_iterations": 4, "iteration": 1, "max_tool_calls": 2, "remaining_tool_calls": 2},
        )
        calls = list(step.tool_calls or ())
        if step.step_type != "tool_calls":
            failures.append(f"step_type={step.step_type}")
        if len(calls) != 1:
            failures.append(f"tool_call_count={len(calls)}")
        tool_call = calls[0] if calls else expected_call
        shape = core_tool_call_contract_shape(tool_call, provider_key=provider_key)
        failures.extend(_tool_call_shape_failures(shape=shape, expected_call=expected_call))
        schema_errors = validate_tool_arguments(arguments=dict(tool_call.arguments or {}), input_schema=spec.input_schema)
        if schema_errors:
            failures.append(f"schema_validation_errors={schema_errors}")
        runtime = _run_runtime_fixture(provider_key=provider_key, spec=spec)
        failures.extend(_runtime_shape_failures(runtime))
        return {
            "provider_key": provider_key,
            "provider_path": _provider_path(provider_key),
            "fixture_status": "ready" if not failures else "failed",
            "fixture_type": "deterministic_no_network_tool_call_contract",
            "step_type": step.step_type,
            "model_path": step.metadata.get("model_path"),
            "tool_call_contract": shape,
            "schema_validation": {
                "status": "passed" if not schema_errors else "failed",
                "errors": schema_errors,
            },
            "runtime_dispatch": runtime,
            "provider_wire_contract": _provider_wire_contract(provider_key=provider_key, spec=spec),
            "external_quality_claim_allowed": False,
            "failures": failures,
        }
    except Exception as exc:  # noqa: BLE001 - this checker records fixture failures.
        return {
            "provider_key": provider_key,
            "provider_path": _provider_path(provider_key),
            "fixture_status": "failed",
            "fixture_type": "deterministic_no_network_tool_call_contract",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
            "failures": [f"{exc.__class__.__name__}: {exc}"],
        }


def _run_runtime_fixture(*, provider_key: str, spec: CoreToolSpec) -> dict[str, Any]:
    registry = CoreToolRegistry()
    registry.register(spec, _fixture_tool_handler)
    request = _fixture_request(provider_key)
    result = AgentCore(
        provider=_provider_for(provider_key),
        tool_registry=registry,
        tool_specs=registry.list_specs(),
    ).run(request)
    event_counts = Counter(event.event_type for event in result.events)
    result_counts = Counter(item.status for item in result.tool_results)
    tool_events = [
        {
            "contract_version": "agent_core.runtime_tool_event_shape.v1",
            "event_type": event.event_type,
            "call_id": event.call_id,
            "tool_name": _event_tool_name(event.payload),
            "has_tool_call": isinstance(event.payload.get("tool_call"), dict),
            "has_tool_spec": isinstance(event.payload.get("tool_spec"), dict),
            "has_tool_result": event.event_type == "tool_result",
        }
        for event in result.events
        if event.event_type in {"tool_call_requested", "tool_call_started", "tool_result"}
    ]
    return {
        "contract_version": "agent_core.runtime_dispatch.v1",
        "session_id": result.session_id,
        "turn_id": result.turn_id,
        "stop_reason": result.stop_reason,
        "final_answer_present": bool(result.final_answer),
        "event_type_counts": {name: event_counts[name] for name in sorted(event_counts)},
        "tool_result_status_counts": {name: result_counts[name] for name in sorted(result_counts)},
        "tool_event_sequence": tool_events,
        "tool_results": [
            {
                "call_id": item.call_id,
                "tool_name": item.tool_name,
                "status": item.status,
                "structured_contract_version": item.structured_content.get("contract_version"),
            }
            for item in result.tool_results
        ],
    }


def _provider_for(provider_key: str) -> CoreProvider:
    if provider_key == "fake_core_provider":
        return FakeCoreProvider(
            [
                CoreModelStep.tools(_fixture_tool_call(provider_key), model_path="fake_core_provider"),
                CoreModelStep.final("fake tool-calling fixture ready", model_path="fake_core_provider"),
            ]
        )
    if provider_key == "json_core_provider":
        return JsonCoreProvider(chat_model=_JsonToolCallingQualityChat(provider_key))
    if provider_key == "native_tool_calling_provider":
        return NativeToolCallingCoreProvider(chat_model=_NativeToolCallingQualityChat(provider_key))
    raise ValueError(f"unknown provider key: {provider_key}")


def _fixture_tool_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name=_TOOL_NAME,
        title="AgentCore tool-calling quality echo",
        description_for_model="Deterministic no-network echo tool for AgentCore tool-call contract quality.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 3},
                "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 4,
                },
            },
            "required": ["query", "limit", "tags"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "contract_version": {"type": "string"},
                "echo": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["contract_version", "echo", "limit"],
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="serial",
        project_service_id=_TOOL_NAME,
        metadata={"contract_version": "agent.tool_calling_quality.echo.v1"},
    )


def _fixture_request(provider_key: str) -> AgentCoreRequest:
    return AgentCoreRequest(
        message=f"Run deterministic AgentCore tool-calling quality fixture for {provider_key}.",
        session_id=f"agent-core-tool-calling-quality-{provider_key}",
        turn_id=f"turn-agent-core-tool-calling-quality-{provider_key}",
        project_key="demo_proj",
        max_iterations=4,
        max_tool_calls=2,
        context={
            "trace_id": f"trace-agent-core-tool-calling-quality-{provider_key}",
            "request_id": f"req-agent-core-tool-calling-quality-{provider_key}",
            "default_provider": provider_key,
            "default_model": "fixture",
        },
    )


def _fixture_tool_call(provider_key: str) -> CoreToolCall:
    return CoreToolCall(
        tool_name=_TOOL_NAME,
        arguments=_fixture_arguments(provider_key),
        call_id=f"call-agent-tool-calling-quality-{provider_key}",
        reason="deterministic AgentCore tool-calling quality fixture",
    )


def _fixture_arguments(provider_key: str) -> dict[str, Any]:
    return {
        "query": f"{provider_key}-contract-shape",
        "limit": 2,
        "tags": ["agent_core", provider_key],
    }


def _fixture_tool_handler(
    tool_call: CoreToolCall,
    tool_spec: CoreToolSpec,
    request: AgentCoreRequest,
    emit: Any,
) -> CoreToolResult:
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="completed",
        model_summary="AgentCore tool-calling quality fixture completed.",
        structured_content={
            "contract_version": "agent.tool_calling_quality.echo.result.v1",
            "echo": str(tool_call.arguments.get("query") or ""),
            "limit": int(tool_call.arguments.get("limit") or 0),
            "provider_key": str((tool_call.arguments.get("tags") or [""])[-1]),
        },
    )


def _provider_wire_contract(*, provider_key: str, spec: CoreToolSpec) -> dict[str, Any]:
    if provider_key == "native_tool_calling_provider":
        native_tools, name_map = NativeToolCallingCoreProvider._to_native_tools([spec])
        native = native_tools[0] if native_tools else {}
        function = native.get("function") if isinstance(native.get("function"), dict) else {}
        native_name = str(function.get("name") or "")
        return {
            "wire_protocol": "native_bind_tools_function_call",
            "native_tool_name": native_name,
            "canonical_tool_name": name_map.get(native_name),
            "safe_name_changed": native_name != spec.name,
            "parameters_additional_properties": (function.get("parameters") or {}).get("additionalProperties"),
            "raw_response_shape": "OpenAI additional_kwargs.tool_calls[].function.arguments JSON string",
        }
    if provider_key == "json_core_provider":
        return {
            "wire_protocol": "json_tool_call_protocol",
            "tool_call_array_key": "tool_calls",
            "argument_key": "arguments",
            "raw_response_shape": "JSON object with type=tool_calls",
        }
    return {
        "wire_protocol": "core_model_step_fixture",
        "raw_response_shape": "CoreModelStep.tools(CoreToolCall)",
    }


def _external_provider_live_gap() -> dict[str, Any]:
    return {
        "state": "external_provider_live_gap",
        "live_model_calls": 0,
        "quality_claim_allowed": False,
        "auto_promotion_allowed": False,
        "gap_reason": (
            "The deterministic fixtures prove provider adapter shape only; they do not measure "
            "the configured external model's live native tool-call reliability, latency, or schema adherence."
        ),
        "required_next_evidence": (
            "Bounded live replay against the selected external provider with timeout, model id, "
            "tool-call response shape, schema-adherence counts, and failure classification."
        ),
    }


def _unsupported_closure_claims() -> list[dict[str, str]]:
    return [
        {
            "code": "deterministic_fixture_proves_external_provider_quality",
            "claim": "The local deterministic fixture proves live external provider tool-calling quality.",
            "reason": "The fixture uses in-process fake chat objects and spends zero external model calls.",
            "required_next_evidence": "Run a bounded live provider probe and record model id, raw tool-call shape, and schema adherence.",
        },
        {
            "code": "native_tool_calling_quality_closed_without_live_replay",
            "claim": "Native tool-calling production quality is closed.",
            "reason": "Native adapter shape is ready, but production reliability remains unmeasured for the selected provider.",
            "required_next_evidence": "Live replay with multiple calls, malformed/edge schema pressure, and stable failure taxonomy.",
        },
    ]


def _tool_call_shape_failures(*, shape: Mapping[str, Any], expected_call: CoreToolCall) -> list[str]:
    failures: list[str] = []
    if shape.get("shape_status") != "valid":
        failures.append("tool_call_shape_invalid")
    if shape.get("contract_version") != AGENT_CORE_TOOL_CALL_CONTRACT_VERSION:
        failures.append("tool_call_contract_version_drift")
    if shape.get("tool_name") != expected_call.tool_name:
        failures.append(f"tool_name={shape.get('tool_name')}")
    if shape.get("call_id") != expected_call.call_id:
        failures.append(f"call_id={shape.get('call_id')}")
    if dict(shape.get("arguments") or {}) != dict(expected_call.arguments or {}):
        failures.append("arguments_drift")
    return failures


def _runtime_shape_failures(runtime: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if runtime.get("stop_reason") != "final_answer":
        failures.append(f"stop_reason={runtime.get('stop_reason')}")
    if not runtime.get("final_answer_present"):
        failures.append("final_answer_missing")
    sequence = [
        item.get("event_type")
        for item in runtime.get("tool_event_sequence") or []
        if isinstance(item, Mapping)
    ]
    if sequence != ["tool_call_requested", "tool_call_started", "tool_result"]:
        failures.append(f"tool_event_sequence={sequence}")
    result_counts = runtime.get("tool_result_status_counts") or {}
    if result_counts.get("completed", 0) < 1:
        failures.append("completed_tool_result_missing")
    return failures


def _event_tool_name(payload: Mapping[str, Any]) -> str | None:
    tool_call = payload.get("tool_call") if isinstance(payload.get("tool_call"), Mapping) else None
    if tool_call is not None:
        return str(tool_call.get("tool_name") or "")
    return str(payload.get("tool_name") or "") or None


def _provider_path(provider_key: str) -> str:
    return {
        "fake_core_provider": "app.services.agent_core.fake_provider.FakeCoreProvider",
        "json_core_provider": "app.services.agent_core.json_provider.JsonCoreProvider",
        "native_tool_calling_provider": "app.services.agent_core.native_provider.NativeToolCallingCoreProvider",
    }.get(provider_key, "unknown")


def _expect(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


class _JsonToolCallingQualityChat:
    def __init__(self, provider_key: str) -> None:
        self.provider_key = provider_key
        self.calls = 0

    def invoke(self, prompt: Any) -> SimpleNamespace:
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "type": "tool_calls",
                        "tool_calls": [
                            {
                                "tool_name": _TOOL_NAME,
                                "arguments": _fixture_arguments(self.provider_key),
                                "call_id": f"call-agent-tool-calling-quality-{self.provider_key}",
                                "reason": "JSON provider deterministic tool-call quality fixture",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        return SimpleNamespace(
            content=json.dumps(
                {
                    "type": "final_answer",
                    "content": f"{self.provider_key} tool-calling fixture ready",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )


class _NativeToolCallingQualityChat:
    def __init__(self, provider_key: str) -> None:
        self.provider_key = provider_key
        self.calls = 0
        self.bound_tools: list[dict[str, Any]] = []

    def bind_tools(self, tools: Any) -> "_NativeToolCallingQualityChat":
        self.bound_tools = [dict(tool) for tool in list(tools or []) if isinstance(tool, dict)]
        return self

    def invoke(self, messages: Any) -> SimpleNamespace:
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": f"call-agent-tool-calling-quality-{self.provider_key}",
                            "type": "function",
                            "function": {
                                "name": _native_tool_name(_TOOL_NAME),
                                "arguments": json.dumps(_fixture_arguments(self.provider_key), sort_keys=True),
                            },
                        }
                    ]
                },
            )
        return SimpleNamespace(content=f"{self.provider_key} tool-calling fixture ready", tool_calls=[])
