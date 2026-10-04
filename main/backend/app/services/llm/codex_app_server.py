from __future__ import annotations

import asyncio
import atexit
from collections import deque
from dataclasses import dataclass
import hashlib
import inspect
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, NoReturn

import websockets
from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import codex_invocation_failures

from ...settings.config import settings
from ..codex_oauth import _is_safe_token_sink_path
from .codex_user_config import (
    load_user_codex_model_config,
    resolve_codex_model,
    resolve_codex_reasoning_effort,
)
from .codex_macro_binding import NativeAgentBinding


_ENDPOINT_RE = re.compile(r"ws://[^\s]+")
_ISOLATED_CODEX_HOME_RE = re.compile(
    r"(?:~|/|[A-Za-z]:\\)[^\s'\"\]\)>,;]*market-research-workflow-codex-core-home-[^\s'\"\]\)>,;]*"
)
_AUTH_JSON_PATH_RE = re.compile(
    r"(?:~|/|[A-Za-z]:\\)[^\s'\"\]\)>,;]*auth(?:_openai)?\.json"
)
_BEARER_TOKEN_RE = re.compile(r"(?i)\b(bearer)(\s*[:=]?\s*)([A-Za-z0-9._~+/=-]{12,})")
_SENSITIVE_KEY_VALUE_RE = re.compile(
    r"(?i)\b(token|access_token|refresh_token|api[_-]?key|authorization|secret|password)(\s*[:=]\s*)([^\s,;}\]]+)"
)
_TOKEN_LIKE_VALUE_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{12,}|[A-Za-z0-9_./+=-]{32,})\b"
)
_ISOLATED_CODEX_HOME_PREFIX = "market-research-workflow-codex-core-home-"
_ISOLATED_CODEX_HOME_OWNER_FILE = ".mrw-codex-home-owner.json"
_ISOLATED_CODEX_HOME_UNMARKED_JANITOR_AGE_SECONDS = 86400
_CODEX_FAILURE_CONTEXT_KEYS = frozenset(
    {"owner", "operation", "site", "public_exception", "public_message"}
)


class _CodexFailureSignal(Exception):
    def __init__(self, failure: Failure) -> None:
        self.failure = failure
        super().__init__(failure.message)


def _codex_failure(
    code: str,
    message: str,
    *,
    operation: str,
    site: str,
    public_exception: str = "RuntimeError",
    public_message: str | None = None,
    **context: Any,
) -> Failure:
    details: dict[str, Any] = {
        "owner": "codex.invocation",
        "operation": operation,
        "site": site,
        "public_exception": public_exception,
        "public_message": message if public_message is None else public_message,
        "witness": "test:test_w01_effect_failures",
    }
    details.update(context)
    return codex_invocation_failures.fail(code, message, details)


def _raise_codex_failure(failure: Failure) -> NoReturn:
    if not codex_invocation_failures.matches(failure):
        # kit:boundary owner=codex.invocation.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_codex_app_server_failure_lift_rejects_invalid_registered_context
        raise TypeError("codex invocation failure lift requires a registered failure")
    context = failure.context or {}
    if _CODEX_FAILURE_CONTEXT_KEYS - set(context):
        # kit:boundary owner=codex.invocation.failure_lift class=PROGRAMMER_DEFECT failure_family=codex.invocation.failure witness=test:test_codex_app_server_failure_lift_rejects_invalid_registered_context
        raise TypeError("codex invocation failure lift context is incomplete")
    if context.get("public_exception") != "RuntimeError":
        # kit:boundary owner=codex.invocation.failure_lift class=PROGRAMMER_DEFECT failure_family=codex.invocation.failure witness=test:test_codex_app_server_failure_lift_rejects_invalid_registered_context
        raise TypeError("codex invocation failure lift only supports RuntimeError ABI")
    # kit:boundary owner=codex.invocation.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_codex_app_server_effect_failure_has_cleanup_and_runtime_lift
    raise RuntimeError(str(context["public_message"]))


@dataclass(frozen=True)
class CodexAppServerInvocation:
    content: str
    endpoint: str
    process_id: int | None
    duration_seconds: float


@dataclass(frozen=True)
class CodexNativeAgentInvocation:
    content: str
    endpoint: str
    process_id: int | None
    duration_seconds: float
    thread_id: str
    turn_id: str
    environment_digest: str
    tool_call_count: int
    tool_calls: tuple[dict[str, Any], ...]
    capability_status: dict[str, str]


@dataclass(frozen=True)
class _CodexTurnResult:
    content: str
    thread_id: str
    turn_id: str
    tool_call_count: int
    tool_calls: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class CodexAppServerHomePreparation:
    path: str
    auth_events: list[dict[str, str]]


class CodexAppServerHomePreparationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        path: str | None,
        auth_events: list[dict[str, str]],
        cleanup_events: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.auth_events = list(auth_events)
        self.cleanup_events = list(cleanup_events or [])


