#!/usr/bin/env python3
"""Run a live project config workflow dry-run smoke flow."""

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


SCHEMA_VERSION = "project_config_workflow_dry_run_smoke.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

PROJECT_CUSTOMIZATION_BASE_PATH = "/api/v1/project-customization"
WORKFLOWS_PATH = f"{PROJECT_CUSTOMIZATION_BASE_PATH}/workflows"
PROJECTS_PATH = "/api/v1/projects"


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: str
    error: str | None = None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", dest="base_url", help="Backend API base URL.")
    parser.add_argument("--api-base", dest="api_base", help="Backend API base URL alias.")
    parser.add_argument("--project-key", default="demo_proj", help="Project key for project-scoped workflow config.")
    parser.add_argument(
        "--workflow",
        default=None,
        help="Workflow name to stage, promote, dry-run, and preview rollback. Defaults to a unique smoke workflow.",
    )
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
    "effect_boundary=project_config_workflow_http_request "
    "witness=test:test_w12_runtime_misc_laws",
]:
    normalized_path = path if path.startswith("/") else f"/{path}"
    url = f"{normalize_api_base(api_base)}{normalized_path}"
    if query:
        clean_query = {key: value for key, value in query.items() if value is not None}
        if clean_query:
            url = f"{url}?{parse.urlencode(clean_query, doseq=True)}"
    return url


def workflow_path(workflow: str, suffix: str = "") -> str:
    quoted_workflow = parse.quote(workflow.strip(), safe="")
    return f"{WORKFLOWS_PATH}/{quoted_workflow}{suffix}"


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


def load_json_payload(result: HttpResult) -> tuple[Any | None, str | None]:
    try:
        return json.loads(result.body), None
    except json.JSONDecodeError as exc:
        return None, f"response is not valid JSON: {exc}"


def unwrap_envelope(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("data"), (dict, list)):
        return payload["data"]
    return payload


def bool_at_path(payload: Any, data_path: str) -> bool | None:
    value = value_at_path(payload, data_path)
    return value if isinstance(value, bool) else None


def int_at_path(payload: Any, data_path: str) -> int | None:
    value = value_at_path(payload, data_path)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def str_at_path(payload: Any, data_path: str) -> str | None:
    value = value_at_path(payload, data_path)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def value_at_path(payload: Any, data_path: str) -> Any:
    current = payload
    for part in [part for part in data_path.replace("/", ".").split(".") if part]:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def response_data_or_step_failure(
    *,
    step: dict[str, Any],
    result: HttpResult,
    failures: list[str],
) -> dict[str, Any] | None:
    step["http_status"] = result.status_code
    step["error"] = result.error
    step.setdefault("evidence", {})
    if result.status_code is None:
        step["status"] = STATUS_BLOCKED
        step["reason"] = "backend_unreachable"
        step["evidence"].update({"backend_unreachable": True, "error": result.error})
        failures.append(f"{step['name']}:backend_unreachable")
        return None
    if not (200 <= result.status_code < 300):
        step["status"] = STATUS_FAILED
        step["reason"] = "http_error"
        step["response_body_preview"] = result.body[:500]
        step["evidence"].update({"http_error": True, "http_status": result.status_code})
        failures.append(f"{step['name']}:http_{result.status_code}")
        return None
    payload, json_error = load_json_payload(result)
    if json_error is not None:
        step["status"] = STATUS_FAILED
        step["reason"] = "invalid_json"
        step["response_body_preview"] = result.body[:500]
        step["evidence"].update({"invalid_json": True, "http_status": result.status_code})
        failures.append(f"{step['name']}:invalid_json")
        return None
    step["response"] = payload
    data = unwrap_envelope(payload)
    if not isinstance(data, dict):
        step["status"] = STATUS_FAILED
        step["reason"] = "missing_data_object"
        step["evidence"].update({"missing_data_object": True, "http_status": result.status_code})
        failures.append(f"{step['name']}:missing_data_object")
        return None
    return data


def workflow_template_payload(smoke_id: str) -> dict[str, Any]:
    return {
        "steps": [
            {
                "handler": "ingest.market",
                "params": {"limit": 2, "smoke_id": smoke_id},
                "enabled": True,
                "name": f"Codex workflow smoke collect {smoke_id}",
            },
            {
                "handler": "ingest.google_news",
                "params": {"q": f"project config workflow smoke {smoke_id}"},
                "enabled": False,
                "name": "Codex workflow smoke disabled news",
            },
        ],
        "board_layout": {
            "layout": "table",
            "source": "run_project_config_workflow_dry_run_smoke.py",
            "smoke_id": smoke_id,
        },
    }


