from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from starlette.requests import Request
    from starlette.background import BackgroundTask
    from starlette.responses import StreamingResponse

    from fastapi.responses import JSONResponse
    from fastapi.routing import APIRoute
    from fastapi.testclient import TestClient

    import app.main as main_module
    from app.production_observability import http as production_http
    from app.api.codex_auth import codex_auth_login
    from app.api.skills import SkillInvokeRequest, invoke_skill_api
    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ApiEnvelopeGapFixesIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"api envelope integration tests require backend dependencies: {_IMPORT_ERROR}")

    @staticmethod
    def _login_request(cookies: dict[str, str] | None = None) -> Request:
        cookie_header = "; ".join(f"{name}={value}" for name, value in (cookies or {}).items())
        headers = [(b"cookie", cookie_header.encode("latin-1"))] if cookie_header else []
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/codex-auth/login",
                "headers": headers,
                "query_string": b"",
                "state": {},
            }
        )

    def test_codex_auth_login_returns_error_envelope_when_cli_login_missing(self):
        with (
            patch("app.api.codex_auth.codex_oauth_enabled", return_value=False),
            patch("app.api.codex_auth.get_session", return_value=None),
        ):
            response = codex_auth_login(request=self._login_request(), next_url=None)

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertIsNone(payload["data"])
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")
        self.assertEqual(payload["error"]["details"]["reason_code"], "codex_cli_login_required")
        self.assertEqual(payload["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(response.headers.get("x-error-code"), "INVALID_INPUT")
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_codex_auth_login_token_sink_only_does_not_shortcut_without_cookie(self):
        with (
            patch("app.api.codex_auth.codex_oauth_enabled", return_value=True),
            patch("app.api.codex_auth.has_valid_token_sink", return_value=True) as has_valid_token_sink,
            patch("app.api.codex_auth.get_session", return_value=None) as get_session,
            patch(
                "app.api.codex_auth.build_authorize_url",
                return_value="https://auth.openai.com/oauth/authorize",
            ),
        ):
            response = codex_auth_login(
                request=self._login_request(),
                next_url="http://localhost:5173",
                force_oauth=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "https://auth.openai.com/oauth/authorize")
        get_session.assert_called_once_with(None)
        has_valid_token_sink.assert_not_called()

    def test_codex_auth_login_shortcuts_with_valid_oauth_session_cookie(self):
        with (
            patch("app.api.codex_auth.codex_oauth_enabled", return_value=True),
            patch("app.api.codex_auth.has_valid_token_sink", return_value=False) as has_valid_token_sink,
            patch("app.api.codex_auth.codex_cookie_name", return_value="codex_session"),
            patch("app.api.codex_auth.get_session", return_value=object()) as get_session,
        ):
            response = codex_auth_login(
                request=self._login_request({"codex_session": "sid-1"}),
                next_url="http://localhost:5173",
                force_oauth=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "http://localhost:5173")
        get_session.assert_called_once_with("sid-1")
        has_valid_token_sink.assert_not_called()

    def test_codex_auth_login_can_force_browser_oauth(self):
        with (
            patch("app.api.codex_auth.codex_oauth_enabled", return_value=True),
            patch("app.api.codex_auth.has_valid_token_sink", return_value=True),
            patch(
                "app.api.codex_auth.get_session",
                side_effect=AssertionError("force_oauth must not read the existing session"),
            ),
            patch("app.api.codex_auth.build_authorize_url", return_value="https://auth.openai.com/oauth/authorize"),
        ):
            response = codex_auth_login(
                request=self._login_request({"codex_session": "sid-1"}),
                next_url="http://localhost:5173",
                force_oauth=True,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "https://auth.openai.com/oauth/authorize")

    def test_skills_invoke_success_returns_ok_envelope(self):
        with patch(
            "app.api.skills.invoke_skill",
            return_value={
                "skill_id": "demo.skill",
                "result": {"accepted": True},
                "trace_id": "trace-1",
                "consumer": "skills.api",
                "actor_role": "orchestration_runtime",
                "requested_permissions": ["read"],
                "owner": "qa",
                "execution_profile": "default",
                "concurrency_class": "read_only",
                "approval_policy": {"default": "optional"},
                "artifact_contract": {"primary": "memory.md"},
                "approval_request": None,
            },
        ):
            response = invoke_skill_api(
                SkillInvokeRequest(skill_id="demo.skill", payload={"query": "ping"})
            )

        self.assertEqual(response["status"], "ok")
        self.assertIsNone(response["error"])
        self.assertEqual(response["data"]["skill_id"], "demo.skill")
        self.assertEqual(response["data"]["skill_meta"]["permissions"], ["read"])
        self.assertEqual(response["data"]["skill_meta"]["execution_profile"], "default")
        self.assertEqual(response["data"]["skill_meta"]["concurrency_class"], "read_only")
        self.assertEqual(response["data"]["skill_meta"]["approval_policy"]["default"], "optional")
        self.assertEqual(response["data"]["skill_meta"]["artifact_contract"]["primary"], "memory.md")
        self.assertIsNone(response["data"]["skill_meta"]["approval_request"])

    def test_skills_invoke_approval_required_returns_error_envelope(self):
        with patch(
            "app.api.skills.invoke_skill",
            side_effect=PermissionError("skill invoke denied: demo.skill (approval_required:approval-1)"),
        ):
            response = invoke_skill_api(
                SkillInvokeRequest(
                    skill_id="demo.skill",
                    payload={},
                    session_id="as-1",
                    task_id="task-1",
                )
            )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")
        self.assertEqual(payload["error"]["details"]["category"], "skill_permission_denied")
        self.assertIn("approval_required:approval-1", payload["error"]["message"])

    def test_skills_invoke_write_conflict_returns_error_envelope(self):
        with patch(
            "app.api.skills.invoke_skill",
            side_effect=RuntimeError("skill invoke denied: demo.skill (write_set_conflict)"),
        ):
            response = invoke_skill_api(
                SkillInvokeRequest(
                    skill_id="demo.skill",
                    payload={},
                    session_id="as-1",
                    task_id="task-1",
                )
            )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")
        self.assertEqual(payload["error"]["details"]["category"], "skill_write_conflict")
        self.assertIn("write_set_conflict", payload["error"]["message"])

    def test_skills_invoke_permission_error_returns_error_envelope(self):
        with patch("app.api.skills.invoke_skill", side_effect=PermissionError("approval_granted is required")):
            response = invoke_skill_api(SkillInvokeRequest(skill_id="demo.skill", payload={}))

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")
        self.assertEqual(payload["error"]["details"]["category"], "skill_permission_denied")
        self.assertEqual(payload["detail"]["error"]["code"], "INVALID_INPUT")
        self.assertEqual(response.headers.get("x-error-code"), "INVALID_INPUT")
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.INVALID_INPUT.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.INVALID_INPUT.value)

    def test_skills_invoke_maps_generic_exception_to_error_status(self):
        with patch("app.api.skills.invoke_skill", side_effect=RuntimeError("skill not found")):
            response = invoke_skill_api(SkillInvokeRequest(skill_id="missing.skill", payload={}))

        self.assertEqual(response.status_code, 404)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "NOT_FOUND")
        self.assertEqual(payload["error"]["message"], "skill not found")
        self.assertEqual(payload["detail"]["error"]["code"], "NOT_FOUND")
        self.assertEqual(response.headers.get("x-error-code"), "NOT_FOUND")
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.NOT_FOUND.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.NOT_FOUND.value)

    def test_skills_invoke_maps_config_error_to_400(self):
        with patch("app.api.skills.invoke_skill", side_effect=RuntimeError("missing API key")):
            response = invoke_skill_api(SkillInvokeRequest(skill_id="missing.skill", payload={}))

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "CONFIG_ERROR")
        self.assertEqual(payload["error"]["message"], "missing API key")
        self.assertEqual(payload["detail"]["error"]["code"], "CONFIG_ERROR")
        self.assertEqual(response.headers.get("x-error-code"), "CONFIG_ERROR")
        self.assertEqual(payload["detail"]["error"]["code"], ErrorCode.CONFIG_ERROR.value)
        self.assertEqual(response.headers.get("x-error-code"), ErrorCode.CONFIG_ERROR.value)

    def _add_temporary_route(self, path: str, endpoint) -> None:
        backend_app.add_api_route(path, endpoint, methods=["GET"])
        route = next(
            route
            for route in backend_app.routes
            if isinstance(route, APIRoute)
            and route.path == path
            and route.endpoint is endpoint
        )
        self.addCleanup(backend_app.router.routes.remove, route)
        self.addCleanup(setattr, backend_app, "openapi_schema", backend_app.openapi_schema)

    def test_middleware_enriches_existing_success_envelope_meta(self):
        path = "/api/v1/test/envelope-gap/existing-success"

        def _existing_success_envelope() -> JSONResponse:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "ok",
                    "data": {"message": "ok"},
                    "error": None,
                    "meta": {"trace_id": None},
                },
                headers={"X-Custom": "preserve"},
            )

        self._add_temporary_route(path, _existing_success_envelope)
        client = TestClient(backend_app)
        self.addCleanup(client.close)

        response = client.get(
            path,
            headers={
                "X-Project-Key": "demo_proj",
                "X-Request-Id": "envelope-metadata-it",
                "X-Trace-Id": "envelope-trace-it",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"], {"message": "ok"})
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["meta"]["trace_id"], "envelope-trace-it")
        self.assertEqual(payload["meta"]["project_key"], "demo_proj")
        self.assertEqual(response.headers.get("x-custom"), "preserve")

    def test_middleware_preserves_duplicate_headers_and_background(self):
        client = TestClient(backend_app)
        self.addCleanup(client.close)
        cases = {
            "wrapped": {
                "payload": {"message": "ok"},
                "data": {"message": "ok"},
            },
            "enriched": {
                "payload": {
                    "status": "ok",
                    "data": {"message": "ok"},
                    "error": None,
                    "meta": {"trace_id": None, "project_key": None},
                },
                "data": {"message": "ok"},
            },
        }

        for case_name, case in cases.items():
            with self.subTest(case_name):
                path = f"/api/v1/test/envelope-gap/{case_name}-metadata"
                background_calls = []

                def _response_with_metadata() -> JSONResponse:
                    response = JSONResponse(status_code=200, content=case["payload"])
                    response.headers.append("Set-Cookie", "first=1")
                    response.headers.append("Set-Cookie", "second=2")
                    response.background = BackgroundTask(background_calls.append, "done")
                    return response

                self._add_temporary_route(path, _response_with_metadata)
                response = client.get(
                    path,
                    headers={"X-Project-Key": "demo_proj", "X-Trace-Id": f"{case_name}-trace"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["data"], case["data"])
                self.assertEqual(response.headers.get_list("set-cookie"), ["first=1", "second=2"])
                self.assertEqual(background_calls, ["done"])

    def test_middleware_materializes_json_stream_string_chunks(self):
        path = "/api/v1/test/envelope-gap/string-json-stream"

        async def _json_chunks():
            yield '{"status":"ok","data":{"message":"streamed"},'
            yield '"error":null,"meta":{"trace_id":null}}'

        def _streaming_json():
            return StreamingResponse(
                _json_chunks(),
                media_type="application/json",
                headers={"X-Custom": "preserve"},
            )

        self._add_temporary_route(path, _streaming_json)
        client = TestClient(backend_app)
        self.addCleanup(client.close)

        response = client.get(
            path,
            headers={"X-Project-Key": "demo_proj", "X-Trace-Id": "stream-trace"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"], {"message": "streamed"})
        self.assertEqual(payload["meta"]["trace_id"], "stream-trace")
        self.assertEqual(payload["meta"]["project_key"], "demo_proj")
        self.assertEqual(response.headers.get("x-custom"), "preserve")

    def test_middleware_does_not_materialize_ndjson_or_sse_streams(self):
        cases = {
            "ndjson": ("application/x-ndjson", '{"event":"one"}\n'),
            "sse": ("text/event-stream", "data: one\n\n"),
        }
        client = TestClient(backend_app)
        self.addCleanup(client.close)

        for case_name, (media_type, body) in cases.items():
            with self.subTest(case_name):
                path = f"/api/v1/test/envelope-gap/{case_name}-stream"

                async def _stream_body():
                    yield body

                def _streaming_response():
                    return StreamingResponse(_stream_body(), media_type=media_type)

                self._add_temporary_route(path, _streaming_response)
                middleware_chunks = []
                capture_middleware_chunks = {"active": False}
                original_materialize = main_module._materialize_success_json_response

                async def _observe_body(chunks):
                    async for chunk in chunks:
                        if capture_middleware_chunks["active"]:
                            middleware_chunks.append(chunk)
                        yield chunk

                async def _observe_materialize(request, response):
                    response.body_iterator = _observe_body(response.body_iterator)
                    capture_middleware_chunks["active"] = True
                    try:
                        return await original_materialize(request, response)
                    finally:
                        capture_middleware_chunks["active"] = False

                with patch(
                    "app.main._materialize_success_json_response",
                    _observe_materialize,
                ):
                    response = client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.text, body)
                self.assertTrue(
                    response.headers.get("content-type", "").startswith(media_type)
                )
                self.assertEqual(middleware_chunks, [])

    def test_controller_observation_failure_does_not_replace_json_response(self):
        path = "/api/v1/test/envelope-gap/observer-failure"

        class _FailingController:
            def observe_http_request(self, **_kwargs) -> None:
                raise RuntimeError("observer unavailable")

            def latch_runtime_failure(self, **_kwargs) -> None:
                raise RuntimeError("latch unavailable")

        def _success_payload() -> JSONResponse:
            return JSONResponse(status_code=200, content={"message": "ok"})

        self._add_temporary_route(path, _success_payload)
        old_controller = getattr(backend_app.state, "production_observability_r7", None)
        backend_app.state.production_observability_r7 = _FailingController()
        self.addCleanup(
            setattr,
            backend_app.state,
            "production_observability_r7",
            old_controller,
        )
        client = TestClient(backend_app)
        self.addCleanup(client.close)

        with (
            patch.object(main_module, "is_production_environment", return_value=True),
            patch.object(
                main_module,
                "production_metrics_label",
                return_value={"domain": "demo", "route": "test", "release_version": "test"},
            ),
        ):
            response = client.get(path, headers={"X-Project-Key": "demo_proj"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], {"message": "ok"})

    def test_stream_original_exception_survives_observer_and_latch_failure(self):
        class _FailingController:
            def observe_http_request(self, **_kwargs) -> None:
                raise RuntimeError("observer unavailable")

            def latch_runtime_failure(self, **_kwargs) -> None:
                raise RuntimeError("latch unavailable")

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/test/envelope-gap/stream-observer-failure",
                "headers": [],
                "query_string": b"",
                "state": {},
            }
        )

        async def source():
            yield b"data: partial\n\n"
            raise LookupError("upstream iterator failed")

        response = StreamingResponse(source(), media_type="text/event-stream")

        def _finalize(terminal_outcome: str) -> None:
            production_http.finalize_request_metrics(
                request=request,
                response=response,
                request_id="stream-observer-failure",
                endpoint="/api/v1/test/envelope-gap/stream-observer-failure",
                metric_labels={"domain": "demo", "route": "test", "release_version": "test"},
                elapsed=0.01,
                production_runtime=True,
                controller=_FailingController(),
                terminal_outcome=terminal_outcome,
            )

        wrapped = production_http.wrap_stream_response(
            request,
            response,
            finalize=_finalize,
        )

        async def consume() -> None:
            async for _chunk in wrapped.body_iterator:
                pass

        with self.assertRaises(LookupError, msg="upstream iterator failed"):
            asyncio.run(consume())

    def test_stream_finalizer_cancellation_is_not_swallowed(self):
        request = Request({"type": "http", "method": "GET", "path": "/stream", "state": {}})

        async def source():
            yield b"data: ok\n\n"

        response = StreamingResponse(source(), media_type="text/event-stream")

        def _cancel_finalize(_terminal_outcome: str) -> None:
            raise asyncio.CancelledError()

        wrapped = production_http.wrap_stream_response(
            request,
            response,
            finalize=_cancel_finalize,
        )

        async def consume() -> None:
            async for _chunk in wrapped.body_iterator:
                pass

        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(consume())

    def test_deep_health_output_survives_runtime_observation_and_latch_failure(self):
        class _FailingController:
            def observe_runtime_health(self, **_kwargs) -> None:
                raise RuntimeError("observer unavailable")

            def latch_runtime_failure(self, **_kwargs) -> None:
                raise RuntimeError("latch unavailable")

        class _FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, _query):
                return object()

        class _FakeEngine:
            def connect(self):
                return _FakeConnection()

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/health/deep",
                "headers": [],
                "query_string": b"",
                "state": {"request_id": "deep-health-observer-failure"},
            }
        )
        old_controller = getattr(backend_app.state, "production_observability_r7", None)
        backend_app.state.production_observability_r7 = _FailingController()
        self.addCleanup(
            setattr,
            backend_app.state,
            "production_observability_r7",
            old_controller,
        )

        with (
            patch.object(main_module, "engine", _FakeEngine()),
            patch.object(main_module, "get_db_pool_status", return_value={"size": 2, "checkedout": 0}),
            patch.object(main_module, "get_es_client", return_value=type("ES", (), {"ping": lambda _self: True})()),
            patch.object(main_module, "build_runtime_health_snapshot", side_effect=RuntimeError("snapshot unavailable")),
        ):
            result = main_module.deep_health_check(request)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["database"], "ok")
        self.assertEqual(result["database_pool"], "ok")
        self.assertEqual(result["elasticsearch"], "ok")


if __name__ == "__main__":
    unittest.main()