class CodexAppServerCore:
    """Lifecycle manager for a mounted Codex app-server model core.

    The process is started lazily on first model use, reused across turns, and
    terminated after the configured idle TTL when no turn is active.
    """

    def __init__(
        self,
        *,
        codex_bin_resolver: Callable[[], str | None],
        workdir_resolver: Callable[[], str],
        disabled_features_resolver: Callable[[], list[str]],
        idle_ttl_seconds: int | None = None,
        start_timeout_seconds: int | None = None,
        process_factory: Callable[..., subprocess.Popen[str]] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.codex_bin_resolver = codex_bin_resolver
        self.workdir_resolver = workdir_resolver
        self.disabled_features_resolver = disabled_features_resolver
        self.idle_ttl_seconds = int(
            idle_ttl_seconds
            if idle_ttl_seconds is not None
            else getattr(settings, "codex_cli_llm_persistent_idle_ttl_seconds", 300)
        )
        self.start_timeout_seconds = int(
            start_timeout_seconds
            if start_timeout_seconds is not None
            else getattr(settings, "codex_cli_llm_persistent_start_timeout_seconds", 20)
        )
        self.process_factory = process_factory or subprocess.Popen
        self.monotonic = monotonic
        self._lock = threading.RLock()
        self._native_invoke_lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._endpoint: str | None = None
        self._stdout_thread: threading.Thread | None = None
        self._endpoint_queue: queue.Queue[str] = queue.Queue(maxsize=1)
        self._recent_logs: deque[str] = deque(maxlen=40)
        self._active_calls = 0
        self._last_used_at = 0.0
        self._invoke_count = 0
        self._start_count = 0
        self._reuse_count = 0
        self._thread_id: str | None = None
        self._thread_key: tuple[str, ...] | None = None
        self._thread_mode = "model-only"
        self._thread_start_count = 0
        self._thread_reuse_count = 0
        self._native_tool_call_count = 0
        self._active_thread_id: str | None = None
        self._active_turn_id: str | None = None
        self._last_start_duration_seconds: float | None = None
        self._last_invoke_duration_seconds: float | None = None
        self._codex_home: str | None = None
        self._codex_home_auth_events: list[dict[str, str]] = []
        self._codex_home_cleanup_events: list[dict[str, str]] = []
        self._codex_home_janitor_events: list[dict[str, str]] = (
            _cleanup_stale_isolated_codex_homes()
        )
        self._reaper_thread: threading.Thread | None = None
        self._stop_reaper = threading.Event()
        atexit.register(self.shutdown)

    def invoke(
        self,
        prompt: str,
        *,
        model: str | None = None,
        timeout_seconds: int | None = None,
        reasoning_effort: str | None = None,
    ) -> CodexAppServerInvocation:
        started_at = self.monotonic()
        endpoint = self._ensure_process()
        with self._lock:
            self._active_calls += 1
        try:
            content = asyncio.run(
                self._invoke_async(
                    endpoint=endpoint,
                    prompt=prompt,
                    model=model,
                    timeout_seconds=int(
                        timeout_seconds
                        or getattr(settings, "codex_cli_llm_timeout_seconds", 120)
                        or 120
                    ),
                    reasoning_effort=reasoning_effort,
                )
            )
        finally:
            with self._lock:
                self._active_calls = max(0, self._active_calls - 1)
                self._last_used_at = self.monotonic()
        duration_seconds = self.monotonic() - started_at
        with self._lock:
            self._invoke_count += 1
            self._last_invoke_duration_seconds = duration_seconds
        return CodexAppServerInvocation(
            content=content,
            endpoint=_redact_app_server_endpoint(endpoint),
            process_id=self._process.pid if self._process is not None else None,
            duration_seconds=duration_seconds,
        )

    def invoke_native(
        self,
        prompt: str,
        *,
        binding: NativeAgentBinding,
        model: str | None = None,
        timeout_seconds: int | None = None,
        reasoning_effort: str | None = None,
    ) -> CodexNativeAgentInvocation:
        """Run one turn in an explicit native Agent capability environment."""

        if not isinstance(binding, NativeAgentBinding):
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_api_rejects_invalid_authoring_before_process_start
            raise TypeError("binding must be a NativeAgentBinding")
        started_at = self.monotonic()
        # extraRoots and the reusable thread are process state. Keep one native
        # environment active at a time within this Core instance.
        with self._native_invoke_lock:
            endpoint = self._ensure_process()
            with self._lock:
                self._active_calls += 1
            try:
                result = asyncio.run(
                    self._invoke_native_async(
                        endpoint=endpoint,
                        prompt=prompt,
                        binding=binding,
                        model=model,
                        timeout_seconds=int(
                            timeout_seconds
                            or getattr(settings, "codex_cli_llm_timeout_seconds", 120)
                            or 120
                        ),
                        reasoning_effort=reasoning_effort,
                    )
                )
            finally:
                with self._lock:
                    self._active_calls = max(0, self._active_calls - 1)
                    self._active_thread_id = None
                    self._active_turn_id = None
                    self._last_used_at = self.monotonic()
        duration_seconds = self.monotonic() - started_at
        with self._lock:
            self._invoke_count += 1
            self._native_tool_call_count += result.tool_call_count
            self._last_invoke_duration_seconds = duration_seconds
        return CodexNativeAgentInvocation(
            content=result.content,
            endpoint=_redact_app_server_endpoint(endpoint),
            process_id=self._process.pid if self._process is not None else None,
            duration_seconds=duration_seconds,
            thread_id=result.thread_id,
            turn_id=result.turn_id,
            environment_digest=binding.environment_digest,
            tool_call_count=result.tool_call_count,
            tool_calls=result.tool_calls,
            capability_status=binding.capability_status(),
        )

    def interrupt_native_turn(
        self, *, thread_id: str, turn_id: str, timeout_seconds: int = 10
    ) -> bool:
        """Interrupt a known native turn through the app-server protocol."""

        if not str(thread_id).strip() or not str(turn_id).strip():
            # kit:boundary owner=codex.native_binding class=PROGRAMMER_DEFECT failure_family=none witness=test:test_native_api_rejects_invalid_authoring_before_process_start
            raise ValueError("thread_id and turn_id are required")
        endpoint = self._ensure_process()
        return asyncio.run(
            self._interrupt_native_turn_async(
                endpoint=endpoint,
                thread_id=str(thread_id),
                turn_id=str(turn_id),
                timeout_seconds=max(5, int(timeout_seconds)),
            )
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            process = self._process
            alive = bool(process and process.poll() is None)
            return {
                "mounted": alive,
                "endpoint": _redact_app_server_endpoint(self._endpoint)
                if alive
                else None,
                "process_id": process.pid if alive else None,
                "active_calls": self._active_calls,
                "idle_seconds": max(0.0, self.monotonic() - self._last_used_at)
                if self._last_used_at
                else None,
                "idle_ttl_seconds": self.idle_ttl_seconds,
                "invoke_count": self._invoke_count,
                "start_count": self._start_count,
                "reuse_count": self._reuse_count,
                "thread_id": self._thread_id if alive else None,
                "thread_mode": self._thread_mode if alive else None,
                "thread_reuse_enabled": bool(
                    getattr(settings, "codex_cli_llm_reuse_thread", False)
                ) or self._thread_mode == "native-agent",
                "thread_reuse_scope": (
                    "workdir_model_project_scope_capability_skill_digest"
                    if self._thread_mode == "native-agent"
                    else (
                        "workdir_model"
                        if bool(getattr(settings, "codex_cli_llm_reuse_thread", False))
                        else "disabled"
                    )
                ),
                "thread_key_hash": _thread_key_hash(self._thread_key)
                if alive
                else None,
                "thread_start_count": self._thread_start_count,
                "thread_reuse_count": self._thread_reuse_count,
                "native_tool_call_count": self._native_tool_call_count,
                "active_thread_id": self._active_thread_id,
                "active_turn_id": self._active_turn_id,
                "last_start_duration_seconds": self._last_start_duration_seconds,
                "last_invoke_duration_seconds": self._last_invoke_duration_seconds,
                "isolated_codex_home": _isolated_codex_home_evidence(self._codex_home)
                if alive
                else None,
                "isolated_codex_home_auth_events": list(self._codex_home_auth_events),
                "isolated_codex_home_cleanup_events": list(
                    self._codex_home_cleanup_events
                ),
                "isolated_codex_home_janitor_events": list(
                    self._codex_home_janitor_events
                ),
                "recent_logs": list(self._recent_logs),
            }

    def shutdown(self, *, preserve_auth_events: bool = False) -> None:
        with self._lock:
            process = self._process
            codex_home = self._codex_home
            self._process = None
            self._endpoint = None
            self._thread_id = None
            self._thread_key = None
            self._thread_mode = "model-only"
            self._active_thread_id = None
            self._active_turn_id = None
            self._active_calls = 0
            self._codex_home = None
            if not preserve_auth_events:
                self._codex_home_auth_events = []
            self._stop_reaper.set()
        if process is None:
            self._cleanup_codex_home(codex_home)
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._cleanup_codex_home(codex_home)

    def _ensure_process(self) -> str:
        outcome = self._ensure_process_effect()
        if isinstance(outcome, Failure):
            _raise_codex_failure(outcome)
        return outcome

    def _ensure_process_effect(self) -> str | Failure:
        with self._lock:
            if (
                self._process is not None
                and self._process.poll() is None
                and self._endpoint
            ):
                self._last_used_at = self.monotonic()
                self._reuse_count += 1
                self._ensure_reaper_locked()
                return self._endpoint
            stale_codex_home = self._codex_home
            self._process = None
            self._endpoint = None
            self._thread_id = None
            self._thread_key = None
            self._thread_mode = "model-only"
            self._codex_home = None
            self._codex_home_auth_events = []
            self._codex_home_cleanup_events = []
            self._cleanup_codex_home(stale_codex_home)
            while not self._endpoint_queue.empty():
                try:
                    self._endpoint_queue.get_nowait()
                except Exception:  # noqa: BLE001
                    break
            codex_bin = self.codex_bin_resolver()
            if not codex_bin:
                return _codex_failure(
                    "cli_not_installed",
                    "codex cli is not installed",
                    operation="app_server.start",
                    site="CodexAppServerCore._ensure_process",
                )
            workdir = self.workdir_resolver()
            args = [
                codex_bin,
                "app-server",
                "--listen",
                "ws://127.0.0.1:0",
            ]
            for feature in self.disabled_features_resolver():
                args.extend(["--disable", feature])
            for key, value in _app_server_config_overrides():
                args.extend(["-c", f"{key}={value}"])
            env = dict(os.environ)
            env.setdefault("NO_COLOR", "1")
            try:
                isolated_home = _prepare_isolated_codex_home()
            except CodexAppServerHomePreparationError as exc:
                self._codex_home = None
                self._codex_home_auth_events = list(exc.auth_events)
                self._codex_home_cleanup_events = list(exc.cleanup_events)
                self._recent_logs.append("codex isolated home preparation failed")
                return _codex_failure(
                    "home_preparation_failed",
                    "codex isolated home preparation failed",
                    operation="app_server.home_prepare",
                    site="CodexAppServerCore._ensure_process",
                    cause=exc,
                    auth_events=list(exc.auth_events),
                    cleanup_events=list(exc.cleanup_events),
                )
            env["CODEX_HOME"] = isolated_home.path
            self._codex_home = isolated_home.path
            self._codex_home_auth_events = list(isolated_home.auth_events)
            start_started_at = self.monotonic()
            try:
                process = self.process_factory(
                    args,
                    cwd=workdir,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                self._codex_home_auth_events.append(
                    _codex_home_auth_event(
                        Path("app-server"),
                        status="process_start_failed",
                        reason=type(exc).__name__,
                    )
                )
                self._recent_logs.append("codex app-server process start failed")
                self._cleanup_codex_home(isolated_home.path)
                self._codex_home = None
                return _codex_failure(
                    "process_start_failed",
                    "codex app-server process start failed",
                    operation="app_server.process_start",
                    site="CodexAppServerCore._ensure_process",
                    cause=exc,
                    auth_events=list(self._codex_home_auth_events),
                )
            self._process = process
            self._stdout_thread = threading.Thread(
                target=self._read_stdout,
                args=(process,),
                name="codex-app-server-core-stdout",
                daemon=True,
            )
            self._stdout_thread.start()
            self._last_used_at = self.monotonic()
            self._ensure_reaper_locked()

            try:
                endpoint = self._endpoint_queue.get(
                    timeout=max(1, self.start_timeout_seconds)
                )
            except queue.Empty as exc:
                self._codex_home_auth_events.append(
                    _codex_home_auth_event(
                        Path("app-server"),
                        status="endpoint_timeout",
                        reason="websocket_endpoint_missing",
                    )
                )
                self._recent_logs.append("codex app-server endpoint timeout")
                logs = "\n".join(list(self._recent_logs)[-8:])
                self.shutdown(preserve_auth_events=True)
                return _codex_failure(
                    "endpoint_timeout",
                    "codex app-server endpoint timeout",
                    operation="app_server.endpoint_wait",
                    site="CodexAppServerCore._ensure_process",
                    public_message=(
                        f"codex app-server did not publish a websocket endpoint within "
                        f"{self.start_timeout_seconds}s. {logs}"
                    ),
                    cause=exc,
                    timeout_seconds=self.start_timeout_seconds,
                    recent_logs=logs,
                    cleanup_events=list(self._codex_home_cleanup_events),
                )
            self._endpoint = endpoint
            self._start_count += 1
            self._last_start_duration_seconds = self.monotonic() - start_started_at
            return endpoint

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        stream = process.stdout
        if stream is None:
            return
        for raw_line in stream:
            line = str(raw_line or "").strip()
            match = _ENDPOINT_RE.search(line)
            if line:
                self._recent_logs.append(_redact_app_server_log_line(line))
            if match:
                endpoint = match.group(0)
                try:
                    self._endpoint_queue.put_nowait(endpoint)
                except queue.Full:
                    pass
        self._recent_logs.append("codex app-server stdout closed")

    def _cleanup_codex_home(self, path: str | None) -> None:
        event = _cleanup_isolated_codex_home(path)
        if not event:
            return
        with self._lock:
            self._codex_home_cleanup_events.append(event)
            self._recent_logs.append(_codex_home_cleanup_log(event))

    def _ensure_reaper_locked(self) -> None:
        if self._reaper_thread is not None and self._reaper_thread.is_alive():
            return
        self._stop_reaper.clear()
        self._reaper_thread = threading.Thread(
            target=self._reap_idle_loop,
            name="codex-app-server-core-reaper",
            daemon=True,
        )
        self._reaper_thread.start()

    def _reap_idle_loop(self) -> None:
        while not self._stop_reaper.wait(timeout=5):
            if self._reap_idle_once():
                return

    def _reap_idle_once(self) -> bool:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                self._process = None
                self._endpoint = None
                return True
            if self._active_calls > 0 or not self._last_used_at:
                return False
            if self.monotonic() - self._last_used_at < max(1, self.idle_ttl_seconds):
                return False
        self.shutdown()
        return True

    async def _invoke_async(
        self,
        *,
        endpoint: str,
        prompt: str,
        model: str | None,
        timeout_seconds: int,
        reasoning_effort: str | None,
    ) -> str:
        outcome = await self._invoke_async_effect(
            endpoint=endpoint,
            prompt=prompt,
            model=model,
            timeout_seconds=timeout_seconds,
            reasoning_effort=reasoning_effort,
        )
        if isinstance(outcome, Failure):
            _raise_codex_failure(outcome)
        return outcome

    async def _invoke_async_effect(
        self,
        *,
        endpoint: str,
        prompt: str,
        model: str | None,
        timeout_seconds: int,
        reasoning_effort: str | None,
    ) -> str | Failure:
        try:
            return await self._invoke_async_raw(
                endpoint=endpoint,
                prompt=prompt,
                model=model,
                timeout_seconds=timeout_seconds,
                reasoning_effort=reasoning_effort,
            )
        except _CodexFailureSignal as exc:
            return exc.failure
        except asyncio.TimeoutError as exc:
            return _codex_failure(
                "endpoint_timeout",
                "codex app-server request timed out",
                operation="app_server.websocket_receive",
                site="CodexAppServerCore._invoke_async",
                cause=exc,
                timeout_seconds=max(5, int(timeout_seconds or 120)),
            )
        except json.JSONDecodeError as exc:
            return _codex_failure(
                "server_event_error",
                "codex app-server emitted invalid JSON",
                operation="app_server.websocket_decode",
                site="CodexAppServerCore._invoke_async",
                cause=exc,
            )
        except websockets.exceptions.WebSocketException as exc:
            return _codex_failure(
                "rpc_error",
                "codex app-server websocket RPC failed",
                operation="app_server.websocket",
                site="CodexAppServerCore._invoke_async",
                cause=exc,
            )
        except OSError as exc:
            return _codex_failure(
                "rpc_error",
                "codex app-server websocket RPC failed",
                operation="app_server.websocket",
                site="CodexAppServerCore._invoke_async",
                cause=exc,
            )

    async def _invoke_native_async(
        self,
        *,
        endpoint: str,
        prompt: str,
        binding: NativeAgentBinding,
        model: str | None,
        timeout_seconds: int,
        reasoning_effort: str | None,
    ) -> _CodexTurnResult:
        try:
            return await self._invoke_native_async_raw(
                endpoint=endpoint,
                prompt=prompt,
                binding=binding,
                model=model,
                timeout_seconds=timeout_seconds,
                reasoning_effort=reasoning_effort,
            )
        except _CodexFailureSignal as exc:
            _raise_codex_failure(exc.failure)
        except asyncio.TimeoutError as exc:
            _raise_codex_failure(
                _codex_failure(
                    "endpoint_timeout",
                    "codex native Agent request timed out",
                    operation="app_server.native.websocket_receive",
                    site="CodexAppServerCore._invoke_native_async",
                    cause=exc,
                    timeout_seconds=max(5, int(timeout_seconds or 120)),
                )
            )
        except (json.JSONDecodeError, websockets.exceptions.WebSocketException, OSError) as exc:
            _raise_codex_failure(
                _codex_failure(
                    "rpc_error",
                    "codex native Agent websocket RPC failed",
                    operation="app_server.native.websocket",
                    site="CodexAppServerCore._invoke_native_async",
                    cause=exc,
                )
            )

    async def _initialize_socket(self, ws: Any, *, timeout_seconds: int) -> None:
        await self._request(
            ws,
            request_id=1,
            method="initialize",
            params={
                "clientInfo": {
                    "name": "market-research-workflow",
                    "version": "0.1.0",
                },
                "capabilities": {
                    "experimentalApi": True,
                    "optOutNotificationMethods": [
                        "mcpServer/startupStatus/updated",
                        "account/rateLimits/updated",
                        "thread/tokenUsage/updated",
                    ],
                },
            },
            timeout_seconds=timeout_seconds,
        )
        await ws.send(json.dumps({"method": "initialized"}, ensure_ascii=False))

    async def _invoke_async_raw(
        self,
        *,
        endpoint: str,
        prompt: str,
        model: str | None,
        timeout_seconds: int,
        reasoning_effort: str | None,
    ) -> str:
        timeout = max(5, int(timeout_seconds or 120))
        async with websockets.connect(endpoint, open_timeout=min(10, timeout)) as ws:
            await self._initialize_socket(ws, timeout_seconds=timeout)
            resolved_model = resolve_codex_model(
                explicit_model=model,
                configured_model=getattr(settings, "codex_cli_llm_model", ""),
            )
            thread_id = await self._ensure_thread_id(
                ws,
                model=str(resolved_model) if resolved_model else None,
                timeout_seconds=timeout,
                binding=None,
            )
            turn_params: dict[str, Any] = {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt, "text_elements": []}],
                "cwd": self.workdir_resolver(),
                "approvalPolicy": "never",
            }
            if resolved_model:
                turn_params["model"] = resolved_model
            effort = str(
                reasoning_effort
                or getattr(settings, "codex_cli_llm_reasoning_effort", "")
                or ""
            ).strip()
            # ``none`` is a valid UI/provider default, but it is not accepted
            # by reasoning models such as gpt-6-astra.  Omitting the field lets
            # the selected model apply its own lowest supported effort.
            if effort and effort.lower() != "none":
                turn_params["effort"] = effort
            try:
                turn_response = await self._request(
                    ws,
                    request_id=3,
                    method="turn/start",
                    params=turn_params,
                    timeout_seconds=timeout,
                )
            except _CodexFailureSignal as exc:
                if exc.failure.code != "rpc_error":
                    # kit:boundary owner=codex.invocation.effect class=PROGRAMMER_DEFECT failure_family=codex.invocation.failure witness=test:test_codex_app_server_rethrows_non_rpc_failure_signal
                    raise
                with self._lock:
                    self._thread_id = None
                    self._thread_key = None
                thread_id = await self._ensure_thread_id(
                    ws,
                    model=str(resolved_model) if resolved_model else None,
                    timeout_seconds=timeout,
                    binding=None,
                )
                turn_params["threadId"] = thread_id
                turn_response = await self._request(
                    ws,
                    request_id=4,
                    method="turn/start",
                    params=turn_params,
                    timeout_seconds=timeout,
                )
            turn_id = str(((turn_response.get("turn") or {}).get("id")) or "").strip()
            result = await self._collect_turn_result(
                ws,
                thread_id=thread_id,
                turn_id=turn_id,
                timeout_seconds=timeout,
                binding=None,
            )
            return result.content

    async def _invoke_native_async_raw(
        self,
        *,
        endpoint: str,
        prompt: str,
        binding: NativeAgentBinding,
        model: str | None,
        timeout_seconds: int,
        reasoning_effort: str | None,
    ) -> _CodexTurnResult:
        timeout = max(5, int(timeout_seconds or 120))
        async with websockets.connect(endpoint, open_timeout=min(10, timeout)) as ws:
            await self._initialize_socket(ws, timeout_seconds=timeout)
            await self._request(
                ws,
                request_id=2,
                method="skills/extraRoots/set",
                params={"extraRoots": list(binding.skill_roots)},
                timeout_seconds=timeout,
            )
            skill_listing = await self._request(
                ws,
                request_id=3,
                method="skills/list",
                params={"cwds": [self.workdir_resolver()], "forceReload": True},
                timeout_seconds=timeout,
            )
            self._verify_native_skills(binding=binding, response=skill_listing)

            resolved_model = resolve_codex_model(
                explicit_model=model,
                configured_model=getattr(settings, "codex_cli_llm_model", ""),
            )
            thread_id = await self._ensure_thread_id(
                ws,
                model=str(resolved_model) if resolved_model else None,
                timeout_seconds=timeout,
                binding=binding,
                request_id=4,
            )
            turn_params: dict[str, Any] = {
                "threadId": thread_id,
                "input": [
                    {"type": "text", "text": prompt, "text_elements": []},
                    *(skill.turn_input() for skill in binding.skills),
                ],
                "cwd": self.workdir_resolver(),
                "approvalPolicy": binding.approval_policy,
            }
            if resolved_model:
                turn_params["model"] = resolved_model
            effort = str(
                reasoning_effort
                or getattr(settings, "codex_cli_llm_reasoning_effort", "")
                or ""
            ).strip()
            if effort and effort.lower() != "none":
                turn_params["effort"] = effort
            pending_events: list[dict[str, Any]] = []
            early_tool_calls: list[dict[str, Any]] = []
            answered_calls: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}

            async def handle_early_server_request(data: dict[str, Any]) -> None:
                params = data.get("params") if isinstance(data.get("params"), dict) else {}
                await self._dispatch_server_request(
                    ws,
                    data=data,
                    binding=binding,
                    thread_id=thread_id,
                    turn_id=str(params.get("turnId") or ""),
                    observations=early_tool_calls,
                    answered_calls=answered_calls,
                )

            # A tool request can arrive before the turn/start RPC response.
            # Never retry an unknown native turn/start outcome: its tools may
            # already have run.
            try:
                turn_response = await self._request(
                    ws,
                    request_id=5,
                    method="turn/start",
                    params=turn_params,
                    timeout_seconds=timeout,
                    pending_events=pending_events,
                    server_request_handler=handle_early_server_request,
                )
            except _CodexFailureSignal as exc:
                # A managed app-server can restart independently of the Python
                # process (idle reaper, daemon replacement, or container
                # recovery).  Native bindings intentionally reuse a thread id,
                # but that id is scoped to the app-server process.  Recreate
                # the thread once when the server explicitly reports that the
                # cached id no longer exists; do not retry arbitrary turn
                # failures because a turn may already have executed tools.
                failure_message = str(
                    (exc.failure.context or {}).get("public_message") or ""
                )
                if "thread not found" not in failure_message.lower():
                    # kit:boundary owner=codex.invocation.effect class=SHELL_BOUNDARY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_native_rpc_failure_lift_preserves_failure_and_public_abi
                    raise
                with self._lock:
                    self._thread_id = None
                    self._thread_key = None
                thread_id = await self._ensure_thread_id(
                    ws,
                    model=str(resolved_model) if resolved_model else None,
                    timeout_seconds=timeout,
                    binding=binding,
                    request_id=6,
                )
                turn_params["threadId"] = thread_id
                turn_response = await self._request(
                    ws,
                    request_id=7,
                    method="turn/start",
                    params=turn_params,
                    timeout_seconds=timeout,
                    pending_events=pending_events,
                    server_request_handler=handle_early_server_request,
                )
            turn_id = str(((turn_response.get("turn") or {}).get("id")) or "").strip()
            if not turn_id:
                # kit:boundary owner=codex.invocation.effect class=SHELL_BOUNDARY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_native_rpc_failure_lift_preserves_failure_and_public_abi
                raise _CodexFailureSignal(
                    _codex_failure(
                        "server_event_error",
                        "codex app-server turn/start returned no turn id",
                        operation="app_server.native.turn_start",
                        site="CodexAppServerCore._invoke_native_async_raw",
                    )
                )
            with self._lock:
                self._active_thread_id = thread_id
                self._active_turn_id = turn_id
            return await self._collect_turn_result(
                ws,
                thread_id=thread_id,
                turn_id=turn_id,
                timeout_seconds=timeout,
                binding=binding,
                pending_events=pending_events,
                initial_tool_calls=early_tool_calls,
                answered_calls=answered_calls,
            )

    @staticmethod
    def _verify_native_skills(
        *, binding: NativeAgentBinding, response: dict[str, Any]
    ) -> None:
        observed: set[tuple[str, str]] = set()
        for group in response.get("data") or []:
            if not isinstance(group, dict):
                continue
            for skill in group.get("skills") or []:
                if isinstance(skill, dict) and bool(skill.get("enabled", True)):
                    observed.add(
                        (
                            str(skill.get("name") or ""),
                            str(Path(str(skill.get("path") or "")).expanduser().resolve()),
                        )
                    )
        expected = {(skill.name, skill.path) for skill in binding.skills}
        missing = sorted(expected - observed)
        if missing:
            # kit:boundary owner=codex.invocation.effect class=SHELL_BOUNDARY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_native_rpc_failure_lift_preserves_failure_and_public_abi
            raise _CodexFailureSignal(
                _codex_failure(
                    "server_event_error",
                    "codex app-server did not expose the bound native skill",
                    operation="app_server.native.skills_list",
                    site="CodexAppServerCore._verify_native_skills",
                    missing_skills=missing,
                )
            )

    async def _collect_turn_result(
        self,
        ws: Any,
        *,
        thread_id: str,
        turn_id: str,
        timeout_seconds: int,
        binding: NativeAgentBinding | None,
        pending_events: list[dict[str, Any]] | None = None,
        initial_tool_calls: list[dict[str, Any]] | None = None,
        answered_calls: dict[str, tuple[dict[str, Any], dict[str, Any]]] | None = None,
    ) -> _CodexTurnResult:
        chunks: list[str] = []
        completed_text = ""
        tool_calls = list(initial_tool_calls or [])
        tool_call_count = len(tool_calls)
        answered_calls = answered_calls if answered_calls is not None else {}
        queued_events = deque(pending_events or [])
        while True:
            data = (
                queued_events.popleft()
                if queued_events
                else await self._recv_json(ws, timeout_seconds=timeout_seconds)
            )
            if data.get("method") and "id" in data:
                handled_tool = await self._dispatch_server_request(
                    ws,
                    data=data,
                    binding=binding,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    observations=tool_calls if binding is not None else None,
                    answered_calls=answered_calls if binding is not None else None,
                )
                tool_call_count += int(handled_tool)
                continue
            if data.get("method") == "item/agentMessage/delta":
                params = data.get("params") if isinstance(data.get("params"), dict) else {}
                if not turn_id or params.get("turnId") == turn_id:
                    chunks.append(str(params.get("delta") or ""))
            elif data.get("method") == "item/completed":
                params = data.get("params") if isinstance(data.get("params"), dict) else {}
                item = params.get("item") if isinstance(params.get("item"), dict) else {}
                if item.get("type") == "agentMessage":
                    completed_text = str(item.get("text") or completed_text or "")
            elif data.get("method") == "turn/completed":
                params = data.get("params") if isinstance(data.get("params"), dict) else {}
                turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
                if not turn_id or turn.get("id") == turn_id:
                    if binding is not None:
                        status = str(turn.get("status") or "")
                        if params.get("threadId") != thread_id or status != "completed":
                            # kit:boundary owner=codex.invocation.effect class=SHELL_BOUNDARY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_native_failed_turn_does_not_return_agent_text
                            raise _CodexFailureSignal(
                                _codex_failure(
                                    "server_event_error",
                                    "codex native Agent turn did not complete successfully",
                                    operation="app_server.native.turn_completed",
                                    site="CodexAppServerCore._collect_turn_result",
                                    thread_id=thread_id,
                                    turn_id=turn_id,
                                    turn_status=status,
                                    turn_error=turn.get("error"),
                                )
                            )
                    break
            elif data.get("error"):
                # kit:boundary owner=codex.invocation.effect class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_codex_app_server_maps_server_event_error
                raise _CodexFailureSignal(
                    _codex_failure(
                        "server_event_error",
                        "codex app-server reported an error event",
                        operation="app_server.event_stream",
                        site="CodexAppServerCore._collect_turn_result",
                        server_error=data.get("error"),
                    )
                )
        content = (completed_text or "".join(chunks)).strip()
        if not content:
            # kit:boundary owner=codex.invocation.effect class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_codex_app_server_maps_empty_output
            raise _CodexFailureSignal(
                _codex_failure(
                    "empty_output",
                    "codex app-server returned empty output",
                    operation="app_server.response_decode",
                    site="CodexAppServerCore._collect_turn_result",
                )
            )
        return _CodexTurnResult(
            content, thread_id, turn_id, tool_call_count, tuple(tool_calls)
        )

    async def _dispatch_server_request(
        self,
        ws: Any,
        *,
        data: dict[str, Any],
        binding: NativeAgentBinding | None,
        thread_id: str,
        turn_id: str,
        observations: list[dict[str, Any]] | None = None,
        answered_calls: dict[str, tuple[dict[str, Any], dict[str, Any]]] | None = None,
    ) -> bool:
        request_id = data.get("id")
        method = str(data.get("method") or "")
        params = data.get("params") if isinstance(data.get("params"), dict) else {}
        if method != "item/tool/call" or binding is None:
            await ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32601,
                            "message": f"server request not supported by this binding: {method}",
                        },
                    },
                    ensure_ascii=False,
                )
            )
            return False

        namespace_value = params.get("namespace")
        namespace = str(namespace_value) if namespace_value is not None else None
        call_id = str(params.get("callId") or "").strip()
        if answered_calls is not None and call_id in answered_calls:
            prior_params, prior_result = answered_calls[call_id]
            replay_result = (
                prior_result
                if prior_params == params
                else {
                    "contentItems": [
                        {
                            "type": "inputText",
                            "text": "dynamic tool call id reused with different arguments",
                        }
                    ],
                    "success": False,
                }
            )
            await ws.send(
                json.dumps(
                    {"jsonrpc": "2.0", "id": request_id, "result": replay_result},
                    ensure_ascii=False,
                )
            )
            return False
        tool = binding.find_tool(namespace=namespace, name=str(params.get("tool") or ""))
        call_matches = (
            bool(call_id)
            and request_id is not None
            and params.get("threadId") == thread_id
            and params.get("turnId") == turn_id
            and isinstance(params.get("arguments"), dict)
        )
        success = bool(tool and call_matches)
        if success and tool is not None:
            try:
                # Dynamic Core handlers are ordinary synchronous project
                # services in the existing runtime.  Run them off the
                # app-server event loop so a mounted tool may legitimately
                # invoke another synchronous/async-capable Core service (for
                # example material extraction calling the persistent model)
                # without nesting ``asyncio.run`` inside the websocket loop.
                if inspect.iscoroutinefunction(tool.handler):
                    result = await tool.handler(params["arguments"])
                else:
                    result = await asyncio.to_thread(tool.handler, params["arguments"])
                    if inspect.isawaitable(result):
                        result = await result
                output = result if isinstance(result, str) else json.dumps(
                    result, ensure_ascii=False, sort_keys=True, default=str
                )
            except Exception as exc:  # handler failure is returned to the native turn
                success = False
                output = f"{type(exc).__name__}: {exc}"
        else:
            output = "dynamic tool call rejected: unknown tool, scope mismatch, or invalid arguments"
        response = {
            "contentItems": [{"type": "inputText", "text": output}],
            "success": success,
        }
        await ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": response,
                },
                ensure_ascii=False,
            )
        )
        if answered_calls is not None and call_id:
            answered_calls[call_id] = (dict(params), response)
        if observations is not None:
            observations.append(
                {
                    "call_id": call_id,
                    "namespace": namespace,
                    "tool": str(params.get("tool") or ""),
                    "success": success,
                }
            )
        return True

    async def _interrupt_native_turn_async(
        self,
        *,
        endpoint: str,
        thread_id: str,
        turn_id: str,
        timeout_seconds: int,
    ) -> bool:
        async with websockets.connect(
            endpoint, open_timeout=min(10, timeout_seconds)
        ) as ws:
            await self._initialize_socket(ws, timeout_seconds=timeout_seconds)
            await self._request(
                ws,
                request_id=2,
                method="turn/interrupt",
                params={"threadId": thread_id, "turnId": turn_id},
                timeout_seconds=timeout_seconds,
            )
        return True

    async def _ensure_thread_id(
        self,
        ws: Any,
        *,
        model: str | None,
        timeout_seconds: int,
        binding: NativeAgentBinding | None = None,
        request_id: int = 2,
    ) -> str:
        workdir = self.workdir_resolver()
        if binding is None:
            thread_key = (workdir, str(model or ""))
            reuse_thread = bool(getattr(settings, "codex_cli_llm_reuse_thread", False))
        else:
            thread_key = (
                "native-agent",
                workdir,
                str(model or ""),
                binding.project_key,
                binding.scope_id,
                binding.environment_digest,
            )
            reuse_thread = True
        if reuse_thread:
            with self._lock:
                if self._thread_id and self._thread_key == thread_key:
                    self._thread_reuse_count += 1
                    return self._thread_id
        if binding is None:
            thread_params: dict[str, Any] = {
                "cwd": workdir,
                "sandbox": "read-only",
                "approvalPolicy": "never",
                "ephemeral": True,
                "baseInstructions": (
                    "You are a mounted Codex model core for another application. "
                    "Follow the user's prompt exactly. Do not run shell commands, edit files, or call tools. "
                    "If the prompt requires JSON, return only JSON."
                ),
                "developerInstructions": "Act only as a chat/model provider for this prompt. Keep answers concise and return promptly.",
            }
        else:
            thread_params = {
                "cwd": workdir,
                "sandbox": binding.sandbox,
                "approvalPolicy": binding.approval_policy,
                "ephemeral": binding.ephemeral,
                "baseInstructions": binding.base_instructions,
                "developerInstructions": binding.developer_instructions,
                "dynamicTools": binding.dynamic_tool_specs(),
            }
        if model:
            thread_params["model"] = model
        thread_response = await self._request(
            ws,
            request_id=request_id,
            method="thread/start",
            params=thread_params,
            timeout_seconds=timeout_seconds,
        )
        thread_id = str(((thread_response.get("thread") or {}).get("id")) or "").strip()
        if not thread_id:
            # kit:boundary owner=codex.invocation.effect class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_codex_app_server_maps_missing_thread_id
            raise _CodexFailureSignal(
                _codex_failure(
                    "thread_id_missing",
                    "codex app-server thread/start returned no thread id",
                    operation="app_server.thread_start",
                    site="CodexAppServerCore._ensure_thread_id",
                )
            )
        with self._lock:
            if reuse_thread:
                self._thread_id = thread_id
                self._thread_key = thread_key
                self._thread_mode = "native-agent" if binding is not None else "model-only"
            else:
                self._thread_id = None
                self._thread_key = None
                self._thread_mode = "model-only"
            self._thread_start_count += 1
        return thread_id

    async def _request(
        self,
        ws: Any,
        *,
        request_id: int,
        method: str,
        params: dict[str, Any],
        timeout_seconds: int,
        pending_events: list[dict[str, Any]] | None = None,
        server_request_handler: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        await ws.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                },
                ensure_ascii=False,
                default=str,
            )
        )
        while True:
            data = await self._recv_json(ws, timeout_seconds=timeout_seconds)
            if data.get("method") and "id" in data and server_request_handler:
                await server_request_handler(data)
                continue
            if data.get("id") != request_id:
                if pending_events is not None and data.get("method"):
                    pending_events.append(data)
                continue
            if data.get("error"):
                # kit:boundary owner=codex.invocation.effect class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_codex_app_server_maps_rpc_error
                raise _CodexFailureSignal(
                    _codex_failure(
                        "rpc_error",
                        f"codex app-server {method} failed",
                        operation=f"app_server.rpc.{method}",
                        site="CodexAppServerCore._request",
                        public_message=f"codex app-server {method} failed: {data.get('error')}",
                        rpc_error=data.get("error"),
                    )
                )
            result = data.get("result")
            return result if isinstance(result, dict) else {}

    @staticmethod
    async def _recv_json(ws: Any, *, timeout_seconds: int) -> dict[str, Any]:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(5, timeout_seconds))
        data = json.loads(str(raw or "{}"))
        return data if isinstance(data, dict) else {}


