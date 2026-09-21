#!/usr/bin/env python3
"""Submit smoke triggers for worker-required business-line readback paths."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Sequence
from urllib import error, request

try:
    from scripts._automation_runtime import utc_now, write_json
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import utc_now, write_json


SCHEMA_VERSION = "business_line_worker_readback_smoke_triggers.v1"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

WORKER_REQUIRED_LINE_KEYS = (
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "writing_knowledge_graph_agent",
)


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: str
    error: str | None = None


@dataclass(frozen=True)
class TriggerSpec:
    line_key: str
    trigger_kind: str
    method: str
    path: str
    payload: dict[str, Any]


def normalize_api_base(api_base: str) -> str:
    return api_base.rstrip("/")


def build_url(api_base: str, path: str) -> Annotated[
    str,
    "kit:prepared-command effect_boundary=trigger_smoke_http_probe witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalize_api_base(api_base)}{normalized_path}"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True, help="Backend base URL, for example http://127.0.0.1:8000.")
    parser.add_argument("--project-key", required=True, help="Project key used by the smoke trigger submissions.")
    parser.add_argument("--output", required=True, type=Path, help="Path to write the trigger artifact JSON.")
    parser.add_argument("--timeout", default=5.0, type=float, help="HTTP timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Print the artifact JSON after writing.")
    return parser.parse_args(argv)


def _http_post_json(url: str, payload: dict[str, Any], *, timeout: float) -> HttpResult:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - explicit backend URL input.
            return HttpResult(
                status_code=int(response.status),
                body=response.read().decode("utf-8", errors="replace"),
            )
    except error.HTTPError as exc:
        return HttpResult(
            status_code=int(exc.code),
            body=exc.read().decode("utf-8", errors="replace"),
            error=str(exc),
        )
    except (error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return HttpResult(status_code=None, body="", error=str(exc))


def smoke_token(observed_at: str) -> str:
    return observed_at.replace("-", "").replace(":", "").replace("Z", "").replace("T", "-")


def trigger_specs(*, project_key: str, observed_at: str) -> list[TriggerSpec]:
    token = smoke_token(observed_at)
    return [
        TriggerSpec(
            line_key="search_discovery_index",
            trigger_kind="agent_batch.search_market",
            method="POST",
            path="/api/v1/agent-batch/jobs",
            payload={
                "project_key": project_key,
                "idempotency_key": f"worker-readback-smoke-search-market-{token}",
                "priority": 0,
                "batch": {
                    "jobs": [
                        {
                            "item_id": "smoke-search-market",
                            "channel": "search.market",
                            "query_terms": ["worker readback smoke market"],
                            "max_items": 1,
                            "provider": "auto",
                            "language": "en",
                            "days_back": 1,
                            "override_params": {"enable_extraction": False},
                        }
                    ]
                },
            },
        ),
        TriggerSpec(
            line_key="resource_source_library",
            trigger_kind="ingest.source_library_run_smoke_only",
            method="POST",
            path="/api/v1/ingest/source-library/run",
            payload={
                "project_key": project_key,
                "idempotency_key": f"worker-readback-smoke-source-library-{token}",
                "item_key": "url_pool.default",
                "query_terms": ["worker readback smoke source library"],
                "max_items": 1,
                "async_mode": True,
                "override_params": {
                    "_source_library_smoke_only": True,
                    "enable_extraction": False,
                    "limit": 1,
                },
            },
        ),
        TriggerSpec(
            line_key="writing_knowledge_graph_agent",
            trigger_kind="writing.llm_action",
            method="POST",
            path="/api/v1/writing/llm-actions",
            payload={
                "project_key": project_key,
                "action_id": "outline_generate",
                "template_key": "worker_readback_smoke",
                "template_version": "smoke.v1",
                "document_id": "worker-readback-smoke",
                "input_markdown": "# Worker readback smoke\n\nSubmit only; readback validation is external.",
                "async": True,
                "gate_mode": "warn",
                "agent_role": "business_capability_wrapper",
            },
        ),
        TriggerSpec(
            line_key="ingest",
            trigger_kind="ingest.url_single_celery",
            method="POST",
            path="/api/v1/ingest/url/single",
            payload={
                "project_key": project_key,
                "url": "https://example.com/",
                "query_terms": ["worker readback smoke ingest"],
                "idempotency_key": f"worker-readback-smoke-ingest-url-{token}",
                "strict_mode": False,
                "search_expand": False,
                "allow_search_summary_write": False,
                "async_mode": True,
            },
        ),
    ]


def payload_roots(payload: Any) -> list[Any]:
    roots = [payload]
    if isinstance(payload, dict):
        for key in ("data", "result", "task", "run", "job", "meta", "observability"):
            value = payload.get(key)
            if isinstance(value, dict):
                roots.append(value)
    return roots


def scalar_from_payload(payload: Any, *keys: str) -> str | None:
    for root in payload_roots(payload):
        if not isinstance(root, dict):
            continue
        for key in keys:
            value = root.get(key)
            if isinstance(value, (str, int, float)) and str(value).strip():
                return str(value).strip()
        for parent in ("meta", "observability", "trace_chain"):
            nested = root.get(parent)
            if not isinstance(nested, dict):
                continue
            for key in keys:
                value = nested.get(key)
                if isinstance(value, (str, int, float)) and str(value).strip():
                    return str(value).strip()
    return None


def accepted_items(payload: Any) -> list[dict[str, Any]]:
    for root in payload_roots(payload):
        if not isinstance(root, dict):
            continue
        value = root.get("accepted_job_items")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def api_status(payload: Any) -> str | None:
    for root in payload_roots(payload):
        if isinstance(root, dict) and isinstance(root.get("status"), str):
            return str(root["status"]).strip().lower()
    return None


def api_error_message(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        for key in ("message", "code", "detail"):
            value = error_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    detail = payload.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    if isinstance(detail, dict):
        return api_error_message(detail)
    return None


def extract_ids(payload: Any) -> dict[str, str | None]:
    items = accepted_items(payload)
    first_item = items[0] if items else None
    return {
        "task_id": (
            scalar_from_payload(first_item, "task_id", "celery_task_id")
            if first_item is not None
            else scalar_from_payload(payload, "task_id", "celery_task_id")
        ),
        "run_id": (
            scalar_from_payload(first_item, "run_id", "workflow_run_id")
            if first_item is not None
            else scalar_from_payload(payload, "run_id", "workflow_run_id")
        ),
        "job_id": scalar_from_payload(payload, "job_id"),
    }


def is_api_success(payload: Any) -> bool:
    status = api_status(payload)
    if status in {"error", "failed", "failure"}:
        return False
    for root in payload_roots(payload):
        if not isinstance(root, dict):
            continue
        rejected_count = root.get("rejected_count")
        accepted_count = root.get("accepted_count")
        if isinstance(rejected_count, int) and rejected_count > 0 and not accepted_count:
            return False
    return True


def line_recommended_next_commands(
    *,
    api_base: str,
    project_key: str,
    output: Path,
    line_key: str,
) -> list[str]:
    artifact_dir = output.parent
    del line_key
    return [
        (
            "python3 scripts/run_business_line_async_task_readback_live_samples.py "
            f"--api-base {api_base} --project-key {project_key} "
            f"--output {artifact_dir / 'business-line-async-task-readback-live-samples.json'} --json"
        ),
        (
            "python3 scripts/run_business_line_worker_readback_evidence_chain.py "
            f"--api-base {api_base} --project-key {project_key} --artifact-dir {artifact_dir} --json"
        ),
    ]


def blocked_line(spec: TriggerSpec, *, api_base: str, project_key: str, output: Path, reason: str, error_text: str | None) -> dict[str, Any]:
    return {
        "line_key": spec.line_key,
        "trigger_kind": spec.trigger_kind,
        "method": spec.method,
        "path": spec.path,
        "accepted": False,
        "blocked": True,
        "status": STATUS_BLOCKED,
        "reason": reason,
        "error": error_text,
        "task_id": None,
        "run_id": None,
        "job_id": None,
        "http_status": None,
        "recommended_next_commands": line_recommended_next_commands(
            api_base=api_base,
            project_key=project_key,
            output=output,
            line_key=spec.line_key,
        ),
    }


def trigger_line(
    spec: TriggerSpec,
    *,
    api_base: str,
    project_key: str,
    output: Path,
    timeout: float,
) -> tuple[dict[str, Any], bool]:
    url = build_url(api_base, spec.path)
    result = _http_post_json(url, spec.payload, timeout=timeout)
    if result.status_code is None:
        return (
            blocked_line(
                spec,
                api_base=api_base,
                project_key=project_key,
                output=output,
                reason="backend_unreachable",
                error_text=result.error,
            ),
            True,
        )

    payload: Any | None
    parse_error: str | None = None
    try:
        payload = json.loads(result.body) if result.body else {}
    except json.JSONDecodeError as exc:
        payload = None
        parse_error = f"response is not valid JSON: {exc}"

    ids = extract_ids(payload) if payload is not None else {"task_id": None, "run_id": None, "job_id": None}
    accepted = (
        200 <= int(result.status_code) < 300
        and parse_error is None
        and payload is not None
        and is_api_success(payload)
        and any(ids.values())
    )
    status = STATUS_PASSED if accepted else STATUS_FAILED
    reason = None
    error_text = None
    if status == STATUS_FAILED:
        if not (200 <= int(result.status_code) < 300):
            reason = "http_error"
            error_text = result.error or api_error_message(payload) if payload is not None else result.error
        elif parse_error is not None:
            reason = "invalid_json_response"
            error_text = parse_error
        elif payload is not None and not is_api_success(payload):
            reason = "api_error"
            error_text = api_error_message(payload)
        else:
            reason = "trigger_identity_missing"
            error_text = "accepted trigger response did not include task_id, run_id, or job_id"

    return (
        {
            "line_key": spec.line_key,
            "trigger_kind": spec.trigger_kind,
            "method": spec.method,
            "path": spec.path,
            "accepted": accepted,
            "blocked": False,
            "status": status,
            "reason": reason,
            "error": error_text,
            "task_id": ids["task_id"],
            "run_id": ids["run_id"],
            "job_id": ids["job_id"],
            "http_status": result.status_code,
            "response_status": api_status(payload) if payload is not None else None,
            "recommended_next_commands": line_recommended_next_commands(
                api_base=api_base,
                project_key=project_key,
                output=output,
                line_key=spec.line_key,
            ),
        },
        False,
    )


def summarize(lines: list[dict[str, Any]]) -> dict[str, Any]:
    by_key = {str(line.get("line_key")): line for line in lines}
    accepted_line_keys = [
        line_key for line_key in WORKER_REQUIRED_LINE_KEYS if by_key.get(line_key, {}).get("accepted") is True
    ]
    blocked_line_keys = [
        line_key for line_key in WORKER_REQUIRED_LINE_KEYS if by_key.get(line_key, {}).get("blocked") is True
    ]
    failed_line_keys = [
        line_key for line_key in WORKER_REQUIRED_LINE_KEYS if by_key.get(line_key, {}).get("status") == STATUS_FAILED
    ]
    return {
        "total": len(lines),
        "accepted": sum(1 for line in lines if line.get("accepted") is True),
        "blocked": sum(1 for line in lines if line.get("blocked") is True),
        "failed": sum(1 for line in lines if line.get("status") == STATUS_FAILED),
        "accepted_line_keys": accepted_line_keys,
        "blocked_line_keys": blocked_line_keys,
        "failed_line_keys": failed_line_keys,
    }


def overall_status(lines: list[dict[str, Any]]) -> str:
    if any(line.get("status") == STATUS_FAILED for line in lines):
        return STATUS_FAILED
    if lines and all(line.get("blocked") is True for line in lines):
        return STATUS_BLOCKED
    if any(line.get("blocked") is True for line in lines):
        return STATUS_BLOCKED
    return STATUS_PASSED


def top_level_recommended_next_commands(*, api_base: str, project_key: str, output: Path) -> list[str]:
    artifact_dir = output.parent
    return [
        (
            "python3 scripts/run_business_line_worker_readback_evidence_chain.py "
            f"--api-base {api_base} --project-key {project_key} --artifact-dir {artifact_dir} --json"
        ),
        (
            "python3 scripts/run_business_line_async_task_readback_live_samples.py "
            f"--api-base {api_base} --project-key {project_key} "
            f"--output {artifact_dir / 'business-line-async-task-readback-live-samples.json'} --json"
        ),
    ]


def build_artifact(
    *, api_base: str, project_key: str, output: Path, timeout: float
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=owned_trigger_http_probe_results "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    observed_at = utc_now()
    specs = trigger_specs(project_key=project_key, observed_at=observed_at)
    lines: list[dict[str, Any]] = []
    backend_blocked = False
    for spec in specs:
        if backend_blocked:
            lines.append(
                blocked_line(
                    spec,
                    api_base=api_base,
                    project_key=project_key,
                    output=output,
                    reason="backend_unreachable_after_prior_trigger",
                    error_text="prior trigger could not reach backend",
                )
            )
            continue
        line, backend_blocked = trigger_line(
            spec,
            api_base=api_base,
            project_key=project_key,
            output=output,
            timeout=timeout,
        )
        lines.append(line)

    status = overall_status(lines)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "api_base": normalize_api_base(api_base),
        "project_key": project_key,
        "generated_at": observed_at,
        "scope": {
            "worker_required_line_keys": list(WORKER_REQUIRED_LINE_KEYS),
            "does_long_poll": False,
            "does_readback_validation": False,
        },
        "summary": summarize(lines),
        "lines": lines,
        "recommended_next_commands": top_level_recommended_next_commands(
            api_base=api_base,
            project_key=project_key,
            output=output,
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    artifact = build_artifact(
        api_base=args.api_base,
        project_key=args.project_key,
        output=args.output,
        timeout=float(args.timeout),
    )
    write_json(args.output, artifact)
    if args.json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if artifact["status"] == STATUS_PASSED else 1


if __name__ == "__main__":
    sys.exit(main())
