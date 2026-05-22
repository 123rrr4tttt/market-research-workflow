from __future__ import annotations

import unittest

import pytest

from app.services.document_queries import (
    DOCUMENT_QUERY_CONTRACT_VERSION,
    build_search_endpoint_document_query_envelope,
    validate_document_query_result_envelope,
)

pytestmark = pytest.mark.unit


class SearchEndpointDocumentQueryContractUnitTestCase(unittest.TestCase):
    def test_search_endpoint_envelope_exposes_document_query_contract(self) -> None:
        envelope = build_search_endpoint_document_query_envelope(
            query="  Robotics   Policy  ",
            state=" CA ",
            modality="text",
            rank="hybrid",
            top_k=999,
            project_key=" demo_proj ",
            used_backends=("opensearch_lexical", "qdrant_vector"),
            results=[
                {
                    "id": "doc-7",
                    "document_id": 7,
                    "title": "Robot market note",
                    "snippet": "robotics market",
                    "score": 0.77,
                    "backend": "opensearch_lexical",
                }
            ],
        )

        validate_document_query_result_envelope(envelope)
        data = envelope["data"]
        query = data["query"]

        self.assertEqual(data["contract_version"], DOCUMENT_QUERY_CONTRACT_VERSION)
        self.assertEqual(query["consumer"], "api.search")
        self.assertEqual(query["project_key"], "demo_proj")
        self.assertEqual(query["query"], "Robotics Policy")
        self.assertEqual(query["filters"], [{"field": "state", "op": "eq", "value": "CA"}])
        self.assertEqual(query["limit"], 100)
        self.assertEqual(envelope["meta"]["source"], "api.search.hybrid")
        self.assertEqual(envelope["meta"]["rank_mode"], "hybrid")
        self.assertEqual(envelope["meta"]["modality"], "text")
        self.assertEqual(envelope["meta"]["search_backends_used"], ["opensearch_lexical", "qdrant_vector"])
        self.assertEqual(data["results"][0]["source_type"], "document")
        self.assertEqual(data["results"][0]["rank"], 1)
        self.assertEqual(data["results"][0]["raw"]["backend"], "opensearch_lexical")


if __name__ == "__main__":
    unittest.main()
