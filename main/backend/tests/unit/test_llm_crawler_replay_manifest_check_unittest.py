from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_llm_crawler_replay_manifest import CONTRACT_VERSION
from scripts.check_llm_crawler_replay_manifest import MANIFEST_CONTRACT_VERSION
from scripts.check_llm_crawler_replay_manifest import build_check
from scripts.check_evidence_source_availability import EVIDENCE_SOURCE_UNAVAILABLE


REPO_ROOT = Path(__file__).resolve().parents[4]


class LlmCrawlerReplayManifestCheckUnitTestCase(unittest.TestCase):
    def test_default_manifest_fails_closed_when_tracked_evidence_is_unavailable(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["manifest_contract_version"], MANIFEST_CONTRACT_VERSION)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["evidence_source"]["status"], EVIDENCE_SOURCE_UNAVAILABLE)
        self.assertFalse(result["validation"]["passed"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["validation"]["browser_runtime_started"])
        self.assertFalse(result["validation"]["shared_indexes_edited"])
        self.assertFalse(result["closure"]["full_closure_allowed"])
        self.assertFalse(result["closure"]["real_public_high_js_replay_complete"])
        self.assertTrue(result["evidence_source"]["missing_paths"])
        self.assertTrue(all(value is False for value in result["evidence_source"]["authority_ceiling"].values()))

    def test_llm_crawler_replay_manifest_authority_metadata(self) -> None:
        return_hint = get_type_hints(build_check, include_extras=True)["return"]
        self.assertIs(get_origin(return_hint), Annotated)
        _, metadata = get_args(return_hint)
        self.assertEqual(
            metadata,
            "kit:non-authoritative derived_as=preflight fact_source=repository.llm_replay_manifest_and_opt_in "
            "witness=test:test_llm_crawler_replay_manifest_authority_metadata",
        )


if __name__ == "__main__":
    unittest.main()
