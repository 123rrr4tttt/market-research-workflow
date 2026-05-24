from __future__ import annotations

from collections import Counter
import hashlib
import json
from time import perf_counter
from typing import Any, Mapping

from .contracts import AgentCoreRequest, CoreEvent, CoreToolCall, CoreToolResult, CoreToolSpec, core_tool_call_contract_shape
from .core import AgentCore
from .native_provider import NativeToolCallingCoreProvider
from .registry import CoreToolRegistry


AGENT_CORE_EXTERNAL_PROVIDER_LIVE_READBACK_VERSION = "agent_core.external_provider_live_readback.v1"

_TOOL_NAME = "agent.external_provider_live.echo"
_TRACE_ID = "trace-agent-core-external-provider-live-readback"
_REQUEST_ID = "req-agent-core-external-provider-live-readback"
_REDACTION_MARKER = "[REDACTED]"
_SENTINEL_BODY = (
    "wave55-agentcore-external-provider-live-readback-sentinel::"
    "not-a-secret;redaction-required"
)
_SUPPORTED_SELECTED_PROVIDERS = {"openai", "azure", "litellm"}


def build_agent_core_external_provider_live_readback_evidence(
    *,
    settings_source: Any | None = None,
    chat_model_factory: Any | None = None,
    allow_external_network: bool = False,
    timeout_ms: int = 20_000,
    model: str | None = None,
) -> dict[str, Any]:
    """Run or classify the selected external provider live AgentCore readback.

    The real network call is gated by ``allow_external_network``.  Without that
    explicit opt-in the evidence records the exact missing gate instead of
    silently spending provider calls.
    """

    if settings_source is None:
        from app.settings.config import settings as settings_source

    provider = _selected_provider(settings_source)
    environment = _provider_environment(settings_source=settings_source, provider=provider, model=model)
    timeout_ms = max(1000, int(timeout_ms))
    if not allow_external_network and chat_model_factory is None:
        return _blocked_evidence(
            environment=environment,
            blocker_code="external_network_not_allowed",
            blocker_detail="Pass --allow-external-network to run the bounded selected-provider invocation.",
            timeout_ms=timeout_ms,
        )
    if provider not in _SUPPORTED_SELECTED_PROVIDERS and chat_model_factory is None:
        return _blocked_evidence(
            environment=environment,
            blocker_code=f"{provider}_external_provider_probe_not_supported",
            blocker_detail="This gate currently supports selected OpenAI, Azure, or LiteLLM chat providers.",
            timeout_ms=timeout_ms,
        )
    missing = list(environment.get("missing_config_keys") or [])
    if missing and chat_model_factory is None:
        return _blocked_evidence(
            environment=environment,
            blocker_code=f"missing_{provider}_provider_config",
            blocker_detail=f"Missing selected-provider config keys: {', '.join(missing)}.",
            timeout_ms=timeout_ms,
        )

    started = perf_counter()
    recorder = _RecordingChatModel(
        _build_chat_model(settings_source=settings_source, chat_model_factory=chat_model_factory, model=environment.get("model_id"), timeout_ms=timeout_ms)
    )
    try:
        registry = CoreToolRegistry()
        spec = _tool_spec()
        registry.register(spec, _tool_handler)
        result = AgentCore(
            provider=NativeToolCallingCoreProvider(chat_model=recorder),
            tool_registry=registry,
            tool_specs=registry.list_specs(),
        ).run(_request(timeout_ms=timeout_ms))
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        return _evidence_from_result(
            environment=environment,
            recorder=recorder,
            result=result,
            timeout_ms=timeout_ms,
            latency_ms=elapsed_ms,
        )
    except Exception as exc:  # noqa: BLE001 - live probe reports the real failure taxonomy.
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        return _blocked_evidence(
            environment=environment,
            blocker_code=f"external_provider_invocation_exception:{exc.__class__.__name__}",
            blocker_detail=str(exc),
            timeout_ms=timeout_ms,
            latency_ms=elapsed_ms,
            provider_calls=len(recorder.calls),
            response_shapes=recorder.response_shapes,
        )


