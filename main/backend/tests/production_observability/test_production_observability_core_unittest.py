from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.production_observability import (  # noqa: E402
    CANARY_ROUTE_DECISION_CONTRACT_VERSION,
    CONTINUITY_REASON,
    OBSERVABILITY_CONTRACT_VERSION,
    SOURCE_CONTRACT_VERSIONS,
    STOP_REASON,
    AlertDirection,
    AlertRule,
    AlertState,
    AlertTransition,
    AlertTransitionReason,
    CanaryRouteAction,
    ContinuityReason,
    ContinueRequest,
    MetricFamily,
    Observation,
    ObservationReceipt,
    ReceiptScope,
    ReceiptValidationCode,
    StopReason,
    StopRequest,
    decide_canary_route,
    evaluate_alert_rule,
    make_observation,
    make_observation_receipt,
    validate_production_receipt,
)
from app.services.ingest.canary_handoff import CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION  # noqa: E402


OBSERVED_AT = "2026-09-05T00:00:00+00:00"
RECEIPT_AT = "2026-09-05T00:01:00+00:00"


def observation(
    observation_id: str,
    metric_family: MetricFamily,
    value: float,
    *,
    domain: str = "news.example",
    route: str = "frontdoor",
    release_version: str = "r7",
    observed_at: str = OBSERVED_AT,
) -> Observation:
    return make_observation(
        observation_id=observation_id,
        observed_at=observed_at,
        source_contract_version=CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION,
        metric_family=metric_family,
        domain=domain,
        route=route,
        release_version=release_version,
        value=value,
        sample_count=10,
    )


def rules() -> tuple[AlertRule, AlertRule, AlertRule]:
    return (
        AlertRule(
            rule_id="domain-rejection",
            metric_family=MetricFamily.DOMAIN_REJECTION_RATE,
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            trigger_threshold=0.8,
            recover_threshold=0.5,
        ),
        AlertRule(
            rule_id="route-error",
            metric_family=MetricFamily.ROUTE_ERROR_RATE,
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            trigger_threshold=0.2,
            recover_threshold=0.1,
        ),
        AlertRule(
            rule_id="release-error",
            metric_family=MetricFamily.RELEASE_VERSION_ERROR_RATE,
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            trigger_threshold=0.2,
            recover_threshold=0.1,
        ),
    )


def healthy_observations() -> tuple[Observation, ...]:
    return (
        observation("domain-ok", MetricFamily.DOMAIN_REJECTION_RATE, 0.1),
        observation("route-ok", MetricFamily.ROUTE_ERROR_RATE, 0.02),
        observation("release-ok", MetricFamily.RELEASE_VERSION_ERROR_RATE, 0.03),
    )


def triggered_observations() -> tuple[Observation, ...]:
    return (
        observation("domain-bad", MetricFamily.DOMAIN_REJECTION_RATE, 0.95),
        observation("route-ok", MetricFamily.ROUTE_ERROR_RATE, 0.02),
        observation("release-ok", MetricFamily.RELEASE_VERSION_ERROR_RATE, 0.03),
    )


def receipt(
    scope: ReceiptScope,
    observations: tuple[Observation, ...],
    *,
    receipt_id: str = "receipt-r7",
) -> ObservationReceipt:
    return make_observation_receipt(
        scope=scope,
        receipt_id=receipt_id,
        observed_at=RECEIPT_AT,
        domain="news.example",
        route="frontdoor",
        release_version="r7",
        issuer="operations" if scope is ReceiptScope.PRODUCTION else f"{scope.value}-runner",
        source_ref="fixture://local" if scope is not ReceiptScope.PRODUCTION else "prod://canary/r7",
        observations=observations,
    )


def continue_request() -> ContinueRequest:
    return ContinueRequest(
        requested_by="release-owner",
        requested_at=RECEIPT_AT,
        release_version="r7",
        reason=ContinuityReason.OPERATOR_CONTINUE,
    )


