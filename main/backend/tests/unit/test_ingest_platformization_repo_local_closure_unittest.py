from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_ingest_platformization_repo_local_closure import (  # noqa: E402
    CONTRACT_VERSION,
    TOPIC_SLUG,
    build_check,
    validate_report,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


class IngestPlatformizationRepoLocalClosureUnitTestCase(unittest.TestCase):
    def test_wave29_checker_closes_repo_local_blockers_and_recommends_external_blocked(self) -> None:
        report = build_check(REPO_ROOT)

        self.assertEqual(report["contract_version"], CONTRACT_VERSION)
        self.assertEqual(report["topic_slug"], TOPIC_SLUG)
        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["canary_gate"]["canary_repo_local_gate_sufficient"])
        self.assertEqual(report["repo_local_blockers_open"], [])
        self.assertEqual(report["archive_recommendation"], "external_blocked")
        self.assertEqual(report["recommended_location"], "ARCHIVE_EXTERNAL_BLOCKED")
        self.assertFalse(report["protected_shared_indexes_edited"])

        blockers = {item["code"]: item for item in report["repo_local_blockers"]}
        self.assertEqual(
            set(blockers),
            {
                "broader_fetch_router_decomposition",
                "shared_gate_service_rule_source_consolidation",
                "default_propagation_drift_control",
                "replay_slo_observability",
                "frontend_ops_entry_closure",
            },
        )
        for blocker in blockers.values():
            self.assertEqual(blocker["status"], "closed_repo_local")
            self.assertTrue(blocker["closed_repo_local"])
            self.assertTrue(all(anchor["passed"] for anchor in blocker["anchors"]))

        slo = blockers["replay_slo_observability"]["dynamic_evidence"]["frontdoor_slo_fixture"]
        self.assertEqual(slo["contract_version"], "ingest.frontdoor_slo.v1")
        self.assertIsNotNone(slo["p95_latency_ms"])
        self.assertFalse(slo["closure_claim"])

    def test_validator_rejects_reopened_repo_local_blocker(self) -> None:
        report = build_check(REPO_ROOT)
        report["repo_local_blockers"][0]["closed_repo_local"] = False
        report["repo_local_blockers"][0]["status"] = "open_missing_repo_evidence"
        report["repo_local_blockers_open"] = [report["repo_local_blockers"][0]["code"]]
        report["archive_recommendation"] = "retain_current_dev"

        errors = validate_report(report)

        self.assertTrue(any("blocker must be closed" in error for error in errors))
        self.assertTrue(any("repo_local_blockers_open" in error for error in errors))
        self.assertTrue(any("archive_recommendation" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
