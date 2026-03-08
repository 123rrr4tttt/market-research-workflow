from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class WorkflowGraphApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"workflow graph integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "workflow-graph-integration"}

    def test_compile_success(self):
        with patch("app.api.workflow_graph._invoke_compile", return_value={"graph_id": "g-1", "ok": True}):
            response = self.client.post("/api/v1/workflow-graph/compile", json={"dsl": {}}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["graph_id"], "g-1")

    def test_compile_with_template_success(self):
        with patch(
            "app.api.workflow_graph._invoke_compile",
            return_value={"graph_id": "g-2", "template_id": "tpl-1", "version_id": "ver-2"},
        ):
            response = self.client.post(
                "/api/v1/workflow-graph/compile",
                json={"template_id": "tpl-1", "version_id": "ver-2"},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["graph_id"], "g-2")
        self.assertEqual(body["data"]["template_id"], "tpl-1")
        self.assertEqual(body["data"]["version_id"], "ver-2")

    def test_run_success(self):
        with patch("app.api.workflow_graph._invoke_run", return_value={"run_id": "r-1", "status": "running"}):
            response = self.client.post("/api/v1/workflow-graph/run", json={"graph_id": "g-1"}, headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["run_id"], "r-1")

    def test_get_run_success(self):
        with patch("app.api.workflow_graph._invoke_get_run", return_value={"run_id": "r-1", "status": "done"}):
            response = self.client.get("/api/v1/workflow-graph/runs/r-1", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["status"], "done")

    def test_get_run_events_success(self):
        with patch("app.api.workflow_graph._invoke_get_run_events", return_value={"items": [{"seq": 1, "event": "started"}]}):
            response = self.client.get("/api/v1/workflow-graph/runs/r-1/events", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["items"][0]["event"], "started")
        self.assertEqual(body["data"]["contract_version"], "workflow_graph.v2")

    def test_replay_run_success(self):
        with patch(
            "app.api.workflow_graph._invoke_replay_run",
            return_value={"run_id": "r-1", "status": "succeeded", "node_statuses": {"n1": "succeeded"}},
        ):
            response = self.client.get("/api/v1/workflow-graph/runs/r-1/replay", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["run_id"], "r-1")
        self.assertEqual(body["data"]["nodes"]["n1"], "succeeded")

    def test_get_compiled_success(self):
        with patch("app.api.workflow_graph._invoke_get_compiled", return_value={"graph_id": "g-1", "version": 1}):
            response = self.client.get("/api/v1/workflow-graph/compiled/g-1", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["version"], 1)

    def test_get_run_not_found_error_envelope(self):
        with patch("app.api.workflow_graph._invoke_get_run", side_effect=KeyError("run not found")):
            response = self.client.get("/api/v1/workflow-graph/runs/missing", headers=self.headers)

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.NOT_FOUND.value)

    def test_template_crud_success(self):
        with patch(
            "app.api.workflow_graph._invoke_list_templates",
            return_value={"items": [{"template_id": "tpl-1"}], "base_version": 3},
        ):
            list_resp = self.client.get("/api/v1/workflow-graph/templates", headers=self.headers)
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.json()["data"]["items"][0]["template_id"], "tpl-1")

        with patch(
            "app.api.workflow_graph._invoke_create_template",
            return_value={"template": {"template_id": "tpl-2", "name": "n"}, "base_version": 4},
        ):
            create_resp = self.client.post(
                "/api/v1/workflow-graph/templates",
                json={"name": "n", "base_version": 3},
                headers=self.headers,
            )
        self.assertEqual(create_resp.status_code, 200)
        self.assertEqual(create_resp.json()["data"]["template"]["template_id"], "tpl-2")

        with patch(
            "app.api.workflow_graph._invoke_get_template",
            return_value={"template": {"template_id": "tpl-2", "name": "n"}, "base_version": 4},
        ):
            get_resp = self.client.get("/api/v1/workflow-graph/templates/tpl-2", headers=self.headers)
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["data"]["template"]["template_id"], "tpl-2")

        with patch(
            "app.api.workflow_graph._invoke_patch_template",
            return_value={"template": {"template_id": "tpl-2", "name": "n2"}, "base_version": 5},
        ):
            patch_resp = self.client.patch(
                "/api/v1/workflow-graph/templates/tpl-2",
                json={"name": "n2", "base_version": 4},
                headers=self.headers,
            )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()["data"]["template"]["name"], "n2")

        with patch(
            "app.api.workflow_graph._invoke_delete_template",
            return_value={"deleted": True, "template_id": "tpl-2", "base_version": 6},
        ):
            delete_resp = self.client.request(
                "DELETE",
                "/api/v1/workflow-graph/templates/tpl-2",
                json={"base_version": 5},
                headers=self.headers,
            )
        self.assertEqual(delete_resp.status_code, 200)
        self.assertTrue(delete_resp.json()["data"]["deleted"])

    def test_template_versions_and_activate_success(self):
        with patch(
            "app.api.workflow_graph._invoke_list_template_versions",
            return_value={"template_id": "tpl-1", "items": [{"version_id": "v1"}], "base_version": 2},
        ):
            list_resp = self.client.get("/api/v1/workflow-graph/templates/tpl-1/versions", headers=self.headers)
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.json()["data"]["items"][0]["version_id"], "v1")

        with patch(
            "app.api.workflow_graph._invoke_create_template_version",
            return_value={"template_id": "tpl-1", "version": {"version_id": "v2"}, "base_version": 3},
        ):
            create_resp = self.client.post(
                "/api/v1/workflow-graph/templates/tpl-1/versions",
                json={"version_id": "v2", "dsl": {"nodes": [], "edges": []}, "base_version": 2},
                headers=self.headers,
            )
        self.assertEqual(create_resp.status_code, 200)
        self.assertEqual(create_resp.json()["data"]["version"]["version_id"], "v2")

        with patch(
            "app.api.workflow_graph._invoke_get_template_version",
            return_value={"template_id": "tpl-1", "version": {"version_id": "v2"}, "base_version": 3},
        ):
            get_resp = self.client.get("/api/v1/workflow-graph/templates/tpl-1/versions/v2", headers=self.headers)
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["data"]["version"]["version_id"], "v2")

        with patch(
            "app.api.workflow_graph._invoke_activate_template_version",
            return_value={"template_id": "tpl-1", "active_version_id": "v2", "base_version": 4},
        ):
            activate_resp = self.client.post(
                "/api/v1/workflow-graph/templates/tpl-1/versions/v2/activate",
                json={"base_version": 3},
                headers=self.headers,
            )
        self.assertEqual(activate_resp.status_code, 200)
        self.assertEqual(activate_resp.json()["data"]["active_version_id"], "v2")

    def test_template_conflict_returns_invalid_input(self):
        with patch(
            "app.api.workflow_graph._invoke_patch_template",
            side_effect=ValueError("conflict: base_version mismatch expected=1 actual=2"),
        ):
            response = self.client.patch(
                "/api/v1/workflow-graph/templates/tpl-1",
                json={"name": "renamed", "base_version": 1},
                headers=self.headers,
            )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertIn("conflict", body["error"]["message"])

    def test_compiler_service_compile_from_template_version(self):
        from app.services.workflow_graph import WorkflowGraphCompilerService

        dsl = {
            "version": "1.0",
            "nodes": [
                {"node_id": "n1", "node_type": "vector_search", "config": {}},
                {"node_id": "n2", "node_type": "join", "config": {}},
            ],
            "edges": [{"from": "n1", "to": "n2"}],
        }
        stored_payload = {
            "base_version": 1,
            "templates": {
                "tpl-1": {
                    "template_id": "tpl-1",
                    "name": "template-1",
                    "active_version_id": "v1",
                    "versions": {"v1": {"version_id": "v1", "dsl": dsl, "created_at": "2026-03-05T00:00:00+00:00"}},
                }
            },
        }

        with patch("app.services.workflow_graph.templates.current_project_key", return_value="demo_proj"), patch(
            "app.services.workflow_graph.templates.get_ingest_config",
            return_value={"payload": stored_payload},
        ):
            service = WorkflowGraphCompilerService()
            result = service.compile({"template_id": "tpl-1", "version_id": "v1", "graph_id": "g-template"})

        self.assertEqual(result["graph_id"], "g-template")
        self.assertEqual(result["template_id"], "tpl-1")
        self.assertEqual(result["version_id"], "v1")
        compiled = service.get_compiled("g-template")
        self.assertEqual(compiled["topo_order"], ["n1", "n2"])
        self.assertEqual(compiled["dsl"]["nodes"][0]["node_id"], "n1")

    def test_template_service_conflict_raises_value_error(self):
        from app.services.workflow_graph.templates import WorkflowGraphTemplateService

        with patch("app.services.workflow_graph.templates.current_project_key", return_value="demo_proj"), patch(
            "app.services.workflow_graph.templates.get_ingest_config",
            return_value={"payload": {"base_version": 2, "templates": {}}},
        ):
            service = WorkflowGraphTemplateService()
            with self.assertRaises(ValueError) as exc_info:
                service.create_template({"name": "demo", "base_version": 1})

        self.assertIn("conflict", str(exc_info.exception))


if __name__ == "__main__":
    unittest.main()