def extract_governance_evidence(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "governance_dry_run": bool_at_path(data, "governance.dry_run"),
        "governance_will_mutate": bool_at_path(data, "governance.will_mutate"),
        "governance_requires_publish": bool_at_path(data, "governance.requires_publish"),
        "governance_operation": str_at_path(data, "governance.operation"),
        "governance_stage": str_at_path(data, "governance.stage"),
        "version_summary_will_mutate": bool_at_path(data, "version_summary.will_mutate"),
        "version_summary_requires_publish": bool_at_path(data, "version_summary.requires_publish"),
        "version_summary_stage": str_at_path(data, "version_summary.stage"),
        "current_version": int_at_path(data, "current_version"),
        "next_version": int_at_path(data, "next_version"),
    }


def extract_diff_evidence(data: dict[str, Any]) -> dict[str, Any]:
    evidence = extract_governance_evidence(data)
    evidence.update(
        {
            "changed": bool_at_path(data, "changed"),
            "will_mutate": bool_at_path(data, "version_summary.will_mutate"),
            "requires_publish": bool_at_path(data, "version_summary.requires_publish"),
            "stage": str_at_path(data, "version_summary.stage"),
            "reason_code": str_at_path(data, "reason_code"),
        }
    )
    return evidence


def extract_stage_evidence(data: dict[str, Any]) -> dict[str, Any]:
    evidence = extract_governance_evidence(data)
    evidence.update(
        {
            "stage": str_at_path(data, "stage"),
            "saved": bool_at_path(data, "saved"),
            "stage_record_stage": str_at_path(data, "stage_record.stage"),
            "stage_record_version": int_at_path(data, "stage_record.version"),
            "audit_action": str_at_path(data, "audit.action"),
            "audit_trace_id": str_at_path(data, "audit.trace_id"),
        }
    )
    return evidence


def extract_versions_evidence(data: dict[str, Any]) -> dict[str, Any]:
    items = data.get("items") if isinstance(data.get("items"), list) else []
    history = data.get("history") if isinstance(data.get("history"), list) else []
    return {
        **extract_governance_evidence(data),
        "has_draft": bool_at_path(data, "stage_summary.has_draft"),
        "has_staging": bool_at_path(data, "stage_summary.has_staging"),
        "has_active": bool_at_path(data, "stage_summary.has_active"),
        "draft_version": int_at_path(data, "stage_summary.draft_version"),
        "staging_version": int_at_path(data, "stage_summary.staging_version"),
        "active_version": int_at_path(data, "stage_summary.active_version"),
        "item_count": len(items),
        "history_count": len(history),
        "latest_trace_id": str_at_path(data, "stage_summary.latest_audit.trace_id"),
    }


def extract_promote_evidence(data: dict[str, Any]) -> dict[str, Any]:
    evidence = extract_governance_evidence(data)
    evidence.update(
        {
            "promoted": bool_at_path(data, "promoted"),
            "from_stage": str_at_path(data, "from_stage"),
            "to_stage": str_at_path(data, "to_stage"),
            "stage_record_stage": str_at_path(data, "stage_record.stage"),
            "stage_record_version": int_at_path(data, "stage_record.version"),
            "stage_record_promoted_from": str_at_path(data, "stage_record.promoted_from"),
            "audit_action": str_at_path(data, "audit.action"),
            "audit_trace_id": str_at_path(data, "audit.trace_id"),
        }
    )
    return evidence


def extract_run_evidence(data: dict[str, Any]) -> dict[str, Any]:
    impact = data.get("impact_summary") if isinstance(data.get("impact_summary"), dict) else {}
    policy_change = impact.get("policy_change") if isinstance(impact.get("policy_change"), dict) else {}
    return {
        **extract_governance_evidence(data),
        "dry_run": bool_at_path(data, "dry_run"),
        "status": str_at_path(data, "status"),
        "reason_code": str_at_path(data, "reason_code"),
        "readiness": str_at_path(data, "readiness"),
        "writes_blocked": impact.get("writes_blocked"),
        "runtime_tasks_blocked": impact.get("runtime_tasks_blocked"),
        "policy_requires_publish": policy_change.get("requires_publish"),
        "policy_will_mutate": policy_change.get("will_mutate"),
        "config_version": int_at_path(data, "config_version"),
    }


