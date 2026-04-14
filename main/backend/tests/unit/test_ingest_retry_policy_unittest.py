from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest.retry_policy import (
        RETRY_CLASS_PERMANENT,
        RETRY_CLASS_TRANSIENT,
        build_retry_observability,
        classify_retry_reason,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class IngestRetryPolicyUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest retry policy unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_classify_retry_reason_transient_and_permanent(self):
        fetch_reason, fetch_class = classify_retry_reason("fetch_failed")
        invalid_reason, invalid_class = classify_retry_reason("invalid_url")

        self.assertEqual(fetch_reason, "fetch_failed")
        self.assertEqual(fetch_class, RETRY_CLASS_TRANSIENT)
        self.assertEqual(invalid_reason, "invalid_url")
        self.assertEqual(invalid_class, RETRY_CLASS_PERMANENT)

    def test_build_retry_observability_aggregates_counts_by_reason_and_class(self):
        payload = {
            "reason_code": "fetch_failed",
            "rejection_breakdown": {
                "fetch_failed": 1,
                "invalid_url": 3,
            },
            "crawler_dispatch": {
                "attempt_count": 3,
            },
            "retry_events": [
                {"reason": "rate_limited", "count": 2},
            ],
        }

        out = build_retry_observability(payload)

        reason_counts = out.get("retry_count_by_reason") or {}
        class_counts = out.get("retry_count_by_class") or {}

        self.assertEqual(reason_counts.get("fetch_failed"), 1)
        self.assertEqual(reason_counts.get("crawler_dispatch_retry"), 2)
        self.assertEqual(reason_counts.get("rate_limited"), 2)
        self.assertNotIn("invalid_url", reason_counts)
        self.assertEqual(class_counts.get(RETRY_CLASS_TRANSIENT), 5)
        self.assertEqual(class_counts.get(RETRY_CLASS_PERMANENT), 0)
        self.assertTrue(bool(out.get("retryable")))


if __name__ == "__main__":
    unittest.main()
