#!/usr/bin/env python3
"""Wave15 local open-search runtime boundary gate.

The gate separates three facts that were previously easy to blur:

* SearXNG/YaCy endpoints are configured in repo-local config surfaces.
* The current external runtime may simply be stopped or unreachable.
* Even a successful live query is not enough to seal provider quality or
  provider=auto promotion.

It deliberately does not start Docker containers.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.http.client import HttpClient  # noqa: E402
from app.services.search import web  # noqa: E402


PROVIDERS = ("searxng", "yacy")
LOCAL_OPEN_SEARCH_FAMILY = "local_open_search"
DEFAULT_PROBE_KEYWORD = "marketworkflow wave15 runtime boundary"
DEFAULT_OUT = Path("development/latest-dev-docs/automation-runs/wave15-open-search-runtime-boundary/2026-05-22/open_search_runtime_boundary.json")

WAVE6_9_DOC = REPO_ROOT / (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-05-14-local-open-search-provider-isolation/"
    "11_wave6-9-status-evidence-and-min-plan-2026-05-22.md"
)
WAVE12_SUMMARY = REPO_ROOT / (
    "development/latest-dev-docs/automation-runs/wave12-provider-readiness/"
    "2026-05-22/provider_readiness_summary.json"
)
TRACE_CONTRACT = REPO_ROOT / (
    "development/latest-dev-docs/automation-runs/search-provider-trace-artifacts/"
    "2026-05-22/search_provider_trace_contract.json"
)
CONTAINER_REPLAY_SUMMARY = REPO_ROOT / (
    "development/latest-dev-docs/automation-runs/search-provider-container-replay/"
    "2026-05-22/provider_trace_replay_summary.json"
)


@dataclass(frozen=True)
class ProviderSpec:
    provider: str
    env_key: str
    default_base_url: str
    query_path: str


PROVIDER_SPECS = {
    "searxng": ProviderSpec(
        provider="searxng",
        env_key="SEARXNG_BASE_URL",
        default_base_url="http://127.0.0.1:8088",
        query_path="/search",
    ),
    "yacy": ProviderSpec(
        provider="yacy",
        env_key="YACY_BASE_URL",
        default_base_url="http://127.0.0.1:8090",
        query_path="/yacysearch.json",
    ),
}


SearchRunner = Callable[[str, str, int], list[dict[str, Any]]]


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.is_file():
        return {}, [f"missing artifact: {display_path(path)}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"artifact is not valid JSON: {display_path(path)}: {exc}"]
    if not isinstance(payload, dict):
        return {}, [f"artifact is not a JSON object: {display_path(path)}"]
    return payload, []


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def config_surface_evidence() -> dict[str, Any]:
    env_example = _read_text(REPO_ROOT / "main/backend/.env.example")
    configure_services = _read_text(REPO_ROOT / "scripts/configure-external-services.py")
    search_service = _read_text(REPO_ROOT / "main/backend/app/services/search/web.py")

    return {
        "env_example": {
            "path": "main/backend/.env.example",
            "has_searxng_base_url": "SEARXNG_BASE_URL" in env_example,
            "has_yacy_base_url": "YACY_BASE_URL" in env_example,
            "has_yacy_resource_mode": "YACY_RESOURCE_MODE" in env_example,
        },
        "configure_external_services": {
            "path": "scripts/configure-external-services.py",
            "has_searxng_setting": "SEARXNG_BASE_URL" in configure_services,
            "has_yacy_setting": "YACY_BASE_URL" in configure_services,
        },
        "search_service": {
            "path": "main/backend/app/services/search/web.py",
            "has_explicit_searxng_provider": 'provider == "searxng"' in search_service,
            "has_explicit_yacy_provider": 'provider == "yacy"' in search_service,
            "auto_mentions_local_open_search": "local_open_search" in search_service,
        },
    }


def endpoint_config(provider: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    values = env if env is not None else os.environ
    spec = PROVIDER_SPECS[provider]
    raw_value = (values.get(spec.env_key) or "").strip()
    base_url = raw_value or spec.default_base_url
    parsed = urlparse(base_url)
    configured = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    return {
        "provider": provider,
        "env_key": spec.env_key,
        "base_url": base_url,
        "default_base_url": spec.default_base_url,
        "source": "env" if raw_value else "repo_default",
        "query_path": spec.query_path,
        "endpoint_state": "configured_endpoint" if configured else "invalid_endpoint",
        "configured": configured,
    }


def validate_provider_trace(provider: str, item: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    expected_route = f"explicit:{provider}"
    if item.get("provider_route") != expected_route:
        failures.append(f"provider_route expected {expected_route!r}, got {item.get('provider_route')!r}")
    if item.get("provider_family") != LOCAL_OPEN_SEARCH_FAMILY:
        failures.append(f"provider_family expected {LOCAL_OPEN_SEARCH_FAMILY!r}, got {item.get('provider_family')!r}")
    if item.get("provider_auto_included") is not False:
        failures.append("provider_auto_included must be false")
    trace = item.get("backend_trace")
    if not isinstance(trace, dict):
        failures.append("backend_trace must be a dict")
        return failures
    if trace.get("provider") != provider:
        failures.append(f"backend_trace.provider expected {provider!r}, got {trace.get('provider')!r}")
    if trace.get("provider_route") != expected_route:
        failures.append(f"backend_trace.provider_route expected {expected_route!r}, got {trace.get('provider_route')!r}")
    if trace.get("provider_family") != LOCAL_OPEN_SEARCH_FAMILY:
        failures.append(f"backend_trace.provider_family expected {LOCAL_OPEN_SEARCH_FAMILY!r}")
    if trace.get("auto_included") is not False:
        failures.append("backend_trace.auto_included must be false")
    return failures


def classify_probe_exception(exc: Exception) -> tuple[str, str, str]:
    error_type = exc.__class__.__name__
    message = str(exc)
    lowered = message.lower()
    if error_type in {"ConnectError", "ConnectTimeout"} or "connection refused" in lowered:
        return "service_not_started", "service_not_started_connect_error", error_type
    if "timed out" in lowered or error_type in {"ReadTimeout", "TimeoutException", "PoolTimeout"}:
        return "runtime_timeout", "service_unreachable_timeout", error_type
    if error_type == "HTTPStatusError":
        return "endpoint_http_error", "endpoint_responded_with_http_error", error_type
    if error_type in {"JSONDecodeError", "ValueError"}:
        return "malformed_response", "endpoint_returned_non_contract_json", error_type
    return "query_error", "endpoint_query_error", error_type


def _default_search_runner(provider: str, base_url: str, limit: int) -> list[dict[str, Any]]:
    if provider == "searxng":
        return web._searxng_search(DEFAULT_PROBE_KEYWORD, base_url, limit, language="en")
    if provider == "yacy":
        resource_mode = os.getenv("YACY_RESOURCE_MODE", "local").strip() or "local"
        return web._yacy_search(DEFAULT_PROBE_KEYWORD, base_url, limit, resource_mode=resource_mode)
    raise ValueError(f"unsupported provider: {provider}")


def probe_provider(
    provider: str,
    *,
    timeout: float,
    env: Mapping[str, str] | None = None,
    search_runner: SearchRunner | None = None,
) -> dict[str, Any]:
    endpoint = endpoint_config(provider, env=env)
    if not endpoint["configured"]:
        return {
            "provider": provider,
            "base_url": endpoint["base_url"],
            "runtime_state": "not_run",
            "boundary_classification": "invalid_endpoint",
            "live_probe_status": "blocked",
            "live_result_count": 0,
            "live_closure_claim_allowed": False,
            "provider_auto_promotion_allowed": False,
            "fallback_reason": "invalid_endpoint",
        }

    client = HttpClient(timeout=timeout, max_retries=0)
    original_client = web.default_http_client
    web.default_http_client = client
    started = time.perf_counter()
    try:
        runner = search_runner or _default_search_runner
        rows = runner(provider, endpoint["base_url"], 1)
        trace_failures = validate_provider_trace(provider, rows[0]) if rows else ["NoResults"]
        if rows and not trace_failures:
            runtime_state = "live_query_returned"
            boundary = "live_query_unsealed"
            live_probe_status = "ready"
            fallback_reason = None
        elif rows:
            runtime_state = "live_query_trace_failed"
            boundary = "live_query_unsealed"
            live_probe_status = "trace_failed"
            fallback_reason = "trace_contract_failed"
        else:
            runtime_state = "live_query_empty"
            boundary = "live_query_unsealed"
            live_probe_status = "empty"
            fallback_reason = "NoResults"
        return {
            "provider": provider,
            "base_url": endpoint["base_url"],
            "runtime_state": runtime_state,
            "boundary_classification": boundary,
            "live_probe_status": live_probe_status,
            "live_result_count": len(rows),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "trace_failures": trace_failures,
            "fallback_reason": fallback_reason,
            "sample_result": rows[0] if rows else None,
            "live_closure_claim_allowed": False,
            "provider_auto_promotion_allowed": False,
        }
    except Exception as exc:  # noqa: BLE001 - runtime boundary reports the blocker.
        runtime_state, boundary, error_type = classify_probe_exception(exc)
        return {
            "provider": provider,
            "base_url": endpoint["base_url"],
            "runtime_state": runtime_state,
            "boundary_classification": boundary,
            "live_probe_status": "unavailable",
            "live_result_count": 0,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "fallback_reason": error_type,
            "error_type": error_type,
            "error": str(exc),
            "live_closure_claim_allowed": False,
            "provider_auto_promotion_allowed": False,
        }
    finally:
        web.default_http_client = original_client
        try:
            client._client.close()
        except Exception:
            pass


def skipped_probe(provider: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    endpoint = endpoint_config(provider, env=env)
    return {
        "provider": provider,
        "base_url": endpoint["base_url"],
        "runtime_state": "not_run",
        "boundary_classification": "configured_endpoint_only"
        if endpoint["configured"]
        else "invalid_endpoint",
        "live_probe_status": "not_run",
        "live_result_count": 0,
        "fallback_reason": "live_probe_disabled",
        "live_closure_claim_allowed": False,
        "provider_auto_promotion_allowed": False,
    }


def _trace_contract_summary(trace_contract: dict[str, Any]) -> dict[str, Any]:
    auto_route = trace_contract.get("auto_route") or {}
    policy = trace_contract.get("provider_auto_policy") or {}
    explicit = trace_contract.get("explicit_results") or {}
    return {
        "path": display_path(TRACE_CONTRACT),
        "contract_version": trace_contract.get("contract_version"),
        "scope": trace_contract.get("scope"),
        "auto_local_open_search_called": auto_route.get("local_open_search_called"),
        "auto_searxng_called": auto_route.get("searxng_called"),
        "auto_yacy_called": auto_route.get("yacy_called"),
        "excluded_local_open_search_providers": policy.get("excluded_local_open_search_providers") or [],
        "explicit_result_providers": sorted(explicit.keys()),
    }


def _wave12_summary(wave12: dict[str, Any]) -> dict[str, Any]:
    providers = wave12.get("provider_availability", {}).get("providers", {}) or {}
    return {
        "path": display_path(WAVE12_SUMMARY),
        "contract_version": wave12.get("contract_version"),
        "status": wave12.get("status"),
        "readiness_state": wave12.get("readiness_state"),
        "provider_live_statuses": {
            provider: {
                "live_probe_status": row.get("live_probe_status"),
                "live_fallback_reason": row.get("live_fallback_reason"),
                "live_result_count": row.get("live_result_count"),
            }
            for provider, row in providers.items()
            if provider in PROVIDERS
        },
        "unsupported_claim_codes": [
            str(item.get("code"))
            for item in (wave12.get("unsupported_claims") or [])
            if isinstance(item, dict)
        ],
    }


def _container_replay_summary(container_replay: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": display_path(CONTAINER_REPLAY_SUMMARY),
        "ok": container_replay.get("ok"),
        "passed_rows": container_replay.get("passed_rows"),
        "failed_rows": container_replay.get("failed_rows"),
        "docker_compose_ok": container_replay.get("docker_compose_ok"),
        "docker_container_count": container_replay.get("docker_container_count"),
        "evidence_role": "prior replay evidence only; not proof that the current external runtime is live",
    }


def validate_contract(contract: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    surfaces = contract.get("config_surfaces") or {}
    env_example = surfaces.get("env_example") or {}
    configure = surfaces.get("configure_external_services") or {}
    search_service = surfaces.get("search_service") or {}
    for field in ("has_searxng_base_url", "has_yacy_base_url", "has_yacy_resource_mode"):
        if env_example.get(field) is not True:
            failures.append(f"env_example missing {field}")
    for field in ("has_searxng_setting", "has_yacy_setting"):
        if configure.get(field) is not True:
            failures.append(f"configure_external_services missing {field}")
    for field in ("has_explicit_searxng_provider", "has_explicit_yacy_provider"):
        if search_service.get(field) is not True:
            failures.append(f"search_service missing {field}")

    trace = contract.get("recorded_evidence", {}).get("search_provider_trace_contract") or {}
    if trace.get("auto_local_open_search_called") is not False:
        failures.append("trace contract does not exclude local open-search from provider=auto")
    excluded = set(trace.get("excluded_local_open_search_providers") or [])
    for provider in PROVIDERS:
        if provider not in excluded:
            failures.append(f"trace contract does not list {provider} as excluded from provider=auto")

    for provider, endpoint in (contract.get("configured_endpoints") or {}).items():
        if provider not in PROVIDERS:
            continue
        if endpoint.get("endpoint_state") != "configured_endpoint":
            failures.append(f"{provider} endpoint is not configured")

    for provider, row in (contract.get("provider_runtime_boundaries") or {}).items():
        if row.get("provider_route") != f"explicit:{provider}":
            failures.append(f"{provider} route is not explicit")
        if row.get("provider_family") != LOCAL_OPEN_SEARCH_FAMILY:
            failures.append(f"{provider} provider_family is not local_open_search")
        if row.get("provider_auto_included") is not False:
            failures.append(f"{provider} provider_auto_included must be false")
        if row.get("live_closure_claim_allowed") is not False:
            failures.append(f"{provider} live closure claim must remain false")
        if row.get("provider_auto_promotion_allowed") is not False:
            failures.append(f"{provider} provider=auto promotion must remain false")
        if not row.get("boundary_classification"):
            failures.append(f"{provider} boundary_classification is missing")
        if row.get("live_probe_status") == "trace_failed":
            failures.append(f"{provider} live query returned rows with invalid explicit provider trace")

    if contract.get("closure_claim_allowed") is not False:
        failures.append("closure_claim_allowed must be false")
    if contract.get("external_runtime_gap") != "retained":
        failures.append("external runtime gap must be retained")
    return failures


def build_contract(
    *,
    enable_live_probe: bool = True,
    probe_timeout: float = 1.0,
    env: Mapping[str, str] | None = None,
    search_runner: SearchRunner | None = None,
) -> dict[str, Any]:
    failures: list[str] = []
    trace_contract, load_failures = load_json(TRACE_CONTRACT)
    failures.extend(load_failures)
    wave12, load_failures = load_json(WAVE12_SUMMARY)
    failures.extend(load_failures)
    container_replay, load_failures = load_json(CONTAINER_REPLAY_SUMMARY)
    failures.extend(load_failures)
    if not WAVE6_9_DOC.is_file():
        failures.append(f"missing Wave6-9 evidence doc: {display_path(WAVE6_9_DOC)}")

    configured_endpoints = {
        provider: endpoint_config(provider, env=env)
        for provider in PROVIDERS
    }
    raw_probes = {
        provider: probe_provider(
            provider,
            timeout=probe_timeout,
            env=env,
            search_runner=search_runner,
        )
        if enable_live_probe
        else skipped_probe(provider, env=env)
        for provider in PROVIDERS
    }
    provider_runtime_boundaries: dict[str, dict[str, Any]] = {}
    for provider in PROVIDERS:
        provider_runtime_boundaries[provider] = {
            "provider": provider,
            "provider_route": f"explicit:{provider}",
            "provider_family": LOCAL_OPEN_SEARCH_FAMILY,
            "provider_auto_included": False,
            "configured_endpoint": configured_endpoints[provider],
            **raw_probes[provider],
        }

    contract: dict[str, Any] = {
        "contract_version": "open-search-runtime-boundary.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "main/backend/scripts/check_open_search_runtime_boundary.py",
        "scope": "configured_endpoint_current_probe_no_container_start_no_live_closure",
        "boundary_state": "partial",
        "external_runtime_gap": "retained",
        "closure_claim_allowed": False,
        "provider_auto_promotion_allowed": False,
        "config_surfaces": config_surface_evidence(),
        "configured_endpoints": configured_endpoints,
        "provider_runtime_boundaries": provider_runtime_boundaries,
        "recorded_evidence": {
            "wave6_9_status_doc": {
                "path": display_path(WAVE6_9_DOC),
                "exists": WAVE6_9_DOC.is_file(),
                "evidence_role": "topic-local provider isolation status and minimum plan",
            },
            "wave12_provider_readiness": _wave12_summary(wave12),
            "search_provider_trace_contract": _trace_contract_summary(trace_contract),
            "container_trace_replay": _container_replay_summary(container_replay),
        },
        "unsupported_claims": [
            {
                "code": "current_open_search_runtime_not_closed",
                "claim": "Current SearXNG/YaCy runtime availability is sealed.",
                "reason": "This checker may observe a connect error, empty result, or successful bounded query, but it does not start or operate the external services.",
            },
            {
                "code": "live_query_quality_not_closed",
                "claim": "A live SearXNG/YaCy query proves provider quality.",
                "reason": "A single bounded query cannot prove result quality, freshness, latency stability, timeout policy, or approval-gate behavior.",
            },
            {
                "code": "provider_auto_promotion_not_allowed",
                "claim": "SearXNG/YaCy can enter provider=auto.",
                "reason": "Recorded provider trace evidence still keeps local open-search providers explicit-only.",
            },
        ],
        "gate_semantics": {
            "status_passed_means": "repo-local config surfaces, explicit provider trace, current runtime classification, and retained external gap are valid",
            "status_passed_does_not_mean": "SearXNG/YaCy live availability, live query quality, provider=auto promotion, or external runtime closure is sealed",
            "runtime_classes": [
                "configured_endpoint_only",
                "service_not_started_connect_error",
                "service_unreachable_timeout",
                "endpoint_responded_with_http_error",
                "live_query_unsealed",
            ],
        },
        "failures": failures,
    }
    validation_failures = validate_contract(contract)
    contract["failures"].extend(validation_failures)
    contract["status"] = "passed" if not contract["failures"] else "failed"
    return contract


def write_output(path: Path, contract: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the Wave15 SearXNG/YaCy runtime boundary.")
    parser.add_argument("--json", action="store_true", help="Print full contract JSON.")
    parser.add_argument("--write-output", type=Path, help=f"Write full contract JSON. Suggested: {DEFAULT_OUT}")
    parser.add_argument("--skip-live-probe", action="store_true", help="Only verify configured endpoints and recorded evidence.")
    parser.add_argument("--probe-timeout", type=float, default=1.0, help="Bounded live probe timeout in seconds.")
    args = parser.parse_args(argv)

    contract = build_contract(
        enable_live_probe=not args.skip_live_probe,
        probe_timeout=args.probe_timeout,
    )
    output_path = args.write_output
    if output_path is not None:
        if not output_path.is_absolute():
            output_path = REPO_ROOT / output_path
        write_output(output_path, contract)

    if args.json:
        print(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        provider_bits = " ".join(
            f"{provider}={row.get('boundary_classification')}:{row.get('live_probe_status')}"
            for provider, row in contract["provider_runtime_boundaries"].items()
        )
        print(
            "OK open_search_runtime_boundary={status} "
            "boundary_state={boundary_state} external_runtime_gap={gap} "
            "closure_claim_allowed={closure} {providers}".format(
                status=contract["status"],
                boundary_state=contract["boundary_state"],
                gap=contract["external_runtime_gap"],
                closure=str(bool(contract["closure_claim_allowed"])).lower(),
                providers=provider_bits,
            )
        )
        if contract["failures"]:
            print(json.dumps({"failures": contract["failures"]}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
