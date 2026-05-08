from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.source_library import resolver

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc

try:
    from app.services.ingest.frontdoor_contract import FRONTDOOR_STAGES
    from app.services.ingest.frontdoor_orchestrator import FrontDoorOrchestrator, FrontDoorOrchestratorConfig

    _INGEST_IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _INGEST_IMPORT_ERROR = exc


class FrontdoorOrchestratorUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"frontdoor orchestrator unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_run_item_payload_url_branch_injects_minimal_frontdoor_envelope(self):
        item = {
            "item_key": "url_pool.default",
            "channel_key": "url_pool",
            "enabled": True,
            "params": {"urls": ["https://example.com/a"]},
        }
        channels = [{"channel_key": "url_pool", "enabled": True, "default_params": {}}]
        routed_result = {"inserted": 1, "updated": 0, "skipped": 0, "errors": [], "by_url": []}

        with patch("app.services.source_library.resolver.run_item_with_url_routing", return_value=routed_result):
            raw = resolver.run_item_payload(item=item, channels=channels, project_key="demo_proj")

        envelope = raw["result"]["middle_layer_protocol"]
        required_keys = {
            "item_key",
            "front_door_owner",
            "execution_mode",
            "write_mode",
            "route_decision",
            "candidate_urls",
            "force_url_routing_flow",
            "routing_parallelism",
            "concurrency_plan",
        }
        self.assertTrue(required_keys.issubset(set(envelope.keys())))
        self.assertEqual(envelope["item_key"], "url_pool.default")
        self.assertEqual(envelope["front_door_owner"], "run_item_payload")
        self.assertEqual(envelope["execution_mode"], "url_routing")
        self.assertEqual(envelope["route_decision"], "front_door_url_routing")
        self.assertIsInstance(envelope["candidate_urls"], list)
        self.assertIsInstance(envelope["routing_parallelism"], int)
        self.assertIsInstance(envelope["concurrency_plan"], dict)

    def test_run_item_payload_handler_cluster_respects_search_then_route_stage_order(self):
        item = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {"site_entries": ["https://example.com/search?q={{q}}"]},
            "extra": {"stable_handler_cluster": True, "expected_entry_type": "search_template"},
        }
        events: list[str] = []

        def _fake_unified_search(**kwargs):
            events.append("search")
            return SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/search?q=robotics"}],
                candidates=["https://example.com/posts/robotics"],
                written={"urls_new": 1, "urls_skipped": 0},
                ingest_result={"inserted": 0, "updated": 0, "skipped": 0, "inserted_valid": 0, "rejected_count": 0, "rejection_breakdown": {}},
                errors=[],
            )

        def _fake_route(**kwargs):
            events.append("route")
            self.assertEqual(kwargs["params"]["urls"], ["https://example.com/posts/robotics"])
            return {"inserted": 1, "updated": 0, "skipped": 0, "errors": [], "by_url": []}

        with patch("app.services.resource_pool.unified_search_by_item_payload", side_effect=_fake_unified_search), patch(
            "app.services.source_library.resolver.run_item_with_url_routing",
            side_effect=_fake_route,
        ):
            raw = resolver.run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={"query_terms": ["robotics"], "_allow_internal_generic_web": True},
            )

        self.assertEqual(events, ["search", "route"])
        self.assertEqual(raw["result"]["single_write_workflow"], "front_door_url_routing")
        self.assertEqual(raw["result"]["middle_layer_protocol"]["execution_mode"], "url_routing")
        self.assertEqual(raw["result"]["middle_layer_protocol"]["route_decision"], "front_door_url_routing")

    def test_run_item_payload_handler_cluster_defaults_to_graceful_degrade_when_no_candidates(self):
        item = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {"site_entries": ["https://example.com/search?q={{q}}"]},
            "extra": {"stable_handler_cluster": True},
        }
        search_only = SimpleNamespace(
            site_entries_used=[{"site_url": "https://example.com/search?q=robotics"}],
            candidates=[],
            written={"urls_new": 0, "urls_skipped": 0},
            ingest_result={"inserted": 0, "updated": 0, "skipped": 0, "inserted_valid": 0, "rejected_count": 0, "rejection_breakdown": {}},
            errors=[{"error": "url_term_filter_empty_no_fallback"}],
        )

        with patch("app.services.resource_pool.unified_search_by_item_payload", return_value=search_only), patch(
            "app.services.source_library.resolver.run_item_with_url_routing"
        ) as routed:
            raw = resolver.run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={"query_terms": ["robotics"], "_allow_internal_generic_web": True},
            )

        routed.assert_not_called()
        self.assertEqual(raw["result"]["stats"]["fetched"], 0)
        self.assertEqual(raw["result"]["stats"]["normalized"], 0)
        self.assertEqual(raw["result"]["stats"]["errors"], 0)
        self.assertEqual(raw["result"]["errors"], [])
        self.assertEqual(raw["result"]["records"], [])
        self.assertEqual(raw["result"]["routing_result"]["inserted"], 0)
        self.assertEqual(raw["result"]["single_write_workflow"], "front_door_url_routing")
        self.assertEqual(raw["result"]["middle_layer_protocol"]["execution_mode"], "search_then_route")
        self.assertEqual(raw["result"]["middle_layer_protocol"]["route_decision"], "handler_cluster_search")

    def test_run_item_payload_blocks_direct_generic_web_without_internal_flag(self):
        item = {
            "item_key": "direct.generic_web.search_template",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {"site_entries": ["https://example.com/search?q={{q}}"]},
        }

        with self.assertRaisesRegex(ValueError, "generic_web\\.\\* direct item execution is disabled"):
            resolver.run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={"query_terms": ["robotics"]},
            )


class FrontdoorStageDiagnosticsUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _INGEST_IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"frontdoor diagnostics tests require backend dependencies: {_INGEST_IMPORT_ERROR}")

    def test_orchestrator_injects_stage_status_when_handler_omits_diagnostics(self):
        orchestrator = FrontDoorOrchestrator(config=FrontDoorOrchestratorConfig(stop_on_failed=False))
        envelope = orchestrator.run(
            payload={"url": "https://example.com/a"},
            stage_handlers={
                "unwrap": lambda _ctx: {},
                "gate": lambda _ctx: {"status": "failed", "reason_code": "url_policy_blocked"},
            },
        )
        diagnostics = envelope.get("diagnostics") or {}
        for stage in FRONTDOOR_STAGES:
            self.assertIn(f"stage.{stage}.status", diagnostics)
        self.assertEqual(diagnostics["stage.unwrap.status"], "ok")
        self.assertEqual(diagnostics["stage.gate.status"], "failed")
        self.assertEqual(diagnostics["stage.gate.reason"], "url_policy_blocked")

if __name__ == "__main__":
    unittest.main()
