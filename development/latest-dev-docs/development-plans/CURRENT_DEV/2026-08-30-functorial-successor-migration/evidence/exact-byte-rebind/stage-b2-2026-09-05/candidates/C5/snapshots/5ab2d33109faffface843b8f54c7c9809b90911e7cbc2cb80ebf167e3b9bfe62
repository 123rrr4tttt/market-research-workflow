"""C5.2 legacy attempt replay and exact reconciliation acceptance."""

from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa
from app.successor_migration.legacy_effect_attempts import (
    ContradictoryAttemptReplay,
    ExactLegacyAttemptBinding,
    IncompleteLegacyAttemptRecord,
    LegacyAttemptBindingMismatch,
    LegacyInterpreterProfile,
    replay_effect_attempt,
    replay_legacy_attempts,
    require_exact_adoption,
)
from app.successor_runtime.runtime.assignments import RecoveryBinding
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import RuntimeClaim
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    EffectReconciler,
    ReconciliationHandlerOutcome,
    ReconciliationResult,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres import (
    reconciliation as postgres_reconciliation,
)
from app.successor_runtime.substrate.postgres.reconciliation import (
    PostgresReconciliationOwner,
    ReconciliationAdoptionError,
)

from . import test_p0c_postgres_reconciliation as owner_test

AUTHORIZATION_DIGEST = owner_test._digest("authorization")


def _recovery_and_profile() -> tuple[RecoveryBinding, LegacyInterpreterProfile]:
    profile = LegacyInterpreterProfile.from_content(
        interpreter_id="legacy.interpreter",
        interpreter_version="1.0.0",
        provider_id="provider.legacy",
        provider_version="2.0.0",
    )
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="authoritative-readback",
        recovery_handler_version="1",
        interpreter_profile_digest=profile.profile_digest,
        authoritative_readback_profile_ref="readback-profile:1",
    )
    return recovery, profile


def _effect_assignment(recovery: RecoveryBinding):
    return owner_test._effect_assignment(recovery)


def _derived_binding(
    original,
    *,
    call_id: str = "call-1",
    idempotency: str = "idem-1",
    locator: str = "provider:receipt",
) -> ExactLegacyAttemptBinding:
    return ExactLegacyAttemptBinding.from_derived_attempt(
        original,
        authorization_digest=AUTHORIZATION_DIGEST,
        call_id=call_id,
        external_idempotency_key=idempotency,
        authoritative_readback_locator=locator,
        capability_id=original.capability_id,
    )


