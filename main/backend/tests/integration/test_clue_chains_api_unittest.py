from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app.api.clue_chains import reset_clue_chain_service_for_tests
    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ClueChainsApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"clue chain integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "clue-chain-api-contract"}

    def setUp(self):
        reset_clue_chain_service_for_tests()

    def test_create_list_get_expand_decision_and_close_flow(self):
        create_response = self.client.post(
            "/api/v1/clue-chains",
            headers=self.headers,
            json={
                "graph_id": "graph-1",
                "title": "Follow pork-chain ownership clues",
                "question": "Which related entities should be investigated next?",
                "root_node_ids": ["node-seed-1", "node-seed-2"],
            },
        )
        self.assertEqual(create_response.status_code, 200)
        create_body = create_response.json()
        self.assertEqual(create_body["status"], "ok")
        chain = create_body["data"]["chain"]
        chain_id = chain["chain_id"]
        self.assertEqual(chain["project_key"], "demo_proj")
        self.assertEqual(chain["status"], "open")
        self.assertEqual(chain["root_node_ids"], ["node-seed-1", "node-seed-2"])

        list_response = self.client.get("/api/v1/clue-chains", headers=self.headers)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["data"]["total"], 1)
        self.assertEqual(list_response.json()["data"]["items"][0]["chain_id"], chain_id)

        get_response = self.client.get(f"/api/v1/clue-chains/{chain_id}", headers=self.headers)
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["data"]["chain"]["chain_id"], chain_id)

        expand_response = self.client.post(
            f"/api/v1/clue-chains/{chain_id}/expand",
            headers=self.headers,
            json={"mode": "source_library_search", "query": "Smithfield supplier relation", "limit": 3},
        )
        self.assertEqual(expand_response.status_code, 200)
        expand_data = expand_response.json()["data"]
        self.assertEqual(expand_data["hop"]["mode"], "source_library_search")
        self.assertEqual(expand_data["hop"]["status"], "completed")
        self.assertEqual(len(expand_data["candidates"]), 1)
        candidate = expand_data["candidates"][0]
        evidence = expand_data["evidence"][0]
        self.assertEqual(candidate["evidence_ids"], [evidence["evidence_id"]])
        self.assertEqual(evidence["candidate_id"], candidate["candidate_id"])

        decision_response = self.client.post(
            f"/api/v1/clue-chains/{chain_id}/candidates/{candidate['candidate_id']}/decision",
            headers=self.headers,
            json={"action": "promote", "reason": "strong ownership clue", "decided_by": "api-test"},
        )
        self.assertEqual(decision_response.status_code, 200)
        decision_data = decision_response.json()["data"]
        self.assertEqual(decision_data["candidate"]["status"], "accepted")
        self.assertEqual(decision_data["decision"]["evidence_ids"], candidate["evidence_ids"])
        self.assertTrue(decision_data["decision"]["target_node_id"].startswith("node_"))

        close_response = self.client.post(
            f"/api/v1/clue-chains/{chain_id}/close",
            headers=self.headers,
            json={"reason": "frontier exhausted", "closed_by": "api-test"},
        )
        self.assertEqual(close_response.status_code, 200)
        close_data = close_response.json()["data"]
        self.assertEqual(close_data["chain"]["status"], "closed")
        self.assertEqual(close_data["chain"]["close_reason"], "frontier exhausted")

    def test_external_search_api_contract_stays_fixture_gated_and_review_only(self):
        create_response = self.client.post(
            "/api/v1/clue-chains",
            headers=self.headers,
            json={
                "graph_id": "graph-1",
                "title": "Fixture-gated external clue search",
                "question": "Which external lead should be reviewed?",
                "root_node_ids": ["node-seed-external"],
            },
        )
        self.assertEqual(create_response.status_code, 200)
        chain_id = create_response.json()["data"]["chain"]["chain_id"]

        expand_response = self.client.post(
            f"/api/v1/clue-chains/{chain_id}/expand",
            headers=self.headers,
            json={"mode": "external_search", "query": "commodity margin source trail", "limit": 5},
        )
        self.assertEqual(expand_response.status_code, 200)
        expand_data = expand_response.json()["data"]

        self.assertNotIn("edges", expand_data)
        self.assertEqual(expand_data["hop"]["mode"], "external_search")
        self.assertEqual(expand_data["hop"]["status"], "completed")
        self.assertGreaterEqual(len(expand_data["candidates"]), 1)
        self.assertGreaterEqual(len(expand_data["evidence"]), 1)

        hop_trace = expand_data["hop"]["metadata"]["trace"]
        provider_trace = hop_trace["expansion"]
        self.assertTrue(hop_trace["requires_review"])
        self.assertFalse(hop_trace["graph_mutation_performed"])
        self.assertTrue(provider_trace["fixture_gate"])
        self.assertFalse(provider_trace["network_allowed"])
        self.assertFalse(provider_trace["live_enabled"])
        self.assertEqual(provider_trace["trace_context"]["api"], "clue_chains.expand")

        candidate = expand_data["candidates"][0]
        evidence = expand_data["evidence"][0]
        self.assertEqual(candidate["status"], "pending")
        self.assertFalse(candidate["metadata"]["promotion_allowed"])
        self.assertTrue(candidate["metadata"]["requires_review"])
        self.assertTrue(candidate["metadata"]["fixture_gate"])
        self.assertEqual(candidate["evidence_ids"], [evidence["evidence_id"]])
        self.assertEqual(evidence["candidate_id"], candidate["candidate_id"])
        self.assertEqual(evidence["metadata"]["fixture_gate"], True)
        self.assertEqual(evidence["metadata"]["trace"]["trace_context"]["api"], "clue_chains.expand")

    def test_invalid_input_and_not_found_are_structured_errors(self):
        invalid_create = self.client.post(
            "/api/v1/clue-chains",
            headers=self.headers,
            json={"graph_id": "graph-1", "title": "No roots", "root_node_ids": []},
        )
        self.assertEqual(invalid_create.status_code, 422)
        self.assertEqual(invalid_create.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        self.assertEqual(invalid_create.json()["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)

        missing_get = self.client.get("/api/v1/clue-chains/missing-chain", headers=self.headers)
        self.assertEqual(missing_get.status_code, 404)
        self.assertEqual(missing_get.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)
        self.assertEqual(missing_get.json()["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)

        create_response = self.client.post(
            "/api/v1/clue-chains",
            headers=self.headers,
            json={"graph_id": "graph-1", "title": "Merge validation", "root_node_ids": ["node-a"]},
        )
        chain_id = create_response.json()["data"]["chain"]["chain_id"]
        expand_response = self.client.post(
            f"/api/v1/clue-chains/{chain_id}/expand",
            headers=self.headers,
            json={"mode": "external_search", "query": "public fixture"},
        )
        candidate_id = expand_response.json()["data"]["candidates"][0]["candidate_id"]
        invalid_decision = self.client.post(
            f"/api/v1/clue-chains/{chain_id}/candidates/{candidate_id}/decision",
            headers=self.headers,
            json={"action": "merge"},
        )
        self.assertEqual(invalid_decision.status_code, 400)
        self.assertEqual(invalid_decision.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        self.assertEqual(invalid_decision.json()["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)

    def test_openapi_response_schemas_are_visible(self):
        schema = backend_app.openapi()
        cases = {
            ("post", "/api/v1/clue-chains"): "ApiEnvelope_ClueChainDetailData_",
            ("get", "/api/v1/clue-chains"): "ApiEnvelope_ClueChainListData_",
            ("get", "/api/v1/clue-chains/{chain_id}"): "ApiEnvelope_ClueChainDetailData_",
            ("post", "/api/v1/clue-chains/{chain_id}/expand"): "ApiEnvelope_ClueChainExpansionData_",
            (
                "post",
                "/api/v1/clue-chains/{chain_id}/candidates/{candidate_id}/decision",
            ): "ApiEnvelope_ClueChainDecisionResponseData_",
            ("post", "/api/v1/clue-chains/{chain_id}/close"): "ApiEnvelope_ClueChainCloseData_",
        }
        for (method, path), expected_component in cases.items():
            with self.subTest(method=method, path=path):
                response_schema = schema["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]
                self.assertEqual(response_schema["$ref"].rsplit("/", 1)[-1], expected_component)

    def test_clue_chains_module_has_no_untyped_openapi_200_schemas(self):
        from scripts.generate_api_schema_inventory import build_inventory

        inventory = build_inventory(backend_app)
        clue_chain_summary = next(
            row for row in inventory["source_summary"] if row["source_module"] == "clue_chains.py"
        )

        self.assertEqual(clue_chain_summary["operations"], 6, msg=clue_chain_summary)
        self.assertEqual(clue_chain_summary["request_bodies"], 4, msg=clue_chain_summary)
        self.assertEqual(clue_chain_summary["untyped_200"], 0, msg=clue_chain_summary)
        self.assertEqual(clue_chain_summary["response_models"], clue_chain_summary["operations"], msg=clue_chain_summary)


if __name__ == "__main__":
    unittest.main()