_persistent_core: CodexAppServerCore | None = None
_persistent_core_lock = threading.Lock()


def get_persistent_codex_core(
    *,
    codex_bin_resolver: Callable[[], str | None],
    workdir_resolver: Callable[[], str],
    disabled_features_resolver: Callable[[], list[str]],
) -> CodexAppServerCore:
    global _persistent_core
    with _persistent_core_lock:
        if _persistent_core is None:
            _persistent_core = CodexAppServerCore(
                codex_bin_resolver=codex_bin_resolver,
                workdir_resolver=workdir_resolver,
                disabled_features_resolver=disabled_features_resolver,
            )
        return _persistent_core


def reset_persistent_codex_core_for_tests() -> None:
    global _persistent_core
    with _persistent_core_lock:
        core = _persistent_core
        _persistent_core = None
    if core is not None:
        core.shutdown()


def codex_app_server_status() -> dict[str, Any]:
    with _persistent_core_lock:
        core = _persistent_core
    if core is None:
        return {
            "mounted": False,
            "idle_ttl_seconds": int(
                getattr(settings, "codex_cli_llm_persistent_idle_ttl_seconds", 300)
            ),
        }
    return core.status()


def _app_server_config_overrides() -> list[tuple[str, str]]:
    return [
        ("features.memories", "false"),
        ("features.apps", "false"),
        ("features.plugins", "false"),
        ("features.multi_agent", "false"),
        ("features.tool_search", "false"),
        ("features.tool_suggest", "false"),
        ("features.browser_use", "false"),
        ("web_search", '"disabled"'),
        ("mcp_servers", "{}"),
        ("plugins", "{}"),
        ("apps._default.enabled", "false"),
        ("analytics.enabled", "false"),
        ("otel.exporter", '"none"'),
        ("otel.trace_exporter", '"none"'),
        ("otel.metrics_exporter", '"none"'),
        ("project_doc_max_bytes", "0"),
        ("skills.bundled.enabled", "false"),
    ]


