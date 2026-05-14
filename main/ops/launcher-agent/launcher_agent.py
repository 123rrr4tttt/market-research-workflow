from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


HOST = "0.0.0.0"
PORT = int(os.environ.get("LAUNCHER_AGENT_PORT", "8787"))
PROJECT_ROOT = Path(os.environ.get("HOST_PROJECT_ROOT", "/Users/wangyiliang/market-research-workflow"))
OPS_DIR = PROJECT_ROOT / "main" / "ops"
LAUNCHER_PROJECT_NAME = os.environ.get("LAUNCHER_PROJECT_NAME", "mrw-launcher")
BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://host.docker.internal:8000").rstrip("/")
ALLOWED_PROFILES = {"modern-ui", "search-enhancements"}
DEFAULT_START_PROFILES = ["modern-ui"]
DEFAULT_CONTROL_PROFILES = ["modern-ui", "search-enhancements"]
CONTROL_SERVICES = {"launcher-agent", "launcher-ui"}
APP_SERVICES = ["db", "es", "redis", "backend", "celery-worker", "frontend-modern"]
SEARCH_SERVICES = ["searxng", "yacy"]
SERVICE_PROFILES = {
    "db": ["modern-ui"],
    "es": ["modern-ui"],
    "redis": ["modern-ui"],
    "backend": ["modern-ui"],
    "celery-worker": ["modern-ui"],
    "frontend-modern": ["modern-ui"],
    "searxng": ["search-enhancements"],
    "yacy": ["search-enhancements"],
}
SERVICE_LABELS = {
    "db": "Database",
    "es": "Elasticsearch",
    "redis": "Redis",
    "backend": "Backend API",
    "celery-worker": "Worker",
    "frontend-modern": "App Frontend",
    "searxng": "SearXNG",
    "yacy": "YaCy",
}


def _is_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(token in upper for token in ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "BEARER"))


def _redact_env_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return payload
    redacted = dict(data)
    for key, value in redacted.items():
        if _is_secret_key(str(key)) and value:
            redacted[key] = "********"
    next_payload = dict(payload)
    next_payload["data"] = redacted
    return next_payload


def _backend_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 15,
) -> tuple[int, dict[str, Any]]:
    url = f"{BACKEND_BASE_URL}{path}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return response.status, parsed if isinstance(parsed, dict) else {"data": parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"error": raw}
        return exc.code, parsed if isinstance(parsed, dict) else {"error": parsed}
    except Exception as exc:  # noqa: BLE001
        return 502, {"ok": False, "error": str(exc)}


def _run(argv: list[str], *, timeout: int = 120) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            argv,
            cwd=OPS_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return completed.returncode, ((completed.stdout or "") + (completed.stderr or "")).strip()
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _compose_base(profiles: list[str]) -> list[str]:
    argv = ["docker", "compose"]
    for profile in profiles:
        argv.extend(["--profile", profile])
    return argv


def _clean_profiles(raw: Any, *, default: list[str]) -> list[str]:
    if not isinstance(raw, list):
        raw = default
    profiles: list[str] = []
    for item in raw:
        value = str(item or "").strip()
        if value in ALLOWED_PROFILES and value not in profiles:
            profiles.append(value)
    return profiles or list(default)


def compose_status() -> dict[str, Any]:
    profiles = DEFAULT_CONTROL_PROFILES
    code, output = _run(_compose_base(profiles) + ["ps", "--status", "running", "--services"], timeout=20)
    services = [line.strip() for line in output.splitlines() if line.strip()]
    control_services = _launcher_control_services()
    app_services = [service for service in services if service not in CONTROL_SERVICES]
    return {
        "ok": code == 0,
        "running_services": app_services if code == 0 else [],
        "running_count": len(app_services) if code == 0 else 0,
        "control_services": control_services if code == 0 else [],
        "known_services": [
            {
                "id": service,
                "label": SERVICE_LABELS.get(service, service),
                "running": service in app_services,
                "optional": service in SEARCH_SERVICES,
            }
            for service in [*APP_SERVICES, *SEARCH_SERVICES]
        ],
        "profiles": profiles,
        "ops_dir": str(OPS_DIR),
        "launcher_project": LAUNCHER_PROJECT_NAME,
        "docker_socket": os.path.exists("/var/run/docker.sock"),
    }


def _launcher_control_services() -> list[str]:
    code, output = _run(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={LAUNCHER_PROJECT_NAME}",
            "--format",
            '{{.Label "com.docker.compose.service"}}',
        ],
        timeout=20,
    )
    if code != 0:
        return []
    services = []
    for line in output.splitlines():
        service = line.strip()
        if service in CONTROL_SERVICES and service not in services:
            services.append(service)
    return services


