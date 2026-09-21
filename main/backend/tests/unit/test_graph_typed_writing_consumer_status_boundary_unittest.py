from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

pytestmark = pytest.mark.unit

from scripts.check_graph_typed_writing_consumer_status_boundary import (  # noqa: E402
    CANONICAL_ROOT,
    CONTRACT_VERSION,
    TARGET_STATUS,
    build_check,
    validate_report,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class GraphTypedWritingConsumerStatusBoundaryUnitTest(unittest.TestCase):
    def test_current_authority_is_later_canonical_closure(self) -> None:
        report = build_check(REPO_ROOT)

        self.assertEqual(report["contract_version"], CONTRACT_VERSION)
        self.assertEqual(report["status"], "passed", report["validation"])
        self.assertTrue(report["validation"]["passed"], report["validation"])
        self.assertEqual(report["authority"]["root"], CANONICAL_ROOT.as_posix())
        self.assertFalse(report["authority"]["historical_wave27_is_current_authority"])

        topic_statuses = {topic["topic_id"]: topic for topic in report["topics"]}
        self.assertEqual(len(topic_statuses), 4)
        for topic in topic_statuses.values():
            self.assertEqual(topic["canonical_status"], TARGET_STATUS)
            self.assertTrue(topic["canonical_directory_exists"])
            self.assertTrue(topic["canonical_closure_doc_exists"])
            self.assertEqual(topic["missing_closure_tokens"], [])
            self.assertTrue(topic["topic_index_has_current_authority"])
            self.assertTrue(topic["closed_index_points_to_closure"])
            self.assertFalse(topic["historical_wave27"]["is_current_authority"])

        waves = {topic["label"]: topic["closure_wave"] for topic in report["topics"]}
        self.assertEqual(waves["graph_editing_and_reporting"], 46)
        self.assertEqual(waves["typed_knowledge_organization"], 54)
        self.assertEqual(waves["writing_workbench_evolution"], 54)
        self.assertEqual(waves["consumer_side_modularization"], 45)

    def test_wave27_decisions_are_history_not_current_authority(self) -> None:
        report = build_check(REPO_ROOT)
        semantics = report["history_semantics"]

        self.assertEqual(semantics["classification"], "pre_closure_snapshots")
        self.assertFalse(semantics["deleted_json_or_jsonl_used_as_evidence"])

        broken = dict(report)
        broken["topics"] = [dict(topic) for topic in report["topics"]]
        broken["topics"][0]["historical_wave27"] = dict(broken["topics"][0]["historical_wave27"])
        broken["topics"][0]["historical_wave27"]["is_current_authority"] = True
        failures = validate_report(broken)
        self.assertIn(
            f"historical_decision_promoted_to_current:{broken['topics'][0]['topic_id']}",
            failures,
        )


if __name__ == "__main__":
    unittest.main()
