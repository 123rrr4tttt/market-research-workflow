from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

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
from scripts.check_crawler_public_replay_shards import SHARD_OUTPUT_CONTRACT_VERSION
from scripts.check_crawler_public_replay_shards import build_check
from scripts.check_evidence_source_availability import EVIDENCE_SOURCE_UNAVAILABLE
from scripts.source_library_replay_scaleout import DEFAULT_HISTORICAL_TARGETS


REPO_ROOT = Path(__file__).resolve().parents[4]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _synthetic_manifest(tmpdir: str) -> dict:
    targets = [dict(target) for target in DEFAULT_HISTORICAL_TARGETS]
    shards = []
    for index in range(5):
        chunk = targets[index * 9 : (index + 1) * 9]
        shards.append(
            {
                "shard_id": f"crawler_public_replay_shard_{index + 1:02d}",
                "shard_index": index + 1,
                "target_count": len(chunk),
                "enabled_public_target_count": sum(1 for row in chunk if row.get("enabled", True)),
                "policy_disabled_target_count": sum(1 for row in chunk if row.get("skip_public_execution")),
                "target_ids": [row["target_id"] for row in chunk],
                "public_output": str(Path(tmpdir) / f"output.public.shard-{index + 1:02d}.json"),
                "expected_missing_output_status": "external_blocked",
            }
        )
    source_manifest = Path(tmpdir) / "source_manifest.json"
    _write_json(source_manifest, {"targets": targets})
    return {
        "contract_version": MANIFEST_CONTRACT_VERSION,
        "scope": "synthetic crawler public replay shard manifest",
        "expected_counts": {
            "historical_target_count": 45,
            "enabled_public_target_count": 40,
            "policy_disabled_target_count": 5,
        },
        "required_artifacts": {
            "source_replay_manifest": str(source_manifest),
            "crawler_public_replay_gate_manifest": str(Path(tmpdir) / "missing-gate.json"),
            "llm_high_js_replay_manifest": str(Path(tmpdir) / "missing-llm-manifest.json"),
            "llm_browser_replay_fixture": str(Path(tmpdir) / "missing-browser-fixture.json"),
            "shard_readback": str(Path(tmpdir) / "shard_readback.json"),
        },
        "shard_policy": {
            "strategy": "source_manifest_order_chunks",
            "preserve_source_manifest_order": True,
            "shard_count": 5,
            "shard_size": 9,
            "public_output_contract_version": SHARD_OUTPUT_CONTRACT_VERSION,
            "missing_public_output_status": "external_blocked",
            "closure_without_all_shard_outputs_allowed": False,
            "browser_replay_fixture_required": True,
        },
        "public_output_boundary": {
            "source_full_output": str(Path(tmpdir) / "missing-full-output.json"),
            "real_public_browser_fleet_replay_status": "external_blocked",
            "full_closure_allowed": False,
            "required_future_evidence": [
                "opt-in 45-site public replay output",
                "per-shard public browser/fetch output JSON",
                "40 enabled public targets attempted",
                "5 policy-disabled platform/API targets skipped",
            ],
        },
        "shards": shards,
    }


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
    manifest = _synthetic_manifest(tmpdir)
    manifest_path = Path(tmpdir) / "shard_manifest.json"
    readback_path = Path(tmpdir) / "shard_readback.json"
    manifest["required_artifacts"]["shard_readback"] = str(readback_path)
    for shard in manifest["shards"]:
        shard["public_output"] = str(Path(tmpdir) / f"{shard['shard_id']}.json")
    readback = _missing_readback_for_manifest(manifest, manifest_path)
    return manifest, readback, manifest_path, readback_path


class CrawlerPublicReplayShardsUnitTestCase(unittest.TestCase):
    def test_default_shard_manifest_fails_closed_when_evidence_is_unavailable(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["manifest_contract_version"], MANIFEST_CONTRACT_VERSION)
        self.assertEqual(result["readback_contract_version"], READBACK_CONTRACT_VERSION)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["evidence_source"]["status"], EVIDENCE_SOURCE_UNAVAILABLE)
        self.assertFalse(result["validation"]["passed"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["validation"]["browser_runtime_started"])
        self.assertFalse(result["validation"]["shared_indexes_edited"])
        self.assertEqual(result["closure"]["overall_status"], "failed")
        self.assertFalse(result["closure"]["public_shard_outputs_present"])
        self.assertFalse(result["closure"]["real_public_browser_fleet_replay_complete"])
        self.assertTrue(result["evidence_source"]["missing_paths"])
        self.assertTrue(all(value is False for value in result["evidence_source"]["authority_ceiling"].values()))

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

    def test_crawler_public_replay_shards_authority_metadata(self) -> None:
        return_hint = get_type_hints(build_check, include_extras=True)["return"]
        self.assertIs(get_origin(return_hint), Annotated)
        _, metadata = get_args(return_hint)
        self.assertEqual(
            metadata,
            "kit:non-authoritative derived_as=preflight fact_source=repository.public_replay_shards_and_readback "
            "witness=test:test_crawler_public_replay_shards_authority_metadata",
        )


if __name__ == "__main__":
    unittest.main()
