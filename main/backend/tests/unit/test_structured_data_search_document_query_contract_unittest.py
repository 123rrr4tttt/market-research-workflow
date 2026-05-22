from __future__ import annotations

from contextlib import contextmanager
import unittest
from unittest.mock import patch

import pytest

from app.services.agent_runtime import structured_data_search as search_module
from app.services.agent_runtime.structured_data_search import query_project_structured_data
from app.services.document_queries import (
    DOCUMENT_QUERY_CONTRACT_VERSION,
    build_structured_data_search_document_query_envelope,
    validate_document_query_result_envelope,
)

pytestmark = pytest.mark.unit


@contextmanager
def _project_context(_project_key: str):
    yield


class _SessionContext:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class StructuredDataSearchDocumentQueryContractUnitTestCase(unittest.TestCase):
    def test_helper_builds_document_query_projection_for_structured_search(self) -> None:
        envelope = build_structured_data_search_document_query_envelope(
            project_key=" demo_proj ",
            query="  Robotics  ",
            datasets_requested=("documents", "market_stats", "documents"),
            limit=999,
            query_mode="search",
            total_matches=4,
            total_stored_rows=11,
            items=[
                {
                    "dataset": "documents",
                    "record_id": "doc-7",
                    "title": "Robot local note",
                    "summary": "stored robot evidence",
                    "source_uri": "https://example.org/robot",
                    "fields": {"source_name": "fixture"},
                }
            ],
        )

        validate_document_query_result_envelope(envelope)
        data = envelope["data"]
        query = data["query"]

        self.assertEqual(data["contract_version"], DOCUMENT_QUERY_CONTRACT_VERSION)
        self.assertEqual(query["consumer"], "project.structured_data.search")
        self.assertEqual(query["project_key"], "demo_proj")
        self.assertEqual(query["sources"], ["project.structured_data"])
        self.assertEqual(query["filters"], [{"field": "dataset", "op": "in", "value": ["documents", "market_stats"]}])
        self.assertEqual(query["limit"], 100)
        self.assertEqual(data["pagination"]["total"], 4)
        self.assertEqual(envelope["meta"]["total_stored_rows"], 11)
        self.assertEqual(data["results"][0]["source_type"], "structured_record")
        self.assertEqual(data["results"][0]["document_id"], "doc-7")
        self.assertEqual(data["results"][0]["backend"], "documents")
        self.assertEqual(data["results"][0]["raw"]["record_id"], "doc-7")

    def test_project_structured_data_search_returns_document_query_projection(self) -> None:
        def documents_handler(_session, query: str, limit: int):
            self.assertEqual(query, "robot")
            self.assertEqual(limit, 5)
            return (
                [
                    {
                        "dataset": "documents",
                        "record_id": "doc-1",
                        "title": "Robot market note",
                        "summary": "stored robot row",
                        "source_uri": "https://example.org/robot-market",
                    }
                ],
                None,
            )

        with patch.object(search_module, "bind_project", _project_context):
            with patch.object(search_module, "SessionLocal", _SessionContext):
                with patch.dict(search_module._DATASET_HANDLERS, {"documents": documents_handler}):
                    result = query_project_structured_data(
                        project_key="demo_proj",
                        query="robot",
                        limit=5,
                        datasets=["documents"],
                    )

        self.assertEqual(result["contract_version"], "project.structured_data.search.v1")
        self.assertEqual(result["document_query_contract_version"], DOCUMENT_QUERY_CONTRACT_VERSION)
        self.assertEqual(result["document_query"]["consumer"], "project.structured_data.search")
        self.assertEqual(result["document_query"]["project_key"], "demo_proj")
        self.assertEqual(result["document_query"]["filters"], [{"field": "dataset", "op": "in", "value": ["documents"]}])
        self.assertEqual(result["document_query_results"][0]["title"], "Robot market note")
        self.assertEqual(result["document_query_results"][0]["source_type"], "structured_record")
        self.assertEqual(result["document_query_pagination"]["result_count"], 1)
        self.assertEqual(result["document_query_meta"]["source"], "agent_runtime.structured_data_search")
        self.assertEqual(result["model_evidence_manifest"][0]["read_tool"], "project.structured_data.item.read")


if __name__ == "__main__":
    unittest.main()
