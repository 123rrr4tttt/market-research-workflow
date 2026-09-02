"""Focused first-specimen recovery-handler acceptance tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    HandlerBindingKind,
    RecoveryBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.blob.internal_export import (
    InternalExportInterpreter,
    InternalExportReadbackFacade,
)
from app.successor_runtime.substrate.postgres.first_specimen_reconciliation_handler import (
    FirstSpecimenReconciliationError,
    InstalledFirstSpecimenReconciliationHandler,
    PostgresFirstSpecimenReconciliationHandler,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    AssignmentEnvelope,
    _assignment_values,
)

from .test_p0c_first_specimen_delivery_handler import (
    NOW,
    _assignment,
    _CountingBlobStore,
    _digest,
    _Replay,
    _replay,
    _Uow,
)
from .test_p0c_first_specimen_delivery_handler import (
    delivery_db as delivery_db_fixture,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def reconciliation_db():
    """Reuse the delivery unit database without widening its production scope."""

    yield from delivery_db_fixture.__wrapped__()


def _recovery(original: RuntimeAssignment) -> RecoveryBinding:
    profile = original.handler_binding.interpreter_profile_digest  # type: ignore[union-attr]
    return RecoveryBinding.from_content(
        recovery_handler_id="mrw.p0c.internal-export.readback",
        recovery_handler_version="1.0.0",
        interpreter_profile_digest=profile,
        authoritative_readback_profile_ref="internal-export-idempotency.v1",
    )


def _reconcile_assignment(
    original: RuntimeAssignment,
    original_claim: ClaimBinding,
    recovery: RecoveryBinding,
) -> RuntimeAssignment:
    values = original.model_dump(mode="python")
    values.update(
        work_item_id=f"reconcile:{original_claim.attempt_id}",
        assignment_kind=AssignmentKind.RECONCILE,
        handler_binding_kind=HandlerBindingKind.RECOVERY,
        handler_binding_ref=(f"handler-binding:sha256:{recovery.binding_digest}"),
        handler_binding_digest=recovery.binding_digest,
        handler_binding=recovery,
        expected_step_revision=(original.expected_step_revision or 0) + 1,
        reconciliation_attempt_id=original_claim.attempt_id,
    )
    return RuntimeAssignment(**values)


def _seed_original(
    connection: sa.Connection,
    original: RuntimeAssignment,
    original_claim: ClaimBinding,
    recovery: RecoveryBinding,
) -> None:
    envelope = AssignmentEnvelope(
        assignment=original,
        required_node_profile_selector="node-profile:p0c",
        authority_digest=original_claim.authorization_digest,
        resource_policy_digest=_digest("resource-policy"),
        fairness_key="p0c:delivery",
        qualification_digest=_digest("qualification"),
        resource_class="filesystem",
        resource_units=1,
        concurrency_key="project:alpha:delivery",
        provider_key="internal-export",
        recovery_binding=recovery,
        authoritative_readback_profile_ref=(
            recovery.authoritative_readback_profile_ref
        ),
        delivery_intent_ref="delivery-intent:first-specimen",
    )
    work_values = _assignment_values(envelope, due_at=NOW)
    work_values.update(
        state="WAITING",
        wait_reason="BACKOFF",
        enqueue_seq=1,
        created_at=NOW,
        updated_at=NOW,
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(**work_values)
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_effect_attempts"]).values(
            attempt_id=original_claim.attempt_id,
            project_key=original.project_key,
            run_id=original.run_id,
            step_id=original.step_id,
            execution_epoch=original.execution_epoch,
            incarnation=original.incarnation,
            assignment_digest=original.assignment_digest,
            handler_binding_digest=original.handler_binding_digest,
            handler_realization_digest=original.handler_binding_digest,
            idempotency_key=f"attempt:{original_claim.attempt_id}",
            authorization_digest=original_claim.authorization_digest,
            input_digest=original.input_closure_digest,
            claim_binding_json=original_claim.model_dump(mode="json"),
            claim_binding_digest=original_claim.binding_digest,
            delivery_intent_ref="delivery-intent:first-specimen",
            disposition=EffectDisposition.OUTCOME_UNKNOWN.value,
            revision=2,
            dispatched_at=NOW - timedelta(minutes=2),
            started_at=NOW - timedelta(minutes=2),
            created_at=NOW - timedelta(minutes=2),
            updated_at=NOW,
        )
    )
    connection.commit()


def _setup(reconciliation_db, tmp_path):
    connection, tables, scope = reconciliation_db
    PUBLIC_TABLES["runtime_work_items"].create(connection, checkfirst=True)
    PUBLIC_TABLES["runtime_effect_attempts"].create(connection, checkfirst=True)
    connection.commit()
    _, original, original_claim, context = _assignment()
    recovery = _recovery(original)
    reconciliation = _reconcile_assignment(original, original_claim, recovery)
    reconcile_claim = ClaimBinding.bind(
        reconciliation,
        authorization_digest=original_claim.authorization_digest,
        lease_token="lease:reconciliation",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id=context.node.node_id,
        node_profile_digest=original_claim.node_profile_digest,
        interpreter_profile_digest=recovery.interpreter_profile_digest,
        authority_digest=original_claim.authority_digest,
    )
    replay, _ = _replay(scope, tables, original)
    replay = replace(
        replay,
        request=replace(
            replay.request,
            attempt_id=original_claim.attempt_id,
            assignment_digest=original.assignment_digest,
        ),
    )
    _seed_original(connection, original, original_claim, recovery)
    blob = _CountingBlobStore(tmp_path)
    writer = InternalExportInterpreter(
        operation_contract_ref=original.operation_contract_ref,
        blob_store=blob,
    )
    readback = InternalExportReadbackFacade(
        operation_contract_ref=original.operation_contract_ref,
        blob_store=blob,
    )
    handler = PostgresFirstSpecimenReconciliationHandler(
        InstalledFirstSpecimenReconciliationHandler(
            recovery_binding=recovery,
            operation_contract_digest=original.operation_contract_digest,
        ),
        lambda: _Uow(connection),
        readback=readback,
        delivery_replay=_Replay(replay),  # type: ignore[arg-type]
    )
    return (
        connection,
        tables,
        original,
        original_claim,
        context,
        recovery,
        reconciliation,
        reconcile_claim,
        replay,
        blob,
        writer,
        handler,
    )


def test_waiting_is_typed_and_never_dispatches_or_persists(
    reconciliation_db, tmp_path
) -> None:
    (
        connection,
        tables,
        _,
        _,
        context,
        _,
        reconciliation,
        reconcile_claim,
        _,
        blob,
        _,
        handler,
    ) = _setup(reconciliation_db, tmp_path)

    outcome = handler.execute(reconciliation, reconcile_claim, context)

    assert outcome.result.state is ReconciliationState.WAITING
    assert outcome.result.disposition is EffectDisposition.OUTCOME_UNKNOWN
    assert outcome.output_digest is None
    assert outcome.receipt_ref is None
    assert not hasattr(InternalExportReadbackFacade, "execute")
    assert blob.store_calls == 0
    assert (
        connection.scalar(
            sa.select(sa.func.count()).select_from(tables.successor_values)
        )
        == 0
    )


def test_authoritative_success_rebuilds_exact_candidate_idempotently_without_redispatch(
    reconciliation_db, tmp_path
) -> None:
    (
        connection,
        tables,
        _,
        original_claim,
        context,
        _,
        reconciliation,
        reconcile_claim,
        replay,
        blob,
        writer,
        handler,
    ) = _setup(reconciliation_db, tmp_path)
    writer._ensure_prepared(replay.request, NOW)
    blob.store(replay.request.project_scope_digest, replay.request.artifact_bytes)
    assert blob.store_calls == 1

    first = handler.execute(reconciliation, reconcile_claim, context)
    second = handler.execute(reconciliation, reconcile_claim, context)

    assert first == second
    assert first.result.state is ReconciliationState.RESOLVED
    assert first.result.disposition is EffectDisposition.SUCCEEDED
    assert first.output_digest is not None
    assert first.receipt_ref is not None
    assert blob.store_calls == 1
    project_rows = (
        connection.execute(sa.select(tables.successor_values)).mappings().all()
    )
    assert len(project_rows) == 2
    staged = (
        connection.execute(sa.select(PUBLIC_TABLES["runtime_staged_artifacts"]))
        .mappings()
        .one()
    )
    assert staged["attempt_id"] == original_claim.attempt_id
    assert staged["receipt_ref"] == first.receipt_ref


class _FailedReadback:
    interpreter_id = InternalExportReadbackFacade.interpreter_id
    interpreter_version = InternalExportReadbackFacade.interpreter_version
    provider_id = InternalExportReadbackFacade.provider_id
    provider_version = InternalExportReadbackFacade.provider_version

    def __init__(self, operation_contract_ref) -> None:
        self.operation_contract_ref = operation_contract_ref

    @staticmethod
    def readback_locator(request) -> str:
        key = _digest(request.delivery_intent.idempotency_key)
        return f"internal-export-index:{request.project_scope_digest}:{key}"

    @staticmethod
    def readback_exact(request) -> AuthoritativeEffectReadback:
        failure = _digest("authoritative-provider-failure")
        return AuthoritativeEffectReadback(
            attempt_id=request.attempt_id,
            disposition=EffectDisposition.FAILED,
            failure_digest=failure,
            observation_digest=canonical_digest(
                {"attempt_id": request.attempt_id, "failure_digest": failure}
            ),
            reason="AUTHORITATIVE_PROVIDER_FAILURE",
        )


def test_authoritative_failure_binds_failure_digest_and_profile_drift_fails_closed(
    reconciliation_db, tmp_path
) -> None:
    (
        connection,
        tables,
        original,
        _,
        context,
        recovery,
        reconciliation,
        reconcile_claim,
        replay,
        _,
        _,
        _,
    ) = _setup(reconciliation_db, tmp_path)
    failed = _FailedReadback(original.operation_contract_ref)
    handler = PostgresFirstSpecimenReconciliationHandler(
        InstalledFirstSpecimenReconciliationHandler(
            recovery_binding=recovery,
            operation_contract_digest=original.operation_contract_digest,
        ),
        lambda: _Uow(connection),
        readback=failed,
        delivery_replay=_Replay(replay),  # type: ignore[arg-type]
    )

    outcome = handler.execute(reconciliation, reconcile_claim, context)
    assert outcome.result.state is ReconciliationState.RESOLVED
    assert outcome.result.disposition is EffectDisposition.FAILED
    assert outcome.result.readback is not None
    assert outcome.result.readback.failure_digest == _digest(
        "authoritative-provider-failure"
    )
    assert outcome.output_digest is None
    assert outcome.receipt_ref is None
    assert (
        connection.scalar(
            sa.select(sa.func.count()).select_from(tables.successor_values)
        )
        == 0
    )

    drifted = RecoveryBinding.from_content(
        recovery_handler_id=recovery.recovery_handler_id,
        recovery_handler_version="2.0.0",
        interpreter_profile_digest=recovery.interpreter_profile_digest,
        authoritative_readback_profile_ref=(
            recovery.authoritative_readback_profile_ref
        ),
    )
    drifted_assignment = _reconcile_assignment(
        original,
        ClaimBinding.model_validate(
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"].c.claim_binding_json)
            ).scalar_one()
        ),
        drifted,
    )
    drifted_claim = ClaimBinding.bind(
        drifted_assignment,
        authorization_digest=reconcile_claim.authorization_digest,
        lease_token="lease:drifted-reconciliation",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id=context.node.node_id,
        node_profile_digest=reconcile_claim.node_profile_digest,
        interpreter_profile_digest=drifted.interpreter_profile_digest,
        authority_digest=reconcile_claim.authority_digest,
    )
    with pytest.raises(FirstSpecimenReconciliationError, match="RecoveryBinding"):
        handler.execute(drifted_assignment, drifted_claim, context)
