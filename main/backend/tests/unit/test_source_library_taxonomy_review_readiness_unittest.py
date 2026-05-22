from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.source_library.relevance_review import CONTRACT_VERSION
from app.services.source_library.relevance_review import TAXONOMY_REVIEW_READINESS_CONTRACT_VERSION
from app.services.source_library.relevance_review import build_relevance_review_queue
from app.services.source_library.relevance_review import build_taxonomy_review_readiness
from scripts.check_source_library_taxonomy_review_readiness import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]


def _fixture_queue() -> dict:
    return build_relevance_review_queue(
        project_key="demo_proj",
        item_key="handler.cluster.search_template",
        query_terms=["robotics funding"],
        candidates=["https://example.com/posts/robotics-review"],
        candidate_refs={
            "https://example.com/posts/robotics-review": {
                "site_entry_url": "https://example.com/search?q={{q}}",
                "domain": "example.com",
                "entry_domain": "example.com",
                "candidate_source": "search_template",
                "site_policy": "keep",
                "search_service": "basic",
                "matched_by": "none",
                "route_kind": "page",
                "candidate_quality": "low",
                "usable_for_search": False,
                "adapter_capability_status": "review",
                "adapter_capability_reason": "low_confidence_anchor_only_profile",
                "parser_profile_resolved": "fallback_anchor_only",
                "candidate_review_state": "relevance_review",
                "relevance_review_required": True,
            }
        },
        runtime_diagnostics=[
            {
                "site_url": "https://example.com/search?q={{q}}",
                "adapter_capability_status": "review",
                "adapter_capability_reason": "low_confidence_anchor_only_profile",
                "parser_profile_resolved": "fallback_anchor_only",
                "relevance_review_required": True,
                "relevance_review_reason": "term_fallback_candidates",
            }
        ],
        errors=[
            {
                "site_url": "https://example.com/search?q={{q}}",
                "error": "url_term_filter_empty_fallback_used",
            }
        ],
    )


def _taxonomy_cases() -> list[dict]:
    return [
        {
            "case_id": "handler_cluster_site_search_taxonomy",
            "item_key": "handler.cluster.search_template",
            "item_channel_key": "handler.cluster",
            "source_mode": "site_search",
            "warnings": ["source_mode_coerced_by_site_search_taxonomy:protocol_search->site_search"],
            "taxonomy": {
                "channel_family": "handler_cluster",
                "item_type": "service_aggregated",
                "managed_by": "system",
                "expected_entry_type": "search_template",
                "internal_adapter_only": False,
                "site_search_authoritative": True,
            },
        }
    ]


class SourceLibraryTaxonomyReviewReadinessUnitTestCase(unittest.TestCase):
    def test_readiness_distinguishes_review_queue_ready_from_completed_human_review(self) -> None:
        queue = _fixture_queue()
        result = build_taxonomy_review_readiness(
            taxonomy_cases=_taxonomy_cases(),
            review_queue=queue,
        )

        self.assertEqual(queue["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["contract_version"], TAXONOMY_REVIEW_READINESS_CONTRACT_VERSION)
        self.assertEqual(result["readiness"]["taxonomy_readiness"], "ready")
        self.assertTrue(result["readiness"]["review_queue_ready"])
        self.assertFalse(result["readiness"]["human_review_completed"])
        self.assertEqual(result["human_review"]["completion_claim"], "not_claimed")
        self.assertEqual(result["review_queue"]["queued_count"], 1)

    def test_completed_human_review_requires_evidence_for_every_queue_id(self) -> None:
        queue = _fixture_queue()
        queue_id = queue["entries"][0]["queue_id"]

        result = build_taxonomy_review_readiness(
            taxonomy_cases=_taxonomy_cases(),
            review_queue=queue,
            human_review_evidence=[
                {
                    "queue_id": queue_id,
                    "reviewed_by": "reviewer@example.com",
                    "reviewed_at": "2026-05-22T12:00:00Z",
                    "decision": "accept",
                    "state": "completed",
                }
            ],
        )

        self.assertTrue(result["readiness"]["human_review_completed"])
        self.assertEqual(result["human_review"]["completion_claim"], "evidence_complete")
        self.assertEqual(result["human_review"]["completed_queue_ids"], [queue_id])

    def test_missing_taxonomy_fields_block_taxonomy_readiness(self) -> None:
        result = build_taxonomy_review_readiness(
            taxonomy_cases=[
                {
                    "case_id": "broken_taxonomy",
                    "source_mode": "site_search",
                    "taxonomy": {"channel_family": "handler_cluster"},
                }
            ],
            review_queue=_fixture_queue(),
        )

        self.assertEqual(result["readiness"]["taxonomy_readiness"], "blocked")
        self.assertFalse(result["taxonomy"]["ready"])
        self.assertIn("taxonomy.item_type", result["taxonomy"]["cases"][0]["missing_fields"])

    def test_checker_reports_taxonomy_ready_and_human_review_open(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], TAXONOMY_REVIEW_READINESS_CONTRACT_VERSION)
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertEqual(result["governance_scope"]["taxonomy_readiness"], "ready")
        self.assertTrue(result["governance_scope"]["review_queue_ready"])
        self.assertFalse(result["governance_scope"]["human_review_completed"])

        readiness = result["taxonomy_review_readiness"]
        cases = {row["case_id"]: row for row in readiness["taxonomy"]["cases"]}
        self.assertEqual(cases["handler_cluster_site_search_taxonomy"]["source_mode"], "site_search")
        self.assertEqual(cases["crawler_provider_harvest_taxonomy"]["source_mode"], "provider_harvest")
        self.assertEqual(cases["candidate_url_execution_taxonomy"]["source_mode"], "url_execution")
        self.assertEqual(len(result["evidence_docs"]["docs"]), 3)


if __name__ == "__main__":
    unittest.main()
