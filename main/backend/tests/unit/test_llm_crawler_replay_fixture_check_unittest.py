from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_llm_crawler_replay_fixture import CONTRACT_VERSION
from scripts.check_llm_crawler_replay_fixture import DEFAULT_FIXTURE_PATH
from scripts.check_llm_crawler_replay_fixture import FIXTURE_CONTRACT_VERSION
from scripts.check_llm_crawler_replay_fixture import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]


def _default_fixture() -> dict:
    return json.loads((REPO_ROOT / DEFAULT_FIXTURE_PATH).read_text(encoding="utf-8"))


class LlmCrawlerReplayFixtureCheckUnitTestCase(unittest.TestCase):
    def test_default_fixture_reads_manifest_and_replays_browser_decision_path(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["fixture_contract_version"], FIXTURE_CONTRACT_VERSION)
        self.assertEqual(result["status"], "fixture_replay_passed_public_replay_not_closed")
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["validation"]["browser_runtime_started"])
        self.assertFalse(result["validation"]["shared_indexes_edited"])

        self.assertTrue(result["manifest_gate"]["passed"])
        self.assertEqual(result["manifest_gate"]["status"], "manifest_valid_real_public_replay_not_closed")
        self.assertFalse(result["manifest_gate"]["real_public_high_js_replay_complete"])

        runtime = result["runtime"]
        self.assertEqual(runtime["mode"], "repo_local_browser_replay_fixture")
        self.assertTrue(runtime["repo_local_fixture"])
        self.assertTrue(runtime["deterministic"])
        self.assertFalse(runtime["public_network_attempted"])
        self.assertFalse(runtime["real_public_replay_claimed"])

        readback = result["manifest_readback"]
        self.assertEqual(readback["target_count"], 3)
        self.assertEqual(
            readback["target_ids"],
            ["instagram_tag_robotics", "x_search_robotics", "youtube_search_robotics"],
        )

        decision = result["browser_decision_path"]
        self.assertEqual(decision["route_hint"], "crawler_browse")
        self.assertEqual(decision["fetch_strategy"], "browser_render")
        self.assertEqual(decision["router_state"], "needs_browser")
        self.assertEqual(decision["reason_code"], "needs_browser_runtime")
        self.assertFalse(decision["http_fetch_fallback_allowed"])
        self.assertFalse(decision["public_browser_replay_performed"])

        targets = result["target_results"]["targets"]
        self.assertEqual(len(targets), 3)
        for target in targets:
            self.assertEqual(target["route_hint"], "crawler_browse")
            self.assertEqual(target["fetch_strategy"], "browser_render")
            self.assertEqual(target["router_state"], "needs_browser")
            self.assertEqual(target["reason_code"], "needs_browser_runtime")
            self.assertTrue(target["browser_render_decision_proven"])
            self.assertFalse(target["public_network_attempted"])

        self.assertTrue(result["closure"]["repo_local_fixture_replay_complete"])
        self.assertFalse(result["closure"]["real_public_high_js_replay_complete"])
        self.assertFalse(result["closure"]["full_closure_allowed"])
        self.assertEqual(
            result["closure"]["claim"],
            "repo_local_browser_replay_fixture_passed_real_public_replay_not_closed",
        )

    def test_fixture_target_decision_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = _default_fixture()
            fixture["target_results"][0]["frontdoor_decision"]["router_state"] = "http_fetch"
            fixture_path = Path(tmpdir) / "replay.fixture.json"
            fixture_path.write_text(json.dumps(fixture, sort_keys=True), encoding="utf-8")

            result = build_check(REPO_ROOT, fixture_path=fixture_path)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["validation"]["passed"])
        self.assertIn(
            "x_search_robotics: frontdoor_decision.router_state drifted",
            result["validation"]["errors"],
        )

    def test_fixture_cannot_claim_public_replay_or_browser_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = _default_fixture()
            fixture["runtime"]["public_network_attempted"] = True
            fixture["runtime"]["browser_runtime_started"] = True
            fixture_path = Path(tmpdir) / "replay.fixture.json"
            fixture_path.write_text(json.dumps(fixture, sort_keys=True), encoding="utf-8")

            result = build_check(REPO_ROOT, fixture_path=fixture_path)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["validation"]["passed"])
        self.assertIn("fixture.runtime.public_network_attempted must be False", result["validation"]["errors"])
        self.assertIn("fixture.runtime.browser_runtime_started must be False", result["validation"]["errors"])


if __name__ == "__main__":
    unittest.main()
