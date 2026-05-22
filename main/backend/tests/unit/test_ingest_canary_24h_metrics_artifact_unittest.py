from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from scripts.check_ingest_canary_24h_metrics_artifact import (
    CONTRACT_VERSION,
    build_24h_metrics_artifact,
    read_24h_metrics_artifact,
    run_24h_metrics_artifact_gate,
    validate_24h_metrics_artifact,
)


pytestmark = pytest.mark.unit


class IngestCanary24hMetricsArtifactTest(unittest.TestCase):
    def test_fixture_artifact_shape_keeps_live_24h_claim_open(self) -> None:
        artifact = build_24h_metrics_artifact()

        self.assertEqual(validate_24h_metrics_artifact(artifact), [])
        self.assertEqual(artifact["contract_version"], CONTRACT_VERSION)
        self.assertTrue(artifact["deterministic_fixture"])
        self.assertEqual(artifact["window"]["window_hours"], 24)
        self.assertFalse(artifact["window"]["live_window_observed"])
        self.assertEqual(artifact["single_url_first_allocation"]["source_mode"], "url_execution")
        self.assertEqual(artifact["single_url_first_allocation"]["allocation_policy"], "single_url_first")
        self.assertEqual(artifact["metrics_24h"]["total_attempts"], 4)
        self.assertEqual(artifact["metrics_24h"]["rejection_rate"], 0.25)
        self.assertEqual(artifact["metrics_24h"]["inserted_valid_ratio"], 1.0)
        self.assertFalse(artifact["live_boundaries"]["live_production_canary_claim"])
        self.assertFalse(artifact["live_boundaries"]["metric_24h_live_readback_claim"])
        self.assertFalse(artifact["live_boundaries"]["closure_claim"])

    def test_write_read_gate_round_trips_artifact_and_digest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ingest-canary-24h-metrics-") as tmp_dir:
            path = Path(tmp_dir) / "nested" / "artifact.json"

            result = run_24h_metrics_artifact_gate(path=path)

            self.assertEqual(result["status"], "passed")
            self.assertTrue(result["write_performed"])
            self.assertTrue(result["readback_performed"])
            self.assertTrue(path.is_file())
            self.assertEqual(result["readback_record"], read_24h_metrics_artifact(path))
            self.assertEqual(validate_24h_metrics_artifact(result["readback_record"]), [])

    def test_validator_rejects_live_24h_closure_claim(self) -> None:
        artifact = build_24h_metrics_artifact()
        artifact["live_boundaries"]["metric_24h_live_readback_claim"] = True

        errors = validate_24h_metrics_artifact(artifact)

        self.assertTrue(any("metric_24h_live_readback_claim" in error for error in errors))
        self.assertTrue(any("snapshot_digest" in error for error in errors))

    def test_validator_rejects_metric_rate_drift(self) -> None:
        artifact = build_24h_metrics_artifact()
        artifact["metrics_24h"]["rejection_rate"] = 0.5

        errors = validate_24h_metrics_artifact(artifact)

        self.assertTrue(any("rejection_rate" in error for error in errors))
        self.assertTrue(any("snapshot_digest" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
