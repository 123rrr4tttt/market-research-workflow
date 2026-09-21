#!/usr/bin/env python3
"""Focused tests for resource source lifecycle smoke artifact behavior."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_resource_source_lifecycle_smoke.py"
SPEC = importlib.util.spec_from_file_location("run_resource_source_lifecycle_smoke", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


class ResourceSourceLifecycleSmokeTestCase(unittest.TestCase):
    def make_output_path(self, name: str = "artifact.json") -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / name

    def http_result(self, status_code: int | None, payload: object | None = None, error: str | None = None) -> object:
        body = "" if payload is None else json.dumps(payload)
        return smoke.HttpResult(status_code=status_code, body=body, error=error)

    def guard(self, site_url: str, *, status: str = "passed") -> dict[str, object]:
        blocked = status == "blocked"
        return {
            "contract_version": "resource_pool.site_entry.single_source_guard.v1",
            "strict_source": True,
            "guarantee": not blocked,
            "status": status,
            "reason_code": None if not blocked else "review_rejected",
            "allowed_urls": [site_url],
            "allowed_count": 1,
            "blocked_reason": None if not blocked else "review_rejected",
            "source_ref": {"site_entry_url": site_url},
            "report_source_ref": "resource_pool.site_entry:project:10",
        }

    def lifecycle_response(self, payload: dict[str, object]) -> object:
        site_url = str(payload["site_url"])
        lifecycle_state = str(payload["lifecycle_state"])
        accepted = lifecycle_state == "accepted"
        guard = self.guard(site_url, status="passed" if accepted else "blocked")
        action = {
            "action": "collect_source_library_run",
            "enabled": accepted,
            "blocked": not accepted,
            "block_reason": None if accepted else "review_rejected",
            "payload": {
                "handler_key": "rss",
                "override_params": {
                    "site_entries": [site_url],
                    "single_source_guard": guard,
                },
            },
            "single_source_guard": guard,
        }
        data = {
            "site_url": site_url,
            "lifecycle_state": lifecycle_state,
            "review_closure": {
                "status": "ready_to_collect" if accepted else "blocked",
                "reason_code": "ready_to_collect" if accepted else "review_rejected",
                "executable": accepted,
                "site_entry_url": site_url,
                "report_source_ref": "resource_pool.site_entry:project:10",
                "single_source_guard": guard,
            },
            "next_actions": [action],
            "evidence_binding": {"report_source_ref": "resource_pool.site_entry:project:10"},
        }
        return self.http_result(200, {"status": "ok", "data": data, "error": None, "meta": {}})

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = Path(argv[argv.index("--output") + 1])
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = smoke.main(argv)
        return exit_code, json.loads(output.read_text(encoding="utf-8"))

    def test_passed_resource_source_lifecycle_flow_writes_evidence(self) -> None:
        output = self.make_output_path()

        def fake_post(url: str, payload: dict[str, object], *, timeout: float) -> object:
            if url.endswith(smoke.SITE_ENTRIES_PATH):
                data = dict(payload)
                data["id"] = 10
                data["lifecycle_state"] = "candidate"
                return self.http_result(200, {"status": "ok", "data": data, "error": None, "meta": {}})
            if url.endswith(smoke.SOURCE_LIBRARY_RUN_PATH):
                self.assertEqual(True, payload["async_mode"])
                self.assertEqual(["https://example.com/" + payload["idempotency_key"] + ".xml"], payload["override_params"]["site_entries"])  # type: ignore[index]
                return self.http_result(
                    200,
                    {
                        "status": "ok",
                        "data": {
                            "status": "queued",
                            "task_id": "source-library-task-1",
                            "trace_id": "trace-1",
                            "submission_id": "submission-1",
                        },
                        "error": None,
                        "meta": {},
                    },
                )
            raise AssertionError(f"unexpected POST {url}")

        created_urls: list[str] = []

        def fake_post_tracking(url: str, payload: dict[str, object], *, timeout: float) -> object:
            if url.endswith(smoke.SITE_ENTRIES_PATH):
                created_urls.append(str(payload["site_url"]))
            return fake_post(url, payload, timeout=timeout)

        def fake_get_tracking(url: str, *, timeout: float) -> object:
            query = smoke.parse.parse_qs(smoke.parse.urlsplit(url).query)
            self.assertEqual(["demo_proj"], query["project_key"])
            return self.http_result(
                200,
                {
                    "status": "ok",
                    "data": {"items": [{"site_url": created_urls[0], "lifecycle_state": "candidate"}]},
                    "error": None,
                    "meta": {},
                },
            )

        with (
            patch.object(smoke, "_http_post_json", side_effect=fake_post_tracking),
            patch.object(smoke, "_http_get", side_effect=fake_get_tracking),
            patch.object(smoke, "_http_patch_json", side_effect=lambda _url, payload, *, timeout: self.lifecycle_response(payload)),
        ):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    "demo_proj",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(smoke.SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual("passed", payload["status"])
        self.assertEqual([], payload["failures"])
        self.assertEqual("passed", payload["summary"]["accepted_guard_status"])
        self.assertEqual("blocked", payload["summary"]["blocked_review_status"])
        self.assertEqual("source-library-task-1", payload["summary"]["run_task_id"])
        self.assertEqual(5, payload["summary"]["passed_step_count"])
        self.assertTrue(all(step["status"] == "passed" for step in payload["steps"]))

    def test_blocked_backend_unreachable_is_not_passed_without_allow_blocked(self) -> None:
        output = self.make_output_path()
        with patch.object(
            smoke,
            "_http_post_json",
            return_value=smoke.HttpResult(status_code=None, body="", error="connection refused"),
        ):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("blocked_by_environment", payload["status"])
        self.assertEqual("blocked_by_environment", payload["steps"][0]["status"])
        self.assertIn("create_site_entry:backend_unreachable", payload["failures"])

        with patch.object(
            smoke,
            "_http_post_json",
            return_value=smoke.HttpResult(status_code=None, body="", error="connection refused"),
        ):
            allow_exit_code, allow_payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--allow-blocked",
                    "--json",
                ]
            )

        self.assertEqual(0, allow_exit_code)
        self.assertEqual("blocked_by_environment", allow_payload["status"])

    def test_missing_accepted_guard_fields_fails(self) -> None:
        output = self.make_output_path()
        created_urls: list[str] = []

        def fake_post(url: str, payload: dict[str, object], *, timeout: float) -> object:
            created_urls.append(str(payload["site_url"]))
            return self.http_result(200, {"status": "ok", "data": dict(payload), "error": None, "meta": {}})

        def fake_get(url: str, *, timeout: float) -> object:
            return self.http_result(
                200,
                {"status": "ok", "data": {"items": [{"site_url": created_urls[0]}]}, "error": None, "meta": {}},
            )

        def fake_patch(url: str, payload: dict[str, object], *, timeout: float) -> object:
            data = {
                "site_url": payload["site_url"],
                "lifecycle_state": "accepted",
                "review_closure": {"status": "ready_to_collect", "executable": True},
                "next_actions": [{"action": "collect_source_library_run", "enabled": True, "payload": {}}],
            }
            return self.http_result(200, {"status": "ok", "data": data, "error": None, "meta": {}})

        with (
            patch.object(smoke, "_http_post_json", side_effect=fake_post),
            patch.object(smoke, "_http_get", side_effect=fake_get),
            patch.object(smoke, "_http_patch_json", side_effect=fake_patch),
        ):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("failed", payload["status"])
        self.assertEqual("failed", payload["steps"][2]["status"])
        self.assertIn("accept_lifecycle:accepted.single_source_guard", payload["failures"])
        self.assertIn("accept_lifecycle:accepted.next_action.payload.override_params.site_entries", payload["failures"])


if __name__ == "__main__":
    unittest.main()
