from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Self

import pytest

import app.successor_runtime.substrate.postgres.first_specimen_terminal as terminal_module
from app.successor_runtime.capabilities.first_specimen import (
    build_first_specimen_bundle,
)
from app.successor_runtime.language.object_contracts import (
    build_first_specimen_return_contract_registry,
)
from app.successor_runtime.research.artifacts import (
    DeliveryReceiptRef,
    ResearchArtifact,
)
from app.successor_runtime.research.claims import Claim, Gap
from app.successor_runtime.research.codec import canonical_bytes, dataclass_to_json
from app.successor_runtime.research.evidence import EvidenceQualification, Validity
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import (
    CLAIM_TYPE,
    DELIVERY_RECEIPT_REF_TYPE,
    EVIDENCE_QUALIFICATION_TYPE,
    GAP_TYPE,
    INQUIRY_TYPE,
    MATERIAL_REF_TYPE,
    RESEARCH_ARTIFACT_TYPE,
)
from app.successor_runtime.runtime.admission import CommitIntent, VerificationBinding
from app.successor_runtime.runtime.admission_coordinator import (
    AdmissionProgress,
    AdmissionResult,
    CanonicalCommit,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledAdmissionBinding,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    NodeIdentity,
    RuntimeExecutionContext,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.qualification import (
    AuthoritySourceBinding,
    StepAuthorizationBinding,
)
from app.successor_runtime.substrate.postgres.first_specimen_terminal import (
    ExactAdmissionPacket,
    ExactFirstSpecimenStage,
    FirstSpecimenCandidateDecoder,
    FirstSpecimenTerminalError,
    PostgresFirstSpecimenTerminalHook,
    PostgresVerifyAdmitHandler,
)
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    ClaimedLifecycle,
    EffectTerminalKind,
    TerminalOutcome,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def _digest(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode()
    return hashlib.sha256(raw).hexdigest()


def _scope() -> RuntimeScope:
    return RuntimeScope(
        ProjectScopeRef(
            project_key="alpha",
            resolved_schema="project_alpha",
            project_registry_revision=3,
            incarnation="scope-inc-3",
            scope_digest=_digest("scope"),
        ),
        actor_id="node-a",
    )


def _assignment(kind: str = "claim.form_or_open_gap.v1") -> RuntimeAssignment:
    operation = build_first_specimen_bundle().operation_by_kind(kind)
    deployment = _digest("deployment")
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=operation.ref.contract_digest,
        interpreter_profile_digest=_digest("interpreter" + kind),
        deployment_catalog_digest=deployment,
        runtime_protocol_version="1",
        project_scope_digest=_scope().project_scope.scope_digest,
        resource_policy_epoch=2,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    returns = build_first_specimen_return_contract_registry().resolve_required(
        operation.return_contract_ref
    )
    return_binding = ReturnContractBinding.from_contract(
        operation.return_contract_ref, returns
    )
    plan_digest = _digest("plan")
    compiled = CompiledAdmissionBinding.from_content(
        plan_digest=plan_digest,
        effect_step_id="effect-step",
        admission_step_id="admission-step",
        operation_contract_digest=operation.ref.contract_digest,
        return_contract_ref=return_binding.return_contract_ref,
        return_contract_digest=return_binding.binding_digest,
        source_map_digest=_digest("source-map"),
        control_digest=_digest("control"),
    )
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work-admission",
        assignment_kind=AssignmentKind.VERIFY_ADMIT,
        project_key="alpha",
        run_id="run-1",
        step_id=compiled.admission_step_id,
        step_role=CompiledStepRole.ADMISSION,
        capability_id="first-specimen",
        operation_contract_ref=operation.ref,
        operation_contract_digest=operation.ref.contract_digest,
        return_contract_binding=return_binding,
        compiled_admission_binding=compiled,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{interpreter.binding_digest}",
        handler_binding_digest=interpreter.binding_digest,
        handler_binding=interpreter,
        program_digest=_digest("program"),
        plan_digest=plan_digest,
        deployment_catalog_digest=deployment,
        execution_epoch=1,
        incarnation="run-inc-1",
        input_refs=("project-value:candidate",),
        input_closure_digest=_digest("input-closure"),
        payload_ref="project-value:operation-payload",
        payload_digest=_digest("operation-payload"),
        queue_eligibility_digest=_digest("eligibility"),
        resource_policy_epoch=2,
        claim_authority_epoch=4,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        trace_id="trace-1",
    )


def _authorization(assignment: RuntimeAssignment) -> StepAuthorizationBinding:
    source = AuthoritySourceBinding(
        source_kind="PROJECT_SCOPE",
        source_ref="project-scope:alpha:3",
        source_digest=_digest("authority-source"),
        source_epoch=3,
    )
    return StepAuthorizationBinding.from_content(
        run_id=assignment.run_id,
        step_id=assignment.step_id,
        operation_kind=assignment.operation_contract_ref.kind,
        operation_contract_digest=assignment.operation_contract_digest,
        capability_id=assignment.capability_id,
        claim_owner="successor",
        claim_authority_epoch=assignment.claim_authority_epoch,
        claim_policy_digest=assignment.claim_policy_digest,
        payload_digest=assignment.payload_digest,
        actor_id="node-a",
        project_key=assignment.project_key,
        project_registry_revision=3,
        project_scope_digest=_scope().project_scope.scope_digest,
        interpreter_binding_digest=assignment.handler_binding_digest,
        deployment_catalog_digest=assignment.deployment_catalog_digest,
        authority_source_bindings=(source,),
        grants_digest=_digest("grants"),
        approval_refs=(),
        resource_ceiling_digest=_digest("ceiling"),
        resource_policy_epoch=assignment.resource_policy_epoch,
        queue_eligibility_digest=assignment.queue_eligibility_digest,
        grant_epoch=4,
        expires_at=NOW + timedelta(hours=1),
        canonical_base_revision=0,
        canonical_incarnation="candidate-inc-1",
    )


def _claim(
    assignment: RuntimeAssignment, authorization: StepAuthorizationBinding
) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest=authorization.binding_digest,
        lease_token="lease-1",
        lease_expires_at=NOW + timedelta(minutes=10),
        node_id="node-a",
        node_profile_digest=_digest("node-profile"),
        authority_digest=authorization.binding_digest,
        interpreter_profile_digest=assignment.handler_binding.interpreter_profile_digest,
        execution_reservation_ref="reservation-1",
        execution_reservation_digest=_digest("reservation"),
    )


