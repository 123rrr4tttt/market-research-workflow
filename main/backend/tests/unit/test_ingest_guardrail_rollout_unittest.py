from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest import url_pool as url_pool_module
    from app.services.ingest import guardrail_rollout as guardrail_rollout_module

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class IngestGuardrailRolloutUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest guardrail rollout tests require backend dependencies: {_IMPORT_ERROR}")

    def test_url_pool_always_uses_current_frontdoor_path(self):
        options = url_pool_module._resolve_frontdoor_options(
            {
                "url_routing_frontdoor_enabled": False,
                "front_door_owner": "ingest.news",
            }
        )

        self.assertEqual(
            options,
            {
                "enabled": True,
                "front_door_owner": "ingest.news",
                "route_decision": "front_door_url_routing",
                "write_mode": "front_door_url_routing",
                "execution_mode": "url_routing",
            },
        )

    def test_guardrail_rollout_canary_default_only_enables_listed_project(self):
        enabled = guardrail_rollout_module.resolve_ingest_guardrail_rollout_decision(
            project_key="demo_proj",
            settings_enabled=False,
            request_enabled=False,
            strict_mode_enabled=False,
            rollout_mode="canary",
            canary_projects=["demo_proj", "alpha_proj"],
        )
        blocked = guardrail_rollout_module.resolve_ingest_guardrail_rollout_decision(
            project_key="beta_proj",
            settings_enabled=False,
            request_enabled=False,
            strict_mode_enabled=False,
            rollout_mode="canary",
            canary_projects=["demo_proj", "alpha_proj"],
        )

        self.assertTrue(enabled.enable_strict_gate)
        self.assertEqual(enabled.strict_gate_source, "settings.ingest_guardrail_rollout_mode:canary")
        self.assertTrue(enabled.canary_matched)
        self.assertFalse(enabled.closure_claim)
        self.assertFalse(enabled.live_canary_validated)
        self.assertFalse(blocked.enable_strict_gate)
        self.assertEqual(blocked.strict_gate_source, "disabled")

    def test_guardrail_rollout_readiness_keeps_live_closure_open(self):
        report = guardrail_rollout_module.build_ingest_guardrail_rollout_readiness(
            rollout_mode="canary",
            canary_projects=["demo_proj"],
            response_visibility_fields=[
                "quality_assessment.strict_gate_enabled",
                "quality_assessment.strict_gate_source",
                "quality_gates.gate_config.guardrail_rollout",
            ],
            metrics_visibility_fields=[
                "metrics_payload.guardrail_rollout.strict_enabled_samples",
                "metrics_payload.guardrail_rollout.canary_matched_samples",
                "metrics_payload.guardrail_rollout.strict_gate_source_counts",
            ],
        )

        self.assertTrue(report.ready_for_repo_rollout)
        self.assertFalse(report.live_canary_validated)
        self.assertFalse(report.closure_claim)
        self.assertIn("24h rejection", " ".join(report.remaining_live_gap))

if __name__ == "__main__":
    unittest.main()
