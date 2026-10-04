#!/usr/bin/env python3
"""Run a live trace baseline over the canonical business-line probes."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Sequence
from urllib import error, request

try:
    from scripts._automation_runtime import CANONICAL_LINE_KEYS, utc_now, write_json
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import CANONICAL_LINE_KEYS, utc_now, write_json


SCHEMA_VERSION = "business_line_trace_baseline_live.v1"
MATRIX_PATH = "/api/v1/business-lines/evidence-matrix"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"
RESPONSE_ASSERTION_PASSED = "passed"
RESPONSE_ASSERTION_FAILED = "failed"
TRACE_NOT_APPLICABLE = "not_applicable"

EXPECTED_LINE_KEYS = CANONICAL_LINE_KEYS


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: str
    headers: dict[str, str]
    duration_ms: float
    error: str | None = None


def normalize_api_base(api_base: str) -> str:
    return api_base.rstrip("/")


def build_url(api_base: str, path: str) -> Annotated[
    str,
    "kit:prepared-command effect_boundary=trace_baseline_http_read witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalize_api_base(api_base)}{normalized_path}"


def recommended_command(api_base: str, output_path: Path) -> str:
    return (
        "python3 scripts/run_business_line_trace_baseline_live.py "
        f"--base-url {api_base} --output {output_path} --json"
    )


def _http_get(url: str, *, timeout: float, trace_id: str) -> HttpResult:
    headers = {
        "Accept": "application/json",
        "X-Trace-Id": trace_id,
        "X-Request-Id": trace_id,
    }
    req = request.Request(url, headers=headers, method="GET")
    started = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - explicit live smoke URL input
            body = response.read().decode("utf-8", errors="replace")
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            return HttpResult(
                status_code=int(response.status),
                body=body,
                headers={key.lower(): value for key, value in response.headers.items()},
                duration_ms=duration_ms,
            )
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        return HttpResult(
            status_code=int(exc.code),
            body=body,
            headers={key.lower(): value for key, value in exc.headers.items()},
            duration_ms=duration_ms,
            error=str(exc),
        )
    except (error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        return HttpResult(status_code=None, body="", headers={}, duration_ms=duration_ms, error=str(exc))


def load_json_payload(result: HttpResult) -> tuple[Any | None, str | None]:
    try:
        return json.loads(result.body), None
    except json.JSONDecodeError as exc:
        return None, f"response is not valid JSON: {exc}"


def payload_roots(payload: Any) -> list[Any]:
    roots = [payload]
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        roots.append(payload["data"])
    return roots


def line_items_from_mapping(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for key, value in mapping.items():
        if not isinstance(value, dict):
            continue
        item = dict(value)
        item.setdefault("line_key", key)
        lines.append(item)
    return lines


def extract_lines(payload: Any) -> list[dict[str, Any]]:
    for root in payload_roots(payload):
        if not isinstance(root, dict):
            continue
        for key in ("lines", "business_lines", "items", "evidence_matrix", "matrix"):
            value = root.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return line_items_from_mapping(value)
    return []


def index_matrix_lines(lines: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    by_key: dict[str, dict[str, Any]] = {}
    seen: dict[str, int] = {}
    invalid_line_keys: list[str] = []
    for line in lines:
        raw_key = line.get("line_key")
        if not isinstance(raw_key, str) or not raw_key.strip():
            invalid_line_keys.append("<missing>")
            continue
        line_key = raw_key.strip()
        if line_key not in EXPECTED_LINE_KEYS:
            invalid_line_keys.append(line_key)
            continue
        seen[line_key] = seen.get(line_key, 0) + 1
        by_key.setdefault(line_key, line)
    return by_key, {
        "missing_line_keys": sorted(set(EXPECTED_LINE_KEYS) - set(by_key)),
        "unexpected_line_keys": sorted(key for key in invalid_line_keys if key != "<missing>"),
        "invalid_line_keys": sorted(key for key in invalid_line_keys if key == "<missing>"),
        "duplicate_line_keys": sorted(line_key for line_key, count in seen.items() if count > 1),
    }


def resolve_data_path(payload: Any, data_path: str) -> tuple[bool, Any]:
    current = payload
    for part in [part for part in data_path.replace("/", ".").split(".") if part]:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _live_smoke(line: dict[str, Any]) -> dict[str, Any]:
    live = line.get("live_smoke")
    return live if isinstance(live, dict) else {}


def _response_assertions(line: dict[str, Any]) -> dict[str, Any]:
    response_assertions = _live_smoke(line).get("response_assertions")
    return response_assertions if isinstance(response_assertions, dict) else {}


def required_data_paths(line: dict[str, Any]) -> list[str]:
    paths = _response_assertions(line).get("required_data_paths")
    if not isinstance(paths, list):
        return []
    return [path for path in paths if isinstance(path, str) and path.strip()]


def expected_statuses(line: dict[str, Any]) -> list[int]:
    statuses = _live_smoke(line).get("expected_statuses")
    if not isinstance(statuses, list):
        return [200]
    out = [status for status in statuses if isinstance(status, int) and not isinstance(status, bool)]
    return out or [200]


def probe_path(line: dict[str, Any]) -> str:
    path = _live_smoke(line).get("probe_path")
    if isinstance(path, str) and path.strip():
        stripped = path.strip()
        return stripped if stripped.startswith("/") else f"/{stripped}"
    return "/api/v1/health"


def body_meta_trace_status(payload: Any, trace_id: str) -> tuple[str, str | None]:
    if not isinstance(payload, dict) or not {"status", "data", "error", "meta"}.issubset(payload.keys()):
        return TRACE_NOT_APPLICABLE, None
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return RESPONSE_ASSERTION_FAILED, None
    observed = meta.get("trace_id")
    return (RESPONSE_ASSERTION_PASSED if observed == trace_id else RESPONSE_ASSERTION_FAILED), (
        str(observed) if observed is not None else None
    )


def evaluate_probe(
    *,
    line_key: str,
    line: dict[str, Any],
    api_base: str,
    trace_id: str,
    timeout: float,
    slow_threshold_ms: float,
) -> dict[str, Any]:
    path = probe_path(line)
    result = _http_get(build_url(api_base, path), timeout=timeout, trace_id=trace_id)
    payload, json_error = load_json_payload(result) if result.status_code is not None else (None, None)
    required_paths = required_data_paths(line)
    missing_paths: list[str] = []
    if payload is not None:
        for data_path in required_paths:
            exists, _value = resolve_data_path(payload, data_path)
            if not exists:
                missing_paths.append(data_path)
    elif required_paths:
        missing_paths = list(required_paths)

    header_trace_id = result.headers.get("x-trace-id")
    header_request_id = result.headers.get("x-request-id")
    body_trace_status, body_trace_id = body_meta_trace_status(payload, trace_id)
    expected = expected_statuses(line)
    failures: list[str] = []
    if result.status_code is None:
        failures.append("endpoint_unreachable")
    elif result.status_code not in expected:
        failures.append("unexpected_http_status")
    if json_error is not None:
        failures.append("valid_json")
    if header_trace_id != trace_id:
        failures.append("header_trace_id")
    if header_request_id != trace_id:
        failures.append("header_request_id")
    if body_trace_status == RESPONSE_ASSERTION_FAILED:
        failures.append("body_meta_trace_id")
    if missing_paths:
        failures.append("required_data_paths")

    if result.status_code is None:
        status = STATUS_BLOCKED
    elif failures:
        status = STATUS_FAILED
    else:
        status = STATUS_PASSED

    return {
        "line_key": line_key,
        "status": status,
        "probe_path": path,
        "trace_id": trace_id,
        "http_status": result.status_code,
        "expected_statuses": expected,
        "duration_ms": result.duration_ms,
        "slow_request": result.duration_ms >= slow_threshold_ms,
        "slow_threshold_ms": slow_threshold_ms,
        "header_trace_id": header_trace_id,
        "header_request_id": header_request_id,
        "body_meta_trace_status": body_trace_status,
        "body_meta_trace_id": body_trace_id,
        "required_data_paths": required_paths,
        "missing_data_paths": missing_paths,
        "failures": failures,
        "error": result.error,
    }


def build_matrix_blocked_report(
    *,
    api_base: str,
    output_path: Path,
    matrix_result: HttpResult,
    trace_id: str,
    started_at: str,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=preflight "
    "fact_source=matrix_http_result_and_start_time_function_inputs "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BLOCKED,
        "started_at": started_at,
        "api_base": api_base,
        "matrix_path": MATRIX_PATH,
        "recommended_command": recommended_command(api_base, output_path),
        "matrix": {
            "status": STATUS_BLOCKED,
            "trace_id": trace_id,
            "http_status": matrix_result.status_code,
            "duration_ms": matrix_result.duration_ms,
            "reason": "evidence_matrix_unreachable",
            "error": matrix_result.error,
        },
        "summary": {
            "line_count": 0,
            "passed_count": 0,
            "failed_count": 0,
            "blocked_count": len(EXPECTED_LINE_KEYS),
            "slow_request_count": 0,
            "first_failure": "evidence_matrix_unreachable",
        },
        "lines": [],
    }


def run_baseline(
    *,
    api_base: str,
    output_path: Path,
    timeout: float,
    trace_prefix: str,
    slow_threshold_ms: float,
) -> dict[str, Any]:
    started_at = utc_now()
    normalized_api_base = normalize_api_base(api_base)
    matrix_trace_id = f"{trace_prefix}-matrix"
    matrix_result = _http_get(
        build_url(normalized_api_base, MATRIX_PATH),
        timeout=timeout,
        trace_id=matrix_trace_id,
    )
    if matrix_result.status_code is None:
        return build_matrix_blocked_report(
            api_base=normalized_api_base,
            output_path=output_path,
            matrix_result=matrix_result,
            trace_id=matrix_trace_id,
            started_at=started_at,
        )

    matrix_payload, matrix_json_error = load_json_payload(matrix_result)
    matrix_failures: list[str] = []
    if matrix_result.status_code != 200:
        matrix_failures.append("evidence_matrix_http_status")
    if matrix_json_error is not None:
        matrix_failures.append("evidence_matrix_valid_json")
    matrix_body_trace_status, matrix_body_trace_id = body_meta_trace_status(matrix_payload, matrix_trace_id)
    if matrix_result.headers.get("x-trace-id") != matrix_trace_id:
        matrix_failures.append("evidence_matrix_header_trace_id")
    if matrix_body_trace_status == RESPONSE_ASSERTION_FAILED:
        matrix_failures.append("evidence_matrix_body_meta_trace_id")

    lines = extract_lines(matrix_payload)
    by_key, matrix_anomalies = index_matrix_lines(lines)
    if any(matrix_anomalies.values()):
        matrix_failures.append("evidence_matrix_line_keys")

    line_results = [
        evaluate_probe(
            line_key=line_key,
            line=by_key.get(line_key, {"line_key": line_key}),
            api_base=normalized_api_base,
            trace_id=f"{trace_prefix}-{line_key}",
            timeout=timeout,
            slow_threshold_ms=slow_threshold_ms,
        )
        for line_key in EXPECTED_LINE_KEYS
        if line_key in by_key
    ]
    missing_line_results = [
        {
            "line_key": line_key,
            "status": STATUS_FAILED,
            "failures": ["missing_line_in_evidence_matrix"],
        }
        for line_key in EXPECTED_LINE_KEYS
        if line_key not in by_key
    ]
    line_results.extend(missing_line_results)

    passed_count = sum(1 for line in line_results if line["status"] == STATUS_PASSED)
    failed_count = sum(1 for line in line_results if line["status"] == STATUS_FAILED)
    blocked_count = sum(1 for line in line_results if line["status"] == STATUS_BLOCKED)
    status = (
        STATUS_FAILED
        if matrix_failures or failed_count
        else STATUS_BLOCKED if blocked_count else STATUS_PASSED
    )
    slow_request_samples = [
        {
            "line_key": line["line_key"],
            "duration_ms": line.get("duration_ms"),
            "probe_path": line.get("probe_path"),
        }
        for line in line_results
        if line.get("slow_request")
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "started_at": started_at,
        "api_base": normalized_api_base,
        "matrix_path": MATRIX_PATH,
        "recommended_command": recommended_command(normalized_api_base, output_path),
        "matrix": {
            "status": STATUS_PASSED if not matrix_failures else STATUS_FAILED,
            "trace_id": matrix_trace_id,
            "http_status": matrix_result.status_code,
            "duration_ms": matrix_result.duration_ms,
            "header_trace_id": matrix_result.headers.get("x-trace-id"),
            "body_meta_trace_status": matrix_body_trace_status,
            "body_meta_trace_id": matrix_body_trace_id,
            "failures": matrix_failures,
            "matrix_anomalies": matrix_anomalies,
        },
        "summary": {
            "line_count": len(line_results),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "blocked_count": blocked_count,
            "slow_request_count": len(slow_request_samples),
            "slow_threshold_ms": slow_threshold_ms,
            "first_failure": next(
                (
                    failure
                    for line in line_results
                    for failure in line.get("failures", [])
                ),
                matrix_failures[0] if matrix_failures else None,
            ),
            "slow_request_samples": slow_request_samples,
        },
        "lines": sorted(line_results, key=lambda item: EXPECTED_LINE_KEYS.index(item["line_key"])),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", "--base-url", dest="api_base", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", default=5.0, type=float)
    parser.add_argument("--trace-prefix", default=f"trace-baseline-{int(time.time())}")
    parser.add_argument("--slow-threshold-ms", default=1000.0, type=float)
    parser.add_argument("--allow-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_baseline(
        api_base=args.api_base,
        output_path=args.output,
        timeout=args.timeout,
        trace_prefix=args.trace_prefix,
        slow_threshold_ms=args.slow_threshold_ms,
    )
    write_json(args.output, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"business_line_trace_baseline_live={report['status']} output={args.output}")
    if report["status"] == STATUS_PASSED:
        return 0
    if args.allow_blocked and report["status"] == STATUS_BLOCKED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
