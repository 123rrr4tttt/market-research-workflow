from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.production_observability import (  # noqa: E402
    PRODUCTION_OBSERVABILITY_RUNTIME_CONTRACT_VERSION,
    RUNTIME_PROJECTION_CONTRACT_VERSION,
    RUNTIME_STATE_KEY,
    AlertDirection,
    CanaryRouteAction,
    ContinuityReason,
    ContinueRequest,
    MetricFamily,
    Observation,
    ObservationReceipt,
    ReceiptScope,
    ReceiptValidationCode,
    StopReason,
    install_production_observability,
    make_observation,
    make_observation_receipt,
    parse_production_observability_config,
    validate_production_receipt,
)
from app.production_observability.errors import (  # noqa: E402
    ObservabilityTypeError,
    ObservabilityValueError,
)
from app.services.ingest.canary_handoff import (  # noqa: E402
    CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION,
)


OBSERVED_AT = "2026-09-05T00:00:00+00:00"
RECEIPT_AT = "2026-09-05T00:01:00+00:00"
EVALUATED_AT = "2026-09-05T00:02:00+00:00"


def config_mapping(*, canary_route_enabled: bool = True) -> dict:
    return {
        "contract_version": PRODUCTION_OBSERVABILITY_RUNTIME_CONTRACT_VERSION,
        "runtime_id": "r7-runtime",
        "domain": "News.Example",
        "route": "FrontDoor",
        "release_version": "r7",
        "canary_route_enabled": canary_route_enabled,
        "alert_rules": [
            {
                "rule_id": "domain-rejection",
                "metric_family": MetricFamily.DOMAIN_REJECTION_RATE,
                "domain": "news.example",
                "route": "frontdoor",
                "release_version": "r7",
                "trigger_threshold": 0.8,
                "recover_threshold": 0.5,
            },
            {
                "rule_id": "route-error",
                "metric_family": "route.error_rate",
                "domain": "news.example",
                "route": "frontdoor",
                "release_version": "r7",
                "trigger_threshold": 0.2,
                "recover_threshold": 0.1,
                "direction": AlertDirection.ABOVE,
            },
        ],
    }


def observation(
    observation_id: str,
    metric_family: MetricFamily,
    value: float,
) -> Observation:
    return make_observation(
        observation_id=observation_id,
        observed_at=OBSERVED_AT,
        source_contract_version=CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION,
        metric_family=metric_family,
        domain="news.example",
        route="frontdoor",
        release_version="r7",
        value=value,
        sample_count=10,
    )


def healthy_observations() -> tuple[Observation, Observation, Observation]:
    return (
        observation("domain-ok", MetricFamily.DOMAIN_REJECTION_RATE, 0.1),
        observation("route-ok", MetricFamily.ROUTE_ERROR_RATE, 0.02),
        observation("release-ok", MetricFamily.RELEASE_VERSION_ERROR_RATE, 0.03),
    )


def triggered_observations() -> tuple[Observation, Observation, Observation]:
    return (
        observation("domain-bad", MetricFamily.DOMAIN_REJECTION_RATE, 0.95),
        observation("route-ok", MetricFamily.ROUTE_ERROR_RATE, 0.02),
        observation("release-ok", MetricFamily.RELEASE_VERSION_ERROR_RATE, 0.03),
    )


def receipt(
    observations: tuple[Observation, ...],
    *,
    receipt_id: str = "receipt-r7-runtime",
) -> ObservationReceipt:
    return make_observation_receipt(
        scope=ReceiptScope.PRODUCTION,
        receipt_id=receipt_id,
        observed_at=RECEIPT_AT,
        domain="news.example",
        route="frontdoor",
        release_version="r7",
        issuer="operations",
        source_ref="prod://canary/r7",
        observations=observations,
    )


def continue_request() -> ContinueRequest:
    return ContinueRequest(
        requested_by="release-owner",
        requested_at=RECEIPT_AT,
        release_version="r7",
        reason=ContinuityReason.OPERATOR_CONTINUE,
    )


