from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_crawler_source_expansion_closure import CONTRACT_VERSION
from scripts.check_crawler_source_expansion_closure import PROTECTED_SHARED_INDEXES
from scripts.check_crawler_source_expansion_closure import build_check
from scripts.check_evidence_source_availability import EVIDENCE_SOURCE_UNAVAILABLE


REPO_ROOT = Path(__file__).resolve().parents[4]


class CrawlerSourceExpansionClosureCheckUnitTest(unittest.TestCase):
    def test_closure_check_fails_closed_when_required_evidence_is_unavailable(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertNotEqual(result["overall_status"], "closed")
        self.assertEqual(result["evidence_source"]["status"], EVIDENCE_SOURCE_UNAVAILABLE)
        self.assertFalse(result["validation"]["passed"])
        self.assertEqual(result["doc_drift"]["status"], "historical_snapshot_superseded")
        a5 = next(task for task in result["tasks"] if task["task_id"] == "A5")
        self.assertNotEqual(a5["status"], "closed")
        self.assertEqual(result["a5_gate"]["status"], EVIDENCE_SOURCE_UNAVAILABLE)
        self.assertEqual(result["public_replay_gate"]["overall_status"], EVIDENCE_SOURCE_UNAVAILABLE)
        self.assertTrue(all(value is False for value in result["evidence_source"]["authority_ceiling"].values()))

    def test_overall_status_does_not_close_without_public_replay_evidence(self) -> None:
        result = build_check(REPO_ROOT)

        non_closed = [task for task in result["tasks"] if task["status"] != "closed"]
        self.assertTrue(non_closed)
        self.assertNotEqual(result["overall_status"], "closed")

    def test_closure_check_keeps_shared_navigation_out_of_this_lane(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["protected_shared_indexes"], PROTECTED_SHARED_INDEXES)
        self.assertIn(
            "Keep A1-A4, A6, and A7 as evidence-closed through their existing code, fixture, and checker anchors.",
            result["minimum_development_plan"],
        )
        self.assertIn(
            "Treat A5 as closed only while the Wave47 opt-in public replay artifact and manual review note remain present.",
            result["minimum_development_plan"],
        )
        self.assertIn(
            "Keep public transport, anti-bot, and empty-source outcomes classified in output.public.json instead of hiding them.",
            result["minimum_development_plan"],
        )
        for protected_path in PROTECTED_SHARED_INDEXES:
            self.assertNotIn("2026-03-07-crawler-source-expansion/", protected_path)

    def test_crawler_source_expansion_closure_authority_metadata(self) -> None:
        return_hint = get_type_hints(build_check, include_extras=True)["return"]
        self.assertIs(get_origin(return_hint), Annotated)
        _, metadata = get_args(return_hint)
        self.assertEqual(
            metadata,
            "kit:non-authoritative derived_as=preflight fact_source=repository.crawler_expansion_anchor_and_gate_artifacts "
            "witness=test:test_crawler_source_expansion_closure_authority_metadata",
        )


if __name__ == "__main__":
    unittest.main()
