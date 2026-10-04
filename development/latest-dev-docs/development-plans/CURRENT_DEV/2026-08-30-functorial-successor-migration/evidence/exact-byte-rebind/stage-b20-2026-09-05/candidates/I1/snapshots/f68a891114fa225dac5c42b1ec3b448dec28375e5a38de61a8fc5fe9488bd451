"""Shared deterministic fixtures for the P4 C7 ingest-index family line.

Every runtime identity (RuntimeAssignment, HandlerBinding, VerificationBinding
and DocumentRef) is derived from the real compiled C7.1 EFFECT/ADMISSION steps
or from canonical commit readback; no runtime intent self-assertion is used.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.successor_migration.document_repository_c7 import (
    CanonicalCommitReadback,
    DocumentRef,
    document_ref_from_readback,
)
from app.successor_runtime.capabilities import ingest_c7_common as c7
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.ingest_c7_program import (
    build_ingest_c7_1_program,
    compile_ingest_c7_program,
)
from app.successor_runtime.runtime.admission import (
    CommitIntent,
    CommitIntentState,
    VerificationBinding,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.reconciliation import (
    EffectAttemptObservation,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest

PROJECT_KEY = "p4-c7-demo"
REGISTRY_REVISION = 1
RESOLVED_SCHEMA = "mrw_p4_c7_demo"
SCOPE_INCARNATION = "scope-inc-c7"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    RESOLVED_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
CANDIDATE_ID = "ingest-candidate-p4c7-001"
DEPLOYMENT_CATALOG_DIGEST = content_digest(
    {"catalog": "mrw.successor.deployment-catalog.c7.v1"}
)
AUTHORITY_DIGEST = content_digest({"authority": "c7-fixture"})
PROGRAM_ID = "program:p4-c7-family"
ATTEMPT_ID = content_digest({"attempt": "p4-c7:001"})


def submission(**overrides: Any) -> c7.C7IngestSubmission:
    values = {
        "idempotency_key": "idem:p4-c7:001",
        "project_key": PROJECT_KEY,
        "source_locator": "https://example.invalid/report",
        "request_key": "req:p4-c7:001",
        "raw_payload": {
            "title": " Q2 Market ",
            "text": " Market grew 12%  in Q2. ",
        },
    }
    values.update(overrides)
    return c7.C7IngestSubmission(**values)


def normalized() -> c7.NormalizedIngestDocument:
    return c7.normalize_ingest_submission(submission())


def bundle() -> c7.C7IngestCapabilityBundle:
    return c7.build_ingest_c7_bundle()


def catalog() -> Any:
    return c7.build_ingest_c7_catalog(bundle())


def registry() -> Any:
    return c7.build_ingest_c7_registry(bundle())


def contract_ref(kind: str) -> Any:
    ref = catalog().lookup(kind)
    if ref is None:
        raise KeyError(kind)
    return ref


def program_and_plan(
    payload: c7.C7IngestSubmission | None = None,
) -> tuple[Any, Any, Any, Any]:
    payload = payload or submission()
    program = build_ingest_c7_1_program(
        payload=payload,
        catalog=catalog(),
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_ingest_c7_program(
        program,
        catalog(),
        operation_contracts=registry(),
    )
    ref = program.root.operation.contract_ref
    payload_ref = program.root.operation.payload_ref
    return program, plan, ref, payload_ref


def compiled_effect_step(plan: Any) -> Any:
    steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    if len(steps) != 1:
        raise AssertionError("C7.1 plan must contain exactly one EFFECT step")
    return steps[0]


def compiled_admission_step(plan: Any) -> Any:
    steps = [step for step in plan.ordered_steps if step.step_kind == "ADMISSION"]
    if len(steps) != 1:
        raise AssertionError("C7.1 plan must contain exactly one ADMISSION step")
    return steps[0]


def _ordered_event_payloads() -> tuple[dict[str, object], ...]:
    return (
        {
            "seq": 1,
            "event_type": "submitted",
            "payload": {"request_key": "req:p4-c7:001"},
        },
        {
            "seq": 2,
            "event_type": "fetched",
            "payload": {"source_locator": submission().source_locator},
        },
        {
            "seq": 3,
            "event_type": "normalized",
            "payload": {"content_digest": normalized().content_digest},
        },
        {
            "seq": 4,
            "event_type": "candidate_created",
            "payload": {"candidate_id": CANDIDATE_ID},
        },
    )


def interpreter_binding(effect_step: Any) -> InterpreterBinding:
    profile = bundle().profiles["interpreter"]
    return InterpreterBinding.from_content(
        operation_contract_digest=effect_step.operation_contract_ref.contract_digest,
        interpreter_profile_digest=profile.profile_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        runtime_protocol_version="1",
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=1,
        authority_requirement_digest=AUTHORITY_DIGEST,
    )


def runtime_assignment() -> RuntimeAssignment:
    """RuntimeAssignment derived exactly from the compiled EFFECT step."""

    program, plan, _ref, payload_ref = program_and_plan()
    effect_step = compiled_effect_step(plan)
    binding = interpreter_binding(effect_step)
    return_contract = effect_step.return_contract
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work-original",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id="run-1",
        step_id=effect_step.step_id,
        step_role=CompiledStepRole.EFFECT,
        capability_id=c7.C7_INGEST_OWNER,
        operation_contract_ref=effect_step.operation_contract_ref,
        operation_contract_digest=effect_step.operation_contract_ref.contract_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            effect_step.return_contract_ref or c7.C7_ADMISSION_RETURN_CONTRACT_REF,
            return_contract,
        ),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=program.program_digest,
        plan_digest=plan.plan_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=1,
        incarnation="run-incarnation-1",
        input_refs=(payload_ref.storage_ref,),
        input_closure_digest=payload_ref.content_digest,
        payload_ref=payload_ref.storage_ref,
        payload_digest=payload_ref.content_digest,
        queue_eligibility_digest=content_digest({"eligibility": "c7"}),
        resource_policy_epoch=1,
        claim_authority_epoch=2,
        claim_policy_digest=content_digest({"claim-policy": "c7"}),
        expected_step_revision=0,
        trace_id="trace-1",
    )


def verification_binding() -> VerificationBinding:
    """VerificationBinding derived from the real compiled ADMISSION step."""

    program, plan, _ref, payload_ref = program_and_plan()
    admission_step = compiled_admission_step(plan)
    profile = bundle().profiles["interpreter"]
    return VerificationBinding.from_content(
        program_digest=program.program_digest,
        plan_digest=plan.plan_digest,
        step_id=admission_step.step_id,
        attempt_id=ATTEMPT_ID,
        input_closure_digest=payload_ref.content_digest,
        output_content_digest=normalized().content_digest,
        ordered_event_payloads=_ordered_event_payloads(),
        schema_digest=content_digest({"schema": "ingest.c7.admission.v1"}),
        compiler_identity=plan.compiler_id,
        interpreter_identity=profile.profile_id,
        verifier_identity="ingest.validator.c7.v1",
        actor_id="actor:p4-c7",
        project_key=PROJECT_KEY,
        authority_digest=AUTHORITY_DIGEST,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        resolved_schema=RESOLVED_SCHEMA,
        canonical_owner=c7.DOCUMENT_CANONICAL_OWNER,
        canonical_object_id=CANDIDATE_ID,
        canonical_base_revision=0,
        canonical_incarnation=SCOPE_INCARNATION,
        evidence_digest=content_digest({"evidence": "c7-fixture"}),
        receipt_digest=content_digest({"receipt": "c7-fixture"}),
        provenance_digest=content_digest({"provenance": "c7-fixture"}),
        qualifier="staged-candidate",
    )


def commit_intent(
    *,
    binding: VerificationBinding | None = None,
) -> CommitIntent:
    binding = binding or verification_binding()
    return CommitIntent(
        commit_intent_id="commit:p4-c7:001",
        canonical_owner=c7.DOCUMENT_CANONICAL_OWNER,
        project_key=PROJECT_KEY,
        object_id=CANDIDATE_ID,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        expected_base_revision=0,
        expected_incarnation=SCOPE_INCARNATION,
        content_digest=binding.output_content_digest,
        ordered_event_closure_digest=binding.ordered_event_payload_closure_digest,
        verification_binding_digest=binding.binding_digest,
        authority_digest=binding.authority_digest,
        idempotency_key="idem:p4-c7:001",
        state=CommitIntentState.PREPARED,
    )


def canonical_commit_readback(
    *,
    committed_revision: int = 1,
) -> CanonicalCommitReadback:
    return CanonicalCommitReadback(
        commit_intent_id="commit:p4-c7:001",
        idempotency_key="idem:p4-c7:001",
        capability_id=c7.C7_INGEST_OWNER,
        project_key=PROJECT_KEY,
        object_id=CANDIDATE_ID,
        committed_revision=committed_revision,
        committed_incarnation=SCOPE_INCARNATION,
        content_digest=normalized().content_digest,
        canonical_commit_ref=f"canonical:document:p4-c7:{committed_revision}",
    )


def document_ref() -> DocumentRef:
    return document_ref_from_readback(canonical_commit_readback())


def _digest(label: str) -> str:
    return canonical_digest((label,))


def recovery_binding() -> RecoveryBinding:
    assignment = runtime_assignment()
    return RecoveryBinding.from_content(
        recovery_handler_id="c7-authoritative-readback",
        recovery_handler_version="1",
        interpreter_profile_digest=assignment.handler_binding.interpreter_profile_digest,
        authoritative_readback_profile_ref="readback-profile:c7",
    )


def effect_assignment(recovery: RecoveryBinding) -> RuntimeAssignment:
    """Original effect assignment derived from the compiled plan."""

    original = runtime_assignment()
    binding = InterpreterBinding.from_content(
        operation_contract_digest=original.operation_contract_ref.contract_digest,
        interpreter_profile_digest=recovery.interpreter_profile_digest,
        deployment_catalog_digest=original.deployment_catalog_digest,
        runtime_protocol_version=original.runtime_protocol_version,
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=original.resource_policy_epoch,
        authority_requirement_digest=original.handler_binding.authority_requirement_digest,
    )
    values = original.model_dump(mode="python")
    values.update(
        handler_binding=binding,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
    )
    return RuntimeAssignment(**values)


def recovery_assignment(
    original: RuntimeAssignment,
    recovery: RecoveryBinding,
    target_attempt_id: str,
) -> RuntimeAssignment:
    values = original.model_dump(mode="python")
    values.update(
        work_item_id="work-reconcile",
        assignment_kind=AssignmentKind.RECONCILE,
        handler_binding_kind=HandlerBindingKind.RECOVERY,
        handler_binding_ref=f"handler-binding:sha256:{recovery.binding_digest}",
        handler_binding_digest=recovery.binding_digest,
        handler_binding=recovery,
        expected_step_revision=4,
        reconciliation_attempt_id=target_attempt_id,
    )
    return RuntimeAssignment(**values)


def effect_attempt_observation(
    assignment: RuntimeAssignment,
    *,
    attempt_id: str | None = None,
) -> EffectAttemptObservation:
    attempt_id = attempt_id or ATTEMPT_ID
    binding = assignment.handler_binding
    return EffectAttemptObservation(
        attempt_id=attempt_id,
        assignment_digest=assignment.assignment_digest,
        handler_binding_digest=assignment.handler_binding_digest,
        interpreter_profile_digest=binding.interpreter_profile_digest,
        interpreter_id="legacy.ingest_index.postprocess.replay.v1",
        interpreter_version="1.0.0",
        provider_id="provider.ingest.fixture",
        provider_version="1.0.0",
        external_idempotency_key="idem:p4-c7:001",
        authoritative_readback_locator="provider:ingest:receipt",
    )


NOW = datetime(2030, 8, 31, 8, 0, tzinfo=UTC)
