from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Mapping

from .contracts import (
    AGENT_CORE_TOOL_CALL_CONTRACT_VERSION,
    AgentCoreRequest,
    AgentCoreRunResult,
    CoreEvent,
    CoreModelStep,
    CoreToolCall,
    CoreToolResult,
    CoreToolSpec,
    core_tool_call_contract_shape,
)
from .core import AgentCore
from .fake_provider import FakeCoreProvider
from .platform_contract import build_provider_capability_matrix
from .provider_readiness import build_agent_core_provider_live_readiness_contract
from .registry import CoreToolRegistry
from .tool_calling_quality import build_agent_core_tool_calling_quality_contract


AGENT_CORE_PROVIDER_TRACE_READBACK_CONTRACT_VERSION = "agent_core.provider_trace_readback.v1"
AGENT_CORE_STATUS_DATA_ERROR_META_COMPAT_VERSION = "agent_core.status_data_error_meta.compat.v1"
AGENT_CORE_PROVIDER_TRACE_REDACTION_REPLAY_VERSION = "agent_core.provider_trace_redaction_replay.v1"

_TOOL_NAME = "agent.provider_trace.echo"
_CALL_ID = "call-agent-provider-trace-readback"
_TRACE_ID = "trace-agent-core-provider-trace-readback"
_REQUEST_ID = "req-agent-core-provider-trace-readback"
_REDACTION_MARKER = "[REDACTED]"
_SENSITIVE_REQUEST_BODY = (
    "wave19-provider-trace-sensitive-request-body::"
    "customer=demo-account;api_key=fixture-openai-key;notes=private strategy memo"
)
_SENSITIVE_TOOL_QUERY = (
    "wave19-provider-trace-sensitive-tool-query::"
    "authorization=bearer fixture-token;prompt=private provider replay body"
)


def build_agent_core_provider_trace_readback_contract() -> dict[str, Any]:
    """Build a deterministic provider-trace readback for the AgentCore live gap.

    This checker intentionally uses the fake provider only. It proves that the
    runtime exposes a stable trace and tool-call envelope while keeping the real
    external provider call marked open for a later bounded live probe.
    """

    registry = CoreToolRegistry()
    spec = _fixture_tool_spec()
    registry.register(spec, _fixture_tool_handler)
    tool_call = _fixture_tool_call()
    provider = FakeCoreProvider(
        [
            CoreModelStep.tools(tool_call, model_path="fake_core_provider"),
            CoreModelStep.final("AgentCore provider trace readback completed.", model_path="fake_core_provider"),
        ]
    )
    request = _fixture_request()
    result = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(request)
    provider_trace = _provider_trace_readback(provider=provider)
    tool_call_envelope = _tool_call_envelope_readback(result=result, tool_call=tool_call)
    status_envelope = _status_data_error_meta_readback(result=result)
    input_contracts = _input_contract_readbacks()
    redaction_replay = _redaction_replay_readback(request=request, provider=provider, result=result, tool_call=tool_call)
    failures = _contract_failures(
        result=result,
        provider_trace=provider_trace,
        tool_call_envelope=tool_call_envelope,
        status_envelope=status_envelope,
        input_contracts=input_contracts,
        redaction_replay=redaction_replay,
    )
    deterministic_ready = not failures
    return {
        "contract_version": AGENT_CORE_PROVIDER_TRACE_READBACK_CONTRACT_VERSION,
        "status": "passed" if deterministic_ready else "failed",
        "readiness_state": (
            "deterministic_provider_trace_redaction_ready_real_external_provider_call_open"
            if deterministic_ready
            else "deterministic_provider_trace_blocked"
        ),
        "scope": "fake_provider_trace_redaction_tool_call_envelope_readback_no_external_model_call",
        "deterministic_provider_trace_ready": deterministic_ready,
        "provider_trace_redaction_ready": redaction_replay.get("status") == "passed",
        "real_external_provider_call_open": True,
        "external_model_calls": 0,
        "provider_trace": provider_trace,
        "tool_call_envelope": tool_call_envelope,
        "status_data_error_meta_compatibility": status_envelope,
        "input_contract_readbacks": input_contracts,
        "redaction_replay": redaction_replay,
        "unsupported_closure_claims": _unsupported_closure_claims(),
        "failures": failures,
    }