def delayed_stop(profiles: list[str]) -> None:
    def worker() -> None:
        time.sleep(0.8)
        services = list(APP_SERVICES)
        if "search-enhancements" in profiles:
            services.extend(SEARCH_SERVICES)
        _run(_compose_base(profiles) + ["stop", *services], timeout=180)

    threading.Thread(target=worker, daemon=True).start()


def _clean_optional_services(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    services: list[str] = []
    for item in raw:
        value = str(item or "").strip()
        if value in SEARCH_SERVICES and value not in services:
            services.append(value)
    return services


def _profiles_for_services(services: list[str]) -> list[str]:
    profiles = ["modern-ui"]
    if any(service in SEARCH_SERVICES for service in services):
        profiles.append("search-enhancements")
    return profiles


class Handler(BaseHTTPRequestHandler):
    server_version = "MRWLauncherAgent/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        raw_len = int(self.headers.get("content-length") or "0")
        if raw_len <= 0:
            return {}
        data = self.rfile.read(raw_len)
        try:
            parsed = json.loads(data.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self) -> None:
        self._send(200, {"ok": True})

    def do_GET(self) -> None:
        if self.path in {"/health", "/api/launcher/health"}:
            self._send(200, {"ok": True, "service": "launcher-agent"})
            return
        if self.path.startswith("/api/launcher/status"):
            self._send(200, {"ok": True, "data": compose_status()})
            return
        if self.path.startswith("/api/launcher/config/env"):
            status, payload = _backend_json("GET", "/api/v1/config/env")
            self._send(status, _redact_env_payload(payload))
            return
        if self.path.startswith("/api/launcher/codex/status"):
            status, payload = _backend_json("GET", "/api/v1/codex-auth/status")
            self._send(status, payload)
            return
        self._send(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        payload = self._read_json()
        if self.path.startswith("/api/launcher/start"):
            services = list(APP_SERVICES)
            services.extend(_clean_optional_services(payload.get("optional_services")))
            profiles = _profiles_for_services(services)
            code, output = _run(_compose_base(profiles) + ["up", "-d", *services], timeout=300)
            self._send(200 if code == 0 else 500, {"ok": code == 0, "profiles": profiles, "output": output})
            return
        if self.path.startswith("/api/launcher/stop"):
            profiles = _clean_profiles(payload.get("profiles"), default=DEFAULT_CONTROL_PROFILES)
            delayed_stop(profiles)
            self._send(202, {"ok": True, "accepted": True, "profiles": profiles})
            return
        if self.path.startswith("/api/launcher/restart"):
            optional_services = _clean_optional_services(payload.get("optional_services"))
            profiles = _profiles_for_services([*APP_SERVICES, *optional_services])
            stop_services = list(APP_SERVICES) + list(SEARCH_SERVICES)
            code, output = _run(_compose_base(DEFAULT_CONTROL_PROFILES) + ["stop", *stop_services], timeout=180)
            if code == 0:
                services = list(APP_SERVICES)
                services.extend(optional_services)
                code, output2 = _run(_compose_base(profiles) + ["up", "-d", *services], timeout=300)
                output = f"{output}\n{output2}".strip()
            self._send(200 if code == 0 else 500, {"ok": code == 0, "profiles": profiles, "output": output})
            return
        if self.path.startswith("/api/launcher/service"):
            service = str(payload.get("service") or "").strip()
            action = str(payload.get("action") or "").strip()
            if service not in SERVICE_PROFILES or action not in {"start", "stop", "restart"}:
                self._send(400, {"ok": False, "error": "invalid_service_action"})
                return
            profiles = SERVICE_PROFILES[service]
            if action == "start":
                code, output = _run(_compose_base(profiles) + ["up", "-d", service], timeout=240)
            elif action == "stop":
                code, output = _run(_compose_base(profiles) + ["stop", service], timeout=120)
            else:
                code, output = _run(_compose_base(profiles) + ["restart", service], timeout=180)
            self._send(
                200 if code == 0 else 500,
                {"ok": code == 0, "service": service, "action": action, "profiles": profiles, "output": output},
            )
            return
        if self.path.startswith("/api/launcher/config/env"):
            status, output = _backend_json("POST", "/api/v1/config/env", payload)
            self._send(status, output)
            return
        if self.path.startswith("/api/launcher/config/reload"):
            status, output = _backend_json("POST", "/api/v1/config/reload", {})
            self._send(status, output)
            return
        if self.path.startswith("/api/launcher/codex/cli/bootstrap"):
            status, output = _backend_json("POST", "/api/v1/codex-auth/cli/bootstrap", {}, timeout=330)
            self._send(status, output)
            return
        self._send(404, {"ok": False, "error": "not_found"})


def main() -> None:
    if not OPS_DIR.exists():
        print(f"warning: ops dir does not exist: {OPS_DIR}", flush=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"launcher-agent listening on {HOST}:{PORT}; ops_dir={OPS_DIR}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
