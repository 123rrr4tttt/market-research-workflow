from __future__ import annotations

import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest.canary_handoff import (
        CANARY_HANDOFF_CONTRACT_VERSION,
        build_single_url_canary_handoff,
    )
    from app.services.ingest.frontdoor_ingress import build_frontdoor_ingress_envelope
    from app.services.ingest.postprocess_frontdoor import run_postprocess_frontdoor
    from app.services.ingest import url_pool as url_pool_module

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class IngestCanaryHandoffUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest canary handoff tests require backend dependencies: {_IMPORT_ERROR}")

    def test_canary_handoff_builder_is_deterministic_and_keeps_live_gap_open(self):
        ingress = {
            "contract_version": "frontdoor.ingress.v1",
            "ingress_type": "source_library",
            "entrypoint": "ingest.url_pool",
            "source_mode": "url_execution",
            "project_key": "demo_proj",
            "source_ref": {
                "url": "https://example.com/search?q=robotics",
                "frontdoor_route_hint": "search_shell",
                "fetch_strategy": "search_candidate_route",
            },
            "meta": {"trace_id": "trace-1", "payload_hash": "hash-1"},
        }
        postprocess = {
            "status": "ok",
            "data": {
                "admission": "reject",
                "writer_result": None,
                "quality_assessment": {
                    "quality_score": 0.0,
                    "meaningful": False,
                    "provenance_ok": False,
                    "content_ok": True,
                    "strict_gate_enabled": True,
                    "strict_gate_source": "settings.ingest_guardrail_rollout_mode:canary",
                    "guardrail_rollout_mode": "canary",
                    "guardrail_canary_matched": True,
                    "guardrail_closure_claim": False,
                },
                "quality_gates": {
                    "gate_plus": {
                        "blocked": True,
                        "blocked_stage": "pre_fetch_url_gate",
                        "blocked_reason": "domain_blocked",
                    },
                    "gate_config": {
                        "enable_strict_gate": True,
                        "strict_gate_source": "settings.ingest_guardrail_rollout_mode:canary",
                        "guardrail_rollout": {
                            "contract_version": "ingest.guardrail_rollout.v1",
                            "enable_strict_gate": True,
                            "strict_gate_source": "settings.ingest_guardrail_rollout_mode:canary",
                            "rollout_mode": "canary",
                            "project_key": "demo_proj",
                            "rollout_eligible": True,
                            "canary_projects": ["demo_proj"],
                            "canary_matched": True,
                            "global_default_enabled": False,
                            "live_canary_validated": False,
                            "closure_claim": False,
                        },
                    },
                },
            },
            "meta": {"trace_id": "trace-1", "reason_code": "domain_blocked"},
        }

        first = build_single_url_canary_handoff(ingress_envelope=ingress, postprocess_frontdoor=postprocess)
        second = build_single_url_canary_handoff(ingress_envelope=ingress, postprocess_frontdoor=postprocess)

        self.assertEqual(first, second)
        self.assertEqual(first["contract_version"], CANARY_HANDOFF_CONTRACT_VERSION)
        self.assertEqual(first["handoff_state"], "partial_live_gap_open")
        self.assertEqual(first["strict_gate_state"]["state"], "strict_blocked")
        self.assertEqual(first["rollout"]["channel"], "canary")
        self.assertEqual(first["metrics_snapshot"]["sample_size"], 1)
        self.assertEqual(first["metrics_snapshot"]["guardrail_rollout"]["strict_enabled_samples"], 1)
        self.assertFalse(first["live_canary_validated"])
        self.assertFalse(first["closure_claim"])
        self.assertTrue(first["remaining_live_run_gaps"])

    def test_postprocess_attaches_canary_handoff_for_strict_canary_rejection(self):
        ingress = build_frontdoor_ingress_envelope(
            ingress_type="source_library",
            entrypoint="ingest.url_pool",
            source_mode="url_execution",
            project_key="demo_proj",
            source_ref={"url": "https://example.com/search?q=robotics"},
            collection_payload={
                "document_candidate": {
                    "uri": "https://example.com/search?q=robotics",
                    "title": "Search page",
                    "summary": "summary",
                    "content": "Robotics market update with enough meaningful context. " * 8,
                    "source_base_url": "example.com",
                    "doc_type": "market",
                },
                "terminal_context": {
                    "project_key": "demo_proj",
                    "source_mode": "url_execution",
                    "ingestion_entrypoint": "ingest.url_pool",
                    "capability_profile": {"source_library_collect_only": True},
                    "content_extraction": {"page_family": "article"},
                    "http_status": 200,
                    "light_filter": {"filter_decision": "accept", "filter_reason_code": "ok", "filter_score": 92},
                    "meaningful_gate_config": {"min_semantic_len": 20},
                },
            },
        )

        with (
            patch("app.services.ingest.postprocess_frontdoor.settings.ingest_enable_strict_gate", False),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_enable_strict_gate", False),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_rollout_mode", "canary"),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_canary_projects", "demo_proj"),
        ):
            result = run_postprocess_frontdoor(ingress_envelope=ingress, run_writer=True)

        handoff = result["data"]["canary_handoff"]
        self.assertEqual(result["data"]["admission"], "reject")
        self.assertEqual(handoff["strict_gate_state"]["state"], "strict_blocked")
        self.assertEqual(handoff["strict_gate_state"]["reason_code"], "domain_blocked")
        self.assertEqual(handoff["rollout"]["channel"], "canary")
        self.assertFalse(handoff["live_canary_validated"])
        self.assertIn("live canary execution", " ".join(handoff["remaining_live_run_gaps"]))

    def test_single_url_frontdoor_result_promotes_canary_handoff(self):
        content = " ".join(
            [
                f"Enterprise robotics adoption segment {idx} expanded across logistics, field operations, "
                f"warehouse safety, and service planning with customer evidence {idx}."
                for idx in range(40)
            ]
        )

        def _fake_route(**_kwargs):
            return {
                "records": [
                    {
                        "url": "https://example.com/article",
                        "title": "Example article",
                        "content_text": content,
                        "summary": "Enterprise robotics adoption expanded",
                        "source_label": "url_pool",
                        "record_meta": {"http_status": 200},
                    }
                ],
                "errors": [],
                "by_url": [{"url": "https://example.com/article", "status": "ok"}],
            }

        with (
            patch("app.services.projects.bind_project", return_value=nullcontext()),
            patch("app.services.source_library.resolver.list_effective_channels", return_value=[{"channel_key": "url_pool"}]),
            patch("app.services.source_library.resolver.run_item_with_url_routing", side_effect=_fake_route),
            patch("app.services.ingest.postprocess_frontdoor.persist_terminal_document", return_value={"doc_id": 90, "inserted": 1, "skipped": 0}),
            patch("app.services.ingest.postprocess_frontdoor.settings.ingest_enable_strict_gate", False),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_enable_strict_gate", False),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_rollout_mode", "canary"),
            patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_canary_projects", "demo_proj"),
        ):
            result = url_pool_module.ingest_url_via_source_library_frontdoor(
                url="https://example.com/article",
                project_key="demo_proj",
                query_terms=["robotics"],
                strict_mode=False,
                frontdoor_options={"enabled": True, "route_hint": "static_detail", "fetch_strategy": "http_fetch"},
                enable_extraction=False,
            )

        handoff = result["canary_handoff"]
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["inserted_valid"], 1)
        self.assertEqual(handoff["strict_gate_state"]["state"], "strict_passed")
        self.assertTrue(handoff["strict_gate_state"]["strict_gate_enabled"])
        self.assertEqual(handoff["rollout"]["channel"], "canary")
        self.assertEqual(handoff["metrics_snapshot"]["guardrail_rollout"]["strict_enabled_samples"], 1)
        self.assertEqual(handoff["frontdoor_run"]["source_url"], "https://example.com/article")


if __name__ == "__main__":
    unittest.main()
