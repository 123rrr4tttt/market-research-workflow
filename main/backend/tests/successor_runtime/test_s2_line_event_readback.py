"""S2 C5.4 line-event/readback runtime binding tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.successor_runtime.assembly.base import (
    C5AssemblyOptions,
    local_assembly_scope_digest,
    sha256_hex,
    successor_binding,
)
from app.successor_runtime.assembly.c5_assembly import (
    C5_4LineEventReadbackRouteHandler,
    build_c5_assembly,
)
from app.successor_runtime.capabilities.line_event_readback_port import (
    IllegalEventMigrationError,
    LineEventReadbackPort,
    LineEventReadbackRecord,
)
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
    NodeIdentity,
    RuntimeExecutionContext,
)
from app.successor_runtime.substrate.projections.legacy_process import (
    LineEventProjectionError,
    project_line_event_readbacks,
)

pytestmark = pytest.mark.unit


def _terminal_record() -> LineEventReadbackRecord:
    record = LineEventReadbackPort.empty("resource_source_library")
    return LineEventReadbackPort.build_acceptance_trace(record)


def test_projection_calls_readback_port_and_builds_payload() -> None:
    record = _terminal_record()

    rows = project_line_event_readbacks((record,))

    assert len(rows) == 1
    row = rows[0]
    assert row["line_key"] == "resource_source_library"
    assert row["record_digest"] == record.digest
    assert row["persistence_decidable"] is True
    assert row["persistence_observed"] is True
    payload = row["payload"]
    assert isinstance(payload, dict)
    assert [item["event"] for item in payload["events"]][-1] == "readback_persisted"
    assert payload["authority"]["canonical_write"] is False
    assert payload["authority"]["live_provider"] is False


def test_undecidable_readback_is_projected_without_terminal_fabrication() -> None:
    record = LineEventReadbackPort.empty("ingest")
    record = LineEventReadbackPort.observe(
        record,
        event="worker_started",
        status="running",
        source="celery_worker",
    )

    rows = project_line_event_readbacks((record,))

    row = rows[0]
    assert row["persistence_decidable"] is False
    assert row["persistence_observed"] is False
    assert "not observed" in str(row["readback_reason"])


def test_projection_rejects_tampered_and_duplicate_records() -> None:
    record = _terminal_record()
    tampered = LineEventReadbackRecord(
        line_key=record.line_key,
        events=record.events,
        status="completed",
        task_id="tampered-task",
        run_id=record.run_id,
        trace_id=record.trace_id,
        worker_name=record.worker_name,
        queue=record.queue,
        digest=record.digest,
    )
    with pytest.raises(IllegalEventMigrationError):
        project_line_event_readbacks((tampered,))

    second = LineEventReadbackPort.build_acceptance_trace(
        LineEventReadbackPort.empty("ingest")
    )
    with pytest.raises(LineEventProjectionError):
        project_line_event_readbacks((record, record))
    assert second is not None


def test_projection_requires_at_least_one_typed_record() -> None:
    with pytest.raises(LineEventProjectionError):
        project_line_event_readbacks(())


def _handler() -> C5_4LineEventReadbackRouteHandler:
    assembly = build_c5_assembly(
        options=C5AssemblyOptions(line_event_readback_records=(_terminal_record(),))
    )
    line_handlers = [
        handler
        for handler in assembly.handlers
        if isinstance(handler, C5_4LineEventReadbackRouteHandler)
    ]
    assert len(line_handlers) == 1
    return line_handlers[0]


def _binding(
    handler: C5_4LineEventReadbackRouteHandler,
) -> InterpreterBinding:
    binding = successor_binding(
        operation_contract_digest=handler.operation_contract_digest,
        interpreter_profile_digest=handler.interpreter_profile_digest,
        deployment_catalog_digest=handler.deployment_catalog_digest,
        project_scope_digest=local_assembly_scope_digest(),
        authority_requirement_digest=sha256_hex(
            "mrw.successor.c5.line-event-readback.authority.v1"
        ),
    )
    assert binding.binding_digest == handler.handler_binding_digest
    return binding


def _assignment(
    handler: C5_4LineEventReadbackRouteHandler,
    binding: InterpreterBinding,
) -> RuntimeAssignment:
    return RuntimeAssignment(
        runtime_protocol_version="mrw.runtime.protocol.v1",
        work_item_id="work:i1-c5-4-s2:001",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="i1-local-c5",
        run_id="run:i1-c5-4-s2:001",
        step_id="step:c5-4:line-readback",
        step_role=CompiledStepRole.EFFECT,
        capability_id="legacy.line_event_readback.project.v1",
        operation_contract_ref=OperationContractRef(
            kind="legacy.line_event_readback.project.v1",
            contract_version="1.0.0",
            contract_digest=handler.operation_contract_digest,
        ),
        operation_contract_digest=handler.operation_contract_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "mrw.successor.runtime.c5-4.line-event-readback.v1",
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
        incarnation="inc:i1-c5-4-s2:001",
        input_refs=(),
        queue_eligibility_digest="0" * 64,
        resource_policy_epoch=1,
        claim_authority_epoch=1,
        claim_policy_digest="0" * 64,
        expected_step_revision=0,
        trace_id="trace:i1-c5-4-s2:001",
    )


def _claim(
    handler: C5_4LineEventReadbackRouteHandler,
    assignment: RuntimeAssignment,
) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest="0" * 64,
        lease_token="lease:i1-c5-4-s2",
        lease_expires_at=datetime(2026, 9, 2, 2, 0, tzinfo=UTC),
        node_id="node:i1-c5-4-s2",
        node_profile_digest="0" * 64,
        authority_digest="0" * 64,
        interpreter_profile_digest=handler.interpreter_profile_digest,
    )


def _context() -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        node=NodeIdentity(
            node_id="node:i1-c5-4-s2",
            incarnation="node-inc:i1-c5-4-s2",
            started_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
        ),
        observed_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
    )


def test_c5_assembly_route_handler_executes_readback_projection() -> None:
    handler = _handler()
    binding = _binding(handler)
    assignment = _assignment(handler, binding)
    claim = _claim(handler, assignment)

    outcome = handler.execute(assignment, claim, _context())

    assert outcome.result_digest is not None
    assert len(outcome.result_digest) == 64
    assert outcome.receipt_ref == "receipt:line-event-readback:c5-4"
    assembly = build_c5_assembly(
        options=C5AssemblyOptions(line_event_readback_records=handler.records)
    )
    assert "S2 line-event readback route handler" in assembly.cell("C5.4").note
