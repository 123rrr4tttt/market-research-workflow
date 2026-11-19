from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from app.api import ingest as ingest_api
    from app.main import app as backend_app
    from fastapi.testclient import TestClient

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _AuthenticatedActorStateApp:
    def __init__(self, app, *, actor_id: str):
        self._app = app
        self._actor_id = actor_id

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            state = scope.setdefault("state", {})
            actor = {
                "actor_id": self._actor_id,
                "source": "test_authenticated_actor_context",
                "auth_type": "codex_test",
            }
            state["authenticated_actor"] = actor
            state["authenticated_actor_id"] = self._actor_id
            state["codex_authenticated_actor"] = actor
        await self._app(scope, receive, send)


class IngestResponseContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest response contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(
            _AuthenticatedActorStateApp(backend_app, actor_id="contract-actor-1")
        )

    def setUp(self):
        admission = patch.object(ingest_api, "check_project_write_admission")
        admission.start()
        self.addCleanup(admission.stop)
        with ingest_api._INGEST_SUBMISSION_LOCK:
            ingest_api._INGEST_SUBMISSIONS.clear()

        def reserve_in_fixture_memory(**kwargs):
            return ingest_api.reserve_ingest_submission_memory_for_test(
                registry_key=kwargs["registry_key"],
                project_key=kwargs["project_key"],
                idempotency_key=kwargs["idempotency_key"],
                trigger_type=kwargs["trigger_type"],
                subject=kwargs["subject"],
                request_hash=kwargs["request_hash"],
                degraded=True,
            )

        self._registry_patchers = [
            patch.object(
                ingest_api,
                "_reserve_ingest_submission_db",
                side_effect=reserve_in_fixture_memory,
            ),
            patch.object(ingest_api, "_complete_ingest_submission_db"),
            patch.object(ingest_api, "_forget_ingest_submission_db"),
        ]
        for patcher in self._registry_patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self._registry_patchers):
            patcher.stop()
        with ingest_api._INGEST_SUBMISSION_LOCK:
            ingest_api._INGEST_SUBMISSIONS.clear()

    @contextmanager
    def installed_url_runtime(self, run_id: str = "url-single-contract-1"):
        with (
            patch("app.models.base.engine") as engine,
            patch(
                "app.successor_runtime.substrate.postgres.session.ServerProjectScopeResolver"
            ) as resolver,
            patch("app.composition.production.submit_installed_program") as submit,
        ):
            resolver.return_value = SimpleNamespace(
                resolve=MagicMock(
                    return_value=SimpleNamespace(
                        project_key="demo_proj",
                        project_registry_revision=1,
                        scope_digest="b" * 64,
                    )
                )
            )
            submit.return_value = ({"run_id": run_id, "state": "READY"}, ("work:1",))
            yield submit
            assert engine.connect.called

    def test_single_url_sync_contract_includes_stable_business_fields(self):
        fake_result = {
            "status": "degraded_success",
            "inserted": 0,
            "inserted_valid": 0,
            "skipped": 1,
            "rejected_count": 1,
            "rejection_breakdown": {"content_gate_rejected": 1},
            "degradation_flags": ["content_gate_rejected:content_gate_rejected"],
            "material_id": None,
            "quality_score": 0.0,
        }

        with patch("app.services.ingest.url_pool.ingest_url_via_source_library_frontdoor", return_value=fake_result):
            resp = self.client.post(
                "/api/v1/ingest/url/single",
                json={
                    "url": "https://example.com/post/1",
                    "project_key": "demo_proj",
                    "async_mode": False,
                    "strict_mode": False,
                },
                headers={"X-Project-Key": "demo_proj"},
            )

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        data = body.get("data") or {}

        # frozen business result fields for platformized ingest outputs
        self.assertIn("status", data)
        self.assertIn("inserted_valid", data)
        self.assertIn("rejected_count", data)
        self.assertIn("rejection_breakdown", data)
        self.assertIn("degradation_flags", data)

        self.assertIsInstance(data.get("rejection_breakdown"), dict)
        self.assertIsInstance(data.get("degradation_flags"), list)

    def test_single_url_async_duplicate_returns_same_pending_submission_without_redis(self):
        request_payload = {
            "url": "https://example.com/post/async-1",
            "project_key": "demo_proj",
            "idempotency_key": "fixture-async-key",
            "async_mode": True,
        }

        with self.installed_url_runtime() as submit_runtime:
            first = self.client.post(
                "/api/v1/ingest/url/single",
                json=request_payload,
                headers={"X-Project-Key": "demo_proj"},
            )
            duplicate = self.client.post(
                "/api/v1/ingest/url/single",
                json=request_payload,
                headers={"X-Project-Key": "demo_proj"},
            )

        self.assertEqual(first.status_code, 200, msg=first.text)
        self.assertEqual(duplicate.status_code, 200, msg=duplicate.text)
        first_data = first.json()["data"]
        duplicate_data = duplicate.json()["data"]
        self.assertIsNone(first_data["task_id"])
        self.assertEqual(first_data["runtime_run_ref"], "runtime-run:url-single-contract-1")
        self.assertEqual(first_data["status"], "submitted")
        self.assertEqual(first_data["feedback_state"], "accepted_pending_worker")
        self.assertEqual(first_data["registry_backend"], "memory")
        self.assertTrue(first_data["registry_degraded"])
        self.assertTrue(duplicate_data["duplicate"])
        self.assertEqual(duplicate_data["duplicate_of"], first_data["submission_id"])
        self.assertEqual(duplicate_data["task_id"], first_data["task_id"])
        self.assertEqual(submit_runtime.call_count, 1)

    def test_single_url_async_dispatch_failure_releases_memory_reservation(self):
        failure_client = TestClient(
            _AuthenticatedActorStateApp(backend_app, actor_id="contract-actor-1"),
            raise_server_exceptions=False,
        )

        with self.installed_url_runtime() as submit_runtime:
            submit_runtime.side_effect = RuntimeError("fixture dispatch failed")
            resp = failure_client.post(
                "/api/v1/ingest/url/single",
                json={
                    "url": "https://example.com/post/dispatch-failure",
                    "project_key": "demo_proj",
                    "idempotency_key": "fixture-dispatch-failure",
                    "async_mode": True,
                },
                headers={"X-Project-Key": "demo_proj"},
            )

        self.assertEqual(resp.status_code, 500, msg=resp.text)
        with ingest_api._INGEST_SUBMISSION_LOCK:
            self.assertEqual(ingest_api._INGEST_SUBMISSIONS, {})

    def test_source_library_batch_rejects_malformed_item_before_service_invocation(self):
        with patch.object(ingest_api, "_run_single_source_library_entry") as mocked_run:
            resp = self.client.post(
                "/api/v1/ingest/source-library/run",
                json={
                    "project_key": "demo_proj",
                    "items": [
                        {
                            "item_key": "fixture.item",
                            "query_terms": "must-be-an-array",
                            "unexpected": True,
                        }
                    ],
                },
                headers={"X-Project-Key": "demo_proj"},
            )

        self.assertEqual(resp.status_code, 400, msg=resp.text)
        self.assertEqual(resp.json()["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(resp.json()["detail"]["error"]["details"]["field"], "items")
        mocked_run.assert_not_called()

    def test_source_library_batch_preserves_explicit_empty_item_overrides(self):
        with patch.object(
            ingest_api,
            "_run_single_source_library_entry",
            return_value={"mode": "source_library_item", "result": {"status": "completed"}},
        ) as mocked_run:
            resp = self.client.post(
                "/api/v1/ingest/source-library/run",
                json={
                    "project_key": "demo_proj",
                    "query_terms": ["top-level-term"],
                    "platforms": ["reddit"],
                    "async_mode": True,
                    "override_params": {"provider": "top-level"},
                    "items": [
                        {
                            "item_key": "fixture.item",
                            "query_terms": [],
                            "platforms": [],
                            "async_mode": False,
                            "override_params": {},
                        }
                    ],
                },
                headers={"X-Project-Key": "demo_proj"},
            )

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        called = mocked_run.call_args.kwargs
        self.assertEqual(called["query_terms"], [])
        self.assertEqual(called["platforms"], [])
        self.assertFalse(called["async_mode"])
        self.assertEqual(called["override_params"], {})

    def test_handler_cluster_uses_system_sync_and_returns_persisted_count(self):
        rows = [
            {"site_url": "https://example.com/one"},
            {"site_url": "https://example.com/two"},
        ]
        sync_response = {
            "status": "ok",
            "data": {
                "ok": True,
                "project_key": "demo_proj",
                "handler_count": 1,
                "results": [
                    {
                        "handler_key": "news",
                        "item_key": "handler.cluster.news",
                        "site_entries_after": 2,
                    }
                ],
            },
            "error": None,
            "meta": {},
        }

        with patch("app.services.resource_pool.list_site_entries", return_value=(rows, 2)), patch(
            "app.services.source_library.item_writer.sync_handler_cluster_items",
            return_value=sync_response,
        ) as sync:
            item_key, site_entry_count = ingest_api._ensure_handler_cluster_item(
                project_key="demo_proj",
                handler_key="news",
            )

        self.assertEqual(item_key, "handler.cluster.news")
        self.assertEqual(site_entry_count, 2)
        sync.assert_called_once_with(
            project_key="demo_proj",
            handlers=["news"],
            incremental=False,
            max_site_entries=2,
        )

    def test_graph_failure_summary_counts_batch_errors_without_provider_calls(self):
        failed_batch = {
            "batch_id": "collect:policy:policy:b1",
            "batch_name": "collect:policy:policy:b1",
            "type": "policy",
            "query_terms": ["water"],
            "async_mode": False,
            "result": {"errors": ["fixture failure"]},
        }
        with patch.object(ingest_api, "_run_policy_batch", return_value=failed_batch):
            resp = self.client.post(
                "/api/v1/ingest/graph/structured-search",
                json={
                    "selected_nodes": [
                        {"type": "policy", "entry_id": "policy", "label": "water"}
                    ],
                    "dashboard": {"project_key": "demo_proj", "async_mode": False},
                    "flow_type": "collect",
                },
                headers={"X-Project-Key": "demo_proj"},
            )

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        summary = resp.json()["data"]["summary"]
        self.assertEqual(summary["batch_count"], 1)
        self.assertEqual(summary["accepted"], 1)
        self.assertEqual(summary["failed"], 1)

    def test_policy_sync_rejects_non_object_raw_metadata(self):
        collect_result = SimpleNamespace(
            meta={"raw": ["malformed"]},
            inserted=0,
            updated=0,
            skipped=0,
            display_meta={},
        )
        with (
            patch.object(ingest_api, "bind_project", return_value=nullcontext()),
            patch("app.services.collect_runtime.collect_request_from_policy_api", return_value=object()),
            patch("app.services.collect_runtime.run_collect", return_value=collect_result),
        ):
            resp = self.client.post(
                "/api/v1/ingest/policy/regulation",
                json={
                    "query_terms": ["water policy"],
                    "project_key": "demo_proj",
                    "async_mode": False,
                },
                headers={"X-Project-Key": "demo_proj"},
            )

        self.assertEqual(resp.status_code, 502, msg=resp.text)
        self.assertEqual(resp.headers.get("x-error-code"), "PARSE_ERROR")
        self.assertEqual(resp.json()["error"]["code"], "PARSE_ERROR")

    def test_json_object_preserves_nested_non_json_path_failure(self):
        with self.assertRaises(TypeError) as raised:
            ingest_api._json_object(
                {"data": {"value": object()}},
                path="ingest.fixture",
            )

        self.assertEqual(
            str(raised.exception),
            "ingest.fixture.data.value contains non-JSON value object",
        )

    def test_graph_structured_search_invalid_payload_uses_standard_error_envelope(self):
        resp = self.client.post(
            "/api/v1/ingest/graph/structured-search",
            json={
                "selected_nodes": [],
                "dashboard": {"project_key": "demo_proj"},
                "flow_type": "collect",
            },
            headers={"X-Project-Key": "demo_proj"},
        )

        self.assertEqual(resp.status_code, 400, msg=resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")
        self.assertEqual(payload["detail"]["error"]["code"], "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
