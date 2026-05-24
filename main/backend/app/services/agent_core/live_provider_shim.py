from __future__ import annotations

from collections import Counter
import hashlib
import json
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Mapping

from .contracts import (
    AgentCoreRequest,
    CoreEvent,
    CoreToolCall,
    CoreToolResult,
    CoreToolSpec,
    core_tool_call_contract_shape,
)
from .core import AgentCore
from .native_provider import NativeToolCallingCoreProvider, _native_tool_name
from .registry import CoreToolRegistry


AGENT_CORE_REPO_LOCAL_LIVE_PROVIDER_SHIM_VERSION = "agent_core.repo_local_live_provider_shim.v1"

_PROVIDER_KEY = "repo_local_live_provider_shim"
_TOOL_NAME = "agent.provider_live_shim.echo"
_CALL_ID = "call-agent-provider-live-shim"
_TRACE_ID = "trace-agent-core-provider-live-shim"
_REQUEST_ID = "req-agent-core-provider-live-shim"
_REDACTION_MARKER = "[REDACTED]"
_SENSITIVE_REQUEST_BODY = (
    "wave55-live-provider-shim-sensitive-request::"
    "account=repo-local-demo;api_key=repo-local-fixture-key;prompt=private-live-shim-body"
)
_SENSITIVE_TOOL_QUERY = (
    "wave55-live-provider-shim-sensitive-tool-query::"
    "authorization=bearer repo-local-fixture-token;prompt=private-tool-body"
)


class RepoLocalLiveProviderShim:
    """OpenAI-compatible in-process provider shim for AgentCore live closure.

    The shim is intentionally not external evidence. It exposes a bounded,
    account/API/network-shaped invocation path that runs through the same
    native tool-call adapter and AgentCore loop without leaving the repo process.
    """

    provider_key = _PROVIDER_KEY
    model_id = "repo-local-agent-core-live-shim-v1"
    api_endpoint = "repo://agent-core/live-provider-shim"
    account_id = "repo-local-agent-core-live-shim-account"
    network_scope = "repo_local_in_process_no_external_network"

    def __init__(self) -> None:
        self.bound_tools: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.response_shapes: list[dict[str, Any]] = []

    def bind_tools(self, tools: Any) -> "RepoLocalLiveProviderShim":
        self.bound_tools = [dict(tool) for tool in list(tools or []) if isinstance(tool, dict)]
        return self

    def invoke(self, messages: Any) -> SimpleNamespace:
        self.calls.append(_invocation_snapshot(messages=messages, bound_tools=self.bound_tools))
        if len(self.calls) == 1:
            native_tool_name = _first_native_tool_name(self.bound_tools)
            arguments = _fixture_arguments()
            self.response_shapes.append(
                {
                    "response_index": len(self.calls),
                    "response_kind": "openai_compatible_tool_calls",
                    "tool_call_count": 1,
                    "function_name": native_tool_name,
                    "arguments_type": "json_string",
                    "arguments": _redacted_arguments_snapshot(arguments),
                    "raw_arguments_persisted": False,
                }
            )
            return SimpleNamespace(
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": _CALL_ID,
                            "type": "function",
                            "function": {
                                "name": native_tool_name,
                                "arguments": json.dumps(arguments, ensure_ascii=False, sort_keys=True),
                            },
                        }
                    ]
                },
            )

        self.response_shapes.append(
            {
                "response_index": len(self.calls),
                "response_kind": "final_answer",
                "tool_call_count": 0,
                "content_present": True,
                "raw_content_persisted": False,
            }
        )
        return SimpleNamespace(content="Repo-local live provider shim completed.", tool_calls=[])


