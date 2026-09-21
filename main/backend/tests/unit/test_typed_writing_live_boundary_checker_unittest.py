from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_typed_writing_live_boundary import (  # noqa: E402
    CONTRACT_VERSION,
    NOT_LIVE,
    REQUIRED_DETERMINISTIC_COVERAGE,
    REQUIRED_CLOSED_GAPS,
    build_inventory,
    validate_inventory,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


def _closed_live_readback_fixture() -> dict[str, object]:
    return {
        "passed": True,
        "execution_status": NOT_LIVE,
        "boundary_live": True,
        "route_live": True,
        "governance_mutation": True,
        "writing_context": True,
        "persisted_card_live": True,
    }


def _build_unit_inventory() -> dict[str, object]:
    return build_inventory(
        REPO_ROOT,
        live_readback_reader=_closed_live_readback_fixture,
    )


class TypedWritingLiveBoundaryCheckerUnitTestCase(unittest.TestCase):
    def test_checker_inventory_keeps_injected_contract_fixture_not_live(self) -> None:
        inventory = _build_unit_inventory()

        self.assertEqual(inventory["contract_version"], CONTRACT_VERSION)
        self.assertEqual(inventory["status"], "failed")
        self.assertEqual(inventory["readiness_state"], "not_live")
        self.assertEqual(inventory["closure_position"], "not_live")
        self.assertFalse(inventory["closure_claim_allowed"])
        self.assertEqual(inventory["live_readback_scope"], "injected_contract_fixture")
        self.assertEqual(inventory["live_execution_status"], NOT_LIVE)

        coverage = {row["code"]: row for row in inventory["deterministic_coverage"]}
        self.assertEqual(set(REQUIRED_DETERMINISTIC_COVERAGE).issubset(coverage), True)
        for code in REQUIRED_DETERMINISTIC_COVERAGE:
            self.assertTrue(coverage[code]["passed"], code)

        live_boundaries = {row["code"]: row for row in inventory["live_boundaries"]}
        self.assertEqual(set(REQUIRED_CLOSED_GAPS).issubset(live_boundaries), True)
        for code in REQUIRED_CLOSED_GAPS:
            self.assertFalse(live_boundaries[code]["closed"], code)
            self.assertFalse(live_boundaries[code]["gap_recorded"], code)

        self.assertEqual(inventory["unsupported_closure_claims"], [])

    def test_validator_rejects_reopened_live_db_api_ui_gaps(self) -> None:
        inventory = _build_unit_inventory()
        mutated = copy.deepcopy(inventory)
        mutated["readiness_state"] = "closed"
        mutated["live_boundaries"][0]["closed"] = False
        mutated["live_boundaries"][0]["gap_recorded"] = True

        failures = validate_inventory(mutated)

        self.assertIn("readiness_state_does_not_match_live_authority", failures)
        self.assertIn(
            f"live_boundary_not_closed:{mutated['live_boundaries'][0]['code']}",
            failures,
        )
        self.assertIn(
            f"live_boundary_gap_still_recorded:{mutated['live_boundaries'][0]['code']}",
            failures,
        )

    def test_production_live_reader_failure_is_not_live_and_fails_closed(self) -> None:
        with patch(
            "scripts.check_typed_writing_live_boundary._live_db_runtime_readback",
            return_value={
                "passed": False,
                "execution_status": NOT_LIVE,
                "error": "OperationalError: Operation not permitted",
            },
        ):
            inventory = build_inventory(REPO_ROOT)

        self.assertEqual(inventory["live_readback_scope"], "production_live")
        self.assertEqual(inventory["live_execution_status"], NOT_LIVE)
        self.assertEqual(inventory["status"], "failed")
        self.assertEqual(inventory["readiness_state"], "not_live")
        self.assertFalse(inventory["closure_claim_allowed"])
        self.assertIn("production_live_readback_not_verified", inventory["failures"])
        self.assertEqual(
            set(inventory["remaining_live_gaps"]),
            set(REQUIRED_CLOSED_GAPS),
        )

    def test_evidence_docs_include_wave54_closure_markers(self) -> None:
        inventory = _build_unit_inventory()
        docs = {row["path"]: row for row in inventory["evidence_docs"]}

        typed_doc = (
            "docs/development/development-plans/ARCHIVE_CLOSED/"
            "2026-03-07-typed-knowledge-organization/"
            "07_wave54-typed-writing-live-closure-2026-05-23.md"
        )
        writing_doc = (
            "docs/development/development-plans/ARCHIVE_CLOSED/"
            "2026-03-07-writing-workbench-evolution/"
            "08_wave54-typed-writing-live-closure-2026-05-23.md"
        )

        self.assertEqual(docs[typed_doc]["missing_markers"], [])
        self.assertEqual(docs[writing_doc]["missing_markers"], [])


if __name__ == "__main__":
    unittest.main()
