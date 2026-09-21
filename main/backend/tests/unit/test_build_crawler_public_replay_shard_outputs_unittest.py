from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.build_crawler_public_replay_shard_outputs import build_public_shard_outputs
from scripts.check_evidence_source_availability import EVIDENCE_SOURCE_UNAVAILABLE


REPO_ROOT = Path(__file__).resolve().parents[4]


class BuildCrawlerPublicReplayShardOutputsUnitTestCase(unittest.TestCase):
    def test_builder_fails_closed_when_tracked_manifest_is_unavailable(self) -> None:
        result = build_public_shard_outputs(repo_root=REPO_ROOT)

        self.assertEqual(result["evidence_source"]["status"], EVIDENCE_SOURCE_UNAVAILABLE)
        self.assertFalse(result["validation"]["passed"])
        self.assertFalse(result["validation"]["write"])
        self.assertEqual(result["shards"], [])
        self.assertTrue(result["evidence_source"]["missing_paths"])
        self.assertTrue(all(value is False for value in result["evidence_source"]["authority_ceiling"].values()))


if __name__ == "__main__":
    unittest.main()
