"""W01 witnesses for typed effect failures and retained public ABI lifts."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from functorial_kit import Failure
from sqlalchemy.exc import OperationalError

from app.models import base
from app.services.llm import codex_app_server, codex_cli
from mrw_functorial_kit.core.application_failure_semantics import (
    codex_invocation_failures,
    database_session_retry_failures,
)


def test_codex_cli_failure_lift_rejects_invalid_registered_context() -> None:
    with pytest.raises(TypeError, match="requires a registered failure"):
        codex_cli._raise_codex_failure(Failure("other.family", "bad", "bad"))
    with pytest.raises(TypeError, match="context is incomplete"):
        codex_cli._raise_codex_failure(
            codex_invocation_failures.fail("prompt_required", "bad", {})
        )
    unsupported = codex_cli._codex_failure(
        "prompt_required", "bad abi", operation="test", site="test", public_exception="KeyError"
    )
    with pytest.raises(TypeError, match="only supports the retained ABI"):
        codex_cli._raise_codex_failure(unsupported)


def test_codex_app_server_failure_lift_rejects_invalid_registered_context() -> None:
    with pytest.raises(TypeError, match="requires a registered failure"):
        codex_app_server._raise_codex_failure(Failure("other.family", "bad", "bad"))
    with pytest.raises(TypeError, match="context is incomplete"):
        codex_app_server._raise_codex_failure(
            codex_invocation_failures.fail("prompt_required", "bad", {})
        )
    unsupported = codex_app_server._codex_failure(
        "prompt_required", "bad abi", operation="test", site="test", public_exception="ValueError"
    )
    with pytest.raises(TypeError, match="only supports RuntimeError ABI"):
        codex_app_server._raise_codex_failure(unsupported)


class _FakeCodexConnect:
    def __init__(self, websocket):
        self.websocket = websocket

    async def __aenter__(self):
        return self.websocket

    async def __aexit__(self, *_args):
        return None


class _FakeCodexWebSocket:
    async def send(self, _message):
        return None


def _codex_raw_core() -> codex_app_server.CodexAppServerCore:
    return codex_app_server.CodexAppServerCore(
        codex_bin_resolver=lambda: "/tmp/codex",
        workdir_resolver=lambda: "/tmp",
        disabled_features_resolver=lambda: [],
    )


def test_codex_app_server_rethrows_non_rpc_failure_signal() -> None:
    core = _codex_raw_core()
    failure = codex_app_server._codex_failure(
        "server_event_error", "server event failed", operation="test", site="test"
    )

    async def request(_ws, *, method, **_kwargs):
        if method == "initialize":
            return {}
        if method == "thread/start":
            return {"thread": {"id": "thread-1"}}
        raise codex_app_server._CodexFailureSignal(failure)

    try:
        with (
            patch.object(core, "_request", side_effect=request),
            patch(
                "app.services.llm.codex_app_server.websockets.connect",
                return_value=_FakeCodexConnect(_FakeCodexWebSocket()),
            ),
        ):
            with pytest.raises(codex_app_server._CodexFailureSignal) as raised:
                asyncio.run(
                    core._invoke_async_raw(
                        endpoint="ws://127.0.0.1:1",
                        prompt="hello",
                        model=None,
                        timeout_seconds=5,
                        reasoning_effort=None,
                    )
                )
        assert raised.value.failure is failure
    finally:
        core.shutdown()


def test_codex_app_server_maps_server_event_error() -> None:
    core = _codex_raw_core()

    async def request(_ws, *, method, **_kwargs):
        if method == "initialize":
            return {}
        if method == "thread/start":
            return {"thread": {"id": "thread-1"}}
        return {"turn": {"id": "turn-1"}}

    async def recv(_ws, *, timeout_seconds):
        return {"error": {"code": "provider_failed"}}

    try:
        with (
            patch.object(core, "_request", side_effect=request),
            patch.object(core, "_recv_json", side_effect=recv),
            patch(
                "app.services.llm.codex_app_server.websockets.connect",
                return_value=_FakeCodexConnect(_FakeCodexWebSocket()),
            ),
        ):
            with pytest.raises(codex_app_server._CodexFailureSignal) as raised:
                asyncio.run(
                    core._invoke_async_raw(
                        endpoint="ws://127.0.0.1:1",
                        prompt="hello",
                        model=None,
                        timeout_seconds=5,
                        reasoning_effort=None,
                    )
                )
        assert raised.value.failure.code == "server_event_error"
    finally:
        core.shutdown()


def test_codex_app_server_maps_empty_output() -> None:
    core = _codex_raw_core()

    async def request(_ws, *, method, **_kwargs):
        if method == "initialize":
            return {}
        if method == "thread/start":
            return {"thread": {"id": "thread-1"}}
        return {"turn": {"id": "turn-1"}}

    async def recv(_ws, *, timeout_seconds):
        return {"method": "turn/completed", "params": {"turn": {"id": "turn-1"}}}

    try:
        with (
            patch.object(core, "_request", side_effect=request),
            patch.object(core, "_recv_json", side_effect=recv),
            patch(
                "app.services.llm.codex_app_server.websockets.connect",
                return_value=_FakeCodexConnect(_FakeCodexWebSocket()),
            ),
        ):
            with pytest.raises(codex_app_server._CodexFailureSignal) as raised:
                asyncio.run(
                    core._invoke_async_raw(
                        endpoint="ws://127.0.0.1:1",
                        prompt="hello",
                        model=None,
                        timeout_seconds=5,
                        reasoning_effort=None,
                    )
                )
        assert raised.value.failure.code == "empty_output"
    finally:
        core.shutdown()


def test_codex_app_server_maps_missing_thread_id() -> None:
    core = _codex_raw_core()

    async def request(_ws, **_kwargs):
        return {}

    try:
        with patch.object(core, "_request", side_effect=request):
            with pytest.raises(codex_app_server._CodexFailureSignal) as raised:
                asyncio.run(core._ensure_thread_id(object(), model="gpt-test", timeout_seconds=5))
        assert raised.value.failure.code == "thread_id_missing"
    finally:
        core.shutdown()


def test_codex_app_server_maps_rpc_error() -> None:
    core = _codex_raw_core()

    async def recv(_ws, *, timeout_seconds):
        return {"id": 1, "error": {"code": "provider_failed"}}

    try:
        with patch.object(core, "_recv_json", side_effect=recv):
            with pytest.raises(codex_app_server._CodexFailureSignal) as raised:
                asyncio.run(
                    core._request(
                        _FakeCodexWebSocket(), request_id=1, method="initialize", params={}, timeout_seconds=5
                    )
                )
        assert raised.value.failure.code == "rpc_error"
    finally:
        core.shutdown()


def test_codex_cli_effect_failure_is_closed_and_public_prompt_abi_is_preserved() -> None:
    failure = codex_cli._invoke_codex_cli_once_effect("")
    assert isinstance(failure, Failure)
    assert failure.family == "codex.invocation.failure"
    assert failure.code == "prompt_required"
    assert (failure.context or {})["public_exception"] == "ValueError"
    assert (failure.context or {})["witness"] == "test:test_w01_effect_failures"
    with pytest.raises(ValueError, match="^prompt is required$"):
        codex_cli._invoke_codex_cli_once("")


def test_codex_cli_effect_retains_subprocess_status_without_message_parsing() -> None:
    completed = SimpleNamespace(returncode=7, stdout="", stderr="provider refused")
    with (
        patch("app.services.llm.codex_cli._resolve_codex_bin", return_value="/tmp/codex"),
        patch("app.services.llm.codex_cli.has_valid_token_sink", return_value=True),
        patch("app.services.llm.codex_cli.subprocess.run", return_value=completed),
    ):
        failure = codex_cli._invoke_codex_cli_once_effect("hello")
    assert isinstance(failure, Failure)
    assert failure.code == "cli_command_failed"
    assert (failure.context or {})["returncode"] == 7
    assert (failure.context or {})["stderr"] == "provider refused"
    with patch("app.services.llm.codex_cli._resolve_codex_bin", return_value="/tmp/codex"), patch(
        "app.services.llm.codex_cli.has_valid_token_sink", return_value=True
    ), patch("app.services.llm.codex_cli.subprocess.run", return_value=completed):
        with pytest.raises(RuntimeError, match="^codex cli failed: provider refused$"):
            codex_cli._invoke_codex_cli_once("hello")


def test_codex_app_server_effect_failure_has_cleanup_and_runtime_lift() -> None:
    core = codex_app_server.CodexAppServerCore(
        codex_bin_resolver=lambda: None,
        workdir_resolver=lambda: "/tmp",
        disabled_features_resolver=lambda: [],
    )
    try:
        failure = core._ensure_process_effect()
        assert isinstance(failure, Failure)
        assert failure.family == "codex.invocation.failure"
        assert failure.code == "cli_not_installed"
        assert (failure.context or {})["site"] == "CodexAppServerCore._ensure_process"
        with pytest.raises(RuntimeError, match="^codex cli is not installed$"):
            core._ensure_process()
    finally:
        core.shutdown()


def test_codex_async_effect_maps_timeout_to_typed_failure() -> None:
    core = codex_app_server.CodexAppServerCore(
        codex_bin_resolver=lambda: "/tmp/codex",
        workdir_resolver=lambda: "/tmp",
        disabled_features_resolver=lambda: [],
    )

    async def timed_out(**_kwargs):
        raise asyncio.TimeoutError()

    try:
        with patch.object(core, "_invoke_async_raw", side_effect=timed_out):
            failure = asyncio.run(
                core._invoke_async_effect(
                    endpoint="ws://127.0.0.1:1",
                    prompt="hello",
                    model=None,
                    timeout_seconds=5,
                    reasoning_effort=None,
                )
            )
        assert isinstance(failure, Failure)
        assert failure.code == "endpoint_timeout"
        assert (failure.context or {})["timeout_seconds"] == 5
    finally:
        core.shutdown()


def test_session_retry_effect_retains_original_exception_and_public_wrapper_reraises_it() -> None:
    class Session:
        def __init__(self) -> None:
            self.committed = False

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            pass

    class Factory:
        def __call__(self):
            session = Session()
            return _Manager(session)

    class _Manager:
        def __init__(self, session: Session) -> None:
            self.session = session

        def __enter__(self):
            return self.session

        def __exit__(self, *_args):
            return None

    original = ValueError("bad payload")

    def operation(_session):
        raise original

    failure = base.run_with_session_retry_effect(
        operation,
        session_factory=Factory(),
        max_attempts=3,
        base_backoff_ms=1,
        max_backoff_ms=1,
    )
    assert isinstance(failure, Failure)
    assert failure.family == "database.session_retry.failure"
    assert failure.code == "operation_failed"
    assert (failure.context or {})["cause"] is original
    with pytest.raises(ValueError) as raised:
        base.run_with_session_retry(
            operation,
            session_factory=Factory(),
            max_attempts=3,
            base_backoff_ms=1,
            max_backoff_ms=1,
        )
    assert raised.value is original


def test_session_retry_effect_marks_retriable_exhaustion() -> None:
    class _Manager:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def commit(self):
            pass

        def rollback(self):
            pass

    original = OperationalError("SELECT 1", {}, Exception("deadlock detected"))
    failure = base.run_with_session_retry_effect(
        lambda _session: (_ for _ in ()).throw(original),
        session_factory=lambda: _Manager(),
        max_attempts=2,
        base_backoff_ms=1,
        max_backoff_ms=1,
    )
    assert isinstance(failure, Failure)
    assert failure.code == "retry_exhausted"
    assert (failure.context or {})["cause"] is original


def test_session_retry_failure_lift_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(TypeError, match="requires a registered failure"):
        base._raise_session_retry_failure(Failure("other.family", "operation_failed", "bad"))

    incomplete = database_session_retry_failures.fail("operation_failed", "bad", {})
    with pytest.raises(TypeError, match="failure lift context is incomplete"):
        base._raise_session_retry_failure(incomplete)

    missing_cause = database_session_retry_failures.fail(
        "operation_failed",
        "bad",
        {
            "owner": "database.session_retry",
            "operation": "test",
            "site": "test",
            "public_exception": "ValueError",
            "public_message": "bad",
            "cause": None,
        },
    )
    with pytest.raises(TypeError, match="missing its original exception"):
        base._raise_session_retry_failure(missing_cause)

    original = ValueError("bad")
    complete = database_session_retry_failures.fail(
        "operation_failed",
        "bad",
        {
            "owner": "database.session_retry",
            "operation": "test",
            "site": "test",
            "public_exception": "ValueError",
            "public_message": "bad",
            "cause": original,
        },
    )
    with pytest.raises(ValueError, match="^bad$") as raised:
        base._raise_session_retry_failure(complete)
    assert raised.value is original

    monkeypatch.setattr(base, "range", lambda *_args: (), raising=False)
    with pytest.raises(RuntimeError, match="reached unexpected empty state"):
        base.run_with_session_retry_effect(lambda _session: None, session_factory=lambda: None)
