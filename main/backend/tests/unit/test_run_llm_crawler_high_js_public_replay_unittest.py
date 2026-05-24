from __future__ import annotations

import sys
import tempfile
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


def _fake_accessible_success_x_external_runner(target, chrome_path: str, timeout_seconds: int) -> dict:
    if target["target_id"] == "x_search_robotics":
        dom = "<html><head><title>X</title></head><body>login required</body></html>"
    elif target["target_id"] == "instagram_tag_robotics":
        dom = (
            "<html><head><title>Robotics on Instagram</title></head>"
            "<body>robotics instagram public tag page</body></html>"
        )
    else:
        dom = "<html><head><title>robotics - YouTube</title></head><body>video-title robotics</body></html>"
    return {
        "browser_runtime_started": True,
        "public_network_attempted": True,
        "timed_out": False,
        "returncode": 0,
        "elapsed_ms": 100,
        "dom": dom,
        "stderr": "",
    }


def _fake_x_rendered_without_auth_other_targets_success_runner(target, chrome_path: str, timeout_seconds: int) -> dict:
    if target["target_id"] == "x_search_robotics":
        dom = "<html><head><title>X</title></head><body>generic rendered shell</body></html>"
    elif target["target_id"] == "instagram_tag_robotics":
        dom = (
            "<html><head><title>Robotics on Instagram</title></head>"
            "<body>robotics instagram public tag page</body></html>"
        )
    else:
        dom = "<html><head><title>robotics - YouTube</title></head><body>video-title robotics</body></html>"
    return {
        "browser_runtime_started": True,
        "public_network_attempted": True,
        "timed_out": False,
        "returncode": 0,
        "elapsed_ms": 100,
        "dom": dom,
        "stderr": "",
    }


def _fake_browser_failure_with_sensitive_stderr(target, chrome_path: str, timeout_seconds: int) -> dict:
    return {
        "browser_runtime_started": True,
        "public_network_attempted": True,
        "timed_out": False,
        "returncode": 1,
        "elapsed_ms": 100,
        "dom": "",
        "stderr": (
            "Chrome failed --user-data-dir=/Users/alice/Library/Application Support/Google/Chrome/Profile 4 "
            "profile /home/alice/.config/chrome C:\\Users\\alice\\AppData\\Local\\Chrome"
        ),
    }


