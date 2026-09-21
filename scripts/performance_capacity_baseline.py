#!/usr/bin/env python3
"""Repo-local performance and capacity baseline smoke lane.

This script intentionally uses deterministic in-memory fixtures instead of a
live service or large load-test environment. It is safe for CI and nightly
automation: missing services are recorded as probe status, not as hard failures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any


SCHEMA_VERSION = "performance_capacity_baseline.v1"
DEFAULT_QUERY_TERMS = ("market", "risk", "capacity", "trend")
FIXTURE_SPECS = (
    {
        "name": "small",
        "record_count": 16,
        "payload_tokens": 24,
        "budget": {
            "max_total_ms": 250.0,
            "max_records": 16,
            "max_fixture_bytes": 24_000,
        },
    },
    {
        "name": "medium",
        "record_count": 256,
        "payload_tokens": 36,
        "budget": {
            "max_total_ms": 750.0,
            "max_records": 256,
            "max_fixture_bytes": 600_000,
        },
    },
    {
        "name": "large",
        "record_count": 2048,
        "payload_tokens": 48,
        "budget": {
            "max_total_ms": 5_000.0,
            "max_records": 2048,
            "max_fixture_bytes": 6_000_000,
        },
    },
)


@dataclass(frozen=True)
class TimerResult:
    elapsed_ms: float
    value: Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a deterministic performance/capacity baseline JSON artifact "
            "for CI or nightly automation."
        )
    )
    parser.add_argument(
        "--output",
        required=False,
        help="JSON artifact path to write. Parent directories are created.",
    )
    parser.add_argument(
        "--previous",
        help="Optional previous baseline artifact for trend/degradation comparison.",
    )
    parser.add_argument(
        "--api-base",
        help=(
            "Optional service base URL to probe. Missing/unreachable services are "
            "recorded as unavailable and do not fail the baseline."
        ),
    )
    parser.add_argument(
        "--runtime-mode",
        default="repo_local_deterministic_fixture_smoke",
        help="Runtime mode label to include in service/preflight evidence; default: repo_local_deterministic_fixture_smoke.",
    )
    parser.add_argument(
        "--service-required",
        action="store_true",
        help="Mark service probe failures as fail-fast decisions in the evidence contract.",
    )
    parser.add_argument(
        "--allow-service-failure",
        action="store_true",
        help=(
            "Keep writing service fail-fast/degradation evidence, but exit zero "
            "when the required service probe is unavailable."
        ),
    )
    parser.add_argument(
        "--probe-timeout",
        type=float,
        default=0.25,
        help="Optional service probe timeout in seconds; default: 0.25.",
    )
    parser.add_argument(
        "--trend-regression-ratio",
        type=float,
        default=1.5,
        help=(
            "Mark degradation when current total_ms exceeds previous total_ms by "
            "this ratio and is close to the fixture budget; default: 1.5."
        ),
    )
    parser.add_argument(
        "--trend-budget-ratio",
        type=float,
        default=0.95,
        help=(
            "Trend ratio regressions become hard degradations only when current "
            "total_ms is at least this share of max_total_ms; default: 0.95."
        ),
    )
    parser.add_argument(
        "--fail-on-degradation",
        action="store_true",
        help="Exit non-zero when a budget or trend degradation is detected.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run a temporary smoke generation and schema sanity check.",
    )
    return parser.parse_args()


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def time_call(fn: Any, *args: Any, **kwargs: Any) -> TimerResult:
    start = time.perf_counter()
    value = fn(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return TimerResult(elapsed_ms=round(elapsed_ms, 3), value=value)


def stable_token(seed: str, length: int) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    words = []
    while len(words) < length:
        for index in range(0, len(digest), 8):
            words.append(f"tok_{digest[index:index + 8]}")
            if len(words) >= length:
                break
        digest = hashlib.sha256((digest + seed).encode("utf-8")).hexdigest()
    return " ".join(words)


def build_fixture(
    name: str, record_count: int, payload_tokens: int
) -> Annotated[
    list[dict[str, Any]],
    "kit:non-authoritative "
    "derived_as=generated_evidence "
    "fact_source=name_record_count_and_payload_tokens_function_inputs "
    "witness=test:test_w12_runtime_misc_laws",
]:
    records: list[dict[str, Any]] = []
    domains = ("consumer", "industrial", "policy", "logistics")
    for idx in range(record_count):
        domain = domains[idx % len(domains)]
        body = stable_token(f"{name}:{idx}:{domain}", payload_tokens)
        records.append(
            {
                "id": f"{name}-{idx:05d}",
                "domain": domain,
                "title": f"{name.title()} baseline record {idx}",
                "body": f"market risk capacity trend {body}",
                "score": (idx % 17) / 17.0,
            }
        )
    return records


def estimate_fixture_bytes(records: list[dict[str, Any]]) -> int:
    return sum(len(json.dumps(record, sort_keys=True, separators=(",", ":"))) for record in records)


def build_index(
    records: list[dict[str, Any]],
) -> Annotated[
    dict[str, set[str]],
    "kit:non-authoritative "
    "derived_as=view "
    "fact_source=records_function_input "
    "witness=test:test_w12_runtime_misc_laws",
]:
    index: dict[str, set[str]] = {}
    for record in records:
        text = f"{record['title']} {record['body']} {record['domain']}".lower()
        for raw_token in text.split():
            token = raw_token.strip(".,:;()[]{}")
            if not token:
                continue
            index.setdefault(token, set()).add(record["id"])
    return index


def run_queries(index: dict[str, set[str]], terms: tuple[str, ...]) -> dict[str, int]:
    return {term: len(index.get(term, set())) for term in terms}


def aggregate_records(records: list[dict[str, Any]], query_hits: dict[str, int]) -> dict[str, Any]:
    by_domain: dict[str, int] = {}
    scores: list[float] = []
    for record in records:
        by_domain[record["domain"]] = by_domain.get(record["domain"], 0) + 1
        scores.append(float(record["score"]))

    return {
        "domain_counts": dict(sorted(by_domain.items())),
        "query_hit_total": sum(query_hits.values()),
        "score_mean": round(statistics.fmean(scores), 6) if scores else 0.0,
        "score_p95": round(percentile(scores, 0.95), 6) if scores else 0.0,
    }


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * quantile
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return ordered[int(pos)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower)


def run_fixture(spec: dict[str, Any]) -> dict[str, Any]:
    build = time_call(build_fixture, spec["name"], spec["record_count"], spec["payload_tokens"])
    records = build.value
    fixture_bytes = estimate_fixture_bytes(records)
    index_result = time_call(build_index, records)
    index = index_result.value
    query_result = time_call(run_queries, index, DEFAULT_QUERY_TERMS)
    aggregate_result = time_call(aggregate_records, records, query_result.value)

    timings = {
        "build_fixture_ms": build.elapsed_ms,
        "build_index_ms": index_result.elapsed_ms,
        "query_ms": query_result.elapsed_ms,
        "aggregate_ms": aggregate_result.elapsed_ms,
    }
    total_ms = round(sum(timings.values()), 3)
    budget = spec["budget"]
    budget_checks = {
        "total_ms_within_budget": total_ms <= float(budget["max_total_ms"]),
        "records_within_budget": len(records) <= int(budget["max_records"]),
        "fixture_bytes_within_budget": fixture_bytes <= int(budget["max_fixture_bytes"]),
    }
    status = "passed" if all(budget_checks.values()) else "budget_exceeded"

    return {
        "fixture": {
            "name": spec["name"],
            "record_count": len(records),
            "payload_tokens_per_record": spec["payload_tokens"],
            "query_terms": list(DEFAULT_QUERY_TERMS),
        },
        "budget": budget,
        "observed": {
            "status": status,
            "timings_ms": {**timings, "total_ms": total_ms},
            "capacity": {
                "fixture_bytes": fixture_bytes,
                "index_terms": len(index),
                "query_hit_total": aggregate_result.value["query_hit_total"],
            },
            "summary": aggregate_result.value,
        },
        "budget_checks": budget_checks,
    }


def probe_url(url: str, timeout: float) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 3)
            return {
                "status": "passed",
                "url": url,
                "http_status": response.status,
                "elapsed_ms": elapsed_ms,
                "latency_ms": elapsed_ms,
            }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 3)
        return {
            "status": "failed",
            "url": url,
            "error": f"{exc.__class__.__name__}: {exc}",
            "timeout_seconds": timeout,
            "elapsed_ms": elapsed_ms,
            "latency_ms": elapsed_ms,
        }


def parse_api_port(api_base: str | None) -> dict[str, Any]:
    if not api_base:
        return {
            "status": "not_configured",
            "value": None,
            "source": "api_base",
        }
    parsed = urllib.parse.urlparse(api_base)
    default_port = 443 if parsed.scheme == "https" else 80 if parsed.scheme == "http" else None
    return {
        "status": "configured" if parsed.hostname else "invalid",
        "value": parsed.port or default_port,
        "host": parsed.hostname,
        "scheme": parsed.scheme or None,
        "source": "api_base",
    }


def build_fail_fast_decision(
    *,
    service_required: bool,
    allow_service_failure: bool,
    service_ping: dict[str, Any],
    service_ready: dict[str, Any],
    dependency: dict[str, Any],
    secret: dict[str, Any],
    recommended_command: str,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=preflight "
    "fact_source=service_dependency_and_secret_probe_results "
    "witness=test:test_w12_runtime_misc_laws",
]:
    dependency_blocked = dependency.get("status") == "failed"
    secret_blocked = secret.get("status") == "failed"
    service_blocked = service_required and service_ready.get("status") != "passed"
    reasons = []
    if service_blocked:
        reasons.append("required service readiness probe did not pass")
    if dependency_blocked:
        reasons.append("required dependency check failed")
    if secret_blocked:
        reasons.append("required secret check failed")
    should_fail = bool(reasons)
    effective_exit_code = 0 if should_fail and allow_service_failure else 1 if should_fail else 0
    return {
        "should_fail": should_fail,
        "status": "fail_fast" if reasons else "continue",
        "exit_code": 1 if reasons else 0,
        "effective_exit_code": effective_exit_code,
        "allow_service_failure": allow_service_failure,
        "reasons": reasons,
        "service_required": service_required,
        "service_ping_status": service_ping.get("status"),
        "service_ready_status": service_ready.get("status"),
        "recommended_command": recommended_command,
    }


def build_probe_latency(
    *,
    ping_attempts: list[dict[str, Any]],
    ready_attempts: list[dict[str, Any]],
    timeout: float,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=preflight "
    "fact_source=ping_and_ready_attempt_timings "
    "witness=test:test_w12_runtime_misc_laws",
]:
    attempts = [*ping_attempts, *ready_attempts]
    elapsed_values = [
        float(item["elapsed_ms"])
        for item in attempts
        if isinstance(item.get("elapsed_ms"), (int, float))
    ]
    return {
        "status": "measured" if attempts else "skipped",
        "timeout_seconds": timeout,
        "attempt_count": len(attempts),
        "total_elapsed_ms": round(sum(elapsed_values), 3),
        "attempts": [
            {
                "url": item.get("url"),
                "status": item.get("status"),
                "elapsed_ms": item.get("elapsed_ms"),
                "http_status": item.get("http_status"),
            }
            for item in attempts
        ],
    }


def build_service_degradation(
    *,
    service_required: bool,
    fail_fast_decision: dict[str, Any],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=preflight "
    "fact_source=service_required_and_fail_fast_decision_inputs "
    "witness=test:test_w12_runtime_misc_laws",
]:
    reasons = [
        reason
        for reason in fail_fast_decision.get("reasons", [])
        if isinstance(reason, str)
    ]
    should_fail = bool(fail_fast_decision.get("should_fail"))
    return {
        "flag": should_fail,
        "status": "degraded" if should_fail else "passed",
        "decision": fail_fast_decision.get("status"),
        "reasons": reasons,
        "service_required": service_required,
    }


def probe_service(
    api_base: str | None,
    timeout: float,
    runtime_mode: str,
    service_required: bool,
    allow_service_failure: bool,
) -> dict[str, Any]:
    recommended_command = (
        "python3 scripts/performance_capacity_baseline.py "
        "--api-base <base-url> "
        f"{'--service-required ' if service_required else ''}"
        "--output <artifact.json>"
    )
    port = parse_api_port(api_base)
    dependency = {
        "status": "not_checked",
        "required": False,
        "missing": [],
        "checks": [],
    }
    secret = {
        "status": "not_checked",
        "required": False,
        "missing": [],
        "checks": [],
    }
    if not api_base:
        service_ping = {
            "status": "skipped",
            "reason": "no api base supplied",
            "candidates": [],
        }
        service_ready = {
            "status": "skipped",
            "reason": "no api base supplied",
            "candidates": [],
        }
        latency = build_probe_latency(
            ping_attempts=[],
            ready_attempts=[],
            timeout=timeout,
        )
        fail_fast_decision = build_fail_fast_decision(
            service_required=service_required,
            allow_service_failure=allow_service_failure,
            service_ping=service_ping,
            service_ready=service_ready,
            dependency=dependency,
            secret=secret,
            recommended_command=recommended_command,
        )
        return {
            "enabled": False,
            "status": "skipped",
            "reason": "no api base supplied",
            "runtime_mode": runtime_mode,
            "allow_service_failure": allow_service_failure,
            "latency": latency,
            "latency_ms": None,
            "service_ping": service_ping,
            "service_ready": service_ready,
            "port": port,
            "secret": secret,
            "dependency": dependency,
            "recommended_command": recommended_command,
            "fail_fast_decision": fail_fast_decision,
            "degradation": build_service_degradation(
                service_required=service_required,
                fail_fast_decision=fail_fast_decision,
            ),
        }

    base = api_base.rstrip("/")
    ping_candidates = (f"{base}/health", f"{base}/api/v1/health")
    ready_candidates = (f"{base}/api/v1/health/deep", f"{base}/health/deep")
    ping_attempts = [probe_url(url, timeout) for url in ping_candidates]
    ready_attempts = [probe_url(url, timeout) for url in ready_candidates]
    ping_elapsed_ms = round(
        sum(float(item.get("elapsed_ms", 0.0)) for item in ping_attempts),
        3,
    )
    ready_elapsed_ms = round(
        sum(float(item.get("elapsed_ms", 0.0)) for item in ready_attempts),
        3,
    )
    service_ping = next((item for item in ping_attempts if item["status"] == "passed"), None) or {
        "status": "failed",
        "candidates": list(ping_candidates),
        "attempts": ping_attempts,
        "timeout_seconds": timeout,
        "elapsed_ms": ping_elapsed_ms,
        "latency_ms": ping_elapsed_ms,
    }
    service_ready = next((item for item in ready_attempts if item["status"] == "passed"), None) or {
        "status": "failed",
        "candidates": list(ready_candidates),
        "attempts": ready_attempts,
        "timeout_seconds": timeout,
        "elapsed_ms": ready_elapsed_ms,
        "latency_ms": ready_elapsed_ms,
    }
    status = (
        "ready"
        if service_ready.get("status") == "passed"
        else "ping_only"
        if service_ping.get("status") == "passed"
        else "unavailable"
    )
    errors = [
        item.get("error")
        for item in [*ping_attempts, *ready_attempts]
        if item.get("status") == "failed" and item.get("error")
    ]
    latency = build_probe_latency(
        ping_attempts=ping_attempts,
        ready_attempts=ready_attempts,
        timeout=timeout,
    )
    selected_elapsed_ms = service_ready.get("elapsed_ms") or service_ping.get("elapsed_ms")
    fail_fast_decision = build_fail_fast_decision(
        service_required=service_required,
        allow_service_failure=allow_service_failure,
        service_ping=service_ping,
        service_ready=service_ready,
        dependency=dependency,
        secret=secret,
        recommended_command=recommended_command,
    )

    return {
        "enabled": True,
        "status": status,
        "runtime_mode": runtime_mode,
        "allow_service_failure": allow_service_failure,
        "url": service_ping.get("url") or service_ready.get("url"),
        "http_status": service_ready.get("http_status") or service_ping.get("http_status"),
        "elapsed_ms": selected_elapsed_ms,
        "latency_ms": selected_elapsed_ms,
        "latency": latency,
        "service_ping": service_ping,
        "service_ready": service_ready,
        "port": port,
        "secret": secret,
        "dependency": dependency,
        "recommended_command": recommended_command,
        "fail_fast_decision": fail_fast_decision,
        "degradation": build_service_degradation(
            service_required=service_required,
            fail_fast_decision=fail_fast_decision,
        ),
        "errors": errors,
        "timeout_seconds": timeout,
    }


def read_previous(path: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if not path:
        return None, None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def observations_by_name(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item.get("fixture", {}).get("name"): item
        for item in artifact.get("observations", [])
        if item.get("fixture", {}).get("name")
    }


def build_trend_record(
    observations: list[dict[str, Any]],
    previous: dict[str, Any] | None,
    previous_error: str | None,
    regression_ratio: float,
    trend_budget_ratio: float,
) -> Annotated[
    tuple[dict[str, Any], list[str]],
    "kit:non-authoritative "
    "derived_as=generated_evidence "
    "fact_source=current_observations_previous_artifact_and_threshold_inputs "
    "witness=test:test_w12_runtime_misc_laws",
]:
    current_by_name = observations_by_name({"observations": observations})
    current_totals = {
        name: item["observed"]["timings_ms"]["total_ms"]
        for name, item in current_by_name.items()
    }

    if previous_error:
        return (
            {
                "status": "previous_unreadable",
                "previous_error": previous_error,
                "current_total_ms_by_fixture": current_totals,
                "degradation_threshold_ratio": regression_ratio,
                "budget_alert_ratio": trend_budget_ratio,
                "comparisons": [],
            },
            [],
        )

    if previous is None:
        return (
            {
                "status": "no_previous_artifact",
                "current_total_ms_by_fixture": current_totals,
                "degradation_threshold_ratio": regression_ratio,
                "budget_alert_ratio": trend_budget_ratio,
                "comparisons": [],
            },
            [],
        )

    previous_by_name = observations_by_name(previous)
    comparisons: list[dict[str, Any]] = []
    degradation_reasons: list[str] = []
    for name, current in sorted(current_by_name.items()):
        previous_item = previous_by_name.get(name)
        current_total = float(current["observed"]["timings_ms"]["total_ms"])
        if not previous_item:
            comparisons.append(
                {
                    "fixture": name,
                    "status": "missing_previous_fixture",
                    "current_total_ms": current_total,
                }
            )
            continue

        previous_total = float(previous_item["observed"]["timings_ms"]["total_ms"])
        ratio = round(current_total / previous_total, 4) if previous_total > 0 else None
        budget_total = float(current["budget"]["max_total_ms"])
        budget_alert_floor = round(budget_total * trend_budget_ratio, 3)
        ratio_regressed = previous_total > 0 and current_total > previous_total * regression_ratio
        degraded = ratio_regressed and current_total >= budget_alert_floor
        if degraded:
            degradation_reasons.append(
                f"{name} total_ms {current_total} exceeds previous {previous_total} by ratio {ratio}"
            )
        comparisons.append(
            {
                "fixture": name,
                "status": (
                    "degraded"
                    if degraded
                    else "trend_watch"
                    if ratio_regressed
                    else "within_trend_budget"
                ),
                "previous_total_ms": previous_total,
                "current_total_ms": current_total,
                "ratio": ratio,
                "threshold_ratio": regression_ratio,
                "budget_alert_floor_ms": budget_alert_floor,
            }
        )

    return (
        {
            "status": "compared",
            "previous_schema_version": previous.get("schema_version"),
            "previous_generated_at": previous.get("generated_at"),
            "current_total_ms_by_fixture": current_totals,
            "degradation_threshold_ratio": regression_ratio,
            "budget_alert_ratio": trend_budget_ratio,
            "comparisons": comparisons,
        },
        degradation_reasons,
    )


def summarize_budget_breaches(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    breaches: list[dict[str, Any]] = []
    budget_field_by_check = {
        "total_ms_within_budget": "max_total_ms",
        "records_within_budget": "max_records",
        "fixture_bytes_within_budget": "max_fixture_bytes",
    }
    for item in observations:
        fixture_name = item["fixture"]["name"]
        timings = item["observed"]["timings_ms"]
        capacity = item["observed"]["capacity"]
        budget = item["budget"]
        observed_values = {
            "max_total_ms": timings["total_ms"],
            "max_records": item["fixture"]["record_count"],
            "max_fixture_bytes": capacity["fixture_bytes"],
        }
        for check_name, passed in item["budget_checks"].items():
            if passed:
                continue
            budget_field = budget_field_by_check.get(check_name, check_name)
            breaches.append(
                {
                    "fixture": fixture_name,
                    "budget_field": budget_field,
                    "observed": observed_values.get(budget_field),
                    "budget": budget.get(budget_field),
                    "check": check_name,
                }
            )
    return breaches


def build_diagnostic_package(
    *,
    generated_at: str,
    budgets: dict[str, dict[str, Any]],
    observations: list[dict[str, Any]],
    trend_record: dict[str, Any],
    degradation: dict[str, Any],
    service_probe: dict[str, Any],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=view "
    "fact_source=budgets_observations_trend_degradation_and_service_probe_inputs "
    "witness=test:test_w12_runtime_misc_laws",
]:
    fixture_budget_summary = []
    for item in sorted(observations, key=lambda row: row["fixture"]["name"]):
        fixture_name = item["fixture"]["name"]
        budget = budgets[fixture_name]
        observed = item["observed"]
        timings = observed["timings_ms"]
        capacity = observed["capacity"]
        fixture_budget_summary.append(
            {
                "fixture": fixture_name,
                "status": observed["status"],
                "record_count": item["fixture"]["record_count"],
                "total_ms": timings["total_ms"],
                "max_total_ms": budget["max_total_ms"],
                "fixture_bytes": capacity["fixture_bytes"],
                "max_fixture_bytes": budget["max_fixture_bytes"],
                "budget_checks": item["budget_checks"],
            }
        )

    budget_breaches = summarize_budget_breaches(observations)
    trend_comparisons = trend_record.get("comparisons", [])
    trend_summary = {
        "status": trend_record.get("status"),
        "previous_schema_version": trend_record.get("previous_schema_version"),
        "previous_generated_at": trend_record.get("previous_generated_at"),
        "current_total_ms_by_fixture": trend_record.get("current_total_ms_by_fixture", {}),
        "comparison_count": len(trend_comparisons) if isinstance(trend_comparisons, list) else 0,
        "degraded_fixtures": [
            item.get("fixture")
            for item in trend_comparisons
            if isinstance(item, dict) and item.get("status") == "degraded"
        ]
        if isinstance(trend_comparisons, list)
        else [],
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "lane": "performance_capacity_baseline_smoke",
        "generated_at": generated_at,
        "summary": {
            "status": "degraded" if degradation["flag"] else "passed",
            "degradation_flag": degradation["flag"],
            "degradation_reason_count": len(degradation["reasons"]),
        },
        "fixture_budget_summary": fixture_budget_summary,
        "budget_breach_summary": {
            "count": len(budget_breaches),
            "breaches": budget_breaches,
        },
        "trend_summary": trend_summary,
        "service_probe_summary": {
            "enabled": service_probe.get("enabled"),
            "status": service_probe.get("status"),
            "runtime_mode": service_probe.get("runtime_mode"),
            "allow_service_failure": service_probe.get("allow_service_failure"),
            "reason": service_probe.get("reason"),
            "url": service_probe.get("url"),
            "http_status": service_probe.get("http_status"),
            "elapsed_ms": service_probe.get("elapsed_ms"),
            "latency_ms": service_probe.get("latency_ms"),
            "latency": service_probe.get("latency"),
            "timeout_seconds": service_probe.get("timeout_seconds"),
            "service_ping": service_probe.get("service_ping"),
            "service_ready": service_probe.get("service_ready"),
            "port": service_probe.get("port"),
            "secret": service_probe.get("secret"),
            "dependency": service_probe.get("dependency"),
            "recommended_command": service_probe.get("recommended_command"),
            "fail_fast_decision": service_probe.get("fail_fast_decision"),
            "degradation": service_probe.get("degradation"),
            "error_count": len(service_probe.get("errors", []))
            if isinstance(service_probe.get("errors"), list)
            else 0,
        },
        "recommended_commands": {
            "minimal_gate": (
                "tmp=$(mktemp); "
                'python3 scripts/performance_capacity_baseline.py --output "$tmp"; '
                'python3 scripts/check_performance_capacity_baseline_artifact.py "$tmp"; '
                'rm -f "$tmp"'
            ),
            "self_test": "python3 scripts/performance_capacity_baseline.py --self-test",
            "nightly": "bash scripts/run_performance_capacity_nightly.sh",
            "compare_previous": (
                "python3 scripts/performance_capacity_baseline.py "
                "--previous <previous-artifact.json> --output <artifact.json>"
            ),
        },
    }


def build_artifact(
    args: argparse.Namespace,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=generated_evidence "
    "fact_source=measured_fixture_observations_previous_artifact_and_service_probe "
    "witness=test:test_w12_runtime_misc_laws",
]:
    observations = [run_fixture(spec) for spec in FIXTURE_SPECS]
    previous, previous_error = read_previous(args.previous)
    trend_record, trend_degradation_reasons = build_trend_record(
        observations=observations,
        previous=previous,
        previous_error=previous_error,
        regression_ratio=args.trend_regression_ratio,
        trend_budget_ratio=args.trend_budget_ratio,
    )

    budget_reasons = [
        f"{item['fixture']['name']} exceeded {key}"
        for item in observations
        for key, passed in item["budget_checks"].items()
        if not passed
    ]
    degradation_reasons = budget_reasons + trend_degradation_reasons
    degradation_flag = bool(degradation_reasons)
    generated_at = now_utc()
    budgets = {
        spec["name"]: spec["budget"]
        for spec in FIXTURE_SPECS
    }
    service_probe = probe_service(
        args.api_base,
        args.probe_timeout,
        args.runtime_mode,
        args.service_required,
        args.allow_service_failure,
    )
    fail_fast = service_probe.get("fail_fast_decision", {})
    if isinstance(fail_fast, dict) and fail_fast.get("should_fail"):
        degradation_reasons.extend(
            f"service fail-fast: {reason}"
            for reason in fail_fast.get("reasons", [])
            if isinstance(reason, str)
        )
    degradation_flag = bool(degradation_reasons)
    degradation = {
        "flag": degradation_flag,
        "reasons": degradation_reasons,
    }
    diagnostic_package = build_diagnostic_package(
        generated_at=generated_at,
        budgets=budgets,
        observations=observations,
        trend_record=trend_record,
        degradation=degradation,
        service_probe=service_probe,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "degraded" if degradation_flag else "passed",
        "lane": "performance_capacity_baseline_smoke",
        "scope": {
            "mode": args.runtime_mode,
            "live_load_test": False,
            "requires_service": args.service_required,
            "allow_service_failure": args.allow_service_failure,
            "fixture_sizes": [spec["name"] for spec in FIXTURE_SPECS],
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cwd": os.getcwd(),
        },
        "budgets": budgets,
        "observations": observations,
        "service_probe": service_probe,
        "trend_record": trend_record,
        "degradation": degradation,
        "diagnostic_package": diagnostic_package,
    }


def validate_artifact_shape(artifact: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if artifact.get("schema_version") != SCHEMA_VERSION:
        problems.append("schema_version mismatch")
    if "budgets" not in artifact or set(artifact["budgets"]) != {"small", "medium", "large"}:
        problems.append("budgets for small/medium/large are missing")
    if "trend_record" not in artifact:
        problems.append("trend_record missing")
    if "degradation" not in artifact or "flag" not in artifact["degradation"]:
        problems.append("degradation.flag missing")
    service_probe = artifact.get("service_probe")
    if not isinstance(service_probe, dict):
        problems.append("service_probe missing")
    else:
        for field in (
            "runtime_mode",
            "latency",
            "service_ping",
            "service_ready",
            "port",
            "secret",
            "dependency",
            "recommended_command",
            "fail_fast_decision",
            "degradation",
        ):
            if field not in service_probe:
                problems.append(f"service_probe.{field} missing")
    diagnostic_package = artifact.get("diagnostic_package")
    if not isinstance(diagnostic_package, dict):
        problems.append("diagnostic_package missing")
    elif diagnostic_package.get("schema_version") != SCHEMA_VERSION:
        problems.append("diagnostic_package.schema_version mismatch")
    observations = artifact.get("observations", [])
    if len(observations) != 3:
        problems.append("expected exactly three observations")
    for item in observations:
        if "budget" not in item:
            problems.append(f"{item.get('fixture', {}).get('name', '?')} budget missing")
        if "observed" not in item or "timings_ms" not in item.get("observed", {}):
            problems.append(f"{item.get('fixture', {}).get('name', '?')} observed timings missing")
    return problems


def write_artifact(path: str, artifact: dict[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def run_self_test() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "performance-baseline.json"
        args = argparse.Namespace(
            output=str(output),
            previous=None,
            api_base=None,
            runtime_mode="repo_local_deterministic_fixture_smoke",
            service_required=False,
            allow_service_failure=False,
            probe_timeout=0.05,
            trend_regression_ratio=1.5,
            trend_budget_ratio=0.95,
            fail_on_degradation=False,
            self_test=True,
        )
        artifact = build_artifact(args)
        write_artifact(str(output), artifact)
        problems = validate_artifact_shape(artifact)
        if problems:
            for problem in problems:
                print(f"FAIL self-test: {problem}", file=sys.stderr)
            return 1
        print(f"OK self-test output={output}")
        return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_test()
    if not args.output:
        print("FAIL --output is required unless --self-test is used", file=sys.stderr)
        return 2

    artifact = build_artifact(args)
    problems = validate_artifact_shape(artifact)
    if problems:
        for problem in problems:
            print(f"FAIL artifact-shape: {problem}", file=sys.stderr)
        return 1

    output = write_artifact(args.output, artifact)
    print(
        "OK performance_capacity_baseline "
        f"status={artifact['status']} degradation={artifact['degradation']['flag']} output={output}"
    )
    fail_fast = artifact.get("service_probe", {}).get("fail_fast_decision", {})
    if isinstance(fail_fast, dict) and fail_fast.get("should_fail"):
        if args.allow_service_failure:
            print("WARN service fail-fast evidence recorded; --allow-service-failure keeps exit_code=0")
        else:
            return int(fail_fast.get("exit_code") or 1)
    if args.fail_on_degradation and artifact["degradation"]["flag"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
