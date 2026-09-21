#!/usr/bin/env python3
"""Generate live async task readback samples for business-line contracts."""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Sequence
from urllib import error, parse, request

try:
    from scripts._automation_runtime import utc_now, write_json
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import utc_now, write_json


SCHEMA_VERSION = "business_line_async_task_readback_live_samples.v1"
MATRIX_PATH = "/api/v1/business-lines/evidence-matrix"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

EXPECTED_LINE_KEYS = (
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "projects_config_workflow",
    "dashboard_admin_governance",
    "writing_knowledge_graph_agent",
    "runtime_ops",
)

NON_WORKER_TERMINAL_STATUS = {
    "projects_config_workflow": "applied",
    "dashboard_admin_governance": "available",
    "runtime_ops": "healthy",
}

FALLBACK_READBACK_PATHS = {
    "projects_config_workflow": "/api/v1/projects",
    "dashboard_admin_governance": "/api/v1/dashboard/stats",
    "runtime_ops": "/api/v1/health/deep",
}

WORKER_REQUIRED_LINE_KEYS = {
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "writing_knowledge_graph_agent",
}

PLACEHOLDER_PATTERN = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)}")
SUCCESS_TERMINAL_STATUSES = ("completed", "succeeded", "applied", "available", "healthy")


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: str
    error: str | None = None


@dataclass(frozen=True)
class ManifestIndex:
    path: str | None
    status: str
    reason: str | None
    error: str | None
    items_by_line: dict[str, dict[str, Any]]
    unexpected_line_keys: list[str]
    duplicate_line_keys: list[str]


def normalize_api_base(api_base: str) -> str:
    return api_base.rstrip("/")