def _stage(
    assignment: RuntimeAssignment,
    exact: bytes,
    object_type: str,
) -> ExactFirstSpecimenStage:
    digest = _digest(exact)
    provenance = {"candidate": object_type, "digest": digest}
    return ExactFirstSpecimenStage(
        scope=_scope(),
        tables=SimpleNamespace(),
        plan=SimpleNamespace(compiler_id="compiler", compiler_version="1"),
        assignment=assignment,
        staged_row={
            "artifact_id": "stage-1",
            "run_id": assignment.run_id,
            "step_id": "effect-step",
            "attempt_id": _digest("effect-attempt"),
            "value_id": "runtime-candidate",
            "receipt_ref": None,
            "qualifier_ref": "qualifier:standard",
            "loss_profile_ref": None,
            "state": "VERIFIED",
            "revision": 1,
        },
        runtime_value_row={
            "value_id": "runtime-candidate",
            "object_type": object_type,
            "codec_id": "mrw.canonical-json.v1",
            "content_digest": digest,
            "byte_size": len(exact),
            "project_value_ref": "project-value:candidate",
            "storage_digest": _digest("storage"),
            "state": "AVAILABLE",
            "revision": 0,
        },
        project_value_row={
            "provenance_digest": canonical_digest(provenance),
            "provenance_json": provenance,
        },
        effect_step_row={
            "run_id": assignment.run_id,
            "step_id": "effect-step",
            "operation_kind": assignment.operation_contract_ref.kind,
            "state": "SUCCEEDED",
            "revision": 3,
            "execution_epoch": 1,
            "output_digest": digest,
        },
        effect_attempt_row={
            "attempt_id": _digest("effect-attempt"),
            "run_id": assignment.run_id,
            "step_id": "effect-step",
            "assignment_digest": _digest("effect-assignment"),
            "handler_binding_digest": _digest("effect-handler"),
            "authorization_digest": _digest("effect-authorization"),
            "disposition": "SUCCEEDED",
            "receipt_ref": None,
            "receipt_digest": None,
            "revision": 2,
        },
        exact_bytes=exact,
    )