def _cleanup_stale_isolated_codex_homes(
    *,
    tempdir: Path | None = None,
    now: float | None = None,
    max_unmarked_age_seconds: int = _ISOLATED_CODEX_HOME_UNMARKED_JANITOR_AGE_SECONDS,
) -> list[dict[str, str]]:
    root = Path(tempdir or tempfile.gettempdir())
    current_time = float(now if now is not None else time.time())
    events: list[dict[str, str]] = []
    try:
        candidates = sorted(root.glob(f"{_ISOLATED_CODEX_HOME_PREFIX}*"))
    except OSError as exc:
        return [
            {
                "target": "isolated_codex_home_janitor",
                "status": "scan_failed",
                "reason": type(exc).__name__,
            }
        ]

    for candidate in candidates:
        if candidate.parent != root or candidate.is_symlink() or not candidate.is_dir():
            continue
        stale_reason = _isolated_codex_home_stale_reason(
            candidate,
            now=current_time,
            max_unmarked_age_seconds=max_unmarked_age_seconds,
        )
        if not stale_reason:
            continue
        cleanup_event = _cleanup_isolated_codex_home(str(candidate))
        if cleanup_event:
            events.append(
                {
                    "target": "isolated_codex_home_janitor",
                    "status": "stale_cleanup_failed",
                    "reason": cleanup_event.get("reason", "unknown"),
                }
            )
        else:
            events.append(
                {
                    "target": "isolated_codex_home_janitor",
                    "status": "stale_cleanup_succeeded",
                    "reason": stale_reason,
                }
            )
    return events


