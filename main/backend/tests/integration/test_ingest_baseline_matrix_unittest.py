from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient
    from app.main import app as backend_app
    from app.contracts.errors import ErrorCode
    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _FakeTask:
    def __init__(self, name: str):
        self._name = name

    def delay(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return SimpleNamespace(id=f"{self._name}-task-id")


class _FakeTasks:
    def __getattr__(self, name: str):
        return _FakeTask(name)


class IngestBaselineMatrixTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest baseline tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)

    def test_ingest_route_inventory_contains_core_modes(self):
        schema = self.client.get("/openapi.json").json()
        paths = schema.get("paths", {})
        expected = [
            "/api/v1/ingest/policy",
            "/api/v1/ingest/market",
            "/api/v1/ingest/source-library/run",
            "/api/v1/ingest/source-library/sync",
            "/api/v1/ingest/social/sentiment",
            "/api/v1/ingest/graph/structured-search",
            "/api/v1/ingest/policy/regulation",
            "/api/v1/ingest/commodity/metrics",
            "/api/v1/ingest/ecom/prices",
        ]
        for p in expected:
            self.assertIn(p, paths)

    def test_core_ingest_modes_require_project_key_in_require_mode(self):
        cases = [
            ("/api/v1/ingest/policy", {"state": "CA", "async_mode": True}),
            ("/api/v1/ingest/market", {"query_terms": ["acme"], "async_mode": True}),
            ("/api/v1/ingest/source-library/run", {"item_key": "demo-item", "async_mode": True}),
            ("/api/v1/ingest/social/sentiment", {"query_terms": ["acme"], "async_mode": True}),
            (
                "/api/v1/ingest/graph/structured-search",
                {
                    "selected_nodes": [{"type": "market", "entry_id": "n1", "label": "ACME"}],
                    "dashboard": {"async_mode": True},
                    "flow_type": "collect",
                },
            ),
            ("/api/v1/ingest/policy/regulation", {"query_terms": ["policy"], "async_mode": True}),
            ("/api/v1/ingest/commodity/metrics", {"limit": 1, "async_mode": True}),
            ("/api/v1/ingest/ecom/prices", {"limit": 1, "async_mode": True}),
        ]
        with patch("app.api.ingest.settings.project_key_enforcement_mode", "require"):
            for path, payload in cases:
                resp = self.client.post(path, json=payload)
                self.assertEqual(resp.status_code, 400, msg=f"path={path} body={resp.text}")
                body = resp.json()
                self.assertIn("detail", body, msg=f"path={path} body={body}")
                self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_core_ingest_modes_accept_explicit_project_key(self):
        headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "baseline-matrix-1"}
        cases = [
            ("/api/v1/ingest/policy", {"state": "CA", "project_key": "demo_proj", "async_mode": True}),
            ("/api/v1/ingest/market", {"query_terms": ["acme"], "project_key": "demo_proj", "async_mode": True}),
            (
                "/api/v1/ingest/source-library/run",
                {"item_key": "demo-item", "project_key": "demo_proj", "async_mode": True},
            ),
            (
                "/api/v1/ingest/social/sentiment",
                {"query_terms": ["acme"], "project_key": "demo_proj", "async_mode": True},
            ),
            (
                "/api/v1/ingest/graph/structured-search",
                {
                    "selected_nodes": [{"type": "market", "entry_id": "n1", "label": "ACME"}],
                    "dashboard": {"async_mode": True, "project_key": "demo_proj"},
                    "flow_type": "collect",
                },
            ),
            (
                "/api/v1/ingest/policy/regulation",
                {"query_terms": ["policy"], "project_key": "demo_proj", "async_mode": True},
            ),
            ("/api/v1/ingest/commodity/metrics", {"limit": 1, "project_key": "demo_proj", "async_mode": True}),
            ("/api/v1/ingest/ecom/prices", {"limit": 1, "project_key": "demo_proj", "async_mode": True}),
        ]
        with patch("app.api.ingest._tasks_module", return_value=_FakeTasks()):
            for path, payload in cases:
                resp = self.client.post(path, json=payload, headers=headers)
                self.assertEqual(resp.status_code, 200, msg=f"path={path} body={resp.text}")
                body = resp.json()
                self.assertEqual(body["status"], "ok", msg=f"path={path} body={body}")
                self.assertEqual(resp.headers.get("x-project-key-source"), "header")
                self.assertEqual(resp.headers.get("x-project-key-resolved"), "demo_proj")


if __name__ == "__main__":
    unittest.main()
