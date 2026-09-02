"""P0-C exact admission, internal export, and readback-only recovery."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.successor_runtime.capabilities.first_specimen import (
    build_first_specimen_bundle,
)
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.research.artifacts import (
    DELIVERY_CHANNEL,
    DELIVERY_FORMAT,
    DELIVERY_IRREVERSIBILITY_PROFILE,
    DeliveryAttempt,
    DeliveryIntent,
)
from app.successor_runtime.research.evidence import EvidenceQualification, Validity
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import (
    INQUIRY_TYPE,
    MATERIAL_REF_TYPE,
)
from app.successor_runtime.runtime.admission import CommitIntent, VerificationBinding
from app.successor_runtime.runtime.admission_coordinator import (
    AdmissionBindingError,
    AdmissionCoordinator,
    AdmissionProgress,
    AdmissionRegistration,
    AdmissionRegistryError,
    CanonicalCommit,
    CanonicalCommitReadback,
    CanonicalReadbackKind,
    ExactAdmissionRegistry,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledAdmissionBinding,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    EffectAttemptObservation,
    EffectReconciler,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.blob.internal_export import (
    InternalExportBindingConflict,
    InternalExportExecutionContext,
    InternalExportInterpreter,
    InternalExportRequest,
    NonStartUnprovable,
)
from app.successor_runtime.substrate.blob.store import ProjectBlobStore
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.owner_bindings import (
    OwnerBindingRecord,
    OwnerBindingRepository,
)
from app.successor_runtime.substrate.postgres.research_admission import (
    AtomicResearchAdmissionCommand,
    DeliveryIntentAdmission,
    EvidenceRelationCandidate,
    ResearchAdmissionHandler,
    ResearchAdmissionMode,
)
from app.successor_runtime.substrate.postgres.research_ledger import (
    ResearchLedgerRepository,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest

pytestmark = pytest.mark.unit


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type: object, _compiler: object, **_kw: object) -> str:
    return "JSON"


def _digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _scope() -> RuntimeScope:
    scope_digest = compute_scope_digest("alpha", "project_alpha", 3, "scope-inc-3")
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key="alpha",
            resolved_schema="project_alpha",
            project_registry_revision=3,
            incarnation="scope-inc-3",
            scope_digest=scope_digest,
        ),
        actor_id="runtime-node-actor",
    )


def _assignment(
    operation_ref: OperationContractRef,
    scope: RuntimeScope,
) -> RuntimeAssignment:
    deployment_digest = _digest("deployment")
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=operation_ref.contract_digest,
        interpreter_profile_digest=_digest("interpreter-profile"),
        deployment_catalog_digest=deployment_digest,
        runtime_protocol_version="1",
        project_scope_digest=scope.project_scope.scope_digest,
        resource_policy_epoch=3,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    return_contract = ReturnContractBinding.from_contract(
        "mrw.return.fixture-admission.v1",
        ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            admission_required=True,
            wait_modes=("WAIT",),
        ),
    )
    compiled = CompiledAdmissionBinding.from_content(
        plan_digest=_digest("plan"),
        effect_step_id="effect-step",
        admission_step_id="admission-step",
        operation_contract_digest=operation_ref.contract_digest,
        return_contract_ref=return_contract.return_contract_ref,
        return_contract_digest=return_contract.binding_digest,
        source_map_digest=_digest("source-map"),
        control_digest=_digest("control"),
    )
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work-admission",
        assignment_kind=AssignmentKind.VERIFY_ADMIT,
        project_key=scope.project_scope.project_key,
        run_id="run-1",
        step_id="admission-step",
        step_role=CompiledStepRole.ADMISSION,
        capability_id="capability-1",
        operation_contract_ref=operation_ref,
        operation_contract_digest=operation_ref.contract_digest,
        return_contract_binding=return_contract,
        compiled_admission_binding=compiled,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=(
            f"handler-binding:sha256:{interpreter.binding_digest}"
        ),
        handler_binding_digest=interpreter.binding_digest,
        handler_binding=interpreter,
        program_digest=_digest("program"),
        plan_digest=_digest("plan"),
        deployment_catalog_digest=deployment_digest,
        execution_epoch=1,
        incarnation="assignment-inc-1",
        input_refs=("value:input",),
        input_closure_digest=_digest("input-closure"),
        payload_ref="value:candidate",
        payload_digest=_digest("candidate"),
        queue_eligibility_digest=_digest("queue-eligibility"),
        resource_policy_epoch=3,
        claim_authority_epoch=4,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        trace_id="trace-1",
    )


def _verification_and_intent(
    *,
    assignment: RuntimeAssignment,
    scope: RuntimeScope,
    canonical_owner: str = "ResearchLedger",
    object_id: str = "object-1",
    content_digest: str | None = None,
    base_revision: int = 0,
    incarnation: str = "inc-1",
) -> tuple[VerificationBinding, CommitIntent, tuple[bytes, ...]]:
    content_digest = content_digest or _digest("candidate-content")
    events = (b"canonical-commit", b"runtime-event")
    binding = VerificationBinding.from_content(
        program_digest=assignment.program_digest,
        plan_digest=assignment.plan_digest,
        step_id=assignment.step_id,
        attempt_id="attempt-admission-1",
        input_closure_digest=assignment.input_closure_digest,
        output_content_digest=content_digest,
        ordered_event_payloads=events,
        schema_digest=_digest("schema"),
        compiler_identity="compiler@1",
        interpreter_identity="interpreter@1",
        verifier_identity="verifier@1",
        actor_id=scope.actor_id,
        project_key=scope.project_scope.project_key,
        authority_digest=_digest("authority"),
        project_registry_revision=scope.project_scope.project_registry_revision,
        project_scope_digest=scope.project_scope.scope_digest,
        resolved_schema=scope.project_scope.resolved_schema,
        canonical_owner=canonical_owner,
        canonical_object_id=object_id,
        canonical_base_revision=base_revision,
        canonical_incarnation=incarnation,
        evidence_digest=_digest("evidence"),
        receipt_digest=_digest("verification-receipt"),
        provenance_digest=_digest("provenance"),
        qualifier="STANDARD",
    )
    intent = CommitIntent(
        commit_intent_id="commit-intent-1",
        canonical_owner=canonical_owner,
        project_key=scope.project_scope.project_key,
        object_id=object_id,
        project_registry_revision=scope.project_scope.project_registry_revision,
        project_scope_digest=scope.project_scope.scope_digest,
        expected_base_revision=base_revision,
        expected_incarnation=incarnation,
        content_digest=content_digest,
        ordered_event_closure_digest=binding.ordered_event_payload_closure_digest,
        verification_binding_digest=binding.binding_digest,
        authority_digest=binding.authority_digest,
        idempotency_key="admission-idempotency-1",
    )
    return binding, intent, events


class _FakeCommitIntentStore:
    def __init__(self) -> None:
        self.row: dict[str, Any] | None = None
        self.binding: object | None = None

    def prepare(self, binding: object) -> dict[str, Any]:
        if self.row is None:
            self.binding = binding
            self.row = {
                "commit_intent_id": getattr(binding, "commit_intent_id", "commit-intent-1"),
                "state": "PREPARED",
                "revision": 0,
                "canonical_commit_ref": None,
                "receipt_digest": None,
            }
        elif binding != self.binding:
            raise AssertionError("exact commit binding drift")
        return dict(self.row)

    def load(self, commit_intent_id: str) -> dict[str, Any]:
        assert self.row is not None
        assert self.row["commit_intent_id"] == commit_intent_id
        return dict(self.row)

    def mark_committed(
        self,
        commit_intent_id: str,
        *,
        expected_revision: int,
        canonical_commit_ref: str,
        receipt_digest: str,
    ) -> dict[str, Any]:
        assert self.row is not None
        assert self.row["revision"] == expected_revision
        self.row.update(
            state="COMMITTED",
            revision=expected_revision + 1,
            canonical_commit_ref=canonical_commit_ref,
            receipt_digest=receipt_digest,
        )
        return dict(self.row)

    def mark_outcome_unknown(
        self, commit_intent_id: str, *, expected_revision: int
    ) -> dict[str, Any]:
        assert self.row is not None
        assert self.row["revision"] == expected_revision
        self.row.update(state="OUTCOME_UNKNOWN", revision=expected_revision + 1)
        return dict(self.row)


class _TwoPhaseHandler:
    canonical_owner = "ResearchLedger"

    def __init__(self) -> None:
        self.commit_count = 0
        self.commit_result: CanonicalCommit | None = None

    def commit(
        self,
        scope: RuntimeScope,
        intent: CommitIntent,
        _candidate: object,
        _binding: VerificationBinding,
    ) -> CanonicalCommit:
        self.commit_count += 1
        body = {
            "schema_version": "mrw.runtime.canonical_commit.v1",
            "commit_intent_id": intent.commit_intent_id,
            "canonical_owner": intent.canonical_owner,
            "project_key": intent.project_key,
            "object_id": intent.object_id,
            "canonical_ref": f"canonical:object:{intent.object_id}:1",
            "canonical_revision": intent.expected_base_revision + 1,
            "canonical_incarnation": intent.expected_incarnation,
            "content_digest": intent.content_digest,
        }
        self.commit_result = CanonicalCommit(
            **body,
            receipt_digest=canonical_digest(body),
        )
        return self.commit_result

    def readback(
        self,
        _scope: RuntimeScope,
        intent: CommitIntent,
        _candidate: object,
    ) -> CanonicalCommitReadback:
        if self.commit_result is None:
            return CanonicalCommitReadback.absent(
                observation={"intent": intent.commit_intent_id, "state": "ABSENT"}
            )
        return CanonicalCommitReadback.found(self.commit_result)


@dataclass(frozen=True)
class _CommitBinding:
    commit_intent_id: str
    assignment_digest: str


def _commit_binding_factory(
    *, assignment: RuntimeAssignment, intent: CommitIntent
) -> _CommitBinding:
    return _CommitBinding(intent.commit_intent_id, assignment.assignment_digest)


def test_exact_operation_digest_registry_never_dispatches_by_candidate_python_type() -> None:
    scope = _scope()
    operation = build_first_specimen_bundle().operation_by_kind("evidence.qualify.v1")
    handler = _TwoPhaseHandler()
    registry = ExactAdmissionRegistry((AdmissionRegistration(operation.ref, handler),))
    assert registry.resolve_required(operation.ref).handler is handler

    substituted = OperationContractRef(
        kind=operation.ref.kind,
        contract_version=operation.ref.contract_version,
        contract_digest=_digest("substituted-contract"),
    )
    with pytest.raises(AdmissionRegistryError, match="exact operation contract digest"):
        registry.resolve_required(substituted)

    # The same arbitrary candidate object cannot change that resolution.
    assignment = _assignment(operation.ref, scope)
    binding, intent, events = _verification_and_intent(
        assignment=assignment, scope=scope
    )
    coordinator = AdmissionCoordinator(
        registry=registry,
        commit_intents=_FakeCommitIntentStore(),
        commit_binding_factory=_commit_binding_factory,
    )
    prepared = coordinator.prepare(
        scope=scope,
        assignment=assignment,
        intent=intent,
        candidate={"python_type": "irrelevant"},
        binding=binding,
        current_authority_digest=binding.authority_digest,
        current_base_revision=0,
        current_incarnation="inc-1",
        ordered_event_payloads=events,
    )
    assert prepared.registration.operation_contract_ref == operation.ref


@pytest.mark.parametrize(
    ("drift", "message"),
    (
        ("authority", "authority drift"),
        ("base", "base revision drift"),
        ("incarnation", "incarnation drift"),
    ),
)
def test_admission_fails_closed_on_authority_base_and_incarnation_drift(
    drift: str, message: str
) -> None:
    scope = _scope()
    operation = build_first_specimen_bundle().operation_by_kind("evidence.qualify.v1")
    assignment = _assignment(operation.ref, scope)
    binding, intent, events = _verification_and_intent(
        assignment=assignment, scope=scope
    )
    coordinator = AdmissionCoordinator(
        registry=ExactAdmissionRegistry(
            (AdmissionRegistration(operation.ref, _TwoPhaseHandler()),)
        ),
        commit_intents=_FakeCommitIntentStore(),
        commit_binding_factory=_commit_binding_factory,
    )
    values = {
        "current_authority_digest": binding.authority_digest,
        "current_base_revision": 0,
        "current_incarnation": "inc-1",
    }
    if drift == "authority":
        values["current_authority_digest"] = _digest("revoked-authority")
    elif drift == "base":
        values["current_base_revision"] = 1
    else:
        values["current_incarnation"] = "inc-recreated"
    with pytest.raises(AdmissionBindingError, match=message):
        coordinator.prepare(
            scope=scope,
            assignment=assignment,
            intent=intent,
            candidate=object(),
            binding=binding,
            ordered_event_payloads=events,
            **values,
        )


def test_cw09_two_phase_recovery_reads_back_without_duplicate_canonical_commit() -> None:
    scope = _scope()
    operation = build_first_specimen_bundle().operation_by_kind("evidence.qualify.v1")
    assignment = _assignment(operation.ref, scope)
    binding, intent, events = _verification_and_intent(
        assignment=assignment, scope=scope
    )
    handler = _TwoPhaseHandler()
    store = _FakeCommitIntentStore()
    coordinator = AdmissionCoordinator(
        registry=ExactAdmissionRegistry(
            (AdmissionRegistration(operation.ref, handler),)
        ),
        commit_intents=store,
        commit_binding_factory=_commit_binding_factory,
    )
    prepared = coordinator.prepare(
        scope=scope,
        assignment=assignment,
        intent=intent,
        candidate=object(),
        binding=binding,
        current_authority_digest=binding.authority_digest,
        current_base_revision=0,
        current_incarnation="inc-1",
        ordered_event_payloads=events,
    )
    canonical = coordinator.commit_prepared(prepared)
    assert canonical.progress is AdmissionProgress.CANONICAL_COMMITTED
    assert handler.commit_count == 1
    assert store.row is not None and store.row["state"] == "PREPARED"

    # Crash before runtime finalize/event. Recovery is readback-only.
    recovered = coordinator.recover(prepared)
    assert recovered.progress is AdmissionProgress.FINALIZED
    assert handler.commit_count == 1
    assert store.row is not None and store.row["state"] == "COMMITTED"


class _ApprovalReader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def require_current(self, approval_id: str, **_kwargs: object) -> object:
        self.calls.append(approval_id)
        return {"decision": "APPROVED"}


def _internal_export_request(
    scope: RuntimeScope,
    *,
    artifact: bytes = b"# exact report\n",
    idempotency_key: str = "delivery-idem-1",
) -> InternalExportRequest:
    operation = build_first_specimen_bundle().operation_by_kind(
        "delivery.internal_export.v1"
    )
    artifact_digest = _digest(artifact)
    intent = DeliveryIntent(
        delivery_intent_id="delivery-intent-1",
        artifact_ref="artifact-1:revision-1",
        audience="internal-research-team",
        channel=DELIVERY_CHANNEL,
        format=DELIVERY_FORMAT,
        approval_refs=("approval-human-1",),
        authority_digest=_digest("delivery-authority"),
        idempotency_key=idempotency_key,
        irreversibility_profile=DELIVERY_IRREVERSIBILITY_PROFILE,
    )
    return InternalExportRequest(
        project_key=scope.project_scope.project_key,
        project_scope_digest=scope.project_scope.scope_digest,
        run_id="run-1",
        step_id="delivery-step",
        attempt_id=_digest("delivery-attempt-1"),
        assignment_digest=_digest("delivery-assignment"),
        operation_contract_ref=operation.ref,
        handler_binding_digest=_digest("delivery-handler"),
        delivery_intent=intent,
        artifact_bytes=artifact,
        artifact_digest=artifact_digest,
        payload_digest=_digest("delivery-payload"),
    )


def test_internal_export_is_content_addressed_internal_only_and_idempotent(
    tmp_path: Path,
) -> None:
    scope = _scope()
    request = _internal_export_request(scope)
    approvals = _ApprovalReader()
    interpreter = InternalExportInterpreter(
        operation_contract_ref=request.operation_contract_ref,
        blob_store=ProjectBlobStore(tmp_path, fsync=False),
    )
    context = InternalExportExecutionContext(
        scope=scope,
        approvals=approvals,
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )
    first = interpreter.execute(request, context)
    second = interpreter.execute(request, context)

    assert first.receipt == second.receipt
    assert first.readback.disposition is EffectDisposition.SUCCEEDED
    assert first.receipt.provider_locator.startswith("internal-export://")
    assert not first.receipt.provider_locator.startswith(("http://", "https://"))
    assert approvals.calls == ["approval-human-1", "approval-human-1"]
    blob_files = tuple(
        path
        for path in tmp_path.glob("projects/*/sha256/*/*")
        if path.is_file()
    )
    assert len(blob_files) == 1
    assert blob_files[0].read_bytes() == request.artifact_bytes

    mutated = _internal_export_request(
        scope,
        artifact=b"# mutated report\n",
        idempotency_key=request.delivery_intent.idempotency_key,
    )
    with pytest.raises(InternalExportBindingConflict, match="idempotency marker"):
        interpreter.execute(mutated, context)


def test_internal_export_readback_and_nonstart_proof_cover_effect_crash_window(
    tmp_path: Path,
) -> None:
    scope = _scope()
    request = _internal_export_request(scope)
    interpreter = InternalExportInterpreter(
        operation_contract_ref=request.operation_contract_ref,
        blob_store=ProjectBlobStore(tmp_path, fsync=False),
    )
    proof = interpreter.prove_not_started(request)
    assert proof.attempt_id == request.attempt_id

    # Simulate effect after PREPARED and before SUCCEEDED marker/receipt event.
    marker = interpreter._ensure_prepared(  # noqa: SLF001 - crash fixture
        request, datetime(2026, 8, 31, tzinfo=UTC)
    )
    assert marker["state"] == "PREPARED"
    interpreter.blob_store.store(
        request.project_scope_digest, request.artifact_bytes
    )
    readback = interpreter.readback(request)
    assert readback.disposition is EffectDisposition.SUCCEEDED
    assert isinstance(interpreter.prove_not_started(request), NonStartUnprovable)


def _reconcile_assignment(
    operation_ref: OperationContractRef,
    attempt_id: str,
) -> RuntimeAssignment:
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="readback-only-reconciler",
        recovery_handler_version="1",
        interpreter_profile_digest=_digest("interpreter-profile"),
        authoritative_readback_profile_ref="internal-export-idempotency",
    )
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="reconcile-work",
        assignment_kind=AssignmentKind.RECONCILE,
        project_key="alpha",
        run_id="run-1",
        step_id="delivery-step",
        capability_id="delivery.first-specimen.v1",
        operation_contract_ref=operation_ref,
        operation_contract_digest=operation_ref.contract_digest,
        handler_binding_kind=HandlerBindingKind.RECOVERY,
        handler_binding_ref=f"handler-binding:sha256:{recovery.binding_digest}",
        handler_binding_digest=recovery.binding_digest,
        handler_binding=recovery,
        program_digest=_digest("program"),
        plan_digest=_digest("plan"),
        deployment_catalog_digest=_digest("deployment"),
        execution_epoch=1,
        incarnation="reconcile-inc-1",
        input_closure_digest=_digest("input"),
        queue_eligibility_digest=_digest("queue"),
        resource_policy_epoch=3,
        claim_authority_epoch=4,
        claim_policy_digest=_digest("claim"),
        expected_step_revision=4,
        reconciliation_attempt_id=attempt_id,
        trace_id="trace-reconcile",
    )


class _UnknownReadbackInterpreter:
    interpreter_id = "successor-native.internal-export"
    interpreter_version = "1.0.0"
    provider_id = "mrw.internal-content-addressed-export"
    provider_version = "1.0.0"

    def __init__(self) -> None:
        self.readback_count = 0
        self.execute_count = 0

    def readback(
        self, attempt: EffectAttemptObservation
    ) -> AuthoritativeEffectReadback:
        self.readback_count += 1
        return AuthoritativeEffectReadback(
            attempt_id=attempt.attempt_id,
            disposition=EffectDisposition.OUTCOME_UNKNOWN,
            observation_digest=_digest("unknown-readback"),
            reason="PROVIDER_READBACK_UNAVAILABLE",
        )

    def prove_not_started(self, _attempt: EffectAttemptObservation) -> object:
        return object()

    def execute(self, *_args: object) -> object:  # must never be called
        self.execute_count += 1
        raise AssertionError("reconciler redispatched the effect")


def test_outcome_unknown_without_nonstart_proof_remains_waiting_and_never_reexecutes() -> None:
    operation = build_first_specimen_bundle().operation_by_kind(
        "delivery.internal_export.v1"
    )
    attempt_id = _digest("delivery-attempt-1")
    assignment = _reconcile_assignment(operation.ref, attempt_id)
    attempt = EffectAttemptObservation(
        attempt_id=attempt_id,
        assignment_digest=_digest("original-assignment"),
        handler_binding_digest=_digest("delivery-handler"),
        interpreter_profile_digest=_digest("interpreter-profile"),
        interpreter_id="successor-native.internal-export",
        interpreter_version="1.0.0",
        provider_id="mrw.internal-content-addressed-export",
        provider_version="1.0.0",
        external_idempotency_key="delivery-idem-1",
        authoritative_readback_locator=(
            f"internal-export-index:{_digest('scope')}:{_digest('idem')}"
        ),
    )
    interpreter = _UnknownReadbackInterpreter()
    reconciler = EffectReconciler()
    result = reconciler.reconcile(
        assignment=assignment,
        attempt=attempt,
        interpreter=interpreter,
    )
    assert result.state is ReconciliationState.WAITING
    assert result.disposition is EffectDisposition.OUTCOME_UNKNOWN
    proof_result = reconciler.prove_non_start(
        assignment=assignment,
        attempt=attempt,
        interpreter=interpreter,
    )
    assert proof_result.state is ReconciliationState.WAITING
    assert interpreter.readback_count == 1
    assert interpreter.execute_count == 0


@pytest.fixture
def admission_db():
    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    connection.connection.create_function(
        "num_nonnulls", -1, lambda *values: sum(value is not None for value in values)
    )
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS project_alpha")
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS public")
    metadata = sa.MetaData()
    tables = project_tables(metadata, "project_alpha")
    metadata.create_all(connection)
    connection.exec_driver_sql(
        "CREATE TABLE public.runtime_event_marker "
        "(event_id TEXT PRIMARY KEY, relation_id TEXT NOT NULL)"
    )
    connection.commit()
    try:
        yield connection, tables, _scope()
    finally:
        if connection.in_transaction():
            connection.rollback()
        connection.close()
        engine.dispose()


def _owner(object_type: str, owner_mode: str, owner_id: str) -> OwnerBindingRecord:
    return OwnerBindingRecord(
        object_type=object_type,
        owner_mode=owner_mode,
        owner_id=owner_id,
        owner_epoch=1,
        readback_profile_ref="ledger-readback-v1",
        base_incarnation="project-inc-1",
        rollback_evidence_ref="rollback:none",
        effective_at=datetime(2026, 8, 31, tzinfo=UTC),
        approval_ref="approval-1",
    )


def _ref(
    object_id: str,
    object_type: Any,
    owner: str,
    scope: RuntimeScope,
) -> ResearchObjectRef:
    return ResearchObjectRef(
        object_id=object_id,
        object_type=object_type,
        project_key=scope.project_scope.project_key,
        owner_binding_ref=owner,
        content_ref=f"value://{object_id}",
        content_digest=_digest(f"{object_id}:content"),
        provenance_closure_digest=_digest(f"{object_id}:provenance"),
    )


class _JournalMarker:
    def __init__(self, relation_id: str, *, fail: bool) -> None:
        self.relation_id = relation_id
        self.fail = fail

    def execute(self, connection: sa.Connection) -> object:
        connection.exec_driver_sql(
            "INSERT INTO public.runtime_event_marker (event_id, relation_id) "
            "VALUES (?, ?)",
            (f"event:{self.relation_id}", self.relation_id),
        )
        if self.fail:
            raise RuntimeError("injected journal failure")
        return {"event_id": f"event:{self.relation_id}"}


def test_cw07_relation_and_runtime_event_are_one_atomic_command_and_relation_only(
    admission_db,
) -> None:
    connection, tables, scope = admission_db
    owners = OwnerBindingRepository(connection, tables)
    owners.put_exact(
        scope,
        _owner(INQUIRY_TYPE.type_id, "CANONICAL_OWNED", "ResearchLedger"),
        expected_owner_epoch=0,
        expected_base_incarnation="project-inc-1",
    )
    owners.put_exact(
        scope,
        _owner(
            MATERIAL_REF_TYPE.type_id,
            "IMMUTABLE_EXTERNAL_REF",
            "CapturedMaterialSnapshot",
        ),
        expected_owner_epoch=0,
        expected_base_incarnation="project-inc-1",
    )
    ledger = ResearchLedgerRepository(connection, tables)
    material = _ref(
        "material-1", MATERIAL_REF_TYPE, "CapturedMaterialSnapshot", scope
    )
    inquiry = _ref("inquiry-1", INQUIRY_TYPE, "ResearchLedger", scope)
    ledger.put_object(scope, material, expected_revision=0, expected_incarnation="inc-1")
    ledger.put_object(scope, inquiry, expected_revision=0, expected_incarnation="inc-1")
    connection.commit()

    qualification = EvidenceQualification(
        qualification_id="qualification-1",
        project_key=scope.project_scope.project_key,
        material_ref=material.object_id,
        inquiry_ref=inquiry.object_id,
        claim_ref=None,
        direction="SUPPORTS",
        scope_statement_ref="scope:first-specimen",
        uncertainty_profile_ref="uncertainty:bounded",
        verifier_profile_ref="verifier:first-specimen",
        provenance_closure_digest=_digest("qualification-provenance"),
        validity=Validity(None, None),
    )
    operation = build_first_specimen_bundle().operation_by_kind("evidence.qualify.v1")
    assignment = _assignment(operation.ref, scope)
    binding, intent, _events = _verification_and_intent(
        assignment=assignment,
        scope=scope,
        object_id=qualification.qualification_id,
        content_digest=qualification.qualification_digest,
    )
    handler = ResearchAdmissionHandler(
        connection=connection,
        tables=tables,
        operation_contract_ref=operation.ref,
        mode=ResearchAdmissionMode.EVIDENCE_RELATION,
    )
    candidate = EvidenceRelationCandidate(
        qualification=qualification,
        source_ref=material,
        target_ref=inquiry,
        expected_revision=0,
        expected_incarnation="inc-1",
    )

    transaction = connection.begin()
    with pytest.raises(RuntimeError, match="injected journal failure"):
        AtomicResearchAdmissionCommand(
            registration=AdmissionRegistration(operation.ref, handler),
            assignment=assignment,
            scope=scope,
            intent=intent,
            candidate=candidate,
            binding=binding,
            journal_command=_JournalMarker(qualification.qualification_id, fail=True),
        ).execute(connection)
    transaction.rollback()
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(tables.research_relations)
    ) == 0
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(tables.research_objects)
    ) == 2
    assert connection.exec_driver_sql(
        "SELECT COUNT(*) FROM public.runtime_event_marker"
    ).scalar_one() == 0
    connection.rollback()

    with connection.begin():
        AtomicResearchAdmissionCommand(
            registration=AdmissionRegistration(operation.ref, handler),
            assignment=assignment,
            scope=scope,
            intent=intent,
            candidate=candidate,
            binding=binding,
            journal_command=_JournalMarker(qualification.qualification_id, fail=False),
        ).execute(connection)
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(tables.research_relations)
    ) == 1
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(tables.research_objects)
    ) == 2
    assert connection.exec_driver_sql(
        "SELECT COUNT(*) FROM public.runtime_event_marker"
    ).scalar_one() == 1


def test_delivery_attempt_is_not_admitted_as_delivery_intent_owner() -> None:
    admission = DeliveryIntentAdmission(ledger=object())  # type: ignore[arg-type]
    attempt = DeliveryAttempt(
        attempt_id="attempt-1",
        delivery_intent_ref="intent-1",
        assignment_digest=_digest("assignment"),
        handler_binding_digest=_digest("handler"),
        effect_disposition="IN_FLIGHT",
    )
    with pytest.raises(AdmissionBindingError, match="Execution Journal-owned"):
        admission.reject_runtime_attempt(attempt)