class _ReadUow:
    def __init__(self, connection: object) -> None:
        self.connection = connection
        self.exited = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.exited = True


@dataclass
class _StageReader:
    stage: ExactFirstSpecimenStage
    expected_connection: object
    calls: int = 0

    def load_exact(self, connection: object, *_args: object, **kwargs: object):
        assert connection is self.expected_connection
        assert kwargs["expected_state"] == "VERIFIED"
        self.calls += 1
        return self.stage


def test_verify_handler_is_read_only_and_returns_only_exact_staged_digest(
    monkeypatch,
) -> None:
    assignment = _assignment()
    authorization = _authorization(assignment)
    claim = _claim(assignment, authorization)
    exact = canonical_bytes({"candidate": "read-only"})
    connection = object()
    uow = _ReadUow(connection)
    reader = _StageReader(_stage(assignment, exact, CLAIM_TYPE.type_id), connection)
    monkeypatch.setattr(
        terminal_module,
        "_resolve_scope",
        lambda exact_connection, _assignment, *, actor_id: (
            _scope()
            if exact_connection is connection and actor_id == "node-a"
            else pytest.fail("scope connection/actor drift")
        ),
    )
    handler = PostgresVerifyAdmitHandler(
        uow_factory=lambda: uow,
        operation_contract_digest=assignment.operation_contract_digest,
        handler_binding_digest=assignment.handler_binding_digest,
        interpreter_profile_digest=assignment.handler_binding.interpreter_profile_digest,
        stage_reader=reader,
    )
    outcome = handler.execute(
        assignment,
        claim,
        RuntimeExecutionContext(
            NodeIdentity("node-a", "node-inc-1", NOW),
            NOW,
        ),
    )
    assert outcome.result_digest == _digest(exact)
    assert outcome.receipt_ref is None
    assert reader.calls == 1 and uow.exited
    assert not hasattr(uow, "commit")

    wrong = _assignment("artifact.compose_markdown.v1")
    with pytest.raises(DefiniteInterpreterFailure):
        handler.execute(
            wrong,
            _claim(wrong, _authorization(wrong)),
            RuntimeExecutionContext(NodeIdentity("node-a", "node-inc-1", NOW), NOW),
        )


@pytest.mark.parametrize(
    "kind", (CLAIM_TYPE.type_id, GAP_TYPE.type_id, RESEARCH_ARTIFACT_TYPE.type_id)
)
def test_candidate_decoder_covers_claim_gap_and_artifact(kind: str) -> None:
    assignment = _assignment(
        {
            CLAIM_TYPE.type_id: "claim.form_or_open_gap.v1",
            GAP_TYPE.type_id: "claim.form_or_open_gap.v1",
            RESEARCH_ARTIFACT_TYPE.type_id: "artifact.compose_markdown.v1",
        }[kind]
    )
    if kind == CLAIM_TYPE.type_id:
        payload: Any = Claim(
            "claim-1",
            "statement-1",
            ("q-1",),
            (),
            "uncertainty-1",
            "DRAFT",
            {"inquiry": "i-1"},
        )
    elif kind == GAP_TYPE.type_id:
        payload = Gap(
            "gap-1",
            "inquiry-1",
            "need evidence",
            "missing",
            "obtain evidence",
            {"mode": "reopen"},
            "evidence",
        )
    else:
        payload = ResearchArtifact(
            "artifact-1",
            "project-value:artifact-bytes",
            None,
            ("claim-1",),
            ("q-1",),
            ("m-1",),
            "markdown",
            1,
            "DRAFT",
        )
    digest_field = "content_digest"
    exact = canonical_bytes(dataclass_to_json(payload, (digest_field,)))
    assert payload.content_digest == _digest(exact)
    candidate = FirstSpecimenCandidateDecoder().decode_exact(
        object(), _stage(assignment, exact, kind), _authorization(assignment)
    )
    assert isinstance(candidate, terminal_module.ResearchObjectCandidate)
    assert candidate.ref.content_digest == _digest(exact)
    assert candidate.ref.revision == 1
    assert candidate.expected_revision == 0