def validate_agent_core_provider_trace_readback_contract(contract: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    _expect(
        contract.get("contract_version") == AGENT_CORE_PROVIDER_TRACE_READBACK_CONTRACT_VERSION,
        errors,
        "unexpected provider trace readback contract version",
    )
    _expect(contract.get("status") in {"passed", "failed"}, errors, "invalid status")
    _expect(
        contract.get("scope") == "fake_provider_trace_redaction_tool_call_envelope_readback_no_external_model_call",
        errors,
        "unexpected scope",
    )
    _expect(contract.get("deterministic_provider_trace_ready") is True, errors, "deterministic provider trace is not ready")
    _expect(contract.get("provider_trace_redaction_ready") is True, errors, "provider trace redaction is not ready")
    _expect(contract.get("real_external_provider_call_open") is True, errors, "real external provider call is not marked open")
    _expect(contract.get("external_model_calls") == 0, errors, "deterministic provider trace spent external model calls")
    _expect(not contract.get("failures"), errors, f"contract failures present: {contract.get('failures')}")

    trace = contract.get("provider_trace") if isinstance(contract.get("provider_trace"), Mapping) else {}
    _expect(trace.get("provider_key") == "fake_core_provider", errors, "fake provider trace missing")
    _expect(trace.get("call_count") == 2, errors, "fake provider call count drift")
    _expect(trace.get("trace_status") == "passed", errors, "fake provider trace status drift")
    calls = [item for item in trace.get("calls") or [] if isinstance(item, Mapping)]
    _expect(len(calls) == 2, errors, "fake provider trace calls missing")
    if calls:
        first = calls[0]
        _expect(_TOOL_NAME in (first.get("tool_names") or []), errors, "fake provider did not see the tool name")
        _expect(first.get("context", {}).get("trace_id") == _TRACE_ID, errors, "trace_id missing from fake provider context")
    if len(calls) > 1:
        second = calls[1]
        _expect(second.get("tool_result_seen") is True, errors, "fake provider did not see tool result transcript")
        _expect(
            second.get("status_data_error_meta_seen_in_transcript") is True,
            errors,
            "fake provider transcript did not preserve status/data/error/meta envelope",
        )

    envelope = contract.get("tool_call_envelope") if isinstance(contract.get("tool_call_envelope"), Mapping) else {}
    _expect(envelope.get("contract_version") == "agent_core.provider_trace_tool_call_envelope.v1", errors, "tool-call envelope version drift")
    shape = envelope.get("tool_call_contract") if isinstance(envelope.get("tool_call_contract"), Mapping) else {}
    _expect(shape.get("contract_version") == AGENT_CORE_TOOL_CALL_CONTRACT_VERSION, errors, "tool-call shape version drift")
    _expect(shape.get("shape_status") == "valid", errors, "tool-call shape invalid")
    _expect(shape.get("tool_name") == _TOOL_NAME, errors, "tool-call tool name drift")
    _expect(shape.get("arguments_redacted") is True, errors, "tool-call shape arguments were not redacted")
    _expect(shape.get("raw_arguments_persisted") is False, errors, "tool-call shape persisted raw arguments")
    shape_arguments = shape.get("arguments") if isinstance(shape.get("arguments"), Mapping) else {}
    _expect(shape_arguments.get("redacted") is True, errors, "tool-call argument snapshot is not redacted")
    event_types = [
        item.get("event_type")
        for item in envelope.get("tool_event_sequence") or []
        if isinstance(item, Mapping)
    ]
    _expect(
        event_types == ["tool_call_requested", "tool_call_started", "tool_result"],
        errors,
        f"tool event sequence drift: {event_types}",
    )
    _expect(envelope.get("tool_result_status_counts", {}).get("completed") == 1, errors, "completed tool result count drift")

    compat = contract.get("status_data_error_meta_compatibility") if isinstance(contract.get("status_data_error_meta_compatibility"), Mapping) else {}
    _expect(compat.get("contract_version") == AGENT_CORE_STATUS_DATA_ERROR_META_COMPAT_VERSION, errors, "status/data/error/meta version drift")
    _expect(compat.get("compatible") is True, errors, "status/data/error/meta envelope not compatible")
    _expect(compat.get("status") == "ok", errors, "status/data/error/meta status drift")
    _expect(compat.get("error_is_null") is True, errors, "status/data/error/meta error should be null")
    _expect(compat.get("meta", {}).get("real_external_provider_call_open") is True, errors, "meta did not preserve real external open flag")

    input_contracts = contract.get("input_contract_readbacks") if isinstance(contract.get("input_contract_readbacks"), Mapping) else {}
    _expect(
        input_contracts.get("wave11_provider_matrix", {}).get("live_provider_claims") is False,
        errors,
        "Wave11 matrix readback claimed live provider availability",
    )
    _expect(
        input_contracts.get("wave13_live_provider_readiness", {}).get("readiness_state") == "partial",
        errors,
        "Wave13 readiness readback should remain partial",
    )
    _expect(
        input_contracts.get("wave14_tool_calling_quality", {}).get("external_provider_live_gap") == "external_provider_live_gap",
        errors,
        "Wave14 tool-calling quality gap readback drift",
    )
    redaction = contract.get("redaction_replay") if isinstance(contract.get("redaction_replay"), Mapping) else {}
    _expect(
        redaction.get("contract_version") == AGENT_CORE_PROVIDER_TRACE_REDACTION_REPLAY_VERSION,
        errors,
        "redaction replay version drift",
    )
    _expect(redaction.get("status") == "passed", errors, "redaction replay did not pass")
    _expect(redaction.get("raw_sensitive_values_absent") is True, errors, "raw sensitive values were persisted")
    _expect(redaction.get("tool_call_arguments_redacted") is True, errors, "tool-call replay arguments were not redacted")
    request_body = redaction.get("request_body") if isinstance(redaction.get("request_body"), Mapping) else {}
    _expect(request_body.get("redacted") is True, errors, "request body was not redacted")
    claim_codes = {
        str(item.get("code") or "")
        for item in contract.get("unsupported_closure_claims") or []
        if isinstance(item, Mapping)
    }
    _expect("real_external_provider_call_open" in claim_codes, errors, "missing real external provider open claim")
    return errors


def _fixture_tool_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name=_TOOL_NAME,
        title="AgentCore provider trace echo",
        description_for_model="Deterministic no-network echo tool for AgentCore provider trace readback.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 3},
                "trace_id": {"type": "string", "minLength": 3},
                "request_body": {"type": "string", "minLength": 3},
            },
            "required": ["query", "trace_id", "request_body"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "data": {"type": "object"},
                "error": {"type": ["object", "null"]},
                "meta": {"type": "object"},
            },
            "required": ["status", "data", "error", "meta"],
            "additionalProperties": False,
        },
        source="project",
        risk="read_only",
        permission="allow",
        concurrency="serial",
        project_service_id=_TOOL_NAME,
        metadata={"contract_version": "agent.provider_trace.echo.v1"},
    )


