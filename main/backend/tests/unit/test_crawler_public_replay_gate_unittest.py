from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_crawler_public_replay_gate import CONTRACT_VERSION
from scripts.check_crawler_public_replay_gate import MANIFEST_CONTRACT_VERSION
from scripts.check_crawler_public_replay_gate import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_REQUIRED_ARTIFACTS = {
    "source_replay_manifest": (
        "development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/input.json"
    ),
    "deterministic_replay_output": (
        "development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.json"
    ),
    "stored_a5_gate_output": (
        "development/latest-dev-docs/automation-runs/crawler-source-expansion-wave8-a7-validation-pack/"
        "2026-05-22/a5_public_replay_gate_check.json"
    ),
    "stored_closure_output": (
        "development/latest-dev-docs/automation-runs/crawler-source-expansion-wave8-a7-validation-pack/"
        "2026-05-22/crawler_source_expansion_closure_check.json"
    ),
    "live_public_output": (
        "development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json"
    ),
}


def _manifest_with_public_output(public_output_path: str) -> dict:
    return {
        "contract_version": MANIFEST_CONTRACT_VERSION,
        "scope": "unit test manifest override for crawler public replay gate",
        "expected_counts": {
            "historical_target_count": 45,
            "enabled_public_target_count": 40,
            "policy_disabled_target_count": 5,
        },
        "required_artifacts": {
            **DEFAULT_REQUIRED_ARTIFACTS,
            "live_public_output": public_output_path,
        },
        "closure_policy": {
            "deterministic_gate_allowed_without_network": True,
            "live_public_replay_default_status": "not_closed_missing_real_evidence",
            "real_evidence_requires": [
                "allow_public_network=true",
                "validation.full_historical_manifest=true",
                "outputs.public_targets_attempted=40",
                "skipped_policy_disabled_platform_entry=5",
            ],
        },
    }


class CrawlerPublicReplayGateUnitTestCase(unittest.TestCase):
    def test_gate_validates_deterministic_artifacts_and_detects_real_public_replay(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["validation"]["shared_indexes_edited"])
        self.assertEqual(
            result["overall_status"],
            "deterministic_artifacts_valid_live_public_replay_evidence_present_review_required",
        )

        manifest = result["deterministic_artifacts"]["source_replay_manifest"]
        self.assertEqual(manifest["target_count"], 45)
        self.assertEqual(manifest["enabled_public_target_count"], 40)
        self.assertEqual(manifest["policy_disabled_target_count"], 5)
        self.assertTrue(manifest["target_ids_match_embedded_snapshot"])

        deterministic = result["deterministic_artifacts"]["deterministic_replay_output"]
        self.assertTrue(deterministic["validation_passed"])
        self.assertEqual(deterministic["status_counts"], {"skipped_public_network_disabled": 45})
        self.assertEqual(deterministic["public_targets_attempted"], 0)

        live = result["live_public_replay"]
        self.assertEqual(live["status"], "real_evidence_present_review_required")
        self.assertEqual(live["closure_claim"], "review_required")
        self.assertTrue(live["evidence_present"])
        self.assertEqual(live["target_result_count"], 45)
        self.assertEqual(live["public_targets_attempted"], 40)
        self.assertEqual(live["policy_skipped_status_count"], 5)
        self.assertEqual(live["operator_gate_skip_count"], 0)

    def test_public_artifact_presence_is_not_enough_without_real_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            public_output = tmp_path / "output.public.json"
            manifest_path = tmp_path / "manifest.json"
            public_output.write_text(
                json.dumps(
                    {
                        "mode": {"allow_public_network": True},
                        "inputs": {
                            "target_count": 45,
                            "manifest_validation": {
                                "target_count": 45,
                                "enabled_target_count": 40,
                                "policy_skipped_target_count": 5,
                            },
                        },
                        "outputs": {
                            "target_results": [],
                            "status_counts": {"skipped_public_network_disabled": 45},
                            "public_targets_attempted": 0,
                        },
                        "validation": {
                            "passed": True,
                            "skipped": False,
                            "full_historical_manifest": True,
                            "live_evidence_sufficient": False,
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps(_manifest_with_public_output(str(public_output)), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            result = build_check(REPO_ROOT, manifest_path=manifest_path)

        self.assertFalse(result["validation"]["passed"])
        self.assertEqual(result["live_public_replay"]["status"], "invalid_public_replay_evidence")
        self.assertEqual(result["live_public_replay"]["closure_claim"], "not_closed")
        self.assertIn("live public replay evidence must attempt 40 enabled targets", result["validation"]["errors"])
        self.assertIn(
            "live public replay evidence must not contain operator-gate public-network skips",
            result["validation"]["errors"],
        )


if __name__ == "__main__":
    unittest.main()
