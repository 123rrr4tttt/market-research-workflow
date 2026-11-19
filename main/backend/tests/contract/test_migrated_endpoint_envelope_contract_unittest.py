from __future__ import annotations

import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from elasticsearch import ConnectionError as ElasticsearchConnectionError
from app.services.search.hybrid import SearchInvocationObservation

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract


class MigratedEndpointEnvelopeContractTestCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="search-consumer-")
        self.addCleanup(temp.cleanup)
        env = patch.dict("os.environ", {"SEARCH_RETRIEVAL_RUNS_PATH": str(Path(temp.name) / "runs.jsonl")})
        env.start()
        self.addCleanup(env.stop)

    def _build_app(self):
        try:
            from fastapi import FastAPI
            from app.api.config import router as config_router
            from app.api.llm_config import router as llm_config_router
            from app.api.projects import router as projects_router
            from app.api.search import router as search_router
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import routers for contract test: {exc}")
        app = FastAPI()
        app.include_router(config_router, prefix="/api/v1")
        app.include_router(llm_config_router, prefix="/api/v1")
        app.include_router(search_router, prefix="/api/v1")
        app.include_router(projects_router, prefix="/api/v1")
        return app

    def test_search_success_envelope_shape(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import TestClient: {exc}")

        client = TestClient(self._build_app())
        mocked_results = [
            {
                "material_id": "material-1",
                "score": 0.99,
                "source_type": "material",
                "provenance": {
                    "source_id": "source-1",
                    "source_reference": "material:material-1",
                },
            }
        ]
        with patch("app.api.search.observe_hybrid_search", return_value=SearchInvocationObservation(mocked_results, ("opensearch",), ())):
            response = client.get(
                "/api/v1/search",
                params={"q": "market", "state": "CA", "rank": "hybrid", "top_k": 1},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(payload.keys()))
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["data"]["results"], mocked_results)
        self.assertEqual(payload["data"]["query"], "market")
        self.assertEqual(payload["data"]["top_k"], 1)
        self.assertEqual(
            payload["data"]["material_query_contract_version"],
            "material_queries.v2",
        )
        self.assertEqual(payload["data"]["material_query"]["sources"], ["material"])
        typed_hit = payload["data"]["material_query_results"][0]
        self.assertEqual(typed_hit["material_id"], "material-1")
        self.assertEqual(typed_hit["source_type"], "material")
        self.assertEqual(typed_hit["rank"], 1)
        evidence_hit = payload["data"]["evidence_hits"][0]
        self.assertEqual(evidence_hit["material_id"], "material-1")
        self.assertEqual(evidence_hit["global_vector_object"]["material_id"], "material-1")
        self.assertEqual(
            evidence_hit["global_vector_object"]["provenance"]["source_reference"],
            "material:material-1",
        )

    def test_projects_auto_create_success_envelope_shape(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import TestClient: {exc}")

        client = TestClient(self._build_app())

        def _project_exists_side_effect(project_key: str) -> bool:
            return project_key == "demo_proj"

        created_stub = {
            "project_key": "new_proj",
            "name": "New Project",
            "schema_name": "tenant_new_proj",
            "activated": True,
            "copied_counts": {},
        }

        with (
            patch("app.api.projects._project_exists", side_effect=_project_exists_side_effect),
            patch("app.api.projects.inject_initial_project", return_value=created_stub),
            patch("app.api.projects._apply_llm_configs_to_project", return_value=0),
        ):
            response = client.post(
                "/api/v1/projects/auto-create",
                json={
                    "project_name": "New Project",
                    "project_key": "new_proj",
                    "template_project_key": "demo_proj",
                    "activate": True,
                    "copy_initial_data": True,
                    "llm_configs": [],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue({"status", "data", "error", "meta"}.issubset(payload.keys()))
        self.assertEqual(payload["status"], "ok")
        self.assertIsNone(payload["error"])
        self.assertIsInstance(payload["data"], dict)
        self.assertEqual(payload["data"]["created_mode"], "inject_initial")
        self.assertEqual(payload["data"]["template_project_key"], "demo_proj")
        self.assertEqual(payload["data"]["llm_configs_applied"], 0)

    def test_projects_auto_create_requires_bound_cell_for_prompt_generation(self):
        from fastapi.testclient import TestClient

        client = TestClient(self._build_app())
        with (
            patch("app.api.projects._project_exists") as check_project,
            patch("app.api.projects.create_project") as create_project,
            patch("app.api.projects._apply_llm_configs_to_project") as apply_configs,
        ):
            response = client.post(
                "/api/v1/projects/auto-create",
                json={
                    "project_name": "New Project",
                    "project_key": "new_proj",
                    "copy_initial_data": False,
                    "llm_configs": [{"service_name": "prompt_factory", "user_prompt_template": "Research notes"}],
                },
            )

        self.assertEqual(response.status_code, 503)
        error = response.json()["detail"]["error"]
        self.assertEqual(error["code"], "CONFIG_ERROR")
        self.assertEqual(error["details"]["binding"], "agent_cell")
        check_project.assert_not_called()
        create_project.assert_not_called()
        apply_configs.assert_not_called()

    def test_search_upstream_error_returns_structured_upstream_error(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())
        with patch(
            "app.services.search.hybrid.get_es_client", side_effect=ElasticsearchConnectionError("Connection refused")
        ):
            response = client.get("/api/v1/search", params={"q": "market", "rank": "bm25"})

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.UPSTREAM_ERROR.value)

    def test_config_env_invalid_payload_returns_structured_invalid_input_error(self):
        try:
            from fastapi.testclient import TestClient
            from app.contracts.errors import ErrorCode
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"Unable to import contract dependencies: {exc}")

        client = TestClient(self._build_app())
        response = client.post("/api/v1/config/env", json={})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)


if __name__ == "__main__":
    unittest.main()
