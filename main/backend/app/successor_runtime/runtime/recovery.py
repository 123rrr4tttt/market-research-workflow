"""Recovery contracts that never infer NOT_STARTED from missing evidence."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from .assignments import Digest, FrozenContract, canonical_digest, require_digest
from .failure_policy import raise_runtime_failure, runtime_failure
from .transitions import EffectDisposition


class OutcomeUnknown(FrozenContract):
    attempt_id: Digest
    disposition: EffectDisposition = EffectDisposition.OUTCOME_UNKNOWN
    reconciliation_hint: str = Field(min_length=1)


class NonStartProof(FrozenContract):
    attempt_id: Digest
    interpreter_id: str = Field(min_length=1)
    interpreter_version: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    external_idempotency_key: str = Field(min_length=1)
    authoritative_readback_locator: str = Field(min_length=1)
    authoritative_observation_digest: Digest
    observed_at: datetime
    proof_digest: Digest

    @model_validator(mode="after")
    def validate_proof_digest(self) -> "NonStartProof":
        expected = canonical_digest(self, exclude_fields={"proof_digest"})
        if self.proof_digest != expected:
            # kit:boundary owner=successor.runtime.recovery class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_runtime_non_start_proof_negative
            raise ValueError("proof_digest does not match canonical non-start proof content")
        return self


def authorize_successor_attempt(*, prior_attempt_id: str, proof: NonStartProof) -> None:
    require_digest(prior_attempt_id, "prior_attempt_id")
    if proof.attempt_id != prior_attempt_id:
        failure = runtime_failure(
            "STAGED_RECOVERY_REQUEST_INVALID",
            "NonStartProof is bound to a different attempt",
            ValueError,
            site="recovery.authorize_successor_attempt",
        )
        raise_runtime_failure(failure, ValueError)
    # Presence of every authoritative field is enforced by the contract.  Lease
    # expiry, node loss, missing receipts, and broker state are intentionally not
    # accepted as substitutes.