class ConfigLoadTestCase(unittest.TestCase):
    def test_explicit_mapping_loads_closed_rules_and_normalizes_binding(self) -> None:
        config = parse_production_observability_config(config_mapping())

        self.assertEqual(config.contract_version, PRODUCTION_OBSERVABILITY_RUNTIME_CONTRACT_VERSION)
        self.assertEqual(config.domain, "News.Example")
        self.assertEqual(len(config.alert_rules), 2)
        self.assertEqual(config.alert_rules[1].direction, AlertDirection.ABOVE)
        self.assertEqual(config.to_dict()["domain"], "news.example")

    def test_unknown_or_invalid_config_fails_closed(self) -> None:
        unknown = config_mapping()
        unknown["unexpected"] = True
        duplicate = config_mapping()
        duplicate["alert_rules"][1]["rule_id"] = duplicate["alert_rules"][0]["rule_id"]
        wrong_contract = config_mapping()
        wrong_contract["contract_version"] = "production.observability.runtime.v0"
        loose_boolean = config_mapping()
        loose_boolean["canary_route_enabled"] = "true"

        with self.assertRaises(ObservabilityValueError):
            parse_production_observability_config(unknown)
        with self.assertRaises(ObservabilityValueError):
            parse_production_observability_config(duplicate)
        with self.assertRaises(ObservabilityValueError):
            parse_production_observability_config(wrong_contract)
        with self.assertRaises(ObservabilityTypeError):
            parse_production_observability_config(loose_boolean)


class InstallRuntimeTestCase(unittest.TestCase):
    def test_install_exposes_one_controller_on_composition_root_state(self) -> None:
        target = SimpleNamespace(state=SimpleNamespace())
        controller = install_production_observability(target, config_mapping())

        self.assertIs(getattr(target.state, RUNTIME_STATE_KEY), controller)
        self.assertFalse(controller.route_advice.authority)
        self.assertEqual(controller.route_advice.action, CanaryRouteAction.HOLD)
        with self.assertRaises(ObservabilityValueError):
            install_production_observability(target, config_mapping())

    def test_target_without_state_fails_closed(self) -> None:
        with self.assertRaises(ObservabilityTypeError):
            install_production_observability(SimpleNamespace(), config_mapping())