@pytest.fixture
def replayed_adoption_store(monkeypatch: pytest.MonkeyPatch):
    tables = owner_test._tables()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    next(iter(tables.values())).metadata.create_all(engine)
    monkeypatch.setattr(postgres_reconciliation, "_table", tables.__getitem__)

    recovery, profile = _recovery_and_profile()
    original = _effect_assignment(recovery)
    original_claim = ClaimBinding.bind(
        original,
        authorization_digest=AUTHORIZATION_DIGEST,
        lease_token="lease-original",
        lease_expires_at=owner_test.NOW + timedelta(minutes=1),
        node_id="node-previous",
        node_profile_digest=owner_test._digest("old-node-profile"),
        authority_digest=AUTHORIZATION_DIGEST,
        interpreter_profile_digest=recovery.interpreter_profile_digest,
        execution_reservation_ref="reservation:original",
        execution_reservation_digest=owner_test._digest("reservation"),
    )
    target_attempt_id = original_claim.attempt_id
    assignment = owner_test._recovery_assignment(original, recovery, target_attempt_id)
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=AUTHORIZATION_DIGEST,
        lease_token="lease-reconcile",
        lease_expires_at=owner_test.NOW + timedelta(minutes=2),
        node_id="runtime-node",
        node_profile_digest=owner_test._digest("node-profile"),
        authority_digest=AUTHORIZATION_DIGEST,
        interpreter_profile_digest=recovery.interpreter_profile_digest,
    )
    runtime_claim = RuntimeClaim(
        assignment=assignment,
        claim_binding=claim,
        work_item_revision=2,
    )
    with engine.begin() as connection:
        connection.execute(
            tables["runtime_runs"]
            .insert()
            .values(
                project_key="project-1",
                run_id="run-1",
                incarnation="run-incarnation-1",
                program_digest=owner_test._digest("program"),
                execution_epoch=1,
                state="RECONCILING",
                revision=7,
                next_event_seq=10,
                updated_at=owner_test.NOW,
            )
        )
        connection.execute(
            tables["runtime_steps"]
            .insert()
            .values(
                project_key="project-1",
                run_id="run-1",
                step_id="step-1",
                state="RECONCILING",
                revision=5,
                execution_epoch=1,
                input_digest=owner_test._digest("input"),
                lease_token=claim.lease_token,
                lease_owner=claim.node_id,
                lease_expires_at=claim.lease_expires_at,
                updated_at=owner_test.NOW,
            )
        )
        connection.execute(
            tables["runtime_work_items"].insert(),
            [
                owner_test._work_values(
                    original,
                    state="COMPLETED",
                    revision=4,
                    claim=original_claim,
                    recovery=recovery,
                ),
                owner_test._work_values(
                    assignment,
                    state="CLAIMED",
                    revision=2,
                    claim=claim,
                    recovery=recovery,
                ),
            ],
        )
        connection.execute(
            tables["runtime_effect_attempts"]
            .insert()
            .values(
                project_key="project-1",
                attempt_id=target_attempt_id,
                run_id="run-1",
                step_id="step-1",
                assignment_digest=original.assignment_digest,
                handler_binding_digest=original.handler_binding_digest,
                claim_binding_json=original_claim.model_dump(mode="json"),
                claim_binding_digest=original_claim.binding_digest,
                disposition="OUTCOME_UNKNOWN",
                revision=3,
                updated_at=owner_test.NOW,
            )
        )
    return engine, tables, runtime_claim, original, original_claim, recovery, profile


def _record(
    *,
    call_id: str = "call-1",
    idempotency: str = "idem-1",
    locator: str = "provider:receipt",
    status: str | None = "",
    capability: str | None = None,
) -> dict[str, object]:
    return {
        "call_id": call_id,
        "idempotency_key": idempotency,
        "authoritative_readback_locator": locator,
        "capability_id": capability,
        "status": status,
    }


def test_legacy_record_replays_to_exact_attempt_observation() -> None:
    recovery, profile = _recovery_and_profile()
    original = _effect_assignment(recovery)
    now = owner_test.NOW + timedelta(seconds=1)

    started_binding = _derived_binding(original)
    started = replay_effect_attempt(
        _record(),
        assignment=original,
        recovery=recovery,
        profile=profile,
        binding=started_binding,
        observed_at=now,
    ).observation
    succeeded_binding = _derived_binding(
        original,
        call_id="call-2",
        idempotency="idem-2",
    )
    succeeded = replay_effect_attempt(
        _record(call_id="call-2", idempotency="idem-2", status="success"),
        assignment=original,
        recovery=recovery,
        profile=profile,
        binding=succeeded_binding,
        observed_at=now,
    ).observation
    failed_binding = _derived_binding(
        original,
        call_id="call-3",
        idempotency="idem-3",
    )
    failed = replay_effect_attempt(
        _record(call_id="call-3", idempotency="idem-3", status="failure"),
        assignment=original,
        recovery=recovery,
        profile=profile,
        binding=failed_binding,
        observed_at=now,
    ).observation

    assert started.assignment_digest == original.assignment_digest
    assert started.handler_binding_digest == original.handler_binding_digest
    assert (
        started.interpreter_profile_digest
        == recovery.interpreter_profile_digest
        == profile.profile_digest
    )
    assert started.attempt_id == started_binding.attempt_id
    assert started.disposition is EffectDisposition.OUTCOME_UNKNOWN
    assert succeeded.disposition is EffectDisposition.SUCCEEDED
    assert failed.disposition is EffectDisposition.FAILED
    assert started.external_idempotency_key == "idem-1"
    assert started.authoritative_readback_locator == "provider:receipt"


