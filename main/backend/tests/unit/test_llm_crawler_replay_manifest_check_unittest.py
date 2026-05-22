from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_llm_crawler_replay_manifest import CONTRACT_VERSION
from scripts.check_llm_crawler_replay_manifest import DEFAULT_MANIFEST_PATH
from scripts.check_llm_crawler_replay_manifest import MANIFEST_CONTRACT_VERSION
from scripts.check_llm_crawler_replay_manifest import OPT_IN_CONTRACT_VERSION
from scripts.check_llm_crawler_replay_manifest import PUBLIC_REPLAY_CONTRACT_VERSION
from scripts.check_llm_crawler_replay_manifest import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]


def _default_manifest() -> dict:
    return json.loads((REPO_ROOT / DEFAULT_MANIFEST_PATH).read_text(encoding="utf-8"))


def _valid_opt_in_request() -> dict:
    manifest = _default_manifest()
    return {
        "contract_version": OPT_IN_CONTRACT_VERSION,
        "operator": "wave15-worker-4",
        "run_id": "high-js-public-replay-2026-05-22T00-00-00Z",
        "requested_at": "2026-05-22T00:00:00Z",
        "browser_runtime": "playwright-public-browser-runtime",
        "evidence_output": manifest["required_artifacts"]["live_public_output"],
        "output_contract_version": PUBLIC_REPLAY_CONTRACT_VERSION,
        "target_ids": [
            "x_search_robotics",
            "instagram_tag_robotics",
            "youtube_search_robotics",
        ],
        "allow_public_network": True,
        "allow_browser_runtime": True,
        "allow_high_js_targets": True,
        "acknowledge_external_site_terms": True,
        "acknowledge_rate_limits": True,
        "acknowledge_no_shared_index_edits": True,
    }


class LlmCrawlerReplayManifestCheckUnitTestCase(unittest.TestCase):
    def test_default_manifest_records_opt_in_schema_and_keeps_public_replay_gap(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["manifest_contract_version"], MANIFEST_CONTRACT_VERSION)
        self.assertEqual(result["status"], "manifest_valid_real_public_replay_not_closed")
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["validation"]["browser_runtime_started"])
        self.assertFalse(result["validation"]["shared_indexes_edited"])

        artifacts = result["artifacts"]
        self.assertFalse(artifacts["live_public_output_present"])
        self.assertTrue(artifacts["present"]["manifest"])
        self.assertTrue(artifacts["present"]["readiness_checker"])
        self.assertTrue(artifacts["present"]["wave15_manifest_evidence_doc"])

        target_set = result["target_set"]
        self.assertEqual(target_set["target_count"], 3)
        self.assertEqual(
            target_set["expected_target_ids"],
            ["instagram_tag_robotics", "x_search_robotics", "youtube_search_robotics"],
        )
        for target in target_set["targets"]:
            self.assertTrue(target["high_js"])
            self.assertTrue(target["public_replay_opt_in_required"])
            self.assertEqual(target["route_hint"], "crawler_browse")
            self.assertEqual(target["fetch_strategy"], "browser_render")
            self.assertEqual(target["router_state"], "needs_browser")
            self.assertFalse(target["public_browser_replay_performed"])

        schema = result["operator_opt_in_schema"]
        self.assertEqual(schema["contract_version"], OPT_IN_CONTRACT_VERSION)
        self.assertIn("allow_public_network", schema["required_true_fields"])
        self.assertIn("allow_browser_runtime", schema["required_true_fields"])
        self.assertIn("target_ids", schema["required_list_fields"])
        self.assertEqual(schema["evidence_output_contract_version"], PUBLIC_REPLAY_CONTRACT_VERSION)

        self.assertFalse(result["closure"]["full_closure_allowed"])
        self.assertFalse(result["closure"]["real_public_high_js_replay_complete"])
        self.assertEqual(
            result["closure"]["claim"],
            "manifest_schema_valid_not_public_high_js_replay_complete",
        )

    def test_manifest_missing_opt_in_fields_fails_schema_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = _default_manifest()
            manifest["operator_opt_in_schema"]["required_true_fields"].remove("allow_browser_runtime")
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest["required_artifacts"]["manifest"] = str(manifest_path)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            result = build_check(REPO_ROOT, manifest_path)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["validation"]["passed"])
        self.assertIn("operator_opt_in_schema.required_true_fields mismatch", result["validation"]["errors"])

    def test_valid_opt_in_request_is_ready_but_does_not_claim_public_replay(self) -> None:
        result = build_check(REPO_ROOT, opt_in_request=_valid_opt_in_request())

        self.assertEqual(result["status"], "manifest_valid_opt_in_request_valid")
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertTrue(result["operator_opt_in_request"]["valid"])
        self.assertTrue(result["operator_opt_in_request"]["public_replay_execution_allowed"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["closure"]["real_public_high_js_replay_complete"])
        self.assertFalse(result["closure"]["full_closure_allowed"])
        self.assertEqual(
            result["closure"]["claim"],
            "operator_opt_in_ready_but_real_public_replay_not_executed",
        )

    def test_opt_in_request_must_cover_exact_manifest_targets(self) -> None:
        request = _valid_opt_in_request()
        request["target_ids"] = ["x_search_robotics"]

        result = build_check(REPO_ROOT, opt_in_request=request)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["validation"]["passed"])
        self.assertEqual(result["operator_opt_in_request"]["status"], "invalid")
        self.assertIn(
            "opt-in target_ids must match the high-JS replay manifest targets",
            result["validation"]["errors"],
        )


if __name__ == "__main__":
    unittest.main()
