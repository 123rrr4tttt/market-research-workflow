from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import llm_report_source_enrichment as enrichment
from app.services.search.hybrid import SearchInvocationObservation
from mrw_functorial_kit.core.service_failure_semantics import search_failures

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
            self.assertEqual(resolved.sources, manual)
            self.assertEqual(resolved.kind, "caller_supplied_only")
            mocked_rag.assert_not_called()

    def test_topic_only_prefers_rag_documents_with_graph_evidence(self):
        doc = SimpleNamespace(
            id=11,
            title="RAG Doc",
            uri="https://example.com/rag-doc",
            material_type="policy",
            publish_date=None,
            summary="summary text",
            extracted_data={
                "entities_relations": {
                    "relations": [{"evidence": "graph relation evidence"}],
                }
            },
        )
        with (
            patch.object(enrichment, "observe_hybrid_search", return_value=SearchInvocationObservation([{"material_id": 11}], ("opensearch",), ())),
            patch.object(enrichment, "SessionLocal", _FakeSessionLocal([doc])),
            patch.object(enrichment, "_collect_from_graph_nodes", return_value=[]),
            patch.object(enrichment, "_collect_from_web", return_value=[]),
        ):
            resolved = enrichment.resolve_report_sources("renewable energy growth", [])
            self.assertEqual(len(resolved.sources), 1)
            self.assertEqual(resolved.sources[0]["id"], "RAG1")
            self.assertIn("graph relation evidence", resolved.sources[0]["evidence"])

    def test_topic_only_falls_back_to_graph_then_web(self):
        graph_row = SimpleNamespace(
            node_type="MarketData",
            canonical_id="m1",
            display_name="renewable energy market",
            properties={
                "source_uri": "https://example.com/graph",
                "summary": "graph summary",
            },
        )
        with (
            patch.object(enrichment, "observe_hybrid_search", return_value=SearchInvocationObservation([], ("opensearch",), ())),
            patch.object(enrichment, "SessionLocal", _FakeSessionLocal([graph_row])),
            patch.object(enrichment, "_collect_from_web", return_value=[]),
        ):
            resolved = enrichment.resolve_report_sources("renewable energy market", [], target_count=2)
            self.assertEqual(len(resolved.sources), 1)
            self.assertTrue(resolved.sources[0]["id"].startswith("GRAPH"))
            self.assertEqual(resolved.sources[0]["url"], "https://example.com/graph")

    def test_successful_empty_is_not_a_source_failure(self):
        def empty_web(**kwargs):
            kwargs["observation_sink"].append({"status": "completed", "provider": "ddg"})
            return []

        with (
            patch.object(enrichment, "observe_hybrid_search", return_value=SearchInvocationObservation([], ("opensearch",), ())),
            patch.object(enrichment, "SessionLocal", _FakeSessionLocal([])),
            patch.object(enrichment, "search_sources", side_effect=empty_web),
        ):
            resolved = enrichment.resolve_report_sources("topic", None)
        self.assertEqual(resolved.kind, "auto_empty")
        self.assertEqual(resolved.sources, [])
        self.assertEqual(resolved.failures, ())

    def test_empty_after_dependency_failures_is_not_a_no_match(self):
        def unavailable_web(**kwargs):
            kwargs["observation_sink"].append({
                "status": "failed", "provider": "ddg", "failure_kind": "timeout", "error_type": "TimeoutError",
                "error_message": "private provider details",
            })
            return []

        failure = search_failures.fail("backend_unavailable", "private search details", {"provider": "opensearch"})
        with (
            patch.object(enrichment, "observe_hybrid_search", return_value=SearchInvocationObservation([], (), (failure,))),
            patch.object(enrichment, "SessionLocal", side_effect=RuntimeError("private database details")),
            patch.object(enrichment, "search_sources", side_effect=unavailable_web),
        ):
            resolved = enrichment.resolve_report_sources("topic", None)
        self.assertEqual(resolved.kind, "auto_failed")
        self.assertEqual(resolved.sources, [])
        self.assertEqual([failure.owner for failure in resolved.failures], [
            "report_sources.rag_search", "report_sources.graph", "report_sources.web",
        ])
        self.assertEqual(resolved.failures[-1].code, "timeout")
        self.assertNotIn("private", str([failure.to_payload() for failure in resolved.failures]))

    def test_dependency_failure_preserves_later_web_source(self):
        with (
            patch.object(enrichment, "observe_hybrid_search", return_value=SearchInvocationObservation(
                [{"material_id": 11}], ("opensearch",), (),
            )),
            patch.object(enrichment, "SessionLocal", side_effect=[RuntimeError("rag load failed"), _FakeSessionLocal([])]),
            patch.object(enrichment, "search_sources", return_value=[{"link": "https://example.com/web"}]),
        ):
            resolved = enrichment.resolve_report_sources("topic", None)
        self.assertEqual(resolved.kind, "auto_partial")
        self.assertEqual([source["url"] for source in resolved.sources], ["https://example.com/web"])
        self.assertEqual([failure.owner for failure in resolved.failures], ["report_sources.rag_load"])


if __name__ == "__main__":
    unittest.main()
