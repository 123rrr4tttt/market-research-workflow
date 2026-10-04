"""S2 C9.1 runtime binding tests for the request-identity horizontal port.

These tests prove that the C9.1 facade validation route handler genuinely
consumes the successor request-identity port during ``execute`` and fails
closed before any facade read when the request actor is not trusted or does
not match the facade actor_ref.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.successor_runtime.assembly import projection_assembly
from app.successor_runtime.assembly.base import ProjectionAssemblyOptions
from app.successor_runtime.assembly.projection_assembly import (
    PROJECTION_COMMAND_QUERY_OPERATION_CONTRACT_REFS,
    PROJECTION_COMMAND_QUERY_ACTOR_BINDING_MISMATCH,
    PROJECTION_COMMAND_QUERY_DEPLOYMENT_CATALOG_DRIFT,
    PROJECTION_COMMAND_QUERY_FACADE_BINDING_DRIFT,
    PROJECTION_COMMAND_QUERY_PAYLOAD_UNSUPPORTED,
    PROJECTION_COMMAND_QUERY_TRUSTED_ACTOR_REQUIRED,
    ProjectionCommandQueryValidationRouteHandler,
    build_projection_assembly,
    build_deterministic_facade_closure,
)
from app.successor_runtime.capabilities import request_identity_port
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.projection_native_contribution import (
    PROJECTION_COMMAND_QUERY_CELL_ID,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    NodeIdentity,
    RuntimeExecutionContext,
)

pytestmark = pytest.mark.unit


def _handler_and_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ProjectionCommandQueryValidationRouteHandler, InterpreterBinding]:
    captured: dict[str, InterpreterBinding] = {}
    original_successor_binding = projection_assembly.successor_binding

    def capture_binding(**kwargs: object) -> InterpreterBinding:
        binding = original_successor_binding(**kwargs)  # type: ignore[arg-type]
        captured["binding"] = binding
        return binding

    monkeypatch.setattr(projection_assembly, "successor_binding", capture_binding)
    assembly = build_projection_assembly(
        options=ProjectionAssemblyOptions(facade=build_deterministic_facade_closure())
    )
    assert len(assembly.handlers) == 1
    handler = assembly.handlers[0]
    assert isinstance(handler, ProjectionCommandQueryValidationRouteHandler)
    binding = captured["binding"]
    assert binding.binding_digest == handler.handler_binding_digest
    return handler, binding


def _assignment(
    handler: ProjectionCommandQueryValidationRouteHandler,
    binding: InterpreterBinding,
) -> RuntimeAssignment:
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work:i1-c9-1-s2:001",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="i1-local-c9",
        run_id="run:i1-c9-1-s2:001",
        step_id="step:c9-1:validate",
        step_role=CompiledStepRole.EFFECT,
        capability_id="facade.query.read-only.v1",
        operation_contract_ref=OperationContractRef(
            kind="facade.query.read-only.v1",
            contract_version="1.0.0",
            contract_digest=handler.operation_contract_digest,
        ),
        operation_contract_digest=handler.operation_contract_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "mrw.successor.c9.validation.v1",
            ReturnContract(
                success_modes=("SUCCEEDED",),
                failure_modes=("FAILED",),
                admission_required=False,
                wait_modes=(),
                cancel_modes=(),
            ),
        ),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=binding.binding_digest,
        deployment_catalog_digest=handler.deployment_catalog_digest,
        execution_epoch=1,
        incarnation="inc:i1-c9-1-s2:001",
        input_refs=(),
        queue_eligibility_digest="0" * 64,
        resource_policy_epoch=1,
        claim_authority_epoch=1,
        claim_policy_digest="0" * 64,
        expected_step_revision=0,
        trace_id="trace:i1-c9-1-s2:001",
    )


def _claim(
    handler: ProjectionCommandQueryValidationRouteHandler,
    assignment: RuntimeAssignment,
) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest="0" * 64,
        lease_token="lease:i1-c9-1-s2",
        lease_expires_at=datetime(2026, 9, 2, 2, 0, tzinfo=UTC),
        node_id="node:i1-c9-1-s2",
        node_profile_digest="0" * 64,
        authority_digest="0" * 64,
        interpreter_profile_digest=handler.interpreter_profile_digest,
    )


def _context() -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        node=NodeIdentity(
            node_id="node:i1-c9-1-s2",
            incarnation="node-inc:i1-c9-1-s2",
            started_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
        ),
        observed_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
    )


def test_c9_1_route_execute_consumes_request_identity_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler, binding = _handler_and_binding(monkeypatch)
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    outcome = handler.execute(assignment, claim, _context())

    assert handler.request_identity_calls == 1
    assert handler.last_actor_context is not None
    assert handler.last_actor_context.actor_trusted is True
    assert handler.last_actor_context.actor_id == "local-offline-validation"
    assert outcome.result_digest is not None
    assert len(outcome.result_digest) == 64


def test_facade_binding_drift_uses_business_failure_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler, binding = _handler_and_binding(monkeypatch)
    assignment = _assignment(handler, binding).model_copy(
        update={"handler_binding_digest": "f" * 64}
    )
    claim = _claim(handler, assignment)

    with pytest.raises(DefiniteInterpreterFailure) as exc:
        handler.execute(assignment, claim, _context())

    assert exc.value.failure_code == PROJECTION_COMMAND_QUERY_FACADE_BINDING_DRIFT


def test_deployment_catalog_drift_uses_business_failure_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler, binding = _handler_and_binding(monkeypatch)
    assignment = _assignment(handler, binding).model_copy(
        update={"deployment_catalog_digest": "f" * 64}
    )
    claim = _claim(handler, assignment)

    with pytest.raises(DefiniteInterpreterFailure) as exc:
        handler.execute(assignment, claim, _context())

    assert exc.value.failure_code == (
        PROJECTION_COMMAND_QUERY_DEPLOYMENT_CATALOG_DRIFT
    )


def test_untrusted_request_actor_fails_closed_before_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler, binding = _handler_and_binding(monkeypatch)
    handler.request_identity_observation = (
        request_identity_port.RequestIdentityObservation(
            headers={"x-forwarded-user": "spoofed-user"},
        )
    )
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    with pytest.raises(DefiniteInterpreterFailure) as exc:
        handler.execute(assignment, claim, _context())

    assert exc.value.failure_code == PROJECTION_COMMAND_QUERY_TRUSTED_ACTOR_REQUIRED
    assert handler.request_identity_calls == 1
    assert handler.last_actor_context is None


def test_request_actor_mismatch_fails_closed_before_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler, binding = _handler_and_binding(monkeypatch)
    handler.request_identity_observation = (
        request_identity_port.RequestIdentityObservation(
            actor_id="different-actor",
            actor_trusted=True,
        )
    )
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    with pytest.raises(DefiniteInterpreterFailure) as exc:
        handler.execute(assignment, claim, _context())

    assert exc.value.failure_code == PROJECTION_COMMAND_QUERY_ACTOR_BINDING_MISMATCH
    assert handler.request_identity_calls == 1


def test_unsupported_projection_payload_uses_business_failure_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler, binding = _handler_and_binding(monkeypatch)
    handler.query = SimpleNamespace(  # type: ignore[assignment]
        actor_ref="local-offline-validation"
    )
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    with pytest.raises(DefiniteInterpreterFailure) as exc:
        handler.execute(assignment, claim, _context())

    assert exc.value.failure_code == PROJECTION_COMMAND_QUERY_PAYLOAD_UNSUPPORTED
    assert handler.request_identity_calls == 1


def test_c9_1_assembly_carries_request_identity_route_without_authority() -> None:
    assembly = build_projection_assembly(
        options=ProjectionAssemblyOptions(facade=build_deterministic_facade_closure())
    )
    cell = assembly.cell(PROJECTION_COMMAND_QUERY_CELL_ID)
    assert cell.status == "INSTALLED"
    assert "request-identity port consumed" in cell.note
    assert PROJECTION_COMMAND_QUERY_OPERATION_CONTRACT_REFS == (
        "projection.command.validation-only.v2",
        "projection.query.read-only.v2",
        "projection.api.envelope.status-data-error-meta.v2",
        "projection.request.server-bound-scope-actor-identity.v2",
        "projection.response.control-feedback-forbidden.v2",
    )
    assert request_identity_port.REQUEST_IDENTITY_PORT_REF
