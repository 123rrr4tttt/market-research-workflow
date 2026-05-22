from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.ingest.frontdoor_ingress import (
    build_discovery_ingress_envelope,
    build_raw_import_ingress_envelope,
    build_source_library_ingress_envelope,
)
from app.services.ingest.postprocess_frontdoor import _evaluate_quality_frontdoor, run_postprocess_frontdoor


class PostprocessFrontdoorUnitTestCase(unittest.TestCase):
    def test_frontdoor_quality_gate_reads_runtime_settings(self) -> None:
        document_candidate = {
            "uri": "https://example.com/article",
            "title": "Example article",
            "summary": "summary",
            "content": "short content",
            "source_base_url": "example.com",
            "doc_type": "market",
        }
        terminal_context = {
            "capability_profile": {"entry_type": "rss"},
            "content_extraction": {"page_family": "article"},
            "http_status": 200,
            "light_filter": {"filter_decision": "accept", "filter_reason_code": "ok", "filter_score": 92},
        }

        with (
            patch("app.services.ingest.postprocess_frontdoor.settings.ingest_enable_strict_gate", False),
            patch("app.services.ingest.postprocess_frontdoor.settings.ingest_min_semantic_len", 640),
        ):
            result = _evaluate_quality_frontdoor(
                document_candidate=document_candidate,
                terminal_context=terminal_context,
            )

        gate_plus = result["quality_gates"]["gate_plus"]
        content_check = next(check for check in gate_plus["checks"] if check["stage"] == "pre_write_content_gate")
        self.assertFalse(content_check["blocked"])
        self.assertEqual(content_check["reason_code"], "disabled")
        self.assertEqual(content_check["diagnostics"]["min_semantic_len"], 640)
        self.assertEqual(result["quality_gates"]["gate_config"]["enable_strict_gate"], False)
        self.assertEqual(result["quality_gates"]["gate_config"]["strict_gate_source"], "disabled")

    def test_frontdoor_quality_gate_strict_mode_forces_request_level_gate(self) -> None:
        document_candidate = {
            "uri": "https://example.com/search?q=robotics",
            "title": "Search page",
            "summary": "summary",
            "content": "Robotics market update with enough meaningful context. " * 8,
            "source_base_url": "example.com",
            "doc_type": "market",
        }
        terminal_context = {
            "strict_mode": True,
            "meaningful_gate_config": {"min_semantic_len": 20},
            "capability_profile": {"entry_type": "search_template"},
            "content_extraction": {"page_family": "article"},
            "http_status": 200,
            "light_filter": {"filter_decision": "accept", "filter_reason_code": "ok", "filter_score": 92},
        }

        with patch("app.services.ingest.postprocess_frontdoor.settings.ingest_enable_strict_gate", False):
            result = _evaluate_quality_frontdoor(
                document_candidate=document_candidate,
                terminal_context=terminal_context,
            )

        self.assertEqual(result["admission"], "reject")
        self.assertEqual(result["reason_code"], "domain_blocked")
        self.assertFalse(result["quality_assessment"]["meaningful"])
        self.assertFalse(result["quality_assessment"]["provenance_ok"])
        self.assertTrue(result["quality_assessment"]["content_ok"])
        self.assertTrue(result["quality_assessment"]["strict_gate_enabled"])
        self.assertEqual(result["quality_assessment"]["strict_gate_source"], "terminal_context.strict_mode")
        gate_config = result["quality_gates"]["gate_config"]
        self.assertTrue(gate_config["enable_strict_gate"])
        self.assertEqual(gate_config["strict_gate_source"], "terminal_context.strict_mode")
        self.assertEqual(gate_config["min_semantic_len"], 20)
        self.assertEqual(result["quality_gates"]["url_gate"]["reason"], "url_policy_low_value_endpoint")

    def test_source_library_terminal_output_is_deferred_without_writer(self) -> None:
        terminal_output = {
            "contract_version": "source_library.terminal_output.v1",
            "status": "ok",
            "source_mode": "site_search",
            "item": {"item_key": "handler.cluster.search_template", "item_type": "service_aggregated", "managed_by": "system"},
            "request": {"project_key": "demo_proj"},
            "results": {"records": [{"record_id": "r1", "url": "https://example.com/a"}], "stats": {"fetched": 1, "normalized": 1, "dropped": 0, "errors": 0}},
            "errors": [],
            "meta": {"reason_code": "ok", "retryable": False, "trace_id": "trace-1"},
            "raw_snapshot": {"raw": True},
        }

        ingress = build_source_library_ingress_envelope(terminal_output=terminal_output, legacy_result={"item_key": "handler.cluster.search_template"})
        self.assertEqual(ingress["source_ref"]["entrypoint"], "ingest.source_library.run")
        self.assertEqual(ingress["source_ref"]["source_mode"], "site_search")
        self.assertEqual(ingress["source_ref"]["project_key"], "demo_proj")
        self.assertEqual(ingress["source_ref"]["ingress_type"], "source_library")
        result = run_postprocess_frontdoor(ingress_envelope=ingress, run_writer=False)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["admission"], "defer")
        self.assertEqual(result["data"]["dispatch_plan"]["run_writer"], False)
        self.assertEqual(result["meta"]["reason_code"], "deferred")

    def test_source_library_ingress_surfaces_record_pdf_artifacts(self) -> None:
        terminal_output = {
            "contract_version": "source_library.terminal_output.v1",
            "status": "ok",
            "source_mode": "site_search",
            "item": {"item_key": "handler.cluster.search_template", "item_type": "service_aggregated", "managed_by": "system"},
            "request": {"project_key": "demo_proj"},
            "results": {
                "records": [
                    {
                        "record_id": "r1",
                        "url": "https://arxiv.org/abs/1808.00177v5",
                        "title": "Learning Dexterous In-Hand Manipulation",
                        "content_text": "Abstract",
                        "record_meta": {
                            "artifact_ref": {
                                "artifact_source": "pdf",
                                "artifact_role": "primary_source_pdf",
                                "source_locator": "https://arxiv.org/pdf/1808.00177v5.pdf",
                                "mime_type": "application/pdf",
                            }
                        },
                    }
                ],
                "stats": {"fetched": 1, "normalized": 1, "dropped": 0, "errors": 0},
            },
            "errors": [],
            "meta": {"reason_code": "ok", "retryable": False, "trace_id": "trace-1"},
            "raw_snapshot": {"raw": True},
        }

        ingress = build_source_library_ingress_envelope(terminal_output=terminal_output, legacy_result={"item_key": "handler.cluster.search_template"})

        self.assertEqual(
            ingress["collection_payload"]["source_artifacts"],
            [
                {
                    "artifact_source": "pdf",
                    "artifact_role": "primary_source_pdf",
                    "source_locator": "https://arxiv.org/pdf/1808.00177v5.pdf",
                    "mime_type": "application/pdf",
                    "parent_url": "https://arxiv.org/abs/1808.00177v5",
                }
            ],
        )

    def test_frontdoor_uses_extraction_plan_when_outcome_missing(self) -> None:
        ingress = build_discovery_ingress_envelope(
            project_key=None,
            item={
                "uri": "https://example.com/discovery",
                "doc_type": "market",
                "title": "Discovery item",
                "content": "meaningful discovery content " * 20,
                "summary": "summary",
                "text_hash": "hash-2",
                "source_name": "example.com",
                "source_kind": "web",
                "source_base_url": "example.com",
                "extracted_data_base": {},
            },
        )
        self.assertEqual(ingress["source_ref"]["entrypoint"], "discovery.store")
        self.assertEqual(ingress["source_ref"]["source_mode"], "discovery")
        self.assertEqual(ingress["source_ref"]["ingress_type"], "discovery")
        self.assertEqual(ingress["source_ref"]["domain"], "example.com")
        collection_payload = ingress["collection_payload"]
        collection_payload["terminal_context"] = {
            "platform": "discovery",
            "ingestion_entrypoint": "discovery.store",
            "source_mode": "discovery",
            "quality_score": 0.0,
            "degradation_flags": [],
            "http_status": None,
            "capability_profile": {},
            "light_filter": {},
        }
        collection_payload["extraction_plan"] = {
            "enabled": True,
            "include_market": True,
            "include_policy": False,
            "include_sentiment": False,
            "include_company": True,
            "include_product": False,
            "include_operation": False,
        }

        with patch(
            "app.services.ingest.postprocess_frontdoor.run_unified_structured_extraction",
            return_value={
                "status": "ok",
                "reason": None,
                "error": None,
                "domains": {"market": {"state": "CA"}},
                "summary": {},
                "extractor_version": "unified.structured.v1",
                "model_profile": {},
                "prompt_profile": {},
                "structured_output_mode": "unknown",
            },
        ) as extraction_mock, patch(
            "app.services.ingest.postprocess_frontdoor.persist_terminal_document",
            return_value={"doc_id": 62, "inserted": 1, "skipped": 0, "reason": "inserted", "doc_type": "market"},
        ):
            result = run_postprocess_frontdoor(ingress_envelope=ingress, run_writer=True)

        self.assertEqual(result["data"]["admission"], "accept")
        extraction_mock.assert_called_once()
        call = extraction_mock.call_args.kwargs
        self.assertEqual(call["include_market"], True)
        self.assertEqual(call["include_policy"], False)
        self.assertEqual(call["include_product"], False)
        self.assertEqual(result["data"]["normalized_payload"]["extracted_data"]["market"]["state"], "CA")

    def test_frontdoor_cleans_content_before_quality_and_extraction(self) -> None:
        noisy_content = "\n".join(
            ["Skip to content", "Accessibility Help"]
            + [f"Meaningful market signal line {idx} with enough semantic detail for scoring." for idx in range(20)]
        )
        ingress = build_discovery_ingress_envelope(
            project_key=None,
            item={
                "uri": "https://example.com/clean",
                "doc_type": "market",
                "title": "  Discovery item  ",
                "content": noisy_content,
                "summary": "Privacy Policy\nMeaningful summary",
                "text_hash": "hash-clean",
                "source_name": "example.com",
                "source_kind": "web",
                "source_base_url": "example.com",
                "extracted_data_base": {},
            },
        )
        collection_payload = ingress["collection_payload"]
        collection_payload["terminal_context"] = {
            "platform": "discovery",
            "ingestion_entrypoint": "discovery.store",
            "source_mode": "discovery",
            "quality_score": 0.0,
            "degradation_flags": [],
            "http_status": None,
            "capability_profile": {},
            "light_filter": {},
        }
        collection_payload["extraction_plan"] = {
            "enabled": True,
            "include_market": True,
            "include_policy": False,
            "include_sentiment": False,
            "include_company": False,
            "include_product": False,
            "include_operation": False,
        }

        with patch(
            "app.services.ingest.postprocess_frontdoor.run_unified_structured_extraction",
            return_value={
                "status": "ok",
                "reason": None,
                "error": None,
                "domains": {"market": {"state": "CA"}},
                "summary": {},
                "extractor_version": "unified.structured.v1",
                "model_profile": {},
                "prompt_profile": {},
                "structured_output_mode": "unknown",
            },
        ) as extraction_mock, patch(
            "app.services.ingest.postprocess_frontdoor.persist_terminal_document",
            return_value={"doc_id": 63, "inserted": 1, "skipped": 0, "reason": "inserted", "doc_type": "market"},
        ):
            result = run_postprocess_frontdoor(ingress_envelope=ingress, run_writer=True)

        self.assertEqual(result["data"]["admission"], "accept")
        self.assertEqual(result["data"]["content_extraction"]["page_family"], "article")
        self.assertTrue(
            bool(result["data"]["cleaning"]["content_changed"])
            or bool(result["data"]["content_extraction"]["prefix_trimmed"])
        )
        self.assertTrue(bool(result["data"]["cleaning"]["summary_changed"]))
        self.assertEqual(extraction_mock.call_args.kwargs["title"], "Discovery item")
        self.assertNotIn("Skip to content", extraction_mock.call_args.kwargs["content"])
        self.assertNotIn("Accessibility Help", extraction_mock.call_args.kwargs["content"])

    def test_frontdoor_returns_video_shell_for_cleanup(self) -> None:
        ingress = build_discovery_ingress_envelope(
            project_key=None,
            item={
                "uri": "https://www.youtube.com/watch?v=abc123",
                "doc_type": "market",
                "title": "Video shell",
                "content": "if(a)return a;c.prototype.toString=function(){return this.g}; Symbol.iterator window.document",
                "summary": "",
                "text_hash": "hash-video",
                "source_name": "youtube",
                "source_kind": "web",
                "source_base_url": "youtube.com",
                "extracted_data_base": {},
            },
        )
        collection_payload = ingress["collection_payload"]
        collection_payload["terminal_context"] = {
            "platform": "discovery",
            "ingestion_entrypoint": "discovery.store",
            "source_mode": "discovery",
            "quality_score": 0.0,
            "degradation_flags": [],
            "http_status": None,
            "capability_profile": {},
            "light_filter": {},
        }

        with patch("app.services.ingest.postprocess_frontdoor.persist_terminal_document") as writer_mock, patch(
            "app.services.ingest.postprocess_frontdoor.run_unified_structured_extraction"
        ) as extraction_mock:
            result = run_postprocess_frontdoor(ingress_envelope=ingress, run_writer=True)

        self.assertEqual(result["data"]["admission"], "return_for_cleanup")
        self.assertEqual(result["data"]["content_extraction"]["page_family"], "video")
        self.assertIn("specialized_extractor_required", result["data"]["cleanup_actions"])
        self.assertIsNotNone(result["data"]["rollback_token"])
        extraction_mock.assert_not_called()
        writer_mock.assert_not_called()

    def test_frontdoor_can_recover_after_cleanup_execution(self) -> None:
        ingress = build_discovery_ingress_envelope(
            project_key=None,
            item={
                "uri": "https://example.com/article-shell",
                "doc_type": "market",
                "title": "Article shell",
                "content": "Home News Subscribe Newsletter Suggested for you Join the conversation",
                "summary": "",
                "text_hash": "hash-support",
                "source_name": "example",
                "source_kind": "web",
                "source_base_url": "example.com",
                "extracted_data_base": {},
            },
        )
        collection_payload = ingress["collection_payload"]
        collection_payload["terminal_context"] = {
            "platform": "discovery",
            "ingestion_entrypoint": "discovery.store",
            "source_mode": "discovery",
            "quality_score": 0.0,
            "degradation_flags": [],
            "http_status": None,
            "capability_profile": {},
            "light_filter": {},
        }
        collection_payload["extraction_plan"] = {
            "enabled": True,
            "include_market": True,
            "include_policy": False,
            "include_sentiment": False,
            "include_company": False,
            "include_product": False,
            "include_operation": False,
        }

        first_quality = {
            "admission": "return_for_cleanup",
            "reason_code": "content_js_template_shell",
            "retryable": False,
            "retry_observability": {"retryable": False},
            "cleanup_actions": ["strip_boilerplate", "refetch_suggested"],
            "cleaning": {},
            "quality_assessment": {
                "quality_score": 12.0,
                "meaningful": False,
                "provenance_ok": True,
                "content_ok": False,
                "readerable": False,
                "page_family": "landing",
            },
            "quality_gates": {"content_profile": {"page_family": "landing"}},
            "degradation_flags": ["content_js_template_shell"],
            "light_filter": {},
            "gate_plus": {},
        }
        second_quality = {
            "admission": "accept",
            "reason_code": "ok",
            "retryable": False,
            "retry_observability": {"retryable": False},
            "cleanup_actions": [],
            "cleaning": {"content_changed": True},
            "quality_assessment": {
                "quality_score": 88.0,
                "meaningful": True,
                "provenance_ok": True,
                "content_ok": True,
                "readerable": True,
                "page_family": "article",
            },
            "quality_gates": {"content_profile": {"page_family": "article", "readerable": True}},
            "degradation_flags": [],
            "light_filter": {},
            "gate_plus": {},
        }

        with patch(
            "app.services.ingest.postprocess_frontdoor._evaluate_quality_frontdoor",
            side_effect=[first_quality, second_quality],
        ), patch(
            "app.services.ingest.postprocess_frontdoor.execute_frontdoor_cleanup",
            return_value={
                "executed": True,
                "recovered": True,
                "document_candidate": {
                    **collection_payload["document_candidate"],
                    "content": (
                        "Published January 2, 2026. "
                        "The company expanded manufacturing capacity and improved retention across enterprise accounts. "
                        "Management said demand rose in the second half of the year, channel partners increased orders, "
                        "and the market outlook improved as adoption widened across logistics and field operations."
                    ),
                },
                "terminal_context": {
                    **collection_payload["terminal_context"],
                    "content_extraction": {
                        "page_family": "article",
                        "readerable": True,
                        "shell_heavy": False,
                        "js_heavy": False,
                        "main_text_ratio": 0.72,
                        "main_text_chars": 312,
                        "raw_text_chars": 420,
                        "shell_marker_hits": 0,
                        "js_template_hits": 0,
                        "duplicate_line_ratio": 0.0,
                    },
                    "frontdoor_cleaning": {"content_changed": True},
                },
            },
        ), patch(
            "app.services.ingest.postprocess_frontdoor.run_unified_structured_extraction",
            return_value={
                "status": "ok",
                "reason": None,
                "error": None,
                "domains": {"market": {"state": "CA"}},
                "summary": {},
                "extractor_version": "unified.structured.v1",
                "model_profile": {},
                "prompt_profile": {},
                "structured_output_mode": "unknown",
            },
        ) as extraction_mock, patch(
            "app.services.ingest.postprocess_frontdoor.persist_terminal_document",
            return_value={"doc_id": 70, "inserted": 1, "skipped": 0, "reason": "inserted", "doc_type": "market"},
        ) as writer_mock:
            result = run_postprocess_frontdoor(ingress_envelope=ingress, run_writer=True)

        self.assertEqual(result["data"]["admission"], "accept")
        self.assertTrue(result["data"]["cleanup_execution"]["executed"])
        self.assertEqual(result["data"]["quality_assessment"]["page_family"], "article")
        extraction_mock.assert_called_once()
        writer_mock.assert_called_once()

    def test_raw_import_ingress_can_be_normalized_and_written(self) -> None:
        ingress = build_raw_import_ingress_envelope(
            project_key="demo_proj",
            payload={"source_name": "raw_import"},
            item={
                "uri": "https://example.com/raw",
                "state": "CA",
                "doc_type": "raw_note",
                "title": "Imported note",
                "publish_date": None,
                "content": "imported content " * 10,
                "summary": "summary",
                "text_hash": "hash-1",
                "source_name": "raw_import",
                "source_kind": "manual",
                "source_base_url": None,
                "extracted_data_base": {"policy": {"state": "CA"}},
            },
        )
        collection_payload = ingress["collection_payload"]
        collection_payload["document_candidate"] = {
            "source_name": "raw_import",
            "source_kind": "manual",
            "source_base_url": None,
            "state": "CA",
            "doc_type": "raw_note",
            "title": "Imported note",
            "publish_date": None,
            "content": "imported content " * 10,
            "summary": "summary",
            "text_hash": "hash-1",
            "uri": "https://example.com/raw",
            "status": None,
            "extracted_data_base": {"policy": {"state": "CA"}},
        }
        collection_payload["terminal_context"] = {
            "platform": "raw_import",
            "ingestion_entrypoint": "ingest.raw_import",
            "source_mode": "raw_import",
            "quality_score": 0.0,
            "degradation_flags": [],
            "http_status": None,
            "capability_profile": {},
            "light_filter": {},
        }
        collection_payload["extraction_outcome"] = {"status": "ok", "reason": None, "error": None, "domains": {"policy": {"state": "CA"}}}

        with patch("app.services.ingest.postprocess_frontdoor.persist_terminal_document", return_value={"doc_id": 52, "inserted": 1, "skipped": 0, "reason": "inserted", "doc_type": "raw_note"}):
            result = run_postprocess_frontdoor(ingress_envelope=ingress, run_writer=True)

        self.assertEqual(result["data"]["admission"], "accept")
        self.assertEqual(result["data"]["normalized_payload"]["extracted_data"]["platform"], "raw_import")
        self.assertEqual(result["data"]["writer_result"]["doc_id"], 52)

    def test_discovery_ingress_can_be_normalized_and_written(self) -> None:
        ingress = build_discovery_ingress_envelope(
            project_key=None,
            item={
                "uri": "https://example.com/discovery",
                "state": None,
                "doc_type": "market",
                "title": "Discovery item",
                "publish_date": None,
                "content": "discovery content " * 10,
                "summary": "summary",
                "text_hash": "hash-2",
                "source_name": "example.com",
                "source_kind": "web",
                "source_base_url": "example.com",
                "extracted_data_base": {"market": {"state": "CA"}},
            },
        )
        collection_payload = ingress["collection_payload"]
        collection_payload["document_candidate"] = {
            "source_name": "example.com",
            "source_kind": "web",
            "source_base_url": "example.com",
            "state": None,
            "doc_type": "market",
            "title": "Discovery item",
            "publish_date": None,
            "content": "discovery content " * 10,
            "summary": "summary",
            "text_hash": "hash-2",
            "uri": "https://example.com/discovery",
            "status": None,
            "extracted_data_base": {"market": {"state": "CA"}},
        }
        collection_payload["terminal_context"] = {
            "platform": "discovery",
            "ingestion_entrypoint": "discovery.store",
            "source_mode": "discovery",
            "quality_score": 0.0,
            "degradation_flags": [],
            "http_status": None,
            "capability_profile": {},
            "light_filter": {},
        }
        collection_payload["extraction_outcome"] = {"status": "ok", "reason": None, "error": None, "domains": {"market": {"state": "CA"}}}

        with patch("app.services.ingest.postprocess_frontdoor.persist_terminal_document", return_value={"doc_id": 62, "inserted": 1, "skipped": 0, "reason": "inserted", "doc_type": "market"}):
            result = run_postprocess_frontdoor(ingress_envelope=ingress, run_writer=True)

        self.assertEqual(result["data"]["admission"], "accept")
        self.assertEqual(result["data"]["normalized_payload"]["extracted_data"]["platform"], "discovery")
        self.assertEqual(result["data"]["writer_result"]["doc_id"], 62)


if __name__ == "__main__":
    unittest.main()