def build_repo_local_live_provider_shim_evidence(*, timeout_ms: int = 1000) -> dict[str, Any]:
    shim = RepoLocalLiveProviderShim()
    started = perf_counter()
    try:
        registry = CoreToolRegistry()
        spec = _fixture_tool_spec()
        registry.register(spec, _fixture_tool_handler)
        request = _fixture_request(timeout_ms=timeout_ms)
        result = AgentCore(
            provider=NativeToolCallingCoreProvider(chat_model=shim),
            tool_registry=registry,
            tool_specs=registry.list_specs(),
        ).run(request)
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        return _evidence_from_result(
            shim=shim,
            result=result,
            timeout_ms=timeout_ms,
            latency_ms=elapsed_ms,
        )
    except Exception as exc:  # noqa: BLE001 - checker evidence records the failure class.
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        return {
            "contract_version": AGENT_CORE_REPO_LOCAL_LIVE_PROVIDER_SHIM_VERSION,
            "status": "failed",
            "closed": False,
            "closure_basis": "repo_local_live_provider_shim",
            "provider_key": _PROVIDER_KEY,
            "model_id": shim.model_id,
            "timeout_ms": int(timeout_ms),
            "latency_ms": elapsed_ms,
            "latency_status": "within_timeout" if elapsed_ms <= timeout_ms else "timeout_budget_exceeded",
            "external_provider_live_verified": False,
            "external_model_calls": 0,
            "repo_local_model_calls": len(shim.calls),
            "failure_taxonomy": f"repo_local_shim_exception:{exc.__class__.__name__}",
            "failures": [f"{exc.__class__.__name__}: {exc}"],
        }


