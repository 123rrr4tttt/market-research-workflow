from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.ingest.canary_handoff import CANARY_HANDOFF_CONTRACT_VERSION, CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION
from app.services.ingest.canary_metrics_readback import (
    build_canary_metrics_readback_record,
    read_canary_metrics_readback_record,
    run_canary_metrics_readback_gate,
    validate_canary_metrics_readback_record,
    write_canary_metrics_readback_record,
)


def _handoff_fixture() -> dict:
    return {
        "contract_version": CANARY_HANDOFF_CONTRACT_VERSION,
        "handoff_state": "partial_live_gap_open",
        "frontdoor_run": {
            "ingress_contract_version": "frontdoor.ingress.v1",
            "ingress_type": "source_library",
            "entrypoint": "ingest.url_pool",
            "source_mode": "url_execution",
            "project_key": "demo_proj",
            "source_url": "https://example.com/search?q=robotics",
            "route_hint": "search_shell",
            "fetch_strategy": "search_candidate_route",
        },
        "strict_gate_state": {
            "state": "strict_blocked",
            "strict_gate_enabled": True,
            "strict_gate_source": "settings.ingest_guardrail_rollout_mode:canary",
            "admission": "reject",
            "reason_code": "domain_blocked",
            "blocked": True,
            "blocked_stage": "pre_fetch_url_gate",
            "blocked_reason": "domain_blocked",
        },
        "rollout": {
            "channel": "canary",
            "rollout_mode": "canary",
            "project_key": "demo_proj",
            "canary_projects": ["demo_proj"],
            "canary_matched": True,
            "global_default_enabled": False,
            "decision_contract_version": "ingest.guardrail_rollout.v1",
        },
        "metrics_snapshot": {
            "contract_version": CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION,
            "metrics_payload_schema_version": "a9.v1",
            "sample_size": 1,
            "url_only_document_rate": 1.0,
            "empty_body_rate": 0.0,
            "reason_code_top_n": [{"reason_code": "domain_blocked", "count": 1, "rate": 1.0}],
            "adapter_hit_rate": [{"adapter": "source_library_frontdoor", "count": 1, "rate": 1.0}],
            "guardrail_rollout": {
                "contract_version": "ingest.guardrail_rollout.metrics.v1",
                "decision_contract_version": "ingest.guardrail_rollout.v1",
                "sample_size": 1,
                "strict_enabled_samples": 1,
                "canary_matched_samples": 1,
                "global_default_samples": 0,
                "strict_enabled_rate": 1.0,
                "canary_matched_rate": 1.0,
                "rollout_mode_counts": [{"key": "canary", "count": 1, "rate": 1.0}],
                "strict_gate_source_counts": [
                    {"key": "settings.ingest_guardrail_rollout_mode:canary", "count": 1, "rate": 1.0}
                ],
                "live_canary_validated": False,
                "closure_claim": False,
            },
            "counters": {"total_samples": 1, "url_only_documents": 1, "empty_body_documents": 0},
        },
        "live_canary_validated": False,
        "closure_claim": False,
        "remaining_live_run_gaps": [
            "demo_proj live canary execution has not been run against configured services",
            "24h rejection-rate and inserted-valid ratios have not been inspected",
        ],
    }


class IngestCanaryMetricsReadbackUnitTestCase(unittest.TestCase):
    def test_write_read_validate_canary_metrics_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(prefix="canary-metrics-readback-") as tmp_dir:
            path = Path(tmp_dir) / "snapshot.json"
            result = run_canary_metrics_readback_gate(handoff=_handoff_fixture(), path=path)

            self.assertEqual(result["status"], "passed")
            self.assertTrue(result["write_performed"])
            self.assertTrue(result["readback_performed"])
            self.assertTrue(path.is_file())
            record = result["readback_record"]
            self.assertEqual(record, read_canary_metrics_readback_record(path))
            self.assertEqual(record["project_key"], "demo_proj")
            self.assertTrue(record["canary_status"]["deterministic_metrics_ready"])
            self.assertTrue(record["canary_status"]["demo_proj_live_canary_open"])
            self.assertTrue(record["canary_status"]["metric_24h_readback_open"])
            self.assertFalse(record["live_production_canary_claim"])
            self.assertFalse(record["metric_24h_live_readback_claim"])
            self.assertFalse(record["closure_claim"])

    def test_digest_detects_readback_record_drift(self) -> None:
        record = build_canary_metrics_readback_record(handoff=_handoff_fixture())
        record["canary_status"]["demo_proj_live_canary_open"] = False

        validation = validate_canary_metrics_readback_record(record)

        self.assertEqual(validation["status"], "failed")
        self.assertIn("demo_proj_live_canary_open", validation["failed_checks"])
        self.assertIn("snapshot_digest", validation["failed_checks"])

    def test_explicit_write_and_read_helpers_round_trip(self) -> None:
        record = build_canary_metrics_readback_record(handoff=_handoff_fixture())
        with tempfile.TemporaryDirectory(prefix="canary-metrics-readback-") as tmp_dir:
            path = Path(tmp_dir) / "nested" / "snapshot.json"
            write_canary_metrics_readback_record(path, record)

            readback = read_canary_metrics_readback_record(path)

        self.assertEqual(readback, record)
        self.assertTrue(validate_canary_metrics_readback_record(readback)["passed"])


if __name__ == "__main__":
    unittest.main()