def extract_rollback_evidence(data: dict[str, Any]) -> dict[str, Any]:
    plan = data.get("rollback_plan") if isinstance(data.get("rollback_plan"), dict) else {}
    return {
        **extract_governance_evidence(data),
        "rollback_preview": bool_at_path(data, "rollback_preview"),
        "rollback_plan_will_mutate": plan.get("will_mutate"),
        "rollback_plan_can_execute": plan.get("can_execute"),
        "rollback_plan_target_version": plan.get("target_version"),
        "rollback_plan_to_stage": plan.get("to_stage"),
        "target_version": int_at_path(data, "version_summary.target_version"),
        "active_version": int_at_path(data, "version_summary.active_version"),
        "staging_version": int_at_path(data, "version_summary.staging_version"),
    }


def fail_step(step: dict[str, Any], failures: list[str], reason: str, checks: Sequence[str]) -> None:
    step["status"] = STATUS_FAILED
    step["reason"] = reason
    failures.extend(f"{step['name']}:{check}" for check in checks)


def validate_project_readback(step: dict[str, Any], data: dict[str, Any], project_key: str, failures: list[str]) -> bool:
    items = data.get("items") if isinstance(data.get("items"), list) else []
    matched_item = next(
        (
            item
            for item in items
            if isinstance(item, dict) and str(item.get("project_key") or "").strip() == project_key
        ),
        None,
    )
    step["evidence"] = {
        "project_key": project_key,
        "project_present": matched_item is not None,
        "project_count": len(items),
        "schema_ready": matched_item.get("schema_ready") if isinstance(matched_item, dict) else None,
        "enabled": matched_item.get("enabled") if isinstance(matched_item, dict) else None,
    }
    if matched_item is None:
        fail_step(step, failures, "project_missing_from_readback", ["project_present"])
        return False
    step["status"] = STATUS_PASSED
    return True


def validate_step_evidence(
    step: dict[str, Any],
    failures: list[str],
    checks: dict[str, Any],
    *,
    reason: str = "contract_missing_fields",
) -> bool:
    missing = [field for field, expected in checks.items() if step.get("evidence", {}).get(field) != expected]
    if missing:
        fail_step(step, failures, reason, missing)
        return False
    step["status"] = STATUS_PASSED
    return True


def build_summary(
    artifact: dict[str, Any],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=view "
    "fact_source=completed_project_config_workflow_artifact "
    "witness=test:test_w12_runtime_misc_laws",
]:
    steps = artifact["steps"]
    evidence = artifact.get("evidence") if isinstance(artifact.get("evidence"), dict) else {}
    return {
        "step_count": len(steps),
        "passed_step_count": sum(1 for step in steps if step.get("status") == STATUS_PASSED),
        "failed_step_count": sum(1 for step in steps if step.get("status") == STATUS_FAILED),
        "blocked_step_count": sum(1 for step in steps if step.get("status") == STATUS_BLOCKED),
        "workflow": artifact["workflow"],
        "project_key": artifact["project_key"],
        "draft_version": evidence.get("draft_version"),
        "staging_version": evidence.get("staging_version"),
        "active_version": evidence.get("active_version"),
        "workflow_dry_run_writes_blocked": evidence.get("workflow_dry_run_writes_blocked"),
        "workflow_dry_run_runtime_tasks_blocked": evidence.get("workflow_dry_run_runtime_tasks_blocked"),
        "rollback_preview_will_mutate": evidence.get("rollback_preview_will_mutate"),
        "failure_count": len(artifact["failures"]),
    }


def recommended_command(api_base: str, output: Path, project_key: str, workflow: str) -> str:
    return (
        "python3 scripts/run_project_config_workflow_dry_run_smoke.py "
        f"--api-base {api_base} --project-key {project_key} --workflow {workflow} "
        f"--output {output} --allow-blocked --json"
    )