def validate_repo_local_live_provider_shim_evidence(evidence: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    _expect(
        evidence.get("contract_version") == AGENT_CORE_REPO_LOCAL_LIVE_PROVIDER_SHIM_VERSION,
        errors,
        "unexpected repo-local live provider shim contract version",
    )
    _expect(evidence.get("status") == "passed", errors, "repo-local live provider shim did not pass")
    _expect(evidence.get("closed") is True, errors, "repo-local live provider shim did not close")
    _expect(evidence.get("closure_basis") == "repo_local_live_provider_shim", errors, "invalid closure basis")
    _expect(evidence.get("provider_key") == _PROVIDER_KEY, errors, "invalid repo-local provider key")
    _expect(evidence.get("external_provider_live_verified") is False, errors, "shim must not claim external provider evidence")
    _expect(evidence.get("external_model_calls") == 0, errors, "shim must not spend external model calls")
    _expect(evidence.get("repo_local_model_calls") == 2, errors, "shim call count drift")
    _expect(evidence.get("latency_status") == "within_timeout", errors, "shim exceeded timeout budget")
    invocation = evidence.get("provider_invocation") if isinstance(evidence.get("provider_invocation"), Mapping) else {}
    _expect(
        invocation.get("network_scope") == "repo_local_in_process_no_external_network",
        errors,
        "shim network scope must remain repo-local",
    )
    _expect(invocation.get("account_state") == "repo_local_shim_account_configured", errors, "shim account state missing")
    runtime = evidence.get("runtime_dispatch") if isinstance(evidence.get("runtime_dispatch"), Mapping) else {}
    _expect(runtime.get("stop_reason") == "final_answer", errors, "shim runtime did not finish")
    sequence = [
        item.get("event_type")
        for item in runtime.get("tool_event_sequence") or []
        if isinstance(item, Mapping)
    ]
    _expect(
        sequence == ["tool_call_requested", "tool_call_started", "tool_result"],
        errors,
        f"shim tool event sequence drift: {sequence}",
    )
    status_trace = evidence.get("status_data_error_meta_trace") if isinstance(evidence.get("status_data_error_meta_trace"), Mapping) else {}
    _expect(status_trace.get("compatible") is True, errors, "status/data/error/meta trace incompatible")
    tool_call = evidence.get("tool_call_readback") if isinstance(evidence.get("tool_call_readback"), Mapping) else {}
    _expect(tool_call.get("shape_status") == "valid", errors, "shim tool-call shape invalid")
    _expect(tool_call.get("tool_name") == _TOOL_NAME, errors, "shim tool-call canonical name drift")
    _expect(tool_call.get("arguments_redacted") is True, errors, "shim tool-call arguments were not redacted")
    redaction = evidence.get("redaction") if isinstance(evidence.get("redaction"), Mapping) else {}
    _expect(redaction.get("raw_sensitive_values_absent") is True, errors, "shim persisted raw sensitive values")
    _expect(not evidence.get("failures"), errors, f"shim failures present: {evidence.get('failures')}")
    return errors


def _evidence_from_result(
    *,
    shim: RepoLocalLiveProviderShim,
    result: Any,
    timeout_ms: int,
    latency_ms: float,
) -> dict[str, Any]:
    event_counts = Counter(event.event_type for event in result.events)
    result_counts = Counter(item.status for item in result.tool_results)
    tool_result = result.tool_results[0] if result.tool_results else None
    envelope = dict(tool_result.structured_content or {}) if tool_result is not None else {}
    status_trace = _status_data_error_meta_trace(envelope)
    tool_call_shape = core_tool_call_contract_shape(_fixture_tool_call(), provider_key=_PROVIDER_KEY)
    tool_call_shape["arguments"] = _redacted_arguments_snapshot(_fixture_arguments())
    tool_call_shape["arguments_redacted"] = True
    tool_call_shape["raw_arguments_persisted"] = False
    runtime = {
        "contract_version": "agent_core.repo_local_live_provider_shim.runtime_dispatch.v1",
        "session_id": result.session_id,
        "turn_id": result.turn_id,
        "stop_reason": result.stop_reason,
        "final_answer_present": bool(result.final_answer),
        "event_type_counts": {name: event_counts[name] for name in sorted(event_counts)},
        "tool_result_status_counts": {name: result_counts[name] for name in sorted(result_counts)},
        "tool_event_sequence": [_tool_event_snapshot(event) for event in result.events if _is_tool_event(event)],
    }
    evidence: dict[str, Any] = {
        "contract_version": AGENT_CORE_REPO_LOCAL_LIVE_PROVIDER_SHIM_VERSION,
        "status": "failed",
        "closed": False,
        "closure_basis": "repo_local_live_provider_shim",
        "provider_key": _PROVIDER_KEY,
        "model_id": shim.model_id,
        "timeout_ms": int(timeout_ms),
        "latency_ms": latency_ms,
        "latency_status": "within_timeout" if latency_ms <= timeout_ms else "timeout_budget_exceeded",
        "external_provider_live_verified": False,
        "external_model_calls": 0,
        "repo_local_model_calls": len(shim.calls),
        "provider_invocation": {
            "provider_key": _PROVIDER_KEY,
            "provider_path": "app.services.agent_core.live_provider_shim.RepoLocalLiveProviderShim",
            "agent_core_provider_path": "app.services.agent_core.native_provider.NativeToolCallingCoreProvider",
            "agent_core_runtime_path": "app.services.agent_core.core.AgentCore",
            "api_endpoint": shim.api_endpoint,
            "account_id": shim.account_id,
            "account_state": "repo_local_shim_account_configured",
            "network_scope": shim.network_scope,
        },
        "raw_response_shape_classification": {
            "contract_version": "agent_core.repo_local_live_provider_shim.response_shape.v1",
            "wire_protocol": "openai_compatible_native_tool_call",
            "responses": list(shim.response_shapes),
            "raw_response_persisted": False,
        },
        "tool_call_readback": tool_call_shape,
        "runtime_dispatch": runtime,
        "status_data_error_meta_trace": status_trace,
        "redaction": {
            "contract_version": "agent_core.repo_local_live_provider_shim.redaction.v1",
            "redaction_marker": _REDACTION_MARKER,
            "raw_request_body_persisted": False,
            "raw_tool_arguments_persisted": False,
            "raw_sensitive_values_absent": False,
        },
        "failure_taxonomy": "none",
        "failures": [],
    }
    evidence["redaction"]["raw_sensitive_values_absent"] = _raw_sensitive_values_absent(
        evidence,
        [_SENSITIVE_REQUEST_BODY, _SENSITIVE_TOOL_QUERY],
    )
    failures = _evidence_failures(evidence)
    evidence["failures"] = failures
    evidence["status"] = "passed" if not failures else "failed"
    evidence["closed"] = not failures
    evidence["failure_taxonomy"] = "none" if not failures else "repo_local_shim_contract_failure"
    return evidence


def _evidence_failures(evidence: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if evidence.get("latency_status") != "within_timeout":
        failures.append("timeout_budget_exceeded")
    if evidence.get("external_provider_live_verified") is not False:
        failures.append("external_provider_claimed")
    if evidence.get("external_model_calls") != 0:
        failures.append("external_model_calls_nonzero")
    if evidence.get("repo_local_model_calls") != 2:
        failures.append(f"repo_local_model_calls={evidence.get('repo_local_model_calls')}")
    runtime = evidence.get("runtime_dispatch") if isinstance(evidence.get("runtime_dispatch"), Mapping) else {}
    if runtime.get("stop_reason") != "final_answer":
        failures.append(f"stop_reason={runtime.get('stop_reason')}")
    if (runtime.get("tool_result_status_counts") or {}).get("completed", 0) < 1:
        failures.append("completed_tool_result_missing")
    sequence = [
        item.get("event_type")
        for item in runtime.get("tool_event_sequence") or []
        if isinstance(item, Mapping)
    ]
    if sequence != ["tool_call_requested", "tool_call_started", "tool_result"]:
        failures.append(f"tool_event_sequence={sequence}")
    trace = evidence.get("status_data_error_meta_trace") if isinstance(evidence.get("status_data_error_meta_trace"), Mapping) else {}
    if trace.get("compatible") is not True:
        failures.append("status_data_error_meta_incompatible")
    redaction = evidence.get("redaction") if isinstance(evidence.get("redaction"), Mapping) else {}
    if redaction.get("raw_sensitive_values_absent") is not True:
        failures.append("raw_sensitive_values_persisted")
    return failures


def _fixture_tool_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name=_TOOL_NAME,
        title="AgentCore repo-local live provider shim echo",
        description_for_model="Repo-local live provider shim echo tool for bounded AgentCore closure.",
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
        metadata={"contract_version": "agent.provider_live_shim.echo.v1"},
    )


def _fixture_request(*, timeout_ms: int) -> AgentCoreRequest:
    return AgentCoreRequest(
        message=f"Run repo-local live provider shim closure. Body: {_SENSITIVE_REQUEST_BODY}",
        session_id="agent-core-provider-live-shim-session",
        turn_id="turn-agent-core-provider-live-shim",
        project_key="demo_proj",
        max_iterations=4,
        max_tool_calls=2,
        context={
            "trace_id": _TRACE_ID,
            "request_id": _REQUEST_ID,
            "default_provider": _PROVIDER_KEY,
            "default_model": RepoLocalLiveProviderShim.model_id,
            "timeout_ms": int(timeout_ms),
            "network_scope": RepoLocalLiveProviderShim.network_scope,
            "closure_basis": "repo_local_live_provider_shim",
        },
    )


def _fixture_tool_call() -> CoreToolCall:
    return CoreToolCall(
        tool_name=_TOOL_NAME,
        arguments=_fixture_arguments(),
        call_id=_CALL_ID,
        reason="repo-local live provider shim bounded tool-call closure",
    )


def _fixture_arguments() -> dict[str, Any]:
    return {
        "query": _SENSITIVE_TOOL_QUERY,
        "trace_id": _TRACE_ID,
        "request_body": _SENSITIVE_REQUEST_BODY,
    }


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
            "contract_version": "agent.provider_live_shim.echo.result.v1",
            "query": _redacted_value_snapshot(tool_call.arguments.get("query")),
            "request_body": _redacted_value_snapshot(tool_call.arguments.get("request_body")),
            "project_key": request.project_key,
            "tool_name": tool_call.tool_name,
            "tool_call_id": tool_call.call_id,
        },
        "error": None,
        "meta": {
            "contract_version": "agent.provider_live_shim.echo.meta.v1",
            "trace_id": str(context.get("trace_id") or ""),
            "request_id": str(context.get("request_id") or ""),
            "provider_key": _PROVIDER_KEY,
            "model_id": RepoLocalLiveProviderShim.model_id,
            "closure_basis": "repo_local_live_provider_shim",
            "external_provider_live_verified": False,
            "external_model_calls": 0,
            "network_scope": RepoLocalLiveProviderShim.network_scope,
        },
    }
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="completed",
        model_summary="Repo-local live provider shim echo completed.",
        structured_content=envelope,
    )