def _fixture_request() -> AgentCoreRequest:
    return AgentCoreRequest(
        message=f"Run deterministic AgentCore provider trace readback. Body: {_SENSITIVE_REQUEST_BODY}",
        session_id="agent-core-provider-trace-readback-session",
        turn_id="turn-agent-core-provider-trace-readback",
        project_key="demo_proj",
        max_iterations=4,
        max_tool_calls=2,
        context={
            "trace_id": _TRACE_ID,
            "request_id": _REQUEST_ID,
            "actor_id": "wave18-worker-7",
            "agent_role": "orchestration_runtime",
            "requested_permissions": ["llm.invoke", "project.read"],
            "default_provider": "fake_core_provider",
            "default_model": "fake-core-provider",
        },
    )


def _fixture_tool_call() -> CoreToolCall:
    return CoreToolCall(
        tool_name=_TOOL_NAME,
        arguments={"query": _SENSITIVE_TOOL_QUERY, "trace_id": _TRACE_ID, "request_body": _SENSITIVE_REQUEST_BODY},
        call_id=_CALL_ID,
        reason="deterministic provider trace readback fixture",
    )


def _fixture_tool_handler(
    tool_call: CoreToolCall,
    tool_spec: CoreToolSpec,
    request: AgentCoreRequest,
    emit: Any,
) -> CoreToolResult:
    context = dict(request.context or {})
    envelope = {
        "status": "ok",
        "data": {
            "contract_version": "agent.provider_trace.echo.result.v1",
            "query": _redacted_value_snapshot(tool_call.arguments.get("query")),
            "request_body": _redacted_value_snapshot(tool_call.arguments.get("request_body")),
            "project_key": request.project_key,
            "tool_name": tool_call.tool_name,
            "tool_call_id": tool_call.call_id,
        },
        "error": None,
        "meta": {
            "contract_version": "agent.provider_trace.echo.meta.v1",
            "trace_id": str(context.get("trace_id") or ""),
            "request_id": str(context.get("request_id") or ""),
            "provider_key": "fake_core_provider",
            "real_external_provider_call_open": True,
            "external_model_calls": 0,
        },
    }
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="completed",
        model_summary="AgentCore provider trace readback fixture completed.",
        structured_content=envelope,
    )


