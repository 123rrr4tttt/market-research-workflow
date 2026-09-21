#!/usr/bin/env python3
"""Check Dashboard -> report closure smoke artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Sequence

try:
    from scripts._automation_runtime import utc_now, write_json
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import utc_now, write_json


ARTIFACT_SCHEMA_VERSION = "dashboard_report_closure_smoke.v1"
CHECK_SCHEMA_VERSION = "dashboard_report_closure_smoke_check.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

REQUIRED_STEPS = (
    "dashboard_stats_source_refs",
    "dashboard_report_from_filter",
    "writing_markdown_export",
    "llm_report_pdf_export",
    "dashboard_llm_report_detail",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="Dashboard report closure smoke JSON artifact path.")
    parser.add_argument("--output", type=Path, help="Path to write checker JSON.")
    parser.add_argument("--allow-blocked", action="store_true", help="Exit 0 when artifact is blocked.")
    parser.add_argument("--json", action="store_true", help="Print checker JSON.")
    return parser.parse_args(argv)


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    if isinstance(value, bool):
        return value
    return True


def as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return len(value)
    return 0


def load_artifact(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"artifact could not be read: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"artifact is not valid JSON: {exc}"


def step_by_name(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    return {str(step.get("name")): step for step in steps if isinstance(step, dict) and is_present(step.get("name"))}


def step_evidence(steps: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    evidence = steps.get(name, {}).get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def check(name: str, passed: bool, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": STATUS_PASSED if passed else STATUS_FAILED, "details": details or {}}


def build_check(path: Path, *, allow_blocked: bool = False) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=dashboard_report_closure_artifact "
    "witness=test:test_w11_non_authoritative_metadata",
]:
    payload, err = load_artifact(path)
    if err or not isinstance(payload, dict):
        return {
            "schema_version": CHECK_SCHEMA_VERSION,
            "status": STATUS_FAILED,
            "checked_at": utc_now(),
            "artifact_path": str(path),
            "checks": [],
            "failures": [err or "artifact root is not an object"],
        }
    artifact_status = str(payload.get("status") or "")
    if artifact_status == STATUS_BLOCKED:
        return {
            "schema_version": CHECK_SCHEMA_VERSION,
            "status": STATUS_BLOCKED if allow_blocked else STATUS_FAILED,
            "checked_at": utc_now(),
            "artifact_path": str(path),
            "artifact_schema_version": payload.get("schema_version"),
            "artifact_status": artifact_status,
            "checks": [check("artifact.blocked_by_environment", allow_blocked)],
            "failures": [] if allow_blocked else ["artifact_status_blocked_by_environment"],
        }

    steps = step_by_name(payload)
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    checks: list[dict[str, Any]] = [
        check("artifact.schema_version", payload.get("schema_version") == ARTIFACT_SCHEMA_VERSION),
        check("artifact.status", artifact_status == STATUS_PASSED, {"actual": artifact_status}),
    ]
    for name in REQUIRED_STEPS:
        step = steps.get(name)
        missing = []
        if not isinstance(step, dict):
            checks.append(check(f"step.{name}", False, {"missing_fields": ["step"]}))
            continue
        for field in ("name", "path", "http_status", "status", "evidence"):
            if field not in step:
                missing.append(field)
        if step.get("status") != STATUS_PASSED:
            missing.append("status:passed")
        checks.append(check(f"step.{name}", not missing, {"missing_fields": missing}))

    report = step_evidence(steps, "dashboard_report_from_filter")
    trace_id = report.get("trace_id") or evidence.get("trace_id")
    checks.append(check("report.trace_id", is_present(trace_id), {"trace_id": trace_id}))
    checks.append(
        check(
            "report.export_artifact_trace",
            is_present(trace_id) and report.get("artifact_trace_id") == trace_id,
            {"trace_id": trace_id, "artifact_trace_id": report.get("artifact_trace_id")},
        )
    )
    checks.append(check("report.source_refs", as_int(report.get("source_ref_count")) > 0, {"source_ref_count": report.get("source_ref_count")}))
    checks.append(check("report.artifact_token", report.get("artifact_token_present") is True))

    markdown = step_evidence(steps, "writing_markdown_export")
    checks.append(
        check(
            "markdown.exported_dashboard_report",
            as_int(markdown.get("markdown_size_bytes")) > 0 and markdown.get("contains_dashboard_title") is True,
            markdown,
        )
    )

    pdf = step_evidence(steps, "llm_report_pdf_export")
    checks.append(
        check(
            "pdf.source_trace_readback",
            is_present(trace_id) and pdf.get("source_trace_id") == trace_id and pdf.get("readiness") == "ready",
            {"source_trace_id": pdf.get("source_trace_id"), "readiness": pdf.get("readiness")},
        )
    )

    detail = step_evidence(steps, "dashboard_llm_report_detail")
    checks.append(check("detail.found", detail.get("found") is True, {"found": detail.get("found")}))
    checks.append(check("detail.source_refs", as_int(detail.get("source_ref_count")) > 0, {"source_ref_count": detail.get("source_ref_count")}))
    checks.append(check("detail.artifact", detail.get("artifact_present") is True))
    checks.append(check("detail.quality_gate", detail.get("quality_gate_status") == "pass", {"quality_gate_status": detail.get("quality_gate_status")}))
    checks.append(check("detail.export_events", as_int(detail.get("export_event_count")) > 0, {"export_event_count": detail.get("export_event_count")}))

    failures = [item["name"] for item in checks if item["status"] != STATUS_PASSED]
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "status": STATUS_PASSED if not failures else STATUS_FAILED,
        "checked_at": utc_now(),
        "artifact_path": str(path),
        "artifact_schema_version": payload.get("schema_version"),
        "artifact_status": artifact_status,
        "checks": checks,
        "failures": failures,
        "summary": {
            "check_count": len(checks),
            "passed_check_count": sum(1 for item in checks if item["status"] == STATUS_PASSED),
            "failed_check_count": len(failures),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_check(Path(args.artifact), allow_blocked=args.allow_blocked)
    if args.output:
        write_json(args.output, result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"dashboard_report_closure_smoke_check={result['status']} artifact={args.artifact}")
    if result["status"] == STATUS_PASSED:
        return 0
    if args.allow_blocked and result["status"] == STATUS_BLOCKED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
