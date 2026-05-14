from __future__ import annotations

import asyncio
import atexit
from collections import deque
from dataclasses import dataclass
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
from typing import Any, Callable

import websockets

from ...settings.config import settings


_ENDPOINT_RE = re.compile(r"ws://[^\s]+")


@dataclass(frozen=True)
class CodexAppServerInvocation:
    content: str
    endpoint: str
    process_id: int | None
    duration_seconds: float


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
        self.idle_ttl_seconds = int(idle_ttl_seconds if idle_ttl_seconds is not None else getattr(settings, "codex_cli_llm_persistent_idle_ttl_seconds", 300))
        self.start_timeout_seconds = int(start_timeout_seconds if start_timeout_seconds is not None else getattr(settings, "codex_cli_llm_persistent_start_timeout_seconds", 20))
        self.process_factory = process_factory or subprocess.Popen
        self.monotonic = monotonic
        self._lock = threading.RLock()
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
        self._thread_key: tuple[str, str] | None = None
        self._thread_start_count = 0
        self._thread_reuse_count = 0
        self._last_start_duration_seconds: float | None = None
        self._last_invoke_duration_seconds: float | None = None
        self._codex_home: str | None = None
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
                    timeout_seconds=int(timeout_seconds or getattr(settings, "codex_cli_llm_timeout_seconds", 120) or 120),
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
            endpoint=endpoint,
            process_id=self._process.pid if self._process is not None else None,
            duration_seconds=duration_seconds,
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            process = self._process
            alive = bool(process and process.poll() is None)
            return {
                "mounted": alive,
                "endpoint": self._endpoint if alive else None,
                "process_id": process.pid if alive else None,
                "active_calls": self._active_calls,
                "idle_seconds": max(0.0, self.monotonic() - self._last_used_at) if self._last_used_at else None,
                "idle_ttl_seconds": self.idle_ttl_seconds,
                "invoke_count": self._invoke_count,
                "start_count": self._start_count,
                "reuse_count": self._reuse_count,
                "thread_id": self._thread_id if alive else None,
                "thread_start_count": self._thread_start_count,
                "thread_reuse_count": self._thread_reuse_count,
                "last_start_duration_seconds": self._last_start_duration_seconds,
                "last_invoke_duration_seconds": self._last_invoke_duration_seconds,
                "isolated_codex_home": self._codex_home if alive else None,
                "recent_logs": list(self._recent_logs),
            }

    def shutdown(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
            self._endpoint = None
            self._thread_id = None
            self._thread_key = None
            self._active_calls = 0
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                pass

    def _ensure_process(self) -> str:
        with self._lock:
            if self._process is not None and self._process.poll() is None and self._endpoint:
                self._last_used_at = self.monotonic()
                self._reuse_count += 1
                self._ensure_reaper_locked()
                return self._endpoint
            self._process = None
            self._endpoint = None
            self._thread_id = None
            self._thread_key = None
            while not self._endpoint_queue.empty():
                try:
                    self._endpoint_queue.get_nowait()
                except Exception:  # noqa: BLE001
                    break
            codex_bin = self.codex_bin_resolver()
            if not codex_bin:
                raise RuntimeError("codex cli is not installed")
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
            isolated_home = _prepare_isolated_codex_home()
            env["CODEX_HOME"] = isolated_home
            self._codex_home = isolated_home
            start_started_at = self.monotonic()
            process = self.process_factory(
                args,
                cwd=workdir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._process = process
            self._stdout_thread = threading.Thread(target=self._read_stdout, args=(process,), name="codex-app-server-core-stdout", daemon=True)
            self._stdout_thread.start()
            self._last_used_at = self.monotonic()
            self._ensure_reaper_locked()

            try:
                endpoint = self._endpoint_queue.get(timeout=max(1, self.start_timeout_seconds))
            except queue.Empty as exc:
                logs = "\n".join(list(self._recent_logs)[-8:])
                self.shutdown()
                raise RuntimeError(f"codex app-server did not publish a websocket endpoint within {self.start_timeout_seconds}s. {logs}") from exc
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
            if line:
                self._recent_logs.append(line)
            match = _ENDPOINT_RE.search(line)
            if match:
                endpoint = match.group(0)
                try:
                    self._endpoint_queue.put_nowait(endpoint)
                except queue.Full:
                    pass
        self._recent_logs.append("codex app-server stdout closed")

    def _ensure_reaper_locked(self) -> None:
        if self._reaper_thread is not None and self._reaper_thread.is_alive():
            return
        self._stop_reaper.clear()
        self._reaper_thread = threading.Thread(target=self._reap_idle_loop, name="codex-app-server-core-reaper", daemon=True)
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
        timeout = max(5, int(timeout_seconds or 120))
        async with websockets.connect(endpoint, open_timeout=min(10, timeout)) as ws:
            await self._request(
                ws,
                request_id=1,
                method="initialize",
                params={
                    "clientInfo": {"name": "market-research-workflow", "version": "0.1.0"},
                    "capabilities": {
                        "experimentalApi": True,
                        "optOutNotificationMethods": [
                            "mcpServer/startupStatus/updated",
                            "account/rateLimits/updated",
                            "thread/tokenUsage/updated",
                        ],
                    },
                },
                timeout_seconds=timeout,
            )
            await ws.send(json.dumps({"method": "initialized"}, ensure_ascii=False))
            resolved_model = model or getattr(settings, "codex_cli_llm_model", None) or "gpt-5.4-mini"
            thread_id = await self._ensure_thread_id(ws, model=str(resolved_model), timeout_seconds=timeout)
            turn_params: dict[str, Any] = {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt, "text_elements": []}],
                "cwd": self.workdir_resolver(),
                "model": resolved_model,
                "approvalPolicy": "never",
            }
            effort = str(reasoning_effort or getattr(settings, "codex_cli_llm_reasoning_effort", "") or "").strip()
            if effort:
                turn_params["effort"] = effort
            try:
                turn_response = await self._request(
                    ws,
                    request_id=3,
                    method="turn/start",
                    params=turn_params,
                    timeout_seconds=timeout,
                )
            except RuntimeError:
                with self._lock:
                    self._thread_id = None
                    self._thread_key = None
                thread_id = await self._ensure_thread_id(ws, model=str(resolved_model), timeout_seconds=timeout)
                turn_params["threadId"] = thread_id
                turn_response = await self._request(
                    ws,
                    request_id=4,
                    method="turn/start",
                    params=turn_params,
                    timeout_seconds=timeout,
                )
            turn_id = str(((turn_response.get("turn") or {}).get("id")) or "").strip()
            chunks: list[str] = []
            completed_text = ""
            while True:
                data = await self._recv_json(ws, timeout_seconds=timeout)
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
                    if not turn_id or ((params.get("turn") or {}).get("id") == turn_id):
                        break
                elif data.get("error"):
                    raise RuntimeError(f"codex app-server error: {data.get('error')}")
            content = (completed_text or "".join(chunks)).strip()
            if not content:
                raise RuntimeError("codex app-server returned empty output")
            return content

    async def _ensure_thread_id(self, ws: Any, *, model: str, timeout_seconds: int) -> str:
        workdir = self.workdir_resolver()
        thread_key = (workdir, model)
        if bool(getattr(settings, "codex_cli_llm_reuse_thread", False)):
            with self._lock:
                if self._thread_id and self._thread_key == thread_key:
                    self._thread_reuse_count += 1
                    return self._thread_id
        thread_response = await self._request(
            ws,
            request_id=2,
            method="thread/start",
            params={
                "cwd": workdir,
                "model": model,
                "sandbox": "read-only",
                "approvalPolicy": "never",
                "ephemeral": True,
                "baseInstructions": (
                    "You are a mounted Codex model core for another application. "
                    "Follow the user's prompt exactly. Do not run shell commands, edit files, or call tools. "
                    "If the prompt requires JSON, return only JSON."
                ),
                "developerInstructions": "Act only as a chat/model provider for this prompt. Keep answers concise and return promptly.",
            },
            timeout_seconds=timeout_seconds,
        )
        thread_id = str(((thread_response.get("thread") or {}).get("id")) or "").strip()
        if not thread_id:
            raise RuntimeError("codex app-server thread/start returned no thread id")
        with self._lock:
            if bool(getattr(settings, "codex_cli_llm_reuse_thread", False)):
                self._thread_id = thread_id
                self._thread_key = thread_key
            else:
                self._thread_id = None
                self._thread_key = None
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
    ) -> dict[str, Any]:
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, ensure_ascii=False, default=str))
        while True:
            data = await self._recv_json(ws, timeout_seconds=timeout_seconds)
            if data.get("id") != request_id:
                continue
            if data.get("error"):
                raise RuntimeError(f"codex app-server {method} failed: {data.get('error')}")
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
        return {"mounted": False, "idle_ttl_seconds": int(getattr(settings, "codex_cli_llm_persistent_idle_ttl_seconds", 300))}
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