def test_missing_result_never_becomes_not_started() -> None:
    recovery, profile = _recovery_and_profile()
    original = _effect_assignment(recovery)
    binding = _derived_binding(original, call_id="call-missing")
    evidence = replay_effect_attempt(
        _record(call_id="call-missing", status=""),
        assignment=original,
        recovery=recovery,
        profile=profile,
        binding=binding,
        observed_at=owner_test.NOW,
    )
    assert evidence.observation.disposition is EffectDisposition.OUTCOME_UNKNOWN
    assert evidence.binding.binding_digest == binding.binding_digest


@pytest.mark.parametrize(
    ("record_overrides", "binding_overrides", "error"),
    [
        (
            {"call_id": "call-unrelated"},
            {},
            LegacyAttemptBindingMismatch,
        ),
        (
            {"idempotency": "idem-wrong"},
            {},
            LegacyAttemptBindingMismatch,
        ),
        (
            {"locator": "provider:wrong"},
            {},
            LegacyAttemptBindingMismatch,
        ),
        (
            {"capability": "mrw.wrong.capability"},
            {},
            LegacyAttemptBindingMismatch,
        ),
        (
            {},
            {"call_id": "call-bound-different"},
            LegacyAttemptBindingMismatch,
        ),
    ],
)
def test_durable_binding_mismatches_fail_closed(
    record_overrides: dict[str, object],
    binding_overrides: dict[str, str],
    error: type[Exception],
) -> None:
    recovery, profile = _recovery_and_profile()
    original = _effect_assignment(recovery)
    binding = _derived_binding(
        original,
        call_id=binding_overrides.get("call_id", "call-1"),
        idempotency=binding_overrides.get("idempotency", "idem-1"),
        locator=binding_overrides.get("locator", "provider:receipt"),
    )
    record = _record(**record_overrides)
    with pytest.raises(error):
        replay_effect_attempt(
            record,
            assignment=original,
            recovery=recovery,
            profile=profile,
            binding=binding,
            observed_at=owner_test.NOW,
        )


def test_contradictory_and_incomplete_records_fail_closed() -> None:
    recovery, profile = _recovery_and_profile()
    original = _effect_assignment(recovery)
    binding = _derived_binding(original)
    with pytest.raises(ContradictoryAttemptReplay):
        replay_legacy_attempts(
            [
                _record(status="success"),
                _record(status="failure"),
            ],
            [binding, binding],
            assignment=original,
            recovery=recovery,
            profile=profile,
            observed_at=owner_test.NOW,
        )
    with pytest.raises(IncompleteLegacyAttemptRecord):
        replay_effect_attempt(
            {"status": "success"},
            assignment=original,
            recovery=recovery,
            profile=profile,
            binding=binding,
            observed_at=owner_test.NOW,
        )


def test_existing_effect_reconciler_resolves_replayed_attempt() -> None:
    recovery, profile = _recovery_and_profile()
    original = _effect_assignment(recovery)
    binding = _derived_binding(
        original,
        call_id="call-reconcile",
        idempotency="idem-reconcile",
    )
    evidence = replay_effect_attempt(
        _record(
            call_id="call-reconcile",
            idempotency="idem-reconcile",
            status="",
        ),
        assignment=original,
        recovery=recovery,
        profile=profile,
        binding=binding,
        observed_at=owner_test.NOW,
    )
    attempt = evidence.observation
    assignment = owner_test._recovery_assignment(
        original,
        recovery,
        attempt.attempt_id,
    )
    readback = AuthoritativeEffectReadback(
        attempt_id=attempt.attempt_id,
        disposition=EffectDisposition.SUCCEEDED,
        provider_locator=binding.authoritative_readback_locator,
        receipt_digest=owner_test._digest("receipt"),
        observation_digest=owner_test._digest("observation"),
    )

    class _Stub:
        interpreter_id = profile.interpreter_id
        interpreter_version = profile.interpreter_version
        provider_id = profile.provider_id
        provider_version = profile.provider_version

        def readback(self, _attempt: object) -> AuthoritativeEffectReadback:
            return readback

        def prove_not_started(self, _attempt: object) -> object:
            return None

    result = EffectReconciler().reconcile(
        assignment=assignment,
        attempt=attempt,
        interpreter=_Stub(),
    )
    assert result.state is ReconciliationState.RESOLVED
    assert result.disposition is EffectDisposition.SUCCEEDED
    assert result.readback == readback