def _provider_trace_readback(*, provider: FakeCoreProvider) -> dict[str, Any]:
    calls = [_provider_call_snapshot(index=index, call=call) for index, call in enumerate(provider.calls, start=1)]
    trace_status = "passed" if len(calls) == 2 and calls[-1].get("status_data_error_meta_seen_in_transcript") is True else "failed"
    return {
        "contract_version": "agent_core.fake_provider_trace.v1",
        "provider_key": "fake_core_provider",
        "provider_path": "app.services.agent_core.fake_provider.FakeCoreProvider",
        "trace_status": trace_status,
        "call_count": len(calls),
        "calls": calls,
    }


def _provider_call_snapshot(*, index: int, call: Mapping[str, Any]) -> dict[str, Any]:
    transcript = [item for item in call.get("transcript") or [] if isinstance(item, Mapping)]
    return {
        "call_index": index,
        "message": _REDACTION_MARKER,
        "message_redaction": _redacted_value_snapshot(call.get("message")),
        "context": _selected_context(call.get("context") if isinstance(call.get("context"), Mapping) else {}),
        "tool_names": [str(name) for name in call.get("tool_names") or []],
        "transcript_roles": [str(item.get("role") or "") for item in transcript],
        "tool_result_seen": any(item.get("role") == "tool" for item in transcript),
        "status_data_error_meta_seen_in_transcript": _transcript_has_status_data_error_meta(transcript),
        "remaining_budget": dict(call.get("remaining_budget") or {}),
    }


def _tool_call_envelope_readback(*, result: AgentCoreRunResult, tool_call: CoreToolCall) -> dict[str, Any]:
    event_counts = Counter(event.event_type for event in result.events)
    result_counts = Counter(item.status for item in result.tool_results)
    tool_call_contract = core_tool_call_contract_shape(tool_call, provider_key="fake_core_provider")
    tool_call_contract["arguments"] = _redacted_arguments_snapshot(tool_call.arguments)
    tool_call_contract["arguments_redacted"] = True
    tool_call_contract["raw_arguments_persisted"] = False
    return {
        "contract_version": "agent_core.provider_trace_tool_call_envelope.v1",
        "tool_call_contract": tool_call_contract,
        "runtime_dispatch": {
            "contract_version": "agent_core.runtime_dispatch.v1",
            "session_id": result.session_id,
            "turn_id": result.turn_id,
            "stop_reason": result.stop_reason,
            "final_answer_present": bool(result.final_answer),
        },
        "event_type_counts": {name: event_counts[name] for name in sorted(event_counts)},
        "tool_result_status_counts": {name: result_counts[name] for name in sorted(result_counts)},
        "tool_event_sequence": [_tool_event_snapshot(event) for event in result.events if _is_tool_event(event)],
    }