class TypedObservationReceiptTestCase(unittest.TestCase):
    def test_observation_is_frozen_and_binds_required_labels(self) -> None:
        item = healthy_observations()[0]
        digest = item.digest

        with self.assertRaises(AttributeError):
            item.value = 0.9  # type: ignore[misc]
        with self.assertRaises(TypeError):
            item.labels["unexpected"] = "label"  # type: ignore[index]
        self.assertEqual(item.digest, digest)
        self.assertEqual(item.contract_version, OBSERVABILITY_CONTRACT_VERSION)
        self.assertEqual(item.to_dict()["release_version"], "r7")

    def test_release_label_is_required(self) -> None:
        with self.assertRaises(ValueError):
            observation("missing-release", MetricFamily.DOMAIN_REJECTION_RATE, 0.1, release_version=" ")

    def test_receipt_scopes_have_distinct_contract_and_kind(self) -> None:
        local = receipt(ReceiptScope.LOCAL_FIXTURE, healthy_observations(), receipt_id="local-r7")
        staging = receipt(ReceiptScope.STAGING, healthy_observations(), receipt_id="staging-r7")
        production = receipt(ReceiptScope.PRODUCTION, healthy_observations(), receipt_id="production-r7")

        self.assertNotEqual(local.contract_version, staging.contract_version)
        self.assertNotEqual(staging.contract_version, production.contract_version)
        self.assertNotEqual(local.artifact_kind, production.artifact_kind)
        self.assertEqual(
            validate_production_receipt(production, observations=healthy_observations()),
            (ReceiptValidationCode.VALID,),
        )
        self.assertIn(
            ReceiptValidationCode.WRONG_SCOPE,
            validate_production_receipt(staging, observations=healthy_observations()),
        )


class AlertEvaluatorTestCase(unittest.TestCase):
    def test_trigger_and_recover_states_are_closed_and_ordered(self) -> None:
        rule = rules()[0]
        old = observation("old-low", MetricFamily.DOMAIN_REJECTION_RATE, 0.1)
        breach = observation(
            "new-high",
            MetricFamily.DOMAIN_REJECTION_RATE,
            0.9,
            observed_at="2026-09-05T00:00:30+00:00",
        )
        recovery = observation(
            "recovered",
            MetricFamily.DOMAIN_REJECTION_RATE,
            0.4,
            observed_at="2026-09-05T00:00:50+00:00",
        )

        triggered = evaluate_alert_rule(rule, (breach, old))
        still_bad = evaluate_alert_rule(rule, (breach,), previous_state=AlertState.TRIGGERED)
        recovered = evaluate_alert_rule(rule, (recovery,), previous_state=AlertState.TRIGGERED)
        empty = evaluate_alert_rule(rule, ())

        self.assertEqual(triggered.state, AlertState.TRIGGERED)
        self.assertEqual(triggered.transition, AlertTransition.TRIGGERED)
        self.assertEqual(triggered.reason, AlertTransitionReason.TRIGGER_THRESHOLD_CROSSED)
        self.assertEqual(still_bad.reason, AlertTransitionReason.STILL_TRIGGERED)
        self.assertEqual(recovered.state, AlertState.RECOVERED)
        self.assertEqual(recovered.transition, AlertTransition.RECOVERED)
        self.assertEqual(empty.state, AlertState.UNKNOWN)

    def test_below_direction_uses_lower_trigger_and_higher_recover(self) -> None:
        rule = AlertRule(
            rule_id="success-rate-floor",
            metric_family=MetricFamily.ROUTE_ERROR_RATE,
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            trigger_threshold=0.2,
            recover_threshold=0.5,
            direction=AlertDirection.BELOW,
        )
        low = observation("low", MetricFamily.ROUTE_ERROR_RATE, 0.1)
        recovered = observation("recovered", MetricFamily.ROUTE_ERROR_RATE, 0.6)

        self.assertEqual(evaluate_alert_rule(rule, (low,)).state, AlertState.TRIGGERED)
        self.assertEqual(
            evaluate_alert_rule(rule, (recovered,), previous_state=AlertState.TRIGGERED).state,
            AlertState.RECOVERED,
        )


