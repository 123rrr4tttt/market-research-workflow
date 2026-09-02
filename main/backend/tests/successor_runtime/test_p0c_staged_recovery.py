"""CW08 exact staged-digest recovery without upstream effect replay."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any

import pytest

from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.admission import CommitIntent, VerificationBinding
from app.successor_runtime.runtime.admission_coordinator import (
    AdmissionCoordinator,
    AdmissionProgress,
    AdmissionRegistration,
    CanonicalCommit,
    CanonicalCommitReadback,
    ExactAdmissionRegistry,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledAdmissionBinding,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.staged_recovery import (
    ExactStagedArtifact,
    RecoverableStagedState,
    StagedAdmissionRecoveryCoordinator,
    StagedArtifactRecoveryError,
    StagedRecoveryRequest,
)

pytestmark = pytest.mark.unit


def _digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _fixture() -> tuple[
    RuntimeScope,
    RuntimeAssignment,
    VerificationBinding,
    CommitIntent,
    tuple[object, ...],
    StagedRecoveryRequest,
    ExactStagedArtifact,
]:
    scope = RuntimeScope(
        ProjectScopeRef(
            project_key="alpha",
            resolved_schema="project_alpha",
            project_registry_revision=3,
            incarnation="project-inc-3",
            scope_digest=_digest("scope-inc-3"),
        ),
        actor_id="node-a",
    )
    operation = OperationContractRef(
        kind="artifact.compose_markdown.v1",
        contract_version="1.0.0",
        contract_digest=_digest("artifact-operation"),
    )
    deployment_digest = _digest("deployment")
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=operation.contract_digest,
        interpreter_profile_digest=_digest("interpreter-profile"),
        deployment_catalog_digest=deployment_digest,
        runtime_protocol_version="1",
        project_scope_digest=scope.project_scope.scope_digest,
        resource_policy_epoch=2,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    return_binding = ReturnContractBinding.from_contract(
        "mrw.return.artifact.test.v1",
        ReturnContract(
            success_modes=("SUCCEEDED",),
            failure_modes=("FAILED",),
            admission_required=True,
        ),
    )
    plan_digest = _digest("plan")
    compiled = CompiledAdmissionBinding.from_content(
        plan_digest=plan_digest,
        effect_step_id="effect-compose",
        admission_step_id="admit-artifact",
        operation_contract_digest=operation.contract_digest,
        return_contract_ref=return_binding.return_contract_ref,
        return_contract_digest=return_binding.binding_digest,
        source_map_digest=_digest("source-map"),
        control_digest=_digest("control"),
    )
    content = b'{"artifact":"exact-staged-value"}'
    content_digest = _digest(content)
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work-admit-artifact",
        assignment_kind=AssignmentKind.VERIFY_ADMIT,
        project_key="alpha",
        run_id="run-1",
        step_id=compiled.admission_step_id,
        step_role=CompiledStepRole.ADMISSION,
        capability_id="artifact.first-specimen.v1",
        operation_contract_ref=operation,
        operation_contract_digest=operation.contract_digest,
        return_contract_binding=return_binding,
        compiled_admission_binding=compiled,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{interpreter.binding_digest}",
        handler_binding_digest=interpreter.binding_digest,
        handler_binding=interpreter,
        program_digest=_digest("program"),
        plan_digest=plan_digest,
        deployment_catalog_digest=deployment_digest,
        execution_epoch=1,
        incarnation="run-inc-1",
        input_refs=("value:claims",),
        input_closure_digest=_digest("input-closure"),
        payload_ref="project-value:artifact-1",
        payload_digest=content_digest,
        queue_eligibility_digest=_digest("eligibility"),
        resource_policy_epoch=2,
        claim_authority_epoch=4,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        trace_id="trace-1",
    )
    events: tuple[object, ...] = (
        {"event": "ArtifactAdmitted", "artifact_id": "artifact-1"},
    )
    authority = _digest("authority")
    binding = VerificationBinding.from_content(
        program_digest=assignment.program_digest,
        plan_digest=plan_digest,
        step_id=assignment.step_id,
        attempt_id="attempt-admit-1",
        input_closure_digest=assignment.input_closure_digest,
        output_content_digest=content_digest,
        ordered_event_payloads=events,
        schema_digest=_digest("schema"),
        compiler_identity="compiler@1",
        interpreter_identity="artifact-interpreter@1",
        verifier_identity="artifact-verifier@1",
        actor_id=scope.actor_id,
        project_key="alpha",
        authority_digest=authority,
        project_registry_revision=3,
        project_scope_digest=scope.project_scope.scope_digest,
        resolved_schema=scope.project_scope.resolved_schema,
        canonical_owner="ResearchLedger",
        canonical_object_id="artifact-1",
        canonical_base_revision=0,
        canonical_incarnation="artifact-inc-1",
        evidence_digest=_digest("evidence"),
        receipt_digest=_digest("verification-receipt"),
        provenance_digest=_digest("provenance"),
        declared_loss_profile_ref="loss:none",
        qualifier="STANDARD",
    )
    intent = CommitIntent(
        commit_intent_id="commit-artifact-1",
        canonical_owner="ResearchLedger",
        project_key="alpha",
        object_id="artifact-1",
        project_registry_revision=3,
        project_scope_digest=scope.project_scope.scope_digest,
        expected_base_revision=0,
        expected_incarnation="artifact-inc-1",
        content_digest=content_digest,
        ordered_event_closure_digest=binding.ordered_event_payload_closure_digest,
        verification_binding_digest=binding.binding_digest,
        authority_digest=authority,
        idempotency_key="admit-artifact-1",
    )
    request = StagedRecoveryRequest(
        artifact_id="artifact-1",
        value_id="artifact-1",
        effect_attempt_id="attempt-compose-1",
        effect_receipt_ref="receipt:compose:sha256:" + _digest("compose-receipt"),
        object_type="ResearchArtifact.v1",
        codec_id="mrw.research-artifact.v1",
        value_revision=1,
        value_incarnation="artifact-value-inc-1",
        qualifier_ref="qualifier:standard",
        loss_profile_ref="loss:none",
    )
    staged = ExactStagedArtifact(
        artifact_id=request.artifact_id,
        project_key="alpha",
        run_id="run-1",
        effect_step_id=compiled.effect_step_id,
        effect_attempt_id=request.effect_attempt_id,
        effect_receipt_ref=request.effect_receipt_ref,
        value_id=request.value_id,
        object_type=request.object_type,
        codec_id=request.codec_id,
        content_digest=content_digest,
        byte_size=len(content),
        value_revision=request.value_revision,
        value_incarnation=request.value_incarnation,
        qualifier_ref=request.qualifier_ref,
        loss_profile_ref=request.loss_profile_ref,
        state=RecoverableStagedState.STAGED,
        staged_revision=0,
        exact_bytes=content,
    )
    return scope, assignment, binding, intent, events, request, staged


class _StagedStore:
    def __init__(self, staged: ExactStagedArtifact) -> None:
        self.staged = staged
        self.loads = 0
        self.verifications = 0

    def load_exact(self, **_kwargs: object) -> ExactStagedArtifact:
        self.loads += 1
        return self.staged

    def mark_verified(
        self, staged: ExactStagedArtifact
    ) -> ExactStagedArtifact:
        assert staged == self.staged
        self.verifications += 1
        self.staged = replace(
            staged,
            state=RecoverableStagedState.VERIFIED,
            staged_revision=staged.staged_revision + 1,
        )
        return self.staged


class _Decoder:
    def __init__(self) -> None:
        self.calls = 0

    def decode_exact(self, staged: ExactStagedArtifact) -> object:
        self.calls += 1
        return {"exact_bytes": staged.exact_bytes}


class _IntentStore:
    def __init__(self) -> None:
        self.row: dict[str, Any] | None = None

    def prepare(self, binding: object) -> dict[str, Any]:
        if self.row is None:
            binding_values = binding.values()  # type: ignore[attr-defined]
            self.row = {
                **binding_values,
                "state": "PREPARED",
                "revision": 0,
            }
        return dict(self.row)

    def load(self, _commit_intent_id: str) -> dict[str, Any]:
        assert self.row is not None
        return dict(self.row)

    def mark_committed(self, _commit_intent_id: str, **kwargs: object) -> dict[str, Any]:
        assert self.row is not None
        self.row.update(
            state="COMMITTED",
            revision=int(self.row["revision"]) + 1,
            canonical_commit_ref=kwargs["canonical_commit_ref"],
            receipt_digest=kwargs["receipt_digest"],
        )
        return dict(self.row)

    def mark_outcome_unknown(self, _commit_intent_id: str, **_kwargs: object) -> dict[str, Any]:
        assert self.row is not None
        self.row.update(state="OUTCOME_UNKNOWN", revision=int(self.row["revision"]) + 1)
        return dict(self.row)


class _Handler:
    canonical_owner = "ResearchLedger"

    def __init__(self) -> None:
        self.commit_count = 0
        self.commit_result: CanonicalCommit | None = None

    def commit(
        self,
        _scope: RuntimeScope,
        intent: CommitIntent,
        _candidate: object,
        _binding: VerificationBinding,
    ) -> CanonicalCommit:
        self.commit_count += 1
        self.commit_result = CanonicalCommit(
            commit_intent_id=intent.commit_intent_id,
            canonical_owner=intent.canonical_owner,
            project_key=intent.project_key,
            object_id=intent.object_id,
            canonical_ref="canonical:artifact-1:1",
            canonical_revision=1,
            canonical_incarnation=intent.expected_incarnation,
            content_digest=intent.content_digest,
            receipt_digest=_digest("canonical-receipt"),
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


def _recovery(
    assignment: RuntimeAssignment,
    staged: ExactStagedArtifact,
) -> tuple[StagedAdmissionRecoveryCoordinator, _StagedStore, _Decoder, _Handler]:
    handler = _Handler()
    store = _IntentStore()
    registry = ExactAdmissionRegistry(
        (
            AdmissionRegistration(
                operation_contract_ref=assignment.operation_contract_ref,
                handler=handler,
            ),
        )
    )
    admission = AdmissionCoordinator(
        registry=registry,
        commit_intents=store,
        commit_binding_factory=lambda *, assignment, intent: type(
            "_Binding",
            (),
            {
                "values": lambda self: {
                    "commit_intent_id": intent.commit_intent_id,
                    "capability_id": assignment.capability_id,
                    "idempotency_key": intent.idempotency_key,
                }
            },
        )(),
    )
    staged_store = _StagedStore(staged)
    decoder = _Decoder()
    return (
        StagedAdmissionRecoveryCoordinator(
            staged_artifacts=staged_store,
            admission=admission,
            decoder=decoder,
        ),
        staged_store,
        decoder,
        handler,
    )


def test_cw08_recovery_uses_exact_staged_bytes_and_readback_prevents_duplicate_commit() -> None:
    scope, assignment, binding, intent, events, request, staged = _fixture()
    recovery, store, decoder, handler = _recovery(assignment, staged)

    first = recovery.resume(
        scope=scope,
        assignment=assignment,
        intent=intent,
        binding=binding,
        request=request,
        current_authority_digest=binding.authority_digest,
        current_base_revision=0,
        current_incarnation="artifact-inc-1",
        ordered_event_payloads=events,
    )
    second = recovery.resume(
        scope=scope,
        assignment=assignment,
        intent=intent,
        binding=binding,
        request=request,
        current_authority_digest=binding.authority_digest,
        current_base_revision=0,
        current_incarnation="artifact-inc-1",
        ordered_event_payloads=events,
    )

    assert first.admission.progress is AdmissionProgress.CANONICAL_COMMITTED
    assert second.admission.progress is AdmissionProgress.CANONICAL_COMMITTED
    assert handler.commit_count == 1
    assert store.loads == 2
    assert store.verifications == 1
    assert decoder.calls == 2


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("content_digest", _digest("mutated"), "content_digest"),
        ("effect_attempt_id", "attempt-rebound", "effect_attempt_id"),
        ("effect_receipt_ref", "receipt:rebound", "effect_receipt_ref"),
        ("value_incarnation", "value-inc-rebound", "value_incarnation"),
        ("qualifier_ref", "qualifier:rebound", "qualifier_ref"),
    ),
)
def test_cw08_staged_binding_drift_fails_before_decode_or_admission(
    field: str,
    replacement: object,
    message: str,
) -> None:
    scope, assignment, binding, intent, events, request, staged = _fixture()
    recovery, store, decoder, handler = _recovery(
        assignment, replace(staged, **{field: replacement})
    )
    with pytest.raises(StagedArtifactRecoveryError, match=message):
        recovery.resume(
            scope=scope,
            assignment=assignment,
            intent=intent,
            binding=binding,
            request=request,
            current_authority_digest=binding.authority_digest,
            current_base_revision=0,
            current_incarnation="artifact-inc-1",
            ordered_event_payloads=events,
        )
    assert store.verifications == decoder.calls == handler.commit_count == 0


@pytest.mark.parametrize(
    ("authority", "base_revision", "incarnation"),
    (
        (_digest("rebound-authority"), 0, "artifact-inc-1"),
        (_digest("authority"), 1, "artifact-inc-1"),
        (_digest("authority"), 0, "artifact-inc-2"),
    ),
)
def test_cw08_current_authority_base_or_incarnation_drift_fails_closed(
    authority: str,
    base_revision: int,
    incarnation: str,
) -> None:
    scope, assignment, binding, intent, events, request, staged = _fixture()
    recovery, store, decoder, handler = _recovery(assignment, staged)
    with pytest.raises(
        StagedArtifactRecoveryError,
        match="authority/base/incarnation drift",
    ):
        recovery.resume(
            scope=scope,
            assignment=assignment,
            intent=intent,
            binding=binding,
            request=request,
            current_authority_digest=authority,
            current_base_revision=base_revision,
            current_incarnation=incarnation,
            ordered_event_payloads=events,
        )
    assert store.loads == decoder.calls == handler.commit_count == 0
