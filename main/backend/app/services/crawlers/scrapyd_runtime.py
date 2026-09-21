from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Any, Protocol

import httpx
from functorial_kit import Failure

from .registry import _failure, _raise_contract_failure


_BOOT_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class ResolvedScrapydBaseUrl:
    """Successful, normalized Scrapyd endpoint returned by the total port."""

    base_url: str


class ScrapydTransportPort(Protocol):
    """Effect boundary for health observation and lazy-start operations."""

    def health(self, base_url: str, timeout: float = 2.0) -> bool | Failure:
        ...

    def start_compose(self) -> Failure | None:
        ...

    def start_local_daemon(self) -> Failure | None:
        ...


def _normalize_health_outcome(value: object, *, site: str) -> bool | Failure:
    """Keep transport observations inside the typed health effect boundary."""
    if value is True or value is False or isinstance(value, Failure):
        return value
    return _failure(
        "scrapyd_response_invalid",
        "scrapyd transport returned a non-canonical health outcome",
        operation="scrapyd_runtime.health_check",
        site=site,
        public_exception="RuntimeError",
        result_type=type(value).__name__,
    )


def _normalize_start_outcome(value: object, *, operation: str, site: str) -> Failure | None:
    """Keep lazy-start observations inside the typed effect boundary."""
    if value is None or isinstance(value, Failure):
        return value
    return _failure(
        "scrapyd_lazy_start_failed",
        "scrapyd transport returned a non-canonical start outcome",
        operation=operation,
        site=site,
        public_exception="RuntimeError",
        result_type=type(value).__name__,
    )


def _scrapyd_repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _default_base_url() -> str:
    return str(os.getenv("SCRAPYD_BASE_URL") or os.getenv("CRAWLER_SCRAPYD_BASE_URL") or "http://127.0.0.1:6800").strip()


def try_resolve_scrapyd_base_url(explicit_base_url: str | None = None) -> str | Failure:
    base = str(_default_base_url() if explicit_base_url is None else explicit_base_url).strip()
    if not base:
        return _failure(
            "scrapyd_base_url_required",
            "SCRAPYD_BASE_URL is required",
            operation="scrapyd_runtime.resolve_base_url",
            site="app.services.crawlers.scrapyd_runtime.resolve_scrapyd_base_url",
        )
    return base.rstrip("/")


def resolve_scrapyd_base_url(explicit_base_url: str | None = None) -> str:
    resolved = try_resolve_scrapyd_base_url(explicit_base_url)
    if isinstance(resolved, Failure):
        _raise_contract_failure(resolved)
    return resolved


def _try_scrapyd_health(base_url: str, timeout: float = 2.0) -> bool | Failure:
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{base_url.rstrip('/')}/daemonstatus.json")
    except Exception as exc:
        return _failure(
            "scrapyd_transport",
            f"scrapyd health check transport failed: {exc}",
            operation="scrapyd_runtime.health_check",
            site="app.services.crawlers.scrapyd_runtime.try_is_scrapyd_healthy",
            public_exception="RuntimeError",
            cause=exc,
        )
    if resp.status_code != 200:
        return _failure(
            "scrapyd_http_status",
            f"scrapyd health check returned HTTP {resp.status_code}",
            operation="scrapyd_runtime.health_check",
            site="app.services.crawlers.scrapyd_runtime.try_is_scrapyd_healthy",
            public_exception="RuntimeError",
            status_code=resp.status_code,
        )
    try:
        body = resp.json()
    except Exception as exc:
        return _failure(
            "scrapyd_response_invalid",
            f"scrapyd health check returned invalid JSON: {exc}",
            operation="scrapyd_runtime.health_check",
            site="app.services.crawlers.scrapyd_runtime.try_is_scrapyd_healthy",
            public_exception="RuntimeError",
            cause=exc,
        )
    if not isinstance(body, dict) or str(body.get("status") or "").strip().lower() != "ok":
        return _failure(
            "scrapyd_response_invalid",
            "scrapyd health check response is not an ok status object",
            operation="scrapyd_runtime.health_check",
            site="app.services.crawlers.scrapyd_runtime.try_is_scrapyd_healthy",
            public_exception="RuntimeError",
        )
    return True


class _DefaultScrapydTransport:
    def health(self, base_url: str, timeout: float = 2.0) -> bool | Failure:
        return _try_scrapyd_health(base_url, timeout)

    def start_compose(self) -> Failure | None:
        return _start_scrapyd_via_compose()

    def start_local_daemon(self) -> Failure | None:
        return _start_scrapyd_local_daemon()


_DEFAULT_TRANSPORT = _DefaultScrapydTransport()


