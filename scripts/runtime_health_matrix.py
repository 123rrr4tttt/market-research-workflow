#!/usr/bin/env python3
"""Passive full-stack runtime health matrix.

This checker does not start services. It records whether the expected local,
Docker, and mixed runtime surfaces are reachable, and marks missing required
services as ``blocked_by_environment`` instead of treating them as passed.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Callable

try:
    from scripts._automation_runtime import repo_root
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import repo_root


SCHEMA_VERSION = "mrw.runtime_health_matrix.v1"
DEFAULT_OUTPUT = (
    "development/latest-dev-docs/automation-runs/"
    "runtime-health-matrix/latest-runtime-health-matrix.json"
)
DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class EndpointSpec:
    check_id: str
    label: str
    url: str
    required: bool = True
    expected_statuses: tuple[int, ...] = (200,)


@dataclass(frozen=True)
class PortSpec:
    check_id: str
    label: str
    host: str
    port: int
    required: bool = True


@dataclass(frozen=True)
class WorkerReadinessSpec:
    check_id: str
    label: str
    url: str
    required: bool = True
    expected_statuses: tuple[int, ...] = (200,)
    recommended_command: str = "./scripts/local-deploy.sh start"


@dataclass(frozen=True)
class RuntimeModeSpec:
    mode: str
    description: str
    endpoints: tuple[EndpointSpec, ...]
    ports: tuple[PortSpec, ...]
    recommended_commands: tuple[str, ...]
    async_readiness: tuple[WorkerReadinessSpec, ...] = ()
    not_probed_reason: str | None = None


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _url_host_port(url: str) -> tuple[str, int | None]:
    parsed = urllib.parse.urlparse(url)
    return parsed.hostname or "", parsed.port


def probe_port(spec: PortSpec, *, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with socket.create_connection((spec.host, spec.port), timeout=timeout):
            return {
                "check_id": spec.check_id,
                "label": spec.label,
                "host": spec.host,
                "port": spec.port,
                "required": spec.required,
                "status": "passed",
                "blocked": False,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "detail": "tcp listener is reachable",
            }
    except OSError as exc:
        return {
            "check_id": spec.check_id,
            "label": spec.label,
            "host": spec.host,
            "port": spec.port,
            "required": spec.required,
            "status": "blocked_by_environment",
            "blocked": True,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "reason": "port_not_listening",
            "detail": str(exc),
        }


def probe_endpoint(spec: EndpointSpec, *, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    request = urllib.request.Request(spec.url, method="GET", headers={"Accept": "application/json,text/html,*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = int(response.status)
            body_sample = response.read(512).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status_code = int(exc.code)
        body_sample = exc.read(512).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        host, port = _url_host_port(spec.url)
        return {
            "check_id": spec.check_id,
            "label": spec.label,
            "url": spec.url,
            "host": host,
            "port": port,
            "required": spec.required,
            "expected_statuses": list(spec.expected_statuses),
            "status": "blocked_by_environment",
            "blocked": True,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "reason": "endpoint_unreachable",
            "detail": str(exc),
        }

    ok = status_code in spec.expected_statuses
    return {
        "check_id": spec.check_id,
        "label": spec.label,
        "url": spec.url,
        "host": _url_host_port(spec.url)[0],
        "port": _url_host_port(spec.url)[1],
        "required": spec.required,
        "expected_statuses": list(spec.expected_statuses),
        "actual_status": status_code,
        "status": "passed" if ok else "failed",
        "blocked": False,
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "body_sample": body_sample[:240],
    }


def _loads_json_object(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _payload_data(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    return []


def _extract_worker_evidence(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = _payload_data(payload)
    worker_names = _string_list(data.get("worker_names"))
    if not worker_names:
        worker_names = _string_list(data.get("workers"))

    worker_count = _coerce_int(data.get("workers"))
    if worker_count is None:
        worker_count = len(worker_names) if worker_names else None

    worker_online = data.get("worker_online")
    if isinstance(worker_online, bool):
        online = worker_online
    elif worker_count is not None:
        online = worker_count > 0
    else:
        online = bool(worker_names)

    return {
        "worker_online": online,
        "worker_count": worker_count,
        "worker_names": worker_names,
        "raw_status": data.get("status") or (payload or {}).get("status"),
    }


def probe_worker_readiness(spec: WorkerReadinessSpec, *, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    request = urllib.request.Request(
        spec.url,
        method="GET",
        headers={"Accept": "application/json", "X-Project-Key": "demo_proj"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = int(response.status)
            body_sample = response.read(4096).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status_code = int(exc.code)
        body_sample = exc.read(1024).decode("utf-8", errors="replace")
        return {
            "check_id": spec.check_id,
            "label": spec.label,
            "url": spec.url,
            "required": spec.required,
            "expected_statuses": list(spec.expected_statuses),
            "actual_status": status_code,
            "status": "blocked_by_environment",
            "blocked": True,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "reason": "worker_status_probe_failed",
            "detail": f"backend worker readiness probe returned HTTP {status_code}: {body_sample[:240]}",
            "recommended_command": spec.recommended_command,
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        host, port = _url_host_port(spec.url)
        return {
            "check_id": spec.check_id,
            "label": spec.label,
            "url": spec.url,
            "host": host,
            "port": port,
            "required": spec.required,
            "expected_statuses": list(spec.expected_statuses),
            "status": "blocked_by_environment",
            "blocked": True,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "reason": "worker_status_probe_unreachable",
            "detail": str(exc),
            "recommended_command": spec.recommended_command,
        }

    payload = _loads_json_object(body_sample)
    evidence = _extract_worker_evidence(payload)
    ok_status = status_code in spec.expected_statuses
    if not ok_status:
        return {
            "check_id": spec.check_id,
            "label": spec.label,
            "url": spec.url,
            "required": spec.required,
            "expected_statuses": list(spec.expected_statuses),
            "actual_status": status_code,
            "status": "blocked_by_environment",
            "blocked": True,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "reason": "worker_status_probe_failed",
            "detail": f"backend worker readiness probe returned unexpected HTTP {status_code}",
            "recommended_command": spec.recommended_command,
            "body_sample": body_sample[:240],
        }
    if not evidence["worker_online"]:
        worker_count = evidence["worker_count"]
        count_detail = "unknown worker count" if worker_count is None else f"{worker_count} Celery workers"
        return {
            "check_id": spec.check_id,
            "label": spec.label,
            "url": spec.url,
            "required": spec.required,
            "expected_statuses": list(spec.expected_statuses),
            "actual_status": status_code,
            "status": "blocked_by_environment",
            "blocked": True,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "reason": "celery_worker_unavailable",
            "detail": f"backend process stats reported {count_detail}; async task lane is not ready",
            "recommended_command": spec.recommended_command,
            "worker_online": evidence["worker_online"],
            "worker_count": worker_count,
            "worker_names": evidence["worker_names"],
            "raw_status": evidence["raw_status"],
        }

    return {
        "check_id": spec.check_id,
        "label": spec.label,
        "url": spec.url,
        "required": spec.required,
        "expected_statuses": list(spec.expected_statuses),
        "actual_status": status_code,
        "status": "passed",
        "blocked": False,
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "detail": "backend process stats report at least one Celery worker",
        "worker_online": evidence["worker_online"],
        "worker_count": evidence["worker_count"],
        "worker_names": evidence["worker_names"],
        "raw_status": evidence["raw_status"],
    }


def build_mode_specs(
    *,
    backend_base_url: str,
    local_frontend_url: str,
    docker_frontend_url: str,
) -> Annotated[
    list[RuntimeModeSpec],
    "kit:prepared-command "
    "effect_boundary=passive_runtime_endpoint_port_and_worker_probes "
    "witness=test:test_w12_runtime_misc_laws",
]:
    backend = backend_base_url.rstrip("/")
    local_frontend = local_frontend_url.rstrip("/")
    docker_frontend = docker_frontend_url.rstrip("/")
    backend_host, backend_port = _url_host_port(backend)
    local_frontend_host, local_frontend_port = _url_host_port(local_frontend)
    docker_frontend_host, docker_frontend_port = _url_host_port(docker_frontend)

    dependency_ports = (
        PortSpec("postgres_port", "PostgreSQL/pgvector", "127.0.0.1", 5432),
        PortSpec("redis_port", "Redis", "127.0.0.1", 6379),
        PortSpec("elasticsearch_port", "Elasticsearch", "127.0.0.1", 9200),
    )
    backend_endpoints = (
        EndpointSpec("backend_health", "Backend health", f"{backend}/api/v1/health"),
        EndpointSpec("backend_deep_health", "Backend deep health", f"{backend}/api/v1/health/deep"),
    )
    async_readiness = (
        WorkerReadinessSpec(
            "celery_worker_process_stats",
            "Celery worker readiness via backend process stats",
            f"{backend}/api/v1/process/stats",
            recommended_command="./scripts/local-deploy.sh start",
        ),
    )
    backend_port_spec = PortSpec("backend_port", "Backend API", backend_host or "127.0.0.1", backend_port or 8000)

    return [
        RuntimeModeSpec(
            mode="local",
            description="Host backend and Vite dev frontend; dependencies may be host-local or Docker-published ports.",
            endpoints=(
                *backend_endpoints,
                EndpointSpec("frontend_local_root", "Local Vite frontend", local_frontend, expected_statuses=(200, 304)),
            ),
            ports=(
                backend_port_spec,
                PortSpec("frontend_local_port", "Local Vite frontend", local_frontend_host or "127.0.0.1", local_frontend_port or 5173),
                *dependency_ports,
            ),
            recommended_commands=(
                "./scripts/local-deploy.sh status",
                "./scripts/local-deploy.sh health",
                "./scripts/local-deploy.sh start",
            ),
            async_readiness=async_readiness,
        ),
        RuntimeModeSpec(
            mode="docker",
            description="Docker compose backend, dependency services, and modern-ui frontend profile.",
            endpoints=(
                *backend_endpoints,
                EndpointSpec("frontend_docker_root", "Docker modern frontend", docker_frontend, expected_statuses=(200, 304)),
            ),
            ports=(
                backend_port_spec,
                PortSpec("frontend_docker_port", "Docker modern frontend", docker_frontend_host or "127.0.0.1", docker_frontend_port or 5174),
                *dependency_ports,
                PortSpec("launcher_ui_port", "Docker launcher UI", "127.0.0.1", 5176, required=False),
                PortSpec("launcher_agent_port", "Docker launcher agent", "127.0.0.1", 8787, required=False),
            ),
            recommended_commands=(
                "./scripts/docker-deploy.sh status",
                "./scripts/docker-deploy.sh health",
                "./scripts/docker-deploy.sh start --profile modern-ui",
            ),
            async_readiness=(
                WorkerReadinessSpec(
                    "celery_worker_process_stats",
                    "Celery worker readiness via backend process stats",
                    f"{backend}/api/v1/process/stats",
                    recommended_command="./scripts/docker-deploy.sh start --profile modern-ui",
                ),
            ),
        ),
        RuntimeModeSpec(
            mode="mixed",
            description="Host frontend/backend surfaces with Docker-published dependency ports, or local frontend against Docker backend.",
            endpoints=(
                *backend_endpoints,
                EndpointSpec("frontend_local_root", "Local Vite frontend", local_frontend, expected_statuses=(200, 304)),
            ),
            ports=(backend_port_spec, PortSpec("frontend_local_port", "Local Vite frontend", local_frontend_host or "127.0.0.1", local_frontend_port or 5173), *dependency_ports),
            recommended_commands=(
                "./scripts/local-deploy.sh status",
                "./scripts/docker-deploy.sh status",
                "VITE_API_PROXY_TARGET=http://127.0.0.1:8000 npm --prefix main/frontend-modern run dev",
            ),
            async_readiness=async_readiness,
        ),
    ]


def classify_mode(
    endpoint_results: list[dict[str, Any]],
    port_results: list[dict[str, Any]],
    async_readiness_results: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    required = [item for item in [*endpoint_results, *port_results, *async_readiness_results] if item.get("required")]
    blocked = [item for item in required if item.get("status") == "blocked_by_environment"]
    failed = [item for item in required if item.get("status") == "failed"]
    async_result_ids = {id(item) for item in async_readiness_results}
    non_async_blocked = [item for item in blocked if id(item) not in async_result_ids]
    if failed:
        return "failed", blocked, failed
    if blocked and not non_async_blocked:
        return "worker_blocked", blocked, failed
    if blocked:
        return "blocked_by_environment", blocked, failed
    return "passed", blocked, failed


def build_matrix(
    specs: list[RuntimeModeSpec],
    *,
    timeout: float,
    endpoint_probe: Callable[[EndpointSpec, float], dict[str, Any]] | None = None,
    port_probe: Callable[[PortSpec, float], dict[str, Any]] | None = None,
    worker_readiness_probe: Callable[[WorkerReadinessSpec, float], dict[str, Any]] | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=generated_evidence "
    "fact_source=runtime_mode_endpoint_port_and_worker_probe_results "
    "witness=test:test_w12_runtime_misc_laws",
]:
    endpoint_probe = endpoint_probe or (lambda spec, timeout: probe_endpoint(spec, timeout=timeout))
    port_probe = port_probe or (lambda spec, timeout: probe_port(spec, timeout=timeout))
    worker_readiness_probe = worker_readiness_probe or (lambda spec, timeout: probe_worker_readiness(spec, timeout=timeout))

    modes = []
    for spec in specs:
        endpoint_results = [endpoint_probe(endpoint, timeout) for endpoint in spec.endpoints]
        port_results = [port_probe(port, timeout) for port in spec.ports]
        async_readiness_results = [worker_readiness_probe(readiness, timeout) for readiness in spec.async_readiness]
        status, blocked, failed = classify_mode(endpoint_results, port_results, async_readiness_results)
        modes.append(
            {
                "mode": spec.mode,
                "status": status,
                "description": spec.description,
                "blocked_by_environment": [
                    {
                        "check_id": item.get("check_id"),
                        "label": item.get("label"),
                        "reason": item.get("reason") or item.get("status"),
                        "detail": item.get("detail"),
                        "recommended_command": item.get("recommended_command") or (spec.recommended_commands[0] if spec.recommended_commands else None),
                    }
                    for item in blocked
                ],
                "failures": [
                    {
                        "check_id": item.get("check_id"),
                        "label": item.get("label"),
                        "actual_status": item.get("actual_status"),
                        "expected_statuses": item.get("expected_statuses"),
                        "detail": item.get("detail") or item.get("body_sample"),
                    }
                    for item in failed
                ],
                "checked_endpoints": endpoint_results,
                "checked_ports": port_results,
                "checked_async_readiness": async_readiness_results,
                "recommended_commands": list(spec.recommended_commands),
                "not_probed_reason": spec.not_probed_reason,
            }
        )

    statuses = [mode["status"] for mode in modes]
    if all(status == "passed" for status in statuses):
        overall_status = "passed"
    elif any(status == "failed" for status in statuses):
        overall_status = "failed"
    elif all(status == "worker_blocked" for status in statuses):
        overall_status = "worker_blocked"
    elif any(status == "passed" for status in statuses):
        overall_status = "passed_with_blocked_modes"
    else:
        overall_status = "blocked_by_environment"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_utc(),
        "generated_by": "scripts/runtime_health_matrix.py",
        "probe_policy": {
            "mode": "passive_host_probe_only",
            "starts_services": False,
            "timeout_seconds": timeout,
        },
        "status": overall_status,
        "runtime_modes": modes,
        "recommended_commands": {
            "local": ["./scripts/local-deploy.sh status", "./scripts/local-deploy.sh health", "./scripts/local-deploy.sh start"],
            "docker": ["./scripts/docker-deploy.sh status", "./scripts/docker-deploy.sh health", "./scripts/docker-deploy.sh start --profile modern-ui"],
            "mixed": ["./scripts/local-deploy.sh status", "./scripts/docker-deploy.sh status"],
        },
    }


def determine_exit_code(matrix: dict[str, Any], *, allow_blocked: bool) -> int:
    status = matrix.get("status")
    if status == "failed":
        return 1
    if status in {"blocked_by_environment", "passed_with_blocked_modes", "worker_blocked"} and not allow_blocked:
        return 3
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a structured MRW full-stack runtime health matrix.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"JSON artifact path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--allow-blocked", action="store_true", help="Exit 0 when required services are environment-blocked.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-port/per-endpoint probe timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument("--backend-base-url", default="http://127.0.0.1:8000", help="Backend base URL to probe.")
    parser.add_argument("--local-frontend-url", default="http://127.0.0.1:5173", help="Local Vite frontend URL to probe.")
    parser.add_argument("--docker-frontend-url", default="http://127.0.0.1:5174", help="Docker modern-ui frontend URL to probe.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    specs = build_mode_specs(
        backend_base_url=args.backend_base_url,
        local_frontend_url=args.local_frontend_url,
        docker_frontend_url=args.docker_frontend_url,
    )
    matrix = build_matrix(specs, timeout=args.timeout)
    output = Path(args.output)
    if not output.is_absolute():
        output = repo_root() / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(matrix, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[runtime-matrix] status={matrix['status']} artifact={output}")
    return determine_exit_code(matrix, allow_blocked=args.allow_blocked)


if __name__ == "__main__":
    raise SystemExit(main())
