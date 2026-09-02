"""P3 C2.3 legacy donor fixture replay, shadow and rollback evidence."""

from __future__ import annotations

from app.successor_migration.legacy_source_library_c2_3 import (
    LegacySourceLibraryC2_3Adapter,
)
from app.successor_runtime.capabilities import source_library_c2_3 as c23
from app.successor_runtime.capabilities import (
    source_library_c2_3_test_interpreters as c23_fixtures,
)

from .test_p3_c2_3_contracts import _effect_request


def test_legacy_donor_replay_never_calls_runner() -> None:
    request = _effect_request()
    adapter = LegacySourceLibraryC2_3Adapter()
    trace = adapter.replay(request, fixture_id="provider_harvest_accepted")
    assert trace.fixture_id == "provider_harvest_accepted"
    assert trace.provider_calls == ()
    assert trace.handoff["contract_version"] == "source_library.provider_handoff.v1"
    assert adapter.provider_calls == []
    assert trace.trace_digest


def test_shadow_shares_fixture_without_double_effect() -> None:
    request = _effect_request()
    legacy = LegacySourceLibraryC2_3Adapter()
    legacy_trace = legacy.replay(request, fixture_id="provider_harvest_accepted")
    attempt = c23_fixtures.build_fixture_attempt_ref(request)
    successor_gateway = c23_fixtures.FixtureProviderEffectGateway(
        credentials=c23_fixtures.FixtureCredentialResolverPort(
            resolved_refs={"credential:/secret-ref/hc-api-key": "handler_cluster"}
        ),
        effect=c23_fixtures.FixtureProviderEffectPort(
            outcomes={
                request.request_id: c23_fixtures.build_deterministic_accepted_outcome(
                    request, attempt_ref=attempt
                )
            }
        ),
        readback=c23_fixtures.FixtureProviderReadbackPort(),
    )
    outcome = successor_gateway.execute(request, {"authority": "shadow"})
    assert isinstance(outcome, c23.AcceptedProviderEffect)
    assert successor_gateway.provider_calls == [request.request_id]
    # The legacy donor trace proves the donor itself never executed.
    assert legacy.provider_calls == []
    assert legacy_trace.handoff["provider_status"] == "COMPLETED"


def test_shadow_transport_failure_and_unknown_are_typed() -> None:
    request = _effect_request()
    adapter = LegacySourceLibraryC2_3Adapter()
    transport = adapter.replay(request, fixture_id="transport_failure")
    unknown = adapter.replay(request, fixture_id="outcome_unknown")
    assert transport.outcome["kind"] == "failed"
    assert transport.outcome["code"] == "TRANSPORT"
    assert unknown.outcome["kind"] == "outcome_unknown"
    assert adapter.provider_calls == []


def test_rollback_retains_journal_and_reconciles_unknown_before_legacy() -> None:
    request = _effect_request()
    adapter = LegacySourceLibraryC2_3Adapter()
    before = adapter.replay(request, fixture_id="outcome_unknown")
    attempt = c23_fixtures.build_fixture_attempt_ref(request)
    readback = c23.ReadbackUnavailable(
        attempt_ref=attempt.as_ref_string(),
        reason="rollback reconciliation readback unavailable",
    )
    reconciled = c23_fixtures.reconcile_provider_effect(request, attempt, readback)
    assert isinstance(reconciled, c23.OutcomeUnknownProviderEffect)
    # Rollback keeps the donor trace/journal and does not re-dispatch.
    assert adapter.provider_calls == []
    assert before.provider_calls == ()