def _redaction_replay_readback(
    *,
    request: AgentCoreRequest,
    provider: FakeCoreProvider,
    result: AgentCoreRunResult,
    tool_call: CoreToolCall,
) -> dict[str, Any]:
    event_replay = [_redacted_tool_event_replay(event) for event in result.events if _is_tool_event(event)]
    provider_call_replay = [
        {
            "call_index": index,
            "message": _redacted_value_snapshot(call.get("message")),
            "context_keys": sorted(str(key) for key in (call.get("context") or {}) if isinstance(call.get("context"), Mapping)),
            "tool_names": [str(name) for name in call.get("tool_names") or []],
            "transcript_roles": [
                str(item.get("role") or "")
                for item in call.get("transcript") or []
                if isinstance(item, Mapping)
            ],
        }
        for index, call in enumerate(provider.calls, start=1)
    ]
    replay = {
        "contract_version": AGENT_CORE_PROVIDER_TRACE_REDACTION_REPLAY_VERSION,
        "status": "failed",
        "redaction_marker": _REDACTION_MARKER,
        "request_body": _redacted_value_snapshot(request.message),
        "request_context_keys": sorted(str(key) for key in request.context),
        "provider_call_replay": provider_call_replay,
        "tool_call_envelope_replay": {
            "call_id": tool_call.call_id,
            "tool_name": tool_call.tool_name,
            "tool_call_arguments": _redacted_arguments_snapshot(tool_call.arguments),
            "event_sequence": event_replay,
        },
        "tool_call_arguments_redacted": True,
        "provider_messages_redacted": True,
        "raw_request_body_persisted": False,
        "raw_tool_arguments_persisted": False,
        "external_model_calls": 0,
    }
    replay["raw_sensitive_values_absent"] = _raw_sensitive_values_absent(replay, _sensitive_fixture_values())
    replay["status"] = (
        "passed"
        if replay["raw_sensitive_values_absent"]
        and replay["tool_call_arguments_redacted"]
        and replay["provider_messages_redacted"]
        and replay["raw_request_body_persisted"] is False
        and replay["raw_tool_arguments_persisted"] is False
        and len(event_replay) == 3
        else "failed"
    )
    return replay


def _status_data_error_meta_readback(*, result: AgentCoreRunResult) -> dict[str, Any]:
    tool_result = result.tool_results[0] if result.tool_results else None
    envelope = dict(tool_result.structured_content or {}) if tool_result is not None else {}
    data = envelope.get("data") if isinstance(envelope.get("data"), Mapping) else {}
    meta = envelope.get("meta") if isinstance(envelope.get("meta"), Mapping) else {}
    keys = sorted(str(key) for key in envelope)
    required_keys = ["data", "error", "meta", "status"]
    compatible = (
        keys == required_keys
        and envelope.get("status") == "ok"
        and isinstance(data, Mapping)
        and envelope.get("error") is None
        and isinstance(meta, Mapping)
        and meta.get("trace_id") == _TRACE_ID
        and meta.get("real_external_provider_call_open") is True
    )
    return {
        "contract_version": AGENT_CORE_STATUS_DATA_ERROR_META_COMPAT_VERSION,
        "compatible": compatible,
        "required_keys": required_keys,
        "present_keys": keys,
        "status": envelope.get("status"),
        "data_contract_version": data.get("contract_version"),
        "error_is_null": envelope.get("error") is None,
        "meta": dict(meta),
    }


def _input_contract_readbacks() -> dict[str, Any]:
    matrix = build_provider_capability_matrix(context={})
    readiness = build_agent_core_provider_live_readiness_contract(
        settings_source={"llm_provider": "openai", "openai_api_key": None},
        codex_cli_status={
            "available": False,
            "binary_available": False,
            "auth_available": False,
            "fallback_enabled": True,
            "model": None,
        },
    )
    quality = build_agent_core_tool_calling_quality_contract()
    matrix_entries = [item for item in matrix.get("entries") or [] if isinstance(item, Mapping)]
    matrix_by_provider = {str(item.get("provider_key") or ""): item for item in matrix_entries}
    selected_live = next(
        (
            item
            for item in readiness.get("live_availability", {}).get("providers") or []
            if isinstance(item, Mapping) and item.get("selected")
        ),
        {},
    )
    return {
        "wave11_provider_matrix": {
            "contract_version": matrix.get("contract_version"),
            "evaluation_mode": matrix.get("evaluation_mode"),
            "live_provider_claims": matrix.get("live_provider_claims"),
            "fake_core_provider_status": (matrix_by_provider.get("fake_core_provider") or {}).get("status"),
            "native_tool_calling_provider_status": (matrix_by_provider.get("native_tool_calling_provider") or {}).get("status"),
            "external_framework_adoption_status": (matrix.get("external_framework_boundary") or {}).get("adoption_status"),
        },
        "wave13_live_provider_readiness": {
            "contract_version": readiness.get("contract_version"),
            "status": readiness.get("status"),
            "readiness_state": readiness.get("readiness_state"),
            "selected_provider": (readiness.get("configured_provider") or {}).get("llm_provider"),
            "selected_live_probe_status": selected_live.get("live_probe_status"),
            "unsupported_claim_codes": _claim_codes(readiness.get("unsupported_closure_claims")),
        },
        "wave14_tool_calling_quality": {
            "contract_version": quality.get("contract_version"),
            "status": quality.get("status"),
            "deterministic_tool_calling_ready": quality.get("deterministic_tool_calling_ready"),
            "external_provider_live_gap": (quality.get("external_provider_live_gap") or {}).get("state"),
            "live_model_calls": (quality.get("quality_gate") or {}).get("live_model_calls"),
            "unsupported_claim_codes": _claim_codes(quality.get("unsupported_closure_claims")),
        },
    }


