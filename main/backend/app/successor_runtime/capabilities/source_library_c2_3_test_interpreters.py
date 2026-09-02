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
from typing import Any

from app.successor_runtime.capabilities import source_library_c2_shared as shared
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
_FIXTURE_AUTHORIZATION_DIGEST = sha256_hex(b"mrw-p3-c2-3-fixture-authorization")


def _stable_digest(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_fixture_attempt_ref(
    request: shared.ProviderEffectRequest,
    *,
    epoch: int = 1,
) -> shared.ProviderAttemptRef:
    attempt_id = f"attempt:c2-3-{request.request_id}-e{epoch}"
    return shared.ProviderAttemptRef(
        attempt_id=attempt_id,
        request_digest=request.request_digest,
        provider=request.provider,
        epoch=epoch,
    )


def build_fixture_receipt(
    request: shared.ProviderEffectRequest,
    attempt_ref: shared.ProviderAttemptRef,
    *,
    provider_job_id: str | None = None,
    provider_status: str = "ACCEPTED",
    observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
) -> shared.ProviderReceipt:
    receipt_id = f"receipt:c2-3-{request.request_id}"
    return shared.ProviderReceipt(
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
        ref: shared.CredentialRef,
        authorization: Any,
    ) -> shared.EphemeralCredentialLease | shared.RedactedCredentialRejection:
        self.resolves.append(ref.ref)
        decision = shared.CredentialDecisionReceipt(
            decision="RESOLVED",
            credential_refs=(ref.ref,),
            redacted_profile={
                "provider": ref.provider,
                "grant_scope": ref.grant_scope,
                "required": ref.required,
            },
        )
        if ref.ref in self._denied or ref.ref not in self._resolved:
            return shared.RedactedCredentialRejection(
                code="MISSING_CREDENTIAL" if ref.required else "UNAUTHORIZED",
                credential_ref=ref.ref,
                message=f"credential ref not resolvable in fixture: {ref.ref}",
                credential_decision_receipt=shared.CredentialDecisionReceipt(
                    decision="MISSING" if ref.required else "UNAUTHORIZED",
                    credential_refs=(ref.ref,),
                    redacted_profile={"provider": ref.provider},
                ),
            )
        lease_id = f"lease:{_stable_digest(ref.ref, ref.provider, _FIXTURE_AUTHORIZATION_DIGEST)[:16]}"
        return shared.EphemeralCredentialLease(
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
        outcomes: Mapping[str, shared.ProviderEffectOutcome] | None = None,
        default_outcome: shared.ProviderEffectOutcome | None = None,
        observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
    ) -> None:
        self._outcomes = dict(outcomes or {})
        self._default = default_outcome
        self._observed_at = observed_at
        self.provider_calls: list[str] = []
        self.cancel_calls: list[str] = []

    def execute(
        self,
        request: shared.ProviderEffectRequest,
        ephemeral_credentials: tuple[shared.EphemeralCredentialLease, ...],
    ) -> shared.ProviderEffectOutcome:
        self.provider_calls.append(request.request_id)
        outcome = self._outcomes.get(
            request.request_id,
            self._outcomes.get(request.idempotency_key, self._default),
        )
        if outcome is None:
            return shared.FailedProviderEffect(
                code="UNSUPPORTED_PROVIDER",
                message=f"no scripted fixture outcome for {request.request_id}",
            )
        return outcome

    def cancel(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.CancelReceipt:
        self.cancel_calls.append(request.request_id)
        return shared.CancelReceipt(
            cancel_receipt_id=f"cancel:c2-3-{request.request_id}",
            attempt_ref=attempt_ref.as_ref_string(),
            request_digest=request.request_digest,
        )


class FixtureProviderReadbackPort:
    """Deterministic readback and non-start proof fixture."""

    def __init__(
        self,
        *,
        readbacks: Mapping[str, shared.ProviderReadbackResult] | None = None,
        non_start_proofs: frozenset[str] = frozenset(),
        observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
    ) -> None:
        self._readbacks = dict(readbacks or {})
        self._non_start_proofs = set(non_start_proofs)
        self._observed_at = observed_at
        self.readback_calls: list[str] = []

    def readback(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.ProviderReadbackResult:
        self.readback_calls.append(attempt_ref.attempt_id)
        result = self._readbacks.get(attempt_ref.attempt_id)
        if result is not None:
            return result
        return shared.ReadbackUnavailable(
            attempt_ref=attempt_ref.as_ref_string(),
            reason="fixture has no authoritative readback script",
        )

    def prove_not_started(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.NonStartProof | shared.NonStartUnprovable:
        if attempt_ref.attempt_id in self._non_start_proofs:
            return shared.NonStartProof(
                attempt_ref=attempt_ref.as_ref_string(),
                evidence_locator=f"fixture:non-start:{attempt_ref.attempt_id}",
            )
        return shared.NonStartUnprovable(
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
        request: shared.ProviderEffectRequest,
        authorization: Any = None,
    ) -> shared.ProviderEffectOutcome:
        leases: list[shared.EphemeralCredentialLease] = []
        for ref in request.credential_refs:
            resolved = self.credentials.resolve(ref, authorization)
            if isinstance(resolved, shared.RedactedCredentialRejection):
                return shared.RejectedProviderEffect(
                    code=resolved.code,
                    message=resolved.message,
                )
            leases.append(resolved)
        return self.effect.execute(request, tuple(leases))

    def readback_attempt(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.ProviderReadbackResult:
        return self.readback.readback(attempt_ref, request)

    def cancel(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.CancelReceipt:
        return self.effect.cancel(attempt_ref, request)

    def prove_not_started(
        self,
        attempt_ref: shared.ProviderAttemptRef,
        request: shared.ProviderEffectRequest,
    ) -> shared.NonStartProof | shared.NonStartUnprovable:
        return self.readback.prove_not_started(attempt_ref, request)


def reconcile_provider_effect(
    request: shared.ProviderEffectRequest,
    attempt_ref: shared.ProviderAttemptRef,
    readback_result: shared.ProviderReadbackResult,
    *,
    observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
) -> shared.OutcomeUnknownProviderEffect | shared.ReconciledProviderEffect:
    """Fold one readback into the attempt without re-executing the provider.

    Terminal readback converges the original attempt; waiting/unavailable
    readback returns OUTCOME_UNKNOWN.  No provider call is made and no
    completion is inferred from an absent receipt.
    """

    if isinstance(readback_result, shared.ReadbackTerminal):
        return shared.ReconciledProviderEffect(
            attempt_ref=attempt_ref.as_ref_string(),
            readback=readback_result.readback,
        )
    return shared.OutcomeUnknownProviderEffect(
        attempt_ref=attempt_ref.as_ref_string(),
        reason=(
            "readback waiting"
            if isinstance(readback_result, shared.ReadbackWaiting)
            else "readback unavailable"
        ),
    )


def build_deterministic_completed_outcome(
    request: shared.ProviderEffectRequest,
    *,
    attempt_ref: shared.ProviderAttemptRef,
    records: tuple[shared.CapturedSourceRecordRef, ...] = (),
    artifacts: tuple[shared.StagedArtifactRef, ...] = (),
    observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
) -> shared.CompletedProviderEffect:
    return shared.CompletedProviderEffect(
        receipt=build_fixture_receipt(
            request,
            attempt_ref,
            provider_job_id=f"job:c2-3-{request.request_id}",
            provider_status="COMPLETED",
            observed_at=observed_at,
        ),
        record_refs=records,
        staged_artifact_refs=artifacts,
    )


def build_deterministic_accepted_outcome(
    request: shared.ProviderEffectRequest,
    *,
    attempt_ref: shared.ProviderAttemptRef,
    observed_at: str = DEFAULT_FIXTURE_OBSERVED_AT,
) -> shared.AcceptedProviderEffect:
    return shared.AcceptedProviderEffect(
        receipt=build_fixture_receipt(
            request,
            attempt_ref,
            provider_job_id=f"job:c2-3-{request.request_id}",
            provider_status="ACCEPTED",
            observed_at=observed_at,
        ),
    )


def build_deterministic_unknown_outcome(
    request: shared.ProviderEffectRequest,
    *,
    attempt_ref: shared.ProviderAttemptRef,
) -> shared.OutcomeUnknownProviderEffect:
    return shared.OutcomeUnknownProviderEffect(
        attempt_ref=attempt_ref.as_ref_string(),
        reason="fixture crash after effect dispatch before receipt",
    )
