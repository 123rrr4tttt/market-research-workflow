"""P0-C unit specimens for runtime submission and the delivery gate."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.successor_runtime.capabilities import (
    build_first_specimen_bundle,
    build_first_specimen_catalog,
)
from app.successor_runtime.capabilities.catalog import build_first_specimen_registry
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
from app.successor_runtime.capabilities.first_specimen_submission import (
    CompileAssignmentRequest,
    FirstSpecimenSubmissionService,
    SubmissionCommand,
)
from app.successor_runtime.language.combinators import default_registries
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import (
    DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
    build_first_specimen_return_contract_registry,
)
from app.successor_runtime.language.program import Atom, ProgramNode, Then, ZipOrdered
from app.successor_runtime.research.artifacts import artifact_identity_ref
from app.successor_runtime.research.codec import sha256_hex
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.inquiries import (
    Inquiry,
    PlanWorkItem,
    ResearchIntent,
    ResearchPlan,
)
from app.successor_runtime.research.object_types import RESEARCH_ARTIFACT_TYPE
from app.successor_runtime.research.sources import SourceRef
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    CompilerBinding,
    HandlerBindingKind,
    InterpreterBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.ports import (
    CanonicalDocumentRead,
    ProjectScopeRef,
    RuntimeScope,
)

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
    programs: dict[str, Any] = field(default_factory=dict)
    runtime_packets: dict[str, Any] = field(default_factory=dict)
    submissions: dict[str, Any] = field(default_factory=dict)
    delivery_admissions: dict[str, Any] = field(default_factory=dict)
    commits: int = 0
    rollbacks: int = 0


class _FakeUoW:
    def __init__(self, state: _State, documents: "_DocumentPort") -> None:
        self.state = state
        self.documents = documents
        self.committed = False

    def __enter__(self):
        self.values = dict(self.state.values)
        self.ledger = dict(self.state.ledger)
        self.programs = dict(self.state.programs)
        self.runtime_packets = dict(self.state.runtime_packets)
        self.submissions = dict(self.state.submissions)
        self.delivery_admissions = dict(self.state.delivery_admissions)
        self.value_port = _ValuePort(self)
        self.ledger_port = _LedgerPort(self)
        self.program_port = _ProgramPort(self)
        self.runtime_port = _RuntimePort(self)
        return self

    def commit(self) -> None:
        self.state.values = self.values
        self.state.ledger = self.ledger
        self.state.programs = self.programs
        self.state.runtime_packets = self.runtime_packets
        self.state.submissions = self.submissions
        self.state.delivery_admissions = self.delivery_admissions
        self.state.commits += 1
        self.committed = True

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.committed:
            self.state.rollbacks += 1


class _DocumentPort:
    def __init__(self, rows: dict[int, CanonicalDocumentRead]) -> None:
        self.rows = rows
        self.reads: list[int] = []
        self.fail_on: int | None = None

    def read_document(self, scope: RuntimeScope, document_id: int):
        assert scope == SCOPE
        self.reads.append(document_id)
        if document_id == self.fail_on:
            raise RuntimeError("injected document read failure")
        return self.rows[document_id]


class _ValuePort:
    def __init__(self, uow: _FakeUoW) -> None:
        self.uow = uow

    def put_exact(self, scope: RuntimeScope, **values: Any) -> object:
        assert scope == SCOPE
        value_id = values["value_id"]
        exact = {
            key: value
            for key, value in values.items()
            if key not in {"expected_revision"}
        }
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
        assert scope == SCOPE
        assert expected_incarnation == ref.incarnation
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
        if (
            ref.revision != expected_revision
            or ref.incarnation != expected_incarnation
        ):
            raise RuntimeError("artifact CAS miss")
        return ref


class _ProgramPort:
    def __init__(self, uow: _FakeUoW) -> None:
        self.uow = uow

    def put_exact(self, scope, program, expected_digest):
        assert scope == SCOPE
        assert program.program_digest == expected_digest == program.digest()
        current = self.uow.programs.get(program.program_id)
        if current is not None and current.canonical_json() != program.canonical_json():
            raise RuntimeError("exact program conflict")
        self.uow.programs[program.program_id] = program
        return program


class _RuntimePort:
    def __init__(self, uow: _FakeUoW) -> None:
        self.uow = uow

    def get_submission(self, scope, submission_id):
        assert scope == SCOPE
        return self.uow.submissions.get(submission_id)

    def create_submitted(self, scope, packet):
        assert scope == SCOPE
        if packet.run_id in self.uow.runtime_packets:
            raise RuntimeError("duplicate run")
        self.uow.runtime_packets[packet.run_id] = packet
        return {"run_id": packet.run_id, "state": packet.state}

    def record_submission(self, scope, submitted):
        assert scope == SCOPE
        self.uow.submissions[submitted.submission_id] = submitted

    def get_delivery_admission(self, scope, delivery_intent_id):
        assert scope == SCOPE
        return self.uow.delivery_admissions.get(delivery_intent_id)

    def admit_delivery(self, scope, packet):
        assert scope == SCOPE
        assert packet.state == "READY"
        self.uow.delivery_admissions[packet.intent.delivery_intent_id] = None
        return {"work_item_id": packet.assignment.work_item_id, "state": "READY"}


class _ApprovalPort:
    def __init__(self, approval: DeliveryApprovalSnapshot) -> None:
        self.approval = approval

    def require_current(self, scope, approval_id, **expected):
        assert scope == SCOPE
        if self.approval.approval_id != approval_id:
            raise DeliveryGateRejected("approval identity drift")
        for field in ("run_id", "step_id", "payload_digest", "authority_digest"):
            if getattr(self.approval, field) != expected[field]:
                raise DeliveryGateRejected(f"approval {field} drift")
        if self.approval.expires_at <= expected["now"]:
            raise DeliveryGateRejected("approval expired")
        return self.approval


class _AuthorityPort:
    def __init__(self, authority: DeliveryAuthoritySnapshot) -> None:
        self.authority = authority

    def current_delivery_authority(self, scope, capability_id):
        assert scope == SCOPE
        assert capability_id == self.authority.capability_id
        return self.authority


def _rows() -> dict[int, CanonicalDocumentRead]:
    return {
        document_id: CanonicalDocumentRead(
            document_id=document_id,
            text_hash=character * 64,
            updated_at=NOW + timedelta(minutes=index),
            exact_bytes=f"document {document_id} exact bytes".encode(),
        )
        for index, (document_id, character) in enumerate(((101, "a"), (102, "b")))
    }


def _source(document_id: int) -> SourceRef:
    return SourceRef(
        source_ref_id=f"source:document:{document_id}",
        owner_id="legacy_document_store",
        locator=f"document://{PROJECT_KEY}/{document_id}",
        source_class="existing_project_document",
        observed_at=NOW,
        access_profile_ref="DocumentCanonicalReadPort",
    )


def _command() -> SubmissionCommand:
    bundle = build_first_specimen_bundle()
    catalog = build_first_specimen_catalog(bundle.operations)
    assert catalog.catalog_digest is not None
    compiler = CompilerBinding.from_content(
        compiler_id="mrw.functorial-successor.compiler",
        compiler_version="1.0.0",
        compiler_digest="2" * 64,
        operation_catalog_digest=catalog.catalog_digest,
        domain_contract_snapshot_digest="3" * 64,
    )
    intent = ResearchIntent(
        intent_id="intent:p0c",
        project_key=PROJECT_KEY,
        purpose="compare two captured documents",
        audience_or_use="internal research review",
        scope={"documents": [101, 102]},
        as_of=NOW,
        constraints={"network": False, "external_delivery": False},
        expected_delivery={"format": "markdown", "channel": "internal_export"},
    )
    inquiry = Inquiry(
        inquiry_id="inquiry:p0c",
        intent_ref=intent.intent_id,
        question_or_hypothesis="What claim is supported by both documents?",
        acceptance_conditions=("two exact captures",),
        stop_conditions=("claim or explicit gap",),
        uncertainty_ceiling="explicit",
    )
    plan = ResearchPlan(
        plan_id="research-plan:p0c",
        inquiry_ref=inquiry.inquiry_id,
        work_items=(
            PlanWorkItem("source:a", "capture_read_qualify"),
            PlanWorkItem("source:b", "capture_read_qualify", ("source:a",)),
        ),
        budget={"documents": 2},
        deadline=None,
        replan_policy={"mode": "open_gap"},
    )
    return SubmissionCommand(
        submission_id="submission:p0c:1",
        scope=SCOPE,
        program_id="program:p0c:1",
        run_id="run:p0c:1",
        run_incarnation="run-inc:p0c:1",
        intent=intent,
        inquiry=inquiry,
        research_plan=plan,
        source_refs=(_source(101), _source(102)),
        document_ids=(101, 102),
        delivery_template=DeliveryIntentTemplate(
            value_id="delivery-template:p0c:1",
            delivery_intent_id="delivery-intent:p0c:1",
            audience="internal-review",
            approval_ref="approval:p0c:1",
            authority_digest="a" * 64,
            idempotency_key="delivery:p0c:1",
        ),
        catalog=catalog,
        registries=default_registries(),
        compiler_binding=compiler,
        deployment_catalog_digest="4" * 64,
        submission_authority_digest="5" * 64,
        claim_authority_epoch=7,
        claim_policy_digest="6" * 64,
        resource_policy_digest="0f" * 32,
        resource_policy_epoch=8,
        queue_eligibility_digest="7" * 64,
        required_node_profile_selector="node-profile:p0c",
        fairness_key="p0c:mrw.first-specimen.compile",
        trace_id="trace:p0c:1",
        due_at=NOW,
    )


def _service(state: _State, documents: _DocumentPort):
    def factory():
        return _FakeUoW(state, documents)

    return FirstSpecimenSubmissionService(
        uow_factory=factory,
        document_port=lambda uow: uow.documents,
        value_port=lambda uow: uow.value_port,
        ledger_port=lambda uow: uow.ledger_port,
        program_port=lambda uow: uow.program_port,
        runtime_port=lambda uow: uow.runtime_port,
        compile_assignment_factory=_compile_assignment,
    )


def _compile_assignment(request: CompileAssignmentRequest) -> RuntimeAssignment:
    command = request.command
    compiler = command.compiler_binding
    assert isinstance(compiler, CompilerBinding)
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=f"{command.run_id}:compile",
        assignment_kind=AssignmentKind.COMPILE,
        project_key=PROJECT_KEY,
        run_id=command.run_id,
        capability_id="mrw.first-specimen.compile",
        handler_binding_kind=HandlerBindingKind.COMPILER,
        handler_binding_ref=f"handler-binding:sha256:{compiler.binding_digest}",
        handler_binding_digest=compiler.binding_digest,
        handler_binding=compiler,
        program_digest=request.program.program_digest,
        deployment_catalog_digest=command.deployment_catalog_digest,
        execution_epoch=0,
        incarnation=command.run_incarnation,
        input_refs=request.input_refs,
        input_closure_digest=sha256_hex(list(request.input_refs)),
        queue_eligibility_digest=command.queue_eligibility_digest,
        resource_policy_epoch=command.resource_policy_epoch,
        claim_authority_epoch=command.claim_authority_epoch,
        claim_policy_digest=command.claim_policy_digest,
        trace_id=command.trace_id,
    )


def _walk(node: ProgramNode):
    yield node
    if isinstance(node, Then):
        yield from _walk(node.first)
        yield from _walk(node.second)
    else:
        for name in ("left", "right", "source"):
            child = getattr(node, name, None)
            if child is not None:
                yield from _walk(child)
        for branch in getattr(node, "branches", ()):
            yield from _walk(branch.program)


def test_submission_captures_two_documents_and_creates_atomic_runtime_packet() -> None:
    state = _State()
    documents = _DocumentPort(_rows())
    submitted = _service(state, documents).submit(_command())

    assert documents.reads == [101, 102]
    assert state.commits == 1 and state.rollbacks == 0
    assert [item.observation.exact_bytes for item in submitted.captures] == [
        b"document 101 exact bytes",
        b"document 102 exact bytes",
    ]
    assert "submission:p0c:1:snapshot:a" in state.values
    assert "submission:p0c:1:snapshot:b" in state.values
    assert all(
        ref.object_type.type_id != "CapturedMaterialSnapshot.v1"
        for ref in state.ledger.values()
    )
    packet = state.runtime_packets["run:p0c:1"]
    assert (packet.state, packet.event_type, packet.work_item_state) == (
        "SUBMITTED",
        "ProgramAccepted",
        "READY",
    )
    assert packet.compile_assignment.program_digest == submitted.program.program_digest


def test_runtime_program_uses_only_real_values_and_ordered_delivery_merge() -> None:
    state = _State()
    command = _command()
    submitted = _service(state, _DocumentPort(_rows())).submit(command)
    nodes = tuple(_walk(submitted.program.root))
    atoms = tuple(node for node in nodes if isinstance(node, Atom))
    assert len(atoms) == 9
    for atom in atoms:
        for ref in atom.operation.input_refs + (atom.operation.payload_ref,):
            assert ref.project_key == PROJECT_KEY
            assert ref.byte_size > 0
            assert ref.content_digest != "0" * 64
            assert ref.provenance_digest != "0" * 64
            assert ref.storage_ref.startswith("project-value:")
    delivery_merges = [
        node
        for node in nodes
        if isinstance(node, ZipOrdered)
        and node.merge_ref.name
        == "mrw.first_specimen.runtime.artifact_delivery_template"
    ]
    assert len(delivery_merges) == 1
    merged = command.registries.merges.resolve_merge(
        delivery_merges[0].merge_ref
    ).callable(
        {"artifact_id": "artifact:p0c:1"},
        {"delivery_template": command.delivery_template.to_payload()},
    )
    assert merged["artifact_ref"] == "artifact:p0c:1"
    assert merged["authority_digest"] == "a" * 64
    assert merged["approval_refs"] == ["approval:p0c:1"]
    assert submitted.program.metadata
    assert b'"delivery_gate_required":true' in submitted.program.canonical_json()
    assert ("a" * 64).encode() in submitted.program.canonical_json()
    registry = build_first_specimen_registry(build_first_specimen_bundle().operations)
    compiled = compile_program(
        submitted.program,
        command.catalog,
        operation_contracts=registry,
        transform_registry=command.registries.transforms,
        merge_registry=command.registries.merges,
        discriminator_registry=command.registries.discriminators,
    )
    assert compiled.program_digest == submitted.program.program_digest
    assert len(compiled.ordered_steps) > len(atoms)


def test_submission_failure_rolls_back_every_successor_write() -> None:
    state = _State()
    documents = _DocumentPort(_rows())
    documents.fail_on = 102
    with pytest.raises(RuntimeError, match="injected document read failure"):
        _service(state, documents).submit(_command())
    assert documents.reads == [101, 102]
    assert state.values == {}
    assert state.ledger == {}
    assert state.programs == {}
    assert state.runtime_packets == {}
    assert state.commits == 0 and state.rollbacks == 1


def test_submission_idempotency_returns_committed_receipt_without_reread() -> None:
    state = _State()
    documents = _DocumentPort(_rows())
    service = _service(state, documents)
    command = _command()
    first = service.submit(command)
    second = service.submit(command)
    assert second is first
    assert documents.reads == [101, 102]
    assert state.commits == 1
    assert state.rollbacks == 1  # read-only idempotency lookup closes without commit


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
    bundle = build_first_specimen_bundle()
    contract = bundle.operation_by_kind("delivery.internal_export.v1")
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


def _gate(
    state: _State,
    documents: _DocumentPort,
    approval: DeliveryApprovalSnapshot,
    authority: DeliveryAuthoritySnapshot,
) -> DeliveryGate:
    def factory():
        return _FakeUoW(state, documents)

    return DeliveryGate(
        uow_factory=factory,
        value_port=lambda uow: uow.value_port,
        ledger_port=lambda uow: uow.ledger_port,
        approval_port=lambda _uow: _ApprovalPort(approval),
        authority_port=lambda _uow: _AuthorityPort(authority),
        runtime_port=lambda uow: uow.runtime_port,
        assignment_factory=_delivery_assignment,
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
        input_refs=(
            request.artifact_content_ref,
            request.intent_value_ref.storage_ref,
        ),
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


def _gate_command(
    *,
    state: _State,
    authority_digest: str = "a" * 64,
    approval_authority_digest: str | None = None,
    approval_payload_digest: str | None = None,
):
    template = DeliveryIntentTemplate(
        value_id="delivery-template:p0c:1",
        delivery_intent_id="delivery-intent:p0c:1",
        audience="internal-review",
        approval_ref="approval:p0c:1",
        authority_digest=authority_digest,
        idempotency_key="delivery:p0c:1",
    )
    artifact = _artifact()
    state.ledger[artifact.object_id] = artifact
    candidate = template.candidate(
        artifact_identity_ref(
            artifact.object_id,
            artifact.revision,
            artifact.content_digest,
        )
    )
    assert candidate.content_digest is not None
    approval = DeliveryApprovalSnapshot(
        approval_id=template.approval_ref,
        revision=4,
        actor_id="human:p0c",
        run_id="run:p0c:1",
        step_id="step:p0c:delivery:1",
        payload_digest=approval_payload_digest or candidate.content_digest,
        authority_digest=approval_authority_digest or authority_digest,
        expires_at=NOW + timedelta(hours=1),
    )
    authority = DeliveryAuthoritySnapshot(
        capability_id="delivery.first_specimen.v1",
        authority_epoch=11,
        authority_digest=authority_digest,
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
    receipt = _gate(state, _DocumentPort(_rows()), approval, authority).admit(command)
    packet = receipt.packet
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
        authority = DeliveryAuthoritySnapshot(
            capability_id=authority.capability_id,
            authority_epoch=authority.authority_epoch + 1,
            authority_digest="0" * 64,
            claim_policy_digest=authority.claim_policy_digest,
            successor_claim_enabled=True,
            legacy_claim_enabled=False,
        )
    else:
        artifact = state.ledger[command.artifact.object_id]
        state.ledger[artifact.object_id] = replace(
            artifact,
            revision=artifact.revision + 1,
            content_digest="0" * 64,
        )
    with pytest.raises((DeliveryGateRejected, RuntimeError)):
        _gate(state, _DocumentPort(_rows()), approval, authority).admit(command)
    assert state.commits == 0 and state.rollbacks == 1
    assert "delivery-intent:p0c:1" not in state.values
    assert "delivery-intent:p0c:1" not in state.ledger
