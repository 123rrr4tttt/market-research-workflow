from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = [pytest.mark.contract, pytest.mark.mocked]

try:
    from fastapi import HTTPException, Query
    from fastapi.responses import JSONResponse
    from fastapi.routing import APIRoute
    from starlette.requests import Request
    from fastapi.exceptions import RequestValidationError

    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app
    from app.release_identity import RELEASE_VERSION
    from app.main import _maybe_wrap_success_json_response
    from app.contracts.responses import ApiMetaModel, ok, reset_api_context_meta, set_api_context_meta

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


if _IMPORT_ERROR is not None:
    pytest.skip(f"main core contract tests require backend dependencies: {_IMPORT_ERROR}", allow_module_level=True)


@pytest.fixture(autouse=True)
def restore_test_routes() -> Iterator[None]:
    original_routes = list(backend_app.router.routes)
    original_schema = backend_app.openapi_schema
    try:
        yield
    finally:
        backend_app.router.routes[:] = original_routes
        backend_app.openapi_schema = original_schema


def _ensure_route(path: str, endpoint, *, methods: list[str] | None = None) -> None:
    methods = methods or ["GET"]
    has_route = any(
        isinstance(route, APIRoute) and route.path == path and set(methods).issubset(route.methods or set())
        for route in backend_app.routes
    )
    if not has_route:
        backend_app.add_api_route(path, endpoint, methods=methods)


def test_app_initialization_core_contract() -> None:
    paths = {route.path for route in backend_app.routes if isinstance(route, APIRoute)}

    assert backend_app.title == "Market Intel API"
    assert backend_app.version == RELEASE_VERSION
    assert "/api/v1/health" in paths
    assert "/api/v1/health/deep" in paths
    assert "/metrics" in paths
    assert HTTPException in backend_app.exception_handlers
    assert RequestValidationError in backend_app.exception_handlers
    assert Exception in backend_app.exception_handlers


def test_success_json_response_is_wrapped_with_contract_envelope():
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/test/main-core/plain-success",
            "raw_path": b"/api/v1/test/main-core/plain-success",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
        }
    )
    response = JSONResponse(
        status_code=200,
        content={"message": "ok"},
        headers={"Cache-Control": "no-store", "X-Custom": "preserve"},
    )
    wrapped = _maybe_wrap_success_json_response(
        request,
        response,
        request_id="main-core-contract",
        trace_id="trace-main-core-contract",
        project_key="demo_proj",
    )

    assert wrapped.status_code == 200
    payload = json.loads(wrapped.body.decode("utf-8"))
    assert payload["status"] == "ok"
    assert payload["data"] == {"message": "ok"}
    assert payload["error"] is None
    assert payload["meta"]["trace_id"] == "trace-main-core-contract"
    assert payload["meta"]["project_key"] == "demo_proj"
    assert wrapped.headers.get("cache-control") == "no-store"
    assert wrapped.headers.get("x-custom") == "preserve"


def test_existing_success_envelope_meta_is_enriched_with_trace_and_project():
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/test/main-core/enveloped-success",
            "raw_path": b"/api/v1/test/main-core/enveloped-success",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
        }
    )
    response = JSONResponse(
        status_code=200,
        content={"status": "ok", "data": {"message": "ok"}, "error": None, "meta": {"trace_id": None}},
        headers={"X-Custom": "preserve"},
    )

    wrapped = _maybe_wrap_success_json_response(
        request,
        response,
        request_id="main-core-contract",
        trace_id="trace-existing-envelope",
        project_key="demo_proj",
    )

    assert wrapped.status_code == 200
    payload = json.loads(wrapped.body.decode("utf-8"))
    assert payload["status"] == "ok"
    assert payload["data"] == {"message": "ok"}
    assert payload["meta"]["trace_id"] == "trace-existing-envelope"
    assert payload["meta"]["project_key"] == "demo_proj"
    assert wrapped.headers.get("x-custom") == "preserve"


def test_existing_success_envelope_keeps_explicit_trace_and_project():
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/test/main-core/enveloped-success",
            "raw_path": b"/api/v1/test/main-core/enveloped-success",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
        }
    )
    response = JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "data": {"message": "ok"},
            "error": None,
            "meta": {"trace_id": "trace-explicit", "project_key": "project-explicit"},
        },
    )

    wrapped = _maybe_wrap_success_json_response(
        request,
        response,
        request_id="main-core-contract",
        trace_id="trace-new",
        project_key="project-new",
    )

    payload = json.loads(wrapped.body.decode("utf-8"))
    assert payload["meta"]["trace_id"] == "trace-explicit"
    assert payload["meta"]["project_key"] == "project-explicit"


