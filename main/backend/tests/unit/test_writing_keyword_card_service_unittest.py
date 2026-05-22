from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.contracts.schemas.writing import KeywordCardItem, KeywordCardRequest, WritingContextEnvelope
    from app.services.document_views.writing_card_view import build_keyword_card_from_typed_knowledge_handoff
    from app.services.typed_knowledge import contracts as typed_knowledge_contracts
    from app.services.writing.keyword_card_service import _CARD_CACHE, _SELECTION_CACHE, aggregate_cards

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


if __name__ == "__main__":
    unittest.main()
