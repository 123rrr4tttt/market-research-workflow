from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_crawler_public_replay_shards import CONTRACT_VERSION
from scripts.check_crawler_public_replay_shards import DEFAULT_MANIFEST_PATH
from scripts.check_crawler_public_replay_shards import MANIFEST_CONTRACT_VERSION
from scripts.check_crawler_public_replay_shards import MISSING_OUTPUT_READBACK_SCOPE
from scripts.check_crawler_public_replay_shards import MISSING_OUTPUT_RUNTIME_MODE
from scripts.check_crawler_public_replay_shards import PUBLIC_OUTPUT_STATUS
from scripts.check_crawler_public_replay_shards import READBACK_CONTRACT_VERSION
from scripts.check_crawler_public_replay_shards import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _default_manifest() -> dict:
    return _read_json(REPO_ROOT / DEFAULT_MANIFEST_PATH)


def _missing_readback_for_manifest(manifest: dict, manifest_path: Path) -> dict:
    shards = []
    for shard in manifest["shards"]:
        shards.append(
            {
                "evidence_present": False,
                "public_output": shard["public_output"],
                "public_output_status": "external_blocked",
                "shard_id": shard["shard_id"],
                "shard_index": shard["shard_index"],
                "target_count": shard["target_count"],
                "target_ids": list(shard["target_ids"]),
            }
        )
    return {
        "contract_version": READBACK_CONTRACT_VERSION,
        "scope": MISSING_OUTPUT_READBACK_SCOPE,
        "shard_manifest_path": str(manifest_path.resolve()),
        "source_manifest_path": manifest["required_artifacts"]["source_replay_manifest"],
        "browser_fixture_path": manifest["required_artifacts"]["llm_browser_replay_fixture"],
        "runtime": {
            "mode": MISSING_OUTPUT_RUNTIME_MODE,
            "repo_local_fixture": True,
            "deterministic": True,
            "public_network_attempted": False,
            "browser_runtime_started": False,
            "public_browser_replay_performed": False,
            "real_public_replay_claimed": False,
        },
        "readback": {
            "shard_count": 5,
            "target_count": 45,
            "enabled_public_target_count": 40,
            "policy_disabled_target_count": 5,
            "missing_public_output_count": 5,
            "missing_public_output_status": "external_blocked",
            "real_public_browser_fleet_replay_complete": False,
            "full_closure_allowed": False,
        },
        "shards": shards,
        "closure": {
            "status": "external_blocked",
            "real_public_browser_fleet_replay_complete": False,
            "full_closure_allowed": False,
            "claim": "repo_local_shard_manifest_passed_missing_public_outputs_external_blocked",
        },
    }


def _temp_manifest_and_readback(tmpdir: str) -> tuple[dict, dict, Path, Path]:
    manifest = _default_manifest()
    manifest_path = Path(tmpdir) / "shard_manifest.json"
    readback_path = Path(tmpdir) / "shard_readback.json"
    manifest["required_artifacts"]["shard_readback"] = str(readback_path)
    for shard in manifest["shards"]:
        shard["public_output"] = str(Path(tmpdir) / f"{shard['shard_id']}.json")
    readback = _missing_readback_for_manifest(manifest, manifest_path)
    return manifest, readback, manifest_path, readback_path