def _isolated_codex_home_stale_reason(
    path: Path,
    *,
    now: float,
    max_unmarked_age_seconds: int,
) -> str | None:
    marker = path / _ISOLATED_CODEX_HOME_OWNER_FILE
    payload: dict[str, Any] | None = None
    if marker.exists() and marker.is_file() and not marker.is_symlink():
        try:
            loaded = json.loads(marker.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:  # noqa: BLE001
            payload = None

    if payload is not None:
        pid = _safe_positive_int(payload.get("pid"))
        if pid is not None and not _process_is_alive(pid):
            return "owner_process_dead"
        return None

    try:
        age_seconds = max(0.0, now - path.stat().st_mtime)
    except OSError:
        return None
    if age_seconds >= max(0, int(max_unmarked_age_seconds)):
        return "unmarked_expired"
    return None


def _write_isolated_codex_home_owner(path: Path) -> None:
    payload = {
        "schema_version": "mrw.codex_app_server_home_owner.v1",
        "pid": os.getpid(),
        "created_at": int(time.time()),
    }
    try:
        (path / _ISOLATED_CODEX_HOME_OWNER_FILE).write_text(
            json.dumps(payload, sort_keys=True), encoding="utf-8"
        )
        (path / _ISOLATED_CODEX_HOME_OWNER_FILE).chmod(0o600)
    except OSError:
        pass


def _isolated_codex_home_evidence(path: str | None) -> dict[str, Any] | None:
    raw = str(path or "").strip()
    if not raw:
        return None
    home = Path(raw)
    marker = home / _ISOLATED_CODEX_HOME_OWNER_FILE
    evidence: dict[str, Any] = {
        "namespace": "isolated_codex_home",
        "path_hash": _stable_secret_hash(raw, prefix="codex_home"),
        "owner_marker_present": False,
    }
    if marker.exists() and marker.is_file() and not marker.is_symlink():
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload = {}
        if isinstance(payload, dict):
            owner_pid = _safe_positive_int(payload.get("pid"))
            evidence["owner_marker_present"] = True
            evidence["owner_pid"] = owner_pid
            evidence["owner_matches_process"] = owner_pid == os.getpid()
            created_at = _safe_positive_int(payload.get("created_at"))
            if created_at is not None:
                evidence["created_at"] = created_at
    return evidence


def _process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _safe_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _thread_key_hash(thread_key: tuple[str, ...] | None) -> str | None:
    if thread_key is None:
        return None
    return _stable_secret_hash(
        json.dumps(list(thread_key), sort_keys=True), prefix="thread_key"
    )


def _stable_secret_hash(value: str, *, prefix: str) -> str:
    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _prepare_isolated_codex_home() -> CodexAppServerHomePreparation:
    """Create a minimal CODEX_HOME for backend-owned app-server mounts.

    The desktop/global Codex config can contain user MCP servers such as
    Storybook or browser tooling. The backend AgentCore model mount should not
    inherit those services because an unavailable local MCP endpoint can make a
    logically mounted model core behave as partially mounted. We copy auth
    files only and provide a small config with MCP/plugins/apps disabled.
    """

    root = Path(tempfile.mkdtemp(prefix=_ISOLATED_CODEX_HOME_PREFIX))
    try:
        root.chmod(0o700)
    except OSError:
        pass
    _write_isolated_codex_home_owner(root)

    auth_events: list[dict[str, str]] = []
    for raw_path in (
        getattr(settings, "codex_cli_auth_path", "~/.codex/auth.json"),
        getattr(settings, "codex_oauth_token_sink_path", "~/.codex/auth_openai.json"),
    ):
        source = Path(str(raw_path or "")).expanduser()
        if not source.is_absolute():
            source = Path.cwd() / source
        if not _is_safe_token_sink_path(source, for_write=False):
            auth_events.append(
                _codex_home_auth_event(source, status="unsafe", reason="path_unsafe")
            )
            continue
        if not source.exists() or not source.is_file():
            auth_events.append(
                _codex_home_auth_event(
                    source, status="missing", reason="source_missing"
                )
            )
            continue
        destination = root / source.name
        try:
            shutil.copy2(source, destination)
            destination.chmod(0o600)
            auth_events.append(_codex_home_auth_event(source, status="copied"))
        except OSError as exc:
            auth_events.append(
                _codex_home_auth_event(
                    source, status="copy_failed", reason=type(exc).__name__
                )
            )
            continue

    # Reuse the local Codex model catalog when one is available.  The
    # isolated app-server otherwise performs a fresh catalog request during
    # startup; in the backend container that request can time out even though
    # the regular Codex CLI can already run with the mounted auth.json.
    cache_root = Path(
        os.environ.get(
            "CODEX_HOME",
            str(
                Path(
                    str(getattr(settings, "codex_cli_auth_path", "~/.codex/auth.json"))
                ).expanduser().parent
            ),
        )
    ).expanduser()
    cache_source = cache_root / "models_cache.json"
    if cache_source.is_file():
        try:
            cache_destination = root / "models_cache.json"
            shutil.copy2(cache_source, cache_destination)
            cache_destination.chmod(0o600)
            auth_events.append(_codex_home_auth_event(cache_source, status="copied"))
        except OSError as exc:
            auth_events.append(
                _codex_home_auth_event(
                    cache_source, status="copy_failed", reason=type(exc).__name__
                )
            )

    try:
        config_path = root / "config.toml"
        config_path.write_text(_isolated_codex_config(), encoding="utf-8")
        config_path.chmod(0o600)
        auth_events.append(
            _codex_home_auth_event(root / "config.toml", status="config_written")
        )
    except OSError as exc:
        auth_events.append(
            _codex_home_auth_event(
                root / "config.toml",
                status="config_write_failed",
                reason=type(exc).__name__,
            )
        )
        cleanup_event = _cleanup_isolated_codex_home(str(root))
        cleanup_events = [cleanup_event] if cleanup_event else []
        # kit:boundary owner=codex.invocation.home_prepare class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_isolated_codex_home_config_write_failure_fail_fast_cleans_home_without_leaks
        raise CodexAppServerHomePreparationError(
            "codex isolated home config write failed",
            path=str(root),
            auth_events=auth_events,
            cleanup_events=cleanup_events,
        ) from exc
    return CodexAppServerHomePreparation(path=str(root), auth_events=auth_events)


def _codex_home_auth_event(
    source: Path, *, status: str, reason: str | None = None
) -> dict[str, str]:
    event = {
        "file": source.name or "unknown",
        "status": status,
    }
    if reason:
        event["reason"] = reason
    return event


def _cleanup_isolated_codex_home(path: str | None) -> dict[str, str] | None:
    raw = str(path or "").strip()
    if not raw:
        return None
    target = Path(raw)
    if not target.name.startswith(_ISOLATED_CODEX_HOME_PREFIX):
        return None
    if target.parent != Path(tempfile.gettempdir()):
        return None
    if not target.exists():
        return None
    try:
        shutil.rmtree(target)
    except OSError as exc:
        if isinstance(exc, FileNotFoundError):
            return None
        return {
            "target": "isolated_codex_home",
            "status": "cleanup_failed",
            "reason": type(exc).__name__,
        }
    return None


def _codex_home_cleanup_log(event: dict[str, str]) -> str:
    reason = str(event.get("reason") or "unknown")
    return f"codex isolated home cleanup failed: {reason}"


def _redact_app_server_log_line(line: str) -> str:
    redacted = _ISOLATED_CODEX_HOME_RE.sub("<redacted-codex-home>", str(line or ""))
    redacted = _AUTH_JSON_PATH_RE.sub("<redacted-auth-path>", redacted)
    redacted = _BEARER_TOKEN_RE.sub(r"\1\2<redacted>", redacted)
    redacted = _SENSITIVE_KEY_VALUE_RE.sub(r"\1\2<redacted>", redacted)
    redacted = _TOKEN_LIKE_VALUE_RE.sub("<redacted>", redacted)
    return redacted


def _redact_app_server_endpoint(endpoint: str | None) -> str | None:
    if endpoint is None:
        return None
    return _redact_app_server_log_line(endpoint)


def _isolated_codex_config() -> str:
    user_config = load_user_codex_model_config()
    model = resolve_codex_model(
        configured_model=getattr(settings, "codex_cli_llm_model", ""),
        user_config=user_config,
    )
    reasoning = resolve_codex_reasoning_effort(
        configured_reasoning_effort=getattr(
            settings, "codex_cli_llm_reasoning_effort", ""
        ),
        user_config=user_config,
    )
    lines = [
        'web_search = "disabled"',
        "project_doc_max_bytes = 0",
        "",
        "[features]",
        "memories = false",
        "apps = false",
        "plugins = false",
        "multi_agent = false",
        "tool_search = false",
        "tool_suggest = false",
        "browser_use = false",
        # Keep the native Codex code-mode host enabled.  The host is a
        # first-class part of the Core runtime: disabling it makes registered
        # tool/skill bindings silently fall back to model-only turns.
        "code_mode_host = true",
        "realtime_conversation = false",
        "chronicle = false",
        "",
        "[analytics]",
        "enabled = false",
        "",
        "[mcp_servers]",
        "",
        "[plugins]",
        "",
        "[apps]",
        "",
    ]
    if model:
        lines.insert(0, f'model = "{_toml_string(model)}"')
    if reasoning and reasoning.lower() != "none":
        lines.insert(
            1 if model else 0, f'model_reasoning_effort = "{_toml_string(reasoning)}"'
        )
    provider = user_config.model_provider
    provider_config = user_config.provider_config
    if provider and isinstance(provider_config, dict):
        lines.insert(
            (2 if model else 1) + (1 if reasoning else 0),
            f'model_provider = "{_toml_string(provider)}"',
        )
        lines.extend(["", f'[model_providers."{_toml_string(provider)}"]'])
        for key, value in provider_config.items():
            if value is None:
                continue
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    return "\n".join(lines)


def _toml_string(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _toml_key(value: object) -> str:
    return f'"{_toml_string(str(value or ""))}"'


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{_toml_string(value)}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return (
            "{ "
            + ", ".join(
                f"{_toml_key(key)} = {_toml_value(item)}"
                for key, item in value.items()
                if item is not None
            )
            + " }"
        )
    return f'"{_toml_string(str(value))}"'
