from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest.frontdoor_slo import (
        CONTRACT_VERSION,
        build_frontdoor_slo_payload,
        new_frontdoor_slo_summary,
        record_frontdoor_slo_observation,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class IngestFrontdoorSloUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"frontdoor SLO unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_frontdoor_slo_payload_reports_tri_state_p95_and_retry(self) -> None:
        summary = new_frontdoor_slo_summary()
        record_frontdoor_slo_observation(
            summary,
            {
                "dashboard_status": "success",
                "latency_ms": 90,
                "retryable": False,
                "reason_code": "ok",
            },
        )
        record_frontdoor_slo_observation(
            summary,
            {
                "dashboard_status": "degraded_success",
                "latency_ms": 210,
                "retryable": True,
                "reason_code": "fetch_failed",
                "retry_observability": {
                    "retry_count_by_reason": {"fetch_failed": 1},
                    "retry_count_by_class": {"transient": 1, "permanent": 0},
                },
            },
        )
        record_frontdoor_slo_observation(
            summary,
            {
                "dashboard_status": "failed",
                "latency_ms": 430,
                "retryable": False,
                "reason_code": "domain_blocked",
            },
        )

        payload = build_frontdoor_slo_payload(summary)

        self.assertEqual(payload["contract_version"], CONTRACT_VERSION)
        self.assertEqual(payload["sample_size"], 3)
        self.assertEqual(payload["dashboard_status_counts"]["success"], 1)
        self.assertEqual(payload["dashboard_status_counts"]["degraded_success"], 1)
        self.assertEqual(payload["dashboard_status_counts"]["failed"], 1)
        self.assertEqual(payload["success_or_degraded_rate"], 0.666667)
        self.assertEqual(payload["p95_latency_ms"], 430.0)
        self.assertEqual(payload["retryable_samples"], 1)
        self.assertEqual(payload["retryable_rate"], 0.333333)
        self.assertEqual(payload["retry_count_by_reason"]["fetch_failed"], 1)
        self.assertEqual(payload["retry_count_by_class"]["transient"], 1)
        self.assertFalse(payload["live_24h_claim"])
        self.assertFalse(payload["closure_claim"])


if __name__ == "__main__":
    unittest.main()
