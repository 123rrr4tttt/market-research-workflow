"""S2 C9.1 runtime binding tests for the request-identity horizontal port.

These tests prove that the C9.1 facade validation route handler genuinely
consumes the successor request-identity port during ``execute`` and fails
closed before any facade read when the request actor is not trusted or does
not match the facade actor_ref.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.successor_runtime.assembly.base import (
    C9AssemblyOptions,
    local_assembly_scope_digest,
    successor_binding,
)
from app.successor_runtime.assembly.c9_assembly import (
    C9_1_OPERATION_CONTRACT_REFS,
    C9_AUTHORITY_REQUIREMENT_DIGEST,
    C9_1FacadeValidationRouteHandler,
    build_c9_assembly,
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
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    NodeIdentity,
    RuntimeExecutionContext,
)

pytestmark = pytest.mark.unit


def _handler() -> C9_1FacadeValidationRouteHandler:
    assembly = build_c9_assembly(
        options=C9AssemblyOptions(facade=build_deterministic_facade_closure())
    )
    assert len(assembly.handlers) == 1
    handler = assembly.handlers[0]
    assert isinstance(handler, C9_1FacadeValidationRouteHandler)
    return handler


def _binding(handler: C9_1FacadeValidationRouteHandler) -> InterpreterBinding:
    binding = successor_binding(
        operation_contract_digest=handler.operation_contract_digest,
        interpreter_profile_digest=handler.interpreter_profile_digest,
        deployment_catalog_digest=handler.deployment_catalog_digest,
        project_scope_digest=local_assembly_scope_digest(),
        authority_requirement_digest=C9_AUTHORITY_REQUIREMENT_DIGEST,
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )
    assert binding.binding_digest == handler.handler_binding_digest
    return binding


def _assignment(
    handler: C9_1FacadeValidationRouteHandler,
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
    handler: C9_1FacadeValidationRouteHandler,
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


def test_c9_1_route_execute_consumes_request_identity_port() -> None:
    handler = _handler()
    binding = _binding(handler)
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    outcome = handler.execute(assignment, claim, _context())

    assert handler.request_identity_calls == 1
    assert handler.last_actor_context is not None
    assert handler.last_actor_context.actor_trusted is True
    assert handler.last_actor_context.actor_id == "local-offline-validation"
    assert outcome.result_digest is not None
    assert len(outcome.result_digest) == 64


def test_untrusted_request_actor_fails_closed_before_facade() -> None:
    handler = _handler()
    handler.request_identity_observation = (
        request_identity_port.RequestIdentityObservation(
            headers={"x-forwarded-user": "spoofed-user"},
        )
    )
    binding = _binding(handler)
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    with pytest.raises(DefiniteInterpreterFailure) as exc:
        handler.execute(assignment, claim, _context())

    assert exc.value.failure_code == "C9_1_TRUSTED_ACTOR_REQUIRED"
    assert handler.request_identity_calls == 1
    assert handler.last_actor_context is None


def test_request_actor_mismatch_fails_closed_before_facade() -> None:
    handler = _handler()
    handler.request_identity_observation = (
        request_identity_port.RequestIdentityObservation(
            actor_id="different-actor",
            actor_trusted=True,
        )
    )
    binding = _binding(handler)
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    with pytest.raises(DefiniteInterpreterFailure) as exc:
        handler.execute(assignment, claim, _context())

    assert exc.value.failure_code == "C9_1_REQUEST_ACTOR_BINDING_MISMATCH"
    assert handler.request_identity_calls == 1


def test_c9_1_assembly_carries_request_identity_route_without_authority() -> None:
    assembly = build_c9_assembly(
        options=C9AssemblyOptions(facade=build_deterministic_facade_closure())
    )
    cell = assembly.cell("C9.1")
    assert cell.status == "INSTALLED"
    assert "request-identity port consumed" in cell.note
    assert len(C9_1_OPERATION_CONTRACT_REFS) == 8
    assert request_identity_port.REQUEST_IDENTITY_PORT_REF
