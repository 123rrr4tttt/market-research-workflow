#!/usr/bin/env python3
"""Run a live source-library resource lifecycle smoke flow."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Sequence
from urllib import error, parse, request

try:
    from scripts._automation_runtime import utc_now
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import utc_now


SCHEMA_VERSION = "resource_source_lifecycle_smoke.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

SITE_ENTRIES_PATH = "/api/v1/resource_pool/site_entries"
SITE_ENTRY_LIFECYCLE_PATH = "/api/v1/resource_pool/site_entries/lifecycle"
SOURCE_LIBRARY_RUN_PATH = "/api/v1/ingest/source-library/run"


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: str
    error: str | None = None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", dest="base_url", help="Backend API base URL.")
    parser.add_argument("--api-base", dest="api_base", help="Backend API base URL alias.")
    parser.add_argument("--project-key", default="demo_proj", help="Project key for project-scoped site entry.")
    parser.add_argument("--output", required=True, help="Path to write the smoke JSON artifact.")
    parser.add_argument("--json", action="store_true", help="Print the artifact JSON.")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 only when the artifact is blocked by environment.",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout in seconds.")
    return parser.parse_args(argv)


def normalize_api_base(value: str) -> str:
    return value.rstrip("/")


def build_url(
    api_base: str,
    path: str,
    query: dict[str, Any] | None = None,
) -> Annotated[
    str,
    "kit:prepared-command "
    "effect_boundary=resource_source_lifecycle_http_request "
    "witness=test:test_w12_runtime_misc_laws",
]:
    normalized_path = path if path.startswith("/") else f"/{path}"
    url = f"{normalize_api_base(api_base)}{normalized_path}"
    if query:
        clean_query = {key: value for key, value in query.items() if value is not None}
        if clean_query:
            url = f"{url}?{parse.urlencode(clean_query, doseq=True)}"
    return url


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None, *, timeout: float) -> HttpResult:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - explicit smoke URL input
            body = response.read().decode("utf-8", errors="replace")
            return HttpResult(status_code=int(response.status), body=body)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return HttpResult(status_code=int(exc.code), body=body, error=str(exc))
    except (error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return HttpResult(status_code=None, body="", error=str(exc))


def _http_get(url: str, *, timeout: float) -> HttpResult:
    return _http_json("GET", url, timeout=timeout)


def _http_post_json(url: str, payload: dict[str, Any], *, timeout: float) -> HttpResult:
    return _http_json("POST", url, payload, timeout=timeout)


def _http_patch_json(url: str, payload: dict[str, Any], *, timeout: float) -> HttpResult:
    return _http_json("PATCH", url, payload, timeout=timeout)


def load_json_payload(result: HttpResult) -> tuple[Any | None, str | None]:
    try:
        return json.loads(result.body), None
    except json.JSONDecodeError as exc:
        return None, f"response is not valid JSON: {exc}"


def unwrap_envelope(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("data"), (dict, list)):
        return payload["data"]
    return payload


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def string_at_path(payload: Any, data_path: str) -> str | None:
    current = payload
    for part in [part for part in data_path.replace("/", ".").split(".") if part]:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    if current is None:
        return None
    if isinstance(current, str):
        return current.strip() or None
    return str(current).strip() or None


def first_string_at_paths(payload: Any, data_paths: Sequence[str]) -> str | None:
    for data_path in data_paths:
        value = string_at_path(payload, data_path)
        if value:
            return value
    return None


def extract_items(payload: Any) -> list[dict[str, Any]]:
    roots = [payload]
    if isinstance(payload, dict) and isinstance(payload.get("data"), (dict, list)):
        roots.append(payload["data"])
    for root in roots:
        if isinstance(root, list):
            return [item for item in root if isinstance(item, dict)]
        if not isinstance(root, dict):
            continue
        for key in ("items", "site_entries", "results", "rows"):
            value = root.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = extract_items(value)
                if nested:
                    return nested
    return []


def find_site_entry(payload: Any, site_url: str) -> dict[str, Any] | None:
    for item in extract_items(payload):
        if str(item.get("site_url") or "").strip() == site_url:
            return item
    return None


def first_collect_action(data: dict[str, Any]) -> dict[str, Any] | None:
    actions = data.get("next_actions")
    if not isinstance(actions, list):
        return None
    for action in actions:
        if isinstance(action, dict) and action.get("action") == "collect_source_library_run":
            return action
    return None


def extract_guard(data: dict[str, Any], action: dict[str, Any] | None) -> dict[str, Any] | None:
    candidates: list[Any] = []
    if action:
        candidates.append(action.get("single_source_guard"))
        payload = action.get("payload")
        if isinstance(payload, dict):
            override_params = payload.get("override_params")
            if isinstance(override_params, dict):
                candidates.append(override_params.get("single_source_guard"))
    review_closure = data.get("review_closure")
    if isinstance(review_closure, dict):
        candidates.append(review_closure.get("single_source_guard"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return None


def response_data_or_step_failure(
    *,
    step: dict[str, Any],
    result: HttpResult,
    failures: list[str],
) -> dict[str, Any] | None:
    step["http_status"] = result.status_code
    step["error"] = result.error
    if result.status_code is None:
        step["status"] = STATUS_BLOCKED
        step["reason"] = "backend_unreachable"
        failures.append(f"{step['name']}:backend_unreachable")
        return None
    if not (200 <= result.status_code < 300):
        step["status"] = STATUS_FAILED
        step["reason"] = "http_error"
        step["response_body_preview"] = result.body[:500]
        failures.append(f"{step['name']}:http_{result.status_code}")
        return None
    payload, json_error = load_json_payload(result)
    if json_error is not None:
        step["status"] = STATUS_FAILED
        step["reason"] = "invalid_json"
        step["response_body_preview"] = result.body[:500]
        failures.append(f"{step['name']}:invalid_json")
        return None
    step["response"] = payload
    data = unwrap_envelope(payload)
    if not isinstance(data, dict):
        step["status"] = STATUS_FAILED
        step["reason"] = "missing_data_object"
        failures.append(f"{step['name']}:missing_data_object")
        return None
    return data


def validate_accepted_response(data: dict[str, Any], site_url: str) -> tuple[dict[str, Any], list[str], dict[str, Any] | None]:
    failures: list[str] = []
    action = first_collect_action(data)
    guard = extract_guard(data, action)
    review_closure = data.get("review_closure") if isinstance(data.get("review_closure"), dict) else {}
    evidence_binding = data.get("evidence_binding") if isinstance(data.get("evidence_binding"), dict) else {}
    action_payload = action.get("payload") if isinstance(action, dict) and isinstance(action.get("payload"), dict) else None
    override_params = action_payload.get("override_params") if isinstance(action_payload, dict) else None
    if not isinstance(override_params, dict):
        override_params = {}

    if data.get("lifecycle_state") != "accepted":
        failures.append("accepted.lifecycle_state")
    if review_closure.get("status") != "ready_to_collect":
        failures.append("accepted.review_closure.status")
    if review_closure.get("executable") is not True:
        failures.append("accepted.review_closure.executable")
    if action is None:
        failures.append("accepted.next_action")
    elif action.get("enabled") is not True or action.get("blocked") is True:
        failures.append("accepted.next_action.enabled")
    if action_payload is None:
        failures.append("accepted.next_action.payload")
    if override_params.get("site_entries") != [site_url]:
        failures.append("accepted.next_action.payload.override_params.site_entries")
    if guard is None:
        failures.append("accepted.single_source_guard")
    else:
        if guard.get("status") != "passed":
            failures.append("accepted.single_source_guard.status")
        if guard.get("strict_source") is not True:
            failures.append("accepted.single_source_guard.strict_source")
        if guard.get("guarantee") is not True:
            failures.append("accepted.single_source_guard.guarantee")
        if guard.get("allowed_urls") != [site_url]:
            failures.append("accepted.single_source_guard.allowed_urls")
        if not is_present(guard.get("report_source_ref")):
            failures.append("accepted.single_source_guard.report_source_ref")
    if not is_present(review_closure.get("report_source_ref")) and not is_present(evidence_binding.get("report_source_ref")):
        failures.append("accepted.report_source_ref")

    evidence = {
        "lifecycle_state": data.get("lifecycle_state"),
        "review_closure_status": review_closure.get("status"),
        "review_closure_executable": review_closure.get("executable"),
        "next_action": action.get("action") if action else None,
        "next_action_enabled": action.get("enabled") if action else None,
        "report_source_ref": (
            review_closure.get("report_source_ref")
            or evidence_binding.get("report_source_ref")
            or (guard or {}).get("report_source_ref")
        ),
        "single_source_guard": guard,
        "next_action_payload": action_payload,
    }
    return evidence, failures, action_payload


def validate_blocked_review_response(data: dict[str, Any], site_url: str) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    action = first_collect_action(data)
    guard = extract_guard(data, action)
    review_closure = data.get("review_closure") if isinstance(data.get("review_closure"), dict) else {}
    action_payload = action.get("payload") if isinstance(action, dict) and isinstance(action.get("payload"), dict) else {}
    override_params = action_payload.get("override_params") if isinstance(action_payload, dict) else {}
    if not isinstance(override_params, dict):
        override_params = {}

    if data.get("lifecycle_state") not in {"rejected", "needs_review"}:
        failures.append("blocked.lifecycle_state")
    if review_closure.get("status") != "blocked":
        failures.append("blocked.review_closure.status")
    if action is None:
        failures.append("blocked.next_action")
    elif action.get("enabled") is not False or action.get("blocked") is not True:
        failures.append("blocked.next_action.blocked")
    if override_params.get("site_entries") != [site_url]:
        failures.append("blocked.next_action.payload.override_params.site_entries")
    if guard is None:
        failures.append("blocked.single_source_guard")
    else:
        if guard.get("status") != "blocked":
            failures.append("blocked.single_source_guard.status")
        if guard.get("strict_source") is not True:
            failures.append("blocked.single_source_guard.strict_source")
        if guard.get("guarantee") is not False:
            failures.append("blocked.single_source_guard.guarantee")
        if guard.get("allowed_urls") != [site_url]:
            failures.append("blocked.single_source_guard.allowed_urls")

    return {
        "lifecycle_state": data.get("lifecycle_state"),
        "review_closure_status": review_closure.get("status"),
        "next_action": action.get("action") if action else None,
        "next_action_enabled": action.get("enabled") if action else None,
        "next_action_blocked": action.get("blocked") if action else None,
        "block_reason": action.get("block_reason") if action else None,
        "single_source_guard": guard,
    }, failures


def extract_run_evidence(data: dict[str, Any]) -> dict[str, Any]:
    task_id = first_string_at_paths(data, ("task_id", "id", "task.id"))
    terminal_status = first_string_at_paths(
        data,
        (
            "terminal_output.status",
            "status",
            "result.status",
            "authority_output.status",
            "compat_projection.status",
        ),
    )
    trace_id = first_string_at_paths(data, ("trace_id", "trace_chain.trace_id", "trace_chain.ids.trace_id"))
    submission_id = first_string_at_paths(data, ("submission_id", "trace_chain.ids.submission_id"))
    return {
        "task_id": task_id,
        "terminal_status": terminal_status,
        "trace_id": trace_id,
        "submission_id": submission_id,
        "has_task_or_terminal_or_trace": bool(task_id or terminal_status or trace_id),
    }


def build_summary(
    artifact: dict[str, Any],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=view "
    "fact_source=completed_resource_source_lifecycle_artifact "
    "witness=test:test_w12_runtime_misc_laws",
]:
    steps = artifact["steps"]
    return {
        "step_count": len(steps),
        "passed_step_count": sum(1 for step in steps if step.get("status") == STATUS_PASSED),
        "failed_step_count": sum(1 for step in steps if step.get("status") == STATUS_FAILED),
        "blocked_step_count": sum(1 for step in steps if step.get("status") == STATUS_BLOCKED),
        "site_entry_url": artifact["site_entry_url"],
        "accepted_guard_status": artifact["evidence"].get("accepted_guard_status"),
        "blocked_review_status": artifact["evidence"].get("blocked_review_status"),
        "run_task_id": artifact["evidence"].get("run_task_id"),
        "run_terminal_status": artifact["evidence"].get("run_terminal_status"),
        "run_trace_id": artifact["evidence"].get("run_trace_id"),
        "failure_count": len(artifact["failures"]),
    }


def recommended_command(api_base: str, output: Path, project_key: str) -> str:
    return (
        "python3 scripts/run_resource_source_lifecycle_smoke.py "
        f"--api-base {api_base} --project-key {project_key} --output {output} --allow-blocked --json"
    )


def build_artifact(
    *, api_base: str, project_key: str, output: Path, timeout: float
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=generated_evidence "
    "fact_source=owned_resource_source_lifecycle_http_step_results "
    "witness=test:test_w12_runtime_misc_laws",
]:
    smoke_id = f"resource-source-lifecycle-{uuid.uuid4().hex[:12]}"
    site_url = f"https://example.com/{smoke_id}.xml"
    generated_at = utc_now()
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_FAILED,
        "generated_at": generated_at,
        "api_base": normalize_api_base(api_base),
        "project_key": project_key,
        "site_entry_url": site_url,
        "smoke_id": smoke_id,
        "steps": [],
        "failures": [],
        "summary": {},
        "evidence": {},
        "recommended_command": recommended_command(api_base, output, project_key),
    }
    failures: list[str] = artifact["failures"]

    create_payload = {
        "project_key": project_key,
        "scope": "project",
        "site_url": site_url,
        "entry_type": "rss",
        "name": f"Codex lifecycle smoke {smoke_id}",
        "source": "codex_live_smoke",
        "tags": ["codex-live-smoke", "resource-source-lifecycle"],
        "enabled": True,
        "extra": {
            "lifecycle_state": "candidate",
            "review_state": "candidate",
            "smoke_id": smoke_id,
            "created_by": "run_resource_source_lifecycle_smoke.py",
        },
    }
    create_step = {"name": "create_site_entry", "path": SITE_ENTRIES_PATH, "request_payload": create_payload}
    artifact["steps"].append(create_step)
    create_result = _http_post_json(build_url(api_base, SITE_ENTRIES_PATH), create_payload, timeout=timeout)
    create_data = response_data_or_step_failure(step=create_step, result=create_result, failures=failures)
    if create_data is None:
        artifact["status"] = STATUS_BLOCKED if create_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    create_step["status"] = STATUS_PASSED
    create_step["site_url"] = create_data.get("site_url")
    create_step["lifecycle_state"] = create_data.get("lifecycle_state")

    readback_step = {
        "name": "readback_site_entry",
        "path": SITE_ENTRIES_PATH,
        "query": {"project_key": project_key, "scope": "project", "page_size": 100},
    }
    artifact["steps"].append(readback_step)
    readback_result = _http_get(build_url(api_base, SITE_ENTRIES_PATH, readback_step["query"]), timeout=timeout)
    readback_data = response_data_or_step_failure(step=readback_step, result=readback_result, failures=failures)
    if readback_data is None:
        artifact["status"] = STATUS_BLOCKED if readback_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    readback_item = find_site_entry(readback_data, site_url)
    readback_step["matched"] = readback_item is not None
    readback_step["observed_lifecycle_state"] = (readback_item or {}).get("lifecycle_state")
    if readback_item is None:
        readback_step["status"] = STATUS_FAILED
        readback_step["reason"] = "site_entry_readback_missing"
        failures.append("readback_site_entry:site_entry_readback_missing")
        artifact["status"] = STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    readback_step["status"] = STATUS_PASSED

    accept_payload = {
        "project_key": project_key,
        "scope": "project",
        "site_url": site_url,
        "lifecycle_state": "accepted",
        "reviewer": "codex-live-smoke",
        "review_note": "accepted by resource source lifecycle smoke",
    }
    accept_step = {"name": "accept_lifecycle", "path": SITE_ENTRY_LIFECYCLE_PATH, "request_payload": accept_payload}
    artifact["steps"].append(accept_step)
    accept_result = _http_patch_json(build_url(api_base, SITE_ENTRY_LIFECYCLE_PATH), accept_payload, timeout=timeout)
    accept_data = response_data_or_step_failure(step=accept_step, result=accept_result, failures=failures)
    if accept_data is None:
        artifact["status"] = STATUS_BLOCKED if accept_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    accepted_evidence, accepted_failures, next_action_payload = validate_accepted_response(accept_data, site_url)
    accept_step["evidence"] = accepted_evidence
    if accepted_failures:
        accept_step["status"] = STATUS_FAILED
        accept_step["reason"] = "accepted_contract_missing_fields"
        failures.extend(f"accept_lifecycle:{failure}" for failure in accepted_failures)
        artifact["evidence"]["accepted_guard_status"] = (accepted_evidence.get("single_source_guard") or {}).get("status")
        artifact["status"] = STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    accept_step["status"] = STATUS_PASSED
    artifact["evidence"]["accepted_guard_status"] = (accepted_evidence.get("single_source_guard") or {}).get("status")
    artifact["evidence"]["accepted_report_source_ref"] = accepted_evidence.get("report_source_ref")

    run_payload = dict(next_action_payload or {})
    run_payload["project_key"] = project_key
    run_payload["async_mode"] = True
    run_payload["idempotency_key"] = smoke_id
    run_step = {
        "name": "source_library_run",
        "path": SOURCE_LIBRARY_RUN_PATH,
        "next_action_payload": next_action_payload,
        "request_payload": run_payload,
    }
    artifact["steps"].append(run_step)
    run_result = _http_post_json(build_url(api_base, SOURCE_LIBRARY_RUN_PATH), run_payload, timeout=timeout)
    run_data = response_data_or_step_failure(step=run_step, result=run_result, failures=failures)
    if run_data is None:
        artifact["status"] = STATUS_BLOCKED if run_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    run_evidence = extract_run_evidence(run_data)
    run_step["evidence"] = run_evidence
    artifact["evidence"]["run_task_id"] = run_evidence.get("task_id")
    artifact["evidence"]["run_terminal_status"] = run_evidence.get("terminal_status")
    artifact["evidence"]["run_trace_id"] = run_evidence.get("trace_id")
    artifact["evidence"]["run_submission_id"] = run_evidence.get("submission_id")
    if not run_evidence["has_task_or_terminal_or_trace"]:
        run_step["status"] = STATUS_FAILED
        run_step["reason"] = "source_library_run_missing_task_terminal_or_trace"
        failures.append("source_library_run:missing_task_terminal_or_trace")
        artifact["status"] = STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    run_step["status"] = STATUS_PASSED

    reject_payload = {
        "project_key": project_key,
        "scope": "project",
        "site_url": site_url,
        "lifecycle_state": "rejected",
        "reviewer": "codex-live-smoke",
        "review_note": "rejected to verify blocked collect action",
        "review_reason": "smoke cleanup state",
    }
    reject_step = {"name": "reject_lifecycle", "path": SITE_ENTRY_LIFECYCLE_PATH, "request_payload": reject_payload}
    artifact["steps"].append(reject_step)
    reject_result = _http_patch_json(build_url(api_base, SITE_ENTRY_LIFECYCLE_PATH), reject_payload, timeout=timeout)
    reject_data = response_data_or_step_failure(step=reject_step, result=reject_result, failures=failures)
    if reject_data is None:
        artifact["status"] = STATUS_BLOCKED if reject_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    blocked_evidence, blocked_failures = validate_blocked_review_response(reject_data, site_url)
    reject_step["evidence"] = blocked_evidence
    artifact["evidence"]["blocked_review_status"] = blocked_evidence.get("review_closure_status")
    artifact["evidence"]["blocked_guard_status"] = (blocked_evidence.get("single_source_guard") or {}).get("status")
    if blocked_failures:
        reject_step["status"] = STATUS_FAILED
        reject_step["reason"] = "blocked_review_contract_missing_fields"
        failures.extend(f"reject_lifecycle:{failure}" for failure in blocked_failures)
        artifact["status"] = STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    reject_step["status"] = STATUS_PASSED

    artifact["status"] = STATUS_PASSED if not failures else STATUS_FAILED
    artifact["summary"] = build_summary(artifact)
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    api_base = args.api_base or args.base_url or "http://127.0.0.1:8000"
    output = Path(args.output)
    artifact = build_artifact(
        api_base=api_base,
        project_key=args.project_key,
        output=output,
        timeout=args.timeout,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    if artifact["status"] == STATUS_PASSED:
        return 0
    if args.allow_blocked and artifact["status"] == STATUS_BLOCKED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