def test_ok_uses_request_context_meta_by_default():
    tokens = set_api_context_meta(trace_id="trace-context", project_key="project-context")
    try:
        payload = ok({"message": "ok"})
    finally:
        reset_api_context_meta(tokens)

    assert payload["meta"]["trace_id"] == "trace-context"
    assert payload["meta"]["project_key"] == "project-context"


def test_ok_fills_missing_explicit_meta_from_request_context():
    tokens = set_api_context_meta(trace_id="trace-context", project_key="project-context")
    try:
        payload = ok({"message": "ok"}, meta=ApiMetaModel(deprecated="legacy-field"))
    finally:
        reset_api_context_meta(tokens)

    assert payload["meta"]["trace_id"] == "trace-context"
    assert payload["meta"]["project_key"] == "project-context"
    assert payload["meta"]["deprecated"] == "legacy-field"


def test_project_key_fallback_headers_and_warning(core_business_client):
    with patch("app.main._get_active_project_key_fallback", return_value="fallback_proj"):
        response = core_business_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers.get("X-Project-Key-Source") == "fallback"
    assert response.headers.get("X-Project-Key-Resolved") == "fallback_proj"
    assert response.headers.get("X-Project-Key-Warning") == "fallback_used"


def test_http_exception_with_dict_detail_is_enveloped(core_business_client, contract_headers: dict[str, str]):
    path = "/api/v1/test/main-core/http-dict-detail"

    def _raise_http_dict_detail() -> None:
        raise HTTPException(
            status_code=404,
            detail={"message": "resource missing", "resource_id": "demo-1"},
        )

    _ensure_route(path, _raise_http_dict_detail)

    response = core_business_client.get(path, headers=contract_headers)

    assert response.status_code == 404
    assert response.headers.get("x-error-code") == ErrorCode.NOT_FOUND.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["data"] is None
    assert payload["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert payload["error"]["details"]["resource_id"] == "demo-1"
    assert payload["detail"]["error"]["code"] == ErrorCode.NOT_FOUND.value


def test_http_exception_with_existing_envelope_detail_preserves_error_code(core_business_client, contract_headers: dict[str, str]):
    path = "/api/v1/test/main-core/http-envelope-detail"

    def _raise_http_enveloped_detail() -> None:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "data": None,
                "error": {
                    "code": ErrorCode.RATE_LIMITED.value,
                    "message": "too many requests",
                    "details": {},
                },
                "meta": {},
            },
        )

    _ensure_route(path, _raise_http_enveloped_detail)

    response = core_business_client.get(path, headers=contract_headers)

    assert response.status_code == 400
    assert response.headers.get("x-error-code") == ErrorCode.RATE_LIMITED.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.RATE_LIMITED.value
    assert payload["detail"]["error"]["code"] == ErrorCode.RATE_LIMITED.value


def test_unhandled_exception_for_contract_api_is_enveloped(core_business_client, contract_headers: dict[str, str]):
    path = "/api/v1/test/main-core/unhandled"

    def _raise_unhandled_contract_error() -> None:
        raise RuntimeError("upstream timeout from dependency")

    _ensure_route(path, _raise_unhandled_contract_error)

    response = core_business_client.get(path, headers=contract_headers)

    assert response.status_code == 500
    assert response.headers.get("x-error-code") == ErrorCode.UPSTREAM_ERROR.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.UPSTREAM_ERROR.value
    assert payload["detail"]["error"]["code"] == ErrorCode.UPSTREAM_ERROR.value


def test_request_validation_error_for_contract_api_is_enveloped(core_business_client, contract_headers: dict[str, str]):
    path = "/api/v1/test/main-core/validation"

    def _validation_route(limit: int = Query(..., ge=1)) -> dict[str, int]:
        return {"limit": limit}

    _ensure_route(path, _validation_route)

    response = core_business_client.get(path, params={"limit": 0}, headers=contract_headers)

    assert response.status_code == 422
    assert response.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert isinstance(payload["error"]["details"]["errors"], list)


def test_unhandled_exception_for_non_contract_api_keeps_legacy_shape(core_business_client, contract_headers: dict[str, str]):
    path = "/test/main-core/unhandled"

    def _raise_unhandled_non_contract_error() -> None:
        raise RuntimeError("boom")

    _ensure_route(path, _raise_unhandled_non_contract_error)

    response = core_business_client.get(path, headers=contract_headers)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert response.headers.get("x-error-code") is None
