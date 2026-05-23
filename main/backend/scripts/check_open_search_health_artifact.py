#!/usr/bin/env python3
"""Wave18 local open-search health artifact checker.

Records SearXNG/YaCy endpoint configuration, compose expectations, current
service status, and bounded live probe facts. The checker is read-only: it does
not start Docker services and never converts a live probe into a closure claim.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.check_open_search_runtime_boundary import (  # noqa: E402
    LOCAL_OPEN_SEARCH_FAMILY,
    OPEN_SEARCH_TOPIC_DIRS,
    PROVIDERS,
    WAVE12_SUMMARY,
    _first_existing_path,
    build_contract as build_runtime_boundary_contract,
    display_path,
    endpoint_config,
    load_json,
)


DEFAULT_OUT = Path(
    "development/latest-dev-docs/automation-runs/"
    "wave18-open-search-health-artifact/2026-05-22/open_search_health_artifact.json"
)
TOPIC_DOC = _first_existing_path(
    *(
        topic_dir / "14_wave18-open-search-health-artifact-2026-05-22.md"
        for topic_dir in OPEN_SEARCH_TOPIC_DIRS
    )
).relative_to(REPO_ROOT)
SEARCH_LAB_COMPOSE = Path("ops/search-lab/docker-compose.yml")
MAIN_OPS_COMPOSE = Path("main/ops/docker-compose.yml")
LAUNCHER_SURFACES = {
    "local_launcher": Path("scripts/launch.py"),
    "launcher_ui_settings": Path("main/ops/launcher-ui/settings.js"),
    "configure_external_services": Path("scripts/configure-external-services.py"),
    "backend_env_example": Path("main/backend/.env.example"),
    "search_provider_code": Path("main/backend/app/services/search/web.py"),
}
PROVIDER_EXPECTATIONS: dict[str, dict[str, Any]] = {
    "searxng": {
        "image_prefix": "searxng/searxng",
        "search_lab_container_name": "mrw-search-lab-searxng",
        "public_endpoint": "http://127.0.0.1:8088",
        "internal_endpoint": "http://searxng:8080",
        "published_port": 8088,
        "target_port": 8080,
        "query_path": "/search",
    },
    "yacy": {
        "image_prefix": "yacy/yacy_search_server",
        "search_lab_container_name": "mrw-search-lab-yacy",
        "public_endpoint": "http://127.0.0.1:8090",
        "internal_endpoint": "http://yacy:8090",
        "published_port": 8090,
        "target_port": 8090,
        "query_path": "/yacysearch.json",
    },
}


CommandRunner = Callable[[list[str], Path, int], dict[str, Any]]


def _read_text(path: Path) -> str:
    absolute = REPO_ROOT / path
    if not absolute.is_file():
        return ""
    return absolute.read_text(encoding="utf-8", errors="replace")


def _normalise_env(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    result: dict[str, str] = {}
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                key, _, val = item.partition("=")
                if key:
                    result[key] = val
    return result


def _load_compose(path: Path) -> tuple[dict[str, Any], list[str]]:
    absolute = REPO_ROOT / path
    if not absolute.is_file():
        return {}, [f"missing compose file: {path}"]
    try:
        payload = yaml.safe_load(absolute.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return {}, [f"invalid compose yaml: {path}: {exc}"]
    if not isinstance(payload, dict) or not isinstance(payload.get("services"), dict):
        return {}, [f"compose file has no services mapping: {path}"]
    return payload, []


def _port_matches(entries: Any, *, published_port: int, target_port: int) -> bool:
    if not isinstance(entries, list):
        return False
    published = str(published_port)
    target = str(target_port)
    for entry in entries:
        if isinstance(entry, str):
            parts = entry.split(":")
            if len(parts) >= 2 and parts[-2] == published and parts[-1].split("/", 1)[0] == target:
                return True
            if len(parts) == 1 and parts[0].split("/", 1)[0] == target:
                return published == target
        elif isinstance(entry, dict):
            entry_published = str(entry.get("published") or entry.get("published_port") or "")
            entry_target = str(entry.get("target") or entry.get("target_port") or "")
            if entry_published == published and entry_target == target:
                return True
    return False


def _service_expectation(compose: dict[str, Any], provider: str, *, compose_name: str) -> dict[str, Any]:
    service = (compose.get("services") or {}).get(provider)
    expected = PROVIDER_EXPECTATIONS[provider]
    if not isinstance(service, dict):
        return {
            "service": provider,
            "service_present": False,
            "failures": [f"{compose_name}:{provider} service missing"],
        }

    failures: list[str] = []
    image = str(service.get("image") or "")
    ports = service.get("ports") or []
    profiles = service.get("profiles") or []
    if not image.startswith(str(expected["image_prefix"])):
        failures.append(f"{compose_name}:{provider} image does not start with {expected['image_prefix']}")
    if not _port_matches(
        ports,
        published_port=int(expected["published_port"]),
        target_port=int(expected["target_port"]),
    ):
        failures.append(
            f"{compose_name}:{provider} missing {expected['published_port']}:{expected['target_port']} port mapping"
        )
    if compose_name == "main_ops" and "search-enhancements" not in profiles:
        failures.append(f"{compose_name}:{provider} missing search-enhancements profile")
    if compose_name == "search_lab" and service.get("container_name") != expected["search_lab_container_name"]:
        failures.append(f"{compose_name}:{provider} container_name expected {expected['search_lab_container_name']}")

    return {
        "service": provider,
        "service_present": True,
        "image": image,
        "ports": ports,
        "profiles": profiles,
        "environment": _normalise_env(service.get("environment")),
        "expected_public_endpoint": expected["public_endpoint"],
        "expected_query_path": expected["query_path"],
        "port_expectation_met": not any("port mapping" in item for item in failures),
        "failures": failures,
    }


def build_compose_expectations() -> dict[str, Any]:
    search_lab, search_lab_failures = _load_compose(SEARCH_LAB_COMPOSE)
    main_ops, main_ops_failures = _load_compose(MAIN_OPS_COMPOSE)
    failures = [*search_lab_failures, *main_ops_failures]
    providers: dict[str, Any] = {}
    for provider in PROVIDERS:
        search_lab_row = _service_expectation(search_lab, provider, compose_name="search_lab") if search_lab else {
            "service": provider,
            "service_present": False,
            "failures": [f"search_lab:{provider} compose unavailable"],
        }
        main_ops_row = _service_expectation(main_ops, provider, compose_name="main_ops") if main_ops else {
            "service": provider,
            "service_present": False,
            "failures": [f"main_ops:{provider} compose unavailable"],
        }
        provider_failures = [*search_lab_row.get("failures", []), *main_ops_row.get("failures", [])]
        providers[provider] = {
            "provider": provider,
            "search_lab": search_lab_row,
            "main_ops": main_ops_row,
            "all_expected_surfaces_present": not provider_failures,
            "failures": provider_failures,
        }
        failures.extend(provider_failures)

    backend_env: dict[str, str] = {}
    if main_ops:
        backend = (main_ops.get("services") or {}).get("backend") or {}
        if isinstance(backend, dict):
            backend_env = _normalise_env(backend.get("environment"))
    backend_checks = {
        "SEARXNG_BASE_URL": "http://searxng:8080" in str(backend_env.get("SEARXNG_BASE_URL", "")),
        "YACY_BASE_URL": "http://yacy:8090" in str(backend_env.get("YACY_BASE_URL", "")),
        "YACY_RESOURCE_MODE": "local" in str(backend_env.get("YACY_RESOURCE_MODE", "")),
    }
    for key, ok in backend_checks.items():
        if not ok:
            failures.append(f"main_ops backend environment missing expected {key}")

    return {
        "compose_files": {
            "search_lab": display_path(REPO_ROOT / SEARCH_LAB_COMPOSE),
            "main_ops": display_path(REPO_ROOT / MAIN_OPS_COMPOSE),
        },
        "providers": providers,
        "backend_environment": {
            "path": display_path(REPO_ROOT / MAIN_OPS_COMPOSE),
            "checks": backend_checks,
            "values": {key: backend_env.get(key) for key in backend_checks},
        },
        "failures": failures,
    }


def launcher_and_provider_surfaces() -> dict[str, Any]:
    surfaces: dict[str, Any] = {}
    for name, path in LAUNCHER_SURFACES.items():
        text = _read_text(path)
        surfaces[name] = {
            "path": display_path(REPO_ROOT / path),
            "exists": bool(text),
            "has_searxng_base_url": "SEARXNG_BASE_URL" in text,
            "has_yacy_base_url": "YACY_BASE_URL" in text,
            "has_explicit_searxng_provider": 'provider == "searxng"' in text,
            "has_explicit_yacy_provider": 'provider == "yacy"' in text,
            "mentions_local_open_search": LOCAL_OPEN_SEARCH_FAMILY in text,
        }
    return surfaces


def _run_command(cmd: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "ok": proc.returncode == 0,
        }
    except (subprocess.SubprocessError, TimeoutError) as exc:
        return {
            "cmd": cmd,
            "returncode": None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "stdout": "",
            "stderr": str(exc),
            "ok": False,
            "error_type": exc.__class__.__name__,
        }


def _parse_json_stream(raw: str) -> list[dict[str, Any]]:
    if not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            rows.append({"raw": text})
            continue
        if isinstance(row, dict):
            rows.append(row)
        elif isinstance(row, list):
            rows.extend(item for item in row if isinstance(item, dict))
    return rows


def _provider_status(rows: list[dict[str, Any]], provider: str, *, command_ok: bool, stderr: str) -> dict[str, Any]:
    if not command_ok:
        return {
            "provider": provider,
            "observed": False,
            "state": "unknown",
            "running": False,
            "status_reason": stderr or "docker_status_command_failed",
        }
    for row in rows:
        service = str(row.get("Service") or row.get("service") or "")
        names = str(row.get("Name") or row.get("Names") or "")
        if service == provider or provider in names:
            raw_state = str(row.get("State") or row.get("state") or "").lower()
            raw_status = str(row.get("Status") or row.get("status") or "")
            running = raw_state == "running" or raw_status.lower().startswith("up")
            return {
                "provider": provider,
                "observed": True,
                "state": "running" if running else (raw_state or "unknown"),
                "running": running,
                "raw_state": row.get("State") or row.get("state"),
                "raw_status": row.get("Status") or row.get("status"),
                "name": row.get("Name") or row.get("Names"),
                "ports": row.get("Ports") or row.get("Publishers"),
            }
    return {
        "provider": provider,
        "observed": False,
        "state": "not_running",
        "running": False,
        "status_reason": "service_not_present_in_compose_ps",
    }


def collect_current_service_status(command_runner: CommandRunner | None = None) -> dict[str, Any]:
    runner = command_runner or _run_command
    result: dict[str, Any] = {
        "collector": "docker compose ps --format json; read-only, does not start services",
        "compose": {},
    }
    for name, path in {"search_lab": SEARCH_LAB_COMPOSE, "main_ops": MAIN_OPS_COMPOSE}.items():
        cmd = ["docker", "compose", "-f", str(path), "ps", "--format", "json"]
        command = runner(cmd, REPO_ROOT, 10)
        rows = _parse_json_stream(command.get("stdout") or "")
        result["compose"][name] = {
            "path": display_path(REPO_ROOT / path),
            "command": {
                "cmd": command.get("cmd", cmd),
                "returncode": command.get("returncode"),
                "ok": bool(command.get("ok")),
                "stderr": command.get("stderr") or "",
                "latency_ms": command.get("latency_ms"),
            },
            "raw_count": len(rows),
            "providers": {
                provider: _provider_status(
                    rows,
                    provider,
                    command_ok=bool(command.get("ok")),
                    stderr=str(command.get("stderr") or ""),
                )
                for provider in PROVIDERS
            },
        }
    return result


def _provider_running_anywhere(status: dict[str, Any], provider: str) -> bool:
    return any(
        bool((row.get("providers") or {}).get(provider, {}).get("running"))
        for row in (status.get("compose") or {}).values()
        if isinstance(row, dict)
    )


def _provider_status_summary(status: dict[str, Any], provider: str) -> dict[str, Any]:
    return {
        name: (row.get("providers") or {}).get(provider, {})
        for name, row in (status.get("compose") or {}).items()
        if isinstance(row, dict)
    }


def _wave12_provider_summary(wave12: dict[str, Any], provider: str) -> dict[str, Any]:
    row = ((wave12.get("provider_availability") or {}).get("providers") or {}).get(provider) or {}
    return {
        "status": wave12.get("status"),
        "readiness_state": wave12.get("readiness_state"),
        "provider_route": row.get("provider_route"),
        "provider_family": row.get("provider_family"),
        "provider_auto_included": row.get("provider_auto_included"),
        "live_probe_status": row.get("live_probe_status"),
        "live_result_count": row.get("live_result_count"),
        "live_fallback_reason": row.get("live_fallback_reason"),
    }


def build_health_artifact(
    *,
    enable_live_probe: bool = True,
    probe_timeout: float = 0.2,
    env: Mapping[str, str] | None = None,
    command_runner: CommandRunner | None = None,
    runtime_boundary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failures: list[str] = []
    wave12, load_failures = load_json(WAVE12_SUMMARY)
    failures.extend(load_failures)
    boundary = runtime_boundary or build_runtime_boundary_contract(
        enable_live_probe=enable_live_probe,
        probe_timeout=probe_timeout,
        env=env,
    )
    compose_expectations = build_compose_expectations()
    service_status = collect_current_service_status(command_runner)
    surfaces = launcher_and_provider_surfaces()

    provider_health: dict[str, Any] = {}
    runtime_rows = boundary.get("provider_runtime_boundaries") or {}
    for provider in PROVIDERS:
        runtime = runtime_rows.get(provider) or {}
        endpoint = endpoint_config(provider, env=env)
        boundary_classification = runtime.get("boundary_classification")
        current_running = _provider_running_anywhere(service_status, provider)
        facts = {
            "configured_endpoint_valid": endpoint.get("endpoint_state") == "configured_endpoint",
            "compose_service_expected": bool(
                (compose_expectations.get("providers") or {}).get(provider, {}).get("all_expected_surfaces_present")
            ),
            "search_provider_explicit_only": runtime.get("provider_route") == f"explicit:{provider}"
            and runtime.get("provider_family") == LOCAL_OPEN_SEARCH_FAMILY
            and runtime.get("provider_auto_included") is False,
            "current_service_running": current_running,
            "live_probe_open": enable_live_probe,
            "service_not_started_connect_error": boundary_classification == "service_not_started_connect_error",
            "live_query_unsealed": boundary_classification == "live_query_unsealed",
            "no_live_closure_claim": runtime.get("live_closure_claim_allowed") is False,
            "no_provider_auto_promotion": runtime.get("provider_auto_promotion_allowed") is False,
        }
        provider_health[provider] = {
            "provider": provider,
            "provider_route": f"explicit:{provider}",
            "provider_family": LOCAL_OPEN_SEARCH_FAMILY,
            "provider_auto_included": False,
            "configured_endpoint": endpoint,
            "compose_expectations": (compose_expectations.get("providers") or {}).get(provider, {}),
            "current_service_status": _provider_status_summary(service_status, provider),
            "wave12_readiness": _wave12_provider_summary(wave12, provider),
            "wave15_runtime_boundary": {
                "runtime_state": runtime.get("runtime_state"),
                "boundary_classification": boundary_classification,
                "live_probe_status": runtime.get("live_probe_status"),
                "live_result_count": runtime.get("live_result_count"),
                "fallback_reason": runtime.get("fallback_reason"),
                "error_type": runtime.get("error_type"),
                "live_closure_claim_allowed": runtime.get("live_closure_claim_allowed"),
                "provider_auto_promotion_allowed": runtime.get("provider_auto_promotion_allowed"),
            },
            "facts": facts,
        }

    artifact: dict[str, Any] = {
        "contract_version": "wave18-open-search-health-artifact.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "main/backend/scripts/check_open_search_health_artifact.py",
        "scope": "configured_endpoints_compose_expectations_current_service_status_live_probe_no_container_start",
        "health_state": "partial",
        "closure_claim_allowed": False,
        "provider_auto_promotion_allowed": False,
        "live_probe": {
            "open": enable_live_probe,
            "timeout_seconds": probe_timeout,
            "does_not_start_services": True,
        },
        "inputs": {
            "wave12_provider_readiness": {
                "path": display_path(WAVE12_SUMMARY),
                "status": wave12.get("status"),
                "readiness_state": wave12.get("readiness_state"),
            },
            "wave15_runtime_boundary": {
                "generated_by": boundary.get("generated_by"),
                "status": boundary.get("status"),
                "boundary_state": boundary.get("boundary_state"),
                "external_runtime_gap": boundary.get("external_runtime_gap"),
                "closure_claim_allowed": boundary.get("closure_claim_allowed"),
            },
            "topic_doc": display_path(REPO_ROOT / TOPIC_DOC),
        },
        "launcher_and_provider_surfaces": surfaces,
        "compose_expectations": compose_expectations,
        "current_service_status": service_status,
        "provider_health": provider_health,
        "unsupported_claims": [
            {
                "code": "service_status_not_live_closure",
                "claim": "Configured compose services prove current SearXNG/YaCy live availability.",
                "reason": "Compose expectations prove repo wiring only; Docker may be stopped and endpoint probes may fail.",
            },
            {
                "code": "live_probe_not_quality_closure",
                "claim": "A bounded live probe proves provider quality or provider=auto promotion.",
                "reason": "A probe is a runtime fact only; quality, freshness, latency stability, and approval policy remain unclosed.",
            },
        ],
        "failures": failures,
    }
    artifact["failures"].extend(validate_health_artifact(artifact))
    artifact["status"] = "passed" if not artifact["failures"] else "failed"
    return artifact


def validate_health_artifact(artifact: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if artifact.get("closure_claim_allowed") is not False:
        failures.append("closure_claim_allowed must be false")
    if artifact.get("provider_auto_promotion_allowed") is not False:
        failures.append("provider_auto_promotion_allowed must be false")
    live_probe = artifact.get("live_probe") or {}
    if live_probe.get("does_not_start_services") is not True:
        failures.append("live probe must be documented as no-container-start")
    if live_probe.get("open") is not True:
        failures.append("default health artifact must record live_probe_open=true")

    inputs = artifact.get("inputs") or {}
    wave12 = inputs.get("wave12_provider_readiness") or {}
    wave15 = inputs.get("wave15_runtime_boundary") or {}
    if wave12.get("status") != "passed":
        failures.append("Wave12 provider readiness input must be passed")
    if wave15.get("status") != "passed":
        failures.append("Wave15 runtime boundary input must be passed")
    if wave15.get("closure_claim_allowed") is not False:
        failures.append("Wave15 runtime boundary must not allow closure")

    for item in (artifact.get("compose_expectations") or {}).get("failures") or []:
        failures.append(str(item))
    surfaces = artifact.get("launcher_and_provider_surfaces") or {}
    for name in ("local_launcher", "launcher_ui_settings", "configure_external_services", "backend_env_example"):
        surface = surfaces.get(name) or {}
        if surface.get("has_searxng_base_url") is not True:
            failures.append(f"{name} missing SEARXNG_BASE_URL")
        if surface.get("has_yacy_base_url") is not True:
            failures.append(f"{name} missing YACY_BASE_URL")
    provider_code = surfaces.get("search_provider_code") or {}
    if provider_code.get("has_explicit_searxng_provider") is not True:
        failures.append("search provider code missing explicit searxng route")
    if provider_code.get("has_explicit_yacy_provider") is not True:
        failures.append("search provider code missing explicit yacy route")

    allowed_classes = {
        "service_not_started_connect_error",
        "service_unreachable_timeout",
        "endpoint_responded_with_http_error",
        "endpoint_query_error",
        "endpoint_returned_non_contract_json",
        "live_query_unsealed",
    }
    for provider in PROVIDERS:
        row = (artifact.get("provider_health") or {}).get(provider) or {}
        facts = row.get("facts") or {}
        runtime = row.get("wave15_runtime_boundary") or {}
        if row.get("provider_route") != f"explicit:{provider}":
            failures.append(f"{provider} route must remain explicit")
        if row.get("provider_family") != LOCAL_OPEN_SEARCH_FAMILY:
            failures.append(f"{provider} provider_family must be {LOCAL_OPEN_SEARCH_FAMILY}")
        if row.get("provider_auto_included") is not False:
            failures.append(f"{provider} provider_auto_included must be false")
        for fact_name in (
            "configured_endpoint_valid",
            "compose_service_expected",
            "search_provider_explicit_only",
            "live_probe_open",
            "service_not_started_connect_error",
            "live_query_unsealed",
            "no_live_closure_claim",
            "no_provider_auto_promotion",
        ):
            if fact_name not in facts:
                failures.append(f"{provider} missing fact {fact_name}")
        if facts.get("configured_endpoint_valid") is not True:
            failures.append(f"{provider} configured endpoint is invalid")
        if facts.get("compose_service_expected") is not True:
            failures.append(f"{provider} compose service expectation failed")
        if facts.get("search_provider_explicit_only") is not True:
            failures.append(f"{provider} search provider route is not explicit-only")
        if facts.get("live_probe_open") is not True:
            failures.append(f"{provider} live_probe_open must be true")
        if facts.get("no_live_closure_claim") is not True:
            failures.append(f"{provider} live closure claim must remain false")
        if facts.get("no_provider_auto_promotion") is not True:
            failures.append(f"{provider} provider auto promotion must remain false")

        classification = runtime.get("boundary_classification")
        if classification == "service_not_started_connect_error" and facts.get("service_not_started_connect_error") is not True:
            failures.append(f"{provider} service_not_started_connect_error fact is inconsistent")
        if classification == "live_query_unsealed" and facts.get("live_query_unsealed") is not True:
            failures.append(f"{provider} live_query_unsealed fact is inconsistent")
        if classification not in allowed_classes:
            failures.append(f"{provider} unexpected runtime boundary classification {classification!r}")
        if facts.get("current_service_running") is False and runtime.get("live_closure_claim_allowed") is not False:
            failures.append(f"{provider} stopped service must not have live closure claim")
    return failures


def write_output(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Wave18 open-search health artifact.")
    parser.add_argument("--json", action="store_true", help="Print full artifact JSON.")
    parser.add_argument("--write-output", type=Path, help=f"Write full artifact JSON. Suggested: {DEFAULT_OUT}")
    parser.add_argument("--skip-live-probe", action="store_true", help="Skip the bounded endpoint probe.")
    parser.add_argument("--probe-timeout", type=float, default=0.2, help="Bounded live probe timeout in seconds.")
    args = parser.parse_args(argv)

    artifact = build_health_artifact(
        enable_live_probe=not args.skip_live_probe,
        probe_timeout=args.probe_timeout,
    )
    if args.write_output is not None:
        output_path = args.write_output
        if not output_path.is_absolute():
            output_path = REPO_ROOT / output_path
        write_output(output_path, artifact)

    if args.json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        provider_bits = " ".join(
            f"{provider}={row['wave15_runtime_boundary'].get('boundary_classification')}:"
            f"{row['wave15_runtime_boundary'].get('live_probe_status')}"
            for provider, row in artifact["provider_health"].items()
        )
        print(
            "OK open_search_health_artifact={status} health_state={health_state} "
            "closure_claim_allowed={closure} live_probe_open={live_probe} {providers}".format(
                status=artifact["status"],
                health_state=artifact["health_state"],
                closure=str(bool(artifact["closure_claim_allowed"])).lower(),
                live_probe=str(bool(artifact["live_probe"]["open"])).lower(),
                providers=provider_bits,
            )
        )
        if artifact["failures"]:
            print(json.dumps({"failures": artifact["failures"]}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 0 if artifact["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
