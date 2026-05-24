from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.ingest.canary_handoff import CANARY_HANDOFF_CONTRACT_VERSION, CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION
from app.services.ingest.canary_metrics import (
    CONFIGURED_PROVIDER_CANARY_CONTRACT_VERSION,
    build_configured_provider_canary_boundary,
    build_ingest_canary_metrics_readiness,
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


def _configured_provider_live_evidence() -> dict:
    handoff = _handoff_fixture()
    return {
        "demo_proj_live_canary_validated": True,
        "single_url_frontdoor_run_completed": True,
        "configured_services_used": True,
        "canary_handoff_readback_present": True,
        "configured_provider": {
            "provider_key": "source_library_frontdoor",
            "config_state": "configured",
            "runtime": "configured_source_library_provider",
            "live_probe_status": "passed",
        },
        "frontdoor_run": dict(handoff["frontdoor_run"]),
        "handoff_readback": handoff,
        "closure_claim": False,
    }


class IngestCanaryMetricsReadinessUnitTestCase(unittest.TestCase):
    def test_deterministic_readiness_keeps_live_canary_and_24h_metrics_open(self) -> None:
        report = build_ingest_canary_metrics_readiness(handoff=_handoff_fixture())

        self.assertEqual(report.status, "ok")
        self.assertTrue(report.deterministic_metrics_ready)
        self.assertFalse(report.closure_claim)
        self.assertFalse(report.live_canary_validated)
        self.assertFalse(report.metric_24h_readback_validated)
        self.assertTrue(report.demo_proj_live_canary_open)
        self.assertTrue(report.metric_24h_readback_open)
        self.assertTrue(report.ready_for_live_canary)
        self.assertFalse(report.ready_for_24h_metric_readback)
        stages = {stage.name: stage for stage in report.stages}
        self.assertEqual(stages["deterministic_canary_metrics_snapshot"].status, "passed")
        self.assertEqual(stages["demo_proj_live_canary"].status, "ready_not_run")
        self.assertEqual(stages["metric_24h_readback"].status, "open_waiting_for_live_canary")
        self.assertEqual(report.configured_provider_canary_boundary["status"], "missing_evidence")
        self.assertIn("live canary execution remains open", " ".join(report.remaining_live_gaps))
        self.assertIn("24h rejection-rate readback remains open", " ".join(report.remaining_live_gaps))

    def test_incomplete_live_canary_evidence_fails_without_closing_24h_readback(self) -> None:
        report = build_ingest_canary_metrics_readiness(
            handoff=_handoff_fixture(),
            live_canary_evidence={
                "demo_proj_live_canary_validated": True,
                "single_url_frontdoor_run_completed": True,
            },
        )

        self.assertEqual(report.status, "failed")
        self.assertFalse(report.live_canary_validated)
        self.assertTrue(report.demo_proj_live_canary_open)
        self.assertTrue(report.metric_24h_readback_open)
        stages = {stage.name: stage for stage in report.stages}
        self.assertEqual(stages["demo_proj_live_canary"].status, "failed_evidence")
        self.assertIn("configured_provider.provider_key", stages["demo_proj_live_canary"].detail)
        self.assertIn(
            "configured_provider.provider_key",
            report.configured_provider_canary_boundary["validation"]["missing_fields"],
        )

    def test_configured_provider_canary_boundary_requires_provider_runtime_and_handoff(self) -> None:
        boundary = build_configured_provider_canary_boundary(
            live_canary_evidence={
                "demo_proj_live_canary_validated": True,
                "single_url_frontdoor_run_completed": True,
                "configured_services_used": True,
                "canary_handoff_readback_present": True,
                "configured_provider": {
                    "provider_key": "source_library_frontdoor",
                    "config_state": "missing_config",
                    "runtime": "configured_source_library_provider",
                    "live_probe_status": "blocked",
                },
                "frontdoor_run": {
                    "project_key": "demo_proj",
                    "entrypoint": "ingest.url_pool",
                    "source_mode": "url_execution",
                    "source_url": "https://example.com/search?q=robotics",
                },
                "handoff_readback": {"contract_version": CANARY_HANDOFF_CONTRACT_VERSION},
            },
        )

        self.assertEqual(boundary["contract_version"], CONFIGURED_PROVIDER_CANARY_CONTRACT_VERSION)
        self.assertEqual(boundary["status"], "failed_evidence")
        self.assertFalse(boundary["validation"]["passed"])
        self.assertIn("configured_provider_configured", boundary["validation"]["failed_checks"])
        self.assertIn("configured_provider_live_runtime_validated", boundary["validation"]["failed_checks"])

    def test_configured_provider_canary_boundary_accepts_single_url_endpoint(self) -> None:
        handoff = _handoff_fixture()
        handoff["frontdoor_run"] = {
            **handoff["frontdoor_run"],
            "entrypoint": "ingest.url.single",
            "source_url": "https://example.com/wave57-single-url",
        }
        evidence = _configured_provider_live_evidence()
        evidence["frontdoor_run"] = dict(handoff["frontdoor_run"])
        evidence["handoff_readback"] = handoff

        boundary = build_configured_provider_canary_boundary(live_canary_evidence=evidence)

        self.assertEqual(boundary["status"], "validated")
        self.assertTrue(boundary["validation"]["passed"])
        self.assertTrue(boundary["validation"]["checks"]["frontdoor_entrypoint_is_single_url_frontdoor"])
        self.assertIn("ingest.url.single", boundary["frontdoor_run"]["allowed_entrypoints"])

    def test_complete_live_and_24h_evidence_validates_readbacks_without_closure_claim(self) -> None:
        report = build_ingest_canary_metrics_readiness(
            handoff=_handoff_fixture(),
            live_canary_evidence=_configured_provider_live_evidence(),
            metric_readback_evidence={
                "metric_24h_readback_validated": True,
                "window_hours_at_least_24": True,
                "rejection_rate_reviewed": True,
                "inserted_valid_ratio_reviewed": True,
                "guardrail_rollout_counts_reviewed": True,
            },
        )

        self.assertEqual(report.status, "ok")
        self.assertTrue(report.live_canary_validated)
        self.assertTrue(report.metric_24h_readback_validated)
        self.assertFalse(report.demo_proj_live_canary_open)
        self.assertFalse(report.metric_24h_readback_open)
        self.assertFalse(report.closure_claim)
        self.assertEqual(report.configured_provider_canary_boundary["status"], "validated")
        self.assertEqual(report.remaining_live_gaps, [])


if __name__ == "__main__":
    unittest.main()
