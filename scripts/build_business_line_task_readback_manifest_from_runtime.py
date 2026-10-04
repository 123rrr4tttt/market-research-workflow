#!/usr/bin/env python3
"""Build worker-required task readback manifest candidates from live runtime data."""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Sequence
from urllib import error, request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    from scripts._automation_runtime import (
        CANONICAL_LINE_KEYS,
        WORKER_REQUIRED_LINE_KEYS,
        utc_now,
        write_json,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import (
        CANONICAL_LINE_KEYS,
        WORKER_REQUIRED_LINE_KEYS,
        utc_now,
        write_json,
    )


SCHEMA_VERSION = "business_line_task_readback_manifest_candidate.v1"
MATRIX_PATH = "/api/v1/business-lines/evidence-matrix"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"


SUCCESS_TERMINAL_STATUSES = {
    "completed",
    "succeeded",
    "applied",
    "available",
    "healthy",
}

SYNTHETIC_MARKER_PATTERN = re.compile(
    r"(^|[^a-z0-9])(synthetic|fixture|fake|mock|mocked|generated|dummy|test[-_]placeholder)([^a-z0-9]|$)",
    re.IGNORECASE,
)

RUNTIME_DISCOVERY_PATHS = {
    "ingest": (
        "/api/v1/process/tasks?line_key=ingest&limit=5",
        "/api/v1/process/logs?line_key=ingest&limit=5",
    ),
    "search_discovery_index": (
        "/api/v1/process/tasks?line_key=search_discovery_index&limit=5",
        "/api/v1/process/logs?line_key=search_discovery_index&limit=5",
    ),
    "resource_source_library": (
        "/api/v1/process/tasks?line_key=resource_source_library&limit=5",
        "/api/v1/process/logs?line_key=resource_source_library&limit=5",
    ),
    "writing_knowledge_graph_agent": (
        "/api/v1/process/tasks?line_key=writing_knowledge_graph_agent&limit=5",
        "/api/v1/process/logs?line_key=writing_knowledge_graph_agent&limit=5",
    ),
}


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: str
    error: str | None = None


def normalize_api_base(api_base: str) -> str:
    return api_base.rstrip("/")


def normalize_path(path: str) -> str:
    stripped = path.strip()
    return stripped if stripped.startswith("/") else f"/{stripped}"


def build_url(api_base: str, path: str) -> Annotated[
    str,
    "kit:prepared-command effect_boundary=task_readback_manifest_runtime witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    if path.startswith(("http://", "https://")):
        return path
    return f"{normalize_api_base(api_base)}{normalize_path(path)}"


def append_project_key_query(path: str, project_key: str | None) -> str:
    if not project_key:
        return path
    stripped_project_key = project_key.strip()
    if not stripped_project_key:
        return path
    parts = urlsplit(path)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("project_key", stripped_project_key))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def normalize_line_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def normalize_status(value: object) -> str:
    return str(value).strip().lower()


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _http_get(url: str, *, timeout: float) -> HttpResult:
    req = request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - explicit live backend URL input
            body = response.read().decode("utf-8", errors="replace")
            return HttpResult(status_code=int(response.status), body=body)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResult(status_code=int(exc.code), body=body, error=str(exc))
    except (error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return HttpResult(status_code=None, body="", error=str(exc))


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
    items: list[dict[str, Any]] = []
    for key, value in mapping.items():
        if isinstance(value, dict):
            item = dict(value)
            item.setdefault("line_key", key)
            items.append(item)
    return items


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


def extract_contract_version(payload: Any) -> str | None:
    for root in payload_roots(payload):
        if isinstance(root, dict) and is_present(root.get("contract_version")):
            return str(root["contract_version"])
    return None


def index_worker_lines(lines: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    by_key: dict[str, dict[str, Any]] = {}
    seen: dict[str, int] = {}
    unexpected_line_keys: list[str] = []
    invalid_line_keys: list[str] = []

    for line in lines:
        raw_key = line.get("line_key")
        if not isinstance(raw_key, str) or not raw_key.strip():
            invalid_line_keys.append("<missing>")
            continue
        line_key = normalize_line_key(raw_key)
        if line_key in WORKER_REQUIRED_LINE_KEYS:
            seen[line_key] = seen.get(line_key, 0) + 1
            by_key.setdefault(line_key, line)
        elif line_key not in CANONICAL_LINE_KEYS:
            unexpected_line_keys.append(line_key)

    return by_key, {
        "missing_line_keys": sorted(set(WORKER_REQUIRED_LINE_KEYS) - set(by_key)),
        "unexpected_line_keys": sorted(set(unexpected_line_keys)),
        "invalid_line_keys": sorted(set(invalid_line_keys)),
        "duplicate_line_keys": sorted(line_key for line_key, count in seen.items() if count > 1),
    }


def matrix_has_anomalies(anomalies: dict[str, list[str]]) -> bool:
    return bool(anomalies["missing_line_keys"] or anomalies["invalid_line_keys"] or anomalies["duplicate_line_keys"])


def async_task_readback_contract(line: dict[str, Any]) -> dict[str, Any]:
    contract = line.get("async_task_readback")
    return contract if isinstance(contract, dict) else {}


def extract_live_smoke_probe_path(line: dict[str, Any]) -> str | None:
    live_smoke = line.get("live_smoke")
    if not isinstance(live_smoke, dict):
        return None
    probe_path = live_smoke.get("probe_path")
    if not isinstance(probe_path, str) or not probe_path.strip():
        return None
    return normalize_path(probe_path)


def has_template_placeholder(path: str) -> bool:
    return "{" in path or "}" in path


def candidate_probe_paths(
    line_key: str,
    line: dict[str, Any],
    contract: dict[str, Any],
    *,
    project_key: str | None,
) -> list[str]:
    paths: list[str] = []
    raw_paths = contract.get("readback_paths")
    if isinstance(raw_paths, list):
        for raw_path in raw_paths:
            if isinstance(raw_path, str) and raw_path.strip() and not has_template_placeholder(raw_path):
                paths.append(normalize_path(raw_path))

    probe_path = extract_live_smoke_probe_path(line)
    if probe_path is not None:
        paths.append(probe_path)

    paths.extend(append_project_key_query(path, project_key) for path in RUNTIME_DISCOVERY_PATHS.get(line_key, ()))

    deduped: list[str] = []
    for path in paths:
        if path not in deduped:
            deduped.append(path)
    return deduped


def string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(string_values(item))
        return values
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(string_values(item))
        return values
    return []


def has_synthetic_marker(value: Any) -> bool:
    return any(SYNTHETIC_MARKER_PATTERN.search(text) is not None for text in string_values(value))


def iter_dicts(value: Any) -> list[dict[str, Any]]:
    dicts: list[dict[str, Any]] = []
    if isinstance(value, dict):
        dicts.append(value)
        for nested in value.values():
            dicts.extend(iter_dicts(nested))
    elif isinstance(value, list):
        for item in value:
            dicts.extend(iter_dicts(item))
    return dicts


def first_present(*values: Any) -> Any:
    for value in values:
        if is_present(value):
            return value
    return None


def find_field(container: dict[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        value = container.get(name)
        if is_present(value):
            return value
    return None


def envelope_trace_id(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None
    meta = payload.get("meta")
    if isinstance(meta, dict):
        return find_field(meta, ("trace_id",))
    return None


def extract_events(container: dict[str, Any]) -> list[Any]:
    for key in ("events", "event_log", "history", "logs"):
        value = container.get(key)
        if isinstance(value, list) and value:
            return list(value)
    return []


def event_terminal_status(event: Any) -> str | None:
    if isinstance(event, str):
        status = normalize_status(event)
        return status if status in SUCCESS_TERMINAL_STATUSES else None
    if not isinstance(event, dict):
        return None
    for key in ("status", "terminal_status", "event", "event_type", "name", "type"):
        if key in event:
            status = normalize_status(event[key])
            if status in SUCCESS_TERMINAL_STATUSES:
                return status
    return None


def has_terminal_event(events: Any) -> bool:
    return isinstance(events, list) and any(event_terminal_status(event) is not None for event in events)


def event_tokens(event: Any) -> set[str]:
    if isinstance(event, str):
        return {normalize_status(event)}
    if not isinstance(event, dict):
        return set()
    tokens: set[str] = set()
    for key in ("status", "state", "event", "event_name", "event_type", "type", "name"):
        value = event.get(key)
        if is_present(value):
            tokens.add(normalize_status(value))
    return tokens


def required_events_from_contract(contract: dict[str, Any]) -> list[str]:
    raw_events = contract.get("required_events")
    if not isinstance(raw_events, list):
        return []
    return [normalize_status(event) for event in raw_events if isinstance(event, str) and event.strip()]


def missing_required_events(events: list[Any], contract: dict[str, Any]) -> list[str]:
    required = required_events_from_contract(contract)
    if not required:
        return []
    observed: set[str] = set()
    for event in events:
        observed.update(event_tokens(event))
    return [event for event in required if event not in observed]


def extract_terminal_status(container: dict[str, Any], events: list[Any]) -> str | None:
    for key in ("status", "state", "task_status", "run_status", "lifecycle_status"):
        value = container.get(key)
        if is_present(value) and normalize_status(value) in SUCCESS_TERMINAL_STATUSES:
            return normalize_status(value)
    for event in events:
        status = event_terminal_status(event)
        if status is not None:
            return status
    return None


def build_candidate_sample(
    *,
    line_key: str,
    endpoint: str,
    payload: Any,
    container: dict[str, Any],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=task_readback_http_payload+container "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    events = extract_events(container)
    task_id = find_field(container, ("task_id", "taskId"))
    run_id = find_field(container, ("run_id", "runId"))
    worker_name = find_field(container, ("worker_name", "workerName", "worker"))
    queue = find_field(container, ("queue", "queue_name", "queueName"))
    trace_id = first_present(find_field(container, ("trace_id", "traceId")), envelope_trace_id(payload))
    readback_endpoint = find_field(container, ("readback_endpoint", "readbackEndpoint"))
    readback_path = find_field(container, ("readback_path", "readbackPath"))
    terminal_status = extract_terminal_status(container, events)

    sample: dict[str, Any] = {
        "line_key": line_key,
        "status": terminal_status,
        "events": events,
        "worker_name": str(worker_name).strip() if is_present(worker_name) else None,
        "queue": str(queue).strip() if is_present(queue) else None,
        "trace_id": str(trace_id).strip() if is_present(trace_id) else None,
        "readback_endpoint": str(readback_endpoint).strip()
        if is_present(readback_endpoint)
        else endpoint,
        "mocked": False,
        "skipped": False,
    }
    if is_present(readback_path):
        sample["readback_path"] = str(readback_path).strip()
    elif not endpoint.startswith(("http://", "https://")):
        sample["readback_path"] = endpoint
    if is_present(task_id):
        sample["task_id"] = str(task_id).strip()
    if is_present(run_id):
        sample["run_id"] = str(run_id).strip()
    return sample


def missing_sample_fields(sample: dict[str, Any], contract: dict[str, Any] | None = None) -> list[str]:
    missing = [
        field
        for field in ("worker_name", "queue", "trace_id", "readback_endpoint", "events", "status")
        if not is_present(sample.get(field))
    ]
    if not (is_present(sample.get("task_id")) or is_present(sample.get("run_id"))):
        missing.append("task_id_or_run_id")
    if not (is_present(sample.get("readback_endpoint")) or is_present(sample.get("readback_path"))):
        missing.append("readback_endpoint_or_readback_path")
    if not has_terminal_event(sample.get("events")):
        missing.append("terminal_events")
    if sample.get("status") not in SUCCESS_TERMINAL_STATUSES:
        missing.append("success_status")
    missing.extend(f"required_event:{event}" for event in missing_required_events(sample.get("events") or [], contract or {}))
    return sorted(set(missing))


def sample_score(sample: dict[str, Any]) -> int:
    fields = (
        "task_id",
        "run_id",
        "worker_name",
        "queue",
        "trace_id",
        "readback_endpoint",
        "readback_path",
        "status",
    )
    score = sum(1 for field in fields if is_present(sample.get(field)))
    if has_terminal_event(sample.get("events")):
        score += 2
    return score


def sample_matches_line(sample: dict[str, Any], line_key: str) -> bool:
    raw_line_key = sample.get("line_key")
    return not is_present(raw_line_key) or normalize_line_key(raw_line_key) == line_key


def is_process_runtime_endpoint(endpoint: str) -> bool:
    normalized = normalize_path(endpoint)
    return normalized.startswith("/api/v1/process/tasks") or normalized.startswith("/api/v1/process/logs")


def is_process_db_job_endpoint(endpoint: str) -> bool:
    normalized = normalize_path(endpoint).split("?", 1)[0]
    return normalized.startswith("/api/v1/process/db-job-")


def exact_process_readback_endpoint(endpoint: str, container: dict[str, Any]) -> str | None:
    if not is_process_runtime_endpoint(endpoint):
        return None
    task_id = find_field(container, ("task_id", "taskId"))
    if is_present(task_id) and str(task_id).strip().startswith("db-job-"):
        return f"/api/v1/process/{str(task_id).strip()}"
    readback_source = find_field(container, ("readback_source", "readbackSource"))
    run_id = find_field(container, ("run_id", "runId"))
    if (
        is_present(readback_source)
        and normalize_status(readback_source) == "etl_job_runs"
        and is_present(run_id)
        and str(run_id).strip().isdigit()
    ):
        return f"/api/v1/process/db-job-{str(run_id).strip()}"
    return None


def apply_project_key_to_sample_readback(sample: dict[str, Any], project_key: str | None) -> dict[str, Any]:
    if not project_key:
        return sample
    scoped = dict(sample)
    for key in ("readback_endpoint", "readback_path"):
        value = scoped.get(key)
        if isinstance(value, str) and value.strip() and is_process_db_job_endpoint(value):
            scoped[key] = append_project_key_query(value.strip(), project_key)
    return scoped


def best_sample_from_payload(
    line_key: str,
    endpoint: str,
    payload: Any,
    *,
    project_key: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if has_synthetic_marker(payload):
        return None, "runtime_payload_contains_disallowed_marker"

    candidates: list[dict[str, Any]] = []
    require_explicit_line_key = is_process_runtime_endpoint(endpoint)
    for container in iter_dicts(payload):
        raw_line_key = container.get("line_key")
        if require_explicit_line_key and not is_present(raw_line_key):
            continue
        if is_present(raw_line_key) and normalize_line_key(raw_line_key) != line_key:
            continue
        sample = build_candidate_sample(line_key=line_key, endpoint=endpoint, payload=payload, container=container)
        exact_endpoint = exact_process_readback_endpoint(endpoint, container)
        if exact_endpoint is not None:
            sample["readback_endpoint"] = exact_endpoint
            sample["readback_path"] = exact_endpoint
        sample = apply_project_key_to_sample_readback(sample, project_key)
        if sample_matches_line(sample, line_key):
            candidates.append(sample)

    if not candidates:
        return None, "runtime_payload_has_no_candidate_objects"
    return max(candidates, key=sample_score), None


def classify_probe_failure(attempts: list[dict[str, Any]]) -> tuple[str, str | None]:
    no_candidate = next(
        (
            attempt
            for attempt in attempts
            if 200 <= (attempt.get("http_status") or 0) < 300 and attempt.get("candidate_error")
        ),
        None,
    )
    if no_candidate is not None:
        return str(no_candidate["candidate_error"]), None

    server_error = next((attempt for attempt in attempts if (attempt.get("http_status") or 0) >= 500), None)
    if server_error is not None:
        return "readback_probe_server_error", server_error.get("error")
    http_error = next((attempt for attempt in attempts if attempt.get("http_status") is not None), None)
    if http_error is not None:
        return "readback_probe_http_error", http_error.get("error")
    return "readback_endpoint_unreachable", attempts[-1].get("error") if attempts else None


def probe_line(
    *,
    api_base: str,
    timeout: float,
    line_key: str,
    line: dict[str, Any],
    contract: dict[str, Any],
    project_key: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    attempts: list[dict[str, Any]] = []
    best_blocked_sample: dict[str, Any] | None = None

    for endpoint in candidate_probe_paths(line_key, line, contract, project_key=project_key):
        result = _http_get(build_url(api_base, endpoint), timeout=timeout)
        attempt: dict[str, Any] = {
            "readback_endpoint": endpoint,
            "http_status": result.status_code,
            "error": result.error,
        }
        attempts.append(attempt)

        if result.status_code is None:
            continue
        if result.status_code >= 500:
            return (
                {
                    "line_key": line_key,
                    "status": STATUS_FAILED,
                    "reason": "readback_probe_server_error",
                    "missing_fields": [],
                    "attempts": attempts,
                    "sample_count": 0,
                },
                None,
            )
        if not (200 <= result.status_code < 300):
            continue

        payload, json_error = load_json_payload(result)
        if json_error is not None:
            attempt["json_error"] = json_error
            continue
        sample, blocked_reason = best_sample_from_payload(line_key, endpoint, payload, project_key=project_key)
        if sample is None:
            attempt["candidate_error"] = blocked_reason
            continue

        missing = missing_sample_fields(sample, contract)
        attempt["missing_fields"] = missing
        if not missing:
            return (
                {
                    "line_key": line_key,
                    "status": STATUS_PASSED,
                    "reason": "runtime_candidate_readback_collected",
                    "missing_fields": [],
                    "readback_endpoint": endpoint,
                    "attempts": attempts,
                    "sample_count": 1,
                },
                sample,
            )
        if best_blocked_sample is None or sample_score(sample) > sample_score(best_blocked_sample):
            best_blocked_sample = sample

    reason, probe_error = classify_probe_failure(attempts)
    missing_fields = missing_sample_fields(best_blocked_sample, contract) if best_blocked_sample is not None else []
    if best_blocked_sample is not None:
        reason = "runtime_candidate_missing_required_fields"
    return (
        {
            "line_key": line_key,
            "status": STATUS_BLOCKED,
            "reason": reason,
            "missing_fields": missing_fields,
            "attempts": attempts,
            "error": probe_error,
            "sample_count": 0,
        },
        None,
    )


def recommended_next_commands(api_base: str, output_path: Path, project_key: str | None) -> list[str]:
    project_key_arg = f" --project-key {project_key.strip()}" if project_key and project_key.strip() else ""
    commands = [
        f"python3 scripts/check_business_line_task_readback_manifest.py {output_path} --json",
        (
            "python3 scripts/run_business_line_async_task_readback_live_samples.py "
            f"--api-base {api_base} --output /tmp/business-line-async-task-readback-live-samples.json "
            f"--task-readback-manifest {output_path}{project_key_arg} --allow-blocked --json"
        ),
    ]
    if project_key_arg:
        commands.append(
            "python3 scripts/build_business_line_task_readback_manifest_from_runtime.py "
            f"--api-base {api_base} --output {output_path}{project_key_arg} --allow-blocked --json"
        )
    return commands


def blocked_matrix_report(
    *,
    api_base: str,
    output_path: Path,
    project_key: str | None,
    matrix_path: str,
    matrix_result: HttpResult,
    observed_at: str,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=blocked_evidence_matrix_http_result "
    "witness=test:test_w11_non_authoritative_metadata",
]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BLOCKED,
        "observed_at": observed_at,
        "api_base": api_base,
        "project_key": project_key,
        "matrix_path": matrix_path,
        "recommended_next_commands": recommended_next_commands(api_base, output_path, project_key),
        "expected_line_keys": list(WORKER_REQUIRED_LINE_KEYS),
        "matrix": {
            "status": STATUS_BLOCKED,
            "http_status": matrix_result.status_code,
            "reason": "evidence_matrix_unreachable",
            "error": matrix_result.error,
        },
        "matrix_anomalies": {
            "missing_line_keys": [],
            "unexpected_line_keys": [],
            "invalid_line_keys": [],
            "duplicate_line_keys": [],
        },
        "summary": {
            "passed_line_keys": [],
            "blocked_line_keys": list(WORKER_REQUIRED_LINE_KEYS),
            "failed_line_keys": [],
            "sample_line_keys": [],
        },
        "task_readback_manifest": [],
        "samples": [],
        "lines": [
            {
                "line_key": line_key,
                "status": STATUS_BLOCKED,
                "reason": "evidence_matrix_unreachable",
                "missing_fields": [],
                "sample_count": 0,
            }
            for line_key in WORKER_REQUIRED_LINE_KEYS
        ],
    }


def build_manifest_candidate(
    *,
    api_base: str,
    output_path: Path,
    timeout: float,
    project_key: str | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=evidence_matrix_http_readback+task_readback_payloads "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    observed_at = utc_now()
    normalized_api_base = normalize_api_base(api_base)
    normalized_project_key = project_key.strip() if project_key and project_key.strip() else None
    matrix_path = append_project_key_query(MATRIX_PATH, normalized_project_key)
    matrix_result = _http_get(build_url(normalized_api_base, matrix_path), timeout=timeout)
    if matrix_result.status_code is None:
        return blocked_matrix_report(
            api_base=normalized_api_base,
            output_path=output_path,
            project_key=normalized_project_key,
            matrix_path=matrix_path,
            matrix_result=matrix_result,
            observed_at=observed_at,
        )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_FAILED,
        "observed_at": observed_at,
        "api_base": normalized_api_base,
        "project_key": normalized_project_key,
        "matrix_path": matrix_path,
        "recommended_next_commands": recommended_next_commands(normalized_api_base, output_path, normalized_project_key),
        "expected_line_keys": list(WORKER_REQUIRED_LINE_KEYS),
        "matrix": {
            "status": STATUS_PASSED if 200 <= matrix_result.status_code < 300 else STATUS_FAILED,
            "http_status": matrix_result.status_code,
            "reason": "evidence_matrix_reachable"
            if 200 <= matrix_result.status_code < 300
            else "evidence_matrix_http_error",
            "error": matrix_result.error,
        },
        "matrix_anomalies": {
            "missing_line_keys": [],
            "unexpected_line_keys": [],
            "invalid_line_keys": [],
            "duplicate_line_keys": [],
        },
        "summary": {
            "passed_line_keys": [],
            "blocked_line_keys": [],
            "failed_line_keys": [],
            "sample_line_keys": [],
        },
        "task_readback_manifest": [],
        "samples": [],
        "lines": [],
    }

    if not (200 <= matrix_result.status_code < 300):
        report["summary"]["failed_line_keys"] = list(WORKER_REQUIRED_LINE_KEYS)
        report["lines"] = [
            {
                "line_key": line_key,
                "status": STATUS_FAILED,
                "reason": "evidence_matrix_http_error",
                "missing_fields": [],
                "sample_count": 0,
            }
            for line_key in WORKER_REQUIRED_LINE_KEYS
        ]
        return report

    matrix_payload, json_error = load_json_payload(matrix_result)
    if json_error is not None:
        report["matrix"]["status"] = STATUS_FAILED
        report["matrix"]["reason"] = "evidence_matrix_invalid_json"
        report["matrix"]["error"] = json_error
        report["summary"]["failed_line_keys"] = list(WORKER_REQUIRED_LINE_KEYS)
        return report

    lines = extract_lines(matrix_payload)
    by_key, matrix_anomalies = index_worker_lines(lines)
    report["matrix"]["contract_version"] = extract_contract_version(matrix_payload)
    report["matrix"]["observed_line_count"] = len(lines)
    report["matrix_anomalies"] = matrix_anomalies

    line_results: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for line_key in WORKER_REQUIRED_LINE_KEYS:
        line = by_key.get(line_key)
        if line is None:
            line_results.append(
                {
                    "line_key": line_key,
                    "status": STATUS_FAILED,
                    "reason": "missing_line_in_evidence_matrix",
                    "missing_fields": [],
                    "sample_count": 0,
                }
            )
            continue

        contract = async_task_readback_contract(line)
        if not contract:
            line_results.append(
                {
                    "line_key": line_key,
                    "status": STATUS_FAILED,
                    "reason": "missing_async_task_readback_contract",
                    "missing_fields": [],
                    "sample_count": 0,
                }
            )
            continue
        if contract.get("requires_worker_readback") is not True:
            line_results.append(
                {
                    "line_key": line_key,
                    "status": STATUS_FAILED,
                    "reason": "line_does_not_require_worker_readback",
                    "missing_fields": [],
                    "sample_count": 0,
                }
            )
            continue

        line_result, sample = probe_line(
            api_base=normalized_api_base,
            timeout=timeout,
            line_key=line_key,
            line=line,
            contract=contract,
            project_key=normalized_project_key,
        )
        line_results.append(line_result)
        if sample is not None:
            samples.append(sample)

    failed_line_keys = [line["line_key"] for line in line_results if line["status"] == STATUS_FAILED]
    blocked_line_keys = [line["line_key"] for line in line_results if line["status"] == STATUS_BLOCKED]
    passed_line_keys = [line["line_key"] for line in line_results if line["status"] == STATUS_PASSED]

    report["lines"] = line_results
    report["samples"] = samples
    report["task_readback_manifest"] = samples
    report["summary"] = {
        "passed_line_keys": passed_line_keys,
        "blocked_line_keys": blocked_line_keys,
        "failed_line_keys": failed_line_keys,
        "sample_line_keys": [sample["line_key"] for sample in samples],
    }

    if matrix_has_anomalies(matrix_anomalies) or failed_line_keys:
        report["status"] = STATUS_FAILED
    elif blocked_line_keys:
        report["status"] = STATUS_BLOCKED
    elif len(passed_line_keys) == len(WORKER_REQUIRED_LINE_KEYS):
        report["status"] = STATUS_PASSED
    else:
        report["status"] = STATUS_FAILED
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True, help="Backend base URL, for example http://127.0.0.1:8000.")
    parser.add_argument("--output", required=True, type=Path, help="Path to write the manifest candidate JSON.")
    parser.add_argument("--timeout", default=5.0, type=float, help="HTTP timeout per request in seconds.")
    parser.add_argument("--project-key", help="Optional project_key query value for runtime discovery endpoints.")
    parser.add_argument("--allow-blocked", action="store_true", help="Return zero when only environment blockers occur.")
    parser.add_argument("--json", action="store_true", help="Print the full manifest candidate JSON to stdout.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_manifest_candidate(
        api_base=args.api_base,
        output_path=args.output,
        timeout=args.timeout,
        project_key=args.project_key,
    )
    write_json(args.output, report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"business_line_task_readback_manifest_candidate={report['status']} output={args.output}")

    if report["status"] == STATUS_PASSED:
        return 0
    if report["status"] == STATUS_BLOCKED and args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
