from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_llm_crawler_high_js_replay_readiness import CONTRACT_VERSION
from scripts.check_llm_crawler_high_js_replay_readiness import PUBLIC_REPLAY_CONTRACT_VERSION
from scripts.check_llm_crawler_high_js_replay_readiness import SESSION_EVIDENCE_CONTRACT_VERSION
from scripts.check_llm_crawler_high_js_replay_readiness import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]


def _configured_session_evidence() -> dict:
    return {
        "contract_version": "llm_crawler.high_js_public_replay_evidence.v1",
        "credential_material_logged": False,
        "session": {
            "contract_version": SESSION_EVIDENCE_CONTRACT_VERSION,
            "requested": True,
            "configured": True,
            "applied": True,
            "source": "unit_session_user_data_dir",
            "user_data_dir_mode": "copied_operator_profile",
            "copy_session_user_data_dir": True,
            "credential_material_logged": False,
            "path_disclosed": False,
        },
    }


class LlmCrawlerHighJsReplayReadinessCheckUnitTestCase(unittest.TestCase):
    def test_default_gate_is_fixture_ready_with_external_replay_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_public_artifact = Path(tmpdir) / "missing-output.public.json"
            result = build_check(REPO_ROOT, missing_public_artifact)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["status"], "fixture_ready_real_public_replay_blocked")
        self.assertFalse(result["validation"]["passed"])
        self.assertTrue(result["validation"]["readiness_checks_passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["validation"]["shared_indexes_edited"])

        deterministic = result["deterministic_fixture"]
        self.assertTrue(deterministic["ready"])
        self.assertEqual(deterministic["target_count"], 3)
        self.assertEqual(deterministic["provider_handoff"]["status"], "passed")
        self.assertTrue(all(deterministic["provider_handoff"]["assertions"].values()))

        for profile in deterministic["target_profiles"]:
            self.assertTrue(profile["high_js"])
            self.assertTrue(profile["render_required"])
            self.assertEqual(profile["route_hint"], "crawler_browse")
            self.assertEqual(profile["fetch_strategy"], "browser_render")
            self.assertEqual(profile["router_contract"]["router_state"], "needs_browser")
            self.assertEqual(profile["router_contract"]["reason_code"], "needs_browser_runtime")
            self.assertFalse(profile["router_contract"]["http_fetch_fallback_allowed"])
            self.assertFalse(profile["router_contract"]["public_browser_replay_performed"])

        public_replay = result["public_high_js_replay"]
        self.assertEqual(public_replay["status"], "absent_blocked")
        self.assertEqual(public_replay["blocker_type"], "external_public_high_js_replay_not_proven")
        self.assertFalse(public_replay["real_public_high_js_replay_proven"])
        self.assertFalse(result["closure"]["full_closure_allowed"])
        self.assertEqual(
            result["closure"]["claim"],
            "deterministic_fixture_ready_not_public_high_js_replay_complete",
        )

    def test_present_public_artifact_must_prove_real_replay_before_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            public_artifact = Path(tmpdir) / "output.public.json"
            public_artifact.write_text(
                json.dumps(
                    {
                        "contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
                        "validation": {
                            "real_public_high_js_replay_proven": False,
                            "public_network_attempted": True,
                        },
                        "inputs": {"target_count": 3},
                        "outputs": {
                            "public_targets_attempted": 1,
                            "high_js_success_count": 1,
                            "target_results": [
                                {
                                    "target_id": "x_search_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                }
                            ],
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            result = build_check(REPO_ROOT, public_artifact)

        self.assertEqual(result["status"], "public_replay_artifact_not_proven")
        self.assertFalse(result["validation"]["passed"])
        self.assertTrue(result["validation"]["public_network_attempted"])
        self.assertEqual(result["public_high_js_replay"]["status"], "present_not_proven")
        self.assertFalse(result["closure"]["real_public_high_js_replay_complete"])
        self.assertFalse(result["closure"]["full_closure_allowed"])
        self.assertIn(
            "public replay artifact is present but does not prove real public high-JS replay completion",
            result["validation"]["errors"],
        )

    def test_accessible_public_artifact_reduces_blocker_to_platform_x_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            public_artifact = Path(tmpdir) / "output.public.json"
            public_artifact.write_text(
                json.dumps(
                    {
                        "contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
                        "validation": {
                            "real_public_high_js_replay_proven": False,
                            "public_network_attempted": True,
                        },
                        "inputs": {"target_count": 3},
                        "outputs": {
                            "public_targets_attempted": 3,
                            "high_js_success_count": 2,
                            "target_results": [
                                {
                                    "target_id": "x_search_robotics",
                                    "status": "auth_or_anti_bot_blocked",
                                    "browser_rendered": True,
                                    "public_network_attempted": True,
                                    "reason": "login required",
                                    "markers": {"contains_login": True, "contains_captcha": False},
                                },
                                {
                                    "target_id": "instagram_tag_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                },
                                {
                                    "target_id": "youtube_search_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                },
                            ],
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            result = build_check(REPO_ROOT, public_artifact)

        self.assertEqual(result["status"], "accessible_public_high_js_replay_proven_external_targets_blocked")
        self.assertFalse(result["validation"]["passed"])
        self.assertTrue(result["validation"]["readiness_checks_passed"], result["validation"]["errors"])
        self.assertTrue(result["public_high_js_replay"]["accessible_public_high_js_replay_proven"])
        self.assertTrue(result["public_high_js_replay"]["external_gate_blockers_proven"])
        self.assertFalse(result["public_high_js_replay"]["real_public_high_js_replay_proven"])
        self.assertEqual(result["public_high_js_replay"]["session_replay_evidence"]["status"], "absent")
        self.assertEqual(
            result["public_high_js_replay"]["blocker_type"],
            "platform_blocked",
        )
        self.assertTrue(result["closure"]["accessible_public_high_js_replay_complete"])
        self.assertFalse(result["closure"]["full_closure_allowed"])
        self.assertEqual(result["closure"]["remaining_external_blockers"][0]["target_id"], "x_search_robotics")
        self.assertEqual(result["closure"]["remaining_external_blockers"][0]["classification"], "platform_blocked")

    def test_proven_public_artifact_is_required_for_full_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            public_artifact = Path(tmpdir) / "output.public.json"
            public_artifact.write_text(
                json.dumps(
                    {
                        "contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
                        "validation": {
                            "real_public_high_js_replay_proven": True,
                            "public_network_attempted": True,
                        },
                        "inputs": {"target_count": 3},
                        "outputs": {
                            "public_targets_attempted": 3,
                            "high_js_success_count": 3,
                            "target_results": [
                                {
                                    "target_id": "x_search_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                },
                                {
                                    "target_id": "instagram_tag_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                },
                                {
                                    "target_id": "youtube_search_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                },
                            ],
                        },
                        "evidence": _configured_session_evidence(),
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            result = build_check(REPO_ROOT, public_artifact)

        self.assertEqual(result["status"], "real_public_high_js_replay_proven")
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertTrue(result["validation"]["readiness_checks_passed"], result["validation"]["errors"])
        self.assertTrue(result["public_high_js_replay"]["real_public_high_js_replay_proven"])
        self.assertTrue(result["closure"]["real_public_high_js_replay_complete"])
        self.assertTrue(result["closure"]["full_closure_allowed"])
        self.assertEqual(result["closure"]["claim"], "real_public_high_js_replay_complete")
        self.assertTrue(result["public_high_js_replay"]["lawful_session_evidence"]["accepted"])

    def test_x_success_without_configured_session_evidence_is_platform_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            public_artifact = Path(tmpdir) / "output.public.json"
            public_artifact.write_text(
                json.dumps(
                    {
                        "contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
                        "validation": {
                            "real_public_high_js_replay_proven": True,
                            "public_network_attempted": True,
                        },
                        "inputs": {"target_count": 3},
                        "outputs": {
                            "public_targets_attempted": 3,
                            "high_js_success_count": 3,
                            "target_results": [
                                {
                                    "target_id": "x_search_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                    "public_network_attempted": True,
                                },
                                {
                                    "target_id": "instagram_tag_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                },
                                {
                                    "target_id": "youtube_search_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                },
                            ],
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            result = build_check(REPO_ROOT, public_artifact)

        self.assertEqual(result["status"], "accessible_public_high_js_replay_proven_external_targets_blocked")
        self.assertFalse(result["validation"]["passed"])
        self.assertTrue(result["validation"]["readiness_checks_passed"], result["validation"]["errors"])
        self.assertFalse(result["public_high_js_replay"]["real_public_high_js_replay_proven"])
        self.assertFalse(result["closure"]["full_closure_allowed"])
        blocker = result["closure"]["remaining_external_blockers"][0]
        self.assertEqual(blocker["target_id"], "x_search_robotics")
        self.assertEqual(blocker["classification"], "platform_blocked")
        self.assertFalse(blocker["lawful_session_evidence"]["session_mode_configured"])

    def test_session_evidence_contract_is_validated_without_requiring_full_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            public_artifact = Path(tmpdir) / "output.public.json"
            public_artifact.write_text(
                json.dumps(
                    {
                        "contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
                        "validation": {
                            "real_public_high_js_replay_proven": False,
                            "public_network_attempted": True,
                        },
                        "inputs": {"target_count": 3},
                        "outputs": {
                            "public_targets_attempted": 3,
                            "high_js_success_count": 1,
                            "target_results": [
                                {
                                    "target_id": "x_search_robotics",
                                    "status": "auth_or_anti_bot_blocked",
                                    "browser_rendered": True,
                                    "public_network_attempted": True,
                                    "reason": "login required",
                                    "markers": {"contains_login": True, "contains_captcha": False},
                                },
                                {
                                    "target_id": "instagram_tag_robotics",
                                    "status": "auth_or_anti_bot_blocked",
                                    "browser_rendered": True,
                                    "public_network_attempted": True,
                                    "reason": "captcha required",
                                    "markers": {"contains_login": True, "contains_captcha": True},
                                },
                                {
                                    "target_id": "youtube_search_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                },
                            ],
                        },
                        "evidence": {
                            "contract_version": "llm_crawler.high_js_public_replay_evidence.v1",
                            "credential_material_logged": False,
                            "session": {
                                "contract_version": SESSION_EVIDENCE_CONTRACT_VERSION,
                                "requested": True,
                                "configured": True,
                                "applied": True,
                                "source": "unit_session_user_data_dir",
                                "user_data_dir_mode": "copied_operator_profile",
                                "copy_session_user_data_dir": True,
                                "credential_material_logged": False,
                                "path_disclosed": False,
                            },
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            result = build_check(REPO_ROOT, public_artifact)

        session_evidence = result["public_high_js_replay"]["session_replay_evidence"]
        self.assertEqual(result["status"], "accessible_public_high_js_replay_proven_external_targets_blocked")
        self.assertFalse(result["validation"]["passed"])
        self.assertTrue(result["validation"]["readiness_checks_passed"], result["validation"]["errors"])
        self.assertEqual(session_evidence["contract_version"], SESSION_EVIDENCE_CONTRACT_VERSION)
        self.assertTrue(session_evidence["session_aware_replay_requested"])
        self.assertTrue(session_evidence["session_context_applied"])
        self.assertFalse(session_evidence["credential_material_logged"])
        self.assertFalse(result["closure"]["full_closure_allowed"])

    def test_session_evidence_rejects_credential_material_logging(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            public_artifact = Path(tmpdir) / "output.public.json"
            public_artifact.write_text(
                json.dumps(
                    {
                        "contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
                        "validation": {
                            "real_public_high_js_replay_proven": True,
                            "public_network_attempted": True,
                        },
                        "inputs": {"target_count": 3},
                        "outputs": {
                            "public_targets_attempted": 3,
                            "high_js_success_count": 3,
                            "target_results": [
                                {"target_id": "x_search_robotics", "status": "success", "browser_rendered": True},
                                {
                                    "target_id": "instagram_tag_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                },
                                {
                                    "target_id": "youtube_search_robotics",
                                    "status": "success",
                                    "browser_rendered": True,
                                },
                            ],
                        },
                        "evidence": {
                            "contract_version": "llm_crawler.high_js_public_replay_evidence.v1",
                            "credential_material_logged": True,
                            "session": {
                                "contract_version": SESSION_EVIDENCE_CONTRACT_VERSION,
                                "requested": True,
                                "configured": True,
                                "applied": True,
                                "source": "unit_session_user_data_dir",
                                "user_data_dir_mode": "copied_operator_profile",
                                "copy_session_user_data_dir": True,
                                "credential_material_logged": True,
                                "path_disclosed": True,
                            },
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            result = build_check(REPO_ROOT, public_artifact)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["validation"]["passed"])
        self.assertFalse(result["closure"]["full_closure_allowed"])
        self.assertIn("public replay artifact must not log credential material", result["validation"]["errors"])


if __name__ == "__main__":
    unittest.main()
