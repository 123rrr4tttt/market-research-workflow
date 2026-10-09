from __future__ import annotations

import unittest

import pytest

from app.services.document_queries import (
    MATERIAL_QUERY_CONTRACT_VERSION,
    build_search_endpoint_material_query_envelope,
    validate_material_query_result_envelope,
)

pytestmark = pytest.mark.unit


class SearchEndpointMaterialQueryContractUnitTestCase(unittest.TestCase):
    def test_search_endpoint_envelope_exposes_material_query_contract(self) -> None:
        envelope = build_search_endpoint_material_query_envelope(
            query="  Robotics   Policy  ",
            state=" CA ",
            modality="text",
            rank="hybrid",
            top_k=999,
            project_key=" demo_proj ",
            used_backends=("opensearch_lexical", "qdrant_vector"),
            results=[
                {
                    "id": "material-7",
                    "material_id": 7,
                    "title": "Robot market note",
                    "snippet": "robotics market",
                    "score": 0.77,
                    "backend": "opensearch_lexical",
                }
            ],
        )

        validate_material_query_result_envelope(envelope)
        data = envelope["data"]
        query = data["query"]

        self.assertEqual(data["contract_version"], MATERIAL_QUERY_CONTRACT_VERSION)
        self.assertEqual(query["consumer"], "api.search")
        self.assertEqual(query["project_key"], "demo_proj")
        self.assertEqual(query["query"], "Robotics Policy")
        self.assertEqual(query["filters"], [{"field": "state", "op": "eq", "value": "CA"}])
        self.assertEqual(query["limit"], 100)
        self.assertEqual(envelope["meta"]["source"], "api.search.hybrid")
        self.assertEqual(envelope["meta"]["rank_mode"], "hybrid")
        self.assertEqual(envelope["meta"]["modality"], "text")
        self.assertEqual(envelope["meta"]["search_backends_used"], ["opensearch_lexical", "qdrant_vector"])
        self.assertEqual(data["results"][0]["source_type"], "material")
        self.assertEqual(data["results"][0]["rank"], 1)
        self.assertEqual(data["results"][0]["raw"]["backend"], "opensearch_lexical")


class SearchApiDefensiveDefaultsUnitTestCase(unittest.TestCase):
    def test_unreachable_defensive_defaults(self) -> None:
        # These guards are not reachable through a legal public readback/search
        # record: the validator enforces list-shaped branch/hit fields (no
        # non-list `_search_object_list`/`_search_text_list`), evidence hits are
        # forced to a non-empty `hit_id`, and the vector provenance source is
        # mandatory. They are verified directly as the default contract.
        from app.api import search as search_api

        self.assertEqual(search_api._search_object_list(None), [])
        self.assertEqual(search_api._search_text_list(None), [])
        self.assertEqual(search_api._search_result_identifier({}, index=3), "result-3")
        self.assertEqual(search_api._search_group_provenance_key({}), "unknown")


if __name__ == "__main__":
    unittest.main()
