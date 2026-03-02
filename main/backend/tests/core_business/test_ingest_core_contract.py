from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _TrackedTasks:
    def __init__(self) -> None:
        self.task_ingest_policy = SimpleNamespace(delay=Mock(return_value=SimpleNamespace(id="policy-task-1")))
        self.task_ingest_market = SimpleNamespace(delay=Mock(return_value=SimpleNamespace(id="market-task-1")))
        self.task_ingest_single_url = SimpleNamespace(delay=Mock(return_value=SimpleNamespace(id="single-url-task-1")))
        self.task_run_source_library_item = SimpleNamespace(
            delay=Mock(return_value=SimpleNamespace(id="source-library-task-1"))
        )


def _response_payload(body):
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    return body


class IngestCoreContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest core contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)

    def test_market_rejects_empty_query_terms_before_task_dispatch(self):
        tasks = _TrackedTasks()
        payload = {
            "query_terms": [],
            "project_key": "demo_proj",
            "async_mode": True,
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/market", json=payload)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("query_terms is required and cannot be empty", resp.text)
        tasks.task_ingest_market.delay.assert_not_called()

    def test_source_library_run_rejects_missing_and_conflicting_identifiers(self):
        tasks = _TrackedTasks()

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            missing_resp = self.client.post(
                "/api/v1/ingest/source-library/run",
                json={"project_key": "demo_proj", "async_mode": True},
            )
            conflict_resp = self.client.post(
                "/api/v1/ingest/source-library/run",
                json={
                    "project_key": "demo_proj",
                    "item_key": "demo-item",
                    "handler_key": "news",
                    "async_mode": True,
                },
            )

        self.assertEqual(missing_resp.status_code, 400)
        self.assertIn("item_key or handler_key is required", missing_resp.text)

        self.assertEqual(conflict_resp.status_code, 400)
        self.assertIn("item_key and handler_key are mutually exclusive", conflict_resp.text)

        tasks.task_run_source_library_item.delay.assert_not_called()

    def test_policy_async_returns_task_contract_shape(self):
        tasks = _TrackedTasks()
        payload = {
            "state": "CA",
            "project_key": "demo_proj",
            "async_mode": True,
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/policy", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")

        data = _response_payload(body)
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("task_id"), "policy-task-1")
        self.assertEqual(data.get("status"), "queued")
        self.assertTrue(data.get("async"))
        self.assertEqual(data.get("params"), {"state": "CA"})

        tasks.task_ingest_policy.delay.assert_called_once_with("CA", "demo_proj")

    def test_market_async_normalizes_params_and_returns_task_contract_shape(self):
        tasks = _TrackedTasks()
        payload = {
            "keywords": [" acme ", "", "acme", "tesla "],
            "limit": 5,
            "project_key": "demo_proj",
            "async_mode": True,
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/market", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")

        data = _response_payload(body)
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("task_id"), "market-task-1")
        self.assertEqual(data.get("status"), "queued")
        self.assertTrue(data.get("async"))
        self.assertEqual(data.get("params"), {"query_terms": ["acme", "tesla"], "max_items": 5})

        tasks.task_ingest_market.delay.assert_called_once_with(
            ["acme", "tesla"],
            5,
            True,
            "demo_proj",
            None,
            None,
            None,
            None,
        )

    def test_source_library_run_async_returns_task_contract_shape(self):
        tasks = _TrackedTasks()
        payload = {
            "item_key": "demo-item",
            "project_key": "demo_proj",
            "async_mode": True,
            "override_params": {"k": "v"},
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/source-library/run", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")

        data = _response_payload(body)
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("task_id"), "source-library-task-1")
        self.assertEqual(data.get("status"), "queued")
        self.assertTrue(data.get("async"))
        self.assertEqual(data.get("params"), {"item_key": "demo-item"})

        tasks.task_run_source_library_item.delay.assert_called_once_with(
            "demo-item",
            "demo_proj",
            {"k": "v"},
        )

    def test_url_single_async_task_contract_compat_with_task_result_status(self):
        tasks = _TrackedTasks()
        payload = {
            "url": "https://example.com/post/42",
            "query_terms": ["market"],
            "strict_mode": True,
            "project_key": "demo_proj",
            "async_mode": True,
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/url/single", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")

        data = _response_payload(body)
        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("task_id"), "single-url-task-1")
        self.assertEqual(data.get("status"), "queued")
        self.assertTrue(data.get("async"))
        self.assertEqual(
            data.get("params"),
            {
                "url": "https://example.com/post/42",
                "query_terms": ["market"],
                "strict_mode": True,
            },
        )
        task_result_status = data.get("task_result_status")
        if task_result_status is not None:
            self.assertEqual(task_result_status, data.get("status"))

        tasks.task_ingest_single_url.delay.assert_called_once_with(
            "https://example.com/post/42",
            ["market"],
            True,
            "demo_proj",
        )

    def test_url_single_async_includes_light_filter_search_options_when_overridden(self):
        tasks = _TrackedTasks()
        payload = {
            "url": "https://example.com/post/43",
            "query_terms": ["market"],
            "strict_mode": False,
            "project_key": "demo_proj",
            "async_mode": True,
            "light_filter_enabled": False,
            "light_filter_min_score": 55,
            "light_filter_reject_static_assets": False,
            "light_filter_reject_search_noise_domain": False,
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/url/single", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")

        data = _response_payload(body)
        self.assertIsInstance(data, dict)
        params = data.get("params") or {}
        self.assertEqual(params.get("url"), "https://example.com/post/43")
        self.assertEqual(params.get("strict_mode"), False)
        self.assertIsInstance(params.get("search_options"), dict)
        self.assertEqual(params["search_options"].get("light_filter_enabled"), False)
        self.assertEqual(params["search_options"].get("light_filter_min_score"), 55)
        self.assertEqual(params["search_options"].get("light_filter_reject_static_assets"), False)
        self.assertEqual(params["search_options"].get("light_filter_reject_search_noise_domain"), False)

        effective_payload = data.get("effective_payload") or {}
        self.assertEqual(effective_payload.get("light_filter_enabled"), False)
        self.assertEqual(effective_payload.get("light_filter_min_score"), 55)
        self.assertEqual(effective_payload.get("light_filter_reject_static_assets"), False)
        self.assertEqual(effective_payload.get("light_filter_reject_search_noise_domain"), False)

        tasks.task_ingest_single_url.delay.assert_called_once_with(
            "https://example.com/post/43",
            ["market"],
            False,
            "demo_proj",
            {
                "search_expand": True,
                "search_expand_limit": 3,
                "search_provider": "auto",
                "search_fallback_provider": "ddg_html",
                "fallback_on_insufficient": True,
                "allow_search_summary_write": False,
                "min_results_required": 6,
                "target_candidates": 6,
                "decode_redirect_wrappers": True,
                "filter_low_value_candidates": True,
                "light_filter_enabled": False,
                "light_filter_min_score": 55,
                "light_filter_reject_static_assets": False,
                "light_filter_reject_search_noise_domain": False,
            },
        )

    def test_url_single_sync_response_contains_effective_payload_with_light_filter_fields(self):
        payload = {
            "url": "https://example.com/post/44",
            "query_terms": ["market"],
            "strict_mode": False,
            "project_key": "demo_proj",
            "async_mode": False,
            "light_filter_min_score": 42,
        }

        with patch("app.services.ingest.single_url.ingest_single_url", return_value={"status": "degraded_success", "inserted": 0}):
            resp = self.client.post("/api/v1/ingest/url/single", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        data = _response_payload(body)
        self.assertEqual(data.get("status"), "degraded_success")
        effective_payload = data.get("effective_payload") or {}
        self.assertEqual(effective_payload.get("url"), "https://example.com/post/44")
        self.assertEqual(effective_payload.get("light_filter_enabled"), True)
        self.assertEqual(effective_payload.get("light_filter_min_score"), 42)
        self.assertEqual(effective_payload.get("light_filter_reject_static_assets"), True)
        self.assertEqual(effective_payload.get("light_filter_reject_search_noise_domain"), True)


if __name__ == "__main__":
    unittest.main()
