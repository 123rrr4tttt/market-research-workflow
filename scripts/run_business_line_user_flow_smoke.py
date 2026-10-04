#!/usr/bin/env python3
"""Run live user-flow smoke probes for the seven business-line boundaries."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Sequence
from urllib import error, request

try:
    from scripts._automation_runtime import CANONICAL_LINE_KEYS, utc_now, write_json
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import CANONICAL_LINE_KEYS, utc_now, write_json


SCHEMA_VERSION = "business_line_user_flow_smoke.v1"
MATRIX_PATH = "/api/v1/business-lines/evidence-matrix"
FEEDBACK_SUBMIT_PATH = "/api/v1/ingest/url/single"
FEEDBACK_HISTORY_PATH = "/api/v1/ingest/history"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"
STATUS_FEEDBACK_READBACK_MISSING = "feedback_readback_missing"
STATUS_PASSED_CONTRACT_REACHABLE = "passed_contract_reachable"
RESPONSE_ASSERTION_PASSED = "passed"
RESPONSE_ASSERTION_FAILED = "failed"
RESPONSE_ASSERTION_NOT_DECLARED = "not_declared"
RESPONSE_ASSERTION_NOT_RUN = "not_run"

EXPECTED_LINE_KEYS = CANONICAL_LINE_KEYS

FALLBACK_PROBE_PATHS = {
    "ingest": "/api/v1/ingest",
    "search_discovery_index": "/api/v1/search",
    "resource_source_library": "/api/v1/resource_pool",
    "projects_config_workflow": "/api/v1/projects",
    "dashboard_admin_governance": "/api/v1/dashboard",
    "writing_knowledge_graph_agent": "/api/v1/workflow-graph/templates",
    "runtime_ops": "/api/v1/health",
}


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: str
    error: str | None = None


def normalize_api_base(api_base: str) -> str:
    return api_base.rstrip("/")


def build_url(api_base: str, path: str) -> Annotated[
    str,
    "kit:prepared-command effect_boundary=user_flow_smoke_http_read witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalize_api_base(api_base)}{normalized_path}"


def recommended_command(api_base: str, output_path: Path) -> str:
    return (
        "python3 scripts/run_business_line_user_flow_smoke.py "
        f"--base-url {api_base} --output {output_path} --allow-blocked --json"
    )


def _http_get(url: str, *, timeout: float) -> HttpResult:
    req = request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - explicit live smoke URL input
            body = response.read().decode("utf-8", errors="replace")
            return HttpResult(status_code=int(response.status), body=body)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResult(status_code=int(exc.code), body=body, error=str(exc))
    except (error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return HttpResult(status_code=None, body="", error=str(exc))


def _http_post_json(url: str, payload: dict[str, Any], *, timeout: float) -> HttpResult:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - explicit live smoke URL input
            response_body = response.read().decode("utf-8", errors="replace")
            return HttpResult(status_code=int(response.status), body=response_body)
    except error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        return HttpResult(status_code=int(exc.code), body=response_body, error=str(exc))
    except (error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return HttpResult(status_code=None, body="", error=str(exc))


def load_json_payload(result: HttpResult) -> tuple[Any | None, str | None]:
    try:
        return json.loads(result.body), None
    except json.JSONDecodeError as exc:
        return None, f"response is not valid JSON: {exc}"


def payload_roots(payload: Any) -> list[Any]:
    roots = [payload]
    if isinstance(payload, dict) and isinstance(payload.get("data"), (dict, list)):
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


def extract_probe_path(line: dict[str, Any], line_key: str) -> str:
    live_smoke = line.get("live_smoke")
    if isinstance(live_smoke, dict):
        probe_path = live_smoke.get("probe_path")
        if isinstance(probe_path, str) and probe_path.strip():
            stripped = probe_path.strip()
            return stripped if stripped.startswith("/") else f"/{stripped}"
    return FALLBACK_PROBE_PATHS[line_key]


def extract_required_data_paths(line: dict[str, Any]) -> tuple[bool, list[str]]:
    live_smoke = line.get("live_smoke")
    if not isinstance(live_smoke, dict):
        return False, []
    response_assertions = live_smoke.get("response_assertions")
    if not isinstance(response_assertions, dict):
        return False, []
    raw_paths = response_assertions.get("required_data_paths")
    if not isinstance(raw_paths, list):
        return True, []
    paths = [path.strip() for path in raw_paths if isinstance(path, str) and path.strip()]
    return True, paths


def resolve_data_path(payload: Any, data_path: str) -> tuple[bool, Any]:
    current = payload
    path_parts = [part for part in data_path.replace("/", ".").split(".") if part]
    for part in path_parts:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def unwrap_envelope(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def string_at_path(payload: Any, data_path: str) -> str | None:
    exists, value = resolve_data_path(payload, data_path)
    if not exists and isinstance(payload, dict) and "data" in payload:
        exists, value = resolve_data_path(payload["data"], data_path)
    if not exists:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if value is None:
        return None
    return str(value).strip() or None


def first_string_at_paths(payload: Any, data_paths: Sequence[str]) -> str | None:
    for data_path in data_paths:
        value = string_at_path(payload, data_path)
        if value:
            return value
    return None


def extract_history_items(payload: Any) -> list[Any]:
    roots = payload_roots(payload)
    for root in roots:
        if isinstance(root, list):
            return root
        if not isinstance(root, dict):
            continue
        for key in ("items", "jobs", "history", "results", "submissions"):
            value = root.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = extract_history_items(value)
                if nested:
                    return nested
    return []


def value_contains_identifier(value: Any, identifier: str) -> bool:
    needle = str(identifier or "").strip()
    if not needle:
        return False
    if isinstance(value, str):
        return value.strip() == needle
    if isinstance(value, dict):
        return any(value_contains_identifier(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(value_contains_identifier(item, needle) for item in value)
    return str(value).strip() == needle


def find_history_readback_item(history_payload: Any, identifiers: Sequence[str]) -> tuple[dict[str, Any] | None, list[str], int]:
    items = extract_history_items(history_payload)
    normalized_identifiers = [identifier for identifier in identifiers if str(identifier or "").strip()]
    for item in items:
        if not isinstance(item, dict):
            continue
        matched_by = [identifier for identifier in normalized_identifiers if value_contains_identifier(item, identifier)]
        if matched_by:
            return item, matched_by, len(items)
    return None, [], len(items)


def build_feedback_loop_blocked(
    *,
    reason: str,
    submit_path: str,
    history_path: str,
    project_key: str,
    submitted_url: str,
    idempotency_key: str,
    submit_result: HttpResult | None = None,
    history_result: HttpResult | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=preflight "
    "fact_source=block_reason_and_feedback_http_result_function_inputs "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    return {
        "status": STATUS_BLOCKED,
        "reason": reason,
        "submit_path": submit_path,
        "history_path": history_path,
        "project_key": project_key,
        "submitted_url": submitted_url,
        "idempotency_key": idempotency_key,
        "submission_id": None,
        "task_id": None,
        "trace_id": None,
        "http_status": {
            "submit": submit_result.status_code if submit_result else None,
            "history": history_result.status_code if history_result else None,
        },
        "failures": [reason],
        "readback": {
            "matched": False,
            "matched_by": [],
            "history_item_count": 0,
            "required_fields": ["submission_id", "task_id", "status", "trace_id"],
            "missing_fields": ["submission_id", "task_id", "status", "trace_id"],
        },
        "errors": {
            "submit": submit_result.error if submit_result else None,
            "history": history_result.error if history_result else None,
        },
    }


def run_feedback_loop(
    *,
    api_base: str,
    timeout: float,
    project_key: str,
    submitted_url: str,
    idempotency_key: str | None,
) -> dict[str, Any]:
    public_idempotency_key = (idempotency_key or "").strip() or f"user-flow-smoke-{uuid.uuid4().hex}"
    submit_payload = {
        "project_key": project_key,
        "url": submitted_url,
        "query_terms": ["market research workflow smoke"],
        "idempotency_key": public_idempotency_key,
        "async_mode": True,
        "strict_mode": False,
        "search_expand": False,
        "search_expand_limit": 1,
        "min_results_required": 1,
        "target_candidates": 1,
    }
    submit_result = _http_post_json(build_url(api_base, FEEDBACK_SUBMIT_PATH), submit_payload, timeout=timeout)
    if submit_result.status_code is None or submit_result.status_code >= 500:
        return build_feedback_loop_blocked(
            reason="feedback_submit_unavailable",
            submit_path=FEEDBACK_SUBMIT_PATH,
            history_path=FEEDBACK_HISTORY_PATH,
            project_key=project_key,
            submitted_url=submitted_url,
            idempotency_key=public_idempotency_key,
            submit_result=submit_result,
        )
    if not (200 <= submit_result.status_code < 300):
        return {
            **build_feedback_loop_blocked(
                reason="feedback_submit_rejected",
                submit_path=FEEDBACK_SUBMIT_PATH,
                history_path=FEEDBACK_HISTORY_PATH,
                project_key=project_key,
                submitted_url=submitted_url,
                idempotency_key=public_idempotency_key,
                submit_result=submit_result,
            ),
            "status": STATUS_FAILED,
        }

    submit_payload_json, submit_json_error = load_json_payload(submit_result)
    if submit_json_error is not None:
        return {
            **build_feedback_loop_blocked(
                reason="feedback_submit_invalid_json",
                submit_path=FEEDBACK_SUBMIT_PATH,
                history_path=FEEDBACK_HISTORY_PATH,
                project_key=project_key,
                submitted_url=submitted_url,
                idempotency_key=public_idempotency_key,
                submit_result=submit_result,
            ),
            "status": STATUS_FAILED,
        }

    submit_data = unwrap_envelope(submit_payload_json)
    submission_id = first_string_at_paths(
        submit_data,
        ("submission_id", "trace_chain.ids.submission_id", "trace_chain.submission_id"),
    )
    task_id = first_string_at_paths(submit_data, ("task_id", "process_id", "trace_chain.ids.task_id", "trace_chain.task_id"))
    trace_id = first_string_at_paths(submit_data, ("trace_id", "trace_chain.trace_id", "trace_chain.ids.trace_id"))
    submit_status = first_string_at_paths(submit_data, ("status", "submission_status", "task_result_status"))

    history_result = _http_get(build_url(api_base, f"{FEEDBACK_HISTORY_PATH}?limit=50"), timeout=timeout)
    if history_result.status_code is None or history_result.status_code >= 500:
        return build_feedback_loop_blocked(
            reason="feedback_history_unavailable",
            submit_path=FEEDBACK_SUBMIT_PATH,
            history_path=FEEDBACK_HISTORY_PATH,
            project_key=project_key,
            submitted_url=submitted_url,
            idempotency_key=public_idempotency_key,
            submit_result=submit_result,
            history_result=history_result,
        )
    if not (200 <= history_result.status_code < 300):
        return {
            **build_feedback_loop_blocked(
                reason="feedback_history_rejected",
                submit_path=FEEDBACK_SUBMIT_PATH,
                history_path=FEEDBACK_HISTORY_PATH,
                project_key=project_key,
                submitted_url=submitted_url,
                idempotency_key=public_idempotency_key,
                submit_result=submit_result,
                history_result=history_result,
            ),
            "status": STATUS_FAILED,
            "submission_id": submission_id,
            "task_id": task_id,
            "trace_id": trace_id,
        }

    history_payload, history_json_error = load_json_payload(history_result)
    if history_json_error is not None:
        return {
            **build_feedback_loop_blocked(
                reason="feedback_history_invalid_json",
                submit_path=FEEDBACK_SUBMIT_PATH,
                history_path=FEEDBACK_HISTORY_PATH,
                project_key=project_key,
                submitted_url=submitted_url,
                idempotency_key=public_idempotency_key,
                submit_result=submit_result,
                history_result=history_result,
            ),
            "status": STATUS_FAILED,
            "submission_id": submission_id,
            "task_id": task_id,
            "trace_id": trace_id,
        }

    matched_item, matched_by, history_item_count = find_history_readback_item(
        history_payload,
        [submission_id or "", task_id or "", trace_id or "", public_idempotency_key],
    )
    readback_submission_id = first_string_at_paths(
        matched_item or {},
        ("submission_id", "trace_chain.ids.submission_id", "trace_chain.submission_id"),
    )
    readback_task_id = first_string_at_paths(
        matched_item or {},
        ("task_id", "process_id", "trace_chain.ids.task_id", "trace_chain.task_id"),
    )
    readback_trace_id = first_string_at_paths(
        matched_item or {},
        ("trace_id", "trace_chain.trace_id", "trace_chain.ids.trace_id"),
    )
    readback_status = first_string_at_paths(matched_item or {}, ("status", "submission_status", "task_result_status"))

    missing_response_fields = [
        field
        for field, value in (
            ("submission_id", submission_id),
            ("task_id", task_id),
            ("status", submit_status),
            ("trace_id", trace_id),
        )
        if not value
    ]
    missing_readback_fields = [
        field
        for field, value in (
            ("submission_id", readback_submission_id),
            ("task_id", readback_task_id),
            ("status", readback_status),
            ("trace_id", readback_trace_id),
        )
        if not value
    ]
    mismatched_readback_fields = [
        field
        for field, submitted, observed in (
            ("submission_id", submission_id, readback_submission_id),
            ("task_id", task_id, readback_task_id),
            ("trace_id", trace_id, readback_trace_id),
        )
        if submitted and observed and submitted != observed
    ]
    failures: list[str] = []
    if missing_response_fields:
        failures.append("feedback_submit_missing_fields")
    if matched_item is None:
        failures.append("feedback_history_missing_submission")
    if missing_readback_fields:
        failures.append("feedback_history_missing_fields")
    if mismatched_readback_fields:
        failures.append("feedback_history_mismatched_fields")

    status = STATUS_PASSED if not failures else STATUS_FEEDBACK_READBACK_MISSING
    return {
        "status": status,
        "reason": "feedback_readback_confirmed" if status == STATUS_PASSED else STATUS_FEEDBACK_READBACK_MISSING,
        "submit_path": FEEDBACK_SUBMIT_PATH,
        "history_path": FEEDBACK_HISTORY_PATH,
        "project_key": project_key,
        "submitted_url": submitted_url,
        "idempotency_key": public_idempotency_key,
        "submission_id": submission_id,
        "task_id": task_id,
        "trace_id": trace_id,
        "submit_status": submit_status,
        "http_status": {"submit": submit_result.status_code, "history": history_result.status_code},
        "failures": failures,
        "readback": {
            "matched": matched_item is not None,
            "matched_by": matched_by,
            "history_item_count": history_item_count,
            "required_fields": ["submission_id", "task_id", "status", "trace_id"],
            "missing_fields": missing_readback_fields,
            "mismatched_fields": mismatched_readback_fields,
            "submission_id": readback_submission_id,
            "task_id": readback_task_id,
            "trace_id": readback_trace_id,
            "status": readback_status,
        },
    }


def evaluate_response_assertions(
    result: HttpResult,
    *,
    assertions_declared: bool,
    required_data_paths: list[str],
) -> dict[str, Any]:
    semantic_fields_checked = list(required_data_paths)
    base = {
        "response_assertion_status": RESPONSE_ASSERTION_NOT_DECLARED
        if not assertions_declared
        else RESPONSE_ASSERTION_NOT_RUN,
        "missing_data_paths": [],
        "semantic_fields_checked": semantic_fields_checked,
    }

    if result.status_code is None or not (200 <= result.status_code < 500):
        return base

    payload, json_error = load_json_payload(result)
    if not assertions_declared:
        return base
    if json_error is not None:
        base["response_assertion_status"] = RESPONSE_ASSERTION_FAILED
        base["missing_data_paths"] = semantic_fields_checked
        return base

    missing_data_paths: list[str] = []
    for data_path in required_data_paths:
        exists, _value = resolve_data_path(payload, data_path)
        if not exists:
            missing_data_paths.append(data_path)

    base["missing_data_paths"] = missing_data_paths
    base["response_assertion_status"] = (
        RESPONSE_ASSERTION_FAILED if missing_data_paths else RESPONSE_ASSERTION_PASSED
    )
    return base


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

    missing_line_keys = sorted(set(EXPECTED_LINE_KEYS) - set(by_key))
    duplicate_line_keys = sorted(line_key for line_key, count in seen.items() if count > 1)
    anomalies = {
        "missing_line_keys": missing_line_keys,
        "unexpected_line_keys": sorted(key for key in invalid_line_keys if key != "<missing>"),
        "invalid_line_keys": sorted(key for key in invalid_line_keys if key == "<missing>"),
        "duplicate_line_keys": duplicate_line_keys,
    }
    return by_key, anomalies


def classify_probe_result(result: HttpResult) -> tuple[str, str, str]:
    if result.status_code is None:
        return STATUS_BLOCKED, "connection_refused_or_timeout", "environment_blocked_no_backend"
    if 200 <= result.status_code < 500:
        return STATUS_PASSED_CONTRACT_REACHABLE, f"http_{result.status_code}_contract_reachable", "live_backend_http_status"
    return STATUS_FAILED, f"http_{result.status_code}_server_error", "live_backend_http_status"


def summarize_status(
    line_results: list[dict[str, Any]],
    matrix_anomalies: dict[str, list[str]],
    feedback_loop: dict[str, Any] | None = None,
) -> str:
    has_matrix_anomaly = any(matrix_anomalies.values())
    if has_matrix_anomaly or any(line["status"] == STATUS_FAILED for line in line_results):
        return STATUS_FAILED
    if feedback_loop and feedback_loop.get("status") == STATUS_FAILED:
        return STATUS_FAILED
    if feedback_loop and feedback_loop.get("status") == STATUS_FEEDBACK_READBACK_MISSING:
        return STATUS_FEEDBACK_READBACK_MISSING
    if any(line["status"] == STATUS_BLOCKED for line in line_results):
        return STATUS_BLOCKED
    if feedback_loop and feedback_loop.get("status") == STATUS_BLOCKED:
        return STATUS_BLOCKED
    return STATUS_PASSED


def build_summary(
    *,
    status: str,
    api_base: str,
    matrix_path: str,
    line_results: list[dict[str, Any]],
    matrix_reason: str | None = None,
    feedback_loop: dict[str, Any] | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view "
    "fact_source=line_results_and_feedback_loop_function_inputs "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    blocked_lines = [line for line in line_results if line.get("status") == STATUS_BLOCKED]
    failed_lines = [line for line in line_results if line.get("status") == STATUS_FAILED]
    passed_contract_lines = [
        line for line in line_results if line.get("status") == STATUS_PASSED_CONTRACT_REACHABLE
    ]
    response_assertion_failures = [
        line
        for line in line_results
        if line.get("response_assertion_status") == RESPONSE_ASSERTION_FAILED
    ]
    first_blocked = blocked_lines[0] if blocked_lines else None
    first_failed = failed_lines[0] if failed_lines else None
    blocker_classification = None
    if status == STATUS_BLOCKED:
        blocker_classification = (
            "evidence_matrix_unreachable"
            if matrix_reason == "evidence_matrix_unreachable"
            else "line_probe_blocked"
        )
    elif status == STATUS_FEEDBACK_READBACK_MISSING:
        blocker_classification = STATUS_FEEDBACK_READBACK_MISSING
    elif status == STATUS_FAILED:
        blocker_classification = "contract_or_semantic_failure"

    checked_endpoints = [build_url(api_base, matrix_path)]
    checked_endpoints.extend(
        build_url(api_base, str(line["probe_path"]))
        for line in line_results
        if isinstance(line.get("probe_path"), str) and line.get("status") != STATUS_BLOCKED
    )
    if feedback_loop:
        checked_endpoints.append(build_url(api_base, str(feedback_loop.get("submit_path") or FEEDBACK_SUBMIT_PATH)))
        checked_endpoints.append(build_url(api_base, f"{feedback_loop.get('history_path') or FEEDBACK_HISTORY_PATH}?limit=50"))

    return {
        "line_count": len(line_results),
        "blocked_count": len(blocked_lines),
        "failed_count": len(failed_lines),
        "passed_contract_reachable_count": len(passed_contract_lines),
        "response_assertion_failed_count": len(response_assertion_failures),
        "feedback_loop_status": feedback_loop.get("status") if feedback_loop else None,
        "feedback_loop_failures": list(feedback_loop.get("failures") or []) if feedback_loop else [],
        "submission_id": feedback_loop.get("submission_id") if feedback_loop else None,
        "task_id": feedback_loop.get("task_id") if feedback_loop else None,
        "trace_id": feedback_loop.get("trace_id") if feedback_loop else None,
        "blocker_classification": blocker_classification,
        "first_blocked_line": first_blocked.get("line_key") if first_blocked else None,
        "first_failed_line": first_failed.get("line_key") if first_failed else None,
        "first_blocker_reason": (
            str(first_blocked.get("reason"))
            if first_blocked
            else str(first_failed.get("reason")) if first_failed else matrix_reason
        ),
        "checked_endpoints": checked_endpoints,
    }


def build_matrix_blocked_report(
    *,
    api_base: str,
    output_path: Path,
    matrix_result: HttpResult,
    started_at: str,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=preflight "
    "fact_source=matrix_http_result_and_start_time_function_inputs "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    line_results = [
        {
            "line_key": line_key,
            "probe_path": FALLBACK_PROBE_PATHS[line_key],
            "status": STATUS_BLOCKED,
            "http_status": None,
            "reason": "evidence_matrix_unreachable",
            "proof_level": "environment_blocked_no_backend",
            "response_assertion_status": RESPONSE_ASSERTION_NOT_RUN,
            "missing_data_paths": [],
            "semantic_fields_checked": [],
        }
        for line_key in EXPECTED_LINE_KEYS
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BLOCKED,
        "started_at": started_at,
        "api_base": normalize_api_base(api_base),
        "matrix_path": MATRIX_PATH,
        "recommended_command": recommended_command(api_base, output_path),
        "summary": build_summary(
            status=STATUS_BLOCKED,
            api_base=normalize_api_base(api_base),
            matrix_path=MATRIX_PATH,
            line_results=line_results,
            matrix_reason="evidence_matrix_unreachable",
        ),
        "expected_line_keys": list(EXPECTED_LINE_KEYS),
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
        "feedback_loop": build_feedback_loop_blocked(
            reason="feedback_loop_not_run_evidence_matrix_unreachable",
            submit_path=FEEDBACK_SUBMIT_PATH,
            history_path=FEEDBACK_HISTORY_PATH,
            project_key="",
            submitted_url="",
            idempotency_key="",
            submit_result=matrix_result,
        ),
        "lines": line_results,
    }


def run_smoke(
    *,
    api_base: str,
    output_path: Path,
    timeout: float,
    feedback_project_key: str = "demo_proj",
    feedback_url: str = "https://example.com/market-research-workflow-user-flow-smoke",
    feedback_idempotency_key: str | None = None,
) -> dict[str, Any]:
    started_at = utc_now()
    normalized_api_base = normalize_api_base(api_base)
    matrix_result = _http_get(build_url(normalized_api_base, MATRIX_PATH), timeout=timeout)

    if matrix_result.status_code is None:
        return build_matrix_blocked_report(
            api_base=normalized_api_base,
            output_path=output_path,
            matrix_result=matrix_result,
            started_at=started_at,
        )

    base_report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_FAILED,
        "started_at": started_at,
        "api_base": normalized_api_base,
        "matrix_path": MATRIX_PATH,
        "recommended_command": recommended_command(normalized_api_base, output_path),
        "expected_line_keys": list(EXPECTED_LINE_KEYS),
        "matrix": {
            "status": STATUS_PASSED if 200 <= matrix_result.status_code < 300 else STATUS_FAILED,
            "http_status": matrix_result.status_code,
            "reason": "evidence_matrix_reachable" if 200 <= matrix_result.status_code < 300 else "evidence_matrix_http_error",
        },
        "matrix_anomalies": {
            "missing_line_keys": [],
            "unexpected_line_keys": [],
            "invalid_line_keys": [],
            "duplicate_line_keys": [],
        },
        "lines": [],
        "feedback_loop": None,
    }

    if not (200 <= matrix_result.status_code < 300):
        base_report["status"] = STATUS_FAILED
        base_report["matrix"]["error"] = matrix_result.error
        base_report["summary"] = build_summary(
            status=STATUS_FAILED,
            api_base=normalized_api_base,
            matrix_path=MATRIX_PATH,
            line_results=[],
            matrix_reason="evidence_matrix_http_error",
        )
        return base_report

    payload, json_error = load_json_payload(matrix_result)
    if json_error is not None:
        base_report["matrix"]["status"] = STATUS_FAILED
        base_report["matrix"]["reason"] = "evidence_matrix_invalid_json"
        base_report["matrix"]["error"] = json_error
        base_report["summary"] = build_summary(
            status=STATUS_FAILED,
            api_base=normalized_api_base,
            matrix_path=MATRIX_PATH,
            line_results=[],
            matrix_reason="evidence_matrix_invalid_json",
        )
        return base_report

    lines = extract_lines(payload)
    by_key, matrix_anomalies = index_matrix_lines(lines)
    base_report["matrix"]["contract_version"] = extract_contract_version(payload)
    base_report["matrix"]["observed_line_count"] = len(lines)
    base_report["matrix_anomalies"] = matrix_anomalies

    line_results: list[dict[str, Any]] = []
    for line_key in EXPECTED_LINE_KEYS:
        matrix_line = by_key.get(line_key)
        if matrix_line is None:
            line_results.append(
                {
                    "line_key": line_key,
                    "probe_path": FALLBACK_PROBE_PATHS[line_key],
                    "status": STATUS_FAILED,
                    "http_status": None,
                    "reason": "missing_line_in_evidence_matrix",
                    "proof_level": "matrix_contract",
                    "response_assertion_status": RESPONSE_ASSERTION_NOT_RUN,
                    "missing_data_paths": [],
                    "semantic_fields_checked": [],
                }
            )
            continue

        probe_path = extract_probe_path(matrix_line, line_key)
        assertions_declared, required_data_paths = extract_required_data_paths(matrix_line)
        probe_result = _http_get(build_url(normalized_api_base, probe_path), timeout=timeout)
        status, reason, proof_level = classify_probe_result(probe_result)
        response_assertions = evaluate_response_assertions(
            probe_result,
            assertions_declared=assertions_declared,
            required_data_paths=required_data_paths,
        )
        if response_assertions["response_assertion_status"] == RESPONSE_ASSERTION_FAILED:
            status = STATUS_FAILED
            reason = "semantic_assertion_failed"
            proof_level = "live_backend_response_semantics"
        line_results.append(
            {
                "line_key": line_key,
                "probe_path": probe_path,
                "status": status,
                "http_status": probe_result.status_code,
                "reason": reason,
                "proof_level": proof_level,
                **response_assertions,
            }
        )

    base_report["lines"] = line_results
    feedback_loop = run_feedback_loop(
        api_base=normalized_api_base,
        timeout=timeout,
        project_key=feedback_project_key,
        submitted_url=feedback_url,
        idempotency_key=feedback_idempotency_key,
    )
    base_report["feedback_loop"] = feedback_loop
    base_report["status"] = summarize_status(line_results, matrix_anomalies, feedback_loop)
    base_report["summary"] = build_summary(
        status=str(base_report["status"]),
        api_base=normalized_api_base,
        matrix_path=MATRIX_PATH,
        line_results=line_results,
        matrix_reason=str(base_report["matrix"]["reason"]),
        feedback_loop=feedback_loop,
    )
    return base_report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base",
        "--base-url",
        dest="api_base",
        required=True,
        help="Backend base URL, for example http://127.0.0.1:8000.",
    )
    parser.add_argument("--output", required=True, type=Path, help="Path to write the JSON smoke artifact.")
    parser.add_argument("--timeout", default=5.0, type=float, help="HTTP timeout per request in seconds.")
    parser.add_argument("--feedback-project-key", default="demo_proj", help="Project key for the ingest feedback-loop probe.")
    parser.add_argument(
        "--feedback-url",
        default="https://example.com/market-research-workflow-user-flow-smoke",
        help="Safe URL submitted by the ingest feedback-loop probe.",
    )
    parser.add_argument(
        "--feedback-idempotency-key",
        default=None,
        help="Optional explicit idempotency key for repeatable feedback-loop probes.",
    )
    parser.add_argument("--allow-blocked", action="store_true", help="Return zero when only environment blockers occur.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON artifact to stdout.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_smoke(
        api_base=args.api_base,
        output_path=args.output,
        timeout=args.timeout,
        feedback_project_key=args.feedback_project_key,
        feedback_url=args.feedback_url,
        feedback_idempotency_key=args.feedback_idempotency_key,
    )
    write_json(args.output, report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"business_line_user_flow_smoke={report['status']} output={args.output}")

    if report["status"] == STATUS_PASSED:
        return 0
    if report["status"] == STATUS_BLOCKED and args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
