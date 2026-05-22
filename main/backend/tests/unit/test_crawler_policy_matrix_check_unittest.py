from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_crawler_policy_matrix import CONTRACT_VERSION
from scripts.check_crawler_policy_matrix import POLICY_ACTIONS
from scripts.check_crawler_policy_matrix import PROTECTED_SHARED_INDEXES
from scripts.check_crawler_policy_matrix import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]


class CrawlerPolicyMatrixCheckUnitTest(unittest.TestCase):
    def test_policy_matrix_binds_all_actions_to_existing_anchors(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertEqual(result["policy_actions"], list(POLICY_ACTIONS))
        self.assertEqual(
            result["doc_decision_coverage"]["coverage"],
            {"allow": True, "downgrade": True, "block": True},
        )

        anchors = result["anchors"]
        for key in (
            "policy_matrix_doc",
            "source_candidate_trust",
            "source_library_resolver",
            "ingest_meaningful_gate",
            "resource_pool_llm_validator",
            "discovery_store",
            "source_candidate_trust_test",
        ):
            self.assertTrue(anchors[key]["passed"], anchors[key])

    def test_policy_matrix_keeps_shared_navigation_out_of_scope(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["protected_shared_indexes"], list(PROTECTED_SHARED_INDEXES))
        touched_paths = [result["policy_matrix_doc"]]
        touched_paths.extend(anchor["path"] for anchor in result["anchors"].values())
        for protected_path in PROTECTED_SHARED_INDEXES:
            self.assertNotIn(protected_path, touched_paths)


if __name__ == "__main__":
    unittest.main()
