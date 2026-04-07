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

if __name__ == "__main__":
    unittest.main()
