from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest import url_pool as url_pool_module
    from app.services.ingest import frontdoor_rollout as rollout_module
    from app.services.ingest import guardrail_rollout as guardrail_rollout_module

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class IngestFrontdoorRolloutUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest frontdoor rollout tests require backend dependencies: {_IMPORT_ERROR}")

    def test_url_pool_frontdoor_disabled_when_rollout_mode_off(self):
        with patch.object(rollout_module.settings, "ingest_frontdoor_rollout_mode", "off"):
            options = url_pool_module._resolve_frontdoor_options(
                {
                    "url_routing_frontdoor_enabled": True,
                    "front_door_owner": "ingest.news",
                },
                project_key="demo_proj",
            )

        self.assertEqual(options, {"enabled": False})

    def test_url_pool_frontdoor_canary_only_allows_listed_project(self):
        with patch.object(rollout_module.settings, "ingest_frontdoor_rollout_mode", "canary"), patch.object(
            rollout_module.settings,
            "ingest_frontdoor_canary_projects",
            "demo_proj, alpha_proj",
        ):
            enabled_options = url_pool_module._resolve_frontdoor_options(
                {"url_routing_frontdoor_enabled": True},
                project_key="demo_proj",
            )
            blocked_options = url_pool_module._resolve_frontdoor_options(
                {"url_routing_frontdoor_enabled": True},
                project_key="beta_proj",
            )

        self.assertTrue(enabled_options.get("enabled"))
        self.assertEqual(blocked_options, {"enabled": False})

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