def _object_ref(object_id: str, object_type: Any) -> ResearchObjectRef:
    return ResearchObjectRef(
        object_id=object_id,
        object_type=object_type,
        project_key="alpha",
        revision=1,
        incarnation=f"{object_id}-inc-1",
        owner_binding_ref="CapturedMaterialSnapshot"
        if object_type == MATERIAL_REF_TYPE
        else "ResearchLedger",
        content_ref=f"project-value:{object_id}",
        content_digest=_digest(object_id),
        provenance_closure_digest=_digest(object_id + "-provenance"),
        lifecycle_state="ADMITTED",
    )


def test_candidate_decoder_keeps_evidence_qualification_relation_only(
    monkeypatch,
) -> None:
    assignment = _assignment("evidence.qualify.v1")
    qualification = EvidenceQualification(
        qualification_id="qualification-1",
        project_key="alpha",
        material_ref="material-1",
        inquiry_ref="inquiry-1",
        claim_ref=None,
        direction="SUPPORTS",
        scope_statement_ref="scope-1",
        uncertainty_profile_ref="uncertainty-1",
        verifier_profile_ref="verifier-1",
        provenance_closure_digest=_digest("qualification-provenance"),
        validity=Validity(None, None),
        revision=1,
        incarnation="candidate-inc-1",
    )
    exact = canonical_bytes(dataclass_to_json(qualification, ("qualification_digest",)))
    refs = {
        "material-1": _object_ref("material-1", MATERIAL_REF_TYPE),
        "inquiry-1": _object_ref("inquiry-1", INQUIRY_TYPE),
    }
    monkeypatch.setattr(
        terminal_module,
        "_load_current_object",
        lambda _connection, _staged, object_id: refs[object_id],
    )
    candidate = FirstSpecimenCandidateDecoder().decode_exact(
        object(),
        _stage(assignment, exact, EVIDENCE_QUALIFICATION_TYPE.type_id),
        _authorization(assignment),
    )
    assert isinstance(candidate, terminal_module.EvidenceRelationCandidate)
    assert candidate.qualification.qualification_digest == _digest(exact)
    assert not isinstance(candidate, terminal_module.ResearchObjectCandidate)


class _ReceiptPort:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.calls = 0

    def read_exact_receipt(self, **_kwargs: object) -> bytes:
        self.calls += 1
        return self.content


def test_candidate_decoder_covers_delivery_receipt_with_authoritative_readback(
    monkeypatch,
) -> None:
    assignment = _assignment("delivery.internal_export.v1")
    receipt_content = canonical_bytes({"provider": "internal", "result": "stored"})
    receipt = DeliveryReceiptRef(
        receipt_ref="receipt:sha256:" + _digest(receipt_content),
        delivery_intent_ref="delivery-intent-1",
        attempt_ref="delivery-attempt-1",
        provider_locator="internal-export://scope/sha256/content",
        receipt_digest=_digest(receipt_content),
        outcome_time=NOW,
    )
    exact = canonical_bytes(dataclass_to_json(receipt, ("content_digest",)))
    artifact = _object_ref("artifact-1", RESEARCH_ARTIFACT_TYPE)
    monkeypatch.setattr(
        terminal_module,
        "_load_delivery_artifact",
        lambda *_args: artifact,
    )
    receipts = _ReceiptPort(receipt_content)
    candidate = FirstSpecimenCandidateDecoder(delivery_receipts=receipts).decode_exact(
        object(),
        _stage(assignment, exact, DELIVERY_RECEIPT_REF_TYPE.type_id),
        _authorization(assignment),
    )
    assert isinstance(candidate, terminal_module.DeliveryReceiptCandidate)
    assert candidate.receipt == receipt
    assert candidate.artifact_ref == artifact
    assert candidate.delivered_as.relation_type == "delivered_as"
    assert receipts.calls == 1


def _lifecycle(claim: ClaimBinding) -> ClaimedLifecycle:
    return ClaimedLifecycle(
        claim=claim,
        run_id="run-1",
        step_id="admission-step",
        work_item_id="work-admission",
        attempt_id=claim.attempt_id,
        reservation_id="reservation-1",
        expected_run_revision=7,
        expected_step_revision=2,
        expected_work_revision=4,
        expected_attempt_revision=1,
        expected_reservation_revision=2,
    )


