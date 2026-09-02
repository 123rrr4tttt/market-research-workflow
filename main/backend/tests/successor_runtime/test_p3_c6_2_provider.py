"""P3 C6.2 deterministic provider port, failures, OUTCOME_UNKNOWN/readback."""

from __future__ import annotations

import inspect
import json

import pytest

from app.successor_runtime.capabilities import agent_core_c6_2 as c6_2
from app.successor_runtime.capabilities.agent_core_c6_2_interpreters import (
    ProviderBindingMismatch,
    authority_requirement_digest,
    require_exact_provider_binding,
    successor_interpreter_profile_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_2_program import (
    build_agent_core_c6_2_program,
    compile_agent_core_c6_2_program,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    AgentModelStep,
    AgentToolCall,
    ProjectScope,
    c6_deployment_catalog_digest,
    freeze_c6_json_object,
)
from app.successor_runtime.language.program import decode_program_spec
from app.successor_runtime.runtime.assignments import InterpreterBinding

pytestmark = pytest.mark.unit

PROJECT_KEY = "demo_proj"
REGISTRY_REVISION = 5
RESOLVED_SCHEMA = "mrw_p_demo_proj"
SCOPE_INCARNATION = "scope-inc-5"
SCOPE_DIGEST = ProjectScope(
    PROJECT_KEY,
    REGISTRY_REVISION,
    RESOLVED_SCHEMA,
    SCOPE_INCARNATION,
    "",
).scope_digest
ATTEMPT_ID = "attempt:c6-2:001"


def _scope() -> ProjectScope:
    return ProjectScope(
        PROJECT_KEY,
        REGISTRY_REVISION,
        RESOLVED_SCHEMA,
        SCOPE_INCARNATION,
        "",
    )


def _request(**overrides) -> c6_2.AgentModelStepRequest:
    values = {
        "schema_version": c6_2.AGENT_CORE_C6_2_PAYLOAD_SCHEMA,
        "operation_kind": c6_2.AGENT_CORE_C6_2_KIND,
        "project_scope": _scope(),
        "session_id": "session-c6-2",
        "turn_id": "turn-c6-2",
        "message_ref": "project-value:message:c6-2",
        "transcript_ref": "project-value:transcript:c6-2",
        "tool_contract_refs": ("source_library.resolve_execution_request.v1",),
        "max_iterations": 3,
        "iteration": 1,
        "max_tool_calls": 2,
        "remaining_tool_calls": 2,
        "provider_profile_ref": "fixture.agent_core.c6_2.provider.v1",
        "credential_ref": "credential:opaque:c6-2",
    }
    values.update(overrides)
    return c6_2.AgentModelStepRequest(**values)


def _final_step() -> AgentModelStep:
    return AgentModelStep(
        schema_version="mrw.successor.agent-core.c6.model-step.v1",
        step_type="final_answer",
        content="provider answered",
        metadata=freeze_c6_json_object({"model_path": "fake_core_provider"}),
    )


def _tool_step() -> AgentModelStep:
    return AgentModelStep(
        schema_version="mrw.successor.agent-core.c6.model-step.v1",
        step_type="tool_calls",
        tool_calls=(
            AgentToolCall(
                call_id="call-c6-2-1",
                tool_name="source_library.resolve_execution_request",
                arguments=freeze_c6_json_object({"query_terms": ["robotics"]}),
            ),
        ),
    )


def _catalog_and_registry():
    bundle = c6_2.build_agent_core_c6_2_bundle()
    catalog = c6_2.build_agent_core_c6_2_catalog(bundle)
    registry = c6_2.build_agent_core_c6_2_registry(bundle)
    return bundle, catalog, registry


def _program(payload):
    _bundle, catalog, _registry = _catalog_and_registry()
    return build_agent_core_c6_2_program(
        payload=payload,
        catalog=catalog,
        program_id="p3.c6-2.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )


def _plan(program):
    _bundle, catalog, registry = _catalog_and_registry()
    return compile_agent_core_c6_2_program(
        program, catalog, operation_contracts=registry
    )


def _binding(contract_ref):
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_ref.contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest(),
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        runtime_protocol_version="mrw.runtime.protocol.v1",
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=1,
        authority_requirement_digest=authority_requirement_digest(),
    )


def test_scripted_success_receipt_counts_exact_provider_calls() -> None:
    request = _request()
    port = c6_2.TestReceiptProviderPort(
        [
            c6_2.ProviderStepSucceeded(
                schema_version="mrw.successor.agent-core.c6-2.step-success.v1",
                step=_final_step(),
                provider_observation_ref="project-value:observation:c6-2",
                provider_calls=1,
            )
        ]
    )
    result = c6_2.interpret_model_step(request, port, attempt_id=ATTEMPT_ID)
    assert port.provider_calls == 1
    assert result.receipt.outcome_code == "ProviderStepSucceeded"
    assert result.receipt.provider_calls == 1
    assert result.receipt.readback_status == "NOT_APPLICABLE"
    assert result.step is not None and result.step.step_type == "final_answer"


def test_typed_failure_codes_are_not_collapsed() -> None:
    request = _request()
    for code, message in (
        ("ProviderUnavailable", "unavailable"),
        ("ProviderTimeout", "timeout"),
        ("ProviderRateLimited", "rate limited"),
        ("ProviderCredentialRejected", "credential rejected"),
        ("ProviderFallbackSelected", "fallback selected"),
    ):
        port = c6_2.TestReceiptProviderPort(
            [
                c6_2.ProviderFailure(
                    code=code,
                    message=message,
                    retryable=code in {"ProviderTimeout", "ProviderRateLimited"},
                )
            ]
        )
        result = c6_2.interpret_model_step(request, port, attempt_id=ATTEMPT_ID)
        assert result.receipt.outcome_code == code
        assert result.receipt.provider_calls == 1
        assert result.step is None


def test_outcome_unknown_readback_success_and_failure() -> None:
    request = _request()
    succeeded = c6_2.ProviderReadback(
        schema_version=c6_2.PROVIDER_READBACK_SCHEMA_REF,
        attempt_id=ATTEMPT_ID,
        status="AUTHORITATIVE_READBACK_SUCCEEDED",
        provider_observation_digest="a" * 64,
    )
    port = c6_2.TestReceiptProviderPort(
        [
            c6_2.ProviderFailure(
                code="ProviderOutcomeUnknown", message="unknown", retryable=False
            )
        ],
        readbacks={ATTEMPT_ID: succeeded},
    )
    result = c6_2.interpret_model_step(request, port, attempt_id=ATTEMPT_ID)
    assert result.receipt.outcome_code == "ProviderOutcomeUnknown"
    assert result.receipt.readback_status == "AUTHORITATIVE_READBACK_SUCCEEDED"
    assert result.receipt.readback_digest == "a" * 64

    failed_port = c6_2.TestReceiptProviderPort(
        [
            c6_2.ProviderFailure(
                code="ProviderOutcomeUnknown", message="unknown", retryable=False
            )
        ],
        readbacks={
            ATTEMPT_ID: c6_2.ProviderReadback(
                schema_version=c6_2.PROVIDER_READBACK_SCHEMA_REF,
                attempt_id=ATTEMPT_ID,
                status="AUTHORITATIVE_READBACK_FAILED",
                provider_observation_digest="b" * 64,
            )
        },
    )
    failed = c6_2.interpret_model_step(request, failed_port, attempt_id=ATTEMPT_ID)
    assert failed.receipt.readback_status == "AUTHORITATIVE_READBACK_FAILED"
    assert failed.receipt.readback_digest == "b" * 64


def test_readback_attempt_mismatch_is_rejected() -> None:
    request = _request()
    port = c6_2.TestReceiptProviderPort(
        [
            c6_2.ProviderFailure(
                code="ProviderOutcomeUnknown",
                message="unknown",
                retryable=False,
            )
        ],
        readbacks={
            ATTEMPT_ID: c6_2.ProviderReadback(
                schema_version=c6_2.PROVIDER_READBACK_SCHEMA_REF,
                attempt_id="attempt:other",
                status="NON_START_PROOF",
            )
        },
    )
    with pytest.raises(ValueError, match="attempt_id"):
        c6_2.interpret_model_step(request, port, attempt_id=ATTEMPT_ID)


def test_authoritative_readback_requires_canonical_digest() -> None:
    request = _request()
    for status in (
        "AUTHORITATIVE_READBACK_SUCCEEDED",
        "AUTHORITATIVE_READBACK_FAILED",
    ):
        port = c6_2.TestReceiptProviderPort(
            [
                c6_2.ProviderFailure(
                    code="ProviderOutcomeUnknown",
                    message="unknown",
                    retryable=False,
                )
            ],
            readbacks={
                ATTEMPT_ID: c6_2.ProviderReadback(
                    schema_version=c6_2.PROVIDER_READBACK_SCHEMA_REF,
                    attempt_id=ATTEMPT_ID,
                    status=status,
                    provider_observation_digest=None,
                )
            },
        )
        with pytest.raises(ValueError, match="observation digest"):
            c6_2.interpret_model_step(request, port, attempt_id=ATTEMPT_ID)


def test_receipt_only_port_proves_zero_provider_calls() -> None:
    request = _request()
    evidence = c6_2.build_c6_2_receipt_only_evidence(request, attempt_id=ATTEMPT_ID)
    assert evidence["provider_calls"] == 0
    assert evidence["outcome_code"] == "ProviderOutcomeUnknown"
    assert evidence["readback_status"] == "NON_START_PROOF"
    assert evidence["network_required"] is False
    assert evidence["live_provider_claim"] is False


def test_replay_receipt_is_deterministic() -> None:
    request = _request()
    first = c6_2.interpret_model_step(
        request,
        c6_2.TestReceiptProviderPort(
            [
                c6_2.ProviderStepSucceeded(
                    schema_version="mrw.successor.agent-core.c6-2.step-success.v1",
                    step=_final_step(),
                    provider_observation_ref="project-value:observation:c6-2",
                    provider_calls=1,
                )
            ]
        ),
        attempt_id=ATTEMPT_ID,
    )
    second = c6_2.interpret_model_step(
        request,
        c6_2.TestReceiptProviderPort(
            [
                c6_2.ProviderStepSucceeded(
                    schema_version="mrw.successor.agent-core.c6-2.step-success.v1",
                    step=_final_step(),
                    provider_observation_ref="project-value:observation:c6-2",
                    provider_calls=1,
                )
            ]
        ),
        attempt_id=ATTEMPT_ID,
    )
    assert first.result_digest == second.result_digest
    assert first.receipt.receipt_digest == second.receipt.receipt_digest


def test_program_plan_compile_and_binding_mismatch() -> None:
    payload = _request()
    program = _program(payload)
    plan = _plan(program)
    _bundle, catalog, registry = _catalog_and_registry()
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
    decoded = decode_program_spec(
        {
            "program": json.loads(program.canonical_json()),
            "program_digest": program.digest(),
        }
    )
    assert decoded.program_digest == program.program_digest
    binding = _binding(contract_ref)
    require_exact_provider_binding(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=binding,
    )
    with pytest.raises(ProviderBindingMismatch):
        require_exact_provider_binding(
            program=_program(_request(session_id="tampered")),
            plan=plan,
            contract_ref=contract_ref,
            payload_ref=program.root.operation.payload_ref,
            payload=payload,
            project_scope=_scope(),
            catalog=catalog,
            deployment_catalog_digest=c6_deployment_catalog_digest(),
            binding=binding,
        )


def test_module_never_reads_global_settings() -> None:
    source = inspect.getsource(c6_2)
    assert "app.settings" not in source
    assert "get_chat_model" not in source
    assert "openai" not in source.lower()