class CrawlerPublicReplayShardsUnitTestCase(unittest.TestCase):
    def test_default_shard_manifest_validates_present_public_outputs(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["manifest_contract_version"], MANIFEST_CONTRACT_VERSION)
        self.assertEqual(result["readback_contract_version"], READBACK_CONTRACT_VERSION)
        self.assertEqual(result["status"], "shard_outputs_present_review_required")
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertTrue(result["validation"]["public_network_attempted"])
        self.assertFalse(result["validation"]["browser_runtime_started"])
        self.assertFalse(result["validation"]["shared_indexes_edited"])

        source_manifest = result["source_manifest"]
        self.assertEqual(source_manifest["target_count"], 45)
        self.assertEqual(source_manifest["enabled_public_target_count"], 40)
        self.assertEqual(source_manifest["policy_disabled_target_count"], 5)
        self.assertTrue(source_manifest["target_order_matches_embedded_snapshot"])

        shard_manifest = result["shard_manifest"]
        self.assertEqual(shard_manifest["shard_count"], 5)
        self.assertEqual(shard_manifest["target_count"], 45)
        self.assertEqual(shard_manifest["enabled_public_target_count"], 40)
        self.assertEqual(shard_manifest["policy_disabled_target_count"], 5)
        self.assertEqual(shard_manifest["missing_public_output_count"], 0)
        self.assertEqual(shard_manifest["present_public_output_count"], 5)

        readback = result["shard_readback"]
        self.assertEqual(readback["scope"], "crawler_public_replay_shards_public_output_readback")
        self.assertEqual(readback["counts"]["public_output_status"], PUBLIC_OUTPUT_STATUS)
        self.assertEqual(readback["counts"]["present_public_output_count"], 5)
        self.assertEqual(readback["closure"]["status"], PUBLIC_OUTPUT_STATUS)
        self.assertTrue(readback["closure"]["real_public_browser_fleet_replay_complete"])
        self.assertFalse(readback["closure"]["full_closure_allowed"])

        self.assertTrue(result["crawler_public_replay_gate"]["passed"])
        self.assertEqual(
            result["crawler_public_replay_gate"]["live_public_replay_status"],
            PUBLIC_OUTPUT_STATUS,
        )
        self.assertTrue(result["browser_replay_fixture_gate"]["passed"])
        self.assertFalse(result["browser_replay_fixture_gate"]["real_public_high_js_replay_complete"])

        closure = result["closure"]
        self.assertEqual(closure["overall_status"], "public_replay_shards_present_review_required")
        self.assertFalse(closure["missing_public_outputs_external_blocked"])
        self.assertTrue(closure["public_shard_outputs_present"])
        self.assertTrue(closure["real_public_browser_fleet_replay_complete"])
        self.assertFalse(closure["full_closure_allowed"])

    def test_manifest_shard_target_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, readback, manifest_path, readback_path = _temp_manifest_and_readback(tmpdir)
            manifest["shards"][0]["target_ids"][0] = "demo_proj_999_unexpected"
            _write_json(manifest_path, manifest)
            _write_json(readback_path, readback)

            result = build_check(REPO_ROOT, manifest_path=manifest_path, readback_path=readback_path)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["validation"]["passed"])
        self.assertIn(
            "crawler_public_replay_shard_01: target_ids must match source manifest order chunk",
            result["validation"]["errors"],
        )
        self.assertIn(
            "crawler_public_replay_shard_01: readback target_ids mismatch",
            result["validation"]["errors"],
        )

    def test_readback_cannot_claim_public_network_or_browser_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, readback, manifest_path, readback_path = _temp_manifest_and_readback(tmpdir)
            readback["runtime"]["public_network_attempted"] = True
            readback["runtime"]["browser_runtime_started"] = True
            readback["runtime"]["real_public_replay_claimed"] = True
            _write_json(manifest_path, manifest)
            _write_json(readback_path, readback)

            result = build_check(REPO_ROOT, manifest_path=manifest_path, readback_path=readback_path)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["validation"]["passed"])
        self.assertIn("readback.runtime.public_network_attempted must be False", result["validation"]["errors"])
        self.assertIn("readback.runtime.browser_runtime_started must be False", result["validation"]["errors"])
        self.assertIn("readback.runtime.real_public_replay_claimed must be False", result["validation"]["errors"])

    def test_missing_output_readback_rejects_present_shard_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, readback, manifest_path, readback_path = _temp_manifest_and_readback(tmpdir)
            public_output = Path(tmpdir) / "output.public.shard-01.json"
            public_output.write_text('{"contract_version":"unexpected"}\n', encoding="utf-8")
            manifest["shards"][0]["public_output"] = str(public_output)
            readback["shards"][0]["public_output"] = str(public_output)
            _write_json(manifest_path, manifest)
            _write_json(readback_path, readback)

            result = build_check(REPO_ROOT, manifest_path=manifest_path, readback_path=readback_path)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["validation"]["passed"])
        self.assertIn(
            "crawler_public_replay_shard_01: public output must remain absent for external_blocked readback",
            result["validation"]["errors"],
        )


if __name__ == "__main__":
    unittest.main()
