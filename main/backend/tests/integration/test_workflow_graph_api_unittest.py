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


if __name__ == "__main__":
    unittest.main()
