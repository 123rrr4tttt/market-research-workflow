"""Sibling legacy adapters for the P3 C6 AgentCore successor family.

This is the only package allowed to call the legacy AgentCore provider/loop
contracts.  It never imports the successor runtime core into legacy services;
instead it projects deterministic legacy observations into the frozen C6 DTOs
and runs the same Program/Plan through both realizations.  The C6.1 tool loop
uses the C2.1 pure tool specimen only: no provider, settings, network,
credential or durable effect is touched.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.agent_core.contracts import (
    AgentCoreRequest,
    AgentCoreRunResult,
    CoreApprovalResume,
    CoreEvent,
    CoreModelStep,
    CoreProvider,
    CoreToolCall,
    CoreToolResult,
    CoreToolSpec,
)
from app.services.agent_core.core import AgentCore
from app.services.agent_core.fake_provider import FakeCoreProvider
from app.successor_runtime.capabilities import (
    agent_core_c6_1 as c6_1,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_2 as c6_2,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_3 as c6_3,
)
from app.successor_runtime.capabilities.agent_core_c6_1_interpreters import (
    AGENT_CORE_C6_1_LEGACY_INTERPRETER_ID,
    require_exact_episode_binding,
)
from app.successor_runtime.capabilities.agent_core_c6_1_interpreters import (
    authority_requirement_digest as c6_1_authority_requirement_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_1_interpreters import (
    legacy_interpreter_profile_digest as c6_1_legacy_profile_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_1_interpreters import (
    successor_interpreter_profile_digest as c6_1_successor_profile_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_2_interpreters import (
    AGENT_CORE_C6_2_LEGACY_INTERPRETER_ID,
    require_exact_provider_binding,
)
from app.successor_runtime.capabilities.agent_core_c6_2_interpreters import (
    authority_requirement_digest as c6_2_authority_requirement_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_2_interpreters import (
    legacy_interpreter_profile_digest as c6_2_legacy_profile_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_2_interpreters import (
    successor_interpreter_profile_digest as c6_2_successor_profile_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_3_interpreters import (
    AGENT_CORE_C6_3_LEGACY_INTERPRETER_ID,
    require_exact_redaction_binding,
)
from app.successor_runtime.capabilities.agent_core_c6_3_interpreters import (
    authority_requirement_digest as c6_3_authority_requirement_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_3_interpreters import (
    legacy_interpreter_profile_digest as c6_3_legacy_profile_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_3_interpreters import (
    successor_interpreter_profile_digest as c6_3_successor_profile_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    AgentModelStep,
    AgentToolCall,
    AgentToolResult,
    ProjectScope,
    c6_deployment_catalog_digest,
    freeze_c6_json_object,
    project_scope_digest,
    thaw_json_value,
)
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest
from app.successor_runtime.capabilities.source_library_c2_1 import (
    SOURCE_RESOLUTION_OBSERVATION_PROFILE,
    SourceResolutionObservation,
    payload_from_dicts,
)
from app.successor_runtime.capabilities.source_library_c2_1_interpreters import (
    resolve_source_execution_request,
)
from app.successor_runtime.runtime.assignments import InterpreterBinding

__all__ = [
    "C2_1_PURE_TOOL_NAME",
    "C2_1PureToolSpecimen",
    "LegacyAgentCoreCapabilityInterpreter",
    "LegacyProviderPortAdapter",
    "NamedProviderModelStepInterpreter",
    "RedactedObservationAdapter",
    "bindings_are_distinct",
    "build_legacy_agent_core_c6_1_binding",
    "build_legacy_agent_core_c6_2_binding",
    "build_legacy_agent_core_c6_3_binding",
    "build_successor_agent_core_c6_1_binding",
    "build_successor_agent_core_c6_2_binding",
    "build_successor_agent_core_c6_3_binding",
    "legacy_rollback_receipt",
]


class LegacyRedactionFailed(RuntimeError):
    """Fail-closed marker for a rejected legacy C6.3 redaction."""


C2_1_PURE_TOOL_NAME = "source_library.resolve_execution_request"
_C2_1_REQUIRED_ARGUMENT_KEYS = (
    "project_key",
    "registry_revision",
    "resolved_schema",
    "scope_incarnation",
    "channels",
    "item",
    "params",
)
_LEGACY_EVENT_TYPE_MAP: dict[str, str] = {
    "session_started": "session_started",
    "user_message": "user_message",
    "assistant_delta": "assistant_delta",
    "assistant_message": "assistant_message",
    "tool_call_requested": "tool_call_requested",
    "tool_call_started": "tool_call_started",
    "tool_result": "tool_result",
    "permission_requested": "permission_requested",
    "approval_resolved": "approval_resolved",
    "run_resumed": "run_resumed",
    "final_answer": "final_answer",
    "error": "error",
}
_LEGACY_STOP_REASON_MAP: dict[str, str] = {
    "final_answer": "final_answer",
    "no_more_tools": "no_more_tools",
    "permission_requested": "permission_requested",
    "approval_denied": "approval_denied",
    "max_tool_calls_exceeded": "max_tool_calls_exceeded",
    "max_iterations_exceeded": "max_iterations_exceeded",
    "canceled": "canceled",
    "error": "error",
}


def _agent_tool_call_to_legacy(call: AgentToolCall) -> CoreToolCall:
    return CoreToolCall(
        tool_name=call.tool_name,
        arguments=thaw_json_value(call.arguments),
        call_id=call.call_id,
        reason=call.reason,
    )


def _agent_model_step_to_legacy(step: AgentModelStep) -> CoreModelStep:
    if step.step_type == "final_answer":
        return CoreModelStep.final(step.content, **dict(step.metadata))
    if step.step_type == "assistant_delta":
        return CoreModelStep.delta(step.content, **dict(step.metadata))
    return CoreModelStep.tools(
        *[_agent_tool_call_to_legacy(call) for call in step.tool_calls],
        **dict(step.metadata),
    )


def _legacy_model_step_to_agent(step: CoreModelStep) -> AgentModelStep:
    return AgentModelStep(
        schema_version="mrw.successor.agent-core.c6.model-step.v1",
        step_type=step.step_type,
        content=step.content,
        tool_calls=tuple(
            AgentToolCall(
                call_id=call.call_id,
                tool_name=call.tool_name,
                arguments=freeze_c6_json_object(dict(call.arguments or {})),
                reason=call.reason,
            )
            for call in step.tool_calls
        ),
        metadata=freeze_c6_json_object(dict(step.metadata or {})),
    )


class C2_1PureToolSpecimen:
    """The only C6.1 tool specimen: the pure C2.1 resolve atom.

    The specimen performs no network/provider/database work; it builds an
    exact C2.1 payload from typed arguments and runs the successor-native pure
    resolver.
    """

    tool_name = C2_1_PURE_TOOL_NAME

    def validate(self, tool_call: AgentToolCall) -> AgentToolResult | None:
        arguments = thaw_json_value(tool_call.arguments)
        missing = [key for key in _C2_1_REQUIRED_ARGUMENT_KEYS if key not in arguments]
        if missing:
            return AgentToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="C2.1 tool arguments are incomplete.",
                error=freeze_c6_json_object(
                    {
                        "code": "tool_schema_validation_failed",
                        "message": "missing arguments: " + ", ".join(missing),
                    }
                ),
                retry_hint="Provide the complete C2.1 payload builder arguments.",
            )
        return None

    def execute(
        self, tool_call: AgentToolCall, request: c6_1.AgentTurnRequest
    ) -> AgentToolResult:
        arguments = thaw_json_value(tool_call.arguments)
        try:
            payload = payload_from_dicts(
                project_key=arguments["project_key"],
                registry_revision=int(arguments["registry_revision"]),
                resolved_schema=arguments["resolved_schema"],
                scope_incarnation=arguments["scope_incarnation"],
                scope_digest=project_scope_digest(
                    arguments["project_key"],
                    arguments["resolved_schema"],
                    int(arguments["registry_revision"]),
                    arguments["scope_incarnation"],
                ),
                channels=arguments["channels"],
                item=arguments["item"],
                params=arguments["params"],
            )
            if payload.project_scope.project_key != request.project_scope.project_key:
                raise ValueError("C2.1 tool project scope does not match the episode")
            resolution = resolve_source_execution_request(payload)
        except Exception as exc:  # noqa: BLE001
            return AgentToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Tool {tool_call.tool_name} failed: {exc}",
                error=freeze_c6_json_object(
                    {"code": exc.__class__.__name__, "message": str(exc)}
                ),
            )
        if resolution.to_plain().get("kind") != "resolved":
            rejection = resolution.rejection.to_plain()
            return AgentToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="C2.1 pure resolver rejected the source item.",
                error=freeze_c6_json_object(
                    {
                        "code": "C2_1_RESOLUTION_REJECTED",
                        "rejection_code": rejection["code"],
                        "message": rejection["message"],
                    }
                ),
            )
        expected_observation_digest = _expected_observation_digest(resolution.request)
        if resolution.observation_digest != expected_observation_digest:
            return AgentToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="C2.1 observation digest does not match the request.",
                error=freeze_c6_json_object(
                    {
                        "code": "OBSERVATION_DIGEST_MISMATCH",
                        "message": "C2.1 resolver observation digest drift",
                    }
                ),
            )
        structured = resolution.to_plain()
        return AgentToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary="source resolution request prepared",
            structured_content=freeze_c6_json_object(structured),
        )


class _SpecimenCoreToolExecutor:
    """Adapt one C6.1 ToolSpecimen to the legacy CoreToolExecutor protocol."""

    def __init__(self, specimen: c6_1.ToolSpecimen) -> None:
        self.specimen = specimen

    def execute_tool(
        self,
        *,
        tool_call: CoreToolCall,
        tool_spec: CoreToolSpec,
        request: AgentCoreRequest,
        emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        agent_call = AgentToolCall(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            arguments=freeze_c6_json_object(thaw_json_value(tool_call.arguments or {})),
            reason=tool_call.reason,
        )
        validation = self.specimen.validate(agent_call)
        if validation is not None:
            return _legacy_result_from_agent(validation)
        episode_request = _turn_request_from_legacy_request(request)
        return _legacy_result_from_agent(
            self.specimen.execute(agent_call, episode_request)
        )


def _legacy_result_from_agent(result: AgentToolResult) -> CoreToolResult:
    return CoreToolResult(
        call_id=result.call_id,
        tool_name=result.tool_name,
        status=result.status,
        model_summary=result.model_summary,
        ui_summary=result.ui_summary,
        structured_content=dict(result.structured_content),
        error=None if result.error is None else dict(result.error),
        retry_hint=result.retry_hint,
    )


def _turn_request_from_legacy_request(
    request: AgentCoreRequest,
) -> c6_1.AgentTurnRequest:
    """Build a bounded adapter request; only project_key is consumed."""

    project_key = request.project_key or "adapter"
    scope = ProjectScope(
        project_key=project_key,
        registry_revision=0,
        resolved_schema="mrw_p_legacy_adapter",
        incarnation="legacy-adapter",
        scope_digest="",
    )
    return c6_1.AgentTurnRequest(
        schema_version=c6_1.AGENT_CORE_C6_1_PAYLOAD_SCHEMA,
        operation_kind=c6_1.AGENT_CORE_C6_1_KIND,
        project_scope=scope,
        session_id=request.session_id,
        turn_id=request.turn_id,
        message_ref=request.message,
        max_iterations=request.max_iterations,
        max_tool_calls=request.max_tool_calls,
        approval_policy=request.approval_policy,
    )


def _legacy_request_from_c6_1(
    payload: c6_1.AgentTurnRequest,
) -> AgentCoreRequest:
    resume = None
    if payload.resume_tool_call is not None:
        resume = CoreApprovalResume(
            approval_id=f"approval:{payload.resume_tool_call.call_id}",
            tool_call=_agent_tool_call_to_legacy(payload.resume_tool_call),
            approved=payload.resume_call_id in payload.approved_call_ids,
            approved_by="user",
        )
    return AgentCoreRequest(
        message=payload.message_ref,
        session_id=payload.session_id,
        project_key=payload.project_scope.project_key,
        turn_id=payload.turn_id,
        context={},
        max_iterations=payload.max_iterations,
        max_tool_calls=payload.max_tool_calls,
        resume=resume,
        approved_call_ids=payload.approved_call_ids,
        approval_policy=payload.approval_policy,
    )


def _expected_observation_digest(
    request: Any,
) -> str:
    """Recompute the exact C2.1 observation digest over one request."""

    return SourceResolutionObservation(
        observation_profile=SOURCE_RESOLUTION_OBSERVATION_PROFILE,
        project_scope=request.project_scope,
        item_revision=request.item_revision,
        item_incarnation=request.item_incarnation,
        item_content_digest=request.item_content_digest,
        catalog_revision=request.catalog_revision,
        catalog_incarnation=request.catalog_incarnation,
        catalog_digest=request.catalog_digest,
        normalized_params=request.params,
        source_mode=request.source_mode,
        taxonomy=request.taxonomy,
        warnings=request.warnings,
        protocol=request.protocol,
    ).observation_digest


def _legacy_request_from_c6_2(
    payload: c6_2.AgentModelStepRequest,
) -> AgentCoreRequest:
    return AgentCoreRequest(
        message=payload.message_ref,
        session_id=payload.session_id,
        project_key=payload.project_scope.project_key,
        turn_id=payload.turn_id,
        context={},
        max_iterations=payload.max_iterations,
        max_tool_calls=payload.max_tool_calls,
        approval_policy="frozen",
    )


def _count_provider_calls(provider: Any) -> int:
    calls = getattr(provider, "calls", None)
    if isinstance(calls, list):
        return len(calls)
    return 0


class LegacyProviderPortAdapter:
    """Expose one legacy ``CoreProvider`` as the C6.2 provider port."""

    interpreter_id = "legacy.agent_core.c6_2.provider.v1"

    def __init__(self, provider: CoreProvider) -> None:
        self.provider = provider

    @property
    def provider_calls(self) -> int:
        return _count_provider_calls(self.provider)

    def next_step(
        self, request: c6_2.AgentModelStepRequest
    ) -> c6_2.ProviderStepOutcome:
        legacy_request = _legacy_request_from_c6_2(request)
        tools = [
            CoreToolSpec(
                name=ref,
                description_for_model=ref,
                input_schema={"type": "object", "properties": {}},
            )
            for ref in request.tool_contract_refs
        ]
        try:
            step = self.provider.next_step(
                request=legacy_request,
                tools=tools,
                transcript=[{"role": "user", "content": request.message_ref}],
                remaining_budget={
                    "max_iterations": request.max_iterations,
                    "iteration": request.iteration,
                    "max_tool_calls": request.max_tool_calls,
                    "remaining_tool_calls": request.remaining_tool_calls,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return c6_2.ProviderFailure(
                code="ProviderInvocationFailed",
                message=f"legacy provider invocation failed: {exc}",
                retryable=True,
            )
        return c6_2.ProviderStepSucceeded(
            schema_version="mrw.successor.agent-core.c6-2.step-success.v1",
            step=_legacy_model_step_to_agent(step),
            provider_observation_ref=(
                "legacy.provider_observation.v1:" + step.step_type
            ),
            provider_calls=self.provider_calls,
        )

    def readback(self, attempt_id: str) -> c6_2.ProviderReadback:
        return c6_2.ProviderReadback(
            schema_version=c6_2.PROVIDER_READBACK_SCHEMA_REF,
            attempt_id=attempt_id,
            status="NON_START_PROOF",
        )


class NamedProviderModelStepInterpreter:
    """Legacy realization of the C6.2 Program over a legacy CoreProvider."""

    interpreter_id = AGENT_CORE_C6_2_LEGACY_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: Any,
        payload_ref: Any,
        payload: c6_2.AgentModelStepRequest,
        project_scope: ProjectScope,
        catalog: Any,
        deployment_catalog_digest: str,
        binding: Any,
        provider: CoreProvider,
        attempt_id: str,
    ) -> Any:
        require_exact_provider_binding(
            program=program,
            plan=plan,
            contract_ref=contract_ref,
            payload_ref=payload_ref,
            payload=payload,
            project_scope=project_scope,
            catalog=catalog,
            deployment_catalog_digest=deployment_catalog_digest,
            binding=binding,
            expected_interpreter_profile_digest=c6_2_legacy_profile_digest(),
        )
        return c6_2.interpret_model_step(
            payload,
            LegacyProviderPortAdapter(provider),
            attempt_id=attempt_id,
        )


class LegacyAgentCoreCapabilityInterpreter:
    """Legacy realization of the C6.1 Program through ``AgentCore.run``."""

    interpreter_id = AGENT_CORE_C6_1_LEGACY_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: Any,
        payload_ref: Any,
        payload: c6_1.AgentTurnRequest,
        project_scope: ProjectScope,
        catalog: Any,
        deployment_catalog_digest: str,
        binding: Any,
        scripted_steps: list[AgentModelStep] | tuple[AgentModelStep, ...],
        specimen: c6_1.ToolSpecimen,
        redactor: c6_1.EventRedactor,
        permission_policy: c6_1.PermissionPolicy | None = None,
    ) -> c6_1.AgentTurnEpisode:
        require_exact_episode_binding(
            program=program,
            plan=plan,
            contract_ref=contract_ref,
            payload_ref=payload_ref,
            payload=payload,
            project_scope=project_scope,
            catalog=catalog,
            deployment_catalog_digest=deployment_catalog_digest,
            binding=binding,
            expected_interpreter_profile_digest=c6_1_legacy_profile_digest(),
        )
        legacy_request = _legacy_request_from_c6_1(payload)
        provider = FakeCoreProvider(
            [_agent_model_step_to_legacy(step) for step in scripted_steps]
        )
        spec = CoreToolSpec(
            name=specimen.tool_name,
            description_for_model=f"Pure {specimen.tool_name} specimen.",
            input_schema={"type": "object", "properties": {}},
            permission=(
                "ask"
                if permission_policy is not None
                and permission_policy.permission_for(
                    AgentToolCall(
                        call_id="permission-probe",
                        tool_name=specimen.tool_name,
                    )
                )
                == "ask"
                else "allow"
            ),
            risk="read_only",
        )
        executor = _SpecimenCoreToolExecutor(specimen)
        result = AgentCore(
            provider=provider,
            tool_registry=executor,
            tool_specs=[spec],
        ).run(legacy_request, event_sink=None)
        return _episode_from_legacy_result(payload, result, redactor)


def _episode_from_legacy_result(
    payload: c6_1.AgentTurnRequest,
    result: AgentCoreRunResult,
    redactor: c6_1.EventRedactor,
) -> c6_1.AgentTurnEpisode:
    events: list[c6_1.AgentTurnEvent] = []
    for event in result.events:
        event_type = _LEGACY_EVENT_TYPE_MAP.get(event.event_type, "error")
        events.append(
            c6_1.AgentTurnEvent(
                schema_version=c6_1.AGENT_TURN_EVENT_SCHEMA_REF,
                event_type=event_type,
                actor=str(event.actor or "agent_core"),
                payload=redactor.redact(
                    event_type=event_type,
                    call_id=event.call_id,
                    payload=dict(event.payload or {}),
                ),
                call_id=event.call_id,
            )
        )
    stop_reason = _LEGACY_STOP_REASON_MAP.get(result.stop_reason, "error")
    iteration = (
        payload.max_iterations
        if stop_reason in {"max_iterations_exceeded", "max_tool_calls_exceeded"}
        else max(1, min(payload.max_iterations, len(events)))
    )
    return c6_1.AgentTurnEpisode(
        schema_version=c6_1.AGENT_TURN_EPISODE_SCHEMA_REF,
        episode_id=f"episode:{payload.turn_id}",
        request_digest=payload.payload_digest,
        ordered_events=tuple(events),
        tool_results=tuple(
            AgentToolResult(
                call_id=item.call_id,
                tool_name=item.tool_name,
                status=item.status,
                model_summary=item.model_summary,
                ui_summary=item.ui_summary,
                structured_content=freeze_c6_json_object(
                    dict(item.structured_content or {})
                ),
                error=None
                if item.error is None
                else freeze_c6_json_object(dict(item.error)),
                retry_hint=item.retry_hint,
            )
            for item in result.tool_results
        ),
        final_answer=result.final_answer,
        stop_reason=stop_reason,
        tool_call_count=len(result.tool_results),
        iteration=iteration,
    )


class RedactedObservationAdapter:
    """Legacy realization of the C6.3 Program over legacy event payloads."""

    interpreter_id = AGENT_CORE_C6_3_LEGACY_INTERPRETER_ID

    def __init__(self) -> None:
        self.legacy_trace: dict[str, Any] | None = None

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: Any,
        payload_ref: Any,
        payload: c6_3.RedactionEvidencePayload,
        project_scope: ProjectScope,
        catalog: Any,
        deployment_catalog_digest: str,
        binding: Any,
        raw_observation: dict[str, Any],
    ) -> c6_3.RedactionReceipt:
        """Same-Program legacy interpreter; rejects any exact binding drift."""

        require_exact_redaction_binding(
            program=program,
            plan=plan,
            contract_ref=contract_ref,
            payload_ref=payload_ref,
            payload=payload,
            project_scope=project_scope,
            catalog=catalog,
            deployment_catalog_digest=deployment_catalog_digest,
            binding=binding,
            expected_interpreter_profile_digest=c6_3_legacy_profile_digest(),
        )
        receipt = c6_3.redact_observation(payload, raw_observation)
        if isinstance(receipt, c6_3.RedactionFailure):
            raise LegacyRedactionFailed(f"legacy C6.3 redaction failed: {receipt.code}")
        self.legacy_trace = {
            "interpreter_id": self.interpreter_id,
            "source_observation_digest": payload.source_observation_digest,
            "policy_digest": payload.policy.policy_digest,
            "redaction_receipt_digest": receipt.receipt_digest,
            "redacted_digest": receipt.evidence.redacted_digest,
            "raw_sensitive_values_absent": True,
            "trace_digest": content_digest(
                {
                    "interpreter_id": self.interpreter_id,
                    "source_observation_digest": payload.source_observation_digest,
                    "policy_digest": payload.policy.policy_digest,
                    "redaction_receipt_digest": receipt.receipt_digest,
                }
            ),
        }
        return receipt

    def redact_legacy_event(
        self,
        *,
        project_scope: ProjectScope,
        source_observation_ref: str,
        source_kind: str,
        trace_id: str,
        request_id: str,
        call_id: str,
        interpreter_profile_ref: str,
        policy: c6_3.RedactionPolicyRef,
        field_classifications: dict[str, str],
        raw_event_payload: dict[str, Any],
    ) -> c6_3.RedactionReceiptOrFailure:
        payload = c6_3.RedactionEvidencePayload(
            schema_version=c6_3.AGENT_CORE_C6_3_PAYLOAD_SCHEMA,
            operation_kind=c6_3.AGENT_CORE_C6_3_KIND,
            project_scope=project_scope,
            source_observation_ref=source_observation_ref,
            source_observation_digest=c6_3.source_observation_digest(raw_event_payload),
            source_kind=source_kind,
            trace_id=trace_id,
            request_id=request_id,
            call_id=call_id,
            interpreter_profile_ref=interpreter_profile_ref,
            policy=policy,
            field_classifications=freeze_c6_json_object(field_classifications),
            max_input_bytes=c6_3.REDACTION_RESOURCE_CEILING.max_input_bytes,
            max_event_batch=c6_3.REDACTION_RESOURCE_CEILING.max_event_batch,
        )
        return c6_3.redact_observation(payload, raw_event_payload)

    def shadow_evidence(
        self,
        *,
        receipts: list[c6_3.RedactionReceipt],
        sensitive_values: list[str],
    ) -> dict[str, Any]:
        encoded = ""
        for receipt in receipts:
            encoded += canonical_json(receipt.to_plain())
        absent = all(value not in encoded for value in sensitive_values)
        return {
            "schema": "mrw.successor.agent-core.c6-3.legacy-shadow.v1",
            "receipt_count": len(receipts),
            "raw_sensitive_values_absent": absent,
            "receipt_digests": [receipt.receipt_digest for receipt in receipts],
        }


def _binding(
    *,
    contract_digest: str,
    interpreter_profile_digest: str,
    project_scope_digest: str,
    authority_requirement_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=interpreter_profile_digest,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest,
    )


def build_legacy_agent_core_c6_1_binding(
    *,
    contract_digest: str,
    project_scope_digest: str,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
    resource_policy_epoch: int = 1,
) -> InterpreterBinding:
    return _binding(
        contract_digest=contract_digest,
        interpreter_profile_digest=c6_1_legacy_profile_digest(),
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=c6_1_authority_requirement_digest(),
        resource_policy_epoch=resource_policy_epoch,
        runtime_protocol_version=runtime_protocol_version,
    )


def build_successor_agent_core_c6_1_binding(
    *,
    contract_digest: str,
    project_scope_digest: str,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
    resource_policy_epoch: int = 1,
) -> InterpreterBinding:
    return _binding(
        contract_digest=contract_digest,
        interpreter_profile_digest=c6_1_successor_profile_digest(),
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=c6_1_authority_requirement_digest(),
        resource_policy_epoch=resource_policy_epoch,
        runtime_protocol_version=runtime_protocol_version,
    )


def build_legacy_agent_core_c6_2_binding(
    *,
    contract_digest: str,
    project_scope_digest: str,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
    resource_policy_epoch: int = 1,
) -> InterpreterBinding:
    return _binding(
        contract_digest=contract_digest,
        interpreter_profile_digest=c6_2_legacy_profile_digest(),
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=c6_2_authority_requirement_digest(),
        resource_policy_epoch=resource_policy_epoch,
        runtime_protocol_version=runtime_protocol_version,
    )


def build_successor_agent_core_c6_2_binding(
    *,
    contract_digest: str,
    project_scope_digest: str,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
    resource_policy_epoch: int = 1,
) -> InterpreterBinding:
    return _binding(
        contract_digest=contract_digest,
        interpreter_profile_digest=c6_2_successor_profile_digest(),
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=c6_2_authority_requirement_digest(),
        resource_policy_epoch=resource_policy_epoch,
        runtime_protocol_version=runtime_protocol_version,
    )


def build_legacy_agent_core_c6_3_binding(
    *,
    contract_digest: str,
    project_scope_digest: str,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
    resource_policy_epoch: int = 1,
) -> InterpreterBinding:
    return _binding(
        contract_digest=contract_digest,
        interpreter_profile_digest=c6_3_legacy_profile_digest(),
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=c6_3_authority_requirement_digest(),
        resource_policy_epoch=resource_policy_epoch,
        runtime_protocol_version=runtime_protocol_version,
    )


def build_successor_agent_core_c6_3_binding(
    *,
    contract_digest: str,
    project_scope_digest: str,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
    resource_policy_epoch: int = 1,
) -> InterpreterBinding:
    return _binding(
        contract_digest=contract_digest,
        interpreter_profile_digest=c6_3_successor_profile_digest(),
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=c6_3_authority_requirement_digest(),
        resource_policy_epoch=resource_policy_epoch,
        runtime_protocol_version=runtime_protocol_version,
    )


def bindings_are_distinct(
    legacy: InterpreterBinding, successor: InterpreterBinding
) -> bool:
    return (
        legacy.interpreter_profile_digest != successor.interpreter_profile_digest
        and legacy.binding_digest != successor.binding_digest
    )


def legacy_rollback_receipt() -> dict[str, Any]:
    """Deterministic family-local rollback observation for the C6 line."""

    return {
        "schema": "mrw.successor.agent-core.c6.legacy-rollback.v1",
        "status": "LOCAL_FIXTURE_ONLY_PROMOTED_NOT_LIVE",
        "rollback_targets": (
            "legacy.agent_core.c6_1.episode.v1",
            "legacy.agent_core.c6_2.provider.v1",
            "legacy.agent_core.c6_3.redaction.v1",
        ),
        "successor_journal_retained_on_rollback": True,
        "dual_claim_authority": False,
        "provider_calls": 0,
        "raw_value_persisted": False,
    }