class RuntimeEvaluateTestCase(unittest.TestCase):
    def test_valid_production_receipt_continues_and_emits_derived_projection(self) -> None:
        controller = install_production_observability(SimpleNamespace(state=SimpleNamespace()), config_mapping())
        observations = healthy_observations()

        result = controller.evaluate(
            observations=observations,
            production_receipt=receipt(observations),
            continue_request=continue_request(),
            evaluated_at=EVALUATED_AT,
        )

        self.assertEqual(result.decision.action, CanaryRouteAction.CONTINUE)
        self.assertTrue(result.decision.promotion_allowed)
        self.assertIs(result.canary_route.authority, False)
        self.assertIs(result.authority, False)
        self.assertEqual(result.projection_contract_version, RUNTIME_PROJECTION_CONTRACT_VERSION)
        self.assertEqual(
            validate_production_receipt(result.receipt, observations=observations),
            (ReceiptValidationCode.VALID,),
        )
        self.assertIsNot(result.receipt.receipt_id, receipt(observations).receipt_id)

    def test_missing_or_invalid_receipt_never_promotes(self) -> None:
        controller = install_production_observability(SimpleNamespace(state=SimpleNamespace()), config_mapping())
        observations = healthy_observations()
        invalid_receipt = dataclasses.replace(
            receipt(observations),
            observation_digests={item.observation_id: "0" * 64 for item in observations},
        )

        missing = controller.evaluate(
            observations=observations,
            continue_request=continue_request(),
            evaluated_at=EVALUATED_AT,
        )
        invalid = controller.evaluate(
            observations=observations,
            production_receipt=invalid_receipt,
            continue_request=continue_request(),
            evaluated_at=EVALUATED_AT,
        )

        self.assertIs(missing.decision.promotion_allowed, False)
        self.assertIs(invalid.decision.promotion_allowed, False)
        self.assertEqual(missing.decision.stop_reason, StopReason.MISSING_PRODUCTION_RECEIPT)
        self.assertEqual(invalid.decision.stop_reason, StopReason.RECEIPT_BINDING_INVALID)
        self.assertIn(ReceiptValidationCode.OBSERVATION_DIGEST_INVALID, invalid.decision.receipt_validation)

    def test_disabled_canary_route_refuses_continue(self) -> None:
        controller = install_production_observability(
            SimpleNamespace(state=SimpleNamespace()),
            config_mapping(canary_route_enabled=False),
        )
        observations = healthy_observations()

        result = controller.evaluate(
            observations=observations,
            production_receipt=receipt(observations),
            continue_request=continue_request(),
            evaluated_at=EVALUATED_AT,
        )

        self.assertEqual(result.decision.action, CanaryRouteAction.HOLD)
        self.assertFalse(result.canary_route.canary_route_enabled)
        self.assertFalse(result.decision.promotion_allowed)

    def test_explicit_stop_has_precedence_and_is_latched(self) -> None:
        target = SimpleNamespace(state=SimpleNamespace())
        controller = install_production_observability(target, config_mapping())
        observations = healthy_observations()
        controller.request_stop(
            request_id="stop-1",
            requested_by="release-owner",
            requested_at=RECEIPT_AT,
            reason="operator stop",
        )

        result = controller.evaluate(
            observations=observations,
            production_receipt=receipt(observations),
            continue_request=continue_request(),
            evaluated_at=EVALUATED_AT,
        )

        self.assertEqual(result.decision.action, CanaryRouteAction.ROLLBACK)
        self.assertEqual(result.decision.stop_reason, StopReason.EXPLICIT_STOP)
        self.assertFalse(result.decision.promotion_allowed)

    def test_runtime_failure_latch_is_idempotent_and_forces_rollback(self) -> None:
        controller = install_production_observability(
            SimpleNamespace(state=SimpleNamespace()),
            config_mapping(),
        )

        first = controller.latch_runtime_failure(
            request_id="observation-failure-1",
            reason="observer unavailable",
            observed_at=RECEIPT_AT,
        )
        second = controller.latch_runtime_failure(
            request_id="observation-failure-2",
            reason="another observer failure",
            observed_at=EVALUATED_AT,
        )
        advice_before_evaluation = controller.route_advice
        result = controller.evaluate(
            observations=healthy_observations(),
            evaluated_at=EVALUATED_AT,
        )

        self.assertIs(first, second)
        self.assertEqual(first.request_id, "observation-failure-1")
        self.assertEqual(advice_before_evaluation.action, CanaryRouteAction.ROLLBACK)
        self.assertFalse(advice_before_evaluation.promotion_allowed)
        self.assertEqual(result.decision.action, CanaryRouteAction.ROLLBACK)
        self.assertEqual(result.decision.stop_reason, StopReason.EXPLICIT_STOP)
        self.assertFalse(result.decision.promotion_allowed)

    def test_unreceipted_http_error_can_only_tighten_route_to_rollback(self) -> None:
        controller = install_production_observability(
            SimpleNamespace(state=SimpleNamespace()),
            config_mapping(),
        )

        result = controller.observe_http_request(
            observation_id="http-500",
            status_code=500,
            observed_at=OBSERVED_AT,
        )

        self.assertEqual(result.decision.action, CanaryRouteAction.ROLLBACK)
        self.assertEqual(result.decision.stop_reason, StopReason.ALERT_TRIGGERED)
        self.assertFalse(result.decision.receipt_valid)
        self.assertFalse(result.decision.promotion_allowed)
        self.assertFalse(result.authority)

        healthy_without_receipt = controller.observe_http_request(
            observation_id="health-200",
            status_code=200,
            observed_at=RECEIPT_AT,
        )
        self.assertEqual(healthy_without_receipt.decision.action, CanaryRouteAction.ROLLBACK)
        self.assertEqual(
            healthy_without_receipt.decision.stop_reason,
            StopReason.ALERT_TRIGGERED,
        )
        self.assertEqual(controller.route_advice.action, CanaryRouteAction.ROLLBACK)

    def test_alert_state_persists_between_evaluations(self) -> None:
        controller = install_production_observability(SimpleNamespace(state=SimpleNamespace()), config_mapping())
        bad = triggered_observations()
        good = healthy_observations()

        triggered = controller.evaluate(
            observations=bad,
            production_receipt=receipt(bad, receipt_id="receipt-bad"),
            continue_request=continue_request(),
            evaluated_at=EVALUATED_AT,
        )
        recovered = controller.evaluate(
            observations=good,
            production_receipt=receipt(good, receipt_id="receipt-good"),
            continue_request=continue_request(),
            evaluated_at=EVALUATED_AT,
        )

        self.assertEqual(triggered.decision.action, CanaryRouteAction.ROLLBACK)
        self.assertEqual(triggered.decision.stop_reason, StopReason.ALERT_TRIGGERED)
        self.assertEqual(recovered.decision.action, CanaryRouteAction.CONTINUE)
        self.assertTrue(recovered.decision.promotion_allowed)


class RuntimeProjectionFailClosedTestCase(unittest.TestCase):
    def test_projection_type_refuses_authority_reshaping(self) -> None:
        from app.production_observability import RuntimeEvaluation

        with self.assertRaises(ObservabilityTypeError):
            type("AuthorityRuntime", (RuntimeEvaluation,), {})
