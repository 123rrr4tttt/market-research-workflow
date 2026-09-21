from __future__ import annotations

import inspect
import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit
_MISSING = object()

try:
    from app.api import process as process_api
    from app.services.collect_runtime.contracts import CollectRequest, CollectResult
    from app.services.collect_runtime.display_meta import build_display_meta

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


def _fake_db_job(*, job_id: int | None = 7, payload_task_id: object = _MISSING) -> SimpleNamespace:
    params: dict[str, object] = {
        "item_key": "handler.cluster.rss",
        "project_key": "demo_proj",
        "handler_allocation": {"handler_used": "crawler_pool"},
        "rejection_breakdown": {"url_policy_low_value_endpoint": 1},
    }
    if payload_task_id is not _MISSING:
        params["task_id"] = payload_task_id
    return SimpleNamespace(
        id=job_id,
        status="running",
        job_type="source_library_run",
        params=params,
        started_at=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        error=None,
        external_provider="scrapyd",
        external_job_id="spider-job-77",
        retry_count=1,
    )


class CollectRuntimeProcessFallbackUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"collect_runtime/process unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_collect_runtime_build_display_meta_maps_new_provider_fields(self):
        request = CollectRequest(
            channel="search.market",
            project_key="demo_proj",
            query_terms=["embodied ai", "policy"],
            limit=20,
            provider="auto",
            language="en",
        )
        result = CollectResult(
            channel="search.market",
            status="running",
            inserted=3,
            updated=1,
            skipped=2,
            provider_job_id="ext-job-123",
            provider_type="scrapyd",
            provider_status="queued",
            attempt_count=2,
        )

        meta = build_display_meta(request, result, summary="市场信息采集")

        self.assertEqual(meta["channel"], "search.market")
        self.assertEqual(meta["provider"], "auto")
        self.assertEqual(meta["provider_job_id"], "ext-job-123")
        self.assertEqual(meta["provider_type"], "scrapyd")
        self.assertEqual(meta["provider_status"], "queued")
        self.assertEqual(meta["attempt_count"], 2)

    def test_process_db_job_provider_fallback_consistent_for_info_and_logs(self):
        fake_job = _fake_db_job()

        with (
            patch("app.api.process._debug_log", return_value=None),
            patch("app.api.process._resolve_db_job", return_value=fake_job),
        ):
            info_resp = process_api.get_task_info("db-job-7", project_key=None)
            logs_resp = process_api.get_task_logs("db-job-7", tail=50)

        self.assertEqual(info_resp["status"], "ok")
        info = info_resp["data"]
        self.assertEqual(info["task_id"], "db-job-7")
        self.assertEqual(info["worker"], "external-provider")
        self.assertFalse(info["ready"])
        self.assertEqual(info["external_provider"], "scrapyd")
        self.assertEqual(info["external_job_id"], "spider-job-77")
        self.assertEqual(info["progress"]["external_provider"], "scrapyd")
        self.assertEqual(info["progress"]["external_job_id"], "spider-job-77")
        self.assertEqual(info["handler_used"], "crawler_pool")
        self.assertEqual(info["skip_reason"], "url_policy_low_value_endpoint")
        self.assertIsNone(info["error_code"])

        self.assertEqual(logs_resp["status"], "ok")
        logs = logs_resp["data"]
        self.assertEqual(logs["task_id"], info["task_id"])
        self.assertEqual(logs["source"], "db")
        self.assertEqual(logs["log_file"], "db://etl_job_runs")
        self.assertIn("external_provider=scrapyd", logs["text"])
        self.assertIn("External provider task is DB-tracked", logs["text"])

    def test_process_db_job_task_id_fallback_precedence_and_empty_values(self):
        for payload_task_id in (_MISSING, None, "", "   "):
            with self.subTest(payload_task_id=payload_task_id):
                projection = process_api._db_job_projection(
                    job=_fake_db_job(payload_task_id=payload_task_id),
                    endpoint="db-job-7",
                    requested_line_key=None,
                    limit=1,
                    project_key=None,
                )
                self.assertIsNotNone(projection)
                self.assertEqual(projection["task_id"], "db-job-7")

        explicit_projection = process_api._db_job_projection(
            job=_fake_db_job(payload_task_id="provider-task-9"),
            endpoint="db-job-7",
            requested_line_key=None,
            limit=1,
            project_key=None,
        )
        self.assertIsNotNone(explicit_projection)
        self.assertEqual(explicit_projection["task_id"], "provider-task-9")

        none_id_projection = process_api._db_job_projection(
            job=_fake_db_job(job_id=None),
            endpoint="db-job-unpersisted",
            requested_line_key=None,
            limit=1,
            project_key=None,
        )
        self.assertIsNotNone(none_id_projection)
        self.assertIsNone(none_id_projection["task_id"])

        none_id_explicit_projection = process_api._db_job_projection(
            job=_fake_db_job(job_id=None, payload_task_id="provider-task-9"),
            endpoint="db-job-unpersisted",
            requested_line_key=None,
            limit=1,
            project_key=None,
        )
        self.assertIsNotNone(none_id_explicit_projection)
        self.assertEqual(none_id_explicit_projection["task_id"], "provider-task-9")

    def test_process_db_job_info_and_logs_share_fallback_for_null_and_empty_payload_ids(self):
        for payload_task_id in (_MISSING, None, ""):
            with self.subTest(payload_task_id=payload_task_id):
                fake_job = _fake_db_job(payload_task_id=payload_task_id)
                with (
                    patch("app.api.process._debug_log", return_value=None),
                    patch("app.api.process._resolve_db_job", return_value=fake_job),
                ):
                    info = process_api.get_task_info("db-job-7", project_key=None)["data"]
                    logs = process_api.get_task_logs("db-job-7", tail=50)["data"]
                self.assertEqual(info["task_id"], "db-job-7")
                self.assertEqual(logs["task_id"], info["task_id"])

    def test_process_query_descriptor_differs_from_http_resolved_none(self):
        query_default = inspect.signature(process_api.get_task_info).parameters["project_key"].default
        self.assertEqual(type(query_default).__module__, "fastapi.params")
        self.assertEqual(type(query_default).__qualname__, "Query")
        self.assertIsNotNone(query_default)
        self.assertIsNone(query_default.default)
        self.assertTrue(query_default)

        captured_bind_values: list[object] = []

        @contextmanager
        def capture_bind(value: object):
            captured_bind_values.append(value)
            yield

        fake_job = _fake_db_job()
        with (
            patch("app.api.process.bind_project", side_effect=capture_bind),
            patch("app.api.process._resolve_db_job", return_value=fake_job),
        ):
            direct_response = process_api.get_task_info("db-job-7")

        self.assertEqual(captured_bind_values, [query_default])
        self.assertEqual(direct_response["data"]["task_id"], "db-job-7")

        def forbidden_bind(_value: object):
            self.fail("HTTP-resolved project_key=None must not bind a project")

        with (
            patch("app.api.process.bind_project", side_effect=forbidden_bind),
            patch("app.api.process._resolve_db_job", return_value=fake_job),
        ):
            http_default_response = process_api.get_task_info("db-job-7", project_key=None)

        self.assertEqual(http_default_response["data"]["task_id"], "db-job-7")

    def test_process_skip_reason_prefers_legacy_gate_fields_even_with_gate_plus(self):
        payload = {
            "pre_fetch_url_gate": {"reason": "url_policy_low_value_endpoint", "blocked": True},
            "pre_write_content_gate": {"reason": "content_semantic_too_short", "blocked": False},
            "gate_plus": {
                "blocked": True,
                "blocked_stage": "pre_fetch_url_gate",
                "blocked_reason": "url_policy_low_value_endpoint",
                "checks": [
                    {"stage": "pre_fetch_url_gate", "reason": "url_policy_low_value_endpoint", "blocked": True},
                    {"stage": "pre_write_content_gate", "reason": "content_semantic_too_short", "blocked": False},
                ],
            },
        }

        reason = process_api._extract_skip_reason(payload)

        # Backward compatibility: downstream consumers still relying on legacy keys
        # should get the same reason resolution after gate_plus fields are added.
        self.assertEqual(reason, "url_policy_low_value_endpoint")


if __name__ == "__main__":
    unittest.main()