class _Activation:
    def __init__(self, connection: object) -> None:
        self.connection = connection
        self.calls = 0

    def activate_after_terminal(self, **kwargs: object) -> object:
        assert kwargs["connection"] is self.connection
        self.calls += 1
        return {"activated": True}


class _FakeLifecycleRepository:
    def __init__(self, connection: object, _scope: RuntimeScope) -> None:
        self.connection = connection

    def begin_commit(
        self, claimed: ClaimedLifecycle, **_kwargs: object
    ) -> ClaimedLifecycle:
        return replace(
            claimed,
            expected_run_revision=claimed.expected_run_revision + 1,
            expected_step_revision=claimed.expected_step_revision + 1,
            expected_work_revision=claimed.expected_work_revision + 1,
        )

    def complete_if_satisfied(self, *_args: object, **_kwargs: object) -> bool:
        return False


class _PlanRepository:
    def __init__(self, step_id: str) -> None:
        self.step_id = step_id

    def get(self, _scope: object, _plan_digest: str) -> object:
        return SimpleNamespace(
            ordered_steps=(
                SimpleNamespace(step_id=self.step_id, step_kind="ADMISSION"),
            )
        )


class _Admission:
    def __init__(self, connection: object, commit: CanonicalCommit) -> None:
        self.connection = connection
        self.commit = commit
        self.calls: list[str] = []

    def prepare(self, **kwargs: object) -> object:
        self.calls.append("prepare")
        return SimpleNamespace(**kwargs)

    def commit_prepared(self, _prepared: object) -> AdmissionResult:
        self.calls.append("commit")
        return AdmissionResult(AdmissionProgress.CANONICAL_COMMITTED, 0, self.commit)

    def finalize(self, _prepared: object, commit: CanonicalCommit) -> AdmissionResult:
        assert commit == self.commit
        self.calls.append("finalize")
        return AdmissionResult(AdmissionProgress.FINALIZED, 1, commit)