def _prepare_isolated_codex_home() -> str:
    """Create a minimal CODEX_HOME for backend-owned app-server mounts.

    The desktop/global Codex config can contain user MCP servers such as
    Storybook or browser tooling. The backend AgentCore model mount should not
    inherit those services because an unavailable local MCP endpoint can make a
    logically mounted model core behave as partially mounted. We copy auth
    files only and provide a small config with MCP/plugins/apps disabled.
    """

    root = Path(tempfile.gettempdir()) / "market-research-workflow-codex-core-home"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass

    for raw_path in (
        getattr(settings, "codex_cli_auth_path", "~/.codex/auth.json"),
        getattr(settings, "codex_oauth_token_sink_path", "~/.codex/auth_openai.json"),
    ):
        source = Path(str(raw_path or "")).expanduser()
        if not source.exists() or not source.is_file():
            continue
        destination = root / source.name
        try:
            shutil.copy2(source, destination)
            destination.chmod(0o600)
        except OSError:
            continue

    (root / "config.toml").write_text(_isolated_codex_config(), encoding="utf-8")
    return str(root)


def _isolated_codex_config() -> str:
    model = str(getattr(settings, "codex_cli_llm_model", "gpt-5.4-mini") or "gpt-5.4-mini").strip() or "gpt-5.4-mini"
    reasoning = str(getattr(settings, "codex_cli_llm_reasoning_effort", "none") or "none").strip() or "none"
    return "\n".join(
        [
            f'model = "{_toml_string(model)}"',
            f'model_reasoning_effort = "{_toml_string(reasoning)}"',
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
    )


def _toml_string(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')
