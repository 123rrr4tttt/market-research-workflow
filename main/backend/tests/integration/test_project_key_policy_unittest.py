from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient
    from app.contracts.errors import ErrorCode
    from app.api import ingest as ingest_api
    from app.api import resource_pool as resource_pool_api
    from app.api import source_library as source_library_api
    from app.api import writing as writing_api
    from app.main import app as backend_app
    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


def _response_payload(body):
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    return body


class ProjectKeyPolicyTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"project key policy tests require backend dependencies: {_IMPORT_ERROR}")

    def test_error_code_contains_project_key_required(self):
        self.assertEqual(ErrorCode.PROJECT_KEY_REQUIRED.value, "PROJECT_KEY_REQUIRED")

    def test_ingest_require_project_key_uses_explicit_value(self):
        value = ingest_api._require_project_key("demo_proj")
        self.assertEqual(value, "demo_proj")

    def test_ingest_require_project_key_fallback_logs_warning(self):
        with patch("app.api.ingest.settings.project_key_enforcement_mode", "warn"):
            with patch("app.api.ingest.current_project_key", return_value="demo_proj"):
                with self.assertLogs("app.api.ingest", level="WARNING") as cm:
                    value = ingest_api._require_project_key(None)
        self.assertEqual(value, "demo_proj")
        self.assertTrue(any("project_key_fallback_used" in msg for msg in cm.output))

    def test_ingest_require_project_key_missing_raises_structured_error(self):
        with patch("app.api.ingest.current_project_key", return_value=""):
            with self.assertRaises(HTTPException) as ctx:
                ingest_api._require_project_key(None)
        detail = ctx.exception.detail
        self.assertIsInstance(detail, dict)
        self.assertEqual(detail["status"], "error")
        self.assertEqual(detail["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_ingest_require_project_key_in_require_mode_rejects_fallback(self):
        with patch("app.api.ingest.settings.project_key_enforcement_mode", "require"):
            with patch("app.api.ingest.current_project_key", return_value="demo_proj"):
                with self.assertRaises(HTTPException) as ctx:
                    ingest_api._require_project_key(None)
        detail = ctx.exception.detail
        self.assertEqual(detail["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_ingest_require_project_key_in_non_dev_opt_in_require_rejects_fallback(self):
        with (
            patch("app.api.ingest.settings.project_key_enforcement_mode", "warn"),
            patch("app.api.ingest.settings.env", "prod"),
            patch("app.api.ingest.settings.project_key_require_in_non_dev", True),
            patch("app.api.ingest.current_project_key", return_value="demo_proj"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                ingest_api._require_project_key(None)
        detail = ctx.exception.detail
        self.assertEqual(detail["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_source_library_require_project_key_fallback_logs_warning(self):
        with patch("app.api.source_library.settings.project_key_enforcement_mode", "warn"):
            with patch("app.api.source_library.current_project_key", return_value="demo_proj"):
                with self.assertLogs("app.api.source_library", level="WARNING") as cm:
                    value = source_library_api._require_project_key(None)
        self.assertEqual(value, "demo_proj")
        self.assertTrue(any("project_key_fallback_used" in msg for msg in cm.output))

    def test_source_library_require_project_key_in_non_dev_opt_in_require_rejects_fallback(self):
        with (
            patch("app.api.source_library.settings.project_key_enforcement_mode", "warn"),
            patch("app.api.source_library.settings.env", "staging"),
            patch("app.api.source_library.settings.project_key_require_in_non_dev", True),
            patch("app.api.source_library.current_project_key", return_value="demo_proj"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                source_library_api._require_project_key(None)
        detail = ctx.exception.detail
        self.assertEqual(detail["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_writing_resolve_project_key_in_require_mode_rejects_fallback(self):
        with (
            patch("app.api.writing.get_effective_project_key_enforcement_mode", return_value="require"),
            patch("app.api.writing.current_project_key", return_value="demo_proj"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                writing_api._resolve_project_key(None)
        detail = ctx.exception.detail
        self.assertEqual(detail["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_middleware_sets_project_context_headers(self):
        client = TestClient(backend_app)
        resp = client.get("/api/v1/health", headers={"X-Project-Key": "demo_proj", "X-Request-Id": "req-1"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-request-id"), "req-1")
        self.assertEqual(resp.headers.get("x-project-key-source"), "header")
        self.assertEqual(resp.headers.get("x-project-key-resolved"), "demo_proj")
        self.assertEqual(resp.headers.get("x-project-key-enforcement-mode"), "warn")
        self.assertEqual(resp.headers.get("x-project-key-fallback-allowed"), "true")

    def test_middleware_exposes_non_dev_require_mode_headers(self):
        client = TestClient(backend_app)
        with (
            patch("app.main.settings.project_key_enforcement_mode", "warn"),
            patch("app.main.settings.env", "prod"),
            patch("app.main.settings.project_key_require_in_non_dev", True),
        ):
            resp = client.get("/api/v1/health", headers={"X-Project-Key": "demo_proj", "X-Request-Id": "req-2"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-project-key-enforcement-mode"), "require")
        self.assertEqual(resp.headers.get("x-project-key-fallback-allowed"), "false")

    def test_graph_structured_search_explicit_project_key_success(self):
        client = TestClient(backend_app)
        payload = {
            "selected_nodes": [
                {"type": "market", "entry_id": "n-1", "label": "ACME"}
            ],
            "dashboard": {
                "project_key": "demo_proj",
                "async_mode": False,
            },
            "flow_type": "collect",
        }
        fake_batch = {
            "batch_id": "collect:n-1:market_company:b1",
            "batch_name": "collect:n-1:market_company:b1",
            "type": "market",
            "topic_focus": "company",
            "query_terms": ["ACME"],
            "async_mode": False,
            "result": {"inserted": 1, "updated": 0, "skipped": 0},
        }
        with patch("app.api.ingest._run_market_batch", return_value=fake_batch):
            resp = client.post("/api/v1/ingest/graph/structured-search", json=payload)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        if isinstance(body, dict) and "status" in body:
            self.assertEqual(body["status"], "ok")
        data = _response_payload(body)
        self.assertIsInstance(data, dict)
        self.assertEqual(data["flow_type"], "collect")
        self.assertEqual(data["summary"]["batch_count"], 1)

    def test_graph_structured_search_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        payload = {
            "selected_nodes": [
                {"type": "market", "entry_id": "n-1", "label": "ACME"}
            ],
            "dashboard": {
                "async_mode": False,
            },
            "flow_type": "collect",
        }
        with patch("app.api.ingest.settings.project_key_enforcement_mode", "require"):
            resp = client.post("/api/v1/ingest/graph/structured-search", json=payload)
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_source_library_run_legacy_endpoint_removed(self):
        client = TestClient(backend_app)
        resp = client.post(
            "/api/v1/source_library/items/demo-item/run",
            json={"project_key": "demo_proj", "async_mode": False, "override_params": {}},
        )
        self.assertEqual(resp.status_code, 410)
        self.assertEqual(resp.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(body["meta"]["deprecated"], "source_library.legacy_item_run.v1")
        self.assertEqual(body["detail"]["error"]["details"]["item_key"], "demo-item")
        self.assertEqual(
            body["detail"]["error"]["details"]["replacement_endpoint"],
            "/api/v1/ingest/source-library/run",
        )
        self.assertFalse(body["detail"]["error"]["details"]["runs_source_library_item"])

    def test_ingest_source_library_run_explicit_project_key_success(self):
        client = TestClient(backend_app)
        with patch(
            "app.services.collect_runtime.run_source_library_item_compat",
            return_value={"item_key": "demo-item", "ok": True, "saved": 1},
        ) as mocked_run:
            resp = client.post(
                "/api/v1/ingest/source-library/run",
                json={"project_key": "demo_proj", "item_key": "demo-item", "async_mode": False, "override_params": {}},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        data = body.get("data") if isinstance(body, dict) and "data" in body else body
        self.assertIsInstance(data, dict)
        self.assertEqual(data["item"]["item_key"], "demo-item")
        mocked_run.assert_called_once()

    def test_ingest_source_library_run_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.ingest.settings.project_key_enforcement_mode", "require"):
            resp = client.post(
                "/api/v1/ingest/source-library/run",
                json={"item_key": "demo-item", "async_mode": False, "override_params": {}},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_ingest_config_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.ingest.settings.project_key_enforcement_mode", "require"):
            resp = client.post(
                "/api/v1/ingest/config",
                json={"config_key": "social_forum", "config_type": "json", "payload": {}},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_agent_batch_jobs_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.agent_batch.settings.project_key_enforcement_mode", "require"):
            resp = client.post(
                "/api/v1/agent-batch/jobs",
                json={"batch": {"jobs": [{"item_key": "demo-item"}]}},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_agent_batch_nl_command_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.agent_batch.settings.project_key_enforcement_mode", "require"):
            resp = client.post(
                "/api/v1/agent-batch/nl-command",
                json={"command": "collect acme"},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_source_library_project_scope_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.source_library.settings.project_key_enforcement_mode", "require"):
            resp = client.get("/api/v1/source_library/items", params={"scope": "project"})
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_source_library_post_item_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.source_library.settings.project_key_enforcement_mode", "require"):
            resp = client.post(
                "/api/v1/source_library/items",
                json={
                    "item_key": "demo.item",
                    "name": "Demo Item",
                    "channel_key": "market.general",
                    "params": {},
                    "extra": {},
                },
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_source_library_put_item_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.source_library.settings.project_key_enforcement_mode", "require"):
            resp = client.put(
                "/api/v1/source_library/items/demo.item",
                json={
                    "item_key": "demo.item",
                    "name": "Demo Item",
                    "channel_key": "market.general",
                    "params": {},
                    "extra": {},
                },
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_source_library_refresh_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.source_library.settings.project_key_enforcement_mode", "require"):
            resp = client.post(
                "/api/v1/source_library/items/demo.item/refresh",
                json={"incremental": True, "max_site_entries": 10},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_source_library_sync_handler_clusters_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.source_library.settings.project_key_enforcement_mode", "require"):
            resp = client.post(
                "/api/v1/source_library/handler_clusters/sync",
                json={"handlers": ["rss"], "incremental": True, "max_site_entries": 10},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_source_library_external_project_register_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.source_library.settings.project_key_enforcement_mode", "require"):
            resp = client.post(
                "/api/v1/source_library/external-projects/register",
                json={"project_link": "https://github.com/example/demo", "persist": False},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_source_library_sync_shared_from_files_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.source_library.settings.project_key_enforcement_mode", "require"):
            resp = client.post("/api/v1/source_library/sync_shared_from_files")
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_resource_pool_unified_search_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.resource_pool.get_effective_project_key_enforcement_mode", return_value="require"):
            resp = client.post(
                "/api/v1/resource_pool/unified-search",
                json={"item_key": "demo-item", "query_terms": ["acme"]},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_resource_pool_extract_from_documents_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.resource_pool.get_effective_project_key_enforcement_mode", return_value="require"):
            resp = client.post(
                "/api/v1/resource_pool/extract/from-documents",
                json={"scope": "project", "filters": {}, "async_mode": False},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_resource_pool_capture_enable_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.resource_pool.get_effective_project_key_enforcement_mode", return_value="require"):
            resp = client.post(
                "/api/v1/resource_pool/capture/enable",
                json={"scope": "project", "job_types": ["ingest"], "enabled": True},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_resource_pool_capture_from_tasks_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.resource_pool.get_effective_project_key_enforcement_mode", return_value="require"):
            resp = client.post(
                "/api/v1/resource_pool/capture/from-tasks",
                json={"scope": "project", "limit": 20, "async_mode": False},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_resource_pool_discover_site_entries_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.resource_pool.get_effective_project_key_enforcement_mode", return_value="require"):
            resp = client.post(
                "/api/v1/resource_pool/discover/site-entries",
                json={"url_scope": "effective", "target_scope": "project", "dry_run": True, "write": False},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_resource_pool_shared_import_open_source_presets_allows_missing_project_key(self):
        client = TestClient(backend_app)

        class _Result:
            pack_key = "demo-pack"
            title = "Demo Pack"
            scope = "shared"
            project_key = None
            inserted_or_updated = ["https://example.com/feed.xml"]

        with patch.object(resource_pool_api, "import_open_source_preset_pack", return_value=_Result()) as mocked_import:
            resp = client.post(
                "/api/v1/resource_pool/import/open-source-presets",
                json={"scope": "shared", "pack_key": "demo-pack", "enabled": True},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["data"]["project_key"], None)
        mocked_import.assert_called_once()
        self.assertEqual(mocked_import.call_args.kwargs["project_key"], None)

    def test_writing_documents_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.writing.get_effective_project_key_enforcement_mode", return_value="require"):
            resp = client.post("/api/v1/writing/documents", json={"title": "Draft"})
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_writing_suggest_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.writing.get_effective_project_key_enforcement_mode", return_value="require"):
            resp = client.get("/api/v1/writing/suggest", params={"query": "market", "mode": "template"})
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_writing_llm_actions_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.writing.get_effective_project_key_enforcement_mode", return_value="require"):
            resp = client.post(
                "/api/v1/writing/llm-actions",
                json={"action_id": "selection_rewrite", "input_markdown": "draft", "async": False},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_writing_export_markdown_missing_project_key_in_require_mode_fails(self):
        client = TestClient(backend_app)
        with patch("app.api.writing.get_effective_project_key_enforcement_mode", return_value="require"):
            resp = client.post("/api/v1/writing/export/markdown", json={"doc_id": 101})
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], ErrorCode.PROJECT_KEY_REQUIRED.value)

    def test_writing_templates_remains_public_without_project_key_in_require_mode(self):
        client = TestClient(backend_app)
        with patch("app.api.writing.get_effective_project_key_enforcement_mode", return_value="require"):
            resp = client.get("/api/v1/writing/templates")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")


if __name__ == "__main__":
    unittest.main()
