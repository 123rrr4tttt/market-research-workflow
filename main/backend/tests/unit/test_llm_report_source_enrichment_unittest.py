from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import llm_report_source_enrichment as enrichment

pytestmark = pytest.mark.unit


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _stmt):
        return _FakeExecuteResult(self._rows)


class _FakeSessionLocal:
    def __init__(self, rows):
        self._rows = rows

    def __call__(self):
        return self

    def __enter__(self):
        return _FakeSession(self._rows)

    def __exit__(self, _exc_type, _exc, _tb):
        return False


class LlmReportSourceEnrichmentUnitTest(unittest.TestCase):
    def test_manual_sources_keep_backward_compatibility(self):
        manual = [{"id": "S1", "title": "Manual", "url": "https://example.com"}]
        with patch.object(enrichment, "_collect_from_rag_documents") as mocked_rag:
            resolved = enrichment.resolve_report_sources("topic", manual)
            self.assertEqual(resolved, manual)
            mocked_rag.assert_not_called()

    def test_topic_only_prefers_rag_documents_with_graph_evidence(self):
        doc = SimpleNamespace(
            id=11,
            title="RAG Doc",
            uri="https://example.com/rag-doc",
            doc_type="policy",
            publish_date=None,
            summary="summary text",
            extracted_data={
                "entities_relations": {
                    "relations": [{"evidence": "graph relation evidence"}],
                }
            },
        )
        with (
            patch.object(enrichment, "hybrid_search", return_value=[{"document_id": 11}]),
            patch.object(enrichment, "SessionLocal", _FakeSessionLocal([doc])),
            patch.object(enrichment, "_collect_from_graph_nodes", return_value=[]),
            patch.object(enrichment, "_collect_from_web", return_value=[]),
        ):
            resolved = enrichment.resolve_report_sources("lottery growth", [])
            self.assertEqual(len(resolved), 1)
            self.assertEqual(resolved[0]["id"], "RAG1")
            self.assertIn("graph relation evidence", resolved[0]["evidence"])

    def test_topic_only_falls_back_to_graph_then_web(self):
        graph_row = SimpleNamespace(
            node_type="MarketData",
            canonical_id="m1",
            display_name="lottery market",
            properties={
                "source_uri": "https://example.com/graph",
                "summary": "graph summary",
            },
        )
        with (
            patch.object(enrichment, "hybrid_search", return_value=[]),
            patch.object(enrichment, "SessionLocal", _FakeSessionLocal([graph_row])),
            patch.object(enrichment, "_collect_from_web", return_value=[]),
        ):
            resolved = enrichment.resolve_report_sources("lottery market", [], target_count=2)
            self.assertEqual(len(resolved), 1)
            self.assertTrue(resolved[0]["id"].startswith("GRAPH"))
            self.assertEqual(resolved[0]["url"], "https://example.com/graph")


if __name__ == "__main__":
    unittest.main()
