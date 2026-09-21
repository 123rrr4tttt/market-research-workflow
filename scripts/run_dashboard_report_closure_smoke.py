#!/usr/bin/env python3
"""Run the live Dashboard -> report -> export -> detail closure smoke."""

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


SCHEMA_VERSION = "dashboard_report_closure_smoke.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"


@dataclass(frozen=True)
class HttpResult:
    status_code: int | None
    body: bytes
    headers: dict[str, str]
    error: str | None = None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", dest="base_url", help="Backend API base URL.")
    parser.add_argument("--api-base", dest="api_base", help="Backend API base URL alias.")
    parser.add_argument("--project-key", default="demo_proj", help="Project key for live smoke writes.")
    parser.add_argument("--output", required=True, help="Path to write the smoke JSON artifact.")
    parser.add_argument("--json", action="store_true", help="Print the artifact JSON.")
    parser.add_argument("--allow-blocked", action="store_true", help="Exit 0 when backend is unreachable.")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds.")
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
    "effect_boundary=dashboard_report_closure_http_request "
    "witness=test:test_w12_runtime_misc_laws",
]:
    url = f"{normalize_api_base(api_base)}{path if path.startswith('/') else '/' + path}"
    if query:
        clean = {key: value for key, value in query.items() if value is not None}
        if clean:
            url = f"{url}?{parse.urlencode(clean, doseq=True)}"
    return url