def _transport_health(transport: ScrapydTransportPort, base_url: str) -> bool | Failure:
    try:
        observed = transport.health(base_url)
    except Exception as exc:
        return _failure(
            "scrapyd_transport",
            f"scrapyd health check transport failed: {exc}",
            operation="scrapyd_runtime.health_check",
            site="app.services.crawlers.scrapyd_runtime.try_ensure_scrapyd_ready",
            public_exception="RuntimeError",
            cause=exc,
        )
    return _normalize_health_outcome(
        observed,
        site="app.services.crawlers.scrapyd_runtime.try_ensure_scrapyd_ready",
    )


def try_is_scrapyd_healthy(base_url: str, timeout: float = 2.0) -> bool | Failure:
    return _DEFAULT_TRANSPORT.health(base_url, timeout)


def is_scrapyd_healthy(base_url: str, timeout: float = 2.0) -> bool:
    result = try_is_scrapyd_healthy(base_url, timeout)
    return result is True


def _lazy_start_enabled() -> bool:
    raw = str(os.getenv("CRAWLER_LAZY_START_SCRAPYD", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _start_scrapyd_via_compose() -> Failure | None:
    root = _scrapyd_repo_root()
    compose_file = root / "main" / "ops" / "docker-compose.yml"
    ops_dir = compose_file.parent
    if not compose_file.exists():
        cause = RuntimeError(f"compose file not found: {compose_file}")
        return _failure(
            "scrapyd_compose_file_missing",
            str(cause),
            operation="scrapyd_runtime.lazy_start.compose",
            site="app.services.crawlers.scrapyd_runtime._start_scrapyd_via_compose",
            public_exception="RuntimeError",
            cause=cause,
        )

    cmd: list[str]
    docker_error: BaseException | None = None
    if which("docker") is not None:
        try:
            subprocess.run(["docker", "compose", "version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cmd = ["docker", "compose", "--profile", "scrapyd", "-f", str(compose_file), "up", "-d", "scrapyd"]
            subprocess.run(cmd, cwd=str(ops_dir), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return None
        except Exception as exc:
            docker_error = exc

    if which("docker-compose") is not None:
        cmd = ["docker-compose", "--profile", "scrapyd", "-f", str(compose_file), "up", "-d", "scrapyd"]
        try:
            subprocess.run(cmd, cwd=str(ops_dir), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return None
        except Exception as exc:
            return _failure(
                "scrapyd_compose_unavailable",
                "docker compose is unavailable",
                operation="scrapyd_runtime.lazy_start.compose",
                site="app.services.crawlers.scrapyd_runtime._start_scrapyd_via_compose",
                public_exception="RuntimeError",
                cause=exc,
            )
    cause = docker_error or RuntimeError("docker compose is unavailable")
    return _failure(
        "scrapyd_compose_unavailable",
        "docker compose is unavailable",
        operation="scrapyd_runtime.lazy_start.compose",
        site="app.services.crawlers.scrapyd_runtime._start_scrapyd_via_compose",
        public_exception="RuntimeError",
        cause=cause,
    )


def _start_scrapyd_local_daemon() -> Failure | None:
    py = sys.executable or "python3"
    try:
        probe = subprocess.run(
            [py, "-c", "import scrapyd"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception as exc:
        return _failure(
            "scrapyd_module_unavailable",
            "python scrapyd module is unavailable",
            operation="scrapyd_runtime.lazy_start.local",
            site="app.services.crawlers.scrapyd_runtime._start_scrapyd_local_daemon",
            public_exception="RuntimeError",
            cause=exc,
        )
    if probe.returncode != 0:
        cause = RuntimeError("python scrapyd module is unavailable")
        return _failure(
            "scrapyd_module_unavailable",
            str(cause),
            operation="scrapyd_runtime.lazy_start.local",
            site="app.services.crawlers.scrapyd_runtime._start_scrapyd_local_daemon",
            public_exception="RuntimeError",
            cause=cause,
        )
    try:
        subprocess.Popen(
            [py, "-m", "scrapyd"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        return _failure(
            "scrapyd_lazy_start_failed",
            f"failed to launch local scrapyd daemon: {exc}",
            operation="scrapyd_runtime.lazy_start.local",
            site="app.services.crawlers.scrapyd_runtime._start_scrapyd_local_daemon",
            public_exception="RuntimeError",
            cause=exc,
        )
    return None


def try_ensure_scrapyd_ready(
    *,
    base_url: str | None = None,
    wait_seconds: float | None = None,
    transport: ScrapydTransportPort | None = None,
) -> ResolvedScrapydBaseUrl | Failure:
    resolved = try_resolve_scrapyd_base_url(base_url)
    if isinstance(resolved, Failure):
        return resolved

    active_transport = transport or _DEFAULT_TRANSPORT
    health = _transport_health(active_transport, resolved)
    if health is True:
        return ResolvedScrapydBaseUrl(resolved)

    if not _lazy_start_enabled():
        return _failure(
            "scrapyd_unavailable",
            "Scrapyd is unavailable and lazy-start is disabled",
            operation="scrapyd_runtime.ensure_ready",
            site="app.services.crawlers.scrapyd_runtime.try_ensure_scrapyd_ready",
            observed_failure=health.code if isinstance(health, Failure) else None,
        )

    with _BOOT_LOCK:
        health = _transport_health(active_transport, resolved)
        if health is True:
            return ResolvedScrapydBaseUrl(resolved)

        compose_failure: Failure | None = None
        try:
            compose_failure = _normalize_start_outcome(
                active_transport.start_compose(),
                operation="scrapyd_runtime.lazy_start.compose",
                site="app.services.crawlers.scrapyd_runtime.try_ensure_scrapyd_ready",
            )
        except Exception as exc:
            compose_failure = _failure(
                "scrapyd_compose_unavailable",
                "docker compose is unavailable",
                operation="scrapyd_runtime.lazy_start.compose",
                site="app.services.crawlers.scrapyd_runtime._start_scrapyd_via_compose",
                public_exception="RuntimeError",
                cause=exc,
            )
        if compose_failure is not None:
            local_failure: Failure | None = None
            try:
                local_failure = _normalize_start_outcome(
                    active_transport.start_local_daemon(),
                    operation="scrapyd_runtime.lazy_start.local",
                    site="app.services.crawlers.scrapyd_runtime.try_ensure_scrapyd_ready",
                )
            except Exception as exc:
                local_failure = _failure(
                    "scrapyd_lazy_start_failed",
                    f"failed to launch local scrapyd daemon: {exc}",
                    operation="scrapyd_runtime.lazy_start.local",
                    site="app.services.crawlers.scrapyd_runtime._start_scrapyd_local_daemon",
                    public_exception="RuntimeError",
                    cause=exc,
                )
            if local_failure is not None:
                local_cause = (local_failure.context or {}).get("cause")
                compose_text = compose_failure.message
                local_text = local_failure.message
                return _failure(
                    "scrapyd_lazy_start_failed",
                    f"failed to lazy-start scrapyd; compose: {compose_text} | local: {local_text}",
                    operation="scrapyd_runtime.ensure_ready",
                    site="app.services.crawlers.scrapyd_runtime.try_ensure_scrapyd_ready",
                    public_exception="RuntimeError",
                    compose_code=compose_failure.code,
                    local_code=local_failure.code,
                    cause=local_cause,
                )

    try:
        timeout_s = float(wait_seconds if wait_seconds is not None else os.getenv("CRAWLER_SCRAPYD_BOOT_TIMEOUT", "30"))
    except (TypeError, ValueError) as exc:
        return _failure(
            "scrapyd_readiness_timeout",
            f"invalid scrapyd readiness timeout: {exc}",
            operation="scrapyd_runtime.ensure_ready",
            site="app.services.crawlers.scrapyd_runtime.try_ensure_scrapyd_ready",
            public_exception="TimeoutError",
            cause=exc,
        )
    deadline = time.time() + max(5.0, timeout_s)
    last_health = health
    while time.time() < deadline:
        last_health = _transport_health(active_transport, resolved)
        if last_health is True:
            return ResolvedScrapydBaseUrl(resolved)
        time.sleep(1.0)

    return _failure(
        "scrapyd_readiness_timeout",
        f"scrapyd is not healthy after lazy start: {resolved}",
        operation="scrapyd_runtime.ensure_ready",
        site="app.services.crawlers.scrapyd_runtime.try_ensure_scrapyd_ready",
        public_exception="TimeoutError",
        observed_failure=last_health.code if isinstance(last_health, Failure) else None,
    )


def ensure_scrapyd_ready(
    *,
    base_url: str | None = None,
    wait_seconds: float | None = None,
    transport: ScrapydTransportPort | None = None,
) -> str:
    result = try_ensure_scrapyd_ready(
        base_url=base_url,
        wait_seconds=wait_seconds,
        transport=transport,
    )
    if isinstance(result, Failure):
        context: dict[str, Any] = dict(result.context or {})
        public_exception = context.get("public_exception")
        exception_type: type[Exception] = {
            "TimeoutError": TimeoutError,
            "RuntimeError": RuntimeError,
        }.get(str(public_exception), ValueError)
        cause = context.get("cause")
        _raise_contract_failure(result, exception_type, cause=cause if isinstance(cause, BaseException) else None)
    return result.base_url


__all__ = [
    "ResolvedScrapydBaseUrl",
    "ScrapydTransportPort",
    "try_resolve_scrapyd_base_url",
    "resolve_scrapyd_base_url",
    "try_is_scrapyd_healthy",
    "is_scrapyd_healthy",
    "try_ensure_scrapyd_ready",
    "ensure_scrapyd_ready",
]
