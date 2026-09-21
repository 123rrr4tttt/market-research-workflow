#!/usr/bin/env python3
"""Check business-line user-flow smoke JSON artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Sequence

try:
    from scripts._automation_runtime import repo_root, utc_now
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import repo_root, utc_now


ARTIFACT_SCHEMA_VERSION = "business_line_user_flow_smoke.v1"
CHECK_SCHEMA_VERSION = "business_line_user_flow_smoke_check.v1"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"
STATUS_FEEDBACK_READBACK_MISSING = "feedback_readback_missing"
LINE_STATUS_PASSED = "passed_contract_reachable"
RESPONSE_ASSERTION_PASSED = "passed"
RESPONSE_ASSERTION_FAILED = "failed"
RESPONSE_ASSERTION_NOT_DECLARED = "not_declared"
RESPONSE_ASSERTION_SKIPPED_BLOCKED = "skipped_blocked"
RESPONSE_ASSERTION_NOT_RUN = "not_run"

REQUIRED_LINE_KEYS = (
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "projects_config_workflow",
    "dashboard_admin_governance",
    "writing_knowledge_graph_agent",
    "runtime_ops",
)
REQUIRED_LINE_FIELDS = ("probe_path", "status", "proof_level", "response_assertion_status")
REQUIRED_FEEDBACK_FIELDS = ("submission_id", "task_id", "trace_id")
REQUIRED_FEEDBACK_READBACK_FIELDS = ("submission_id", "task_id", "status", "trace_id")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="Business-line user-flow smoke JSON artifact path.")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 when the artifact is blocked by environment, while still failing failed states.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


def normalize_line_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    if isinstance(value, bool):
        return value
    return True


def relative_artifact_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def load_artifact(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"artifact could not be read: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"artifact is not valid JSON: {exc}"


def payload_roots(payload: Any) -> list[Any]:
    roots = [payload]
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        roots.append(payload["data"])
    return roots


def detect_schema_version(payload: Any) -> str | None:
    for root in payload_roots(payload):
        if isinstance(root, dict) and is_present(root.get("schema_version")):
            return str(root["schema_version"])
    return None


def detect_artifact_status(payload: Any) -> str | None:
    for root in payload_roots(payload):
        if isinstance(root, dict) and is_present(root.get("status")):
            return str(root["status"])
    return None


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
        for key in ("lines", "business_lines", "items", "user_flows", "results"):
            value = root.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return line_items_from_mapping(value)
    return []


def extract_feedback_loop(payload: Any) -> dict[str, Any] | None:
    for root in payload_roots(payload):
        if isinstance(root, dict) and isinstance(root.get("feedback_loop"), dict):
            return root["feedback_loop"]
    return None


def normalize_status(value: object) -> str:
    return str(value).strip().lower()


def response_assertion_failures(
    response_assertion_status: str | None,
    artifact_status: str | None,
) -> list[str]:
    if response_assertion_status is None:
        return ["response_assertion_status"]
    if artifact_status == STATUS_BLOCKED:
        allowed_statuses = {
            RESPONSE_ASSERTION_PASSED,
            RESPONSE_ASSERTION_FAILED,
            RESPONSE_ASSERTION_NOT_DECLARED,
            RESPONSE_ASSERTION_SKIPPED_BLOCKED,
            RESPONSE_ASSERTION_NOT_RUN,
        }
        return [] if response_assertion_status in allowed_statuses else ["valid_response_assertion_status"]
    if response_assertion_status == RESPONSE_ASSERTION_PASSED:
        return []
    return ["valid_response_assertion_status"]


def response_assertion_missing_for_summary(
    response_assertion_status: str | None,
    artifact_status: str | None,
) -> bool:
    if response_assertion_status is None or response_assertion_status == RESPONSE_ASSERTION_NOT_DECLARED:
        return True
    if artifact_status == STATUS_PASSED and response_assertion_status in {
        RESPONSE_ASSERTION_SKIPPED_BLOCKED,
        RESPONSE_ASSERTION_NOT_RUN,
    }:
        return True
    return False


def check_line(line: dict[str, Any], *, artifact_status: str | None) -> dict[str, Any]:
    raw_line_key = line.get("line_key")
    line_key = normalize_line_key(raw_line_key) if is_present(raw_line_key) else "<missing>"
    missing_fields = [field for field in REQUIRED_LINE_FIELDS if not is_present(line.get(field))]
    if not is_present(raw_line_key):
        missing_fields.insert(0, "line_key")

    status = normalize_status(line.get("status")) if is_present(line.get("status")) else None
    allowed_line_statuses = {LINE_STATUS_PASSED, STATUS_BLOCKED}
    if artifact_status == STATUS_PASSED:
        allowed_line_statuses = {LINE_STATUS_PASSED}
    invalid_status = status not in allowed_line_statuses
    if invalid_status:
        missing_fields.append("valid_status")

    response_assertion_status = (
        normalize_status(line.get("response_assertion_status"))
        if is_present(line.get("response_assertion_status"))
        else None
    )
    for failure in response_assertion_failures(response_assertion_status, artifact_status):
        if failure not in missing_fields:
            missing_fields.append(failure)

    return {
        "line_key": line_key,
        "raw_line_key": raw_line_key,
        "status": status,
        "response_assertion_status": response_assertion_status,
        "check_status": STATUS_PASSED if not missing_fields else STATUS_FAILED,
        "missing_fields": missing_fields,
        "required_status": LINE_STATUS_PASSED,
        "allowed_blocked_status": STATUS_BLOCKED,
        "required_response_assertion_status": RESPONSE_ASSERTION_PASSED,
        "allowed_blocked_response_assertion_statuses": [
            RESPONSE_ASSERTION_SKIPPED_BLOCKED,
            RESPONSE_ASSERTION_NOT_RUN,
        ],
    }


def check_feedback_loop(feedback_loop: dict[str, Any] | None, *, artifact_status: str | None) -> dict[str, Any]:
    if feedback_loop is None:
        return {
            "status": STATUS_FAILED,
            "raw_status": None,
            "submission_id": None,
            "task_id": None,
            "trace_id": None,
            "failures": ["feedback_loop"],
            "missing_fields": ["feedback_loop"],
            "readback": {},
        }

    raw_status = normalize_status(feedback_loop.get("status")) if is_present(feedback_loop.get("status")) else None
    readback = feedback_loop.get("readback") if isinstance(feedback_loop.get("readback"), dict) else {}
    missing_fields = [field for field in REQUIRED_FEEDBACK_FIELDS if not is_present(feedback_loop.get(field))]
    readback_missing_fields = [
        field
        for field in REQUIRED_FEEDBACK_READBACK_FIELDS
        if not is_present(readback.get(field))
    ]
    reported_readback_missing = [
        str(field).strip()
        for field in (readback.get("missing_fields") if isinstance(readback.get("missing_fields"), list) else [])
        if str(field).strip()
    ]
    mismatched_fields = [
        str(field).strip()
        for field in (readback.get("mismatched_fields") if isinstance(readback.get("mismatched_fields"), list) else [])
        if str(field).strip()
    ]
    failures = [
        str(failure).strip()
        for failure in (feedback_loop.get("failures") if isinstance(feedback_loop.get("failures"), list) else [])
        if str(failure).strip()
    ]

    if artifact_status == STATUS_BLOCKED:
        allowed_statuses = {STATUS_BLOCKED}
        invalid_status = raw_status not in allowed_statuses
        return {
            "status": STATUS_PASSED if not invalid_status else STATUS_FAILED,
            "raw_status": raw_status,
            "submission_id": feedback_loop.get("submission_id"),
            "task_id": feedback_loop.get("task_id"),
            "trace_id": feedback_loop.get("trace_id"),
            "failures": failures + (["valid_feedback_loop_status"] if invalid_status else []),
            "missing_fields": [],
            "readback_missing_fields": reported_readback_missing,
            "mismatched_fields": mismatched_fields,
            "readback": readback,
        }

    if raw_status == STATUS_FEEDBACK_READBACK_MISSING:
        return {
            "status": STATUS_FEEDBACK_READBACK_MISSING,
            "raw_status": raw_status,
            "submission_id": feedback_loop.get("submission_id"),
            "task_id": feedback_loop.get("task_id"),
            "trace_id": feedback_loop.get("trace_id"),
            "failures": failures or ["feedback_readback_missing"],
            "missing_fields": missing_fields,
            "readback_missing_fields": sorted(set(readback_missing_fields + reported_readback_missing)),
            "mismatched_fields": mismatched_fields,
            "readback": readback,
        }

    invalid_status = raw_status != STATUS_PASSED
    readback_not_matched = readback.get("matched") is not True
    if invalid_status:
        failures.append("valid_feedback_loop_status")
    if readback_not_matched:
        failures.append("feedback_history_missing_submission")
    if readback_missing_fields:
        failures.append("feedback_history_missing_fields")
    if mismatched_fields:
        failures.append("feedback_history_mismatched_fields")

    deduped_failures = sorted(set(failures))
    return {
        "status": STATUS_PASSED if not deduped_failures and not missing_fields else STATUS_FAILED,
        "raw_status": raw_status,
        "submission_id": feedback_loop.get("submission_id"),
        "task_id": feedback_loop.get("task_id"),
        "trace_id": feedback_loop.get("trace_id"),
        "failures": deduped_failures,
        "missing_fields": missing_fields,
        "readback_missing_fields": sorted(set(readback_missing_fields + reported_readback_missing)),
        "mismatched_fields": mismatched_fields,
        "readback": readback,
    }


def classify_status(
    *,
    artifact_status: str | None,
    line_checks: Sequence[dict[str, Any]],
    feedback_loop_check: dict[str, Any],
    structural_failures: Sequence[str],
) -> str:
    if structural_failures:
        if feedback_loop_check.get("status") == STATUS_FEEDBACK_READBACK_MISSING:
            return STATUS_FEEDBACK_READBACK_MISSING
        return STATUS_FAILED
    if artifact_status not in {STATUS_PASSED, STATUS_BLOCKED, STATUS_FEEDBACK_READBACK_MISSING}:
        return STATUS_FAILED
    if artifact_status == STATUS_BLOCKED:
        return STATUS_BLOCKED
    if artifact_status == STATUS_FEEDBACK_READBACK_MISSING:
        return STATUS_FEEDBACK_READBACK_MISSING

    line_statuses = [line.get("status") for line in line_checks]
    if any(status != LINE_STATUS_PASSED for status in line_statuses):
        return STATUS_FAILED
    if any(line.get("check_status") != STATUS_PASSED for line in line_checks):
        return STATUS_FAILED
    if feedback_loop_check.get("status") != STATUS_PASSED:
        if feedback_loop_check.get("status") == STATUS_FEEDBACK_READBACK_MISSING:
            return STATUS_FEEDBACK_READBACK_MISSING
        return STATUS_FAILED
    return STATUS_PASSED


def inspect_artifact(path: Path, root: Path, observed_at: str) -> dict[str, Any]:
    artifact_path = relative_artifact_path(path, root)
    row: dict[str, Any] = {
        "artifact_path": artifact_path,
        "absolute_path": str(path.resolve()),
        "observed_at": observed_at,
    }
    if not path.exists():
        row.update(
            {
                "status": STATUS_FAILED,
                "artifact_status": None,
                "schema_version": None,
                "structural_failures": ["artifact_file"],
                "lines": [],
            }
        )
        return row

    payload, error = load_artifact(path)
    if error is not None:
        row.update(
            {
                "status": STATUS_FAILED,
                "artifact_status": None,
                "schema_version": None,
                "reason": error,
                "structural_failures": ["valid_json"],
                "lines": [],
            }
        )
        return row

    schema_version = detect_schema_version(payload)
    artifact_status = detect_artifact_status(payload)
    lines = [check_line(line, artifact_status=artifact_status) for line in extract_lines(payload)]
    feedback_loop = extract_feedback_loop(payload)
    feedback_loop_check = check_feedback_loop(feedback_loop, artifact_status=artifact_status)
    observed_line_keys = [line["line_key"] for line in lines if line["line_key"] != "<missing>"]
    expected_line_keys = set(REQUIRED_LINE_KEYS)
    observed_line_key_set = set(observed_line_keys)
    duplicate_line_keys = sorted(
        line_key for line_key in observed_line_key_set if observed_line_keys.count(line_key) > 1
    )
    missing_line_keys = sorted(expected_line_keys - observed_line_key_set)
    unexpected_line_keys = sorted(observed_line_key_set - expected_line_keys)
    incomplete_line_keys = sorted(
        {
            line["line_key"]
            for line in lines
            if line["line_key"] != "<missing>" and line["check_status"] == STATUS_FAILED
        }
    )
    response_assertion_failed_line_keys = sorted(
        {
            line["line_key"]
            for line in lines
            if line["line_key"] != "<missing>"
            and line.get("response_assertion_status") == RESPONSE_ASSERTION_FAILED
        }
    )
    response_assertion_missing_line_keys = sorted(
        {
            line["line_key"]
            for line in lines
            if line["line_key"] != "<missing>"
            and response_assertion_missing_for_summary(
                line.get("response_assertion_status"),
                artifact_status,
            )
        }
    )
    feedback_failures = list(feedback_loop_check.get("failures") or [])

    structural_failures: list[str] = []
    if schema_version != ARTIFACT_SCHEMA_VERSION:
        structural_failures.append("schema_version")
    if artifact_status is None:
        structural_failures.append("artifact_status")
    if not lines:
        structural_failures.append("lines")
    if missing_line_keys:
        structural_failures.append("missing_line_keys")
    if unexpected_line_keys:
        structural_failures.append("unexpected_line_keys")
    if duplicate_line_keys:
        structural_failures.append("duplicate_line_keys")
    if incomplete_line_keys:
        structural_failures.append("line_contract_fields")
    if feedback_loop_check.get("status") != STATUS_PASSED:
        structural_failures.append("feedback_loop")

    status = classify_status(
        artifact_status=artifact_status,
        line_checks=lines,
        feedback_loop_check=feedback_loop_check,
        structural_failures=structural_failures,
    )
    row.update(
        {
            "status": status,
            "artifact_status": artifact_status,
            "schema_version": schema_version,
            "expected_schema_version": ARTIFACT_SCHEMA_VERSION,
            "structural_failures": structural_failures,
            "summary": {
                "expected_line_count": len(REQUIRED_LINE_KEYS),
                "observed_line_count": len(observed_line_key_set),
                "missing_line_keys": missing_line_keys,
                "unexpected_line_keys": unexpected_line_keys,
                "duplicate_line_keys": duplicate_line_keys,
                "incomplete_line_keys": incomplete_line_keys,
                "response_assertion_failed_line_keys": response_assertion_failed_line_keys,
                "response_assertion_missing_line_keys": response_assertion_missing_line_keys,
                "feedback_loop_status": feedback_loop_check.get("raw_status"),
                "feedback_loop_failures": feedback_failures,
                "submission_id": feedback_loop_check.get("submission_id"),
                "task_id": feedback_loop_check.get("task_id"),
                "trace_id": feedback_loop_check.get("trace_id"),
                "required_line_fields": list(REQUIRED_LINE_FIELDS),
                "required_feedback_fields": list(REQUIRED_FEEDBACK_FIELDS),
                "required_feedback_readback_fields": list(REQUIRED_FEEDBACK_READBACK_FIELDS),
            },
            "feedback_loop": feedback_loop_check,
            "expected_line_keys": list(REQUIRED_LINE_KEYS),
            "observed_line_keys": sorted(observed_line_key_set),
            "lines": lines,
        }
    )
    return row


def build_report(
    artifact_path: str | Path, root: Path | None = None
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=user_flow_smoke_artifact "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    resolved_root = root.resolve() if root else repo_root()
    observed_at = utc_now()
    artifact = inspect_artifact(Path(artifact_path), resolved_root, observed_at)
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "status": artifact["status"],
        "observed_at": observed_at,
        "summary": artifact.get("summary") or {},
        "failures": artifact.get("structural_failures") or [],
        "evidence": {
            "submission_id": (artifact.get("summary") or {}).get("submission_id"),
            "task_id": (artifact.get("summary") or {}).get("task_id"),
            "trace_id": (artifact.get("summary") or {}).get("trace_id"),
        },
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "line_status_required": LINE_STATUS_PASSED,
        "line_status_allowed_blocked": STATUS_BLOCKED,
        "response_assertion_status_required": RESPONSE_ASSERTION_PASSED,
        "response_assertion_status_allowed_blocked": [
            RESPONSE_ASSERTION_SKIPPED_BLOCKED,
            RESPONSE_ASSERTION_NOT_RUN,
        ],
        "artifact": artifact,
        "recommended_command": (
            "python3 scripts/check_business_line_user_flow_smoke_artifact.py "
            "<artifact.json> [--allow-blocked] [--json]"
        ),
    }


def print_human(report: dict[str, Any]) -> None:
    artifact = report["artifact"]
    if report["status"] == STATUS_PASSED:
        print("OK business-line user-flow smoke artifact passed")
        return
    if report["status"] == STATUS_BLOCKED:
        print("BLOCKED business-line user-flow smoke artifact is environment-blocked")
        return

    print("FAILED business-line user-flow smoke artifact")
    failures = artifact.get("structural_failures") or ["unknown"]
    print(f"- {artifact['artifact_path']}: failures={', '.join(failures)}")
    summary = artifact.get("summary") or {}
    for key in (
        "missing_line_keys",
        "unexpected_line_keys",
        "duplicate_line_keys",
        "incomplete_line_keys",
        "response_assertion_failed_line_keys",
        "response_assertion_missing_line_keys",
    ):
        values = summary.get(key) or []
        if values:
            print(f"- {key}: {', '.join(values)}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args.artifact)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human(report)
    if report["status"] == STATUS_PASSED:
        return 0
    if args.allow_blocked and report["status"] == STATUS_BLOCKED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
