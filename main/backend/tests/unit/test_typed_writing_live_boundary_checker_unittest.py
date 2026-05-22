from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_typed_writing_live_boundary import (  # noqa: E402
    CLOSURE_POSITION,
    CONTRACT_VERSION,
    REQUIRED_DETERMINISTIC_COVERAGE,
    REQUIRED_OPEN_GAPS,
    build_inventory,
    validate_inventory,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class TypedWritingLiveBoundaryCheckerUnitTestCase(unittest.TestCase):
    def test_checker_inventory_passes_with_deterministic_coverage_and_open_live_gaps(self) -> None:
        inventory = build_inventory(REPO_ROOT)

        self.assertEqual(inventory["contract_version"], CONTRACT_VERSION)
        self.assertEqual(inventory["status"], "passed")
        self.assertEqual(inventory["readiness_state"], "partial")
        self.assertEqual(inventory["closure_position"], CLOSURE_POSITION)
        self.assertFalse(inventory["closure_claim_allowed"])
        self.assertEqual(validate_inventory(inventory), [])

        coverage = {row["code"]: row for row in inventory["deterministic_coverage"]}
        self.assertEqual(set(REQUIRED_DETERMINISTIC_COVERAGE).issubset(coverage), True)
        for code in REQUIRED_DETERMINISTIC_COVERAGE:
            self.assertTrue(coverage[code]["passed"], code)

        live_boundaries = {row["code"]: row for row in inventory["live_boundaries"]}
        self.assertEqual(set(REQUIRED_OPEN_GAPS).issubset(live_boundaries), True)
        for code in REQUIRED_OPEN_GAPS:
            self.assertFalse(live_boundaries[code]["closed"], code)
            self.assertTrue(live_boundaries[code]["gap_recorded"], code)

        self.assertIn("typed_writing_live_boundary_closed", {
            row["code"] for row in inventory["unsupported_closure_claims"]
        })

    def test_validator_rejects_live_db_api_ui_overclaims(self) -> None:
        inventory = build_inventory(REPO_ROOT)
        mutated = copy.deepcopy(inventory)
        mutated["closure_claim_allowed"] = True
        mutated["live_boundaries"][0]["closed"] = True

        failures = validate_inventory(mutated)

        self.assertIn("closure_claim_allowed_must_remain_false", failures)
        self.assertIn(
            f"live_boundary_overclaimed:{mutated['live_boundaries'][0]['code']}",
            failures,
        )

    def test_evidence_docs_include_wave15_boundary_markers(self) -> None:
        inventory = build_inventory(REPO_ROOT)
        docs = {row["path"]: row for row in inventory["evidence_docs"]}

        typed_doc = (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-03-07-typed-knowledge-organization/"
            "06_wave15-typed-writing-live-boundary-2026-05-22.md"
        )
        writing_doc = (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-03-07-writing-workbench-evolution/"
            "07_wave15-typed-writing-live-boundary-2026-05-22.md"
        )

        self.assertEqual(docs[typed_doc]["missing_markers"], [])
        self.assertEqual(docs[writing_doc]["missing_markers"], [])


if __name__ == "__main__":
    unittest.main()
