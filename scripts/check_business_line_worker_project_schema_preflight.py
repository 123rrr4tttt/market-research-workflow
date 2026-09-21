#!/usr/bin/env python3
"""Preflight project-scoped process endpoints for worker readback schema drift."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Sequence

try:
    from scripts._automation_runtime import write_json
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import write_json


STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"
SCHEMA_VERSION = "business_line_worker_project_schema_preflight.v1"

HEALTH_PATH = "/api/v1/health"
PROCESS_ENDPOINTS = (
    ("process_tasks", "/api/v1/process/tasks"),
    ("process_logs", "/api/v1/process/logs"),
)
SCHEMA_MISSING_MARKERS = (
    "relation",
    "does not exist",
    "UndefinedTable",
    "ProgrammingError",
    "missing table",
    "schema missing",
)


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    text: str
    error: str


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def normalize_api_base(api_base: str) -> str:
    return api_base.rstrip("/")


def build_url(api_base: str, path: str, *, project_key: str | None = None) -> Annotated[
    str,
    "kit:prepared-command effect_boundary=business_line_worker_schema_preflight witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    base = f"{normalize_api_base(api_base)}{path}"
    if not project_key:
        return base
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urllib.parse.urlencode({'project_key': project_key})}"


def _http_get(url: str, *, timeout: float, project_key: str) -> HttpResult:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "X-Project-Key": project_key,
            "X-Request-Id": f"business-line-worker-project-schema-preflight:{project_key}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
            return HttpResult(int(response.status), body, "")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResult(int(exc.code), body, str(exc))
    except Exception as exc:  # noqa: BLE001
        return HttpResult(None, "", str(exc))


def _json_or_none(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return None


def _compact_tail(value: str, *, max_len: int = 1600) -> str:
    if len(value) <= max_len:
        return value
    return value[-max_len:]


def _contains_schema_missing_marker(text: str) -> bool:
    lowered = text.lower()
    if "does not exist" in lowered and ("relation" in lowered or "table" in lowered):
        return True
    return any(marker.lower() in lowered for marker in SCHEMA_MISSING_MARKERS[2:])


def recommended_next_commands(api_base: str, project_key: str, output_path: Path) -> list[str]:
    return [
        "./scripts/local-deploy.sh start --non-interactive --force",
        (
            "python3 scripts/check_business_line_worker_project_schema_preflight.py "
            f"--api-base {api_base} --project-key {project_key} --output {output_path} "
            "--allow-blocked --json"
        ),
        (
            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
            "main/backend/tests/integration/test_project_schema_guard_unittest.py -q"
        ),
        (
            "python3 scripts/run_backend_migration_live_smoke.py "
            "--output /tmp/mrw_backend_migration_live_smoke.json --allow-blocked --json"
        ),
    ]


def _endpoint_record(
    *,
    name: str,
    url: str,
    result: HttpResult,
    project_key: str,
    required: bool,
) -> dict[str, Any]:
    payload = _json_or_none(result.text)
    text_for_marker = result.text
    if payload is not None:
        text_for_marker += "\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)

    schema_marker = _contains_schema_missing_marker(text_for_marker)
    if result.status_code is None:
        status = STATUS_BLOCKED
        reason = "backend_unreachable" if name == "backend_health" else "endpoint_unreachable"
    elif schema_marker:
        status = STATUS_FAILED
        reason = "schema_missing_marker"
    elif 200 <= result.status_code < 300:
        status = STATUS_PASSED
        reason = "reachable"
    elif 500 <= result.status_code:
        status = STATUS_FAILED
        reason = "endpoint_5xx"
    else:
        status = STATUS_FAILED if required else STATUS_BLOCKED
        reason = "unexpected_http_status"

    return {
        "name": name,
        "url": url,
        "project_key": project_key,
        "required": required,
        "status": status,
        "reason": reason,
        "http_status": result.status_code,
        "error": result.error,
        "schema_missing_marker": schema_marker,
        "json_envelope_status": payload.get("status") if isinstance(payload, dict) else None,
        "body_tail": _compact_tail(result.text),
    }


def run_preflight(*, api_base: str, project_key: str, timeout: float, output_path: Path) -> dict[str, Any]:
    normalized_api_base = normalize_api_base(api_base)
    checked_endpoints: list[dict[str, Any]] = []

    health_url = build_url(normalized_api_base, HEALTH_PATH)
    health_result = _http_get(health_url, timeout=timeout, project_key=project_key)
    health_record = _endpoint_record(
        name="backend_health",
        url=health_url,
        result=health_result,
        project_key=project_key,
        required=True,
    )
    checked_endpoints.append(health_record)

    if health_record["status"] == STATUS_BLOCKED:
        status = STATUS_BLOCKED
    else:
        for name, path in PROCESS_ENDPOINTS:
            endpoint_url = build_url(normalized_api_base, path, project_key=project_key)
            endpoint_result = _http_get(endpoint_url, timeout=timeout, project_key=project_key)
            checked_endpoints.append(
                _endpoint_record(
                    name=name,
                    url=endpoint_url,
                    result=endpoint_result,
                    project_key=project_key,
                    required=True,
                )
            )

        endpoint_statuses = [endpoint["status"] for endpoint in checked_endpoints]
        if any(endpoint["status"] == STATUS_FAILED for endpoint in checked_endpoints):
            status = STATUS_FAILED
        elif any(endpoint["status"] == STATUS_BLOCKED for endpoint in checked_endpoints):
            status = STATUS_BLOCKED
        elif all(endpoint_status == STATUS_PASSED for endpoint_status in endpoint_statuses):
            status = STATUS_PASSED
        else:
            status = STATUS_FAILED

    failed = [endpoint for endpoint in checked_endpoints if endpoint["status"] == STATUS_FAILED]
    blocked = [endpoint for endpoint in checked_endpoints if endpoint["status"] == STATUS_BLOCKED]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "observed_at": utc_now(),
        "api_base": normalized_api_base,
        "project_key": project_key,
        "timeout": timeout,
        "checked_endpoints": checked_endpoints,
        "summary": {
            "checked_count": len(checked_endpoints),
            "passed_count": len([endpoint for endpoint in checked_endpoints if endpoint["status"] == STATUS_PASSED]),
            "failed_count": len(failed),
            "blocked_count": len(blocked),
            "failed_endpoints": [endpoint["name"] for endpoint in failed],
            "blocked_endpoints": [endpoint["name"] for endpoint in blocked],
        },
        "recommended_next_commands": recommended_next_commands(normalized_api_base, project_key, output_path),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True, help="Backend base URL, for example http://127.0.0.1:8000.")
    parser.add_argument("--project-key", required=True, help="Project key to pass via query string and X-Project-Key.")
    parser.add_argument("--timeout", default=5.0, type=float, help="HTTP timeout per request in seconds.")
    parser.add_argument("--output", required=True, type=Path, help="Path to write the preflight JSON artifact.")
    parser.add_argument("--allow-blocked", action="store_true", help="Exit zero for blocked environment states.")
    parser.add_argument("--json", action="store_true", help="Print the full preflight JSON to stdout.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_preflight(
        api_base=args.api_base,
        project_key=args.project_key,
        timeout=args.timeout,
        output_path=args.output,
    )
    write_json(args.output, report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "business_line_worker_project_schema_preflight="
            f"{report['status']} project_key={args.project_key} output={args.output}"
        )

    if report["status"] == STATUS_PASSED:
        return 0
    if report["status"] == STATUS_BLOCKED and args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