class CanaryRouteDecisionTestCase(unittest.TestCase):
    def test_missing_production_receipt_never_promotes(self) -> None:
        decision = decide_canary_route(
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            observations=healthy_observations(),
            alert_rules=rules(),
            continue_request=continue_request(),
        )

        self.assertEqual(decision.action, CanaryRouteAction.HOLD)
        self.assertFalse(decision.promotion_allowed)
        self.assertEqual(decision.stop_reason, StopReason.MISSING_PRODUCTION_RECEIPT)
        self.assertEqual(decision.receipt_validation, (ReceiptValidationCode.CONTRACT_VERSION_INVALID,))
        self.assertFalse(decision.authority)

    def test_local_and_staging_receipts_cannot_be_promotion_receipts(self) -> None:
        for scope in (ReceiptScope.LOCAL_FIXTURE, ReceiptScope.STAGING):
            with self.subTest(scope=scope):
                decision = decide_canary_route(
                    domain="news.example",
                    route="frontdoor",
                    release_version="r7",
                    observations=healthy_observations(),
                    alert_rules=rules(),
                    production_receipt=receipt(scope, healthy_observations()),
                    continue_request=continue_request(),
                )

                self.assertEqual(decision.action, CanaryRouteAction.HOLD)
                self.assertFalse(decision.promotion_allowed)
                self.assertEqual(decision.stop_reason, StopReason.RECEIPT_SCOPE_NOT_PRODUCTION)
                self.assertIn(ReceiptValidationCode.WRONG_SCOPE, decision.receipt_validation)

    def test_valid_production_receipt_with_continue_allows_continue(self) -> None:
        production = receipt(ReceiptScope.PRODUCTION, healthy_observations(), receipt_id="prod-r7")
        decision = decide_canary_route(
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            observations=healthy_observations(),
            alert_rules=rules(),
            production_receipt=production,
            continue_request=continue_request(),
        )

        self.assertEqual(decision.contract_version, CANARY_ROUTE_DECISION_CONTRACT_VERSION)
        self.assertEqual(decision.action, CanaryRouteAction.CONTINUE)
        self.assertTrue(decision.promotion_allowed)
        self.assertEqual(decision.stop_reason, StopReason.NO_STOP_CONDITION)
        self.assertEqual(decision.precedence, (StopReason.NO_STOP_CONDITION,))
        self.assertTrue(decision.receipt_valid)
        self.assertEqual(decision.receipt_scope, ReceiptScope.PRODUCTION)
        self.assertFalse(decision.authority)
        self.assertEqual(decision.derived_as, "view")
        self.assertEqual(
            decision.alert_evaluations[0].latest_observation_id,
            "domain-ok",
        )

    def test_continue_is_required_even_when_production_receipt_is_valid(self) -> None:
        decision = decide_canary_route(
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            observations=healthy_observations(),
            alert_rules=rules(),
            production_receipt=receipt(ReceiptScope.PRODUCTION, healthy_observations()),
        )

        self.assertEqual(decision.action, CanaryRouteAction.HOLD)
        self.assertFalse(decision.promotion_allowed)
        self.assertEqual(decision.stop_reason, StopReason.CONTINUE_NOT_REQUESTED)

    def test_missing_receipt_never_promotes_but_alert_can_tighten_to_rollback(self) -> None:
        decision = decide_canary_route(
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            observations=triggered_observations(),
            alert_rules=rules(),
            continue_request=continue_request(),
        )

        self.assertEqual(decision.action, CanaryRouteAction.ROLLBACK)
        self.assertFalse(decision.promotion_allowed)
        self.assertEqual(decision.stop_reason, StopReason.ALERT_TRIGGERED)
        self.assertEqual(decision.precedence, (StopReason.ALERT_TRIGGERED,))
        self.assertFalse(decision.receipt_valid)

    def test_alert_has_precedence_over_continue_with_valid_receipt(self) -> None:
        decision = decide_canary_route(
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            observations=triggered_observations(),
            alert_rules=rules(),
            production_receipt=receipt(ReceiptScope.PRODUCTION, triggered_observations()),
            continue_request=continue_request(),
        )

        self.assertEqual(decision.action, CanaryRouteAction.ROLLBACK)
        self.assertFalse(decision.promotion_allowed)
        self.assertEqual(decision.stop_reason, StopReason.ALERT_TRIGGERED)
        self.assertEqual(decision.precedence, (StopReason.ALERT_TRIGGERED,))

    def test_explicit_stop_has_highest_precedence(self) -> None:
        stop = StopRequest(
            request_id="stop-1",
            requested_by="release-owner",
            requested_at=RECEIPT_AT,
            release_version="r7",
            reason="release freeze",
        )
        decision = decide_canary_route(
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            observations=triggered_observations(),
            alert_rules=rules(),
            explicit_stop=stop,
            continue_request=continue_request(),
        )

        self.assertEqual(decision.action, CanaryRouteAction.ROLLBACK)
        self.assertEqual(decision.stop_reason, StopReason.EXPLICIT_STOP)
        self.assertEqual(decision.precedence[0], StopReason.EXPLICIT_STOP)
        self.assertIn(StopReason.ALERT_TRIGGERED, decision.precedence)
        self.assertFalse(decision.promotion_allowed)

    def test_tampered_observation_binding_blocks_promotion(self) -> None:
        production = receipt(ReceiptScope.PRODUCTION, healthy_observations())
        tampered = ObservationReceipt(
            receipt_id=production.receipt_id,
            observed_at=production.observed_at,
            scope=ReceiptScope.PRODUCTION,
            contract_version=production.contract_version,
            artifact_kind=production.artifact_kind,
            domain=production.domain,
            route=production.route,
            release_version=production.release_version,
            issuer=production.issuer,
            source_ref=production.source_ref,
            observation_ids=production.observation_ids,
            observation_digests={"domain-ok": "not-the-bound-digest"},
        )
        decision = decide_canary_route(
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            observations=healthy_observations(),
            alert_rules=rules(),
            production_receipt=tampered,
            continue_request=continue_request(),
        )

        self.assertEqual(decision.action, CanaryRouteAction.HOLD)
        self.assertFalse(decision.promotion_allowed)
        self.assertEqual(decision.stop_reason, StopReason.RECEIPT_BINDING_INVALID)
        self.assertIn(ReceiptValidationCode.OBSERVATION_DIGEST_INVALID, decision.receipt_validation)

    def test_decision_does_not_authorize_production(self) -> None:
        decision = decide_canary_route(
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            observations=healthy_observations(),
            alert_rules=rules(),
            production_receipt=receipt(ReceiptScope.PRODUCTION, healthy_observations()),
            continue_request=continue_request(),
        )
        payload = decision.to_dict()

        self.assertIs(decision.authority, False)
        self.assertEqual(payload["authority"], False)
        self.assertEqual(payload["derived_as"], "view")
        with self.assertRaises(AttributeError):
            decision.action = CanaryRouteAction.HOLD  # type: ignore[misc]


class ContractBoundaryTestCase(unittest.TestCase):
    def test_closed_wordlists_are_declared(self) -> None:
        self.assertEqual(
            {item.value for item in STOP_REASON},
            {
                "explicit_stop",
                "alert_triggered",
                "receipt_scope_not_production",
                "receipt_contract_invalid",
                "receipt_binding_invalid",
                "receipt_time_invalid",
                "missing_production_receipt",
                "no_production_observations",
                "alert_evaluation_unknown",
                "continue_not_requested",
                "no_stop_condition",
            },
        )
        self.assertEqual(
            {item.value for item in CONTINUITY_REASON},
            {
                "operator_continue",
                "automatic_policy_continue",
            },
        )
        self.assertIn(CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION, SOURCE_CONTRACT_VERSIONS)

    def test_receipt_payload_is_copy_safe_but_content_frozen(self) -> None:
        item = receipt(ReceiptScope.PRODUCTION, healthy_observations())
        snapshot = copy.deepcopy(item.to_dict())
        item.to_dict()["receipt_id"] = "changed"

        self.assertEqual(snapshot["receipt_id"], "receipt-r7")
        with self.assertRaises(TypeError):
            item.observation_digests["domain-ok"] = "changed"  # type: ignore[index]
