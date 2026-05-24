from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.unit


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_source_library_three_lane_live_closure.py"
    )
    spec = importlib.util.spec_from_file_location("check_source_library_three_lane_live_closure", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load source-library live closure checker: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_live_probe() -> dict:
    return {
        "probe_id": "source_library_public_live_probes_2026_05_22",
        "mode": {"allow_public_network": True, "skip_safe": True},
        "outputs": {
            "status_counts": {"candidate_ready_with_term_fallback": 1},
            "candidate_ready_targets": ["example_parser_weak"],
            "target_results": [
                {
                    "target": {
                        "target_id": "example_parser_weak",
                        "template": "https://example.com/search?q={{q}}",
                        "query_terms": ["robotics"],
                    },
                    "entry_domain": "example.com",
                    "classification": {"status": "candidate_ready_with_term_fallback"},
                    "adapter_result": {
                        "candidates": ["https://example.com/posts/robotics"],
                        "used_term_fallback": True,
                        "search_urls": ["https://example.com/search?q=robotics"],
                        "diagnostics": {"parser_profile_resolved": "fallback_anchor_only"},
                    },
                }
            ],
        },
        "validation": {
            "passed": True,
            "skipped": False,
            "live_evidence_sufficient": True,
            "errors": [],
        },
    }


def _fake_article_extraction_result() -> dict:
    return {
        "status": "ok",
        "records": [
            {
                "url": "https://example.com/posts/robotics",
                "title": "Robotics Funding",
                "content_text": "Robotics funding article body",
                "record_meta": {
                    "article_extraction": {
                        "contract_version": "external_project.article_body_extraction.v1",
                        "state": "article_body_extracted",
                        "extractor": "heuristic.main_content.v1",
                        "confidence": "medium",
                        "content_chars": 29,
                    }
                },
            }
        ],
        "errors": [],
        "runtime_diagnostics": {
            "provider_binding": {"provider_key": "external_project.article_extractor"},
            "diagnostics": {"article_body_extracted": 1},
        },
    }


class SourceLibraryThreeLaneLiveClosureTest(unittest.TestCase):
    def test_default_no_network_path_keeps_live_evidence_open(self) -> None:
        module = _load_module()

        contract = module.build_contract(
            targets=module.DEFAULT_TARGETS[:1],
            allow_public_network=False,
            max_candidates=2,
        )

        self.assertEqual(contract["contract_version"], "source_library.three_lane_live_closure.v1")
        self.assertTrue(contract["validation"]["passed"], contract["validation"]["errors"])
        self.assertFalse(contract["live_source_collection"]["complete"])
        self.assertTrue(contract["provider_article_extraction"]["skipped"])
        self.assertFalse(contract["human_review_readback"]["complete"])
        self.assertEqual(contract["closure_state"], "live_evidence_open")

    def test_live_probe_feeds_article_extractor_and_human_review_readback(self) -> None:
        module = _load_module()

        with patch.object(module, "run_probe", return_value=_fake_live_probe()), patch.object(
            module,
            "handle_external_project_manifest",
            return_value=_fake_article_extraction_result(),
        ):
            first = module.build_contract(allow_public_network=True, max_candidates=2)

        self.assertTrue(first["validation"]["passed"], first["validation"]["errors"])
        self.assertTrue(first["live_source_collection"]["complete"])
        self.assertTrue(first["provider_article_extraction"]["complete"])
        self.assertFalse(first["human_review_readback"]["complete"])
        self.assertEqual(
            first["closure_state"],
            "live_collection_article_extraction_ready_human_review_open",
        )
        blocker = first["human_review_readback"]["blocker"]
        self.assertEqual(blocker["status"], "human_review_evidence_missing")
        self.assertFalse(blocker["closure_allowed"])
        self.assertEqual(
            blocker["required_fields"],
            ["queue_id", "reviewed_by", "reviewed_at", "decision", "state"],
        )
        queue_ids = first["human_review_readback"]["readiness"]["review_queue"]["queue_ids"]
        self.assertEqual(len(queue_ids), 1)
        self.assertEqual(blocker["missing_queue_ids"], queue_ids)
        self.assertEqual(blocker["review_packet"][0]["queue_id"], queue_ids[0])
        self.assertEqual(blocker["review_packet"][0]["required_evidence"]["state"], "completed")

        human_evidence = [
            {
                "queue_id": queue_ids[0],
                "reviewed_by": "wave55-worker-c2",
                "reviewed_at": "2026-05-23T00:00:00Z",
                "decision": "accept_for_closure_evidence",
                "state": "completed",
            }
        ]
        with patch.object(module, "run_probe", return_value=_fake_live_probe()), patch.object(
            module,
            "handle_external_project_manifest",
            return_value=_fake_article_extraction_result(),
        ):
            reviewed = module.build_contract(
                allow_public_network=True,
                max_candidates=2,
                human_review_evidence=human_evidence,
            )

        self.assertTrue(reviewed["human_review_readback"]["complete"])
        self.assertTrue(reviewed["non_closure_markers"]["claims_human_review_complete"])
        self.assertEqual(
            reviewed["human_review_readback"]["blocker"]["status"],
            "closed_by_explicit_human_review_evidence",
        )
        self.assertTrue(reviewed["human_review_readback"]["blocker"]["closure_allowed"])
        self.assertEqual(
            reviewed["closure_state"],
            "live_collection_article_extraction_human_review_complete",
        )

    def test_candidate_selection_keeps_extraction_ready_and_review_required_rows(self) -> None:
        module = _load_module()
        probe = _fake_live_probe()
        probe["outputs"]["target_results"].append(
            {
                "target": {
                    "target_id": "example_ready",
                    "template": "https://example.com/search?q={{q}}",
                    "query_terms": ["robotics"],
                },
                "entry_domain": "example.com",
                "classification": {"status": "candidate_ready"},
                "adapter_result": {
                    "candidates": [
                        "https://example.com/posts/ready-one",
                        "https://example.com/posts/ready-two",
                    ],
                    "used_term_fallback": False,
                    "search_urls": ["https://example.com/search?q=robotics"],
                    "diagnostics": {},
                },
            }
        )

        rows = module._candidate_rows_from_probe(probe, max_candidates=2)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["url"], "https://example.com/posts/ready-one")
        self.assertTrue(any(row["used_term_fallback"] for row in rows))


if __name__ == "__main__":
    unittest.main()
