"""Deterministic fixture and receipt-only interpreters for C2.3.

These implementations are test/interpreter fixtures, not live provider
adapters.  Every outcome, receipt, readback and non-start proof is derived
from an explicit script with stable digests, and every provider call is
recorded so replay/shadow evidence can assert ``provider_calls == 0`` for the
successor line when the fixture is shared.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from app.successor_runtime.capabilities import source_contracts as contracts
from app.successor_runtime.capabilities.checksum import sha256_hex

__all__ = [
    "DEFAULT_FIXTURE_OBSERVED_AT",
    "FixtureCredentialResolverPort",
    "FixtureProviderEffectGateway",
    "FixtureProviderEffectPort",
    "FixtureProviderReadbackPort",
    "build_fixture_attempt_ref",
    "build_fixture_receipt",
    "reconcile_provider_effect",
]


DEFAULT_FIXTURE_OBSERVED_AT = "2030-09-01T08:00:00Z"
_FIXTURE_AUTHORIZATION_DIGEST = sha256_hex(b"mrw-source-provider-acquisition-fixture-authorization-v2")


def _stable_digest(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_fixture_attempt_ref(
    request: contracts.ProviderEffectRequest,
    *,
    epoch: int = 1,
) -> Annotated[
    contracts.ProviderAttemptRef,
    Literal[
        "kit:non-authoritative derived_as=simulation fact_source=ProviderEffectRequest+fixture_epoch witness=test:test_w06_successor_authority_metadata"
    ],
]:
    attempt_id = f"attempt:source-acquisition:{request.request_id}:e{epoch}"
    return contracts.ProviderAttemptRef(
        attempt_id=attempt_id,
        request_digest=request.request_digest,
        provider=request.provider,
        epoch=epoch,
    )


def build_fixture_receipt(
    request: contracts.ProviderEffectRequest,
    attempt_ref: contracts.ProviderAttemptRef,
    *,
    provider_job_id: str | None = None,
    provider_status: str = "ACCEPTED",
    observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
) -> Annotated[
    contracts.ProviderReceipt,
    Literal[
        "kit:non-authoritative derived_as=simulation fact_source=ProviderEffectRequest+fixture_epoch witness=test:test_w06_successor_authority_metadata"
    ],
]:
    receipt_id = f"receipt:source-acquisition:{request.request_id}"
    return contracts.ProviderReceipt(
        receipt_id=receipt_id,
        provider=request.provider,
        provider_job_id=provider_job_id,
        provider_status=provider_status,
        attempt_ref=attempt_ref.as_ref_string(),
        observed_at=observed_at,
    )


class FixtureCredentialResolverPort:
    """Resolve opaque credential refs from an explicit allowlist.

    The fixture stores only redacted ref ids and provider names.  A
    deterministic lease id binds ref, provider and the fixed fixture
    authorization digest; no secret value is present anywhere.
    """

    def __init__(
        self,
        *,
        resolved_refs: Mapping[str, str] | None = None,
        denied_refs: frozenset[str] = frozenset(),
        observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
    ) -> None:
        self._resolved = dict(resolved_refs or {})
        self._denied = set(denied_refs)
        self._observed_at = observed_at
        self.resolves: list[str] = []

    def resolve(
        self,
        ref: contracts.CredentialRef,
        authorization: Any,
    ) -> contracts.EphemeralCredentialLease | contracts.RedactedCredentialRejection:
        self.resolves.append(ref.ref)
        decision = contracts.CredentialDecisionReceipt(
            decision="RESOLVED",
            credential_refs=(ref.ref,),
            redacted_profile={
                "provider": ref.provider,
                "grant_scope": ref.grant_scope,
                "required": ref.required,
            },
        )
        if ref.ref in self._denied or ref.ref not in self._resolved:
            return contracts.RedactedCredentialRejection(
                code="MISSING_CREDENTIAL" if ref.required else "UNAUTHORIZED",
                credential_ref=ref.ref,
                message=f"credential ref not resolvable in fixture: {ref.ref}",
                credential_decision_receipt=contracts.CredentialDecisionReceipt(
                    decision="MISSING" if ref.required else "UNAUTHORIZED",
                    credential_refs=(ref.ref,),
                    redacted_profile={"provider": ref.provider},
                ),
            )
        lease_id = f"lease:{_stable_digest(ref.ref, ref.provider, _FIXTURE_AUTHORIZATION_DIGEST)[:16]}"
        return contracts.EphemeralCredentialLease(
            lease_id=lease_id,
            credential_ref=ref.ref,
            provider=ref.provider,
            expires_at=self._observed_at,
            credential_decision_receipt=decision,
        )


class FixtureProviderEffectPort:
    """Deterministic scripted provider effect execution and cancellation."""

    def __init__(
        self,
        *,
        outcomes: Mapping[str, contracts.ProviderEffectOutcome] | None = None,
        default_outcome: contracts.ProviderEffectOutcome | None = None,
        observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
    ) -> None:
        self._outcomes = dict(outcomes or {})
        self._default = default_outcome
        self._observed_at = observed_at
        self.provider_calls: list[str] = []
        self.cancel_calls: list[str] = []

    def execute(
        self,
        request: contracts.ProviderEffectRequest,
        ephemeral_credentials: tuple[contracts.EphemeralCredentialLease, ...],
    ) -> contracts.ProviderEffectOutcome:
        self.provider_calls.append(request.request_id)
        outcome = self._outcomes.get(
            request.request_id,
            self._outcomes.get(request.idempotency_key, self._default),
        )
        if outcome is None:
            return contracts.RejectedProviderEffect(
                code="UNSUPPORTED_PROVIDER",
                message=f"no scripted fixture outcome for {request.request_id}",
            )
        return outcome

    def cancel(
        self,
        attempt_ref: contracts.ProviderAttemptRef,
        request: contracts.ProviderEffectRequest,
    ) -> contracts.CancelReceipt:
        self.cancel_calls.append(request.request_id)
        return contracts.CancelReceipt(
            cancel_receipt_id=f"cancel:source-acquisition:{request.request_id}",
            attempt_ref=attempt_ref.as_ref_string(),
            request_digest=request.request_digest,
        )


class FixtureProviderReadbackPort:
    """Deterministic readback and non-start proof fixture."""

    def __init__(
        self,
        *,
        readbacks: Mapping[str, contracts.ProviderReadbackResult] | None = None,
        non_start_proofs: frozenset[str] = frozenset(),
        observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
    ) -> None:
        self._readbacks = dict(readbacks or {})
        self._non_start_proofs = set(non_start_proofs)
        self._observed_at = observed_at
        self.readback_calls: list[str] = []

    def readback(
        self,
        attempt_ref: contracts.ProviderAttemptRef,
        request: contracts.ProviderEffectRequest,
    ) -> contracts.ProviderReadbackResult:
        self.readback_calls.append(attempt_ref.attempt_id)
        result = self._readbacks.get(attempt_ref.attempt_id)
        if result is not None:
            return result
        return contracts.ReadbackUnavailable(
            attempt_ref=attempt_ref.as_ref_string(),
            reason="fixture has no authoritative readback script",
        )

    def prove_not_started(
        self,
        attempt_ref: contracts.ProviderAttemptRef,
        request: contracts.ProviderEffectRequest,
    ) -> contracts.NonStartProof | contracts.NonStartUnprovable:
        if attempt_ref.attempt_id in self._non_start_proofs:
            return contracts.NonStartProof(
                attempt_ref=attempt_ref.as_ref_string(),
                evidence_locator=f"fixture:non-start:{attempt_ref.attempt_id}",
            )
        return contracts.NonStartUnprovable(
            attempt_ref=attempt_ref.as_ref_string(),
            reason="fixture cannot prove non-start for this attempt",
        )


class FixtureProviderEffectGateway:
    """Combined deterministic gateway used by P3 C2.3 replay/shadow tests."""

    def __init__(
        self,
        *,
        credentials: FixtureCredentialResolverPort,
        effect: FixtureProviderEffectPort,
        readback: FixtureProviderReadbackPort,
    ) -> None:
        self.credentials = credentials
        self.effect = effect
        self.readback = readback

    @property
    def provider_calls(self) -> list[str]:
        return self.effect.provider_calls

    def execute(
        self,
        request: contracts.ProviderEffectRequest,
        authorization: Any = None,
    ) -> contracts.ProviderEffectOutcome:
        leases: list[contracts.EphemeralCredentialLease] = []
        for ref in request.credential_refs:
            resolved = self.credentials.resolve(ref, authorization)
            if isinstance(resolved, contracts.RedactedCredentialRejection):
                return contracts.RejectedProviderEffect(
                    code=resolved.code,
                    message=resolved.message,
                )
            leases.append(resolved)
        return self.effect.execute(request, tuple(leases))

    def readback_attempt(
        self,
        attempt_ref: contracts.ProviderAttemptRef,
        request: contracts.ProviderEffectRequest,
    ) -> contracts.ProviderReadbackResult:
        return self.readback.readback(attempt_ref, request)

    def cancel(
        self,
        attempt_ref: contracts.ProviderAttemptRef,
        request: contracts.ProviderEffectRequest,
    ) -> contracts.CancelReceipt:
        return self.effect.cancel(attempt_ref, request)

    def prove_not_started(
        self,
        attempt_ref: contracts.ProviderAttemptRef,
        request: contracts.ProviderEffectRequest,
    ) -> contracts.NonStartProof | contracts.NonStartUnprovable:
        return self.readback.prove_not_started(attempt_ref, request)


def reconcile_provider_effect(
    request: contracts.ProviderEffectRequest,
    attempt_ref: contracts.ProviderAttemptRef,
    readback_result: contracts.ProviderReadbackResult,
    *,
    observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
) -> contracts.OutcomeUnknownProviderEffect | contracts.ReconciledProviderEffect:
    """Fold one readback into the attempt without re-executing the provider.

    Terminal readback converges the original attempt; waiting/unavailable
    readback returns OUTCOME_UNKNOWN.  No provider call is made and no
    completion is inferred from an absent receipt.
    """

    if isinstance(readback_result, contracts.ReadbackTerminal):
        return contracts.ReconciledProviderEffect(
            attempt_ref=attempt_ref.as_ref_string(),
            readback=readback_result.readback,
        )
    return contracts.OutcomeUnknownProviderEffect(
        attempt_ref=attempt_ref.as_ref_string(),
        reason=(
            "readback waiting" if isinstance(readback_result, contracts.ReadbackWaiting) else "readback unavailable"
        ),
    )


def build_deterministic_completed_outcome(
    request: contracts.ProviderEffectRequest,
    *,
    attempt_ref: contracts.ProviderAttemptRef,
    records: tuple[contracts.CapturedSourceRecordRef, ...] = (),
    artifacts: tuple[contracts.StagedArtifactRef, ...] = (),
    observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
) -> Annotated[
    contracts.CompletedProviderEffect,
    "kit:non-authoritative derived_as=simulation "
    "fact_source=source.provider_acquisition.fixture_script "
    "witness=test:test_scripted_outcomes_are_deterministic_and_traced",
]:
    return contracts.CompletedProviderEffect(
        receipt=build_fixture_receipt(
            request,
            attempt_ref,
            provider_job_id=f"job:source-acquisition:{request.request_id}",
            provider_status="COMPLETED",
            observed_at=observed_at,
        ),
        record_refs=records,
        staged_artifact_refs=artifacts,
    )


def build_deterministic_accepted_outcome(
    request: contracts.ProviderEffectRequest,
    *,
    attempt_ref: contracts.ProviderAttemptRef,
    observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
) -> Annotated[
    contracts.AcceptedProviderEffect,
    Literal[
        "kit:non-authoritative derived_as=simulation fact_source=ProviderEffectRequest+fixture_epoch witness=test:test_w06_successor_authority_metadata"
    ],
]:
    return contracts.AcceptedProviderEffect(
        receipt=build_fixture_receipt(
            request,
            attempt_ref,
            provider_job_id=f"job:source-acquisition:{request.request_id}",
            provider_status="ACCEPTED",
            observed_at=observed_at,
        ),
    )


def build_deterministic_unknown_outcome(
    request: contracts.ProviderEffectRequest,
    *,
    attempt_ref: contracts.ProviderAttemptRef,
) -> Annotated[
    contracts.OutcomeUnknownProviderEffect,
    Literal[
        "kit:non-authoritative derived_as=simulation fact_source=ProviderEffectRequest+fixture_epoch witness=test:test_w06_successor_authority_metadata"
    ],
]:
    return contracts.OutcomeUnknownProviderEffect(
        attempt_ref=attempt_ref.as_ref_string(),
        reason="fixture crash after effect dispatch before receipt",
    )