def validate_agent_core_external_provider_live_readback_evidence(evidence: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    _expect(
        evidence.get("contract_version") == AGENT_CORE_EXTERNAL_PROVIDER_LIVE_READBACK_VERSION,
        errors,
        "unexpected external provider live readback contract version",
    )
    _expect(evidence.get("status") in {"passed", "blocked", "failed"}, errors, "invalid status")
    _expect(evidence.get("closure_basis") == "selected_external_provider_live_readback", errors, "invalid closure basis")
    if evidence.get("status") != "passed" or evidence.get("closed") is not True:
        _expect(evidence.get("closed") is False, errors, "blocked evidence must not be closed")
        _expect(evidence.get("external_provider_live_verified") is False, errors, "blocked evidence must not claim live verification")
        _expect(bool(evidence.get("remaining_blockers")), errors, "blocked evidence missing remaining blockers")
        return errors

    _expect(evidence.get("external_provider_live_verified") is True, errors, "external provider live verification missing")
    _expect(int(evidence.get("external_model_calls") or 0) >= 1, errors, "external provider call count missing")
    _expect(evidence.get("latency_status") == "within_timeout", errors, "external provider probe exceeded timeout")
    invocation = evidence.get("provider_invocation") if isinstance(evidence.get("provider_invocation"), Mapping) else {}
    _expect(invocation.get("network_scope") == "external_provider_network", errors, "external network scope not recorded")
    _expect(invocation.get("account_state") == "selected_provider_credentials_configured", errors, "account state not configured")
    runtime = evidence.get("runtime_dispatch") if isinstance(evidence.get("runtime_dispatch"), Mapping) else {}
    _expect(runtime.get("stop_reason") == "final_answer", errors, "AgentCore live run did not finish")
    result_counts = runtime.get("tool_result_status_counts") if isinstance(runtime.get("tool_result_status_counts"), Mapping) else {}
    _expect(int(result_counts.get("completed") or 0) >= 1, errors, "completed tool result missing")
    sequence = [item.get("event_type") for item in runtime.get("tool_event_sequence") or [] if isinstance(item, Mapping)]
    _expect(sequence == ["tool_call_requested", "tool_call_started", "tool_result"], errors, f"tool event sequence drift: {sequence}")
    tool_call = evidence.get("tool_call_readback") if isinstance(evidence.get("tool_call_readback"), Mapping) else {}
    _expect(tool_call.get("shape_status") == "valid", errors, "tool-call shape invalid")
    _expect(tool_call.get("tool_name") == _TOOL_NAME, errors, "tool-call canonical name drift")
    _expect(tool_call.get("arguments_redacted") is True, errors, "tool-call arguments not redacted")
    status_trace = evidence.get("status_data_error_meta_trace") if isinstance(evidence.get("status_data_error_meta_trace"), Mapping) else {}
    _expect(status_trace.get("compatible") is True, errors, "status/data/error/meta readback incompatible")
    reviewer = evidence.get("reviewer_readback") if isinstance(evidence.get("reviewer_readback"), Mapping) else {}
    _expect(reviewer.get("status") == "accepted", errors, "reviewer readback did not accept live evidence")
    redaction = evidence.get("redaction") if isinstance(evidence.get("redaction"), Mapping) else {}
    _expect(redaction.get("raw_sensitive_values_absent") is True, errors, "raw sensitive values persisted")
    _expect(not evidence.get("failures"), errors, f"failures present: {evidence.get('failures')}")
    return errors


class _RecordingChatModel:
    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.bound_tools: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.response_shapes: list[dict[str, Any]] = []

    def bind_tools(self, tools: Any) -> "_BoundRecordingChatModel":
        self.bound_tools = [dict(tool) for tool in list(tools or []) if isinstance(tool, dict)]
        bound_inner = self.inner.bind_tools(tools)
        return _BoundRecordingChatModel(parent=self, inner=bound_inner)

    def invoke(self, messages: Any) -> Any:
        return _BoundRecordingChatModel(parent=self, inner=self.inner).invoke(messages)


class _BoundRecordingChatModel:
    def __init__(self, *, parent: _RecordingChatModel, inner: Any) -> None:
        self.parent = parent
        self.inner = inner

    def invoke(self, messages: Any) -> Any:
        started = perf_counter()
        self.parent.calls.append(_invocation_snapshot(messages=messages, bound_tools=self.parent.bound_tools))
        response = self.inner.invoke(messages)
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        self.parent.response_shapes.append(_response_shape(response=response, response_index=len(self.parent.calls), latency_ms=elapsed_ms))
        return response


def _build_chat_model(*, settings_source: Any, chat_model_factory: Any | None, model: Any, timeout_ms: int) -> Any:
    if chat_model_factory is not None:
        return chat_model_factory()
    from app.services.llm.provider import get_chat_model

    timeout_seconds = max(5, int(timeout_ms / 1000))
    return get_chat_model(
        model=str(model or "").strip() or None,
        temperature=0.0,
        max_tokens=220,
        timeout=timeout_seconds,
    )


def _evidence_from_result(
    *,
    environment: Mapping[str, Any],
    recorder: _RecordingChatModel,
    result: Any,
    timeout_ms: int,
    latency_ms: float,
) -> dict[str, Any]:
    event_counts = Counter(event.event_type for event in result.events)
    result_counts = Counter(item.status for item in result.tool_results)
    tool_call = _first_tool_call(result.events)
    tool_result = result.tool_results[0] if result.tool_results else None
    envelope = dict(tool_result.structured_content or {}) if tool_result is not None else {}
    tool_shape = core_tool_call_contract_shape(tool_call or _fixture_tool_call(), provider_key=str(environment.get("provider") or "unknown"))
    tool_shape["arguments"] = _redacted_arguments_snapshot(tool_shape.get("arguments") if isinstance(tool_shape.get("arguments"), Mapping) else {})
    tool_shape["arguments_redacted"] = True
    tool_shape["raw_arguments_persisted"] = False
    runtime = {
        "contract_version": "agent_core.external_provider_live_readback.runtime_dispatch.v1",
        "session_id": result.session_id,
        "turn_id": result.turn_id,
        "stop_reason": result.stop_reason,
        "final_answer_present": bool(result.final_answer),
        "event_type_counts": {name: event_counts[name] for name in sorted(event_counts)},
        "tool_result_status_counts": {name: result_counts[name] for name in sorted(result_counts)},
        "tool_event_sequence": [_tool_event_snapshot(event) for event in result.events if event.event_type in {"tool_call_requested", "tool_call_started", "tool_result"}],
    }
    evidence: dict[str, Any] = {
        "contract_version": AGENT_CORE_EXTERNAL_PROVIDER_LIVE_READBACK_VERSION,
        "status": "failed",
        "closed": False,
        "closure_basis": "selected_external_provider_live_readback",
        "provider": environment.get("provider"),
        "model_id": environment.get("model_id"),
        "timeout_ms": int(timeout_ms),
        "latency_ms": latency_ms,
        "latency_status": "within_timeout" if latency_ms <= timeout_ms else "timeout_budget_exceeded",
        "external_provider_live_verified": False,
        "external_model_calls": len(recorder.calls),
        "provider_invocation": {
            "provider": environment.get("provider"),
            "provider_path": environment.get("provider_path"),
            "api_endpoint": environment.get("api_endpoint"),
            "account_state": "selected_provider_credentials_configured",
            "network_scope": "external_provider_network",
        },
        "raw_response_shape_classification": {
            "contract_version": "agent_core.external_provider_live_readback.response_shape.v1",
            "responses": list(recorder.response_shapes),
            "raw_response_persisted": False,
        },
        "tool_call_readback": tool_shape,
        "runtime_dispatch": runtime,
        "status_data_error_meta_trace": _status_data_error_meta_trace(envelope),
        "reviewer_readback": {},
        "redaction": {
            "contract_version": "agent_core.external_provider_live_readback.redaction.v1",
            "redaction_marker": _REDACTION_MARKER,
            "raw_request_body_persisted": False,
            "raw_tool_arguments_persisted": False,
            "raw_sensitive_values_absent": False,
        },
        "remaining_blockers": [],
        "failures": [],
    }
    evidence["redaction"]["raw_sensitive_values_absent"] = _raw_sensitive_values_absent(evidence, [_SENTINEL_BODY])
    evidence["reviewer_readback"] = _reviewer_readback(evidence)
    failures = _evidence_failures(evidence)
    evidence["failures"] = failures
    evidence["status"] = "passed" if not failures else "failed"
    evidence["closed"] = not failures
    evidence["external_provider_live_verified"] = not failures
    if failures:
        evidence["remaining_blockers"] = [{"code": failure, "detail": "External provider live readback assertion failed."} for failure in failures]
    return evidence


def _blocked_evidence(
    *,
    environment: Mapping[str, Any],
    blocker_code: str,
    blocker_detail: str,
    timeout_ms: int,
    latency_ms: float | None = None,
    provider_calls: int = 0,
    response_shapes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": AGENT_CORE_EXTERNAL_PROVIDER_LIVE_READBACK_VERSION,
        "status": "blocked",
        "closed": False,
        "closure_basis": "selected_external_provider_live_readback",
        "provider": environment.get("provider"),
        "model_id": environment.get("model_id"),
        "timeout_ms": int(timeout_ms),
        "latency_ms": latency_ms,
        "latency_status": "not_run" if latency_ms is None else ("within_timeout" if latency_ms <= timeout_ms else "timeout_budget_exceeded"),
        "external_provider_live_verified": False,
        "external_model_calls": int(provider_calls),
        "provider_invocation": {
            "provider": environment.get("provider"),
            "provider_path": environment.get("provider_path"),
            "api_endpoint": environment.get("api_endpoint"),
            "account_state": environment.get("account_state"),
            "network_scope": "external_provider_network",
        },
        "raw_response_shape_classification": {
            "contract_version": "agent_core.external_provider_live_readback.response_shape.v1",
            "responses": list(response_shapes or []),
            "raw_response_persisted": False,
        },
        "remaining_blockers": [{"code": blocker_code, "detail": blocker_detail}],
        "failures": [],
    }


def _evidence_failures(evidence: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if evidence.get("latency_status") != "within_timeout":
        failures.append("timeout_budget_exceeded")
    if int(evidence.get("external_model_calls") or 0) < 1:
        failures.append("external_model_call_missing")
    runtime = evidence.get("runtime_dispatch") if isinstance(evidence.get("runtime_dispatch"), Mapping) else {}
    if runtime.get("stop_reason") != "final_answer":
        failures.append(f"stop_reason={runtime.get('stop_reason')}")
    if (runtime.get("tool_result_status_counts") or {}).get("completed", 0) < 1:
        failures.append("completed_tool_result_missing")
    sequence = [item.get("event_type") for item in runtime.get("tool_event_sequence") or [] if isinstance(item, Mapping)]
    if sequence != ["tool_call_requested", "tool_call_started", "tool_result"]:
        failures.append(f"tool_event_sequence={sequence}")
    tool_shape = evidence.get("tool_call_readback") if isinstance(evidence.get("tool_call_readback"), Mapping) else {}
    if tool_shape.get("shape_status") != "valid":
        failures.append("tool_call_shape_invalid")
    if tool_shape.get("tool_name") != _TOOL_NAME:
        failures.append("tool_call_name_drift")
    status_trace = evidence.get("status_data_error_meta_trace") if isinstance(evidence.get("status_data_error_meta_trace"), Mapping) else {}
    if status_trace.get("compatible") is not True:
        failures.append("status_data_error_meta_incompatible")
    reviewer = evidence.get("reviewer_readback") if isinstance(evidence.get("reviewer_readback"), Mapping) else {}
    if reviewer.get("status") != "accepted":
        failures.append("reviewer_readback_rejected")
    redaction = evidence.get("redaction") if isinstance(evidence.get("redaction"), Mapping) else {}
    if redaction.get("raw_sensitive_values_absent") is not True:
        failures.append("raw_sensitive_values_persisted")
    return failures


def _provider_environment(*, settings_source: Any, provider: str, model: str | None) -> dict[str, Any]:
    if provider == "openai":
        missing = [] if _has_setting(settings_source, "openai_api_key") else ["OPENAI_API_KEY"]
        return {
            "provider": provider,
            "provider_path": "langchain_openai.ChatOpenAI",
            "model_id": model or _setting(settings_source, "openai_model") or "gpt-4o-mini",
            "api_endpoint": _setting(settings_source, "openai_api_base") or "https://api.openai.com/v1",
            "account_state": "selected_provider_credentials_configured" if not missing else "missing_selected_provider_credentials",
            "missing_config_keys": missing,
        }
    if provider == "azure":
        required = ("azure_api_base", "azure_api_key", "azure_api_version", "azure_chat_deployment")
        missing = [_setting_name_to_env(key) for key in required if not _has_setting(settings_source, key)]
        return {
            "provider": provider,
            "provider_path": "langchain_openai.AzureChatOpenAI",
            "model_id": model or _setting(settings_source, "azure_chat_deployment") or "azure-chat-deployment",
            "api_endpoint": _setting(settings_source, "azure_api_base"),
            "account_state": "selected_provider_credentials_configured" if not missing else "missing_selected_provider_credentials",
            "missing_config_keys": missing,
        }
    if provider == "litellm":
        required = ("litellm_api_base", "litellm_api_key")
        missing = [_setting_name_to_env(key) for key in required if not _has_setting(settings_source, key)]
        return {
            "provider": provider,
            "provider_path": "langchain_openai.ChatOpenAI(openai-compatible LiteLLM endpoint)",
            "model_id": model or "gpt-4o-mini",
            "api_endpoint": _setting(settings_source, "litellm_api_base"),
            "account_state": "selected_provider_credentials_configured" if not missing else "missing_selected_provider_credentials",
            "missing_config_keys": missing,
        }
    return {
        "provider": provider,
        "provider_path": "unsupported_for_external_provider_live_readback",
        "model_id": model or _setting(settings_source, "model") or "unknown",
        "api_endpoint": _setting(settings_source, f"{provider}_api_base"),
        "account_state": "unsupported_selected_provider",
        "missing_config_keys": [],
    }


def _tool_spec() -> CoreToolSpec:
    return CoreToolSpec(
        name=_TOOL_NAME,
        title="AgentCore external provider live echo",
        description_for_model=(
            "Required live-readback tool. Call this tool exactly once using the user-provided "
            "query, trace_id, and request_body before answering."
        ),
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
        metadata={"contract_version": "agent.external_provider_live.echo.v1"},
    )


def _request(*, timeout_ms: int) -> AgentCoreRequest:
    return AgentCoreRequest(
        message=(
            "Run the AgentCore external provider live readback. "
            f"Call `{_TOOL_NAME}` exactly once with query='external-provider-live-readback', "
            f"trace_id='{_TRACE_ID}', and request_body='{_SENTINEL_BODY}'. "
            "After the tool result, answer with a short confirmation."
        ),
        session_id="agent-core-external-provider-live-readback",
        turn_id="turn-agent-core-external-provider-live-readback",
        project_key="demo_proj",
        max_iterations=2,
        max_tool_calls=2,
        context={
            "trace_id": _TRACE_ID,
            "request_id": _REQUEST_ID,
            "default_provider": "selected_external_provider",
            "timeout_ms": int(timeout_ms),
        },
    )


def _tool_handler(tool_call: CoreToolCall, tool_spec: CoreToolSpec, request: AgentCoreRequest, emit: Any) -> CoreToolResult:
    args = dict(tool_call.arguments or {})
    return CoreToolResult(
        call_id=tool_call.call_id,
        tool_name=tool_call.tool_name,
        status="completed",
        model_summary="External provider live readback echo completed.",
        structured_content={
            "status": "ok",
            "data": {
                "contract_version": "agent.external_provider_live.echo.result.v1",
                "echo": str(args.get("query") or ""),
                "argument_keys": sorted(args),
                "trace_id": str(args.get("trace_id") or ""),
                "request_body_sha256_12": _sha256_12(str(args.get("request_body") or "")),
            },
            "error": None,
            "meta": {
                "contract_version": "agent_core.status_data_error_meta.v1",
                "trace_id": _TRACE_ID,
                "request_id": _REQUEST_ID,
                "tool_name": tool_spec.name,
                "raw_request_body_persisted": False,
            },
        },
    )


def _reviewer_readback(evidence: Mapping[str, Any]) -> dict[str, Any]:
    runtime = evidence.get("runtime_dispatch") if isinstance(evidence.get("runtime_dispatch"), Mapping) else {}
    trace = evidence.get("status_data_error_meta_trace") if isinstance(evidence.get("status_data_error_meta_trace"), Mapping) else {}
    tool_call = evidence.get("tool_call_readback") if isinstance(evidence.get("tool_call_readback"), Mapping) else {}
    assertions = [
        ("external_provider_invoked", int(evidence.get("external_model_calls") or 0) >= 1),
        ("tool_call_shape_valid", tool_call.get("shape_status") == "valid" and tool_call.get("tool_name") == _TOOL_NAME),
        ("runtime_completed_tool", (runtime.get("tool_result_status_counts") or {}).get("completed", 0) >= 1),
        ("status_data_error_meta_compatible", trace.get("compatible") is True),
        ("raw_arguments_redacted", tool_call.get("arguments_redacted") is True),
    ]
    rows = [{"code": code, "passed": bool(passed)} for code, passed in assertions]
    return {
        "contract_version": "agent_core.external_provider_live_readback.reviewer.v1",
        "status": "accepted" if all(row["passed"] for row in rows) else "rejected",
        "reviewed_assertions": rows,
        "remaining_blockers": [row["code"] for row in rows if not row["passed"]],
    }


def _status_data_error_meta_trace(envelope: Mapping[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") if isinstance(envelope.get("data"), Mapping) else {}
    meta = envelope.get("meta") if isinstance(envelope.get("meta"), Mapping) else {}
    compatible = (
        envelope.get("status") == "ok"
        and isinstance(data, Mapping)
        and "error" in envelope
        and isinstance(meta, Mapping)
        and bool(meta.get("trace_id"))
        and bool(meta.get("request_id"))
    )
    return {
        "contract_version": "agent_core.status_data_error_meta.readback.v1",
        "compatible": compatible,
        "status": envelope.get("status"),
        "data_keys": sorted(str(key) for key in data),
        "error_present": envelope.get("error") is not None,
        "meta_keys": sorted(str(key) for key in meta),
        "trace_id": meta.get("trace_id"),
        "request_id": meta.get("request_id"),
        "raw_request_body_persisted": bool(meta.get("raw_request_body_persisted")),
    }


def _response_shape(*, response: Any, response_index: int, latency_ms: float) -> dict[str, Any]:
    raw_calls = getattr(response, "tool_calls", None)
    additional = getattr(response, "additional_kwargs", None)
    if raw_calls is None and isinstance(additional, Mapping):
        raw_calls = additional.get("tool_calls")
    response_metadata = getattr(response, "response_metadata", None)
    if not isinstance(response_metadata, Mapping):
        response_metadata = {}
    return {
        "response_index": response_index,
        "latency_ms": latency_ms,
        "response_kind": "native_tool_calls" if raw_calls else "final_answer",
        "tool_call_count": len(list(raw_calls or [])),
        "content_present": bool(str(getattr(response, "content", "") or "").strip()),
        "model_name": response_metadata.get("model_name") or response_metadata.get("model") or None,
        "finish_reason": response_metadata.get("finish_reason") or None,
        "raw_response_persisted": False,
    }


def _first_tool_call(events: Any) -> CoreToolCall | None:
    for event in events:
        if not isinstance(event, CoreEvent) or event.event_type != "tool_call_requested":
            continue
        raw = event.payload.get("tool_call") if isinstance(event.payload, Mapping) else None
        if not isinstance(raw, Mapping):
            continue
        args = raw.get("arguments") if isinstance(raw.get("arguments"), Mapping) else {}
        return CoreToolCall(
            tool_name=str(raw.get("tool_name") or ""),
            arguments=dict(args),
            call_id=str(raw.get("call_id") or ""),
            reason=str(raw.get("reason") or ""),
        )
    return None


def _fixture_tool_call() -> CoreToolCall:
    return CoreToolCall(
        tool_name=_TOOL_NAME,
        arguments={"query": "", "trace_id": "", "request_body": ""},
        call_id="missing-live-tool-call",
        reason="missing live external provider tool call",
    )


def _tool_event_snapshot(event: CoreEvent) -> dict[str, Any]:
    raw = event.to_dict()
    payload = raw.get("payload") if isinstance(raw.get("payload"), Mapping) else {}
    return {
        "contract_version": "agent_core.external_provider_live_readback.tool_event.v1",
        "event_type": event.event_type,
        "call_id": event.call_id,
        "tool_name": _event_tool_name(payload),
        "has_tool_call": isinstance(payload.get("tool_call"), Mapping),
        "has_tool_spec": isinstance(payload.get("tool_spec"), Mapping),
        "has_tool_result": event.event_type == "tool_result",
    }


def _event_tool_name(payload: Mapping[str, Any]) -> str:
    if isinstance(payload.get("tool_call"), Mapping):
        return str(payload["tool_call"].get("tool_name") or "")
    if isinstance(payload.get("tool_spec"), Mapping):
        return str(payload["tool_spec"].get("name") or "")
    if isinstance(payload.get("structured_content"), Mapping):
        return _TOOL_NAME
    return ""


def _invocation_snapshot(*, messages: Any, bound_tools: list[dict[str, Any]]) -> dict[str, Any]:
    message_count = len(list(messages or [])) if isinstance(messages, list) else 1
    return {
        "contract_version": "agent_core.external_provider_live_readback.invocation.v1",
        "message_count": message_count,
        "bound_tool_count": len(bound_tools),
        "bound_tool_names": [_tool_name_from_native(tool) for tool in bound_tools],
        "raw_messages_persisted": False,
        "raw_request_body_persisted": False,
    }


def _tool_name_from_native(tool: Mapping[str, Any]) -> str:
    function = tool.get("function") if isinstance(tool.get("function"), Mapping) else {}
    return str(function.get("name") or "")


def _redacted_arguments_snapshot(arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): {
            "type": type(value).__name__,
            "sha256_12": _sha256_12(str(value)),
            "value": _REDACTION_MARKER,
        }
        for key, value in sorted(dict(arguments or {}).items())
    }


def _raw_sensitive_values_absent(payload: Any, sensitive_values: list[str]) -> bool:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return all(value not in rendered for value in sensitive_values if value)


def _selected_provider(settings_source: Any) -> str:
    return str(_setting(settings_source, "llm_provider", "openai") or "openai").strip().lower() or "openai"


def _setting(settings_source: Any, key: str, default: Any = None) -> Any:
    if isinstance(settings_source, Mapping):
        return settings_source.get(key, default)
    return getattr(settings_source, key, default)


def _has_setting(settings_source: Any, key: str) -> bool:
    value = _setting(settings_source, key, None)
    if isinstance(value, bool):
        return value
    return bool(str(value or "").strip())


def _setting_name_to_env(key: str) -> str:
    return str(key or "").upper()


def _sha256_12(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


def _expect(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)