def build_url(api_base: str, path: str) -> Annotated[
    str,
    "kit:prepared-command effect_boundary=evidence_matrix_http_read witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalize_api_base(api_base)}{normalized_path}"


def append_query_param(path: str, key: str, value: str | None) -> str:
    if not value:
        return path
    parsed = parse.urlsplit(path)
    query_pairs = parse.parse_qsl(parsed.query, keep_blank_values=True)
    if any(existing_key == key for existing_key, _existing_value in query_pairs):
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{parse.urlencode({key: value})}"


def apply_project_key(path: str, project_key: str | None) -> str:
    return append_query_param(path, "project_key", project_key)


def build_probe_url(api_base: str, endpoint: str) -> Annotated[
    str,
    "kit:prepared-command effect_boundary=task_readback_probe_http_read witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    return build_url(api_base, endpoint)


def recommended_command(
    api_base: str,
    output_path: Path,
    manifest_path: Path | None = None,
    *,
    project_key: str | None = None,
) -> str:
    command = (
        "python3 scripts/run_business_line_async_task_readback_live_samples.py "
        f"--api-base {api_base} --output {output_path} --allow-blocked --json"
    )
    if manifest_path is not None:
        command += f" --task-readback-manifest {manifest_path}"
    if project_key:
        command += f" --project-key {project_key}"
    return command


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


def extract_contract_version(payload: Any) -> str | None:
    for root in payload_roots(payload):
        if isinstance(root, dict) and root.get("contract_version"):
            return str(root["contract_version"])
    return None


def normalize_line_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def normalize_status(value: object) -> str:
    return str(value).strip().lower()


def index_matrix_lines(lines: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    by_key: dict[str, dict[str, Any]] = {}
    seen: dict[str, int] = {}
    invalid_line_keys: list[str] = []

    for line in lines:
        raw_key = line.get("line_key")
        if not isinstance(raw_key, str) or not raw_key.strip():
            invalid_line_keys.append("<missing>")
            continue
        line_key = normalize_line_key(raw_key)
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


def matrix_has_anomalies(matrix_anomalies: dict[str, list[str]]) -> bool:
    return any(matrix_anomalies.values())


def manifest_has_anomalies(manifest_index: ManifestIndex) -> bool:
    return bool(manifest_index.path and (manifest_index.unexpected_line_keys or manifest_index.duplicate_line_keys))


def manifest_anomaly_reason(line_key: str, manifest_index: ManifestIndex) -> str | None:
    if not manifest_has_anomalies(manifest_index):
        return None
    if line_key in manifest_index.duplicate_line_keys:
        return "task_readback_manifest_duplicate_line_keys"
    if manifest_index.unexpected_line_keys:
        return "task_readback_manifest_unexpected_line_keys"
    if manifest_index.duplicate_line_keys:
        return "task_readback_manifest_duplicate_line_keys"
    return "task_readback_manifest_anomaly"


def async_task_readback_contract(line: dict[str, Any]) -> dict[str, Any]:
    contract = line.get("async_task_readback")
    return contract if isinstance(contract, dict) else {}


def has_template_placeholder(path: str) -> bool:
    return "{" in path or "}" in path


def normalize_path(path: str) -> str:
    stripped = path.strip()
    return stripped if stripped.startswith("/") else f"/{stripped}"


def extract_live_smoke_probe_path(line: dict[str, Any]) -> str | None:
    live_smoke = line.get("live_smoke")
    if not isinstance(live_smoke, dict):
        return None
    probe_path = live_smoke.get("probe_path")
    if not isinstance(probe_path, str) or not probe_path.strip():
        return None
    return normalize_path(probe_path)


def candidate_readback_paths(line: dict[str, Any], line_key: str, contract: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    raw_paths = contract.get("readback_paths")
    if isinstance(raw_paths, list):
        for raw_path in raw_paths:
            if isinstance(raw_path, str) and raw_path.strip() and not has_template_placeholder(raw_path):
                paths.append(normalize_path(raw_path))

    probe_path = extract_live_smoke_probe_path(line)
    if probe_path:
        paths.append(probe_path)

    fallback = FALLBACK_READBACK_PATHS.get(line_key)
    if fallback:
        paths.append(fallback)

    deduped: list[str] = []
    for path in paths:
        if path not in deduped:
            deduped.append(path)
    return deduped


def load_json_file(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, str(exc)
    except json.JSONDecodeError as exc:
        return None, f"manifest is not valid JSON: {exc}"


def extract_manifest_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if is_present(payload.get("line_key")):
        return [payload]
    for root in payload_roots(payload):
        if not isinstance(root, dict):
            continue
        for key in ("items", "samples", "task_readback_samples", "task_readback_manifest", "manifest", "lines"):
            value = root.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return [dict(item, line_key=line_key) for line_key, item in value.items() if isinstance(item, dict)]
    return []


def load_manifest_index(path: Path | None) -> ManifestIndex:
    if path is None:
        return ManifestIndex(
            path=None,
            status=STATUS_BLOCKED,
            reason="task_readback_manifest_not_provided",
            error=None,
            items_by_line={},
            unexpected_line_keys=[],
            duplicate_line_keys=[],
        )

    payload, load_error = load_json_file(path)
    if load_error is not None:
        return ManifestIndex(
            path=str(path),
            status=STATUS_FAILED,
            reason="task_readback_manifest_load_failed",
            error=load_error,
            items_by_line={},
            unexpected_line_keys=[],
            duplicate_line_keys=[],
        )

    items_by_line: dict[str, dict[str, Any]] = {}
    unexpected_line_keys: list[str] = []
    duplicate_line_keys: list[str] = []
    for item in extract_manifest_items(payload):
        raw_line_key = item.get("line_key")
        if not is_present(raw_line_key):
            unexpected_line_keys.append("<missing>")
            continue
        line_key = normalize_line_key(raw_line_key)
        if line_key not in EXPECTED_LINE_KEYS:
            unexpected_line_keys.append(line_key)
            continue
        if line_key in items_by_line:
            duplicate_line_keys.append(line_key)
            continue
        normalized_item = dict(item)
        normalized_item["line_key"] = line_key
        items_by_line[line_key] = normalized_item

    return ManifestIndex(
        path=str(path),
        status=STATUS_PASSED,
        reason=None,
        error=None,
        items_by_line=items_by_line,
        unexpected_line_keys=sorted(set(unexpected_line_keys)),
        duplicate_line_keys=sorted(set(duplicate_line_keys)),
    )


def item_scalar_values(item: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in item.items():
        if isinstance(value, (str, int, float)) and str(value).strip():
            values[str(key)] = str(value).strip()
    return values


def render_readback_template(template: str, item: dict[str, Any]) -> str | None:
    values = item_scalar_values(item)
    placeholders = PLACEHOLDER_PATTERN.findall(template)
    if not placeholders:
        return template if template.startswith(("http://", "https://")) else normalize_path(template)
    missing = [placeholder for placeholder in placeholders if placeholder not in values]
    if missing:
        return None

    rendered = template
    for placeholder in placeholders:
        rendered = rendered.replace(f"{{{placeholder}}}", values[placeholder])
    if has_template_placeholder(rendered):
        return None
    return rendered if rendered.startswith(("http://", "https://")) else normalize_path(rendered)


def is_process_collection_endpoint(endpoint: str) -> bool:
    if endpoint.startswith(("http://", "https://")):
        path = "/" + endpoint.split("://", 1)[1].split("/", 1)[1] if "/" in endpoint.split("://", 1)[1] else "/"
    else:
        path = endpoint
    normalized = normalize_path(path).split("?", 1)[0]
    return normalized in {"/api/v1/process/tasks", "/api/v1/process/logs"}


def resolve_manifest_readback_endpoint(
    item: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    for key in ("readback_endpoint", "readback_path"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            rendered = render_readback_template(value.strip(), item)
            if rendered is None:
                return None, None, "readback_location_unresolved"
            if is_process_collection_endpoint(rendered):
                return None, None, "readback_location_not_precise"
            return rendered, rendered if not rendered.startswith(("http://", "https://")) else None, None

    raw_paths = contract.get("readback_paths")
    if isinstance(raw_paths, list):
        for raw_path in raw_paths:
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            rendered = render_readback_template(raw_path.strip(), item)
            if rendered is not None:
                if is_process_collection_endpoint(rendered):
                    continue
                return rendered, rendered, None
    return None, None, "readback_location_unresolved"


def contract_terminal_states(contract: dict[str, Any]) -> list[str]:
    states = contract.get("terminal_states")
    if isinstance(states, list):
        normalized = [normalize_status(state) for state in states if is_present(state)]
        if normalized:
            return normalized
    return list(SUCCESS_TERMINAL_STATUSES)


def success_terminal_status(contract: dict[str, Any]) -> str:
    states = set(contract_terminal_states(contract))
    for status in SUCCESS_TERMINAL_STATUSES:
        if status in states:
            return status
    return "completed"


def iter_payload_dicts(payload: Any) -> list[dict[str, Any]]:
    dicts: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        dicts.append(payload)
        for key in ("data", "result", "task", "run", "item", "action", "batch", "session", "artifact"):
            value = payload.get(key)
            if isinstance(value, dict):
                dicts.append(value)
    return dicts


def extract_terminal_status(payload: Any, item: dict[str, Any], contract: dict[str, Any]) -> str:
    allowed = set(contract_terminal_states(contract))
    for container in iter_payload_dicts(payload):
        for key in ("status", "state", "task_status", "run_status", "lifecycle_status"):
            value = container.get(key)
            if is_present(value) and normalize_status(value) in allowed:
                return normalize_status(value)

    manifest_status = item.get("status")
    if is_present(manifest_status) and normalize_status(manifest_status) in allowed:
        return normalize_status(manifest_status)
    return success_terminal_status(contract)


def extract_worker_terminal_status(payload: Any, contract: dict[str, Any]) -> str | None:
    allowed = set(contract_terminal_states(contract)) & set(SUCCESS_TERMINAL_STATUSES)
    if not allowed:
        allowed = set(SUCCESS_TERMINAL_STATUSES)
    for container in iter_payload_dicts(payload):
        for key in ("status", "state", "task_status", "run_status", "lifecycle_status"):
            value = container.get(key)
            if is_present(value) and normalize_status(value) in allowed:
                return normalize_status(value)
    return None


def extract_worker_events(payload: Any) -> list[Any] | None:
    for container in iter_payload_dicts(payload):
        for key in ("events", "event_log", "history", "logs"):
            value = container.get(key)
            if isinstance(value, list) and value:
                return list(value)
    return None


def event_contains_terminal_status(event: Any, terminal_status: str) -> bool:
    if isinstance(event, str):
        return normalize_status(event) == terminal_status
    if isinstance(event, dict):
        for key in ("status", "state", "event", "event_name", "type", "name"):
            value = event.get(key)
            if is_present(value) and normalize_status(value) == terminal_status:
                return True
    return False


def extract_events(payload: Any, item: dict[str, Any], contract: dict[str, Any], terminal_status: str) -> list[Any]:
    payload_events = extract_worker_events(payload)
    if payload_events:
        events = list(payload_events)
        if not any(event_contains_terminal_status(event, terminal_status) for event in events):
            events.append(terminal_status)
        return events

    manifest_events = item.get("events")
    if isinstance(manifest_events, list) and manifest_events:
        events = list(manifest_events)
        if terminal_status not in {event if isinstance(event, str) else "" for event in events}:
            events.append(terminal_status)
        return events

    required_events = contract.get("required_events")
    events = [event for event in required_events if isinstance(event, str) and event.strip()] if isinstance(required_events, list) else []
    if terminal_status not in events:
        events.append(terminal_status)
    return events


def payload_scalar_value(payload: Any, *keys: str) -> str | None:
    for container in iter_payload_dicts(payload):
        for key in keys:
            value = container.get(key)
            if is_present(value) and isinstance(value, (str, int, float)):
                return str(value).strip()
        meta = container.get("meta")
        if isinstance(meta, dict):
            for key in keys:
                value = meta.get(key)
                if is_present(value) and isinstance(value, (str, int, float)):
                    return str(value).strip()
    return None


def trace_id_from_payload(payload: Any, line_key: str, endpoint: str) -> str:
    if isinstance(payload, dict):
        meta = payload.get("meta")
        if isinstance(meta, dict):
            for key in ("trace_id", "request_id", "correlation_id"):
                value = meta.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        for key in ("trace_id", "request_id", "correlation_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    stable_endpoint = endpoint.strip("/").replace("/", "-").replace("?", "-").replace("=", "-")
    return f"live-readback-{line_key}-{stable_endpoint}"


def worker_trace_id_from_payload(payload: Any) -> str | None:
    return payload_scalar_value(payload, "trace_id")


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


def readback_identity_matches_manifest(payload: Any, item: dict[str, Any]) -> tuple[bool, str | None]:
    identity_fields = ("task_id", "run_id")
    observed = {
        key: payload_scalar_value(payload, key)
        for key in identity_fields
        if is_present(item.get(key))
    }
    observed_present = {key: value for key, value in observed.items() if is_present(value)}
    if not observed_present:
        return False, "live_readback_identity_missing"
    mismatched = [
        key
        for key, observed_value in observed_present.items()
        if observed_value != str(item[key]).strip()
    ]
    if mismatched:
        return False, "live_readback_identity_mismatch"
    return True, None


def validate_worker_readback_payload(
    *,
    payload: Any,
    item: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[str | None, str | None, list[Any] | None]:
    identity_matches, identity_reason = readback_identity_matches_manifest(payload, item)
    if not identity_matches:
        return identity_reason, None, None

    payload_worker_name = payload_scalar_value(payload, "worker_name", "worker")
    if payload_worker_name is None:
        return "live_readback_worker_missing", None, None
    if payload_worker_name != str(item["worker_name"]).strip():
        return "live_readback_worker_mismatch", None, None

    payload_queue = payload_scalar_value(payload, "queue", "queue_name")
    if payload_queue is None:
        return "live_readback_queue_missing", None, None
    if payload_queue != str(item["queue"]).strip():
        return "live_readback_queue_mismatch", None, None

    payload_trace_id = worker_trace_id_from_payload(payload)
    if payload_trace_id is None:
        return "live_readback_trace_missing", None, None
    if payload_trace_id != str(item["trace_id"]).strip():
        return "live_readback_trace_mismatch", None, None

    terminal_status = extract_worker_terminal_status(payload, contract)
    events = extract_worker_events(payload)
    if terminal_status is None or not events:
        return "live_readback_terminal_evidence_missing", None, None
    if not any(event_contains_terminal_status(event, terminal_status) for event in events):
        return "live_readback_terminal_evidence_missing", None, None
    if missing_required_events(events, contract):
        return "live_readback_required_events_missing", None, None

    return None, terminal_status, events


def make_sample(
    *,
    line_key: str,
    endpoint: str,
    terminal_status: str,
    result: HttpResult,
) -> dict[str, Any]:
    payload, _json_error = load_json_payload(result)
    return {
        "line_key": line_key,
        "run_id": f"live-readback-{line_key}",
        "status": terminal_status,
        "events": [
            "readback_probe_started",
            "readback_probe_completed",
            terminal_status,
        ],
        "trace_id": trace_id_from_payload(payload, line_key, endpoint),
        "readback_endpoint": endpoint,
        "http_status": result.status_code,
        "mocked": False,
        "skipped": False,
    }


def make_worker_sample(
    *,
    line_key: str,
    item: dict[str, Any],
    endpoint: str,
    readback_path: str | None,
    terminal_status: str,
    events: list[Any],
    result: HttpResult,
) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "line_key": line_key,
        "status": terminal_status,
        "events": events,
        "worker_name": str(item["worker_name"]).strip(),
        "queue": str(item["queue"]).strip(),
        "trace_id": str(item["trace_id"]).strip(),
        "readback_endpoint": endpoint,
        "http_status": result.status_code,
        "mocked": False,
        "skipped": False,
    }
    if readback_path is not None:
        sample["readback_path"] = readback_path
    for key in ("task_id", "run_id"):
        value = item.get(key)
        if is_present(value):
            sample[key] = str(value).strip()
    return sample


def classify_failed_probe(attempts: list[dict[str, Any]]) -> tuple[str, int | None, str | None]:
    server_error = next((attempt for attempt in attempts if (attempt.get("http_status") or 0) >= 500), None)
    if server_error is not None:
        return "readback_probe_server_error", server_error.get("http_status"), server_error.get("error")
    http_error = next((attempt for attempt in attempts if attempt.get("http_status") is not None), None)
    if http_error is not None:
        return "readback_probe_http_error", http_error.get("http_status"), http_error.get("error")
    return "readback_endpoint_unreachable", None, attempts[-1].get("error") if attempts else None


def probe_worker_line(
    *,
    api_base: str,
    timeout: float,
    line_key: str,
    contract: dict[str, Any],
    manifest_index: ManifestIndex,
    project_key: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    manifest_reason = manifest_anomaly_reason(line_key, manifest_index)
    if manifest_reason is not None:
        return (
            {
                "line_key": line_key,
                "status": STATUS_FAILED,
                "requires_worker_readback": True,
                "reason": manifest_reason,
                "unexpected_line_keys": manifest_index.unexpected_line_keys,
                "duplicate_line_keys": manifest_index.duplicate_line_keys,
                "sample_count": 0,
            },
            None,
        )

    if manifest_index.status == STATUS_FAILED:
        return (
            {
                "line_key": line_key,
                "status": STATUS_FAILED,
                "requires_worker_readback": True,
                "reason": manifest_index.reason,
                "error": manifest_index.error,
                "sample_count": 0,
            },
            None,
        )

    item = manifest_index.items_by_line.get(line_key)
    if item is None:
        return (
            {
                "line_key": line_key,
                "status": STATUS_BLOCKED,
                "requires_worker_readback": True,
                "reason": "task_readback_manifest_missing",
                "readback_paths": contract.get("readback_paths") if isinstance(contract.get("readback_paths"), list) else [],
                "sample_count": 0,
            },
            None,
        )

    if not (is_present(item.get("task_id")) or is_present(item.get("run_id"))):
        return (
            {
                "line_key": line_key,
                "status": STATUS_BLOCKED,
                "requires_worker_readback": True,
                "reason": "task_readback_manifest_missing_identity",
                "sample_count": 0,
            },
            None,
        )
    if not is_present(item.get("worker_name")) or not is_present(item.get("queue")):
        return (
            {
                "line_key": line_key,
                "status": STATUS_FAILED,
                "requires_worker_readback": True,
                "reason": "task_readback_manifest_missing_worker_queue_context",
                "sample_count": 0,
            },
            None,
        )
    if not is_present(item.get("trace_id")):
        return (
            {
                "line_key": line_key,
                "status": STATUS_FAILED,
                "requires_worker_readback": True,
                "reason": "task_readback_manifest_missing_trace_id",
                "sample_count": 0,
            },
            None,
        )

    endpoint, readback_path, endpoint_error = resolve_manifest_readback_endpoint(item, contract)
    if endpoint is None:
        return (
            {
                "line_key": line_key,
                "status": STATUS_BLOCKED,
                "requires_worker_readback": True,
                "reason": endpoint_error or "readback_location_unresolved",
                "readback_paths": contract.get("readback_paths") if isinstance(contract.get("readback_paths"), list) else [],
                "sample_count": 0,
            },
            None,
        )

    endpoint = apply_project_key(endpoint, project_key)
    if readback_path is not None:
        readback_path = apply_project_key(readback_path, project_key)
    result = _http_get(build_probe_url(api_base, endpoint), timeout=timeout)
    attempts = [
        {
            "readback_endpoint": endpoint,
            "http_status": result.status_code,
            "error": result.error,
        }
    ]
    if result.status_code is not None and result.status_code >= 500:
        return (
            {
                "line_key": line_key,
                "status": STATUS_FAILED,
                "requires_worker_readback": True,
                "reason": "readback_probe_server_error",
                "readback_endpoint": endpoint,
                "http_status": result.status_code,
                "error": result.error,
                "attempts": attempts,
                "sample_count": 0,
            },
            None,
        )
    if result.status_code is not None and 200 <= result.status_code < 300:
        payload, json_error = load_json_payload(result)
        if json_error is not None:
            return (
                {
                    "line_key": line_key,
                    "status": STATUS_FAILED,
                    "requires_worker_readback": True,
                    "reason": "live_readback_invalid_json",
                    "readback_endpoint": endpoint,
                    "http_status": result.status_code,
                    "error": json_error,
                    "attempts": attempts,
                    "sample_count": 0,
                },
                None,
            )

        evidence_reason, terminal_status, events = validate_worker_readback_payload(
            payload=payload,
            item=item,
            contract=contract,
        )
        if evidence_reason is not None or terminal_status is None or events is None:
            return (
                {
                    "line_key": line_key,
                    "status": STATUS_FAILED,
                    "requires_worker_readback": True,
                    "reason": evidence_reason or "live_readback_terminal_evidence_missing",
                    "readback_endpoint": endpoint,
                    "http_status": result.status_code,
                    "attempts": attempts,
                    "sample_count": 0,
                },
                None,
            )

        sample = make_worker_sample(
            line_key=line_key,
            item=item,
            endpoint=endpoint,
            readback_path=readback_path,
            terminal_status=terminal_status,
            events=events,
            result=result,
        )
        return (
            {
                "line_key": line_key,
                "status": STATUS_PASSED,
                "reason": "live_readback_sample_generated",
                "requires_worker_readback": True,
                "readback_endpoint": endpoint,
                "http_status": result.status_code,
                "attempts": attempts,
                "sample_count": 1,
            },
            sample,
        )

    reason, http_status, probe_error = classify_failed_probe(attempts)
    status = STATUS_BLOCKED if http_status is None else STATUS_FAILED
    return (
        {
            "line_key": line_key,
            "status": status,
            "reason": reason,
            "requires_worker_readback": True,
            "readback_endpoint": endpoint,
            "http_status": http_status,
            "error": probe_error,
            "attempts": attempts,
            "sample_count": 0,
        },
        None,
    )


def probe_non_worker_line(
    *,
    api_base: str,
    timeout: float,
    line_key: str,
    line: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    terminal_status = NON_WORKER_TERMINAL_STATUS[line_key]
    attempts: list[dict[str, Any]] = []
    for endpoint in candidate_readback_paths(line, line_key, contract):
        result = _http_get(build_url(api_base, endpoint), timeout=timeout)
        attempt = {
            "readback_endpoint": endpoint,
            "http_status": result.status_code,
            "error": result.error,
        }
        attempts.append(attempt)
        if result.status_code is not None and result.status_code >= 500:
            return (
                {
                    "line_key": line_key,
                    "status": STATUS_FAILED,
                    "reason": "readback_probe_server_error",
                    "requires_worker_readback": False,
                    "readback_endpoint": endpoint,
                    "http_status": result.status_code,
                    "error": result.error,
                    "attempts": attempts,
                    "sample_count": 0,
                },
                None,
            )
        if result.status_code is not None and 200 <= result.status_code < 300:
            sample = make_sample(
                line_key=line_key,
                endpoint=endpoint,
                terminal_status=terminal_status,
                result=result,
            )
            return (
                {
                    "line_key": line_key,
                    "status": STATUS_PASSED,
                    "reason": "live_readback_sample_generated",
                    "requires_worker_readback": False,
                    "readback_endpoint": endpoint,
                    "http_status": result.status_code,
                    "attempts": attempts,
                    "sample_count": 1,
                },
                sample,
            )

    reason, http_status, probe_error = classify_failed_probe(attempts)
    status = STATUS_BLOCKED if http_status is None else STATUS_FAILED
    return (
        {
            "line_key": line_key,
            "status": status,
            "reason": reason,
            "requires_worker_readback": False,
            "readback_endpoint": attempts[-1]["readback_endpoint"] if attempts else None,
            "http_status": http_status,
            "error": probe_error,
            "attempts": attempts,
            "sample_count": 0,
        },
        None,
    )


def summarize_status(
    line_results: list[dict[str, Any]],
    matrix_anomalies: dict[str, list[str]],
    manifest_index: ManifestIndex,
) -> str:
    if (
        matrix_has_anomalies(matrix_anomalies)
        or manifest_has_anomalies(manifest_index)
        or any(line["status"] == STATUS_FAILED for line in line_results)
    ):
        return STATUS_FAILED
    if any(line["status"] == STATUS_BLOCKED for line in line_results):
        return STATUS_BLOCKED
    return STATUS_PASSED


def blocked_matrix_report(
    *,
    api_base: str,
    output_path: Path,
    manifest_path: Path | None,
    manifest_index: ManifestIndex,
    matrix_result: HttpResult,
    observed_at: str,
    project_key: str | None,
) -> dict[str, Any]:
    status = STATUS_FAILED if manifest_has_anomalies(manifest_index) else STATUS_BLOCKED
    line_reports = []
    for line_key in EXPECTED_LINE_KEYS:
        manifest_reason = (
            manifest_anomaly_reason(line_key, manifest_index) if line_key in WORKER_REQUIRED_LINE_KEYS else None
        )
        line_reports.append(
            {
                "line_key": line_key,
                "status": STATUS_FAILED if manifest_reason is not None else STATUS_BLOCKED,
                "requires_worker_readback": line_key in WORKER_REQUIRED_LINE_KEYS,
                "reason": manifest_reason or "evidence_matrix_unreachable",
                "sample_count": 0,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "observed_at": observed_at,
        "api_base": normalize_api_base(api_base),
        "project_key": project_key,
        "matrix_path": apply_project_key(MATRIX_PATH, project_key),
        "recommended_command": recommended_command(api_base, output_path, manifest_path, project_key=project_key),
        "expected_line_keys": list(EXPECTED_LINE_KEYS),
        "task_readback_manifest": {
            "path": manifest_index.path,
            "status": manifest_index.status,
            "reason": manifest_index.reason,
            "error": manifest_index.error,
            "worker_required_line_keys": sorted(WORKER_REQUIRED_LINE_KEYS),
            "line_keys": sorted(manifest_index.items_by_line),
            "unexpected_line_keys": manifest_index.unexpected_line_keys,
            "duplicate_line_keys": manifest_index.duplicate_line_keys,
        },
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
            "sample_line_keys": [],
            "passed_line_keys": [],
            "blocked_line_keys": [line["line_key"] for line in line_reports if line["status"] == STATUS_BLOCKED],
            "failed_line_keys": [line["line_key"] for line in line_reports if line["status"] == STATUS_FAILED],
        },
        "samples": [],
        "lines": line_reports,
    }


def build_live_samples(
    *,
    api_base: str,
    output_path: Path,
    timeout: float,
    task_readback_manifest_path: Path | None = None,
    project_key: str | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=manifest_index+evidence_matrix_http_observation_function_inputs "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    observed_at = utc_now()
    normalized_api_base = normalize_api_base(api_base)
    manifest_index = load_manifest_index(task_readback_manifest_path)
    matrix_path = apply_project_key(MATRIX_PATH, project_key)
    matrix_result = _http_get(build_url(normalized_api_base, matrix_path), timeout=timeout)

    if matrix_result.status_code is None:
        return blocked_matrix_report(
            api_base=normalized_api_base,
            output_path=output_path,
            manifest_path=task_readback_manifest_path,
            manifest_index=manifest_index,
            matrix_result=matrix_result,
            observed_at=observed_at,
            project_key=project_key,
        )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_FAILED,
        "observed_at": observed_at,
        "api_base": normalized_api_base,
        "project_key": project_key,
        "matrix_path": matrix_path,
        "recommended_command": recommended_command(
            normalized_api_base,
            output_path,
            task_readback_manifest_path,
            project_key=project_key,
        ),
        "expected_line_keys": list(EXPECTED_LINE_KEYS),
        "task_readback_manifest": {
            "path": manifest_index.path,
            "status": manifest_index.status,
            "reason": manifest_index.reason,
            "error": manifest_index.error,
            "worker_required_line_keys": sorted(WORKER_REQUIRED_LINE_KEYS),
            "line_keys": sorted(manifest_index.items_by_line),
            "unexpected_line_keys": manifest_index.unexpected_line_keys,
            "duplicate_line_keys": manifest_index.duplicate_line_keys,
        },
        "matrix": {
            "status": STATUS_PASSED if 200 <= matrix_result.status_code < 300 else STATUS_FAILED,
            "http_status": matrix_result.status_code,
            "reason": "evidence_matrix_reachable"
            if 200 <= matrix_result.status_code < 300
            else "evidence_matrix_http_error",
        },
        "matrix_anomalies": {
            "missing_line_keys": [],
            "unexpected_line_keys": [],
            "invalid_line_keys": [],
            "duplicate_line_keys": [],
        },
        "summary": {
            "sample_line_keys": [],
            "passed_line_keys": [],
            "blocked_line_keys": [],
            "failed_line_keys": [],
        },
        "samples": [],
        "lines": [],
    }

    if not (200 <= matrix_result.status_code < 300):
        report["matrix"]["error"] = matrix_result.error
        report["summary"]["failed_line_keys"] = list(EXPECTED_LINE_KEYS)
        return report

    payload, json_error = load_json_payload(matrix_result)
    if json_error is not None:
        report["matrix"]["status"] = STATUS_FAILED
        report["matrix"]["reason"] = "evidence_matrix_invalid_json"
        report["matrix"]["error"] = json_error
        report["summary"]["failed_line_keys"] = list(EXPECTED_LINE_KEYS)
        return report

    lines = extract_lines(payload)
    by_key, matrix_anomalies = index_matrix_lines(lines)
    report["matrix"]["contract_version"] = extract_contract_version(payload)
    report["matrix"]["observed_line_count"] = len(lines)
    report["matrix_anomalies"] = matrix_anomalies

    line_results: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for line_key in EXPECTED_LINE_KEYS:
        line = by_key.get(line_key)
        if line is None:
            line_results.append(
                {
                    "line_key": line_key,
                    "status": STATUS_FAILED,
                    "requires_worker_readback": None,
                    "reason": "missing_line_in_evidence_matrix",
                    "sample_count": 0,
                }
            )
            continue

        contract = async_task_readback_contract(line)
        requires_worker_readback = contract.get("requires_worker_readback")
        if not contract:
            line_results.append(
                {
                    "line_key": line_key,
                    "status": STATUS_FAILED,
                    "requires_worker_readback": None,
                    "reason": "missing_async_task_readback_contract",
                    "sample_count": 0,
                }
            )
            continue
        if not isinstance(requires_worker_readback, bool):
            line_results.append(
                {
                    "line_key": line_key,
                    "status": STATUS_FAILED,
                    "requires_worker_readback": None,
                    "reason": "missing_requires_worker_readback",
                    "sample_count": 0,
                }
            )
            continue
        if requires_worker_readback:
            line_result, sample = probe_worker_line(
                api_base=normalized_api_base,
                timeout=timeout,
                line_key=line_key,
                contract=contract,
                manifest_index=manifest_index,
                project_key=project_key,
            )
            line_results.append(line_result)
            if sample is not None:
                samples.append(sample)
            continue
        if line_key not in NON_WORKER_TERMINAL_STATUS:
            line_results.append(
                {
                    "line_key": line_key,
                    "status": STATUS_FAILED,
                    "requires_worker_readback": False,
                    "reason": "missing_non_worker_terminal_status_mapping",
                    "sample_count": 0,
                }
            )
            continue

        line_result, sample = probe_non_worker_line(
            api_base=normalized_api_base,
            timeout=timeout,
            line_key=line_key,
            line=line,
            contract=contract,
        )
        line_results.append(line_result)
        if sample is not None:
            samples.append(sample)

    report["lines"] = line_results
    report["samples"] = samples
    report["summary"] = {
        "sample_line_keys": [sample["line_key"] for sample in samples],
        "passed_line_keys": [line["line_key"] for line in line_results if line["status"] == STATUS_PASSED],
        "blocked_line_keys": [line["line_key"] for line in line_results if line["status"] == STATUS_BLOCKED],
        "failed_line_keys": [line["line_key"] for line in line_results if line["status"] == STATUS_FAILED],
    }
    report["status"] = summarize_status(line_results, matrix_anomalies, manifest_index)
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True, help="Backend base URL, for example http://127.0.0.1:8000.")
    parser.add_argument("--output", required=True, type=Path, help="Path to write the sample JSON file.")
    parser.add_argument("--timeout", default=5.0, type=float, help="HTTP timeout per request in seconds.")
    parser.add_argument(
        "--task-readback-manifest",
        type=Path,
        help="Optional manifest with real worker task/run identities and readback locations.",
    )
    parser.add_argument("--project-key", help="Optional project key for project-scoped matrix and process readback endpoints.")
    parser.add_argument("--allow-blocked", action="store_true", help="Return zero when only environment blockers occur.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON sample artifact to stdout.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_live_samples(
        api_base=args.api_base,
        output_path=args.output,
        timeout=args.timeout,
        task_readback_manifest_path=args.task_readback_manifest,
        project_key=args.project_key,
    )
    write_json(args.output, report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"business_line_async_task_readback_live_samples={report['status']} output={args.output}")

    if report["status"] == STATUS_PASSED:
        return 0
    if report["status"] == STATUS_BLOCKED and args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
