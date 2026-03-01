from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


class FrontendModernEntryBaselineTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"frontend-modern entry tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "modern-entry-baseline"}

    def test_frontend_modern_entry_inventory(self):
        """Mirror IngestPage + GraphPage heterogeneous task entries."""
        expected_routes = [
            "/api/v1/discovery/generate-keywords",
            "/api/v1/ingest/source-library/sync",
            "/api/v1/ingest/source-library/run",
            "/api/v1/ingest/policy",
            "/api/v1/ingest/policy/regulation",
            "/api/v1/ingest/market",
            "/api/v1/ingest/social/sentiment",
            "/api/v1/ingest/commodity/metrics",
            "/api/v1/ingest/ecom/prices",
            "/api/v1/ingest/graph/structured-search",
        ]
        schema = self.client.get("/openapi.json").json()
        for route in expected_routes:
            self.assertIn(route, schema.get("paths", {}), msg=f"missing route {route}")

    def test_frontend_modern_entries_success_with_explicit_project_key(self):
        cases = [
            (
                "/api/v1/discovery/generate-keywords",
                {
                    "topic": "market intelligence",
                    "language": "en",
                    "platform": None,
                    "topic_focus": None,
                    "base_keywords": ["market intelligence"],
                },
            ),
            ("/api/v1/ingest/source-library/sync", {}),
            (
                "/api/v1/ingest/source-library/run",
                {"item_key": "demo-item", "handler_key": None, "project_key": "demo_proj", "async_mode": True, "override_params": {}},
            ),
            ("/api/v1/ingest/policy", {"state": "CA", "source_hint": None, "project_key": "demo_proj", "async_mode": True}),
            (
                "/api/v1/ingest/policy/regulation",
                {"query_terms": ["regulation"], "keywords": ["regulation"], "max_items": 1, "project_key": "demo_proj", "async_mode": True},
            ),
            (
                "/api/v1/ingest/market",
                {"query_terms": ["market"], "keywords": ["market"], "max_items": 1, "project_key": "demo_proj", "async_mode": True},
            ),
            (
                "/api/v1/ingest/social/sentiment",
                {"query_terms": ["sentiment"], "keywords": ["sentiment"], "platforms": ["reddit"], "max_items": 1, "project_key": "demo_proj", "async_mode": True},
            ),
            ("/api/v1/ingest/commodity/metrics", {"limit": 1, "project_key": "demo_proj", "async_mode": True}),
            ("/api/v1/ingest/ecom/prices", {"limit": 1, "project_key": "demo_proj", "async_mode": True}),
            (
                "/api/v1/ingest/graph/structured-search",
                {
                    "selected_nodes": [{"type": "market", "entry_id": "n1", "label": "ACME"}],
                    "selected_edges": [],
                    "dashboard": {
                        "language": "en",
                        "provider": "auto",
                        "max_items": 1,
                        "enable_extraction": False,
                        "async_mode": True,
                        "platforms": ["reddit"],
                        "enable_subreddit_discovery": True,
                        "base_subreddits": ["MachineLearning"],
                        "source_item_keys": [],
                        "project_key": "demo_proj",
                    },
                    "llm_assist": False,
                    "flow_type": "collect",
                },
            ),
            (
                "/api/v1/ingest/graph/structured-search",
                {
                    "selected_nodes": [{"type": "market", "entry_id": "n2", "label": "ACME2"}],
                    "selected_edges": [],
                    "dashboard": {
                        "language": "en",
                        "provider": "auto",
                        "max_items": 1,
                        "enable_extraction": False,
                        "async_mode": True,
                        "platforms": ["reddit"],
                        "enable_subreddit_discovery": True,
                        "base_subreddits": ["MachineLearning"],
                        "source_item_keys": ["demo-item"],
                        "project_key": "demo_proj",
                    },
                    "llm_assist": False,
                    "flow_type": "source_collect",
                },
            ),
        ]

        with (
            patch("app.api.ingest._tasks_module", return_value=_FakeTasks()),
            patch("app.api.discovery.generate_keywords", return_value=["k1", "k2"]),
            patch("app.services.source_library.sync_shared_library_from_files", return_value={"synced": 1}),
        ):
            for path, payload in cases:
                resp = self.client.post(path, json=payload, headers=self.headers)
                self.assertEqual(resp.status_code, 200, msg=f"path={path} body={resp.text}")
                body = resp.json()
                self.assertEqual(body["status"], "ok", msg=f"path={path} body={body}")
                self.assertEqual(resp.headers.get("x-project-key-source"), "header")
                self.assertEqual(resp.headers.get("x-project-key-resolved"), "demo_proj")

    def test_frontend_modern_ingest_entries_reject_missing_project_key_in_require_mode(self):
        ingest_only_cases = [
            ("/api/v1/ingest/source-library/run", {"item_key": "demo-item", "async_mode": True, "override_params": {}}),
            ("/api/v1/ingest/policy", {"state": "CA", "async_mode": True}),
            ("/api/v1/ingest/policy/regulation", {"query_terms": ["regulation"], "async_mode": True}),
            ("/api/v1/ingest/market", {"query_terms": ["market"], "async_mode": True}),
            ("/api/v1/ingest/social/sentiment", {"query_terms": ["sentiment"], "async_mode": True}),
            ("/api/v1/ingest/commodity/metrics", {"limit": 1, "async_mode": True}),
            ("/api/v1/ingest/ecom/prices", {"limit": 1, "async_mode": True}),
            (
                "/api/v1/ingest/graph/structured-search",
                {
                    "selected_nodes": [{"type": "market", "entry_id": "n1", "label": "ACME"}],
                    "dashboard": {"async_mode": True},
                    "flow_type": "collect",
                },
            ),
        ]
        with patch("app.api.ingest.settings.project_key_enforcement_mode", "require"):
            for path, payload in ingest_only_cases:
                resp = self.client.post(path, json=payload)
                self.assertEqual(resp.status_code, 400, msg=f"path={path} body={resp.text}")
                body = resp.json()
                self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)


if __name__ == "__main__":
    unittest.main()
