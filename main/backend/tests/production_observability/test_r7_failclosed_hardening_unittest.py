from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.production_observability import (  # noqa: E402
    CanaryRouteAction,
    CanaryRouteDecision,
    ContinueRequest,
    MetricFamily,
    Observation,
    ObservationReceipt,
    ReceiptScope,
    ReceiptValidationCode,
    StopReason,
    ContinuityReason,
    decide_canary_route,
    make_observation,
    make_observation_receipt,
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


def production_receipt(
    observations: tuple[Observation, ...],
) -> ObservationReceipt:
    return make_observation_receipt(
        scope=ReceiptScope.PRODUCTION,
        receipt_id="receipt-r7-hardening",
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


def healthy_decision() -> CanaryRouteDecision:
    observations = healthy_observations()
    return decide_canary_route(
        domain="news.example",
        route="frontdoor",
        release_version="r7",
        observations=observations,
        alert_rules=(),
        production_receipt=production_receipt(observations),
        continue_request=continue_request(),
    )


class DecisionFailClosedTestCase(unittest.TestCase):
    def test_decision_authority_and_view_are_runtime_invariants(self) -> None:
        decision = healthy_decision()

        self.assertIs(decision.authority, False)
        self.assertEqual(decision.to_dict()["derived_as"], "view")
        with self.assertRaises(ObservabilityTypeError):
            dataclasses.replace(decision, authority=True)
        with self.assertRaises(ObservabilityValueError):
            dataclasses.replace(decision, derived_as="runtime")

    def test_decision_type_is_closed_to_authority_reshaping_subclasses(self) -> None:
        with self.assertRaises(ObservabilityTypeError):
            type("MutableAuthorityDecision", (CanaryRouteDecision,), {})


class ReceiptDigestFailClosedTestCase(unittest.TestCase):
    def test_factory_binds_declared_digest_to_canonical_receipt(self) -> None:
        item = production_receipt(healthy_observations())

        self.assertEqual(item.declared_digest, item.digest)
        self.assertEqual(item.to_dict()["declared_digest"], item.digest)
        self.assertEqual(
            validate_production_receipt(item, observations=healthy_observations()),
            (ReceiptValidationCode.VALID,),
        )

    def test_changed_receipt_content_with_stale_declaration_is_invalid(self) -> None:
        item = production_receipt(healthy_observations())
        tampered = dataclasses.replace(item, release_version="r8")

        validation = validate_production_receipt(tampered, observations=healthy_observations())
        self.assertIn(ReceiptValidationCode.RECEIPT_DIGEST_INVALID, validation)
        self.assertIn(ReceiptValidationCode.OBSERVATION_RELEASE_MISMATCH, validation)

    def test_missing_or_changed_declared_digest_is_invalid(self) -> None:
        item = production_receipt(healthy_observations())
        missing = dataclasses.replace(item, declared_digest=None)
        changed = dataclasses.replace(item, declared_digest="0" * 64)

        self.assertIn(
            ReceiptValidationCode.RECEIPT_DIGEST_INVALID,
            validate_production_receipt(missing, observations=healthy_observations()),
        )
        self.assertEqual(
            validate_production_receipt(changed, observations=healthy_observations()),
            (ReceiptValidationCode.RECEIPT_DIGEST_INVALID,),
        )


class DuplicateObservationFailClosedTestCase(unittest.TestCase):
    def test_factory_rejects_duplicate_observation_ids(self) -> None:
        items = healthy_observations()

        with self.assertRaises(ValueError):
            production_receipt((*items, items[0]))

    def test_validation_rejects_duplicate_observation_input_ids(self) -> None:
        item = production_receipt(healthy_observations())
        duplicated = (*healthy_observations(), healthy_observations()[0])

        self.assertIn(
            ReceiptValidationCode.OBSERVATION_DUPLICATED,
            validate_production_receipt(item, observations=duplicated),
        )

    def test_duplicate_observation_input_holds_and_does_not_promote(self) -> None:
        receipt = production_receipt(healthy_observations())
        decision = decide_canary_route(
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            observations=(*healthy_observations(), healthy_observations()[0]),
            alert_rules=(),
            production_receipt=receipt,
            continue_request=continue_request(),
        )

        self.assertEqual(decision.action, CanaryRouteAction.HOLD)
        self.assertFalse(decision.promotion_allowed)
        self.assertEqual(decision.stop_reason, StopReason.RECEIPT_BINDING_INVALID)
        self.assertIn(
            ReceiptValidationCode.OBSERVATION_DUPLICATED,
            decision.receipt_validation,
        )

    def test_decision_consumes_an_observation_generator_once(self) -> None:
        decision = decide_canary_route(
            domain="news.example",
            route="frontdoor",
            release_version="r7",
            observations=iter(healthy_observations()),
            alert_rules=(),
            production_receipt=production_receipt(healthy_observations()),
            continue_request=continue_request(),
        )

        self.assertEqual(decision.action, CanaryRouteAction.CONTINUE)
        self.assertFalse(decision.authority)
