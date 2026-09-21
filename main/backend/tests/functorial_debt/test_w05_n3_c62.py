"""W05-N3 C6.2 typed-failure and legacy-boundary witnesses."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from functorial_kit import Failure
from mrw_functorial_kit.core import successor_capability_contract_failures

from app.successor_runtime.capabilities import agent_core_c6_2 as c6_2
from app.successor_runtime.capabilities import (
    agent_core_c6_2_live_model_port as live,
)
from app.successor_runtime.capabilities import agent_core_c6_2_program as program
from app.successor_runtime.capabilities.agent_core_c6_2_interpreters import (
    ProviderBindingMismatch,
    require_exact_provider_binding,
    try_require_exact_provider_binding,
)
from app.successor_runtime.capabilities.agent_core_c6_common import ProjectScope


ATTEMPT_ID = "attempt:w05-n3:c6-2"
WITNESS = "test:test_w05_n3_c62_typed_contract_failures"
REPO_ROOT = Path(__file__).resolve().parents[4]
TARGETS = (
    Path("main/backend/app/successor_runtime/capabilities/agent_core_c6_2.py"),
    Path("main/backend/app/successor_runtime/capabilities/agent_core_c6_2_interpreters.py"),
    Path("main/backend/app/successor_runtime/capabilities/agent_core_c6_2_live_model_port.py"),
    Path("main/backend/app/successor_runtime/capabilities/agent_core_c6_2_program.py"),
)


def _scope() -> ProjectScope:
    return ProjectScope("demo_proj", 5, "mrw_p_demo_proj", "scope-inc-5", "")


def _request() -> c6_2.AgentModelStepRequest:
    return c6_2.AgentModelStepRequest(
        schema_version=c6_2.AGENT_CORE_C6_2_PAYLOAD_SCHEMA,
        operation_kind=c6_2.AGENT_CORE_C6_2_KIND,
        project_scope=_scope(),
        session_id="session-w05-n3",
        turn_id="turn-w05-n3",
        message_ref="project-value:message",
        transcript_ref="project-value:transcript",
        tool_contract_refs=("source_library.resolve_execution_request.v1",),
        max_iterations=2,
        iteration=1,
        max_tool_calls=1,
        remaining_tool_calls=1,
        provider_profile_ref="fixture.agent_core.c6_2.provider_port.v1",
        credential_ref="credential:opaque",
    )


def _unknown_port(**readback) -> c6_2.TestReceiptProviderPort:
    return c6_2.TestReceiptProviderPort(
        [
            c6_2.ProviderFailure(
                code="ProviderOutcomeUnknown",
                message="unknown",
                retryable=False,
            )
        ],
        readbacks={ATTEMPT_ID: readback["readback"]} if readback else None,
    )


def test_w05_n3_c62_typed_contract_failures() -> None:
    request = _request()
    port = _unknown_port(
        readback=c6_2.ProviderReadback(
            schema_version=c6_2.PROVIDER_READBACK_SCHEMA_REF,
            attempt_id="attempt:other",
            status="NON_START_PROOF",
        )
    )
    outcome = c6_2.try_interpret_model_step(request, port, attempt_id=ATTEMPT_ID)

    assert isinstance(outcome, c6_2.ProviderFailure)
    assert outcome.code == "ProviderInvocationFailed"
    assert outcome.message == ("provider readback attempt_id does not match the requested attempt")
    failure = c6_2._contract_failure(
        "scope_contract_invalid",
        outcome.message,
        attempt_id=ATTEMPT_ID,
    )
    assert successor_capability_contract_failures.matches(failure)
    assert failure.context is not None
    assert failure.context["witness"] == WITNESS


def test_public_interpret_lifts_exact_readback_message() -> None:
    request = _request()
    port = _unknown_port(
        readback=c6_2.ProviderReadback(
            schema_version=c6_2.PROVIDER_READBACK_SCHEMA_REF,
            attempt_id="attempt:other",
            status="NON_START_PROOF",
        )
    )

    with pytest.raises(ValueError, match="^provider readback attempt_id"):
        c6_2.interpret_model_step(request, port, attempt_id=ATTEMPT_ID)


def test_public_interpret_lifts_missing_authoritative_digest() -> None:
    request = _request()
    port = _unknown_port(
        readback=c6_2.ProviderReadback(
            schema_version=c6_2.PROVIDER_READBACK_SCHEMA_REF,
            attempt_id=ATTEMPT_ID,
            status="AUTHORITATIVE_READBACK_SUCCEEDED",
            provider_observation_digest=None,
        )
    )

    with pytest.raises(ValueError, match="^authoritative readback requires"):
        c6_2.interpret_model_step(request, port, attempt_id=ATTEMPT_ID)


def test_http_body_decode_returns_typed_protocol_failure() -> None:
    for raw in (b"not-json", b"[]"):
        outcome = live._decode_http_body(raw, require_object=True)
        assert isinstance(outcome, c6_2.ProviderFailure)
        assert outcome.code == "ProviderProtocolInvalid"


def test_fake_transport_can_return_provider_failure_directly() -> None:
    class Transport:
        calls = 0

        def __call__(self, url, body, headers, timeout_seconds):
            self.calls += 1
            assert timeout_seconds == 30.0
            return 200, c6_2.ProviderFailure(
                code="ProviderProtocolInvalid",
                message="fake typed transport failure",
                retryable=False,
            )

    transport = Transport()
    port = live.OpenAILiveProviderPort(
        api_key_provider=lambda: "fixture-key",
        transport=transport,
    )
    outcome = port.next_step(_request())
    assert transport.calls == 1
    assert isinstance(outcome, c6_2.ProviderFailure)
    assert outcome.message == "fake typed transport failure"


def test_program_drift_returns_kit_failure_and_public_lift_is_exact() -> None:
    payload = _request()
    outcome = program.try_payload_value_ref(
        payload,
        program_id="w05-n3",
        project_key="other_project",
    )
    assert isinstance(outcome, Failure)
    assert outcome.family == "successor.capability.contract_failure"
    assert outcome.code == "scope_contract_invalid"
    assert outcome.context is not None
    assert outcome.context["witness"] == WITNESS

    with pytest.raises(ValueError, match="^payload project scope drift$"):
        program.payload_value_ref(
            payload,
            program_id="w05-n3",
            project_key="other_project",
        )


def _program_closure(payload):
    bundle = c6_2.build_agent_core_c6_2_bundle()
    catalog = c6_2.build_agent_core_c6_2_catalog(bundle)
    registry = c6_2.build_agent_core_c6_2_registry(bundle)
    built = program.build_agent_core_c6_2_program(
        payload=payload,
        catalog=catalog,
        program_id="w05-n3",
        project_key=payload.project_scope.project_key,
        project_registry_revision=payload.project_scope.registry_revision,
        project_scope_digest=payload.project_scope.scope_digest,
    )
    plan = program.compile_agent_core_c6_2_program(
        built,
        catalog,
        operation_contracts=registry,
    )
    return built, plan, catalog, registry.resolve_required(built.root.operation.contract_ref).ref


def test_binding_drift_returns_kit_failure_and_provider_binding_mismatch() -> None:
    payload = _request()
    built, plan, catalog, contract_ref = _program_closure(payload)
    arguments = {
        "program": built,
        "plan": plan,
        "contract_ref": contract_ref,
        "payload_ref": built.root.operation.payload_ref,
        "payload": payload,
        "project_scope": payload.project_scope,
        "catalog": catalog,
        "deployment_catalog_digest": "0" * 64,
        "binding": SimpleNamespace(binding_digest="not-hex64"),
    }

    outcome = try_require_exact_provider_binding(**arguments)
    assert isinstance(outcome, Failure)
    assert outcome.code == "program_binding_invalid"
    assert outcome.message.startswith("C6.2 provider binding drift: ")
    assert outcome.context is not None
    assert outcome.context["witness"] == WITNESS

    with pytest.raises(ProviderBindingMismatch):
        require_exact_provider_binding(**arguments)


def test_w05_n3_c62_retained_boundary_lifts() -> None:
    checked = 0
    for relative_path in TARGETS:
        path = REPO_ROOT / relative_path
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise):
                continue
            checked += 1
            metadata = lines[node.lineno - 2].strip()
            assert metadata.startswith("# kit:boundary owner=agent_core_c6_2.py ")
            assert "class=" in metadata
            assert "failure_family=" in metadata
            assert "witness=test:test_w05_n3_c62_retained_boundary_lifts" in metadata
    assert checked > 0
