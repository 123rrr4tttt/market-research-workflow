from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.contracts.schemas.writing import (
        KeywordCardDetailRequest,
        KeywordCardItem,
        KeywordCardPreviewRequest,
        KeywordCardRequest,
        WritingContextEnvelope,
    )
    from app.services.document_views.writing_card_view import build_keyword_card_from_typed_knowledge_handoff
    from app.services.typed_knowledge import contracts as typed_knowledge_contracts
    from app.services.typed_knowledge import persistence_boundary as typed_knowledge_boundary
    from app.services.writing.keyword_card_service import (
        _CARD_CACHE,
        _SELECTION_CACHE,
        aggregate_cards,
        get_card_detail,
        get_card_preview,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class WritingKeywordCardServiceUnitTestCase(unittest.TestCase):
    def setUp(self):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"writing keyword card service tests require backend dependencies: {_IMPORT_ERROR}")
        _CARD_CACHE.clear()
        _SELECTION_CACHE.clear()

    def test_graph_context_is_consumed_as_optional_adapter(self):
        payload = KeywordCardRequest(
            project_key="demo_proj",
            query="robotics",
            sources=["graph"],
            context=WritingContextEnvelope(
                graph_context={
                    "contract_version": "graph_handoff.v1",
                    "selected_nodes": [
                        {
                            "node_id": "n-1",
                            "node_type": "entity",
                            "title": "Humanoid Robotics",
                            "summary": "Graph-derived context snippet.",
                            "source_uri": "https://example.com/robotics",
                        }
                    ],
                },
                accepted_citation_context={"citations": [{"citation_id": "c-1"}]},
            ),
        )
        with (
            patch("app.services.writing.keyword_card_service._cards_from_hybrid", return_value=[]),
            patch("app.services.writing.keyword_card_service._cards_from_sources", return_value=[]),
            patch("app.services.writing.keyword_card_service._cards_from_source_library", return_value=[]),
        ):
            response = aggregate_cards(payload)

        self.assertEqual(len(response.cards), 1)
        self.assertEqual(response.cards[0].source_type, "graph")
        self.assertTrue(response.context_boundary["graph_context_attached"])
        self.assertEqual(response.context_boundary["accepted_citation_context_count"], 1)
        self.assertTrue(response.dependency_gate["passed"])

    def test_sources_filter_is_enforced(self):
        payload = KeywordCardRequest(
            project_key="demo_proj",
            query="robotics",
            sources=["graph"],
            context=WritingContextEnvelope(
                graph_context={
                    "contract_version": "graph_handoff.v1",
                    "selected_nodes": [
                        {"node_id": "n-1", "node_type": "entity", "title": "Humanoid Robotics", "summary": "graph"}
                    ],
                },
            ),
        )
        graph_card = [
            (
                KeywordCardItem(card_id="g1", source_type="graph", title="g", snippet="g", score=0.7),
                {},
            )
        ]
        resource_card = [
            (
                KeywordCardItem(card_id="r1", source_type="resource", title="r", snippet="r", score=0.6),
                {},
            )
        ]
        with (
            patch("app.services.writing.keyword_card_service._cards_from_graph_context", return_value=graph_card),
            patch("app.services.writing.keyword_card_service._cards_from_hybrid", return_value=[]),
            patch("app.services.writing.keyword_card_service._cards_from_sources", return_value=resource_card),
            patch("app.services.writing.keyword_card_service._cards_from_source_library", return_value=[]),
        ):
            response = aggregate_cards(payload)

        self.assertEqual([item.source_type for item in response.cards], ["graph"])

    def test_source_library_query_layer_is_used_for_resource_cards(self):
        payload = KeywordCardRequest(
            project_key="demo_proj",
            query="robotics",
            sources=["resource"],
        )
        with (
            patch("app.services.writing.keyword_card_service.query_hybrid_document_rows", return_value=[]),
            patch("app.services.writing.keyword_card_service.query_report_source_rows", return_value=[]),
            patch(
                "app.services.writing.keyword_card_service.query_source_library_material_rows",
                return_value=[
                    {"item_key": "robotics_feed", "name": "Robotics Feed", "description": "robotics source", "channel_key": "market"}
                ],
            ),
        ):
            response = aggregate_cards(payload)

        self.assertEqual(len(response.cards), 1)
        self.assertEqual(response.cards[0].source_type, "resource")
        self.assertEqual(response.cards[0].extra["item_key"], "robotics_feed")

    def test_typed_knowledge_handoff_builds_stable_writing_card_selection_contract(self):
        item = typed_knowledge_contracts.KnowledgeItem(
            key="ki:robotics-policy",
            project_key="demo_proj",
            canonical_statement="Humanoid robotics investment is shifting toward industrial pilots.",
            primary_type_node_key="type:market_signal",
            evidence_refs=("doc:robotics:42",),
            topic_cluster_keys=("topic:robotics",),
            booklet_keys=("booklet:q2-review",),
            review_state=typed_knowledge_contracts.REVIEW_STATE_HUMAN_CONFIRMED,
            quality_grade=typed_knowledge_contracts.QUALITY_GRADE_GOLD,
            locale="en",
        )
        draft = typed_knowledge_contracts.build_downstream_contract_draft(item)
        handoff = typed_knowledge_contracts.build_writing_knowledge_handoff(
            draft,
            selection_hash="selection:robotics",
            selection_text="robotics investment",
        )

        card = build_keyword_card_from_typed_knowledge_handoff(handoff, normalized_query="robotics investment")

        self.assertEqual(handoff.contract_version, "typed_knowledge.writing_handoff.v1")
        self.assertIn("selection_hash", typed_knowledge_contracts.WRITING_KNOWLEDGE_HANDOFF_FIELDS)
        self.assertEqual(handoff.selection_hash, "selection:robotics")
        self.assertEqual(card.source_type, "resource")
        self.assertEqual(card.publisher, "typed_knowledge")
        self.assertEqual(card.extra["handoff_source"], "typed_knowledge")
        self.assertEqual(card.extra["typed_knowledge_contract_version"], handoff.contract_version)
        self.assertEqual(card.extra["knowledge_item_key"], "ki:robotics-policy")
        self.assertEqual(card.extra["primary_type_node_key"], "type:market_signal")
        self.assertEqual(card.extra["topic_cluster_keys"], ["topic:robotics"])
        self.assertEqual(card.extra["booklet_keys"], ["booklet:q2-review"])
        self.assertEqual(card.extra["visibility_scope"], typed_knowledge_contracts.VISIBILITY_SCOPE_DOWNSTREAM_READY)
        self.assertEqual(card.extra["selection_hash"], "selection:robotics")
        self.assertEqual(card.extra["selection_text"], "robotics investment")
        self.assertEqual(card.extra["facets"]["consumer_boundary"]["card_source_type"], "resource")

    def test_typed_knowledge_context_envelope_is_consumed_as_resource_card(self):
        item = typed_knowledge_contracts.KnowledgeItem(
            key="ki:robotics-policy",
            project_key="demo_proj",
            canonical_statement="Humanoid robotics investment is shifting toward industrial pilots.",
            primary_type_node_key="type:market_signal",
            evidence_refs=("doc:robotics:42",),
            topic_cluster_keys=("topic:robotics",),
            booklet_keys=("booklet:q2-review",),
            review_state=typed_knowledge_contracts.REVIEW_STATE_HUMAN_CONFIRMED,
            quality_grade=typed_knowledge_contracts.QUALITY_GRADE_GOLD,
            locale="en",
        )
        handoff = typed_knowledge_contracts.build_writing_knowledge_handoff(
            typed_knowledge_contracts.build_downstream_contract_draft(item),
            selection_hash="selection:robotics",
            selection_text="robotics investment",
        )
        envelope = typed_knowledge_contracts.build_writing_knowledge_context_envelope((handoff,))
        payload = KeywordCardRequest(
            project_key="demo_proj",
            query="robotics investment",
            sources=["resource"],
            context=WritingContextEnvelope(typed_knowledge_context=envelope),
        )

        with (
            patch("app.services.writing.keyword_card_service._cards_from_sources", return_value=[]),
            patch("app.services.writing.keyword_card_service._cards_from_source_library", return_value=[]),
        ):
            response = aggregate_cards(payload)

        self.assertEqual(len(response.cards), 1)
        self.assertEqual(response.cards[0].source_type, "resource")
        self.assertEqual(response.cards[0].publisher, "typed_knowledge")
        self.assertEqual(response.cards[0].extra["handoff_payload"]["contract_version"], handoff.contract_version)
        self.assertTrue(response.context_boundary["typed_knowledge_context_attached"])
        self.assertEqual(response.context_boundary["typed_knowledge_context_count"], 1)
        self.assertFalse(response.context_boundary["graph_context_attached"])
        self.assertTrue(response.dependency_gate["typed_knowledge"]["attached"])
        self.assertEqual(response.dependency_gate["typed_knowledge"]["card_source_type"], "resource")

    def test_typed_knowledge_card_preview_and_detail_readback_after_consumer_fetch(self):
        item = typed_knowledge_contracts.KnowledgeItem(
            key="ki:robotics-policy",
            project_key="demo_proj",
            canonical_statement="Humanoid robotics investment is shifting toward industrial pilots.",
            primary_type_node_key="type:market_signal",
            evidence_refs=("doc:robotics:42",),
            topic_cluster_keys=("topic:robotics",),
            booklet_keys=("booklet:q2-review",),
            review_state=typed_knowledge_contracts.REVIEW_STATE_HUMAN_CONFIRMED,
            quality_grade=typed_knowledge_contracts.QUALITY_GRADE_GOLD,
            locale="en",
        )
        handoff = typed_knowledge_contracts.build_writing_knowledge_handoff(
            typed_knowledge_contracts.build_downstream_contract_draft(item),
            selection_hash="selection:robotics",
            selection_text="robotics investment",
        )
        envelope = typed_knowledge_contracts.build_writing_knowledge_context_envelope((handoff,))
        payload = KeywordCardRequest(
            project_key="demo_proj",
            query="robotics investment",
            sources=["resource"],
            context=WritingContextEnvelope(typed_knowledge_context=envelope),
        )

        with (
            patch("app.services.writing.keyword_card_service._cards_from_sources", return_value=[]),
            patch("app.services.writing.keyword_card_service._cards_from_source_library", return_value=[]),
        ):
            response = aggregate_cards(payload)

        card_id = response.cards[0].card_id
        preview = get_card_preview(
            KeywordCardPreviewRequest(project_key="demo_proj", card_id=card_id, query="robotics investment")
        )
        detail = get_card_detail(
            KeywordCardDetailRequest(
                project_key="demo_proj",
                request_id="wave16-worker5-readback",
                card_id=card_id,
                include_provenance=True,
                max_provenance_items=12,
            )
        )

        self.assertEqual(preview.publisher, "typed_knowledge")
        self.assertEqual(preview.source_type, "resource")
        self.assertEqual(detail.publisher, "typed_knowledge")
        self.assertEqual(detail.source_type, "resource")
        self.assertEqual(detail.normalized_query, "robotics investment")
        self.assertEqual(detail.provenance["raw_keys"], ["typed_knowledge_context"])
        self.assertEqual(detail.selection_matches["query"], "robotics investment")
        self.assertEqual(detail.selection_matches["request_id"], "wave16-worker5-readback")

    def test_wave19_persisted_card_request_from_typed_api_boundary_round_trips_response(self):
        readback = typed_knowledge_boundary.build_persisted_card_request_response_readback(project_key="demo_proj")
        expected_response = readback["keyword_card_response"]["body"]
        payload = KeywordCardRequest.model_validate(readback["keyword_card_request"]["body"])

        with (
            patch("app.services.writing.keyword_card_service._cards_from_hybrid", return_value=[]),
            patch("app.services.writing.keyword_card_service._cards_from_sources", return_value=[]),
            patch("app.services.writing.keyword_card_service._cards_from_source_library", return_value=[]),
        ):
            response = aggregate_cards(payload)

        self.assertEqual(len(response.cards), 1)
        self.assertEqual(response.cards[0].card_id, expected_response["cards"][0]["card_id"])
        self.assertEqual(response.cards[0].publisher, "typed_knowledge")
        self.assertEqual(response.cards[0].source_type, "resource")
        self.assertEqual(response.cards[0].extra["knowledge_item_key"], "ki:robotics-policy")
        self.assertEqual(response.cards[0].extra["selection_hash"], "selection:robotics")
        self.assertTrue(response.context_boundary["typed_knowledge_context_attached"])
        self.assertEqual(response.context_boundary["typed_knowledge_context_count"], 1)
        self.assertTrue(response.dependency_gate["typed_knowledge"]["attached"])
        self.assertEqual(response.source_count["resource"], 1)

        preview = get_card_preview(
            KeywordCardPreviewRequest(
                project_key="demo_proj",
                card_id=response.cards[0].card_id,
                query=payload.query,
            )
        )
        detail = get_card_detail(
            KeywordCardDetailRequest(
                project_key="demo_proj",
                request_id="wave19-worker10-readback",
                card_id=response.cards[0].card_id,
                include_provenance=True,
            )
        )

        self.assertEqual(preview.publisher, "typed_knowledge")
        self.assertEqual(detail.publisher, "typed_knowledge")
        self.assertEqual(detail.provenance["raw_keys"], ["typed_knowledge_context"])
        self.assertEqual(detail.selection_matches["request_id"], "wave19-worker10-readback")
        self.assertFalse(readback["meta"]["readiness"]["live_db_persistence"])
        self.assertFalse(readback["meta"]["readiness"]["live_api_closure"])
        self.assertFalse(readback["meta"]["readiness"]["live_ui_closure"])


if __name__ == "__main__":
    unittest.main()
