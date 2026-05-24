from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_llm_crawler_high_js_replay_readiness import PUBLIC_REPLAY_CONTRACT_VERSION
from scripts.run_llm_crawler_high_js_public_replay import run_high_js_public_replay


def _fake_success_runner(target, chrome_path: str, timeout_seconds: int) -> dict:
    target_id = target["target_id"]
    title = {
        "x_search_robotics": "robotics / X",
        "instagram_tag_robotics": "Robotics on Instagram",
        "youtube_search_robotics": "robotics - YouTube",
    }[target_id]
    marker = "video-title" if target_id == "youtube_search_robotics" else "robotics"
    return {
        "browser_runtime_started": True,
        "public_network_attempted": True,
        "timed_out": False,
        "returncode": 0,
        "elapsed_ms": 100,
        "dom": f"<html><head><title>{title}</title></head><body>{marker} x.com/search?q=robotics</body></html>",
        "stderr": "",
    }


def _fake_partial_runner(target, chrome_path: str, timeout_seconds: int) -> dict:
    if target["target_id"] == "x_search_robotics":
        dom = "<html><head><title>X</title></head><body>login required</body></html>"
    else:
        dom = "<html><head><title>robotics - YouTube</title></head><body>video-title robotics</body></html>"
    return {
        "browser_runtime_started": True,
        "public_network_attempted": True,
        "timed_out": True,
        "returncode": None,
        "elapsed_ms": 1000,
        "dom": dom,
        "stderr": "timeout",
    }


class RunLlmCrawlerHighJsPublicReplayUnitTestCase(unittest.TestCase):
    def test_fake_success_proves_public_high_js_replay(self) -> None:
        result = run_high_js_public_replay(
            operator="unit",
            run_id="unit-success",
            allow_public_network=True,
            allow_browser_runtime=True,
            chrome_path="/tmp/fake-chrome",
            target_runner=_fake_success_runner,
        )

        self.assertEqual(result["contract_version"], PUBLIC_REPLAY_CONTRACT_VERSION)
        self.assertTrue(result["validation"]["real_public_high_js_replay_proven"])
        self.assertTrue(result["closure"]["real_public_high_js_replay_complete"])
        self.assertEqual(result["outputs"]["public_targets_attempted"], 3)
        self.assertEqual(result["outputs"]["high_js_success_count"], 3)
        self.assertEqual(result["outputs"]["status_counts"], {"success": 3})

    def test_partial_browser_run_records_attempt_without_claiming_proof(self) -> None:
        result = run_high_js_public_replay(
            operator="unit",
            run_id="unit-partial",
            allow_public_network=True,
            allow_browser_runtime=True,
            chrome_path="/tmp/fake-chrome",
            target_runner=_fake_partial_runner,
        )

        self.assertTrue(result["validation"]["public_network_attempted"])
        self.assertTrue(result["validation"]["browser_runtime_started"])
        self.assertFalse(result["validation"]["real_public_high_js_replay_proven"])
        self.assertFalse(result["closure"]["real_public_high_js_replay_complete"])
        self.assertEqual(result["outputs"]["public_targets_attempted"], 3)
        self.assertLess(result["outputs"]["high_js_success_count"], 3)
        self.assertIn("auth_or_anti_bot_blocked", result["outputs"]["status_counts"])


if __name__ == "__main__":
    unittest.main()
