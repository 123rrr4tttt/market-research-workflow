from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.build_crawler_public_replay_shard_outputs import build_public_shard_outputs
from scripts.check_crawler_public_replay_shards import DEFAULT_MANIFEST_PATH
from scripts.check_crawler_public_replay_shards import PUBLIC_OUTPUT_STATUS
from scripts.check_crawler_public_replay_shards import SHARD_OUTPUT_CONTRACT_VERSION


REPO_ROOT = Path(__file__).resolve().parents[4]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class BuildCrawlerPublicReplayShardOutputsUnitTestCase(unittest.TestCase):
    def test_builder_splits_full_public_replay_into_manifest_shards(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            manifest = _read_json(REPO_ROOT / DEFAULT_MANIFEST_PATH)
            manifest_path = tmp_path / "shard_manifest.json"
            readback_path = tmp_path / "shard_readback.json"
            manifest["required_artifacts"]["shard_readback"] = str(readback_path)
            for shard in manifest["shards"]:
                shard["public_output"] = str(tmp_path / f"{shard['shard_id']}.json")
            _write_json(manifest_path, manifest)

            result = build_public_shard_outputs(repo_root=REPO_ROOT, manifest_path=manifest_path)

            self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
            self.assertEqual(len(result["shards"]), 5)
            self.assertTrue(readback_path.is_file())

            readback = _read_json(readback_path)
            self.assertEqual(readback["readback"]["present_public_output_count"], 5)
            self.assertEqual(readback["readback"]["public_output_status"], PUBLIC_OUTPUT_STATUS)
            self.assertTrue(readback["closure"]["real_public_browser_fleet_replay_complete"])

            first_shard = _read_json(Path(manifest["shards"][0]["public_output"]))
            self.assertEqual(first_shard["contract_version"], SHARD_OUTPUT_CONTRACT_VERSION)
            self.assertEqual(first_shard["shard_id"], "crawler_public_replay_shard_01")
            self.assertTrue(first_shard["validation"]["passed"])
            self.assertEqual(first_shard["outputs"]["public_targets_attempted"], 8)


if __name__ == "__main__":
    unittest.main()
