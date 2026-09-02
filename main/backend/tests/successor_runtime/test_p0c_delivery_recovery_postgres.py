"""Real PostgreSQL approval/receipt plus internal-export recovery acceptance."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.successor_runtime.capabilities import build_first_specimen_bundle
from app.successor_runtime.research.artifacts import (
    DELIVERY_CHANNEL,
    DELIVERY_FORMAT,
    DELIVERY_IRREVERSIBILITY_PROFILE,
    DeliveryIntent,
)
from app.successor_runtime.research.claims import Claim
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import CLAIM_TYPE
from app.successor_runtime.runtime.admission import CommitIntent, VerificationBinding
from app.successor_runtime.runtime.admission_coordinator import (
    AdmissionCoordinator,
    AdmissionProgress,
    AdmissionRegistration,
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
)
from app.successor_runtime.runtime.reconciliation import (
    EffectAttemptObservation,
    EffectReconciler,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.blob.internal_export import (
    InternalExportExecutionContext,
    InternalExportInterpreter,
    InternalExportRequest,
)
from app.successor_runtime.substrate.blob.store import ProjectBlobStore
from app.successor_runtime.substrate.postgres.approvals import (
    ApprovalBinding,
    ApprovalRepository,
)
from app.successor_runtime.substrate.postgres.commit_intents import (
    CommitIntentRepository,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.research_admission import (
    PostgresCommitIntentAdapter,
    ResearchAdmissionHandler,
    ResearchAdmissionMode,
    ResearchObjectCandidate,
    commit_binding_from_assignment,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RuntimeJournalRepository,
)
from app.successor_runtime.substrate.postgres.values import ReceiptRepository

from .p0c_postgres_fixture import (
    DELIVERY_AUTHORITY_DIGEST,
    DEPLOYMENT_CATALOG_DIGEST,
    NOW,
    PROJECT_KEY,
    PROJECT_REGISTRY_REVISION,
    PROJECT_SCHEMA,
    PROJECT_SCOPE_DIGEST,
    LiveP0CDatabase,
    live_p0c_database,
    p0c_database,
)

pytestmark = pytest.mark.integration


def _digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _seed_run(database: LiveP0CDatabase, *, run_id: str = "run:delivery") -> None:
    program_digest = _digest("delivery-program")
    with database.engine.begin() as connection:
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
                program_id="program:delivery",
                project_key=PROJECT_KEY,
                program_digest=program_digest,
                project_storage_ref=f"{PROJECT_SCHEMA}:program:delivery",
                contract_version="1.0.0",
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_runs"]).values(
                run_id=run_id,
                project_key=PROJECT_KEY,
                project_registry_revision=PROJECT_REGISTRY_REVISION,
                project_scope_digest=PROJECT_SCOPE_DIGEST,
                resolved_schema=PROJECT_SCHEMA,
                program_id="program:delivery",
                program_digest=program_digest,
                state="SUBMITTED",
                revision=0,
                next_event_seq=1,
                execution_epoch=0,
                incarnation="run-inc:delivery",
                submission_authority_digest=DELIVERY_AUTHORITY_DIGEST,
                cancellation_requested=False,
            )
        )


def _intent(*, authority_digest: str = DELIVERY_AUTHORITY_DIGEST) -> DeliveryIntent:
    return DeliveryIntent(
        delivery_intent_id="delivery-intent:p0c",
        artifact_ref="artifact:p0c@1:sha256:" + _digest("artifact-ref"),
        audience="internal-research-review",
        channel=DELIVERY_CHANNEL,
        format=DELIVERY_FORMAT,
        approval_refs=("approval:p0c-human",),
        authority_digest=authority_digest,
        idempotency_key="delivery:p0c:idempotency",
        irreversibility_profile=DELIVERY_IRREVERSIBILITY_PROFILE,
    )


def _request(
    database: LiveP0CDatabase,
    artifact: bytes,
    *,
    authority_digest: str = DELIVERY_AUTHORITY_DIGEST,
) -> InternalExportRequest:
    operation = build_first_specimen_bundle().operation_by_kind(
        "delivery.internal_export.v1"
    )
    return InternalExportRequest(
        project_key=PROJECT_KEY,
        project_scope_digest=database.scope.project_scope.scope_digest,
        run_id="run:delivery",
        step_id="step:delivery",
        attempt_id=_digest("delivery-attempt:p0c"),
        assignment_digest=_digest("delivery-assignment:p0c"),
        operation_contract_ref=operation.ref,
        handler_binding_digest=_digest("delivery-handler:p0c"),
        delivery_intent=_intent(authority_digest=authority_digest),
        artifact_bytes=artifact,
        artifact_digest=_digest(artifact),
        payload_digest=_digest("delivery-approved-payload"),
    )


def _approve(database: LiveP0CDatabase, request: InternalExportRequest) -> None:
    with database.engine.begin() as connection:
        ApprovalRepository(connection, database.scope).decide(
            ApprovalBinding(
                approval_id=request.delivery_intent.approval_refs[0],
                actor_id=database.scope.actor_id,
                run_id=request.run_id,
                step_id=request.step_id,
                payload_digest=request.payload_digest,
                decision="APPROVED",
                expires_at=NOW + timedelta(days=1),
                authority_digest=request.delivery_intent.authority_digest,
            )
        )


class CountingProjectBlobStore(ProjectBlobStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root, fsync=False)
        self.store_calls = 0

    def store(self, scope: object, data: bytes):  # type: ignore[override]
        self.store_calls += 1
        return super().store(scope, data)  # type: ignore[arg-type]


class LiveApprovalReader:
    """Fresh-connection approval readback; no approval is cached in memory."""

    def __init__(self, database: LiveP0CDatabase) -> None:
        self.database = database
        self.calls = 0

    def require_current(self, approval_id: str, **expected: object) -> object:
        self.calls += 1
        with self.database.engine.connect() as connection:
            return ApprovalRepository(
                connection, self.database.scope
            ).require_current(approval_id, **expected)  # type: ignore[arg-type]


def _receipt_body(request: InternalExportRequest, outcome_time: object) -> dict[str, object]:
    return {
        "schema_version": "mrw.internal-export.receipt.v1",
        "delivery_intent_ref": request.delivery_intent.delivery_intent_id,
        "attempt_ref": request.attempt_id,
        "provider_locator": (
            f"internal-export://{request.project_scope_digest}/sha256/"
            f"{request.artifact_digest}"
        ),
        "artifact_digest": request.artifact_digest,
        "request_digest": request.request_digest,
        "outcome_time": outcome_time,
    }


def test_a07_stale_approval_or_authority_fails_before_internal_export(
    p0c_database: LiveP0CDatabase, tmp_path: Path
) -> None:
    _seed_run(p0c_database)
    artifact = b"# P0-C internal artifact\n"
    approved = _request(p0c_database, artifact)
    _approve(p0c_database, approved)
    drifted = _request(
        p0c_database,
        artifact,
        authority_digest=_digest("revoked-delivery-authority"),
    )
    store = CountingProjectBlobStore(tmp_path)
    interpreter = InternalExportInterpreter(
        operation_contract_ref=drifted.operation_contract_ref,
        blob_store=store,
    )
    with pytest.raises(ExactBindingConflict, match="approval does not bind"):
        interpreter.execute(
            drifted,
            InternalExportExecutionContext(
                scope=p0c_database.scope,
                approvals=LiveApprovalReader(p0c_database),
                now=NOW,
            ),
        )
    assert store.store_calls == 0
    assert not store.exists(PROJECT_SCOPE_DIGEST, drifted.artifact_digest)
    with p0c_database.engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(
                p0c_database.project_tables.successor_receipts
            )
        ) == 0


def test_a10_cw10_effect_before_receipt_event_recovers_without_duplicate_export(
    p0c_database: LiveP0CDatabase, tmp_path: Path
) -> None:
    _seed_run(p0c_database)
    artifact = b"# Exact internal report\n\n- citation: material:101\n"
    request = _request(p0c_database, artifact)
    _approve(p0c_database, request)
    store = CountingProjectBlobStore(tmp_path)
    interpreter = InternalExportInterpreter(
        operation_contract_ref=request.operation_contract_ref,
        blob_store=store,
    )

    # CW10: durable PREPARED intent and content effect exist, while the
    # successor receipt row/runtime event has not yet been written.
    marker = interpreter._ensure_prepared(request, NOW)  # noqa: SLF001
    assert marker["state"] == "PREPARED"
    store.store(PROJECT_SCOPE_DIGEST, artifact)
    assert store.store_calls == 1

    recovered = interpreter.execute(
        request,
        InternalExportExecutionContext(
            scope=p0c_database.scope,
            approvals=LiveApprovalReader(p0c_database),
            now=NOW,
        ),
    )
    assert recovered.readback.disposition is EffectDisposition.SUCCEEDED
    assert store.store_calls == 1
    assert recovered.receipt.provider_locator.startswith("internal-export://")

    body = _receipt_body(request, recovered.receipt.outcome_time.isoformat())
    exact = canonical_bytes(body)
    assert hashlib.sha256(exact).hexdigest() == recovered.receipt.receipt_digest
    with p0c_database.engine.begin() as connection:
        receipts = ReceiptRepository(connection, p0c_database.project_tables)
        first = receipts.put_exact(
            p0c_database.scope,
            receipt_id=recovered.receipt.receipt_ref,
            receipt_digest=recovered.receipt.receipt_digest,
            delivery_intent_ref=recovered.receipt.delivery_intent_ref,
            attempt_ref=recovered.receipt.attempt_ref,
            provider_locator=recovered.receipt.provider_locator,
            content=exact,
            outcome_time=recovered.receipt.outcome_time,
        )
        second = receipts.put_exact(
            p0c_database.scope,
            receipt_id=recovered.receipt.receipt_ref,
            receipt_digest=recovered.receipt.receipt_digest,
            delivery_intent_ref=recovered.receipt.delivery_intent_ref,
            attempt_ref=recovered.receipt.attempt_ref,
            provider_locator=recovered.receipt.provider_locator,
            content=exact,
            outcome_time=recovered.receipt.outcome_time,
        )
        assert first == second == recovered.receipt.receipt_ref
    with p0c_database.engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(
                p0c_database.project_tables.successor_receipts
            )
        ) == 1


def _reconcile_assignment(request: InternalExportRequest) -> RuntimeAssignment:
    interpreter_profile_digest = _digest("p0c-internal-export-profile")
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="p0c-internal-export-readback",
        recovery_handler_version="1.0.0",
        interpreter_profile_digest=interpreter_profile_digest,
        authoritative_readback_profile_ref="internal-export-idempotency",
    )
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="reconcile:p0c-delivery",
        assignment_kind=AssignmentKind.RECONCILE,
        project_key=PROJECT_KEY,
        run_id=request.run_id,
        step_id=request.step_id,
        capability_id="mrw.first-specimen.delivery",
        operation_contract_ref=request.operation_contract_ref,
        operation_contract_digest=request.operation_contract_ref.contract_digest,
        handler_binding_kind=HandlerBindingKind.RECOVERY,
        handler_binding_ref=f"handler-binding:sha256:{recovery.binding_digest}",
        handler_binding_digest=recovery.binding_digest,
        handler_binding=recovery,
        program_digest=_digest("delivery-program"),
        plan_digest=_digest("delivery-plan"),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=1,
        incarnation="run-inc:delivery",
        input_closure_digest=_digest("delivery-input-closure"),
        queue_eligibility_digest=_digest("reconcile-eligibility"),
        resource_policy_epoch=1,
        claim_authority_epoch=1,
        claim_policy_digest=_digest("reconcile-claim-policy"),
        expected_step_revision=1,
        reconciliation_attempt_id=request.attempt_id,
        trace_id="trace:p0c-reconcile",
    )


def _attempt(
    request: InternalExportRequest,
    interpreter: InternalExportInterpreter,
) -> EffectAttemptObservation:
    recovery = _reconcile_assignment(request).handler_binding
    assert isinstance(recovery, RecoveryBinding)
    assert recovery.interpreter_profile_digest is not None
    return EffectAttemptObservation(
        attempt_id=request.attempt_id,
        assignment_digest=request.assignment_digest,
        handler_binding_digest=request.handler_binding_digest,
        interpreter_profile_digest=recovery.interpreter_profile_digest,
        interpreter_id=interpreter.interpreter_id,
        interpreter_version=interpreter.interpreter_version,
        provider_id=interpreter.provider_id,
        provider_version=interpreter.provider_version,
        external_idempotency_key=request.delivery_intent.idempotency_key,
        authoritative_readback_locator=interpreter.readback_locator(request),
    )


def test_cw06_outcome_unknown_waits_or_reads_back_and_reconciler_never_dispatches(
    p0c_database: LiveP0CDatabase, tmp_path: Path
) -> None:
    request = _request(p0c_database, b"# uncertain internal export\n")
    store = CountingProjectBlobStore(tmp_path)
    interpreter = InternalExportInterpreter(
        operation_contract_ref=request.operation_contract_ref,
        blob_store=store,
    )
    assignment = _reconcile_assignment(request)
    attempt = _attempt(request, interpreter)
    reconciler = EffectReconciler()

    unresolved = reconciler.reconcile(
        assignment=assignment,
        attempt=attempt,
        interpreter=interpreter,
    )
    assert unresolved.state is ReconciliationState.WAITING
    assert unresolved.disposition is EffectDisposition.OUTCOME_UNKNOWN
    assert store.store_calls == 0

    interpreter._ensure_prepared(request, NOW)  # noqa: SLF001
    store.store(PROJECT_SCOPE_DIGEST, request.artifact_bytes)
    resolved = reconciler.reconcile(
        assignment=assignment,
        attempt=attempt,
        interpreter=interpreter,
    )
    assert resolved.state is ReconciliationState.RESOLVED
    assert resolved.disposition is EffectDisposition.SUCCEEDED
    assert store.store_calls == 1


def test_a09_cw09_canonical_commit_before_event_recovers_by_readback(
    p0c_database: LiveP0CDatabase,
) -> None:
    _seed_run(p0c_database, run_id="run:delivery")
    operation = build_first_specimen_bundle().operation_by_kind(
        "claim.form_or_open_gap.v1"
    )
    claim = Claim(
        claim_id="claim:p0c:cw09",
        statement_ref="statement:p0c:cw09",
        support_relation_refs=("qualification:p0c:support",),
        contradiction_relation_refs=(),
        uncertainty_profile_ref="uncertainty:p0c:explicit",
        lifecycle_state="DRAFT",
        scope={"inquiry_ref": "inquiry:p0c:cw09"},
    )
    assert claim.content_digest is not None
    claim_ref = ResearchObjectRef(
        object_id=claim.claim_id,
        object_type=CLAIM_TYPE,
        project_key=PROJECT_KEY,
        revision=1,
        incarnation="claim-inc:p0c:cw09",
        owner_binding_ref="ResearchLedger",
        content_ref="project-value:claim:p0c:cw09",
        content_digest=claim.content_digest,
        provenance_closure_digest=_digest("claim:p0c:cw09:provenance"),
        lifecycle_state="ADMITTED",
    )
    candidate = ResearchObjectCandidate(
        ref=claim_ref,
        payload=claim,
        expected_revision=0,
        expected_incarnation=claim_ref.incarnation,
    )
    plan_digest = _digest("p0c-cw09-plan")
    return_contract_ref = operation.return_contract_ref
    from app.successor_runtime.language.object_contracts import (
        build_first_specimen_return_contract_registry,
    )

    return_binding = ReturnContractBinding.from_contract(
        return_contract_ref,
        build_first_specimen_return_contract_registry().resolve_required(
            return_contract_ref
        ),
    )
    compiled = CompiledAdmissionBinding.from_content(
        plan_digest=plan_digest,
        effect_step_id="step:p0c:cw09:effect",
        admission_step_id="step:p0c:cw09:admission",
        operation_contract_digest=operation.ref.contract_digest,
        return_contract_ref=return_binding.return_contract_ref,
        return_contract_digest=return_binding.binding_digest,
        source_map_digest=_digest("p0c-cw09-source-map"),
        control_digest=_digest("p0c-cw09-control"),
    )
    interpreter = InterpreterBinding.from_content(
        operation_contract_digest=operation.ref.contract_digest,
        interpreter_profile_digest=operation.interpreter_compatibility_ref.profile_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        runtime_protocol_version="1",
        project_scope_digest=PROJECT_SCOPE_DIGEST,
        resource_policy_epoch=1,
        authority_requirement_digest=DELIVERY_AUTHORITY_DIGEST,
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work:p0c:cw09:admission",
        assignment_kind=AssignmentKind.VERIFY_ADMIT,
        project_key=PROJECT_KEY,
        run_id="run:delivery",
        step_id=compiled.admission_step_id,
        step_role=CompiledStepRole.ADMISSION,
        capability_id="claim.first_specimen.v1",
        operation_contract_ref=operation.ref,
        operation_contract_digest=operation.ref.contract_digest,
        return_contract_binding=return_binding,
        compiled_admission_binding=compiled,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{interpreter.binding_digest}",
        handler_binding_digest=interpreter.binding_digest,
        handler_binding=interpreter,
        program_digest=_digest("delivery-program"),
        plan_digest=plan_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=0,
        incarnation="run-inc:delivery",
        input_refs=("project-value:qualification:p0c:support",),
        input_closure_digest=_digest("p0c-cw09-input-closure"),
        payload_ref="project-value:claim:p0c:cw09",
        payload_digest=claim.content_digest,
        queue_eligibility_digest=_digest("p0c-cw09-eligibility"),
        resource_policy_epoch=1,
        claim_authority_epoch=1,
        claim_policy_digest=_digest("p0c-cw09-claim-policy"),
        expected_step_revision=0,
        trace_id="trace:p0c:cw09",
    )
    events = (
        {
            "schema_version": "mrw.runtime.event.claim-admitted.v1",
            "claim_ref": claim.claim_id,
        },
    )
    binding = VerificationBinding.from_content(
        program_digest=assignment.program_digest,
        plan_digest=plan_digest,
        step_id=assignment.step_id,
        attempt_id=_digest("p0c-cw09-attempt"),
        input_closure_digest=assignment.input_closure_digest,
        output_content_digest=claim.content_digest,
        ordered_event_payloads=events,
        schema_digest=_digest("p0c-cw09-schema"),
        compiler_identity="mrw.functorial-successor.compiler@1.0.0",
        interpreter_identity="successor-native.claim-admission@1.0.0",
        verifier_identity="p0c-exact-verifier@1.0.0",
        actor_id=p0c_database.scope.actor_id,
        project_key=PROJECT_KEY,
        authority_digest=DELIVERY_AUTHORITY_DIGEST,
        project_registry_revision=PROJECT_REGISTRY_REVISION,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
        resolved_schema=PROJECT_SCHEMA,
        canonical_owner="ResearchLedger",
        canonical_object_id=claim.claim_id,
        canonical_base_revision=0,
        canonical_incarnation=claim_ref.incarnation,
        evidence_digest=_digest("p0c-cw09-evidence"),
        receipt_digest=_digest("p0c-cw09-verification-receipt"),
        provenance_digest=claim_ref.provenance_closure_digest,
        qualifier="STANDARD",
    )
    intent = CommitIntent(
        commit_intent_id="commit-intent:p0c:cw09",
        canonical_owner="ResearchLedger",
        project_key=PROJECT_KEY,
        object_id=claim.claim_id,
        project_registry_revision=PROJECT_REGISTRY_REVISION,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
        expected_base_revision=0,
        expected_incarnation=claim_ref.incarnation,
        content_digest=claim.content_digest,
        ordered_event_closure_digest=binding.ordered_event_payload_closure_digest,
        verification_binding_digest=binding.binding_digest,
        authority_digest=DELIVERY_AUTHORITY_DIGEST,
        idempotency_key="admission:p0c:cw09",
    )
    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_steps"]).values(
                project_key=PROJECT_KEY,
                run_id="run:delivery",
                step_id=assignment.step_id,
                operation_id="claim.form_or_open_gap",
                operation_kind=operation.ref.kind,
                operation_version=operation.ref.contract_version,
                state="READY",
                revision=0,
                execution_epoch=0,
                input_digest=assignment.input_closure_digest,
                effect_class="ADMISSION",
                resource_class="CPU_LIGHT",
                concurrency_key="p0c:cw09",
                capability_id=assignment.capability_id,
                claim_owner="successor",
                claim_authority_epoch=1,
                claim_policy_digest=assignment.claim_policy_digest,
                attempt_count=0,
                max_attempts=1,
            )
        )

    connection = p0c_database.engine.connect()
    handler = ResearchAdmissionHandler(
        connection=connection,
        tables=p0c_database.project_tables,
        operation_contract_ref=operation.ref,
        mode=ResearchAdmissionMode.CLAIM_OR_GAP_OBJECT,
    )
    registry = ExactAdmissionRegistry((AdmissionRegistration(operation.ref, handler),))
    coordinator = AdmissionCoordinator(
        registry=registry,
        commit_intents=PostgresCommitIntentAdapter(
            CommitIntentRepository(connection, p0c_database.scope)
        ),
        commit_binding_factory=commit_binding_from_assignment,
    )
    transaction = connection.begin()
    prepared = coordinator.prepare(
        scope=p0c_database.scope,
        assignment=assignment,
        intent=intent,
        candidate=candidate,
        binding=binding,
        current_authority_digest=DELIVERY_AUTHORITY_DIGEST,
        current_base_revision=0,
        current_incarnation=claim_ref.incarnation,
        ordered_event_payloads=events,
    )
    transaction.commit()

    transaction = connection.begin()
    canonical = coordinator.commit_prepared(prepared)
    assert canonical.progress is AdmissionProgress.CANONICAL_COMMITTED
    transaction.commit()
    connection.close()

    # Crash boundary: canonical row exists, while commit-intent finalization and
    # runtime recovery event have not happened.
    with p0c_database.engine.connect() as check:
        state = check.scalar(
            sa.select(PUBLIC_TABLES["runtime_commit_intents"].c.state)
        )
        assert state == "PREPARED"
        assert check.scalar(
            sa.select(sa.func.count()).select_from(
                p0c_database.project_tables.research_objects
            ).where(
                p0c_database.project_tables.research_objects.c.object_id
                == claim.claim_id
            )
        ) == 1
    p0c_database.engine.dispose()

    with p0c_database.engine.begin() as connection:
        recovered_handler = ResearchAdmissionHandler(
            connection=connection,
            tables=p0c_database.project_tables,
            operation_contract_ref=operation.ref,
            mode=ResearchAdmissionMode.CLAIM_OR_GAP_OBJECT,
        )
        recovered_registry = ExactAdmissionRegistry(
            (AdmissionRegistration(operation.ref, recovered_handler),)
        )
        recovered_coordinator = AdmissionCoordinator(
            registry=recovered_registry,
            commit_intents=PostgresCommitIntentAdapter(
                CommitIntentRepository(connection, p0c_database.scope)
            ),
            commit_binding_factory=commit_binding_from_assignment,
        )
        rebound = replace(
            prepared,
            registration=recovered_registry.resolve_required(operation.ref),
        )
        recovered = recovered_coordinator.recover(rebound)
        assert recovered.progress is AdmissionProgress.FINALIZED
        RuntimeJournalRepository(
            connection, p0c_database.scope
        ).append_transition(
            run_id="run:delivery",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(
                {
                    "event_type": "CanonicalCommitRecovered",
                    "schema_version": "mrw.runtime.event.commit-recovered.v1",
                    "event_metadata_json": {"claim_ref": claim.claim_id},
                    "payload_ref": f"canonical:research-object:{claim.claim_id}:1",
                    "payload_digest": claim.content_digest,
                    "authority_digest": DELIVERY_AUTHORITY_DIGEST,
                },
            ),
        )

    with p0c_database.engine.connect() as check:
        assert check.scalar(
            sa.select(sa.func.count()).select_from(
                p0c_database.project_tables.research_objects
            ).where(
                p0c_database.project_tables.research_objects.c.object_id
                == claim.claim_id
            )
        ) == 1
        assert check.scalar(
            sa.select(PUBLIC_TABLES["runtime_commit_intents"].c.state)
        ) == "COMMITTED"
        assert check.scalar(
            sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_events"])
        ) == 1
