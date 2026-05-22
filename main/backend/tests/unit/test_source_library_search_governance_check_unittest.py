from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.check_source_library_search_governance import CONTRACT_VERSION
from scripts.check_source_library_search_governance import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]


class SourceLibrarySearchGovernanceCheckUnitTestCase(unittest.TestCase):
    def test_governance_checker_keeps_mounting_and_capability_boundaries(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["governance_scope"]["claims_full_45_site_public_replay"])
        self.assertFalse(result["governance_scope"]["claims_human_relevance_review_complete"])

        routes = {row["route_id"]: row for row in result["mount_routes"]["routes"]}
        self.assertTrue(routes["source_library_authoritative_sync"]["present"])
        self.assertEqual(
            routes["source_library_authoritative_sync"]["public_path"],
            "/api/v1/ingest/source-library/run",
        )
        self.assertEqual(
            routes["source_library_legacy_item_run"]["expected_status"],
            "410_gone_no_execution",
        )
        self.assertEqual(
            routes["resource_pool_unified_search"]["governance_role"],
            "capability_endpoint_not_source_library_frontdoor",
        )

        resolver_cases = result["resolver"]["cases"]
        self.assertEqual(resolver_cases["handler_cluster_forces_site_search"]["source_mode"], "site_search")
        self.assertIn(
            "source_mode_coerced_by_site_search_taxonomy:protocol_search->site_search",
            resolver_cases["handler_cluster_forces_site_search"]["warnings"],
        )
        self.assertEqual(resolver_cases["candidate_urls_override_to_url_execution"]["source_mode"], "url_execution")
        self.assertIn(
            "generic_web_internal_adapter_detected",
            resolver_cases["generic_web_stays_internal_site_search"]["warnings"],
        )

    def test_checker_preserves_public_replay_and_relevance_review_as_open_gaps(self) -> None:
        result = build_check(REPO_ROOT)

        replay = result["public_replay_gaps"]
        self.assertIn(
            replay["a5_status"],
            {
                "deterministic_replay_gate_closed_external_public_replay_blocked",
                "full_public_replay_artifact_present_review_required",
            },
        )
        self.assertFalse(replay["public_network_attempted"])

        review = replay["term_fallback_relevance_review"]
        self.assertEqual(review["status"], "review_required_not_full_closure")
        self.assertGreaterEqual(review["review_target_count"], 1)

        capability_cases = result["adapter_capability"]["cases"]
        self.assertEqual(capability_cases["validated_domain_profile"]["adapter_capability_status"], "allow")
        self.assertEqual(capability_cases["unknown_profile_downgraded"]["adapter_capability_status"], "downgrade")
        self.assertEqual(capability_cases["anchor_only_requires_review"]["adapter_capability_status"], "review")
        self.assertTrue(capability_cases["anchor_only_requires_review"]["candidate_relevance_review_required"])


if __name__ == "__main__":
    unittest.main()
