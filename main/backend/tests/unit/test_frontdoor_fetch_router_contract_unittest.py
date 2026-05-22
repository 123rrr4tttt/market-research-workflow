from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest import url_pool as url_pool_module
    from app.services.ingest.frontdoor_router_contract import (
        CONTRACT_VERSION,
        build_frontdoor_fetch_router_contract,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class FrontdoorFetchRouterContractUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"frontdoor fetch router tests require backend dependencies: {_IMPORT_ERROR}")

    def test_high_js_profile_marks_needs_browser_without_public_replay(self) -> None:
        profile = url_pool_module._frontdoor_route_profile_for_url("https://x.com/search?q=robotics")

        router_contract = profile["router_contract"]
        boundary = router_contract["fallback_boundary"]
        self.assertEqual(router_contract["contract_version"], CONTRACT_VERSION)
        self.assertEqual(router_contract["tri_state_statuses"], ["success", "degraded_success", "failed"])
        self.assertEqual(router_contract["dashboard_status"], "degraded_success")
        self.assertEqual(router_contract["router_state"], "needs_browser")
        self.assertEqual(router_contract["reason_code"], "needs_browser_runtime")
        self.assertEqual(router_contract["fetch_strategy"], "browser_render")
        self.assertTrue(router_contract["high_js"])
        self.assertTrue(boundary["browser_fetch_required"])
        self.assertTrue(boundary["crawler_provider_allowed"])
        self.assertFalse(boundary["http_fetch_fallback_allowed"])
        self.assertFalse(boundary["legacy_url_only_write_allowed"])
        self.assertFalse(boundary["public_browser_replay_performed"])

    def test_contract_exposes_unsupported_and_blocked_failures(self) -> None:
        unsupported = build_frontdoor_fetch_router_contract(
            route_hint="crawler_browse",
            fetch_strategy="browser_render",
            router_state="unsupported",
        )
        blocked = build_frontdoor_fetch_router_contract(
            route_hint="crawler_browse",
            fetch_strategy="browser_render",
            router_state="blocked",
            reason_code="browser_runtime_blocked",
        )

        self.assertEqual(unsupported["dashboard_status"], "failed")
        self.assertEqual(unsupported["reason_code"], "unsupported_fetch_strategy")
        self.assertEqual(unsupported["reason_category"], "technical")
        self.assertFalse(unsupported["fallback_boundary"]["crawler_provider_allowed"])
        self.assertFalse(unsupported["fallback_boundary"]["http_fetch_fallback_allowed"])

        self.assertEqual(blocked["dashboard_status"], "failed")
        self.assertEqual(blocked["reason_code"], "browser_runtime_blocked")
        self.assertEqual(blocked["reason_category"], "policy")
        self.assertFalse(blocked["fallback_boundary"]["http_fetch_fallback_allowed"])
        self.assertFalse(blocked["fallback_boundary"]["legacy_url_only_write_allowed"])

    def test_frontdoor_status_projection_preserves_router_boundary(self) -> None:
        profile = url_pool_module._frontdoor_route_profile_for_url("https://x.com/search?q=robotics")
        projection = url_pool_module._build_frontdoor_status_projection(
            {
                "status": "degraded_success",
                "inserted_valid": 0,
                "frontdoor_route": {
                    "route_hint": "crawler_browse",
                    "fetch_strategy": "browser_render",
                    "router_contract": profile["router_contract"],
                },
            }
        )

        self.assertEqual(projection["dashboard_status"], "degraded_success")
        self.assertEqual(projection["reason_code"], "needs_browser_runtime")
        self.assertEqual(projection["router_state"], "needs_browser")
        self.assertEqual(projection["router_reason_code"], "needs_browser_runtime")
        self.assertFalse(projection["fallback_boundary"]["http_fetch_fallback_allowed"])
        self.assertFalse(projection["fallback_boundary"]["public_browser_replay_performed"])


if __name__ == "__main__":
    unittest.main()
