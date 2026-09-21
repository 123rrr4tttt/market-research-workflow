from __future__ import annotations

from contextlib import contextmanager
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_live_sample_write_requires_explicit_project_key(self):
        response = self.client.post(
            "/api/v1/typed-knowledge/live-sample",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("x-error-code"), "INVALID_INPUT")
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], "INVALID_INPUT")
        self.assertEqual(
            body["error"]["message"],
            "project_key is required for typed-knowledge write requests",
        )
        self.assertTrue(body["error"]["details"]["recoverable"])
        self.assertEqual(body["error"]["details"]["field"], "project_key")
        self.assertEqual(body["error"]["details"]["next_action"], "retry_with_explicit_project_key")
        self.assertEqual(body["detail"]["error"], body["error"])

    def test_live_boundary_error_preserves_typed_failure_code(self):
        with patch(
            "app.api.typed_knowledge.live_service.read_live_public_route_contract",
            side_effect=boundary.TypedKnowledgePersistenceBoundaryError(
                "persistence_api_envelope_contract_version_mismatch"
            ),
        ):
            response = self.client.get(
                "/api/v1/typed-knowledge/persistence-boundary",
                params={"project_key": "demo_proj", "repository_mode": "live"},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("x-error-code"), "INVALID_INPUT")
        body = response.json()
        self.assertEqual(body["error"]["code"], "INVALID_INPUT")
        self.assertEqual(
            body["error"]["details"]["failure_code"],
            boundary.TYPED_KNOWLEDGE_PERSISTENCE_BOUNDARY_FAILURE,
        )

    def test_governance_review_write_requires_explicit_project_key(self):
        response = self.client.post(
            "/api/v1/typed-knowledge/governance/review-state",
            json={"object_key": "ki:robotics-policy"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], "INVALID_INPUT")
        self.assertTrue(body["error"]["details"]["recoverable"])
        self.assertEqual(body["error"]["details"]["field"], "project_key")
        self.assertEqual(body["error"]["details"]["next_action"], "retry_with_explicit_project_key")
        self.assertEqual(body["detail"]["error"], body["error"])

    def test_typed_knowledge_write_routes_reject_reserved_public_before_session(self):
        with (
            patch(
                "app.api.typed_knowledge.live_service.seed_live_sample",
                side_effect=AssertionError("reserved project key must not enter a write session"),
            ),
            patch(
                "app.api.typed_knowledge.live_service.apply_governance_review_state",
                side_effect=AssertionError("reserved project key must not enter a write session"),
            ),
        ):
            live_sample = self.client.post(
                "/api/v1/typed-knowledge/live-sample",
                params={"project_key": "public"},
                headers=self.headers,
            )
            governance = self.client.post(
                "/api/v1/typed-knowledge/governance/review-state",
                json={
                    "project_key": "public",
                    "object_key": "ki:robotics-policy",
                },
                headers=self.headers,
            )

        for response in (live_sample, governance):
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.headers.get("x-error-code"), "INVALID_INPUT")
            body = response.json()
            self.assertEqual(body["status"], "error")
            self.assertEqual(body["error"]["code"], "INVALID_INPUT")
            self.assertEqual(
                body["error"]["message"],
                "project_key must retain an explicit writable identity after normalization",
            )
            self.assertEqual(body["error"]["details"]["field"], "project_key")
            self.assertEqual(body["detail"]["error"], body["error"])

    def test_live_sample_write_uses_explicit_project_key_without_demo_fallback(self):
        bound_projects: list[str] = []

        @contextmanager
        def fake_bind_project(project_key: str):
            bound_projects.append(project_key)
            yield

        class FakeSession:
            committed = False

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def commit(self):
                self.committed = True

        with (
            patch("app.services.typed_knowledge.adapters.live_service.bind_project", fake_bind_project),
            patch("app.services.typed_knowledge.adapters.live_service.SessionLocal", FakeSession),
            patch(
                "app.api.typed_knowledge.persistence_boundary.build_live_db_boundary_envelope"
            ) as build_envelope,
        ):
            build_envelope.return_value = {
                "data": {
                    "project_key": "alternate_proj",
                    "repository": {"live_db_write": True},
                    "writes": [
                        {
                            "live_db_write": True,
                            "readback": {
                                "identity_ref": "alternate_proj:knowledge_item:ki:robotics-policy",
                            },
                        }
                    ],
                },
                "meta": {"readiness": {"live_db_persistence": True}},
            }
            response = self.client.post(
                "/api/v1/typed-knowledge/live-sample",
                params={"project_key": "Alternate Proj"},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(bound_projects, ["alternate_proj"])
        self.assertEqual(build_envelope.call_args.kwargs["project_key"], "alternate_proj")
        self.assertNotEqual(build_envelope.call_args.kwargs["project_key"], "demo_proj")
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["data"]["repository"]["live_db_write"])
        self.assertTrue(body["data"]["writes"][0]["live_db_write"])
        self.assertEqual(
            body["data"]["writes"][0]["readback"]["identity_ref"],
            "alternate_proj:knowledge_item:ki:robotics-policy",
        )

    def test_writing_context_uses_explicit_project_key_and_returns_live_context(self):
        bound_projects: list[str] = []

        @contextmanager
        def fake_bind_project(project_key: str):
            bound_projects.append(project_key)
            yield

        class FakeSession:
            committed = False

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def commit(self):
                self.committed = True

        typed_context = {
            "contract_version": "typed_knowledge.writing_knowledge_context.v1",
            "items": [
                {
                    "identity_ref": "alternate_proj:knowledge_item:ki:robotics-policy",
                    "source": "typed_knowledge_live_db_readback",
                }
            ],
        }
        with (
            patch("app.services.typed_knowledge.adapters.live_service.bind_project", fake_bind_project),
            patch("app.services.typed_knowledge.adapters.live_service.SessionLocal", FakeSession),
            patch(
                "app.api.typed_knowledge.persistence_boundary.build_live_writing_context_from_repository"
            ) as build_context,
        ):
            build_context.return_value = typed_context
            response = self.client.get(
                "/api/v1/typed-knowledge/writing-context",
                params={"project_key": "Alternate Proj"},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(bound_projects, ["alternate_proj"])
        self.assertEqual(build_context.call_args.kwargs["project_key"], "alternate_proj")
        self.assertNotEqual(build_context.call_args.kwargs["project_key"], "demo_proj")
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["project_key"], "alternate_proj")
        self.assertEqual(body["data"]["route_path"], boundary.WRITING_CONTEXT_ROUTE_PATH)
        self.assertTrue(body["data"]["live_db_backed"])
        self.assertEqual(body["data"]["typed_knowledge_context"], typed_context)

    def test_governance_review_write_uses_explicit_project_key_without_demo_fallback(self):
        bound_projects: list[str] = []

        @contextmanager
        def fake_bind_project(project_key: str):
            bound_projects.append(project_key)
            yield

        class FakeSession:
            committed = False

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def commit(self):
                self.committed = True

        with (
            patch("app.services.typed_knowledge.adapters.live_service.bind_project", fake_bind_project),
            patch("app.services.typed_knowledge.adapters.live_service.SessionLocal", FakeSession),
            patch(
                "app.api.typed_knowledge.persistence_boundary.apply_live_governance_review_state"
            ) as apply_review_state,
        ):
            apply_review_state.return_value = {
                "project_key": "alternate_proj",
                "identity_ref": "alternate_proj:knowledge_item:ki:robotics-policy",
            }
            response = self.client.post(
                "/api/v1/typed-knowledge/governance/review-state",
                json={"project_key": "Alternate Proj", "object_key": "ki:robotics-policy"},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(bound_projects, ["alternate_proj"])
        self.assertEqual(apply_review_state.call_args.kwargs["project_key"], "alternate_proj")
        self.assertNotEqual(apply_review_state.call_args.kwargs["project_key"], "demo_proj")


if __name__ == "__main__":
    unittest.main()