def _contract_failures(
    *,
    result: AgentCoreRunResult,
    provider_trace: Mapping[str, Any],
    tool_call_envelope: Mapping[str, Any],
    status_envelope: Mapping[str, Any],
    input_contracts: Mapping[str, Any],
    redaction_replay: Mapping[str, Any],
) -> list[str]:
    failures: list[str] = []
    if result.stop_reason != "final_answer":
        failures.append(f"stop_reason={result.stop_reason}")
    if not result.tool_results or result.tool_results[0].status != "completed":
        failures.append("completed_tool_result_missing")
    if provider_trace.get("trace_status") != "passed":
        failures.append("fake_provider_trace_failed")
    event_types = [
        item.get("event_type")
        for item in tool_call_envelope.get("tool_event_sequence") or []
        if isinstance(item, Mapping)
    ]
    if event_types != ["tool_call_requested", "tool_call_started", "tool_result"]:
        failures.append(f"tool_event_sequence={event_types}")
    shape = tool_call_envelope.get("tool_call_contract") if isinstance(tool_call_envelope.get("tool_call_contract"), Mapping) else {}
    if shape.get("shape_status") != "valid":
        failures.append("tool_call_shape_invalid")
    if shape.get("arguments_redacted") is not True or shape.get("raw_arguments_persisted") is not False:
        failures.append("tool_call_arguments_not_redacted")
    if status_envelope.get("compatible") is not True:
        failures.append("status_data_error_meta_envelope_incompatible")
    if input_contracts.get("wave11_provider_matrix", {}).get("live_provider_claims") is not False:
        failures.append("wave11_provider_matrix_live_claim_drift")
    if input_contracts.get("wave13_live_provider_readiness", {}).get("readiness_state") != "partial":
        failures.append("wave13_readiness_state_drift")
    if input_contracts.get("wave14_tool_calling_quality", {}).get("external_provider_live_gap") != "external_provider_live_gap":
        failures.append("wave14_external_provider_gap_drift")
    if redaction_replay.get("status") != "passed":
        failures.append("provider_trace_redaction_replay_failed")
    if redaction_replay.get("raw_sensitive_values_absent") is not True:
        failures.append("raw_sensitive_values_persisted")
    if redaction_replay.get("tool_call_arguments_redacted") is not True:
        failures.append("redacted_tool_call_envelope_replay_missing")
    return failures


def _unsupported_closure_claims() -> list[dict[str, str]]:
    return [
        {
            "code": "real_external_provider_call_open",
            "claim": "The selected real external provider has completed a live AgentCore tool-call probe.",
            "reason": "This Wave18 checker spends zero external model calls and only reads back the fake provider trace envelope.",
            "required_next_evidence": "Bounded live provider invocation with timeout, model id, raw response shape, latency, and failure classification.",
        },
        {
            "code": "fake_provider_trace_does_not_close_live_provider_quality",
            "claim": "A deterministic fake provider trace proves production provider quality.",
            "reason": "The fake provider proves runtime trace and envelope preservation only.",
            "required_next_evidence": "Live replay against the configured provider while preserving the same status/data/error/meta readback.",
        },
    ]


def _tool_event_snapshot(event: CoreEvent) -> dict[str, Any]:
    payload = dict(event.payload or {})
    tool_call = payload.get("tool_call") if isinstance(payload.get("tool_call"), Mapping) else {}
    tool_spec = payload.get("tool_spec") if isinstance(payload.get("tool_spec"), Mapping) else {}
    structured = payload.get("structured_content") if isinstance(payload.get("structured_content"), Mapping) else {}
    return {
        "contract_version": "agent_core.provider_trace_tool_event.v1",
        "event_type": event.event_type,
        "call_id": event.call_id,
        "tool_name": tool_call.get("tool_name") or payload.get("tool_name") or tool_spec.get("name"),
        "has_tool_call": isinstance(payload.get("tool_call"), Mapping),
        "has_tool_spec": isinstance(payload.get("tool_spec"), Mapping),
        "has_status_data_error_meta": _is_status_data_error_meta_envelope(structured),
        "permission": payload.get("permission"),
        "status": payload.get("status"),
    }