class RunLlmCrawlerHighJsPublicReplayUnitTestCase(unittest.TestCase):
    def test_fake_x_success_without_session_evidence_is_platform_blocked(self) -> None:
        result = run_high_js_public_replay(
            operator="unit",
            run_id="unit-success",
            allow_public_network=True,
            allow_browser_runtime=True,
            chrome_path="/tmp/fake-chrome",
            target_runner=_fake_success_runner,
        )

        self.assertEqual(result["contract_version"], PUBLIC_REPLAY_CONTRACT_VERSION)
        self.assertFalse(result["validation"]["real_public_high_js_replay_proven"])
        self.assertFalse(result["closure"]["real_public_high_js_replay_complete"])
        self.assertEqual(result["outputs"]["public_targets_attempted"], 3)
        self.assertEqual(result["outputs"]["high_js_success_count"], 2)
        self.assertEqual(result["outputs"]["status_counts"], {"platform_blocked": 1, "success": 2})
        session_evidence = result["evidence"]["session"]
        self.assertFalse(session_evidence["requested"])
        self.assertFalse(session_evidence["applied"])
        self.assertFalse(result["operator_opt_in"]["credential_material_logged"])
        blocker = result["outputs"]["remaining_external_blockers"][0]
        self.assertEqual(blocker["target_id"], "x_search_robotics")
        self.assertEqual(blocker["classification"], "platform_blocked")
        self.assertFalse(blocker["lawful_session_evidence"]["session_mode_configured"])

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
        self.assertIn("platform_blocked", result["outputs"]["status_counts"])
        self.assertFalse(result["validation"]["accessible_public_high_js_replay_proven"])

    def test_accessible_public_targets_can_close_with_x_external_gate_retained(self) -> None:
        result = run_high_js_public_replay(
            operator="unit",
            run_id="unit-accessible",
            allow_public_network=True,
            allow_browser_runtime=True,
            chrome_path="/tmp/fake-chrome",
            target_runner=_fake_accessible_success_x_external_runner,
        )

        self.assertTrue(result["validation"]["public_network_attempted"])
        self.assertTrue(result["validation"]["browser_runtime_started"])
        self.assertFalse(result["validation"]["real_public_high_js_replay_proven"])
        self.assertTrue(result["validation"]["accessible_public_high_js_replay_proven"])
        self.assertTrue(result["validation"]["external_gate_blockers_proven"])
        self.assertFalse(result["closure"]["full_closure_allowed"])
        self.assertTrue(result["closure"]["accessible_public_high_js_replay_complete"])
        self.assertEqual(
            result["closure"]["claim"],
            "accessible_public_high_js_replay_complete_external_targets_blocked",
        )
        self.assertEqual(result["outputs"]["high_js_success_count"], 2)
        self.assertEqual(result["outputs"]["remaining_external_blockers"][0]["target_id"], "x_search_robotics")
        self.assertEqual(result["outputs"]["remaining_external_blockers"][0]["classification"], "platform_blocked")

    def test_x_rendered_without_auth_or_success_does_not_reduce_external_gate(self) -> None:
        result = run_high_js_public_replay(
            operator="unit",
            run_id="unit-rendered-without-auth",
            allow_public_network=True,
            allow_browser_runtime=True,
            chrome_path="/tmp/fake-chrome",
            target_runner=_fake_x_rendered_without_auth_other_targets_success_runner,
        )

        self.assertTrue(result["validation"]["public_network_attempted"])
        self.assertFalse(result["validation"]["real_public_high_js_replay_proven"])
        self.assertFalse(result["validation"]["accessible_public_high_js_replay_proven"])
        self.assertFalse(result["validation"]["external_gate_blockers_proven"])
        self.assertFalse(result["closure"]["full_closure_allowed"])
        self.assertEqual(result["outputs"]["high_js_success_count"], 2)
        self.assertEqual(result["outputs"]["remaining_external_blockers"], [])
        x_result = next(row for row in result["outputs"]["target_results"] if row["target_id"] == "x_search_robotics")
        self.assertEqual(x_result["status"], "rendered_without_expected_search_content")
        self.assertNotIn("pre_session_policy_status", x_result)

    def test_browser_failure_stderr_is_redacted_before_artifact_output(self) -> None:
        result = run_high_js_public_replay(
            operator="unit",
            run_id="unit-redaction",
            allow_public_network=True,
            allow_browser_runtime=True,
            chrome_path="/tmp/fake-chrome",
            target_runner=_fake_browser_failure_with_sensitive_stderr,
        )

        rendered = str(result)
        self.assertNotIn("--user-data-dir=", rendered)
        self.assertNotIn("/Users/alice", rendered)
        self.assertNotIn("/home/alice", rendered)
        self.assertNotIn("C:\\Users\\alice", rendered)
        target_result = result["outputs"]["target_results"][0]
        self.assertIn("<redacted_user_data_dir>", target_result["stderr_tail"])
        self.assertIn("<redacted_path>", target_result["stderr_tail"])

    def test_operator_session_profile_is_recorded_without_logging_secret_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "operator-session"
            session_dir.mkdir()
            result = run_high_js_public_replay(
                operator="unit",
                run_id="unit-session",
                allow_public_network=True,
                allow_browser_runtime=True,
                chrome_path="/tmp/fake-chrome",
                session_user_data_dir=session_dir,
                session_user_data_dir_source="unit_session_user_data_dir",
                copy_session_user_data_dir=True,
                target_runner=_fake_success_runner,
            )

        session_evidence = result["evidence"]["session"]
        self.assertTrue(session_evidence["requested"])
        self.assertTrue(session_evidence["configured"])
        self.assertTrue(session_evidence["applied"])
        self.assertEqual(session_evidence["source"], "unit_session_user_data_dir")
        self.assertEqual(session_evidence["user_data_dir_mode"], "copied_operator_profile")
        self.assertFalse(session_evidence["credential_material_logged"])
        self.assertFalse(session_evidence["path_disclosed"])
        self.assertNotIn(str(session_dir), str(result))
        self.assertTrue(result["validation"]["real_public_high_js_replay_proven"])
        self.assertTrue(result["closure"]["real_public_high_js_replay_complete"])
        self.assertEqual(result["outputs"]["status_counts"], {"success": 3})
        x_result = next(row for row in result["outputs"]["target_results"] if row["target_id"] == "x_search_robotics")
        self.assertTrue(x_result["lawful_session_evidence"]["accepted"])
        for target_result in result["outputs"]["target_results"]:
            self.assertTrue(target_result["session_context"]["session_context_applied"])

    def test_missing_operator_session_profile_keeps_replay_blocked(self) -> None:
        result = run_high_js_public_replay(
            operator="unit",
            run_id="unit-missing-session",
            allow_public_network=True,
            allow_browser_runtime=True,
            chrome_path="/tmp/fake-chrome",
            session_user_data_dir="/tmp/mrw-missing-session-profile",
            session_user_data_dir_source="unit_session_user_data_dir",
            target_runner=_fake_success_runner,
        )

        self.assertFalse(result["validation"]["passed"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["closure"]["full_closure_allowed"])
        self.assertIn("session user data dir is not available", result["validation"]["errors"][0])
        self.assertEqual(result["outputs"]["status_counts"], {"skipped_runtime_not_available": 3})


if __name__ == "__main__":
    unittest.main()
