"""Focused successor tests for the ALL-SM-013 quality-promotion port.

The fixtures here express the same semantic inputs as the donor
``search_quality_replay`` readback contract (case ids, critic score source,
bounded-retry observations and provider threshold rows) without importing or
executing donor code.  Every assertion is against the successor typed port.
"""

from __future__ import annotations

from dataclasses import replace

from app.successor_runtime.capabilities.quality_promotion_port import (
    BoundedRetryReadback,
    CriticScoreReadback,
    ExecutorHealthEvidence,
    FixtureQualityReadback,
    InputPromotionClaim,
    LiveProviderReplayReadback,
    LiveProviderRowEvidence,
    ProviderRolloutPolicyEvidence,
    QualityGateEvidence,
    RetryBoundaryObservation,
    evaluate_quality_promotion_gate,
    redact_broker_url,
)


def _online_executor_health() -> ExecutorHealthEvidence:
    return ExecutorHealthEvidence(
        worker_online=True,
        workers=("celery@successor",),
        inspect_performed=True,
        inspect_ok=True,
        broker_url_masked="redis://localhost:6379/0",
    )


def _fixture_quality_readback() -> FixtureQualityReadback:
    return FixtureQualityReadback(
        case_count=2,
        critic=CriticScoreReadback(
            case_id="robotics-source-gap",
            score=0.66,
            score_threshold=0.72,
            next_action="retry_with_precision_query",
            reason_codes=("entity_coverage_gap", "freshness_gap"),
        ),
        retry=BoundedRetryReadback(
            observations=(
                RetryBoundaryObservation(
                    case_id="robotics-source-gap",
                    expected_decision="retry_allowed",
                    decision="retry_allowed",
                    critic_score=0.66,
                    replay_score_is_observational=True,
                ),
                RetryBoundaryObservation(
                    case_id="robotics-sufficient-stop",
                    expected_decision="retry_blocked",
                    decision="retry_blocked",
                    critic_score=0.91,
                    replay_score_is_observational=True,
                ),
            ),
            enabled=True,
            retry_budget=1,
            max_retry_rounds=1,
        ),
        fixture_threshold_status="passed",
    )


def _provider_row(provider: str) -> LiveProviderRowEvidence:
    return LiveProviderRowEvidence(
        provider=provider,
        replay_status="passed",
        result_count=3,
        source_domains=("interestingengineering.com", "globenewswire.com"),
        relevance_score=0.82,
        freshness_score=0.84,
        duplicate_rate=0.0,
        timeout_rate=0.0,
        p95_latency_ms=980,
        review_sample_count=3,
        review_visible_sample_count=3,
        trace_success=True,
    )


def _live_replay_readback() -> LiveProviderReplayReadback:
    return LiveProviderReplayReadback(
        readback_artifact_ref="evidence/live-provider-quality-replay.v1.json",
        provider_rows=tuple(
            _provider_row(provider) for provider in ("searxng", "yacy", "web")
        ),
        operator_review_status="approved",
    )


def _approved_rollout_policy() -> ProviderRolloutPolicyEvidence:
    return ProviderRolloutPolicyEvidence(
        approval_status="approved",
        approved_providers=("searxng", "yacy", "web"),
        rollback_criteria=("timeout_rate_above_10_percent",),
        monitoring_requirements=("daily_threshold_replay",),
        manual_review_artifact="evidence/provider-auto-review.md",
    )


def _assert_no_authority_or_effect(result: object) -> None:
    authority = result.authority
    assert authority.authority_granted is False
    assert authority.provider_auto_promotion_authorized is False
    assert authority.live_provider_call_authorized is False
    assert authority.rollout_change_authorized is False
    assert authority.canonical_write_authorized is False
    assert authority.credential_read_authorized is False
    counts = result.effect_counts
    assert counts.provider_calls == 0
    assert counts.store_writes == 0
    assert counts.canonical_writes == 0
    assert counts.export_calls == 0


def test_no_live_readback_evidence_means_no_promotion() -> None:
    gate = evaluate_quality_promotion_gate(
        QualityGateEvidence(
            fixture_replay=_fixture_quality_readback(),
            executor_health=_online_executor_health(),
        )
    )

    assert gate.status == "passed"
    assert (
        gate.gate_state == "provider_independent_quality_promotion_held_live_gap_open"
    )
    assert gate.quality.passed is True
    assert gate.health.passed is True
    assert gate.promotion.decision.decision == "hold_provider_auto_promotion"
    assert gate.promotion.decision.promotion_allowed is False
    assert gate.promotion.decision.provider_auto_promotion_allowed is False
    assert gate.readback.readback_matches_decision is True
    assert gate.readback.promotion_allowed is False
    assert gate.readback.decision_digest == gate.readback.readback_digest
    gap_codes = {gap.code for gap in gate.remaining_gaps}
    assert "live_provider_replay_readback_missing" in gap_codes
    assert "provider_auto_rollout_policy_not_approved" in gap_codes
    _assert_no_authority_or_effect(gate)


