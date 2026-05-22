from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app.main import app as backend_app
    from app.services.typed_knowledge import persistence_boundary as boundary

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class TypedKnowledgeApiRouteIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"typed knowledge route tests require backend dependencies: {_IMPORT_ERROR}")
        backend_app.openapi_schema = None
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "typed-knowledge-route"}

    def test_public_persistence_boundary_route_returns_contract_envelope(self):
        response = self.client.get(
            "/api/v1/typed-knowledge/persistence-boundary",
            params={"project_key": "demo_proj"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["contract_version"], boundary.PUBLIC_API_ROUTE_CONTRACT_VERSION)
        self.assertEqual(body["data"]["route"]["path"], boundary.PUBLIC_API_ROUTE_PATH)
        self.assertTrue(body["data"]["route"]["public_api_route"])
        self.assertFalse(body["data"]["route"]["live_db_backed"])
        self.assertTrue(body["meta"]["readiness"]["public_api_route"])
        self.assertTrue(body["meta"]["readiness"]["persisted_card_request_response_readback"])
        self.assertFalse(body["meta"]["readiness"]["live_db_persistence"])
        self.assertFalse(body["meta"]["readiness"]["live_api_closure"])
        self.assertFalse(body["meta"]["readiness"]["live_ui_closure"])
        self.assertIn("live_db_persistence_not_implemented", body["meta"]["remaining_live_gaps"])
        self.assertNotIn(
            "public_typed_knowledge_api_route_not_implemented",
            body["meta"]["remaining_live_gaps"],
        )

        records = body["data"]["persistence_boundary"]["records"]
        self.assertEqual(len(records), 4)
        records_by_type = {record["object_type"]: record for record in records}
        item_record = records_by_type["knowledge_item"]
        self.assertEqual(item_record["identity_ref"], "demo_proj:knowledge_item:ki:robotics-policy")
        self.assertEqual(
            item_record["writing_handoff_refs"][0]["consumer"],
            "writing.keyword_card",
        )
        self.assertFalse(body["data"]["persistence_boundary"]["repository"]["live_db_write"])

        readback = body["data"]["persisted_card_request_response_readback"]
        self.assertEqual(
            readback["contract_version"],
            boundary.PERSISTED_CARD_REQUEST_RESPONSE_READBACK_CONTRACT_VERSION,
        )
        self.assertEqual(readback["keyword_card_request"]["path"], boundary.WRITING_KEYWORD_CARD_ROUTE_PATH)
        self.assertEqual(
            readback["persisted_document"]["metadata_json"]["typed_knowledge_context"],
            readback["keyword_card_request"]["body"]["context"]["typed_knowledge_context"],
        )
        self.assertEqual(readback["keyword_card_response"]["body"]["cards"][0]["publisher"], "typed_knowledge")
        self.assertFalse(readback["meta"]["readiness"]["live_api_closure"])
        self.assertFalse(readback["meta"]["readiness"]["live_ui_closure"])

    def test_public_route_keeps_project_scoped_identity_in_contract_readback(self):
        response = self.client.get(
            "/api/v1/typed-knowledge/persistence-boundary",
            params={"project_key": "alternate_proj"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        records_by_type = {
            record["object_type"]: record
            for record in body["data"]["persistence_boundary"]["records"]
        }
        self.assertEqual(
            records_by_type["knowledge_item"]["identity_ref"],
            "alternate_proj:knowledge_item:ki:robotics-policy",
        )
        self.assertEqual(
            body["data"]["persistence_boundary"]["repository"]["persistence_mode"],
            "in_memory_contract",
        )
        self.assertEqual(
            body["data"]["persisted_card_request_response_readback"]["readback"]["knowledge_item_key"],
            "ki:robotics-policy",
        )

    def test_openapi_exposes_typed_knowledge_route_contract_schema(self):
        schema = backend_app.openapi()
        response_schema = (
            schema["paths"]["/api/v1/typed-knowledge/persistence-boundary"]["get"]
            ["responses"]["200"]["content"]["application/json"]["schema"]
        )

        self.assertEqual(response_schema["$ref"].rsplit("/", 1)[-1], "TypedKnowledgeRouteContractEnvelope")
        route_data = schema["components"]["schemas"]["TypedKnowledgeRouteContractData"]["properties"]
        self.assertIn("persisted_card_request_response_readback", route_data)


if __name__ == "__main__":
    unittest.main()
