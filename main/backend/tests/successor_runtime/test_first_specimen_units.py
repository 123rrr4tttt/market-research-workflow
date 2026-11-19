"""Focused pure witnesses for the surviving first-specimen delivery gate."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.successor_runtime.capabilities import build_first_specimen_bundle
from app.successor_runtime.capabilities.first_specimen_delivery_gate import (
    DeliveryApprovalSnapshot,
    DeliveryAssignmentParameters,
    DeliveryAssignmentRequest,
    DeliveryAuthoritySnapshot,
    DeliveryGate,
    DeliveryGateCommand,
    DeliveryGateRejected,
    DeliveryIntentTemplate,
)
from app.successor_runtime.language.object_contracts import (
    DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
    build_first_specimen_return_contract_registry,
)
from app.successor_runtime.research.artifacts import artifact_identity_ref
from app.successor_runtime.research.codec import sha256_hex
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import RESEARCH_ARTIFACT_TYPE
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope

NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)
PROJECT_KEY = "p0c"
SCOPE = RuntimeScope(
    ProjectScopeRef(
        project_key=PROJECT_KEY,
        resolved_schema="mrw_p_p0c",
        project_registry_revision=5,
        incarnation="scope-inc-p0c-5",
        scope_digest="1" * 64,
    ),
    actor_id="human:p0c",
)


@dataclass
class _State:
    values: dict[str, dict[str, Any]] = field(default_factory=dict)
    ledger: dict[str, ResearchObjectRef] = field(default_factory=dict)
    delivery_admissions: dict[str, Any] = field(default_factory=dict)
    commits: int = 0
    rollbacks: int = 0


class _FakeUoW:
    def __init__(self, state: _State) -> None:
        self.state = state
        self.committed = False

    def __enter__(self):
        self.values = dict(self.state.values)
        self.ledger = dict(self.state.ledger)
        self.delivery_admissions = dict(self.state.delivery_admissions)
        self.value_port = _ValuePort(self)
        self.ledger_port = _LedgerPort(self)
        self.runtime_port = _RuntimePort(self)
        return self

    def commit(self) -> None:
        self.state.values = self.values
        self.state.ledger = self.ledger
        self.state.delivery_admissions = self.delivery_admissions
        self.state.commits += 1
        self.committed = True

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.committed:
            self.state.rollbacks += 1


class _ValuePort:
    def __init__(self, uow: _FakeUoW) -> None:
        self.uow = uow

    def put_exact(self, scope: RuntimeScope, **values: Any) -> object:
        assert scope == SCOPE
        value_id = values["value_id"]
        exact = {k: v for k, v in values.items() if k != "expected_revision"}
        current = self.uow.values.get(value_id)
        if current is not None and current != exact:
            raise RuntimeError("exact value conflict")
        self.uow.values[value_id] = exact
        return {"value_id": value_id, "content_digest": values["expected_digest"]}


class _LedgerPort:
    def __init__(self, uow: _FakeUoW) -> None:
        self.uow = uow

    def put_object(
        self,
        scope: RuntimeScope,
        ref: ResearchObjectRef,
        *,
        expected_revision: int,
        expected_incarnation: str,
    ) -> ResearchObjectRef:
        assert scope == SCOPE and expected_incarnation == ref.incarnation
        current = self.uow.ledger.get(ref.object_id)
        if current is not None and current != ref:
            raise RuntimeError("exact ledger conflict")
        if current is None:
            assert expected_revision == 0
        self.uow.ledger[ref.object_id] = ref
        return ref

    def get_object(
        self,
        scope: RuntimeScope,
        object_id: str,
        *,
        expected_revision: int,
        expected_incarnation: str,
    ) -> ResearchObjectRef:
        assert scope == SCOPE
        ref = self.uow.ledger[object_id]
        if ref.revision != expected_revision or ref.incarnation != expected_incarnation:
            raise RuntimeError("artifact CAS miss")
        return ref


class _RuntimePort:
    def __init__(self, uow: _FakeUoW) -> None:
        self.uow = uow

    def get_delivery_admission(self, scope: RuntimeScope, intent_id: str) -> object:
        assert scope == SCOPE
        return self.uow.delivery_admissions.get(intent_id)

    def admit_delivery(self, scope: RuntimeScope, packet: object) -> object:
        assert scope == SCOPE and packet.state == "READY"
        self.uow.delivery_admissions[packet.intent.delivery_intent_id] = None
        return {"work_item_id": packet.assignment.work_item_id, "state": "READY"}


class _ApprovalPort:
    def __init__(self, approval: DeliveryApprovalSnapshot) -> None:
        self.approval = approval

    def require_current(self, scope: RuntimeScope, approval_id: str, **expected: object):
        assert scope == SCOPE
        if self.approval.approval_id != approval_id:
            raise DeliveryGateRejected("approval identity drift")
        for field_name in ("run_id", "step_id", "payload_digest", "authority_digest"):
            if getattr(self.approval, field_name) != expected[field_name]:
                raise DeliveryGateRejected(f"approval {field_name} drift")
        if self.approval.expires_at <= expected["now"]:
            raise DeliveryGateRejected("approval expired")
        return self.approval


class _AuthorityPort:
    def __init__(self, authority: DeliveryAuthoritySnapshot) -> None:
        self.authority = authority

    def current_delivery_authority(
        self, scope: RuntimeScope, capability_id: str
    ) -> DeliveryAuthoritySnapshot:
        assert scope == SCOPE and capability_id == self.authority.capability_id
        return self.authority


def _artifact() -> ResearchObjectRef:
    return ResearchObjectRef(
        object_id="artifact:p0c:1",
        object_type=RESEARCH_ARTIFACT_TYPE,
        project_key=PROJECT_KEY,
        revision=3,
        incarnation="artifact-inc-1",
        owner_binding_ref="ResearchLedger_plus_project_artifact_store",
        content_ref="project-value:artifact:p0c:1",
        content_digest="8" * 64,
        provenance_closure_digest="9" * 64,
        lifecycle_state="ADMITTED",
    )


def _delivery_parameters(template: DeliveryIntentTemplate) -> DeliveryAssignmentParameters:
    contract = build_first_specimen_bundle().operation_by_kind(
        "delivery.internal_export.v1"
    )
    return_contract = build_first_specimen_return_contract_registry().resolve_required(
        DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF
    )
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=contract.ref.contract_digest,
        interpreter_profile_digest="b" * 64,
        deployment_catalog_digest="c" * 64,
        runtime_protocol_version="1",
        project_scope_digest=SCOPE.project_scope.scope_digest,
        resource_policy_epoch=12,
        authority_requirement_digest=template.authority_digest,
    )
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="mrw.p0c.internal-export.readback",
        recovery_handler_version="1",
        interpreter_profile_digest=interpreter.interpreter_profile_digest,
        authoritative_readback_profile_ref="project-receipt-store",
    )
    return DeliveryAssignmentParameters(
        runtime_protocol_version="1",
        work_item_id="work:p0c:delivery:1",
        run_id="run:p0c:1",
        step_id="step:p0c:delivery:1",
        capability_id="delivery.first_specimen.v1",
        operation_contract_ref=contract.ref,
        return_contract_binding=ReturnContractBinding.from_contract(
            DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF, return_contract
        ),
        handler_binding=interpreter,
        recovery_binding=recovery,
        program_digest="d" * 64,
        plan_digest="e" * 64,
        deployment_catalog_digest=interpreter.deployment_catalog_digest,
        execution_epoch=0,
        incarnation="delivery-assignment-inc-1",
        queue_eligibility_digest="f" * 64,
        qualification_digest="1a" * 32,
        required_node_profile_selector="node-profile:p0c:delivery",
        resource_policy_digest="1b" * 32,
        fairness_key="p0c:delivery.first_specimen.v1",
        resource_class="cpu",
        resource_units=1,
        concurrency_key="project:p0c:internal-export",
        resource_policy_epoch=interpreter.resource_policy_epoch,
        expected_step_revision=2,
        trace_id="trace:p0c:delivery:1",
    )


def _delivery_assignment(request: DeliveryAssignmentRequest) -> RuntimeAssignment:
    params = request.parameters
    handler = params.handler_binding
    assert isinstance(handler, InterpreterBinding)
    return RuntimeAssignment(
        runtime_protocol_version=params.runtime_protocol_version,
        work_item_id=params.work_item_id,
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=request.project_key,
        run_id=params.run_id,
        step_id=params.step_id,
        step_role=CompiledStepRole.EFFECT,
        capability_id=params.capability_id,
        operation_contract_ref=params.operation_contract_ref,
        operation_contract_digest=params.operation_contract_ref.contract_digest,
        return_contract_binding=params.return_contract_binding,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{handler.binding_digest}",
        handler_binding_digest=handler.binding_digest,
        handler_binding=handler,
        program_digest=params.program_digest,
        plan_digest=params.plan_digest,
        deployment_catalog_digest=params.deployment_catalog_digest,
        execution_epoch=params.execution_epoch,
        incarnation=params.incarnation,
        input_refs=(request.artifact_content_ref, request.intent_value_ref.storage_ref),
        input_closure_digest=sha256_hex(
            [request.artifact_content_ref, request.intent_value_ref.storage_ref]
        ),
        payload_ref=request.export_payload_ref.storage_ref,
        payload_digest=request.export_payload_ref.content_digest,
        queue_eligibility_digest=params.queue_eligibility_digest,
        resource_policy_epoch=params.resource_policy_epoch,
        claim_authority_epoch=request.authority.authority_epoch,
        claim_policy_digest=request.authority.claim_policy_digest,
        expected_step_revision=params.expected_step_revision,
        deadline_at=params.deadline_at,
        trace_id=params.trace_id,
    )


def _gate(
    state: _State,
    approval: DeliveryApprovalSnapshot,
    authority: DeliveryAuthoritySnapshot,
) -> DeliveryGate:
    return DeliveryGate(
        uow_factory=lambda: _FakeUoW(state),
        value_port=lambda uow: uow.value_port,
        ledger_port=lambda uow: uow.ledger_port,
        approval_port=lambda _uow: _ApprovalPort(approval),
        authority_port=lambda _uow: _AuthorityPort(authority),
        runtime_port=lambda uow: uow.runtime_port,
        assignment_factory=_delivery_assignment,
    )


def _gate_command(*, state: _State):
    template = DeliveryIntentTemplate(
        value_id="delivery-template:p0c:1",
        delivery_intent_id="delivery-intent:p0c:1",
        audience="internal-review",
        approval_ref="approval:p0c:1",
        authority_digest="a" * 64,
        idempotency_key="delivery:p0c:1",
    )
    artifact = _artifact()
    state.ledger[artifact.object_id] = artifact
    candidate = template.candidate(
        artifact_identity_ref(
            artifact.object_id, artifact.revision, artifact.content_digest
        )
    )
    assert candidate.content_digest is not None
    approval = DeliveryApprovalSnapshot(
        approval_id=template.approval_ref,
        revision=4,
        actor_id="human:p0c",
        run_id="run:p0c:1",
        step_id="step:p0c:delivery:1",
        payload_digest=candidate.content_digest,
        authority_digest=template.authority_digest,
        expires_at=NOW + timedelta(hours=1),
    )
    authority = DeliveryAuthoritySnapshot(
        capability_id="delivery.first_specimen.v1",
        authority_epoch=11,
        authority_digest=template.authority_digest,
        claim_policy_digest="7" * 64,
        successor_claim_enabled=True,
        legacy_claim_enabled=False,
    )
    command = DeliveryGateCommand(
        scope=SCOPE,
        template=template,
        artifact=artifact,
        artifact_expected_revision=artifact.revision,
        artifact_expected_incarnation=artifact.incarnation,
        assignment=_delivery_parameters(template),
        value_incarnation="delivery-value-inc-1",
        intent_incarnation="delivery-intent-inc-1",
        now=NOW,
    )
    return command, approval, authority


def test_delivery_gate_requires_current_base_human_approval_and_authority() -> None:
    state = _State()
    command, approval, authority = _gate_command(state=state)
    packet = _gate(state, approval, authority).admit(command).packet
    assert packet.state == "READY"
    assert packet.intent_ref.object_type.type_id == "DeliveryIntent.v1"
    assert packet.assignment.claim_authority_epoch == authority.authority_epoch
    assert packet.assignment.claim_policy_digest == authority.claim_policy_digest
    assert packet.assignment.payload_ref == packet.export_payload_ref.storage_ref
    assert packet.assignment.payload_digest == packet.export_payload_ref.content_digest
    assert state.commits == 1 and state.rollbacks == 0
    assert "delivery-intent:p0c:1" in state.values
    assert state.ledger["delivery-intent:p0c:1"] == packet.intent_ref


@pytest.mark.parametrize("drift", ["approval", "authority", "artifact"])
def test_delivery_gate_rejects_exact_binding_drift_before_ready_assignment(
    drift: str,
) -> None:
    state = _State()
    command, approval, authority = _gate_command(state=state)
    if drift == "approval":
        approval = replace(approval, payload_digest="0" * 64)
    elif drift == "authority":
        authority = replace(
            authority,
            authority_epoch=authority.authority_epoch + 1,
            authority_digest="0" * 64,
        )
    else:
        artifact = state.ledger[command.artifact.object_id]
        state.ledger[artifact.object_id] = replace(
            artifact, revision=artifact.revision + 1, content_digest="0" * 64
        )
    with pytest.raises((DeliveryGateRejected, RuntimeError)):
        _gate(state, approval, authority).admit(command)
    assert state.commits == 0 and state.rollbacks == 1
    assert "delivery-intent:p0c:1" not in state.values
    assert "delivery-intent:p0c:1" not in state.ledger