def _http(method: str, url: str, payload: dict[str, Any] | None, *, timeout: float, accept: str) -> HttpResult:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Accept": accept, "Content-Type": "application/json", "X-Actor-Id": "codex-dashboard-smoke"},
        method=method,
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - explicit smoke URL input
            return HttpResult(
                status_code=int(response.status),
                body=response.read(),
                headers={str(key).lower(): str(value) for key, value in response.headers.items()},
            )
    except error.HTTPError as exc:
        return HttpResult(
            status_code=int(exc.code),
            body=exc.read(),
            headers={str(key).lower(): str(value) for key, value in exc.headers.items()},
            error=str(exc),
        )
    except (error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        return HttpResult(status_code=None, body=b"", headers={}, error=str(exc))


def _http_get_json(url: str, *, timeout: float) -> HttpResult:
    return _http("GET", url, None, timeout=timeout, accept="application/json")


def _http_post_json(url: str, payload: dict[str, Any], *, timeout: float) -> HttpResult:
    return _http("POST", url, payload, timeout=timeout, accept="application/json")


def _http_post_markdown(url: str, payload: dict[str, Any], *, timeout: float) -> HttpResult:
    return _http("POST", url, payload, timeout=timeout, accept="text/markdown")


def _http_post_binary(url: str, payload: dict[str, Any], *, timeout: float, accept: str) -> HttpResult:
    return _http("POST", url, payload, timeout=timeout, accept=accept)


def load_json(result: HttpResult) -> tuple[Any | None, str | None]:
    try:
        return json.loads(result.body.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"response is not valid JSON: {exc}"


def unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("data"), (dict, list)):
        return payload["data"]
    return payload


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if not isinstance(value, dict):
        return value
    redacted: dict[str, Any] = {}
    for key, item in value.items():
        normalized = str(key).lower()
        if normalized in {"artifact_token", "token", "signed_token", "secret", "signature"}:
            redacted[key] = "[redacted]"
        else:
            redacted[key] = redact_sensitive(item)
    return redacted


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def append_step(artifact: dict[str, Any], name: str, path: str) -> dict[str, Any]:
    step = {"name": name, "path": path, "status": "not_run", "http_status": None, "evidence": {}}
    artifact["steps"].append(step)
    return step


def json_step_data(step: dict[str, Any], result: HttpResult, failures: list[str]) -> dict[str, Any] | None:
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
        step["response_body_preview"] = result.body.decode("utf-8", errors="replace")[:500]
        failures.append(f"{step['name']}:http_{result.status_code}")
        return None
    payload, err = load_json(result)
    if err:
        step["status"] = STATUS_FAILED
        step["reason"] = "invalid_json"
        failures.append(f"{step['name']}:invalid_json")
        return None
    step["response"] = redact_sensitive(payload)
    data = unwrap_data(payload)
    if not isinstance(data, dict):
        step["status"] = STATUS_FAILED
        step["reason"] = "missing_data_object"
        failures.append(f"{step['name']}:missing_data_object")
        return None
    return data


def fail_step(artifact: dict[str, Any], step: dict[str, Any], failures: list[str], reason: str, missing: list[str]) -> dict[str, Any]:
    step["status"] = STATUS_FAILED
    step["reason"] = reason
    failures.extend(f"{step['name']}:{item}" for item in missing)
    artifact["status"] = STATUS_FAILED
    artifact["summary"] = build_summary(artifact)
    return artifact


def blocked_or_failed(artifact: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    artifact["status"] = STATUS_BLOCKED if step.get("status") == STATUS_BLOCKED else STATUS_FAILED
    artifact["summary"] = build_summary(artifact)
    return artifact


def dashboard_payload(project_key: str, smoke_id: str) -> dict[str, Any]:
    trace_id = f"dashboard-report:{smoke_id}"
    return {
        "request_type": "report_from_dashboard_filter",
        "project_key": project_key,
        "dashboard": {
            "variant": "dashboard",
            "trace_id": trace_id,
            "selected_label": "Documents",
            "selected_metric": "documents",
            "selected_source_ref": "dashboard.stats.documents",
            "filters": {"limit": 1, "doc_type": "policy"},
            "source_query": {
                "scope": "dashboard.stats",
                "card": "documents",
                "table": "documents",
                "metrics": ["documents"],
                "filters": {"doc_type": "policy"},
            },
            "source_refs": [
                {
                    "id": "dashboard.stats.documents",
                    "kind": "sql_table",
                    "table": "documents",
                    "columns": ["id", "title"],
                    "published_at": "2026-05-01",
                    "trust_score": 0.92,
                }
            ],
            "sample_rows": [{"id": 101, "title": "Policy sample"}],
            "sample_row_count": 1,
        },
        "report_options": {"include_dashboard_sample_rows": True, "as_of_date": "2026-05-24", "trace_id": trace_id},
    }


def build_summary(
    artifact: dict[str, Any],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=view "
    "fact_source=completed_dashboard_report_closure_artifact "
    "witness=test:test_w12_runtime_misc_laws",
]:
    steps = artifact.get("steps") if isinstance(artifact.get("steps"), list) else []
    evidence = artifact.get("evidence") if isinstance(artifact.get("evidence"), dict) else {}
    return {
        "step_count": len(steps),
        "passed_step_count": sum(1 for step in steps if isinstance(step, dict) and step.get("status") == STATUS_PASSED),
        "failed_step_count": sum(1 for step in steps if isinstance(step, dict) and step.get("status") == STATUS_FAILED),
        "blocked_step_count": sum(1 for step in steps if isinstance(step, dict) and step.get("status") == STATUS_BLOCKED),
        "failure_count": len(artifact.get("failures") or []),
        "trace_id": evidence.get("trace_id"),
        "document_id": evidence.get("document_id"),
        "markdown_size_bytes": evidence.get("markdown_size_bytes"),
        "export_size_bytes": evidence.get("export_size_bytes"),
        "detail_found": evidence.get("detail_found"),
        "detail_source_ref_count": evidence.get("detail_source_ref_count"),
        "detail_export_event_count": evidence.get("detail_export_event_count"),
        "detail_quality_gate_status": evidence.get("detail_quality_gate_status"),
    }


def build_artifact(
    *, api_base: str, project_key: str, output: Path, timeout: float
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative "
    "derived_as=generated_evidence "
    "fact_source=owned_dashboard_report_closure_http_step_results "
    "witness=test:test_w12_runtime_misc_laws",
]:
    smoke_id = uuid.uuid4().hex[:12]
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_FAILED,
        "generated_at": utc_now(),
        "api_base": normalize_api_base(api_base),
        "project_key": project_key,
        "smoke_id": smoke_id,
        "steps": [],
        "failures": [],
        "evidence": {},
        "summary": {},
        "recommended_command": (
            "python3 scripts/run_dashboard_report_closure_smoke.py "
            f"--api-base {api_base} --project-key {project_key} --output {output} --allow-blocked --json"
        ),
    }
    failures: list[str] = artifact["failures"]

    stats_step = append_step(artifact, "dashboard_stats_source_refs", "/api/v1/dashboard/stats")
    stats_data = json_step_data(
        stats_step,
        _http_get_json(build_url(api_base, "/api/v1/dashboard/stats"), timeout=timeout),
        failures,
    )
    if stats_data is None:
        return blocked_or_failed(artifact, stats_step)
    stats_evidence = {
        "documents_source_ref_count": len(stats_data.get("documents", {}).get("source_refs") or []),
        "pending_action_count": len(stats_data.get("pending_actions") or []),
        "llm_report_quality_present": isinstance(stats_data.get("llm_report_quality"), dict),
    }
    stats_step["evidence"] = stats_evidence
    if stats_evidence["documents_source_ref_count"] <= 0:
        return fail_step(artifact, stats_step, failures, "dashboard_stats_missing_source_refs", ["documents.source_refs"])
    stats_step["status"] = STATUS_PASSED

    report_step = append_step(artifact, "dashboard_report_from_filter", "/api/v1/dashboard/report-from-filter")
    report_data = json_step_data(
        report_step,
        _http_post_json(
            build_url(api_base, "/api/v1/dashboard/report-from-filter"),
            dashboard_payload(project_key, smoke_id),
            timeout=timeout,
        ),
        failures,
    )
    if report_data is None:
        return blocked_or_failed(artifact, report_step)
    trace_id = str(report_data.get("trace_id") or "").strip()
    document_id = report_data.get("document_id") or report_data.get("draft_id")
    export_artifact = report_data.get("export_artifact") if isinstance(report_data.get("export_artifact"), dict) else {}
    report_evidence = {
        "trace_id": trace_id,
        "document_id": document_id,
        "source_ref_count": len(report_data.get("source_refs") or []),
        "quality_gate_status": (report_data.get("report_quality_gate") or {}).get("status") if isinstance(report_data.get("report_quality_gate"), dict) else None,
        "artifact_token_present": is_present(export_artifact.get("artifact_token")),
        "artifact_trace_id": export_artifact.get("trace_id"),
        "artifact_sha256_present": is_present(export_artifact.get("artifact_sha256")),
    }
    report_step["evidence"] = report_evidence
    artifact["evidence"].update({"trace_id": trace_id, "document_id": document_id})
    missing = [key for key in ("trace_id", "document_id") if not is_present(report_evidence[key])]
    if report_evidence["source_ref_count"] <= 0:
        missing.append("source_refs")
    if report_evidence["artifact_token_present"] is not True:
        missing.append("export_artifact.artifact_token")
    if report_evidence["artifact_trace_id"] != trace_id:
        missing.append("export_artifact.trace_id")
    if missing:
        return fail_step(artifact, report_step, failures, "dashboard_report_contract_incomplete", missing)
    report_step["status"] = STATUS_PASSED

    markdown_step = append_step(artifact, "writing_markdown_export", "/api/v1/writing/export/markdown")
    markdown_result = _http_post_markdown(
        build_url(api_base, "/api/v1/writing/export/markdown"),
        {"project_key": project_key, "doc_id": int(document_id)},
        timeout=timeout,
    )
    markdown_step["http_status"] = markdown_result.status_code
    markdown_step["error"] = markdown_result.error
    if markdown_result.status_code is None:
        markdown_step["status"] = STATUS_BLOCKED
        failures.append("writing_markdown_export:backend_unreachable")
        return blocked_or_failed(artifact, markdown_step)
    if not (200 <= int(markdown_result.status_code) < 300):
        markdown_step["status"] = STATUS_FAILED
        markdown_step["reason"] = "http_error"
        failures.append(f"writing_markdown_export:http_{markdown_result.status_code}")
        return blocked_or_failed(artifact, markdown_step)
    markdown = markdown_result.body.decode("utf-8", errors="replace")
    markdown_step["evidence"] = {
        "markdown_size_bytes": len(markdown_result.body),
        "content_disposition": markdown_result.headers.get("content-disposition"),
        "contains_dashboard_title": "Dashboard report draft" in markdown,
    }
    artifact["evidence"]["markdown_size_bytes"] = len(markdown_result.body)
    if len(markdown_result.body) <= 0 or "Dashboard report draft" not in markdown:
        return fail_step(artifact, markdown_step, failures, "markdown_export_missing_dashboard_report", ["markdown"])
    markdown_step["status"] = STATUS_PASSED

    pdf_step = append_step(artifact, "llm_report_pdf_export", "/api/v1/llm-report/export/pdf")
    pdf_result = _http_post_binary(
        build_url(api_base, "/api/v1/llm-report/export/pdf"),
        {
            "markdown": markdown,
            "project_key": project_key,
            "quality_gate": report_data.get("report_quality_gate") or {},
            "quality_gate_mode": "warn",
            "filename": f"dashboard-report-{smoke_id}.pdf",
            "artifact_token": export_artifact.get("artifact_token"),
            "artifact_sha256": export_artifact.get("artifact_sha256"),
        },
        timeout=timeout,
        accept="application/pdf",
    )
    pdf_step["http_status"] = pdf_result.status_code
    pdf_step["error"] = pdf_result.error
    if pdf_result.status_code is None:
        pdf_step["status"] = STATUS_BLOCKED
        failures.append("llm_report_pdf_export:backend_unreachable")
        return blocked_or_failed(artifact, pdf_step)
    if not (200 <= int(pdf_result.status_code) < 300):
        pdf_step["status"] = STATUS_FAILED
        pdf_step["reason"] = "http_error"
        pdf_step["response_body_preview"] = pdf_result.body.decode("utf-8", errors="replace")[:500]
        failures.append(f"llm_report_pdf_export:http_{pdf_result.status_code}")
        return blocked_or_failed(artifact, pdf_step)
    pdf_evidence = {
        "export_size_bytes": len(pdf_result.body),
        "readiness": pdf_result.headers.get("x-llm-report-export-readiness"),
        "format": pdf_result.headers.get("x-llm-report-export-format"),
        "integrity": pdf_result.headers.get("x-llm-report-export-integrity"),
        "source_trace_id": pdf_result.headers.get("x-llm-report-source-trace-id"),
        "source_ref": pdf_result.headers.get("x-llm-report-source-ref"),
    }
    pdf_step["evidence"] = pdf_evidence
    artifact["evidence"]["export_size_bytes"] = len(pdf_result.body)
    if pdf_evidence["source_trace_id"] != trace_id or pdf_evidence["readiness"] != "ready":
        return fail_step(artifact, pdf_step, failures, "pdf_export_trace_or_readiness_missing", ["source_trace_id", "readiness"])
    pdf_step["status"] = STATUS_PASSED

    detail_step = append_step(artifact, "dashboard_llm_report_detail", "/api/v1/dashboard/llm-report-detail")
    detail_data = json_step_data(
        detail_step,
        _http_get_json(
            build_url(api_base, "/api/v1/dashboard/llm-report-detail", {"trace_id": trace_id, "project_key": project_key}),
            timeout=timeout,
        ),
        failures,
    )
    if detail_data is None:
        return blocked_or_failed(artifact, detail_step)
    detail_evidence = {
        "found": detail_data.get("found") is True,
        "trace_id": detail_data.get("trace_id"),
        "source_ref_count": len(detail_data.get("source_refs") or []),
        "artifact_present": bool(detail_data.get("report_artifact") or detail_data.get("artifact")),
        "quality_gate_status": (detail_data.get("quality_gate") or {}).get("status") if isinstance(detail_data.get("quality_gate"), dict) else None,
        "export_event_count": len(detail_data.get("export_events") or []),
        "export_events_summary_total": (detail_data.get("export_events_summary") or {}).get("total") if isinstance(detail_data.get("export_events_summary"), dict) else None,
        "actionability_next_action": (detail_data.get("actionability") or {}).get("next_action") if isinstance(detail_data.get("actionability"), dict) else None,
    }
    detail_step["evidence"] = detail_evidence
    artifact["evidence"].update(
        {
            "detail_found": detail_evidence["found"],
            "detail_source_ref_count": detail_evidence["source_ref_count"],
            "detail_export_event_count": detail_evidence["export_event_count"],
            "detail_quality_gate_status": detail_evidence["quality_gate_status"],
        }
    )
    missing_detail = []
    if detail_evidence["found"] is not True:
        missing_detail.append("found")
    if detail_evidence["source_ref_count"] <= 0:
        missing_detail.append("source_refs")
    if detail_evidence["artifact_present"] is not True:
        missing_detail.append("report_artifact")
    if detail_evidence["quality_gate_status"] != "pass":
        missing_detail.append("quality_gate.status")
    if detail_evidence["export_event_count"] <= 0:
        missing_detail.append("export_events")
    if missing_detail:
        return fail_step(artifact, detail_step, failures, "dashboard_report_detail_contract_incomplete", missing_detail)
    detail_step["status"] = STATUS_PASSED

    artifact["status"] = STATUS_PASSED if not failures else STATUS_FAILED
    artifact["summary"] = build_summary(artifact)
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    api_base = args.api_base or args.base_url or "http://127.0.0.1:8000"
    output = Path(args.output)
    artifact = build_artifact(api_base=api_base, project_key=args.project_key, output=output, timeout=args.timeout)
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