def test_terminal_hook_enlists_commit_and_activation_on_the_same_connection(
    monkeypatch,
) -> None:
    assignment = _assignment()
    authorization = _authorization(assignment)
    claim_binding = _claim(assignment, authorization)
    exact = canonical_bytes(
        dataclass_to_json(
            Claim(
                "claim-1",
                "statement-1",
                (),
                (),
                "uncertainty",
                "DRAFT",
                {"inquiry": "i-1"},
            ),
            ("content_digest",),
        )
    )
    staged = _stage(assignment, exact, CLAIM_TYPE.type_id)
    connection = object()
    activation = _Activation(connection)
    canonical = CanonicalCommit(
        commit_intent_id="commit-1",
        canonical_owner="ResearchLedger",
        project_key="alpha",
        object_id="claim-1",
        canonical_ref="canonical:research-object:claim-1:1",
        canonical_revision=1,
        canonical_incarnation="candidate-inc-1",
        content_digest=staged.content_digest,
        receipt_digest=_digest("canonical-receipt"),
    )
    admission = _Admission(connection, canonical)
    events = ({"seq": 1, "event_type": "CommitPrepared"},)
    verification = VerificationBinding.from_content(
        program_digest=assignment.program_digest,
        plan_digest=assignment.plan_digest,
        step_id=assignment.step_id,
        attempt_id=claim_binding.attempt_id,
        input_closure_digest=assignment.input_closure_digest,
        output_content_digest=staged.content_digest,
        ordered_event_payloads=events,
        schema_digest=_digest("schema"),
        compiler_identity="compiler@1",
        interpreter_identity="handler@1",
        verifier_identity="verifier@1",
        actor_id="node-a",
        project_key="alpha",
        authority_digest=authorization.binding_digest,
        project_registry_revision=3,
        project_scope_digest=_scope().project_scope.scope_digest,
        resolved_schema="project_alpha",
        canonical_owner="ResearchLedger",
        canonical_object_id="claim-1",
        canonical_base_revision=0,
        canonical_incarnation="candidate-inc-1",
        evidence_digest=_digest("evidence"),
        receipt_digest=_digest("verification-receipt"),
        provenance_digest=staged.provenance_digest,
        qualifier="STANDARD",
    )
    intent = CommitIntent(
        commit_intent_id="commit-1",
        canonical_owner="ResearchLedger",
        project_key="alpha",
        object_id="claim-1",
        project_registry_revision=3,
        project_scope_digest=_scope().project_scope.scope_digest,
        expected_base_revision=0,
        expected_incarnation="candidate-inc-1",
        content_digest=staged.content_digest,
        ordered_event_closure_digest=verification.ordered_event_payload_closure_digest,
        verification_binding_digest=verification.binding_digest,
        authority_digest=authorization.binding_digest,
        idempotency_key="admit-claim-1",
    )
    packet = ExactAdmissionPacket(
        candidate=object(),
        intent=intent,
        binding=verification,
        ordered_event_payloads=events,
        authorization=authorization,
    )
    monkeypatch.setattr(
        terminal_module, "RuntimeLifecycleRepository", _FakeLifecycleRepository
    )
    monkeypatch.setattr(
        terminal_module, "_one_public", lambda *_args, **_kwargs: {"state": "RUNNING"}
    )
    reader = _StageReader(staged, connection)
    hook = PostgresFirstSpecimenTerminalHook(
        bundle=build_first_specimen_bundle(),
        activation=activation,
        stage_reader=reader,
        admission_factory=lambda exact_connection, _scope, _tables: (
            admission
            if exact_connection is connection
            else pytest.fail("connection drift")
        ),
        plan_repository_factory=lambda _connection, _tables: _PlanRepository(
            assignment.step_id or ""
        ),
    )
    monkeypatch.setattr(hook, "_packet", lambda **_kwargs: packet)
    lifecycle = _lifecycle(claim_binding)
    terminal = TerminalOutcome(
        claimed=lifecycle,
        kind=EffectTerminalKind.SUCCEEDED,
        authority_digest=authorization.binding_digest,
        output_digest=staged.content_digest,
        observed_at=NOW,
    )
    prepared = hook.prepare_terminal(
        connection=connection,
        scope=_scope(),
        claim=SimpleNamespace(assignment=assignment, claim_binding=claim_binding),
        lifecycle=lifecycle,
        outcome=InterpreterOutcome.succeeded(staged.content_digest),
        terminal=terminal,
    )
    assert (
        prepared.claimed.expected_step_revision == lifecycle.expected_step_revision + 1
    )
    assert prepared.staged_artifact_id == staged.artifact_id
    assert prepared.expected_staged_revision == 1
    assert prepared.admit_staged
    assert prepared.receipt_ref == f"receipt:sha256:{canonical.receipt_digest}"
    assert admission.calls == ["prepare", "commit", "finalize"]
    hook.after_terminal(
        connection=connection,
        scope=_scope(),
        claim=SimpleNamespace(assignment=assignment),
        lifecycle=prepared.claimed,
        outcome=InterpreterOutcome.succeeded(staged.content_digest),
        terminal=prepared,
    )
    assert activation.calls == 1


def test_terminal_hook_fails_closed_if_shared_commit_transition_is_absent(
    monkeypatch,
) -> None:
    assignment = _assignment()
    authorization = _authorization(assignment)
    claim_binding = _claim(assignment, authorization)
    monkeypatch.setattr(
        terminal_module, "_one_public", lambda *_args, **_kwargs: {"state": "SUCCEEDED"}
    )
    hook = PostgresFirstSpecimenTerminalHook(
        bundle=build_first_specimen_bundle(), activation=_Activation(object())
    )
    lifecycle = _lifecycle(claim_binding)
    with pytest.raises(FirstSpecimenTerminalError, match="CommitPrepared"):
        hook.prepare_terminal(
            connection=object(),
            scope=_scope(),
            claim=SimpleNamespace(assignment=assignment, claim_binding=claim_binding),
            lifecycle=lifecycle,
            outcome=InterpreterOutcome.succeeded(_digest("candidate")),
            terminal=TerminalOutcome(
                claimed=lifecycle,
                kind=EffectTerminalKind.SUCCEEDED,
                authority_digest=authorization.binding_digest,
                output_digest=_digest("candidate"),
                observed_at=NOW,
            ),
        )
