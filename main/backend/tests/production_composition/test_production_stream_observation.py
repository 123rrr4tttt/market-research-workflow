"""Focused R7 request/stream observation semantics."""

# ruff: noqa: E402, E501, TRY003

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys

import pytest
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.requests import Request


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent
for path in (str(BACKEND_ROOT), str(REPOSITORY_ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

from app import main as main_module
from app.production_observability import http as production_http


pytestmark = pytest.mark.unit


class _Metric:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.fail = fail

    def labels(self, *labels: object, **named_labels: object) -> _Metric:
        if self.fail:
            raise RuntimeError("metric unavailable")
        self.calls.append((*labels, *named_labels.values()))
        return self

    def inc(self) -> None:
        if self.fail:
            raise RuntimeError("metric unavailable")

    def observe(self, _value: float) -> None:
        if self.fail:
            raise RuntimeError("metric unavailable")


class _Controller:
    def __init__(self) -> None:
        self.observations: list[dict[str, object]] = []
        self.latches: list[dict[str, object]] = []

    def observe_http_request(self, **kwargs: object) -> None:
        self.observations.append(kwargs)

    def latch_runtime_failure(self, **kwargs: object) -> None:
        self.latches.append(kwargs)


def _request(path: str = "/api/v1/test") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 1234),
            "root_path": "",
            "state": {},
        }
    )


def _patch_metrics(monkeypatch: pytest.MonkeyPatch, *, legacy_fail: bool = False) -> None:
    monkeypatch.setattr(production_http, "REQUEST_COUNT", _Metric(fail=legacy_fail))
    monkeypatch.setattr(production_http, "REQUEST_LATENCY", _Metric(fail=legacy_fail))
    monkeypatch.setattr(production_http, "PRODUCTION_REQUEST_COUNT", _Metric())
    monkeypatch.setattr(production_http, "PRODUCTION_REQUEST_LATENCY", _Metric())


def _finalize(
    request: Request,
    response: JSONResponse | StreamingResponse,
    controller: _Controller,
    *,
    terminal_outcome: str | None = None,
) -> None:
    production_http.finalize_request_metrics(
        request=request,
        response=response,
        request_id="r7-test",
        endpoint="/api/v1/test",
        metric_labels={"domain": "demo", "route": "test", "release_version": "r7"},
        elapsed=0.01,
        production_runtime=True,
        controller=controller,
        terminal_outcome=terminal_outcome,
    )


def test_json_response_observes_once_after_finalize(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_metrics(monkeypatch)
    controller = _Controller()
    _finalize(_request(), JSONResponse({"ok": True}), controller)

    assert len(controller.observations) == 1
    assert controller.observations[0]["status_code"] == 200
    assert controller.observations[0]["terminal_outcome"] is None


@pytest.mark.asyncio
async def test_sse_observation_is_deferred_until_full_consumption(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_metrics(monkeypatch)
    controller = _Controller()
    request = _request("/api/v1/stream")
    request.state.production_stream_state = {"terminal_outcome": "success"}
    consumed = False

    async def source():
        nonlocal consumed
        yield b"data: ok\n\n"
        consumed = True

    response = StreamingResponse(source(), media_type="text/event-stream")

    async def call_next(_request: Request) -> StreamingResponse:
        return response

    monkeypatch.setattr(main_module, "_is_codex_protected_path", lambda _path: False)
    monkeypatch.setattr(
        main_module,
        "_resolve_request_project_context",
        lambda _request: ("demo", "header", False),
    )
    monkeypatch.setattr(main_module, "get_effective_project_key_enforcement_mode", lambda: "require")
    monkeypatch.setattr(main_module, "is_production_environment", lambda: True)
    monkeypatch.setattr(
        main_module,
        "production_metrics_label",
        lambda _request: {"domain": "demo", "route": "stream", "release_version": "r7"},
    )
    monkeypatch.setattr(main_module.app.state, "production_observability_r7", controller, raising=False)

    @contextmanager
    def noop_bind(_project_key: str):
        yield

    monkeypatch.setattr(main_module, "bind_project", noop_bind)
    monkeypatch.setattr(main_module, "_maybe_wrap_success_json_response", lambda _request, response, **_kwargs: response)

    wrapped = await main_module.metrics_middleware(request, call_next)
    assert controller.observations == []
    async for _chunk in wrapped.body_iterator:
        pass
    assert consumed
    assert len(controller.observations) == 1
    assert controller.observations[0]["terminal_outcome"] == "success"


def test_application_error_http_200_is_observed_as_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_metrics(monkeypatch)
    controller = _Controller()
    _finalize(
        _request(),
        JSONResponse({"status": "ok"}),
        controller,
        terminal_outcome="application_error",
    )

    assert controller.observations[0]["status_code"] == 200
    assert controller.observations[0]["terminal_outcome"] == "application_error"


@pytest.mark.asyncio
async def test_sse_iterator_failure_preserves_original_exception_and_latches(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_metrics(monkeypatch)
    controller = _Controller()
    request = _request("/api/v1/stream")

    async def source():
        yield b"data: partial\n\n"
        raise LookupError("upstream iterator failed")

    response = StreamingResponse(source(), media_type="text/event-stream")

    async def call_next(_request: Request) -> StreamingResponse:
        return response

    monkeypatch.setattr(main_module, "_is_codex_protected_path", lambda _path: False)
    monkeypatch.setattr(main_module, "_resolve_request_project_context", lambda _request: ("demo", "header", False))
    monkeypatch.setattr(main_module, "get_effective_project_key_enforcement_mode", lambda: "require")
    monkeypatch.setattr(main_module, "is_production_environment", lambda: True)
    monkeypatch.setattr(main_module, "production_metrics_label", lambda _request: {"domain": "demo", "route": "stream", "release_version": "r7"})

    @contextmanager
    def noop_bind(_project_key: str):
        yield

    monkeypatch.setattr(main_module, "bind_project", noop_bind)
    monkeypatch.setattr(main_module, "_maybe_wrap_success_json_response", lambda _request, response, **_kwargs: response)
    monkeypatch.setattr(main_module.app.state, "production_observability_r7", controller, raising=False)

    wrapped = await main_module.metrics_middleware(request, call_next)
    with pytest.raises(LookupError, match="upstream iterator failed"):
        async for _chunk in wrapped.body_iterator:
            pass

    assert len(controller.observations) == 1
    assert controller.observations[0]["terminal_outcome"] == "iterator_failure"


def test_legacy_metrics_failure_latches_without_replacing_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_metrics(monkeypatch, legacy_fail=True)
    controller = _Controller()
    response = JSONResponse({"ok": True})
    _finalize(_request(), response, controller)

    assert response.status_code == 200
    assert len(controller.observations) == 1
    assert controller.latches
    assert "legacy request metrics failed" in str(controller.latches[0]["reason"])
