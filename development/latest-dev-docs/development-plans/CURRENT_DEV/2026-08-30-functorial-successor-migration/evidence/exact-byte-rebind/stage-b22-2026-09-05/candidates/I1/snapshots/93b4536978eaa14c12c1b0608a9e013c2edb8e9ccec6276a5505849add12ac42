"""C7.4 readback and non-start reconciliation using shared runtime contracts."""

from __future__ import annotations

from typing import Any

import pytest

from app.successor_migration.ingest_recovery_c7 import (
    C7ReconciliationError,
    C7ReconciliationPolicy,
    prove_non_start_with_shared_reconciler,
    reconcile_with_shared_reconciler,
)
from app.successor_runtime.runtime.assignments import canonical_digest
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    ReconciliationState,
)
from app.successor_runtime.runtime.recovery import NonStartProof
from app.successor_runtime.runtime.transitions import EffectDisposition
from tests.successor_runtime.p4_c7_fixture import (
    AUTHORITY_DIGEST,
    NOW,
    effect_assignment,
    effect_attempt_observation,
    recovery_assignment,
    recovery_binding,
)


class C7ReadbackInterpreter:
    interpreter_id = "legacy.ingest_index.postprocess.replay.v1"
    interpreter_version = "1.0.0"
    provider_id = "provider.ingest.fixture"
    provider_version = "1.0.0"

    def __init__(
        self,
        *,
        profile_digest: str,
        disposition: EffectDisposition,
    ) -> None:
        self.profile_digest = profile_digest
        self.disposition = disposition

    def readback(self, attempt: Any) -> AuthoritativeEffectReadback:
        receipt = canonical_digest({"receipt": "c7-readback"})
        failure = canonical_digest({"failure": "c7-readback"})
        return AuthoritativeEffectReadback(
            attempt_id=attempt.attempt_id,
            disposition=self.disposition,
            provider_locator=attempt.authoritative_readback_locator,
            receipt_digest=receipt
            if self.disposition is EffectDisposition.SUCCEEDED
            else None,
            failure_digest=failure
            if self.disposition is EffectDisposition.FAILED
            else None,
            observation_digest=canonical_digest(
                {"attempt": attempt.attempt_id, "disposition": self.disposition.value}
            ),
        )

    def prove_not_started(self, attempt: Any) -> NonStartProof:
        values = {
            "attempt_id": attempt.attempt_id,
            "interpreter_id": self.interpreter_id,
            "interpreter_version": self.interpreter_version,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "external_idempotency_key": attempt.external_idempotency_key,
            "authoritative_readback_locator": attempt.authoritative_readback_locator,
            "authoritative_observation_digest": canonical_digest(
                {"nonstart": attempt.attempt_id}
            ),
        }
        provisional = NonStartProof.model_construct(
            **values,
            observed_at=NOW,
            proof_digest="0" * 64,
        )
        return NonStartProof(
            **values,
            observed_at=NOW,
            proof_digest=canonical_digest(
                provisional,
                exclude_fields={"proof_digest"},
            ),
        )


def _recovery_context(
    *,
    disposition: EffectDisposition = EffectDisposition.OUTCOME_UNKNOWN,
) -> tuple[Any, Any, Any, Any, Any]:
    recovery = recovery_binding()
    original = effect_assignment(recovery)
    from app.successor_runtime.capabilities.checksum import content_digest

    attempt_id = content_digest({"attempt": "p4-c7:001"})
    reconcile = recovery_assignment(original, recovery, attempt_id)
    attempt = effect_attempt_observation(original, attempt_id=attempt_id)
    interpreter = C7ReadbackInterpreter(
        profile_digest=recovery.interpreter_profile_digest,
        disposition=disposition,
    )
    return recovery, original, reconcile, attempt, interpreter


def test_terminal_readback_never_starts_new_attempt() -> None:
    _recovery, _original, reconcile, attempt, interpreter = _recovery_context(
        disposition=EffectDisposition.SUCCEEDED
    )
    result = reconcile_with_shared_reconciler(
        assignment=reconcile,
        attempt=attempt,
        interpreter=interpreter,
    )
    assert result.state is ReconciliationState.RESOLVED
    assert result.disposition is EffectDisposition.SUCCEEDED
    decision = C7ReconciliationPolicy().terminal_decision(result.disposition)
    assert decision.new_attempt_allowed is False
    assert decision.requirement == "terminal_readback_is_final"


def test_exact_nonstart_proof_with_current_authority_allows_new_epoch() -> None:
    _recovery, _original, reconcile, attempt, interpreter = _recovery_context()
    result = prove_non_start_with_shared_reconciler(
        assignment=reconcile,
        attempt=attempt,
        interpreter=interpreter,
    )
    assert result.state is ReconciliationState.NOT_STARTED_PROVEN
    decision = C7ReconciliationPolicy().authorize_new_epoch(
        attempt_id=attempt.attempt_id,
        proof=result.non_start_proof,
        current_authority_digest=AUTHORITY_DIGEST,
        expected_authority_digest=AUTHORITY_DIGEST,
        next_epoch=2,
        prior_epoch=1,
    )
    assert decision.new_attempt_allowed is True
    assert decision.requirement == "exact_nonstart_proof_and_current_authority"


def test_authority_mismatch_fails_closed() -> None:
    _recovery, _original, reconcile, attempt, interpreter = _recovery_context()
    result = prove_non_start_with_shared_reconciler(
        assignment=reconcile,
        attempt=attempt,
        interpreter=interpreter,
    )
    with pytest.raises(C7ReconciliationError, match="authority"):
        C7ReconciliationPolicy().authorize_new_epoch(
            attempt_id=attempt.attempt_id,
            proof=result.non_start_proof,
            current_authority_digest=canonical_digest({"authority": "drifted"}),
            expected_authority_digest=AUTHORITY_DIGEST,
            next_epoch=2,
            prior_epoch=1,
        )


def test_non_advancing_epoch_and_attempt_mismatch_fail_closed() -> None:
    _recovery, _original, reconcile, attempt, interpreter = _recovery_context()
    result = prove_non_start_with_shared_reconciler(
        assignment=reconcile,
        attempt=attempt,
        interpreter=interpreter,
    )
    policy = C7ReconciliationPolicy()
    with pytest.raises(C7ReconciliationError, match="epoch"):
        policy.authorize_new_epoch(
            attempt_id=attempt.attempt_id,
            proof=result.non_start_proof,
            current_authority_digest=AUTHORITY_DIGEST,
            expected_authority_digest=AUTHORITY_DIGEST,
            next_epoch=1,
            prior_epoch=1,
        )
    with pytest.raises(C7ReconciliationError, match="different attempt"):
        policy.authorize_new_epoch(
            attempt_id="attempt:other",
            proof=result.non_start_proof,
            current_authority_digest=AUTHORITY_DIGEST,
            expected_authority_digest=AUTHORITY_DIGEST,
            next_epoch=2,
            prior_epoch=1,
        )


def test_failed_terminal_readback_is_final_not_retryable() -> None:
    _recovery, _original, reconcile, attempt, interpreter = _recovery_context(
        disposition=EffectDisposition.FAILED
    )
    result = reconcile_with_shared_reconciler(
        assignment=reconcile,
        attempt=attempt,
        interpreter=interpreter,
    )
    assert result.state is ReconciliationState.RESOLVED
    assert result.disposition is EffectDisposition.FAILED
    assert result.readback is not None
    decision = C7ReconciliationPolicy().terminal_decision(result.disposition)
    assert decision.new_attempt_allowed is False
