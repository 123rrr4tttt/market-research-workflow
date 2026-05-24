from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_single_url_official_api_provider_maturity import (  # noqa: E402
    CONTRACT_VERSION,
    PROVIDER_CREDENTIALS_EVIDENCE_CONTRACT_VERSION,
    build_report,
)


def _provider_credentials_evidence() -> dict:
    return {
        "contract_version": PROVIDER_CREDENTIALS_EVIDENCE_CONTRACT_VERSION,
        "evidence_scope": "provider_credentials_quota",
        "generated_by": "ops-provider-health-export",
        "generated_at": "2026-05-24T01:00:00Z",
        "credential_material_logged": False,
        "providers": [
            {
                "provider_key": "semanticscholar",
                "credential_state": "configured",
                "quota_status": "within_quota",
                "live_probe_status": "passed",
                "live_probe_authorized": True,
                "provider_specific_quota_validated": True,
                "credential_material_logged": False,
            }
        ],
    }


def _provider_credentials_configured_only_evidence() -> dict:
    evidence = _provider_credentials_evidence()
    evidence["providers"][0].update(
        {
            "quota_status": "configured_only",
            "live_probe_status": "configured_only",
            "live_probe_authorized": False,
            "provider_specific_quota_validated": False,
        }
    )
    return evidence


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
        self.assertFalse(
            report["non_arxiv_provider_maturity"]["provider_credentials_beyond_crossref_satisfied"]
        )

    def test_provider_credentials_artifact_can_close_beyond_crossref_boundary(self) -> None:
        report = build_report(provider_credentials_evidence=_provider_credentials_evidence())

        self.assertEqual(report["status"], "passed")
        maturity = report["non_arxiv_provider_maturity"]
        self.assertTrue(maturity["provider_credentials_beyond_crossref_satisfied"])
        self.assertEqual(maturity["provider_credentials_boundary"]["status"], "validated")
        self.assertFalse(
            any(
                "provider-specific credentials" in item
                for item in maturity["remaining_provider_catalog_boundary"]
            )
        )

    def test_provider_credentials_without_live_authorization_is_configured_only(self) -> None:
        report = build_report(provider_credentials_evidence=_provider_credentials_configured_only_evidence())

        self.assertEqual(report["status"], "passed")
        maturity = report["non_arxiv_provider_maturity"]
        boundary = maturity["provider_credentials_boundary"]
        self.assertFalse(maturity["provider_credentials_beyond_crossref_satisfied"])
        self.assertEqual(boundary["status"], "configured_only")
        self.assertEqual(boundary["configured_only_provider_count"], 1)
        self.assertIn(
            "provider-specific credentials and quota behavior beyond public Crossref remain external",
            maturity["remaining_provider_catalog_boundary"],
        )

    def test_invalid_provider_credentials_artifact_fails_gate(self) -> None:
        evidence = _provider_credentials_evidence()
        evidence["providers"][0]["credential_material_logged"] = True

        report = build_report(provider_credentials_evidence=evidence)

        self.assertEqual(report["status"], "failed")
        maturity = report["non_arxiv_provider_maturity"]
        self.assertFalse(maturity["provider_credentials_beyond_crossref_satisfied"])
        self.assertEqual(maturity["provider_credentials_boundary"]["status"], "failed_evidence")

    def test_provider_credentials_artifact_rejects_secret_material_without_echoing_value(self) -> None:
        evidence = _provider_credentials_evidence()
        evidence["providers"][0]["api_key"] = "fixture-material-should-not-echo"

        report = build_report(provider_credentials_evidence=evidence)

        self.assertEqual(report["status"], "failed")
        boundary = report["non_arxiv_provider_maturity"]["provider_credentials_boundary"]
        self.assertEqual(boundary["status"], "failed_evidence")
        self.assertIn("$.providers[0].api_key", boundary["secret_material_field_paths"])
        self.assertNotIn("fixture-material-should-not-echo", str(report))


if __name__ == "__main__":
    unittest.main()