def test_quality_gate_precedes_promotion_even_with_live_closure() -> None:
    gate = evaluate_quality_promotion_gate(
        QualityGateEvidence(
            executor_health=_online_executor_health(),
            live_replay=_live_replay_readback(),
            rollout_policy=_approved_rollout_policy(),
            input_promotion_claim=InputPromotionClaim(
                decision="promote_provider_auto",
                promotion_allowed=True,
                provider_auto_promotion_allowed=True,
            ),
        )
    )

    assert gate.status == "failed"
    assert gate.quality.state == "fixture_quality_readback_missing"
    assert gate.promotion.decision.decision == "hold_provider_auto_promotion"
    assert gate.promotion.decision.promotion_allowed is False
    assert gate.readback.input_promotion_claim_rejected is True
    assert "fixture_quality_gate_blocked" in {gap.code for gap in gate.remaining_gaps}
    assert "input_promotion_decision_claim_rejected" in {
        claim.code for claim in gate.unsupported_claims
    }
    _assert_no_authority_or_effect(gate)


def test_health_anomaly_fails_closed_despite_live_closure() -> None:
    gate = evaluate_quality_promotion_gate(
        QualityGateEvidence(
            fixture_replay=_fixture_quality_readback(),
            executor_health=ExecutorHealthEvidence(
                worker_online=False,
                workers=(),
                inspect_performed=True,
                inspect_ok=True,
            ),
            live_replay=_live_replay_readback(),
            rollout_policy=_approved_rollout_policy(),
        )
    )

    assert gate.status == "failed"
    assert gate.quality.passed is True
    assert gate.health.passed is False
    assert gate.health.state == "executor_health_failed"
    assert "executor_health_no_online_worker" in gate.health.failures
    assert gate.promotion.decision.promotion_allowed is False
    assert "executor_health_blocked" in {gap.code for gap in gate.remaining_gaps}
    _assert_no_authority_or_effect(gate)


def test_live_readback_and_approved_policy_reach_decision_without_authority() -> None:
    gate = evaluate_quality_promotion_gate(
        QualityGateEvidence(
            fixture_replay=_fixture_quality_readback(),
            executor_health=_online_executor_health(),
            live_replay=_live_replay_readback(),
            rollout_policy=_approved_rollout_policy(),
        )
    )

    assert gate.status == "passed"
    assert gate.gate_state == "promotion_decision_approved_readback_only"
    assert gate.quality.passed is True
    assert gate.health.passed is True
    assert gate.promotion.decision.decision == "promote_provider_auto"
    assert gate.promotion.decision.promotion_allowed is True
    assert gate.promotion.decision.provider_auto_promotion_allowed is True
    assert (
        "provider_auto_rollout_policy_approved" in gate.promotion.decision.reason_codes
    )
    assert gate.readback.promotion_allowed is True
    assert gate.readback.readback_matches_decision is True
    assert gate.remaining_gaps == ()
    assert gate.unsupported_claims == ()
    _assert_no_authority_or_effect(gate)


def test_below_threshold_provider_row_keeps_live_gap_open() -> None:
    rows = [
        _provider_row("searxng"),
        _provider_row("yacy"),
        _provider_row("web"),
    ]
    rows[0] = replace(rows[0], relevance_score=0.5)
    gate = evaluate_quality_promotion_gate(
        QualityGateEvidence(
            fixture_replay=_fixture_quality_readback(),
            executor_health=_online_executor_health(),
            live_replay=LiveProviderReplayReadback(
                readback_artifact_ref="evidence/live-provider-quality-replay.v1.json",
                provider_rows=tuple(rows),
                operator_review_status="approved",
            ),
            rollout_policy=_approved_rollout_policy(),
        )
    )

    assert gate.status == "passed"
    assert gate.promotion.decision.promotion_allowed is False
    assert "searxng_relevance_below_minimum" in {
        gap.code for gap in gate.remaining_gaps
    }
    _assert_no_authority_or_effect(gate)


def test_broker_url_redaction_never_exposes_credentials() -> None:
    masked = redact_broker_url("redis://user:secret@localhost:6379/0?token=abc")
    assert masked == "redis://user:***@localhost:6379/0?token=%2A%2A%2A"
    assert "secret" not in masked
    assert "abc" not in masked
    assert redact_broker_url("redis://localhost:6379/1") == ("redis://localhost:6379/1")
    assert redact_broker_url("") == ""


def test_acceptance_trace_holds_until_explicit_readback_closes_gate() -> None:
    step1 = evaluate_quality_promotion_gate()
    assert step1.status == "failed"
    assert step1.promotion.decision.promotion_allowed is False
    assert "fixture_quality_readback_missing" in step1.failures
    assert "executor_health_evidence_missing" in step1.failures

    step2 = evaluate_quality_promotion_gate(
        QualityGateEvidence(
            fixture_replay=_fixture_quality_readback(),
            executor_health=_online_executor_health(),
        )
    )
    assert step2.status == "passed"
    assert (
        step2.gate_state == "provider_independent_quality_promotion_held_live_gap_open"
    )
    assert step2.promotion.decision.promotion_allowed is False

    step3 = evaluate_quality_promotion_gate(
        QualityGateEvidence(
            fixture_replay=_fixture_quality_readback(),
            executor_health=_online_executor_health(),
            live_replay=_live_replay_readback(),
            rollout_policy=_approved_rollout_policy(),
        )
    )
    assert step3.status == "passed"
    assert step3.promotion.decision.decision == "promote_provider_auto"
    assert step3.authority.authority_granted is False
    assert step3.effect_counts.provider_calls == 0
    assert step3.effect_counts.canonical_writes == 0
