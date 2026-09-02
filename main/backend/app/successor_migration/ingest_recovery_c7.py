"""C7.4 readback and non-start reconciliation using shared runtime contracts.

Terminal authoritative readback is a final observation and never starts a new attempt
the effect.  A new execution epoch requires an exact ``NonStartProof`` bound
to the prior attempt plus the current authority digest; any mismatch fails
closed.  The shared ``EffectReconciler`` performs exact recovery-binding and
readback validation; this adapter owns only the C7 new-epoch decision.
"""

from __future__ import annotations

from typing import Any

from app.successor_runtime.capabilities.ingest_c7_common import (
    C7ReconciliationDecision,
)
from app.successor_runtime.runtime.reconciliation import EffectReconciler
from app.successor_runtime.runtime.recovery import (
    NonStartProof,
    authorize_successor_attempt,
)
from app.successor_runtime.runtime.transitions import EffectDisposition

__all__ = [
    "C7ReconciliationError",
    "C7ReconciliationPolicy",
    "prove_non_start_with_shared_reconciler",
    "reconcile_with_shared_reconciler",
]


class C7ReconciliationError(ValueError):
    """C7 recovery identity, authority or epoch guard failed."""


class C7ReconciliationPolicy:
    """Family-local decision policy over shared terminal readback/proof types."""

    def terminal_decision(
        self, disposition: EffectDisposition
    ) -> C7ReconciliationDecision:
        if disposition not in {
            EffectDisposition.SUCCEEDED,
            EffectDisposition.FAILED,
        }:
            raise C7ReconciliationError("terminal readback requires SUCCEEDED/FAILED")
        return C7ReconciliationDecision(
            new_attempt_allowed=False,
            requirement="terminal_readback_is_final",
            reason="terminal readback resolves the attempt; no new attempt is permitted",
        )

    def authorize_new_epoch(
        self,
        *,
        attempt_id: str,
        proof: NonStartProof,
        current_authority_digest: str,
        expected_authority_digest: str,
        next_epoch: int,
        prior_epoch: int,
    ) -> C7ReconciliationDecision:
        if proof.attempt_id != attempt_id:
            raise C7ReconciliationError("NonStartProof is bound to a different attempt")
        authorize_successor_attempt(prior_attempt_id=attempt_id, proof=proof)
        if current_authority_digest != expected_authority_digest:
            raise C7ReconciliationError(
                "current authority does not match the required authority"
            )
        if next_epoch <= prior_epoch:
            raise C7ReconciliationError("new execution epoch must advance")
        return C7ReconciliationDecision(
            new_attempt_allowed=True,
            requirement="exact_nonstart_proof_and_current_authority",
            reason="exact NonStartProof plus current authority authorizes one new epoch",
        )


def reconcile_with_shared_reconciler(
    *,
    assignment: Any,
    attempt: Any,
    interpreter: Any,
) -> Any:
    """Delegate terminal readback to the shared EffectReconciler."""

    return EffectReconciler().reconcile(
        assignment=assignment,
        attempt=attempt,
        interpreter=interpreter,
    )


def prove_non_start_with_shared_reconciler(
    *,
    assignment: Any,
    attempt: Any,
    interpreter: Any,
) -> Any:
    """Delegate non-start proof validation to the shared EffectReconciler."""

    return EffectReconciler().prove_non_start(
        assignment=assignment,
        attempt=attempt,
        interpreter=interpreter,
    )
