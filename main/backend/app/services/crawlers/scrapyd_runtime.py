from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from shutil import which

import httpx


_BOOT_LOCK = threading.Lock()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _default_base_url() -> str:
    return str(os.getenv("SCRAPYD_BASE_URL") or os.getenv("CRAWLER_SCRAPYD_BASE_URL") or "http://127.0.0.1:6800").strip()


def resolve_scrapyd_base_url(explicit_base_url: str | None = None) -> str:
    base = str(explicit_base_url or _default_base_url()).strip()
    if not base:
        raise ValueError("SCRAPYD_BASE_URL is required")
    return base.rstrip("/")


def is_scrapyd_healthy(base_url: str, timeout: float = 2.0) -> bool:
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{base_url.rstrip('/')}/daemonstatus.json")
            if resp.status_code != 200:
                return False
            body = resp.json()
            if not isinstance(body, dict):
                return False
            return str(body.get("status") or "").strip().lower() == "ok"
    except Exception:
        return False


def _lazy_start_enabled() -> bool:
    raw = str(os.getenv("CRAWLER_LAZY_START_SCRAPYD", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _start_scrapyd_via_compose() -> None:
    root = _repo_root()
    compose_file = root / "main" / "ops" / "docker-compose.yml"
    ops_dir = compose_file.parent
    if not compose_file.exists():
        raise RuntimeError(f"compose file not found: {compose_file}")

    cmd: list[str]
    if which("docker") is not None:
        try:
            subprocess.run(["docker", "compose", "version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cmd = ["docker", "compose", "--profile", "scrapyd", "-f", str(compose_file), "up", "-d", "scrapyd"]
            subprocess.run(cmd, cwd=str(ops_dir), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass

    if which("docker-compose") is not None:
        cmd = ["docker-compose", "--profile", "scrapyd", "-f", str(compose_file), "up", "-d", "scrapyd"]
        subprocess.run(cmd, cwd=str(ops_dir), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    raise RuntimeError("docker compose is unavailable")


def _start_scrapyd_local_daemon() -> None:
    py = sys.executable or "python3"
    probe = subprocess.run(
        [py, "-c", "import scrapyd"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    if probe.returncode != 0:
        raise RuntimeError("python scrapyd module is unavailable")
    subprocess.Popen(
        [py, "-m", "scrapyd"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def ensure_scrapyd_ready(
    *,
    base_url: str | None = None,
    wait_seconds: float | None = None,
) -> str:
    resolved = resolve_scrapyd_base_url(base_url)
    if is_scrapyd_healthy(resolved):
        return resolved

    if not _lazy_start_enabled():
        raise ValueError("Scrapyd is unavailable and lazy-start is disabled")

    with _BOOT_LOCK:
        if is_scrapyd_healthy(resolved):
            return resolved
        errors: list[str] = []
        try:
            _start_scrapyd_via_compose()
        except Exception as exc:
            errors.append(f"compose: {exc}")
            try:
                _start_scrapyd_local_daemon()
            except Exception as exc2:
                errors.append(f"local: {exc2}")
                raise RuntimeError("failed to lazy-start scrapyd; " + " | ".join(errors)) from exc2

    timeout_s = float(wait_seconds if wait_seconds is not None else os.getenv("CRAWLER_SCRAPYD_BOOT_TIMEOUT", "30"))
    deadline = time.time() + max(5.0, timeout_s)
    while time.time() < deadline:
        if is_scrapyd_healthy(resolved):
            return resolved
        time.sleep(1.0)

    raise TimeoutError(f"scrapyd is not healthy after lazy start: {resolved}")


__all__ = [
    "resolve_scrapyd_base_url",
    "is_scrapyd_healthy",
    "ensure_scrapyd_ready",
]
