from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.resource_pool.unified_search import unified_search_by_item_payload
from app.services.source_library.relevance_review import CONTRACT_VERSION
from app.services.source_library.relevance_review import annotate_records_with_relevance_review_queue
from app.services.source_library.relevance_review import build_relevance_review_queue
from app.services.source_library.resolver import run_item_payload
from scripts.check_source_library_relevance_review_queue import build_check


REPO_ROOT = Path(__file__).resolve().parents[4]


class SourceLibraryRelevanceReviewQueueUnitTestCase(unittest.TestCase):
    def test_queue_is_deterministic_and_fail_closed_for_anchor_only_low_confidence_candidate(self) -> None:
        queue = build_relevance_review_queue(
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
                    "relevance_review_required": True,
                }
            },
            runtime_diagnostics=[
                {
                    "site_url": "https://example.com/search?q={{q}}",
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
        repeat = build_relevance_review_queue(
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
                    "relevance_review_required": True,
                }
            },
            runtime_diagnostics=[
                {
                    "site_url": "https://example.com/search?q={{q}}",
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

        self.assertEqual(queue["contract_version"], CONTRACT_VERSION)
        self.assertEqual(queue["summary"]["queued_count"], 1)
        self.assertEqual(queue["queue_state"], "ready_for_review")
        self.assertEqual(queue["entries"][0]["queue_id"], repeat["entries"][0]["queue_id"])
        self.assertEqual(
            set(queue["entries"][0]["reason_codes"]),
            {
                "fallback_anchor_only_profile",
                "term_fallback_candidates",
                "low_confidence_candidate",
                "adapter_capability_review",
            },
        )
        self.assertTrue(queue["entries"][0]["reviewer_ready"])
        self.assertFalse(queue["entries"][0]["fail_closed"]["auto_accept_allowed"])
        self.assertFalse(queue["entries"][0]["fail_closed"]["auto_ingest_allowed"])
        self.assertFalse(queue["entries"][0]["gap_markers"]["human_relevance_review_completed"])
        self.assertFalse(queue["entries"][0]["gap_markers"]["live_public_replay_completed"])

    def test_annotation_preserves_record_meta_and_marks_review_required(self) -> None:
        queue = build_relevance_review_queue(
            project_key="demo_proj",
            item_key="handler.cluster.search_template",
            query_terms=["robotics"],
            candidates=["https://example.com/posts/robotics-review"],
            candidate_refs={
                "https://example.com/posts/robotics-review": {
                    "site_entry_url": "https://example.com/search?q={{q}}",
                    "domain": "example.com",
                    "entry_domain": "example.com",
                    "matched_by": "none",
                    "candidate_quality": "low",
                    "usable_for_search": False,
                }
            },
        )

        annotated = annotate_records_with_relevance_review_queue(
            [
                {
                    "record_id": "candidate:0:https://example.com/posts/robotics-review",
                    "url": "https://example.com/posts/robotics-review",
                    "record_meta": {"artifact_ref": {"local_path": "/tmp/alpha.pdf"}},
                }
            ],
            queue,
        )

        meta = annotated[0]["record_meta"]
        self.assertEqual(meta["artifact_ref"]["local_path"], "/tmp/alpha.pdf")
        review = meta["source_library_relevance_review"]
        self.assertEqual(review["contract_version"], CONTRACT_VERSION)
        self.assertEqual(review["state"], "review_required")
        self.assertFalse(review["review_completed"])
        self.assertFalse(review["auto_accept_allowed"])

    def test_unified_search_emits_queue_for_anchor_only_parser_profile(self) -> None:
        item = {
            "item_key": "search-item",
            "params": {
                "site_entries": ["https://example.com/search?q={{q}}"],
            },
        }
        with patch(
            "app.services.resource_pool.unified_search.get_site_entry_by_url",
            return_value={
                "site_url": "https://example.com/search?q={{q}}",
                "domain": "example.com",
                "entry_type": "search_template",
                "channel_key": "generic_web.search_template",
                "template": "https://example.com/search?q={{q}}",
                "capabilities": {"supports_query_terms": True, "keyword_mode": "search"},
                "extra": {"remediation": {"parser_profile": "fallback_anchor_only"}},
            },
        ), patch(
            "app.services.resource_pool.unified_search.execute_search_template",
            return_value=SimpleNamespace(
                selected_candidates=[
                    SimpleNamespace(
                        url="https://example.com/posts/robotics-review",
                        matched_by="none",
                        candidate_quality="low",
                        usable_for_search=False,
                        score=0.1,
                        route_kind="page",
                    )
                ],
                used_term_fallback=True,
                errors=[],
                diagnostics={"search_service": "basic"},
            ),
        ):
            result = unified_search_by_item_payload(
                project_key="demo_proj",
                item=item,
                query_terms=["robotics"],
                allow_term_fallback=True,
            )

        queue = result.relevance_review_queue
        self.assertEqual(queue["summary"]["queued_count"], 1)
        self.assertEqual(queue["entries"][0]["reviewer_fields"]["url"], "https://example.com/posts/robotics-review")
        self.assertIn("fallback_anchor_only_profile", queue["entries"][0]["reason_codes"])
        self.assertIn("term_fallback_candidates", queue["entries"][0]["reason_codes"])

    def test_source_library_frontdoor_propagates_queue_to_records(self) -> None:
        item = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "generic_web.search_template",
            "enabled": True,
            "params": {
                "site_entries": ["https://example.com/search?q=%7B%7Bq%7D%7D"],
                "expected_entry_type": "search_template",
            },
            "extra": {
                "stable_handler_cluster": True,
                "expected_entry_type": "search_template",
            },
        }
        queue = build_relevance_review_queue(
            project_key="demo_proj",
            item_key="handler.cluster.search_template",
            query_terms=["alpha"],
            candidates=["https://example.com/posts/alpha"],
            candidate_refs={
                "https://example.com/posts/alpha": {
                    "site_entry_url": "https://example.com/search?q=alpha",
                    "domain": "example.com",
                    "entry_domain": "example.com",
                    "matched_by": "none",
                    "candidate_quality": "low",
                    "usable_for_search": False,
                }
            },
        )

        with patch(
            "app.services.resource_pool.unified_search_by_item_payload",
            return_value=SimpleNamespace(
                site_entries_used=[{"site_url": "https://example.com/search?q=alpha"}],
                runtime_diagnostics=[{"site_url": "https://example.com/search?q=alpha"}],
                candidates=["https://example.com/posts/alpha"],
                written={"urls_new": 0, "urls_skipped": 0},
                ingest_result={"inserted": 0, "updated": 0, "skipped": 0, "inserted_valid": 0, "rejected_count": 0, "rejection_breakdown": {}},
                errors=[],
                relevance_review_queue=queue,
            ),
        ), patch(
            "app.services.source_library.resolver.run_item_with_url_routing",
            return_value={"inserted": 0, "updated": 0, "skipped": 0, "errors": [], "by_url": []},
        ):
            raw = run_item_payload(
                item=item,
                channels=[],
                project_key="demo_proj",
                override_params={"query_terms": ["alpha"], "_allow_internal_generic_web": True},
            )

        frontdoor_queue = raw["result"]["relevance_review_queue"]
        self.assertEqual(frontdoor_queue["summary"]["queued_count"], 1)
        self.assertEqual(raw["result"]["candidate_pipeline"]["relevance_review"]["queued_count"], 1)
        record_review = raw["result"]["records"][0]["record_meta"]["source_library_relevance_review"]
        self.assertEqual(record_review["state"], "review_required")
        self.assertFalse(record_review["review_completed"])

    def test_checker_preserves_review_queue_readiness_as_non_closure(self) -> None:
        result = build_check(REPO_ROOT)

        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertTrue(result["validation"]["passed"], result["validation"]["errors"])
        self.assertFalse(result["validation"]["public_network_attempted"])
        self.assertFalse(result["governance_scope"]["claims_human_relevance_review_complete"])
        self.assertFalse(result["governance_scope"]["claims_live_public_replay_complete"])
        self.assertEqual(result["fixture"]["queue"]["summary"]["queued_count"], 1)


if __name__ == "__main__":
    unittest.main()
