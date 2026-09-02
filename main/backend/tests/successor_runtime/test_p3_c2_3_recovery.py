"""P3 C2.3 readback, OUTCOME_UNKNOWN, reconcile and cancellation contracts."""

from __future__ import annotations

from app.successor_runtime.capabilities import source_library_c2_3 as c23
from app.successor_runtime.capabilities import (
    source_library_c2_3_test_interpreters as c23_fixtures,
)

from .test_p3_c2_3_contracts import _effect_request


def _attempt(request: c23.ProviderEffectRequest) -> c23.ProviderAttemptRef:
    return c23_fixtures.build_fixture_attempt_ref(request)


def test_terminal_readback_reconciles_without_duplicate_provider_call() -> None:
    request = _effect_request()
    attempt = _attempt(request)
    gateway = c23_fixtures.FixtureProviderEffectGateway(
        credentials=c23_fixtures.FixtureCredentialResolverPort(
            resolved_refs={"credential:/secret-ref/hc-api-key": "handler_cluster"}
        ),
        effect=c23_fixtures.FixtureProviderEffectPort(),
        readback=c23_fixtures.FixtureProviderReadbackPort(
            readbacks={
                attempt.attempt_id: c23.ReadbackTerminal(
                    readback=c23.AuthoritativeProviderReadback(
                        attempt_ref=attempt.as_ref_string(),
                        provider_job_id="job:reconcile",
                        terminal_status="COMPLETED",
                        readback_receipt_id="readback:reconcile",
                        observed_at="2030-09-01T08:01:00Z",
                    )
                )
            }
        ),
    )
    readback = gateway.readback_attempt(attempt, request)
    reconciled = c23_fixtures.reconcile_provider_effect(request, attempt, readback)
    assert isinstance(reconciled, c23.ReconciledProviderEffect)
    assert reconciled.readback.terminal_status == "COMPLETED"
    assert reconciled.attempt_ref == attempt.as_ref_string()
    # Readback reconciliation never re-executes the provider.
    assert gateway.provider_calls == []
    assert gateway.readback.readback_calls == [attempt.attempt_id]


def test_waiting_and_unavailable_readback_stay_outcome_unknown() -> None:
    request = _effect_request()
    attempt = _attempt(request)
    for result in (
        c23.ReadbackWaiting(
            attempt_ref=attempt.as_ref_string(),
            observed_at="2030-09-01T08:01:00Z",
        ),
        c23.ReadbackUnavailable(
            attempt_ref=attempt.as_ref_string(),
            reason="provider readback endpoint unavailable",
        ),
    ):
        reconciled = c23_fixtures.reconcile_provider_effect(request, attempt, result)
        assert isinstance(reconciled, c23.OutcomeUnknownProviderEffect)
        assert reconciled.kind == "outcome_unknown"


def test_crash_before_receipt_is_outcome_unknown_not_completed() -> None:
    request = _effect_request()
    attempt = _attempt(request)
    gateway = c23_fixtures.FixtureProviderEffectGateway(
        credentials=c23_fixtures.FixtureCredentialResolverPort(
            resolved_refs={"credential:/secret-ref/hc-api-key": "handler_cluster"}
        ),
        effect=c23_fixtures.FixtureProviderEffectPort(
            outcomes={
                request.request_id: c23_fixtures.build_deterministic_unknown_outcome(
                    request, attempt_ref=attempt
                )
            }
        ),
        readback=c23_fixtures.FixtureProviderReadbackPort(),
    )
    outcome = gateway.execute(request, {"authority": "fixture"})
    assert isinstance(outcome, c23.OutcomeUnknownProviderEffect)
    assert outcome.attempt_ref == attempt.as_ref_string()
    assert gateway.provider_calls == [request.request_id]
    # No completion or receipt is inferred from the unknown outcome.
    assert not isinstance(outcome, c23.CompletedProviderEffect)
    assert not isinstance(outcome, c23.AcceptedProviderEffect)


def test_cancel_returns_deterministic_receipt_and_never_claims_terminal() -> None:
    request = _effect_request()
    attempt = _attempt(request)
    gateway = c23_fixtures.FixtureProviderEffectGateway(
        credentials=c23_fixtures.FixtureCredentialResolverPort(
            resolved_refs={"credential:/secret-ref/hc-api-key": "handler_cluster"}
        ),
        effect=c23_fixtures.FixtureProviderEffectPort(),
        readback=c23_fixtures.FixtureProviderReadbackPort(),
    )
    receipt = gateway.cancel(attempt, request)
    assert isinstance(receipt, c23.CancelReceipt)
    assert receipt.cancel_status == "CANCEL_ACCEPTED"
    assert receipt.request_digest == request.request_digest
    assert gateway.effect.cancel_calls == [request.request_id]
    assert gateway.provider_calls == []


def test_non_start_proof_and_unprovable_are_honest() -> None:
    request = _effect_request()
    attempt = _attempt(request)
    gateway = c23_fixtures.FixtureProviderEffectGateway(
        credentials=c23_fixtures.FixtureCredentialResolverPort(
            resolved_refs={"credential:/secret-ref/hc-api-key": "handler_cluster"}
        ),
        effect=c23_fixtures.FixtureProviderEffectPort(),
        readback=c23_fixtures.FixtureProviderReadbackPort(
            non_start_proofs=frozenset({attempt.attempt_id})
        ),
    )
    proof = gateway.prove_not_started(attempt, request)
    assert isinstance(proof, c23.NonStartProof)
    assert proof.attempt_ref == attempt.as_ref_string()

    other = c23_fixtures.build_fixture_attempt_ref(request, epoch=2)
    unprovable = gateway.prove_not_started(other, request)
    assert isinstance(unprovable, c23.NonStartUnprovable)
    assert unprovable.attempt_ref == other.as_ref_string()


def test_rollback_requires_reconcile_before_legacy_redispatches() -> None:
    request = _effect_request()
    attempt = _attempt(request)
    gateway = c23_fixtures.FixtureProviderEffectGateway(
        credentials=c23_fixtures.FixtureCredentialResolverPort(
            resolved_refs={"credential:/secret-ref/hc-api-key": "handler_cluster"}
        ),
        effect=c23_fixtures.FixtureProviderEffectPort(),
        readback=c23_fixtures.FixtureProviderReadbackPort(),
    )
    readback = gateway.readback_attempt(attempt, request)
    reconciled = c23_fixtures.reconcile_provider_effect(request, attempt, readback)
    # Unresolved OutcomeUnknown blocks any legacy re-dispatch for the same
    # request digest; the fixture proves zero additional provider calls.
    assert isinstance(reconciled, c23.OutcomeUnknownProviderEffect)
    assert gateway.provider_calls == []