def _redacted_tool_event_replay(event: CoreEvent) -> dict[str, Any]:
    payload = dict(event.payload or {})
    tool_call = payload.get("tool_call") if isinstance(payload.get("tool_call"), Mapping) else {}
    structured = payload.get("structured_content") if isinstance(payload.get("structured_content"), Mapping) else {}
    return {
        "contract_version": "agent_core.provider_trace_redacted_tool_event.v1",
        "event_type": event.event_type,
        "call_id": event.call_id,
        "tool_name": tool_call.get("tool_name") or payload.get("tool_name"),
        "tool_call_arguments": _redacted_arguments_snapshot(tool_call.get("arguments") if isinstance(tool_call, Mapping) else {}),
        "structured_content": _status_envelope_redaction_snapshot(structured),
        "permission": payload.get("permission"),
        "status": payload.get("status"),
    }


def _is_tool_event(event: CoreEvent) -> bool:
    return event.event_type in {"tool_call_requested", "tool_call_started", "tool_result"}


def _transcript_has_status_data_error_meta(transcript: list[Mapping[str, Any]]) -> bool:
    for item in transcript:
        if item.get("role") != "tool":
            continue
        tool_result = item.get("tool_result") if isinstance(item.get("tool_result"), Mapping) else {}
        structured = tool_result.get("structured_content") if isinstance(tool_result.get("structured_content"), Mapping) else {}
        if _is_status_data_error_meta_envelope(structured):
            return True
    return False


def _is_status_data_error_meta_envelope(value: Mapping[str, Any]) -> bool:
    return sorted(str(key) for key in value) == ["data", "error", "meta", "status"]


def _selected_context(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "trace_id": value.get("trace_id"),
        "request_id": value.get("request_id"),
        "default_provider": value.get("default_provider"),
        "default_model": value.get("default_model"),
    }


def _status_envelope_redaction_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    if not value:
        return {"present": False}
    structured = dict(value or {})
    data = structured.get("data") if isinstance(structured.get("data"), Mapping) else {}
    meta = structured.get("meta") if isinstance(structured.get("meta"), Mapping) else {}
    return {
        "present": True,
        "has_status_data_error_meta": _is_status_data_error_meta_envelope(structured),
        "present_keys": sorted(str(key) for key in structured),
        "status": structured.get("status"),
        "data_keys": sorted(str(key) for key in data),
        "meta_keys": sorted(str(key) for key in meta),
        "raw_values_persisted": False,
    }


def _redacted_arguments_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "redacted": True,
            "type": type(value).__name__,
            "keys": [],
            "value_fingerprints": {},
            "raw_values_persisted": False,
        }
    arguments = dict(value or {})
    return {
        "redacted": True,
        "type": "object",
        "keys": sorted(str(key) for key in arguments),
        "value_fingerprints": {
            str(key): _redacted_value_snapshot(arguments[key])
            for key in sorted(arguments, key=lambda item: str(item))
        },
        "raw_values_persisted": False,
    }


def _redacted_value_snapshot(value: Any) -> dict[str, Any]:
    encoded = _canonical_json(value)
    if isinstance(value, str):
        value_type = "string"
        length = len(value)
    elif isinstance(value, Mapping):
        value_type = "object"
        length = len(value)
    elif isinstance(value, (list, tuple)):
        value_type = "array"
        length = len(value)
    elif value is None:
        value_type = "null"
        length = 0
    else:
        value_type = type(value).__name__
        length = len(encoded)
    return {
        "redacted": True,
        "marker": _REDACTION_MARKER,
        "type": value_type,
        "length": length,
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sensitive_fixture_values() -> list[str]:
    return [_SENSITIVE_REQUEST_BODY, _SENSITIVE_TOOL_QUERY]


def _raw_sensitive_values_absent(value: Mapping[str, Any], sensitive_values: list[str]) -> bool:
    encoded = _canonical_json(value)
    return all(item not in encoded for item in sensitive_values)


def _claim_codes(value: Any) -> list[str]:
    return sorted(
        str(item.get("code") or "")
        for item in value or []
        if isinstance(item, Mapping) and str(item.get("code") or "").strip()
    )


def _expect(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)