def test_existing_owner_adopts_replayed_attempt_readback_once(
    replayed_adoption_store,
) -> None:
    engine, tables, runtime_claim, original, original_claim, recovery, profile = (
        replayed_adoption_store
    )
    binding = ExactLegacyAttemptBinding.from_claim(
        original_claim,
        call_id="call-owner",
        external_idempotency_key="idem-owner",
        authoritative_readback_locator="provider:receipt",
        capability_id=original.capability_id,
    )
    evidence = replay_effect_attempt(
        _record(
            call_id="call-owner",
            idempotency="idem-owner",
            locator="provider:receipt",
            status="",
        ),
        assignment=original,
        recovery=recovery,
        profile=profile,
        binding=binding,
        observed_at=owner_test.NOW + timedelta(seconds=1),
    )
    attempt = evidence.observation
    assert attempt.attempt_id == original_claim.attempt_id
    readback = AuthoritativeEffectReadback(
        attempt_id=attempt.attempt_id,
        disposition=EffectDisposition.SUCCEEDED,
        provider_locator=binding.authoritative_readback_locator,
        receipt_digest=owner_test._digest("receipt"),
        observation_digest=owner_test._digest("observation"),
    )
    require_exact_adoption(
        binding,
        claim=original_claim,
        assignment=original,
        readback=readback,
    )
    outcome = ReconciliationHandlerOutcome(
        result=ReconciliationResult(
            state=ReconciliationState.RESOLVED,
            attempt_id=attempt.attempt_id,
            disposition=EffectDisposition.SUCCEEDED,
            readback=readback,
        ),
        output_digest=owner_test._digest("output"),
        receipt_ref="receipt:authoritative",
    )
    with engine.begin() as connection:
        owner = PostgresReconciliationOwner(
            connection,
            terminal_authority=owner_test._AllowCurrentTerminalAuthority(),
            failure_policy=owner_test._StaticFailurePolicy(required=True),
        )
        owner.adopt(
            claim=runtime_claim,
            outcome=outcome,
            actor_id="runtime-node",
            observed_at=owner_test.NOW + timedelta(seconds=1),
        )
        with pytest.raises(ReconciliationAdoptionError):
            owner.adopt(
                claim=runtime_claim,
                outcome=outcome,
                actor_id="runtime-node",
                observed_at=owner_test.NOW + timedelta(seconds=2),
            )

    with engine.connect() as connection:
        attempt_row = (
            connection.execute(
                sa.select(tables["runtime_effect_attempts"]).where(
                    tables["runtime_effect_attempts"].c.attempt_id == attempt.attempt_id
                )
            )
            .mappings()
            .one()
        )
        events = (
            connection.execute(
                sa.select(tables["runtime_events"]).order_by(
                    tables["runtime_events"].c.seq
                )
            )
            .mappings()
            .all()
        )
    assert attempt_row["disposition"] == EffectDisposition.SUCCEEDED.value
    assert events[0]["event_type"] == "AuthoritativeReadbackSucceeded"
    assert events[0]["event_metadata_json"]["observation_digest"] == owner_test._digest(
        "observation"
    )