def build_artifact(
    *,
    api_base: str,
    project_key: str,
    workflow: str | None,
    output: Path,
    timeout: float,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=generated_evidence "
    "fact_source=owned_project_config_workflow_dry_run_step_results "
    "witness=test:test_w12_runtime_misc_laws",
]:
    smoke_id = f"project-config-workflow-dry-run-{uuid.uuid4().hex[:12]}"
    workflow_name = (workflow or "").strip() or f"codex_workflow_dry_run_{smoke_id.rsplit('-', 1)[-1]}"
    generated_at = utc_now()
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_FAILED,
        "generated_at": generated_at,
        "api_base": normalize_api_base(api_base),
        "project_key": project_key,
        "workflow": workflow_name,
        "smoke_id": smoke_id,
        "steps": [],
        "failures": [],
        "summary": {},
        "evidence": {},
        "recommended_command": recommended_command(api_base, output, project_key, workflow_name),
    }
    failures: list[str] = artifact["failures"]
    template_payload = {"project_key": project_key, **workflow_template_payload(smoke_id)}

    config_step = {
        "name": "project_readback",
        "path": PROJECTS_PATH,
    }
    artifact["steps"].append(config_step)
    config_result = _http_get(build_url(api_base, PROJECTS_PATH), timeout=timeout)
    config_data = response_data_or_step_failure(step=config_step, result=config_result, failures=failures)
    if config_data is None or not validate_project_readback(config_step, config_data, project_key, failures):
        artifact["status"] = STATUS_BLOCKED if config_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact

    diff_step = {
        "name": "template_diff_preview",
        "path": workflow_path(workflow_name, "/template/diff"),
        "request_payload": template_payload,
    }
    artifact["steps"].append(diff_step)
    diff_result = _http_post_json(build_url(api_base, diff_step["path"]), template_payload, timeout=timeout)
    diff_data = response_data_or_step_failure(step=diff_step, result=diff_result, failures=failures)
    if diff_data is None:
        artifact["status"] = STATUS_BLOCKED if diff_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    diff_step["evidence"] = extract_diff_evidence(diff_data)
    if not validate_step_evidence(
        diff_step,
        failures,
        {
            "governance_dry_run": True,
            "governance_will_mutate": False,
            "governance_requires_publish": True,
            "version_summary_requires_publish": True,
        },
    ):
        artifact["status"] = STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact

    draft_trace_id = f"{smoke_id}:stage-draft"
    stage_payload = {**template_payload, "stage": "draft", "actor": "codex-live-smoke", "trace_id": draft_trace_id}
    stage_step = {
        "name": "stage_draft",
        "path": workflow_path(workflow_name, "/template/stage"),
        "request_payload": stage_payload,
    }
    artifact["steps"].append(stage_step)
    stage_result = _http_post_json(build_url(api_base, stage_step["path"]), stage_payload, timeout=timeout)
    stage_data = response_data_or_step_failure(step=stage_step, result=stage_result, failures=failures)
    if stage_data is None:
        artifact["status"] = STATUS_BLOCKED if stage_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    stage_step["evidence"] = extract_stage_evidence(stage_data)
    if not validate_step_evidence(
        stage_step,
        failures,
        {
            "stage": "draft",
            "governance_will_mutate": True,
            "governance_requires_publish": True,
            "version_summary_requires_publish": True,
        },
    ):
        artifact["status"] = STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    draft_version = stage_step["evidence"].get("next_version")
    artifact["evidence"]["draft_version"] = draft_version

    versions_step = {
        "name": "versions_after_draft",
        "path": workflow_path(workflow_name, "/template/versions"),
        "query": {"project_key": project_key},
    }
    artifact["steps"].append(versions_step)
    versions_result = _http_get(build_url(api_base, versions_step["path"], versions_step["query"]), timeout=timeout)
    versions_data = response_data_or_step_failure(step=versions_step, result=versions_result, failures=failures)
    if versions_data is None:
        artifact["status"] = STATUS_BLOCKED if versions_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    versions_step["evidence"] = extract_versions_evidence(versions_data)
    if not validate_step_evidence(
        versions_step,
        failures,
        {"governance_dry_run": True, "governance_will_mutate": False, "has_draft": True, "draft_version": draft_version},
    ):
        artifact["status"] = STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact

    staging_trace_id = f"{smoke_id}:promote-staging"
    staging_payload = {
        "project_key": project_key,
        "from_stage": "draft",
        "to_stage": "staging",
        "actor": "codex-live-smoke",
        "trace_id": staging_trace_id,
    }
    staging_step = {
        "name": "promote_to_staging",
        "path": workflow_path(workflow_name, "/template/promote"),
        "request_payload": staging_payload,
    }
    artifact["steps"].append(staging_step)
    staging_result = _http_post_json(build_url(api_base, staging_step["path"]), staging_payload, timeout=timeout)
    staging_data = response_data_or_step_failure(step=staging_step, result=staging_result, failures=failures)
    if staging_data is None:
        artifact["status"] = STATUS_BLOCKED if staging_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    staging_step["evidence"] = extract_promote_evidence(staging_data)
    if not validate_step_evidence(
        staging_step,
        failures,
        {
            "from_stage": "draft",
            "to_stage": "staging",
            "governance_will_mutate": True,
            "governance_requires_publish": True,
            "version_summary_requires_publish": True,
        },
    ):
        artifact["status"] = STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    staging_version = staging_step["evidence"].get("next_version")
    artifact["evidence"]["staging_version"] = staging_version

    active_trace_id = f"{smoke_id}:promote-active"
    active_payload = {
        "project_key": project_key,
        "from_stage": "staging",
        "to_stage": "active",
        "actor": "codex-live-smoke",
        "trace_id": active_trace_id,
    }
    active_step = {
        "name": "promote_to_active",
        "path": workflow_path(workflow_name, "/template/promote"),
        "request_payload": active_payload,
    }
    artifact["steps"].append(active_step)
    active_result = _http_post_json(build_url(api_base, active_step["path"]), active_payload, timeout=timeout)
    active_data = response_data_or_step_failure(step=active_step, result=active_result, failures=failures)
    if active_data is None:
        artifact["status"] = STATUS_BLOCKED if active_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    active_step["evidence"] = extract_promote_evidence(active_data)
    if not validate_step_evidence(
        active_step,
        failures,
        {
            "from_stage": "staging",
            "to_stage": "active",
            "governance_will_mutate": True,
            "governance_requires_publish": False,
            "version_summary_requires_publish": False,
        },
    ):
        artifact["status"] = STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    active_version = active_step["evidence"].get("next_version")
    artifact["evidence"]["active_version"] = active_version

    run_payload = {"project_key": project_key, "params": {"limit": 2, "smoke_id": smoke_id}, "dry_run": True}
    run_step = {
        "name": "workflow_dry_run",
        "path": workflow_path(workflow_name, "/run"),
        "query": {"dry_run": "true"},
        "request_payload": run_payload,
    }
    artifact["steps"].append(run_step)
    run_result = _http_post_json(build_url(api_base, run_step["path"], run_step["query"]), run_payload, timeout=timeout)
    run_data = response_data_or_step_failure(step=run_step, result=run_result, failures=failures)
    if run_data is None:
        artifact["status"] = STATUS_BLOCKED if run_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    run_step["evidence"] = extract_run_evidence(run_data)
    if not validate_step_evidence(
        run_step,
        failures,
        {
            "dry_run": True,
            "governance_dry_run": True,
            "governance_will_mutate": False,
            "governance_requires_publish": False,
            "writes_blocked": True,
            "runtime_tasks_blocked": True,
            "policy_requires_publish": False,
        },
    ):
        artifact["status"] = STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    artifact["evidence"]["workflow_dry_run_writes_blocked"] = run_step["evidence"].get("writes_blocked")
    artifact["evidence"]["workflow_dry_run_runtime_tasks_blocked"] = run_step["evidence"].get("runtime_tasks_blocked")

    rollback_payload = {
        "project_key": project_key,
        "target_stage": "staging",
        "target_version": staging_version,
        "reason": "project config workflow dry-run smoke rollback preview",
        "actor": "codex-live-smoke",
        "trace_id": f"{smoke_id}:rollback-preview",
    }
    rollback_step = {
        "name": "rollback_preview",
        "path": workflow_path(workflow_name, "/template/rollback/preview"),
        "request_payload": rollback_payload,
    }
    artifact["steps"].append(rollback_step)
    rollback_result = _http_post_json(build_url(api_base, rollback_step["path"]), rollback_payload, timeout=timeout)
    rollback_data = response_data_or_step_failure(step=rollback_step, result=rollback_result, failures=failures)
    if rollback_data is None:
        artifact["status"] = STATUS_BLOCKED if rollback_step["status"] == STATUS_BLOCKED else STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    rollback_step["evidence"] = extract_rollback_evidence(rollback_data)
    if not validate_step_evidence(
        rollback_step,
        failures,
        {
            "rollback_preview": True,
            "governance_dry_run": True,
            "governance_will_mutate": False,
            "rollback_plan_will_mutate": False,
            "version_summary_will_mutate": False,
        },
    ):
        artifact["status"] = STATUS_FAILED
        artifact["summary"] = build_summary(artifact)
        return artifact
    artifact["evidence"]["rollback_preview_will_mutate"] = rollback_step["evidence"].get("rollback_plan_will_mutate")

    progression_failures: list[str] = []
    if not isinstance(draft_version, int) or not isinstance(staging_version, int) or not isinstance(active_version, int):
        progression_failures.append("version_progression.missing_version")
    elif not (draft_version < staging_version < active_version):
        progression_failures.append("version_progression.not_increasing")
    if progression_failures:
        failures.extend(progression_failures)
        artifact["status"] = STATUS_FAILED
    else:
        artifact["status"] = STATUS_PASSED
    artifact["summary"] = build_summary(artifact)
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    api_base = args.api_base or args.base_url or "http://127.0.0.1:8000"
    output = Path(args.output)
    artifact = build_artifact(
        api_base=api_base,
        project_key=args.project_key,
        workflow=args.workflow,
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
