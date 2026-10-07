from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from app.api import ingest as ingest_api
    from app.main import app as backend_app
    from fastapi.testclient import TestClient

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _TrackedTasks:
    def __init__(self) -> None:
        self.task_ingest_market = SimpleNamespace(delay=Mock(return_value=SimpleNamespace(id="market-task-1")))
        self.task_run_source_library_item = SimpleNamespace(
            delay=Mock(return_value=SimpleNamespace(id="source-library-task-1"))
        )


class _ApplyAsyncTask:
    def __init__(self, task_id: str) -> None:
        self.delay = Mock(return_value=SimpleNamespace(id=task_id))
        self.apply_async = Mock(return_value=SimpleNamespace(id=task_id))


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


def _response_payload(body):
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    return body


def _unique_key(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _reserve_in_fixture_memory(**kwargs):
    return ingest_api.reserve_ingest_submission_memory_for_test(
        registry_key=kwargs["registry_key"],
        project_key=kwargs["project_key"],
        idempotency_key=kwargs["idempotency_key"],
        trigger_type=kwargs["trigger_type"],
        subject=kwargs["subject"],
        request_hash=kwargs["request_hash"],
        degraded=True,
    )


@contextmanager
def installed_url_runtime():
    run = {"run_id": "url-single-runtime-1", "state": "READY"}
    work_item_ids = ("work:url-single-runtime-1:1",)
    with (
        patch("app.models.base.engine") as engine,
        patch(
            "app.successor_runtime.substrate.postgres.session.ServerProjectScopeResolver"
        ) as resolver,
        patch(
            "app.composition.production.submit_installed_program"
        ) as submit,
    ):
        connection = engine.connect.return_value.__enter__.return_value
        project_scope = SimpleNamespace(
            project_key="demo_proj",
            project_registry_revision=1,
            scope_digest="a" * 64,
        )
        resolver.return_value = SimpleNamespace(
            resolve=Mock(return_value=project_scope)
        )
        submit.return_value = (run, work_item_ids)
        yield submit
        assert connection is not None


class IngestCoreContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest core contract tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(
            _AuthenticatedActorStateApp(backend_app, actor_id="api-actor-1")
        )

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
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(body["detail"]["error"]["details"]["field"], "query_terms")
        tasks.task_ingest_market.delay.assert_not_called()

    def test_ingest_config_maps_known_failures_to_standard_error_envelope(self):
        with patch("app.api.ingest.upsert_ingest_config", side_effect=ValueError("invalid config payload")):
            invalid_resp = self.client.post(
                "/api/v1/ingest/config",
                json={
                    "project_key": "demo_proj",
                    "config_key": "social_forum",
                    "config_type": "social_forum",
                    "payload": {"k": "v"},
                },
            )
        with patch("app.api.ingest.upsert_ingest_config", side_effect=RuntimeError("database timeout")):
            upstream_resp = self.client.post(
                "/api/v1/ingest/config",
                json={
                    "project_key": "demo_proj",
                    "config_key": "social_forum",
                    "config_type": "social_forum",
                    "payload": {"k": "v"},
                },
            )

        self.assertEqual(invalid_resp.status_code, 400)
        self.assertEqual(invalid_resp.json()["detail"]["error"]["code"], "INVALID_INPUT")

        self.assertEqual(upstream_resp.status_code, 503)
        self.assertEqual(upstream_resp.json()["detail"]["error"]["code"], "UPSTREAM_ERROR")

    def test_ingest_config_missing_record_sets_error_header(self):
        with patch("app.api.ingest.get_ingest_config", return_value=None):
            resp = self.client.get(
                "/api/v1/ingest/config",
                params={"project_key": "demo_proj", "config_key": "missing_config"},
            )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.headers.get("x-error-code"), "NOT_FOUND")
        body = resp.json()
        self.assertEqual(body["error"]["code"], "NOT_FOUND")
        self.assertEqual(body["detail"]["error"]["code"], "NOT_FOUND")

    def test_market_runtime_errors_use_mapped_status_and_error_headers(self):
        with patch("app.api.ingest.bind_project", side_effect=RuntimeError("missing API key")):
            config_resp = self.client.post(
                "/api/v1/ingest/market",
                json={
                    "query_terms": ["acme"],
                    "project_key": "demo_proj",
                    "async_mode": False,
                },
            )

        with patch("app.api.ingest.bind_project", side_effect=RuntimeError("database timeout")):
            upstream_resp = self.client.post(
                "/api/v1/ingest/market",
                json={
                    "query_terms": ["acme"],
                    "project_key": "demo_proj",
                    "async_mode": False,
                },
            )

        self.assertEqual(config_resp.status_code, 400)
        self.assertEqual(config_resp.headers.get("x-error-code"), "CONFIG_ERROR")
        self.assertEqual(config_resp.json()["detail"]["error"]["code"], "CONFIG_ERROR")

        self.assertEqual(upstream_resp.status_code, 503)
        self.assertEqual(upstream_resp.headers.get("x-error-code"), "UPSTREAM_ERROR")
        self.assertEqual(upstream_resp.json()["detail"]["error"]["code"], "UPSTREAM_ERROR")

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
        self.assertEqual(missing_resp.json()["detail"]["error"]["code"], "INVALID_INPUT")

        self.assertEqual(conflict_resp.status_code, 400)
        self.assertEqual(conflict_resp.json()["detail"]["error"]["code"], "INVALID_INPUT")

        tasks.task_run_source_library_item.delay.assert_not_called()

    def test_source_library_run_rejects_invalid_items_payload_with_standard_envelope(self):
        resp = self.client.post(
            "/api/v1/ingest/source-library/run",
            json={
                "project_key": "demo_proj",
                "items": ["bad-entry"],
            },
        )

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(body["detail"]["error"]["details"]["field"], "items")

    def test_subproject_news_rejects_body_project_mismatch_with_standard_envelope(self):
        resp = self.client.post(
            "/api/v1/ingest/subprojects/demo_proj/news/google_news",
            json={"project_key": "other_proj", "limit": 5, "async_mode": True},
        )

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(body["detail"]["error"]["details"]["project_key"], "other_proj")

    def test_graph_structured_search_rejects_invalid_payload_with_standard_envelope(self):
        empty_nodes = self.client.post(
            "/api/v1/ingest/graph/structured-search",
            json={
                "selected_nodes": [],
                "dashboard": {"project_key": "demo_proj"},
                "flow_type": "collect",
            },
        )
        invalid_flow = self.client.post(
            "/api/v1/ingest/graph/structured-search",
            json={
                "selected_nodes": [{"type": "company", "label": "Acme"}],
                "dashboard": {"project_key": "demo_proj"},
                "flow_type": "bad",
            },
        )

        self.assertEqual(empty_nodes.status_code, 400)
        self.assertEqual(empty_nodes.json()["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(empty_nodes.json()["detail"]["error"]["details"]["field"], "selected_nodes")

        self.assertEqual(invalid_flow.status_code, 400)
        self.assertEqual(invalid_flow.json()["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(invalid_flow.json()["detail"]["error"]["details"]["field"], "flow_type")

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
            workflow_run_id=None,
            trace_id=None,
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
        trace_chain = data.get("trace_chain") or {}
        self.assertEqual(trace_chain.get("contract_version"), "ingest_search.trace_chain.v1")
        self.assertEqual(trace_chain.get("entrypoint"), "ingest.source_library.run")
        self.assertEqual(trace_chain.get("ids", {}).get("task_id"), "source-library-task-1")
        self.assertEqual(trace_chain.get("ids", {}).get("retrieval_run_id"), None)
        self.assertEqual(trace_chain.get("run_order", [])[0]["stage"], "ingest_submission")
        self.assertEqual(trace_chain.get("run_order", [])[1]["stage"], "dispatch_or_execution")
        self.assertEqual(trace_chain.get("run_order", [])[2]["status"], "not_created_at_ingest_response")
        self.assertEqual(trace_chain.get("fallback", {}).get("used"), "unknown")
        self.assertFalse(trace_chain.get("index", {}).get("real_timestamp_available"))
        self.assertIn("no_real_index_timestamp_at_ingest_response", trace_chain.get("known_limitations") or [])

        tasks.task_run_source_library_item.delay.assert_called_once_with(
            "demo-item",
            "demo_proj",
            {"k": "v"},
            workflow_run_id=None,
            trace_id=None,
        )

    def test_source_library_run_promotes_top_level_fields_into_override_params(self):
        tasks = _TrackedTasks()
        payload = {
            "item_key": "demo-item",
            "project_key": "demo_proj",
            "async_mode": True,
            "query_terms": ["ai terminal"],
            "urls": ["https://example.com/a"],
            "max_items": 3,
            "provider": "google",
            "language": "zh",
            "scope": "project",
            "platforms": ["web", "rss"],
            "source_mode": "site_search",
            "override_params": {"k": "v"},
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/source-library/run", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        tasks.task_run_source_library_item.delay.assert_called_once_with(
            "demo-item",
            "demo_proj",
            {
                "k": "v",
                "query_terms": ["ai terminal"],
                "urls": ["https://example.com/a"],
                "max_items": 3,
                "limit": 3,
                "provider": "google",
                "language": "zh",
                "scope": "project",
                "platforms": ["web", "rss"],
            },
            workflow_run_id=None,
            trace_id=None,
        )

    def test_source_library_run_accepts_single_source_guard_and_preserves_evidence(self):
        tasks = _TrackedTasks()
        guard = {
            "contract_version": "resource_pool.site_entry.single_source_guard.v1",
            "strict_source": True,
            "guarantee": True,
            "allowed_urls": ["https://example.com/feed.xml"],
            "allowed_count": 1,
            "blocked_reason": None,
            "source_ref": {"site_entry_url": "https://example.com/feed.xml"},
            "report_source_ref": "resource_pool.site_entry:project:10",
        }
        payload = {
            "item_key": "demo-item",
            "project_key": "demo_proj",
            "async_mode": True,
            "override_params": {
                "site_entries": ["https://example.com/feed.xml"],
                "single_source_guard": guard,
            },
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/source-library/run", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        data = _response_payload(resp.json())
        self.assertEqual(data.get("task_id"), "source-library-task-1")
        self.assertEqual(data.get("single_source_guard"), guard)
        self.assertEqual(data.get("strict_source"), guard)
        tasks.task_run_source_library_item.delay.assert_called_once_with(
            "demo-item",
            "demo_proj",
            {
                "site_entries": ["https://example.com/feed.xml"],
                "single_source_guard": guard,
            },
            workflow_run_id=None,
            trace_id=None,
        )

    def test_source_library_run_rejects_blocked_single_source_guard_before_dispatch(self):
        tasks = _TrackedTasks()
        guard = {
            "contract_version": "resource_pool.site_entry.single_source_guard.v1",
            "strict_source": True,
            "guarantee": False,
            "allowed_urls": ["https://example.com/feed.xml"],
            "allowed_count": 1,
            "blocked_reason": "review_rejected",
        }
        payload = {
            "item_key": "demo-item",
            "project_key": "demo_proj",
            "async_mode": True,
            "override_params": {
                "site_entries": ["https://example.com/feed.xml"],
                "single_source_guard": guard,
            },
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/source-library/run", json=payload)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        details = body["detail"]["error"]["details"]
        self.assertEqual(body["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(details["reason_code"], "single_source_guard_blocked")
        self.assertEqual(details["single_source_guard"], guard)
        self.assertEqual(details["expected"], {"guarantee": True, "blocked_reason": None})
        self.assertEqual(details["actual"], {"guarantee": False, "blocked_reason": "review_rejected"})
        tasks.task_run_source_library_item.delay.assert_not_called()

    def test_source_library_run_rejects_single_source_guard_site_entries_mismatch_before_dispatch(self):
        tasks = _TrackedTasks()
        guard = {
            "contract_version": "resource_pool.site_entry.single_source_guard.v1",
            "strict_source": True,
            "guarantee": True,
            "allowed_urls": ["https://example.com/feed.xml"],
            "allowed_count": 1,
            "blocked_reason": None,
        }
        payload = {
            "item_key": "demo-item",
            "project_key": "demo_proj",
            "async_mode": True,
            "override_params": {
                "site_entries": ["https://evil.example/feed.xml"],
                "single_source_guard": guard,
            },
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/source-library/run", json=payload)

        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        details = body["detail"]["error"]["details"]
        self.assertEqual(body["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(details["reason_code"], "single_source_guard_site_entries_mismatch")
        self.assertEqual(details["single_source_guard"], guard)
        self.assertEqual(
            details["expected"],
            {
                "site_entries": ["https://example.com/feed.xml"],
                "allowed_urls": ["https://example.com/feed.xml"],
            },
        )
        self.assertEqual(
            details["actual"],
            {
                "site_entries": ["https://evil.example/feed.xml"],
                "allowed_urls": ["https://example.com/feed.xml"],
            },
        )
        tasks.task_run_source_library_item.delay.assert_not_called()

    def test_source_library_run_items_batch_uses_item_form_only(self):
        tasks = _TrackedTasks()
        payload = {
            "project_key": "demo_proj",
            "items": [
                {
                    "item_key": "demo-item",
                    "async_mode": True,
                    "override_params": {"k": "v"},
                },
                {
                    "item_key": "demo-item-2",
                    "async_mode": True,
                },
            ],
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks):
            resp = self.client.post("/api/v1/ingest/source-library/run", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        data = _response_payload(body)
        self.assertTrue(bool(data.get("batch")))
        self.assertEqual(data.get("count"), 2)
        self.assertEqual(data.get("queued"), 2)
        self.assertEqual(len(data.get("items") or []), 2)

        self.assertEqual(tasks.task_run_source_library_item.delay.call_count, 2)
        calls = tasks.task_run_source_library_item.delay.call_args_list
        self.assertEqual(calls[0].args, ("demo-item", "demo_proj", {"k": "v"}))
        self.assertEqual(calls[1].args, ("demo-item-2", "demo_proj", {}))

    def test_source_library_run_sync_preserves_terminal_payload_and_exposes_frontdoor_tracks(self):
        payload = {
            "item_key": "external.demo.item",
            "project_key": "demo_proj",
            "async_mode": False,
            "override_params": {"max_items": 2},
        }
        compat_result = {
            "terminal_output": {
                "contract_version": "source_library.terminal_output.v1",
                "status": "ok",
                "source_mode": "protocol_search",
                "item": {
                    "item_key": "external.demo.item",
                    "item_type": "user_defined",
                    "managed_by": "user",
                    "external_manifest": {
                        "project_link": "https://github.com/example/external-demo",
                        "execution_mode": "rss_feed",
                    },
                },
                "request": {"project_key": "demo_proj"},
                "results": {
                    "records": [{"record_id": "r1", "url": "https://example.com/a", "title": "Alpha"}],
                    "stats": {"fetched": 1, "normalized": 1, "dropped": 0, "errors": 0},
                },
                "errors": [],
                "meta": {"reason_code": "ok"},
            },
            "frontdoor_ingress": {
                "contract_version": "frontdoor.ingress.v1",
                "ingress_type": "source_library",
                "source_ref": {
                    "source_kind": "feed_aggregator",
                    "execution_mode": "rss_feed",
                },
            },
            "postprocess_frontdoor": {
                "status": "ok",
                "data": {"admission": "defer"},
            },
            "legacy_result": {
                "item_key": "external.demo.item",
                "channel_key": "external_project.manifest",
            },
            "legacy_result_is_deprecated": True,
            "display_meta": {"summary": "external item"},
        }

        with patch("app.services.collect_runtime.run_source_library_item_compat", return_value=compat_result):
            resp = self.client.post("/api/v1/ingest/source-library/run", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        data = _response_payload(body)
        self.assertEqual(data["contract_version"], "source_library.terminal_output.v1")
        self.assertEqual(data["terminal_output"]["contract_version"], "source_library.terminal_output.v1")
        self.assertEqual(data["authority_output"]["contract_version"], "source_library.authority_output.v1")
        self.assertEqual(data["compat_projection"]["contract_version"], "source_library.compat_projection.v1")
        self.assertEqual(data["frontdoor_ingress"]["contract_version"], "frontdoor.ingress.v1")
        self.assertEqual(data["frontdoor_ingress"]["ingress_type"], "source_library")
        self.assertEqual(data["postprocess_frontdoor"]["data"]["admission"], "defer")
        self.assertEqual(data["legacy_result"]["item_key"], "external.demo.item")
        self.assertEqual(data["item"]["item_key"], "external.demo.item")

    def test_market_async_routes_with_lane_queue_when_apply_async_available(self):
        tasks = SimpleNamespace(
            task_ingest_market=_ApplyAsyncTask("market-task-apply"),
            task_run_source_library_item=SimpleNamespace(delay=Mock(return_value=SimpleNamespace(id="source-library-task-1"))),
        )
        payload = {
            "query_terms": ["acme"],
            "max_items": 5,
            "project_key": "demo_proj",
            "async_mode": True,
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks), patch(
            "app.api.ingest.settings.agent_batch_lane_main_queue",
            "lane-main-q",
        ):
            resp = self.client.post("/api/v1/ingest/market", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        tasks.task_ingest_market.apply_async.assert_called_once()
        self.assertEqual(tasks.task_ingest_market.apply_async.call_args.kwargs["queue"], "lane-main-q")
        self.assertEqual(tasks.task_ingest_market.apply_async.call_args.kwargs["routing_key"], "agent_batch.main")

    def test_source_library_run_async_routes_with_subagent_lane_when_apply_async_available(self):
        tasks = SimpleNamespace(
            task_ingest_market=SimpleNamespace(delay=Mock(return_value=SimpleNamespace(id="market-task-1"))),
            task_run_source_library_item=_ApplyAsyncTask("source-library-task-apply"),
        )
        payload = {
            "item_key": "demo-item",
            "project_key": "demo_proj",
            "async_mode": True,
            "override_params": {"k": "v"},
        }

        with patch("app.api.ingest._tasks_module", return_value=tasks), patch(
            "app.api.ingest.settings.agent_batch_lane_subagent_queue",
            "lane-subagent-q",
        ):
            resp = self.client.post("/api/v1/ingest/source-library/run", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        tasks.task_run_source_library_item.apply_async.assert_called_once()
        self.assertEqual(tasks.task_run_source_library_item.apply_async.call_args.kwargs["queue"], "lane-subagent-q")
        self.assertEqual(tasks.task_run_source_library_item.apply_async.call_args.kwargs["routing_key"], "agent_batch.subagent")

    def test_url_single_async_task_contract_compat_with_task_result_status(self):
        tasks = _TrackedTasks()
        unique_url = f"https://example.com/post/{_unique_key('task-contract')}"
        payload = {
            "url": unique_url,
            "query_terms": ["market"],
            "idempotency_key": _unique_key("core-url-single-task-contract"),
            "strict_mode": True,
            "project_key": "demo_proj",
            "async_mode": True,
        }

        with (
            patch("app.api.ingest._tasks_module", return_value=tasks),
            installed_url_runtime() as submit_runtime,
            patch(
                "app.api.ingest._reserve_ingest_submission_db",
                side_effect=_reserve_in_fixture_memory,
            ),
            patch("app.api.ingest._complete_ingest_submission_db"),
            patch("app.api.ingest._forget_ingest_submission_db"),
        ):
            resp = self.client.post("/api/v1/ingest/url/single", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")

        data = _response_payload(body)
        self.assertIsInstance(data, dict)
        self.assertIsNone(data.get("task_id"))
        self.assertEqual(data.get("runtime_run_ref"), "runtime-run:url-single-runtime-1")
        self.assertEqual(data.get("runtime_state"), "READY")
        self.assertEqual(data.get("work_item_ids"), ["work:url-single-runtime-1:1"])
        self.assertEqual(data.get("status"), "submitted")
        self.assertTrue(data.get("async"))
        self.assertEqual(
            data.get("params"),
            {
                "url": unique_url,
                "query_terms": ["market"],
                "strict_mode": True,
            },
        )
        task_result_status = data.get("task_result_status")
        if task_result_status is not None:
            self.assertEqual(task_result_status, data.get("status"))

        self.assertEqual(submit_runtime.call_count, 1)
        request = submit_runtime.call_args.kwargs
        self.assertEqual(request["project_key"], "demo_proj")
        self.assertEqual(request["actor_id"], "api-actor-1")

    def test_url_single_async_reuses_existing_submission_for_duplicate_idempotency_key(self):
        tasks = _TrackedTasks()
        idempotency_key = _unique_key("core-url-single-idem")
        unique_url = f"https://example.com/post/{idempotency_key}"
        payload = {
            "url": unique_url,
            "query_terms": ["market"],
            "idempotency_key": idempotency_key,
            "strict_mode": True,
            "project_key": "demo_proj",
            "async_mode": True,
        }

        with (
            patch("app.api.ingest._tasks_module", return_value=tasks),
            installed_url_runtime() as submit_runtime,
            patch(
                "app.api.ingest._reserve_ingest_submission_db",
                side_effect=_reserve_in_fixture_memory,
            ),
            patch("app.api.ingest._complete_ingest_submission_db"),
            patch("app.api.ingest._forget_ingest_submission_db"),
        ):
            first_resp = self.client.post("/api/v1/ingest/url/single", json=payload)
            duplicate_resp = self.client.post("/api/v1/ingest/url/single", json=payload)

        self.assertEqual(first_resp.status_code, 200, msg=first_resp.text)
        self.assertEqual(duplicate_resp.status_code, 200, msg=duplicate_resp.text)

        first_data = _response_payload(first_resp.json())
        duplicate_data = _response_payload(duplicate_resp.json())

        self.assertIsNone(first_data.get("task_id"))
        self.assertEqual(first_data.get("runtime_run_ref"), "runtime-run:url-single-runtime-1")
        self.assertEqual(first_data.get("status"), "submitted")
        self.assertEqual(first_data.get("submission_status"), "submitted")
        self.assertEqual(first_data.get("idempotency_key"), idempotency_key)
        self.assertTrue(first_data.get("submission_id"))
        self.assertFalse(first_data.get("duplicate"))
        first_trace_chain = first_data.get("trace_chain") or {}
        self.assertEqual(first_trace_chain.get("entrypoint"), "ingest.url.single")
        self.assertEqual(first_trace_chain.get("ids", {}).get("submission_id"), first_data.get("submission_id"))
        self.assertIsNone(first_trace_chain.get("ids", {}).get("task_id"))
        self.assertEqual(first_trace_chain.get("run_order", [])[2]["status"], "not_created_at_ingest_response")
        self.assertEqual(first_trace_chain.get("fallback", {}).get("used"), "unknown")
        self.assertFalse(first_trace_chain.get("index", {}).get("real_timestamp_available"))

        self.assertIsNone(duplicate_data.get("task_id"))
        self.assertEqual(duplicate_data.get("runtime_run_ref"), "runtime-run:url-single-runtime-1")
        self.assertEqual(duplicate_data.get("status"), "submitted")
        self.assertEqual(duplicate_data.get("submission_id"), first_data.get("submission_id"))
        self.assertEqual(duplicate_data.get("idempotency_key"), idempotency_key)
        self.assertEqual(duplicate_data.get("submission_status"), "already_submitted")
        self.assertTrue(duplicate_data.get("duplicate"))
        self.assertIn("duplicate idempotency_key", duplicate_data.get("duplicate_hint") or "")
        self.assertEqual(
            duplicate_data.get("trace_chain", {}).get("ids", {}).get("submission_id"),
            first_data.get("submission_id"),
        )

        self.assertEqual(submit_runtime.call_count, 1)

    def test_url_single_async_submission_readback_is_visible_in_history(self):
        tasks = _TrackedTasks()
        idempotency_key = _unique_key("core-url-single-history-idem")
        unique_url = f"https://example.com/post/{idempotency_key}"
        payload = {
            "url": unique_url,
            "query_terms": ["market"],
            "idempotency_key": idempotency_key,
            "strict_mode": True,
            "project_key": "demo_proj",
            "async_mode": True,
        }
        legacy_job = {"id": 999, "job_type": "legacy_job", "status": "completed", "params": {"k": "v"}}

        with patch("app.api.ingest._tasks_module", return_value=tasks), patch(
            "app.api.ingest.list_jobs",
            return_value=[legacy_job],
        ), installed_url_runtime(), patch(
            "app.api.ingest._reserve_ingest_submission_db",
            side_effect=_reserve_in_fixture_memory,
        ), patch("app.api.ingest._complete_ingest_submission_db"), patch(
            "app.api.ingest._list_recent_ingest_submissions_db", return_value=[]
        ):
            first_resp = self.client.post("/api/v1/ingest/url/single", json=payload)
            duplicate_resp = self.client.post("/api/v1/ingest/url/single", json=payload)
            history_resp = self.client.get("/api/v1/ingest/history", params={"limit": 5})

        self.assertEqual(first_resp.status_code, 200, msg=first_resp.text)
        self.assertEqual(duplicate_resp.status_code, 200, msg=duplicate_resp.text)
        self.assertEqual(history_resp.status_code, 200, msg=history_resp.text)

        first_data = _response_payload(first_resp.json())
        duplicate_data = _response_payload(duplicate_resp.json())
        history_items = history_resp.json()["data"]
        readback = next(
            item for item in history_items if item.get("submission_id") == first_data.get("submission_id")
        )

        self.assertEqual(duplicate_data.get("submission_id"), first_data.get("submission_id"))
        self.assertEqual(readback.get("submission_id"), first_data.get("submission_id"))
        self.assertEqual(readback.get("idempotency_key"), idempotency_key)
        self.assertIsNone(readback.get("task_id"))
        self.assertEqual(readback.get("runtime_run_ref"), "runtime-run:url-single-runtime-1")
        self.assertEqual(readback.get("status"), "submitted")
        self.assertEqual(readback.get("task_status"), "submitted")
        self.assertEqual(readback.get("submission_status"), "submitted")
        self.assertEqual(readback.get("feedback_state"), "accepted_pending_worker")
        self.assertEqual(readback.get("registry_backend"), "memory")
        self.assertTrue(readback.get("registry_degraded"))
        self.assertEqual(readback.get("trace_id"), first_data.get("trace_id"))
        self.assertEqual(readback.get("trace_chain", {}).get("ids", {}).get("submission_id"), first_data.get("submission_id"))
        self.assertIsNone(readback.get("trace_chain", {}).get("ids", {}).get("task_id"))
        self.assertTrue(any(item.get("job_type") == "legacy_job" for item in history_items))

    def test_source_library_run_async_reuses_existing_submission_for_explicit_idempotency_key(self):
        tasks = _TrackedTasks()
        idempotency_key = _unique_key("core-source-library-idem")
        item_key = f"demo-item-idempotent-{uuid4().hex}"
        payload = {
            "item_key": item_key,
            "project_key": "demo_proj",
            "async_mode": True,
            "idempotency_key": idempotency_key,
            "override_params": {"k": "v"},
        }

        with (
            patch("app.api.ingest._tasks_module", return_value=tasks),
            patch(
                "app.api.ingest._reserve_ingest_submission_db",
                side_effect=_reserve_in_fixture_memory,
            ),
            patch("app.api.ingest._complete_ingest_submission_db"),
            patch("app.api.ingest._forget_ingest_submission_db"),
        ):
            first_resp = self.client.post("/api/v1/ingest/source-library/run", json=payload)
            duplicate_resp = self.client.post("/api/v1/ingest/source-library/run", json=payload)

        self.assertEqual(first_resp.status_code, 200, msg=first_resp.text)
        self.assertEqual(duplicate_resp.status_code, 200, msg=duplicate_resp.text)

        first_data = _response_payload(first_resp.json())
        duplicate_data = _response_payload(duplicate_resp.json())

        self.assertEqual(first_data.get("task_id"), "source-library-task-1")
        self.assertEqual(first_data.get("status"), "queued")
        self.assertEqual(first_data.get("submission_status"), "submitted")
        self.assertEqual(first_data.get("idempotency_key"), idempotency_key)
        self.assertFalse(first_data.get("duplicate"))

        self.assertEqual(duplicate_data.get("task_id"), "source-library-task-1")
        self.assertEqual(duplicate_data.get("status"), "queued")
        self.assertEqual(duplicate_data.get("submission_id"), first_data.get("submission_id"))
        self.assertEqual(duplicate_data.get("submission_status"), "already_submitted")
        self.assertTrue(duplicate_data.get("duplicate"))

        tasks.task_run_source_library_item.delay.assert_called_once()
        source_args = tasks.task_run_source_library_item.delay.call_args.args
        source_kwargs = tasks.task_run_source_library_item.delay.call_args.kwargs
        self.assertEqual(source_args[:2], (item_key, "demo_proj"))
        self.assertEqual(source_args[2]["k"], "v")
        source_readback = source_args[2]["runtime_readback"]
        self.assertEqual(source_readback["line_key"], "resource_source_library")
        self.assertTrue(source_readback["trace_id"].startswith("ingest.source_library.run:"))
        self.assertEqual(source_kwargs["trace_id"], source_readback["trace_id"])

    def test_url_single_async_reuses_persistent_registry_hit_without_dispatch(self):
        tasks = _TrackedTasks()
        payload = {
            "url": "https://example.com/post/db-duplicate",
            "query_terms": ["market"],
            "idempotency_key": "core-url-single-db-idem-1",
            "project_key": "demo_proj",
            "async_mode": True,
        }
        submission = {
            "submission_id": "sub_db_existing",
            "idempotency_key": "core-url-single-db-idem-1",
            "trigger_type": "ingest.url.single",
            "project_key": "demo_proj",
            "registry_key": "ingest.url.single:demo_proj:core-url-single-db-idem-1",
            "request_hash": "",
            "subject": {"url": "https://example.com/post/db-duplicate", "project_key": "demo_proj"},
            "response": {
                "task_id": "db-task-1",
                "status": "queued",
                "async": True,
                "params": {"url": "https://example.com/post/db-duplicate"},
            },
            "registry_backend": "db",
            "registry_degraded": False,
        }

        def reserve_existing(**kwargs):
            submission["request_hash"] = kwargs["request_hash"]
            return submission, True

        with patch("app.api.ingest._tasks_module", return_value=tasks), patch(
            "app.api.ingest._reserve_ingest_submission_db",
            side_effect=reserve_existing,
        ) as reserve_db:
            resp = self.client.post("/api/v1/ingest/url/single", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        data = _response_payload(resp.json())
        self.assertEqual(data.get("task_id"), "db-task-1")
        self.assertEqual(data.get("submission_id"), "sub_db_existing")
        self.assertEqual(data.get("submission_status"), "already_submitted")
        self.assertTrue(data.get("duplicate"))
        self.assertEqual(data.get("registry_backend"), "db")
        self.assertFalse(data.get("registry_degraded"))
        self.assertEqual(data.get("request_hash"), submission["request_hash"])
        reserve_db.assert_called_once()

    def test_url_single_async_fails_closed_when_db_unavailable(self):
        tasks = _TrackedTasks()
        idempotency_key = _unique_key("core-url-single-db-down-idem")
        unique_url = f"https://example.com/post/{idempotency_key}"
        payload = {
            "url": unique_url,
            "query_terms": ["market"],
            "idempotency_key": idempotency_key,
            "project_key": "demo_proj",
            "async_mode": True,
        }
        db_error = OperationalError("select", {}, Exception("database down"))

        with patch("app.api.ingest._tasks_module", return_value=tasks), patch(
            "app.api.ingest._reserve_ingest_submission_db",
            side_effect=db_error,
        ), patch("app.api.ingest._complete_ingest_submission_db"):
            resp = self.client.post("/api/v1/ingest/url/single", json=payload)

        self.assertEqual(resp.status_code, 503, msg=resp.text)
        error = resp.json()["detail"]["error"]
        self.assertEqual(error["code"], "UPSTREAM_ERROR")
        self.assertEqual(error["details"]["reason"], "ingest_submission_registry_unavailable")

    def test_url_single_async_rejects_same_key_with_changed_url_without_dispatch(self):
        tasks = _TrackedTasks()
        idempotency_key = _unique_key("core-url-single-hash-conflict")
        first_payload = {
            "url": "https://example.com/post/first",
            "idempotency_key": idempotency_key,
            "project_key": "demo_proj",
            "async_mode": True,
        }
        changed_payload = {**first_payload, "url": "https://example.com/post/changed"}

        with patch("app.api.ingest._tasks_module", return_value=tasks), patch(
            "app.api.ingest._reserve_ingest_submission_db",
            side_effect=_reserve_in_fixture_memory,
        ), installed_url_runtime(), patch("app.api.ingest._complete_ingest_submission_db"):
            first_resp = self.client.post("/api/v1/ingest/url/single", json=first_payload)
            conflict_resp = self.client.post("/api/v1/ingest/url/single", json=changed_payload)

        self.assertEqual(first_resp.status_code, 200, msg=first_resp.text)
        self.assertEqual(conflict_resp.status_code, 409, msg=conflict_resp.text)
        error = conflict_resp.json()["detail"]["error"]
        self.assertEqual(error["code"], "INVALID_INPUT")
        self.assertEqual(error["details"]["reason"], "idempotency_key_payload_conflict")

    def test_source_library_run_rejects_same_key_with_changed_item_without_dispatch(self):
        tasks = _TrackedTasks()
        idempotency_key = _unique_key("core-source-item-hash-conflict")
        first_payload = {
            "item_key": "fixture.item.first",
            "project_key": "demo_proj",
            "async_mode": True,
            "idempotency_key": idempotency_key,
        }
        changed_payload = {**first_payload, "item_key": "fixture.item.changed"}

        with patch("app.api.ingest._tasks_module", return_value=tasks), patch(
            "app.api.ingest._reserve_ingest_submission_db",
            side_effect=_reserve_in_fixture_memory,
        ), patch("app.api.ingest._complete_ingest_submission_db"):
            first_resp = self.client.post("/api/v1/ingest/source-library/run", json=first_payload)
            conflict_resp = self.client.post("/api/v1/ingest/source-library/run", json=changed_payload)

        self.assertEqual(first_resp.status_code, 200, msg=first_resp.text)
        self.assertEqual(conflict_resp.status_code, 409, msg=conflict_resp.text)
        self.assertEqual(
            conflict_resp.json()["detail"]["error"]["details"]["reason"],
            "idempotency_key_payload_conflict",
        )
        tasks.task_run_source_library_item.delay.assert_called_once()

    def test_source_library_run_rejects_same_key_with_changed_params_without_dispatch(self):
        tasks = _TrackedTasks()
        idempotency_key = _unique_key("core-source-params-hash-conflict")
        first_payload = {
            "item_key": "fixture.item.same",
            "project_key": "demo_proj",
            "async_mode": True,
            "idempotency_key": idempotency_key,
            "override_params": {"limit": 1},
        }
        changed_payload = {**first_payload, "override_params": {"limit": 2}}

        with patch("app.api.ingest._tasks_module", return_value=tasks), patch(
            "app.api.ingest._reserve_ingest_submission_db",
            side_effect=_reserve_in_fixture_memory,
        ), patch("app.api.ingest._complete_ingest_submission_db"):
            first_resp = self.client.post("/api/v1/ingest/source-library/run", json=first_payload)
            conflict_resp = self.client.post("/api/v1/ingest/source-library/run", json=changed_payload)

        self.assertEqual(first_resp.status_code, 200, msg=first_resp.text)
        self.assertEqual(conflict_resp.status_code, 409, msg=conflict_resp.text)
        self.assertEqual(
            conflict_resp.json()["detail"]["error"]["details"]["reason"],
            "idempotency_key_payload_conflict",
        )
        tasks.task_run_source_library_item.delay.assert_called_once()

    def test_source_library_run_reuses_persistent_registry_hit_without_dispatch(self):
        tasks = _TrackedTasks()
        payload = {
            "item_key": "demo-item-db-idempotent",
            "project_key": "demo_proj",
            "async_mode": True,
            "idempotency_key": "core-source-library-db-idem-1",
            "override_params": {"k": "v"},
        }
        submission = {
            "submission_id": "sub_source_db_existing",
            "idempotency_key": "core-source-library-db-idem-1",
            "trigger_type": "ingest.source_library.run",
            "project_key": "demo_proj",
            "registry_key": "ingest.source_library.run:demo_proj:core-source-library-db-idem-1",
            "request_hash": "",
            "subject": {"item_key": "demo-item-db-idempotent", "project_key": "demo_proj"},
            "response": {
                "task_id": "source-db-task-1",
                "status": "queued",
                "async": True,
                "params": {"item_key": "demo-item-db-idempotent"},
            },
            "registry_backend": "db",
            "registry_degraded": False,
        }

        def reserve_existing(**kwargs):
            submission["request_hash"] = kwargs["request_hash"]
            return submission, True

        with patch("app.api.ingest._tasks_module", return_value=tasks), patch(
            "app.api.ingest._reserve_ingest_submission_db",
            side_effect=reserve_existing,
        ):
            resp = self.client.post("/api/v1/ingest/source-library/run", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        data = _response_payload(resp.json())
        self.assertEqual(data.get("task_id"), "source-db-task-1")
        self.assertEqual(data.get("submission_id"), "sub_source_db_existing")
        self.assertEqual(data.get("submission_status"), "already_submitted")
        self.assertTrue(data.get("duplicate"))
        self.assertEqual(data.get("registry_backend"), "db")
        self.assertFalse(data.get("registry_degraded"))
        tasks.task_run_source_library_item.delay.assert_not_called()

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

        submission = {
            "submission_id": "sub_url_light_filter_runtime_readback",
            "idempotency_key": "core-url-single-light-filter-runtime-readback",
            "trigger_type": "ingest.url.single",
            "project_key": "demo_proj",
            "registry_key": "ingest.url.single:demo_proj:core-url-single-light-filter-runtime-readback",
            "request_hash": "c" * 64,
            "subject": {"url": "https://example.com/post/43", "project_key": "demo_proj"},
            "submission_status": "submitted",
            "status": "submitted",
            "registry_backend": "memory",
            "registry_degraded": False,
        }
        with (
            patch("app.api.ingest._tasks_module", return_value=tasks),
            installed_url_runtime() as submit_runtime,
            patch("app.api.ingest._reserve_ingest_submission", return_value=(submission, False)),
            patch("app.api.ingest._complete_ingest_submission"),
        ):
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

        self.assertEqual(submit_runtime.call_count, 1)
        submit_request = submit_runtime.call_args.kwargs
        self.assertEqual(submit_request["program"].project_key, "demo_proj")
        self.assertEqual(submit_request["trace_id"], "ingest.url.single:sub_url_light_filter_runtime_readback")
        self.assertEqual(submit_request["run_id"], "url-single-sub_url_light_filter_runtime_readback")

    def test_url_single_sync_response_contains_effective_payload_with_light_filter_fields(self):
        unique_url = f"https://example.com/post/{_unique_key('sync-light-filter')}"
        payload = {
            "url": unique_url,
            "query_terms": ["market"],
            "idempotency_key": _unique_key("core-url-single-sync"),
            "strict_mode": False,
            "project_key": "demo_proj",
            "async_mode": False,
            "light_filter_min_score": 42,
        }

        with (
            patch(
                "app.services.ingest.url_pool.ingest_url_via_source_library_frontdoor",
                return_value={"status": "degraded_success", "inserted": 0},
            ),
            patch(
                "app.api.ingest._reserve_ingest_submission_db",
                side_effect=_reserve_in_fixture_memory,
            ),
            patch("app.api.ingest._complete_ingest_submission_db"),
            patch("app.api.ingest._forget_ingest_submission_db"),
        ):
            resp = self.client.post("/api/v1/ingest/url/single", json=payload)

        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        data = _response_payload(body)
        self.assertEqual(data.get("status"), "degraded_success")
        effective_payload = data.get("effective_payload") or {}
        self.assertEqual(effective_payload.get("url"), unique_url)
        self.assertEqual(effective_payload.get("light_filter_enabled"), True)
        self.assertEqual(effective_payload.get("light_filter_min_score"), 42)
        self.assertEqual(effective_payload.get("light_filter_reject_static_assets"), True)
        self.assertEqual(effective_payload.get("light_filter_reject_search_noise_domain"), True)
        trace_chain = data.get("trace_chain") or {}
        self.assertEqual(trace_chain.get("contract_version"), "ingest_search.trace_chain.v1")
        self.assertEqual(trace_chain.get("entrypoint"), "ingest.url.single")
        self.assertEqual(trace_chain.get("fallback", {}).get("used"), True)
        self.assertEqual(trace_chain.get("fallback", {}).get("reason"), "sync_url_ingest_returned_degraded_status")
        self.assertFalse(trace_chain.get("index", {}).get("real_timestamp_available"))
        self.assertIn("no_real_index_timestamp_at_ingest_response", trace_chain.get("known_limitations") or [])


if __name__ == "__main__":
    unittest.main()