def _status_data_error_meta_trace(envelope: Mapping[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") if isinstance(envelope.get("data"), Mapping) else {}
    meta = envelope.get("meta") if isinstance(envelope.get("meta"), Mapping) else {}
    keys = sorted(str(key) for key in envelope)
    compatible = (
        keys == ["data", "error", "meta", "status"]
        and envelope.get("status") == "ok"
        and isinstance(data, Mapping)
        and envelope.get("error") is None
        and isinstance(meta, Mapping)
        and meta.get("trace_id") == _TRACE_ID
        and meta.get("provider_key") == _PROVIDER_KEY
        and meta.get("closure_basis") == "repo_local_live_provider_shim"
        and meta.get("external_provider_live_verified") is False
        and meta.get("external_model_calls") == 0
    )
    return {
        "contract_version": "agent_core.repo_local_live_provider_shim.status_data_error_meta.v1",
        "compatible": compatible,
        "required_keys": ["data", "error", "meta", "status"],
        "present_keys": keys,
        "status": envelope.get("status"),
        "error_is_null": envelope.get("error") is None,
        "data_keys": sorted(str(key) for key in data),
        "meta": dict(meta),
    }


def _tool_event_snapshot(event: CoreEvent) -> dict[str, Any]:
    payload = dict(event.payload or {})
    tool_call = payload.get("tool_call") if isinstance(payload.get("tool_call"), Mapping) else {}
    tool_spec = payload.get("tool_spec") if isinstance(payload.get("tool_spec"), Mapping) else {}
    structured = payload.get("structured_content") if isinstance(payload.get("structured_content"), Mapping) else {}
    return {
        "contract_version": "agent_core.repo_local_live_provider_shim.tool_event.v1",
        "event_type": event.event_type,
        "call_id": event.call_id,
        "tool_name": tool_call.get("tool_name") or payload.get("tool_name") or tool_spec.get("name"),
        "has_tool_call": isinstance(payload.get("tool_call"), Mapping),
        "has_tool_spec": isinstance(payload.get("tool_spec"), Mapping),
        "has_status_data_error_meta": _is_status_data_error_meta_envelope(structured),
        "permission": payload.get("permission"),
        "status": payload.get("status"),
    }


def _invocation_snapshot(*, messages: Any, bound_tools: list[dict[str, Any]]) -> dict[str, Any]:
    message_rows = [item for item in list(messages or []) if isinstance(item, Mapping)]
    return {
        "contract_version": "agent_core.repo_local_live_provider_shim.invocation.v1",
        "message_count": len(message_rows),
        "message_roles": [str(item.get("role") or "") for item in message_rows],
        "bound_tool_count": len(bound_tools),
        "bound_tool_names": [_first_native_tool_name(bound_tools)] if bound_tools else [],
        "raw_messages_persisted": False,
    }


def _first_native_tool_name(bound_tools: list[dict[str, Any]]) -> str:
    for tool in bound_tools:
        function = tool.get("function") if isinstance(tool.get("function"), Mapping) else {}
        name = str(function.get("name") or "").strip()
        if name:
            return name
    return _native_tool_name(_TOOL_NAME)


def _is_tool_event(event: CoreEvent) -> bool:
    return event.event_type in {"tool_call_requested", "tool_call_started", "tool_result"}


def _is_status_data_error_meta_envelope(value: Mapping[str, Any]) -> bool:
    return sorted(str(key) for key in value) == ["data", "error", "meta", "status"]


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


def _raw_sensitive_values_absent(value: Mapping[str, Any], sensitive_values: list[str]) -> bool:
    encoded = _canonical_json(value)
    return all(item not in encoded for item in sensitive_values)


def _expect(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)
