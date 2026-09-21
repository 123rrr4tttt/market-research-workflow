#!/usr/bin/env python3
"""Check live business-line trace baseline JSON artifacts offline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Sequence

try:
    from scripts._automation_runtime import utc_now
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import utc_now


ARTIFACT_SCHEMA_VERSION = "business_line_trace_baseline_live.v1"
CHECK_SCHEMA_VERSION = "business_line_trace_baseline_check.v1"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"
TRACE_NOT_APPLICABLE = "not_applicable"

REQUIRED_LINE_KEYS = (
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "projects_config_workflow",
    "dashboard_admin_governance",
    "writing_knowledge_graph_agent",
    "runtime_ops",
)
BODY_META_TRACE_EXEMPT_PROBE_PATHS = frozenset(("/api/v1/health", "/api/v1/health/deep"))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Trace baseline live artifact path.")
    parser.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON.")
    return parser.parse_args(argv)


def load_artifact(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"artifact could not be read: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"artifact is not valid JSON: {exc}"


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_number(value: Any) -> bool:
    return (isinstance(value, int | float) and not isinstance(value, bool))


def normalize_probe_path(value: Any) -> str:
    if not is_non_empty_string(value):
        return ""
    stripped = value.strip()
    return stripped if stripped.startswith("/") else f"/{stripped}"


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
    if not isinstance(payload, dict):
        return []
    value = payload.get("lines")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return line_items_from_mapping(value)
    return []


def failure(reason: str, *, line_key: str | None = None, detail: Any = None) -> dict[str, Any]:
    item: dict[str, Any] = {"reason": reason}
    if line_key is not None:
        item["line_key"] = line_key
    if detail is not None:
        item["detail"] = detail
    return item


def check_matrix(payload: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    matrix = payload.get("matrix")
    if not isinstance(matrix, dict):
        return [failure("matrix")]

    if matrix.get("status") != STATUS_PASSED:
        failures.append(failure("matrix_status", detail=matrix.get("status")))
    trace_id = matrix.get("trace_id")
    if not is_non_empty_string(trace_id):
        failures.append(failure("matrix_trace_id"))
    if matrix.get("header_trace_id") != trace_id:
        failures.append(
            failure(
                "matrix_header_trace_id",
                detail={"expected": trace_id, "observed": matrix.get("header_trace_id")},
            )
        )
    if matrix.get("body_meta_trace_status") != STATUS_PASSED:
        failures.append(failure("matrix_body_meta_trace_status", detail=matrix.get("body_meta_trace_status")))
    if matrix.get("failures"):
        failures.append(failure("matrix_failures", detail=matrix.get("failures")))
    return failures


def body_meta_trace_valid(line: dict[str, Any], line_key: str) -> tuple[bool, dict[str, Any] | None]:
    status = line.get("body_meta_trace_status")
    if status == STATUS_PASSED:
        return True, None
    if status != TRACE_NOT_APPLICABLE:
        return False, failure("body_meta_trace_status", line_key=line_key, detail=status)

    probe_path = normalize_probe_path(line.get("probe_path"))
    if probe_path in BODY_META_TRACE_EXEMPT_PROBE_PATHS:
        return True, None
    return False, failure(
        "body_meta_trace_not_applicable_for_non_exempt_path",
        line_key=line_key,
        detail={"probe_path": probe_path, "allowed_paths": sorted(BODY_META_TRACE_EXEMPT_PROBE_PATHS)},
    )


def check_line(line: dict[str, Any]) -> dict[str, Any]:
    line_key = str(line.get("line_key") or "").strip()
    failures: list[dict[str, Any]] = []
    if not line_key:
        line_key = "<missing>"
        failures.append(failure("line_key", line_key=line_key))

    if line.get("status") != STATUS_PASSED:
        failures.append(failure("line_status", line_key=line_key, detail=line.get("status")))

    trace_id = line.get("trace_id")
    if not is_non_empty_string(trace_id):
        failures.append(failure("trace_id", line_key=line_key))
    if line.get("header_trace_id") != trace_id:
        failures.append(
            failure(
                "header_trace_id",
                line_key=line_key,
                detail={"expected": trace_id, "observed": line.get("header_trace_id")},
            )
        )
    if line.get("header_request_id") != trace_id:
        failures.append(
            failure(
                "header_request_id",
                line_key=line_key,
                detail={"expected": trace_id, "observed": line.get("header_request_id")},
            )
        )

    _body_valid, body_failure = body_meta_trace_valid(line, line_key)
    if body_failure is not None:
        failures.append(body_failure)

    if line.get("missing_data_paths"):
        failures.append(failure("required_data_paths", line_key=line_key, detail=line.get("missing_data_paths")))
    if not isinstance(line.get("required_data_paths"), list):
        failures.append(failure("required_data_paths_field", line_key=line_key))

    if not is_number(line.get("duration_ms")):
        failures.append(failure("duration_ms", line_key=line_key, detail=line.get("duration_ms")))

    if line.get("failures"):
        failures.append(failure("line_failures", line_key=line_key, detail=line.get("failures")))

    return {
        "line_key": line_key,
        "status": STATUS_PASSED if not failures else STATUS_FAILED,
        "probe_path": normalize_probe_path(line.get("probe_path")),
        "failures": failures,
    }


def build_report(artifact_path: Path) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=trace_baseline_artifact "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    observed_at = utc_now()
    payload, load_error = load_artifact(artifact_path)
    failures: list[dict[str, Any]] = []
    line_checks: list[dict[str, Any]] = []

    if load_error is not None:
        failures.append(failure("valid_json", detail=load_error))
        return {
            "schema_version": CHECK_SCHEMA_VERSION,
            "status": STATUS_FAILED,
            "observed_at": observed_at,
            "artifact_path": str(artifact_path),
            "checked_line_keys": [],
            "failures": failures,
            "summary": {"expected_line_count": len(REQUIRED_LINE_KEYS), "checked_line_count": 0},
        }

    if not isinstance(payload, dict):
        failures.append(failure("artifact_object"))
        payload = {}

    if payload.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        failures.append(failure("schema_version", detail=payload.get("schema_version")))
    if payload.get("status") != STATUS_PASSED:
        failures.append(failure("artifact_status", detail=payload.get("status")))

    failures.extend(check_matrix(payload))

    lines = extract_lines(payload)
    line_checks = [check_line(line) for line in lines]
    observed_line_keys = [line["line_key"] for line in line_checks if line["line_key"] != "<missing>"]
    observed_line_key_set = set(observed_line_keys)
    expected_line_key_set = set(REQUIRED_LINE_KEYS)
    missing_line_keys = sorted(expected_line_key_set - observed_line_key_set)
    unexpected_line_keys = sorted(observed_line_key_set - expected_line_key_set)
    duplicate_line_keys = sorted(
        line_key for line_key in observed_line_key_set if observed_line_keys.count(line_key) > 1
    )
    failed_line_keys = sorted(
        {
            line["line_key"]
            for line in line_checks
            if line["line_key"] != "<missing>" and line["status"] != STATUS_PASSED
        }
    )

    if not lines:
        failures.append(failure("lines"))
    if missing_line_keys:
        failures.append(failure("missing_line_keys", detail=missing_line_keys))
    if unexpected_line_keys:
        failures.append(failure("unexpected_line_keys", detail=unexpected_line_keys))
    if duplicate_line_keys:
        failures.append(failure("duplicate_line_keys", detail=duplicate_line_keys))
    for line in line_checks:
        failures.extend(line["failures"])

    checked_line_keys = sorted(observed_line_key_set & expected_line_key_set)
    status = STATUS_PASSED if not failures else STATUS_FAILED
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "status": status,
        "observed_at": observed_at,
        "artifact_path": str(artifact_path),
        "artifact_schema_version": payload.get("schema_version"),
        "expected_artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "checked_line_keys": checked_line_keys,
        "failures": failures,
        "summary": {
            "expected_line_count": len(REQUIRED_LINE_KEYS),
            "observed_line_count": len(observed_line_key_set),
            "checked_line_count": len(checked_line_keys),
            "missing_line_keys": missing_line_keys,
            "unexpected_line_keys": unexpected_line_keys,
            "duplicate_line_keys": duplicate_line_keys,
            "failed_line_keys": failed_line_keys,
            "body_meta_trace_exempt_probe_paths": sorted(BODY_META_TRACE_EXEMPT_PROBE_PATHS),
        },
        "lines": sorted(line_checks, key=lambda item: item["line_key"]),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args.input)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == STATUS_PASSED else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
