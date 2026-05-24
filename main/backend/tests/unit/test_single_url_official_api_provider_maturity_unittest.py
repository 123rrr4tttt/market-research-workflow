from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_single_url_official_api_provider_maturity import (  # noqa: E402
    CONTRACT_VERSION,
    build_report,
)


class SingleUrlOfficialApiProviderMaturityTestCase(unittest.TestCase):
    def test_crossref_fixture_reduces_non_arxiv_provider_blocker_without_closure_claim(self) -> None:
        report = build_report()

        self.assertEqual(report["contract_version"], CONTRACT_VERSION)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["decision_marker"], "single_url_non_arxiv_official_api_provider_reduced")
        self.assertFalse(report["closure_claim"])
        self.assertEqual(report["non_arxiv_provider_maturity"]["closed_provider"], "crossref")
        self.assertTrue(all(item["passed"] for item in report["token_results"]))
        self.assertTrue(all(item["passed"] for item in report["runtime_results"]))

        runtime = {item["name"]: item for item in report["runtime_results"]}
        self.assertTrue(runtime["crossref_policy_is_api_preferred"]["passed"])
        self.assertTrue(runtime["crossref_official_api_fixture_returns_candidates"]["passed"])
        self.assertTrue(runtime["crossref_provider_is_public_no_credential_boundary"]["passed"])
        self.assertEqual(report["live_crossref"]["status"], "not_requested")


if __name__ == "__main__":
    unittest.main()
