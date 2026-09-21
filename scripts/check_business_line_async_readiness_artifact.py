#!/usr/bin/env python3
"""Check async/worker readiness artifacts for canonical business lines."""

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


ARTIFACT_SCHEMA_VERSION = "business_line_async_readiness.v1"
CHECK_SCHEMA_VERSION = "business_line_async_readiness_check.v1"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

REQUIRED_LINE_KEYS = (
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "projects_config_workflow",
    "dashboard_admin_governance",
    "writing_knowledge_graph_agent",
    "runtime_ops",
)

REQUIRED_LINE_FIELDS = ("line_key", "status", "requires_worker")
REQUIRED_WORKER_LINE_FIELDS = ("mocked", "skipped")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="Business-line async readiness JSON artifact path.")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 when the artifact is blocked by environment, while failed remains non-zero.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


def normalize_line_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def normalize_status(value: object) -> str:
    return str(value).strip().lower()


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


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
            return normalize_status(root["status"])
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
        for key in ("lines", "business_lines", "items", "results", "user_flows"):
            value = root.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return line_items_from_mapping(value)
    return []


def check_line(line: dict[str, Any], *, artifact_status: str | None) -> dict[str, Any]:
    raw_line_key = line.get("line_key")
    line_key = normalize_line_key(raw_line_key) if is_present(raw_line_key) else "<missing>"
    status = normalize_status(line.get("status")) if is_present(line.get("status")) else None
    requires_worker = line.get("requires_worker") if isinstance(line.get("requires_worker"), bool) else None
    mocked = normalize_bool(line.get("mocked")) if "mocked" in line else None
    skipped = normalize_bool(line.get("skipped")) if "skipped" in line else None

    missing_fields = [field for field in REQUIRED_LINE_FIELDS if field not in line or line[field] is None]
    if requires_worker is True:
        missing_fields.extend(field for field in REQUIRED_WORKER_LINE_FIELDS if field not in line or line[field] is None)
    if not is_present(raw_line_key) and "line_key" not in missing_fields:
        missing_fields.insert(0, "line_key")
    if not is_present(line.get("status")) and "status" not in missing_fields:
        missing_fields.append("status")

    violations: list[str] = []
    if status == STATUS_FAILED:
        violations.append("failed_status")
    if artifact_status == STATUS_PASSED:
        if requires_worker is True and status != STATUS_PASSED:
            violations.append("requires_worker_status_passed")
        if requires_worker is True and mocked is not False:
            violations.append("not_mocked")
        if requires_worker is True and skipped is not False:
            violations.append("not_skipped")
        if requires_worker is False and status != STATUS_PASSED:
            violations.append("non_worker_status_passed")
    elif artifact_status == STATUS_BLOCKED:
        if requires_worker is True:
            if status not in {STATUS_PASSED, STATUS_BLOCKED, None}:
                violations.append("valid_blocked_worker_status")
            if mocked is not False:
                violations.append("not_mocked")
            if skipped is not False:
                violations.append("not_skipped")
        elif requires_worker is False and status not in {STATUS_PASSED, None}:
            violations.append("valid_non_worker_status")
    else:
        violations.append("valid_artifact_status")

    line_failures = []
    for field in [*missing_fields, *violations]:
        if field not in line_failures:
            line_failures.append(field)

    return {
        "line_key": line_key,
        "raw_line_key": raw_line_key,
        "status": status,
        "requires_worker": requires_worker,
        "mocked": mocked,
        "skipped": skipped,
        "check_status": STATUS_PASSED if not line_failures else STATUS_FAILED,
        "missing_fields": missing_fields,
        "violations": violations,
    }


def classify_status(
    *,
    artifact_status: str | None,
    structural_failures: Sequence[str],
    failed_line_keys: Sequence[str],
    incomplete_line_keys: Sequence[str],
) -> str:
    if structural_failures or failed_line_keys or incomplete_line_keys:
        return STATUS_FAILED
    if artifact_status == STATUS_BLOCKED:
        return STATUS_BLOCKED
    if artifact_status == STATUS_PASSED:
        return STATUS_PASSED
    return STATUS_FAILED


def inspect_artifact(path: Path, root: Path, observed_at: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "artifact_path": relative_artifact_path(path, root),
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

    observed_line_keys = [line["line_key"] for line in lines if line["line_key"] != "<missing>"]
    expected_line_keys = set(REQUIRED_LINE_KEYS)
    observed_line_key_set = set(observed_line_keys)
    duplicate_line_keys = sorted(
        line_key for line_key in observed_line_key_set if observed_line_keys.count(line_key) > 1
    )
    missing_line_keys = sorted(expected_line_keys - observed_line_key_set)
    unexpected_line_keys = sorted(observed_line_key_set - expected_line_keys)
    requires_worker_line_keys = sorted(
        line["line_key"] for line in lines if line["requires_worker"] is True and line["line_key"] in expected_line_keys
    )
    blocked_line_keys = sorted(
        line["line_key"] for line in lines if line["status"] == STATUS_BLOCKED and line["line_key"] in expected_line_keys
    )
    failed_line_keys = sorted(
        line["line_key"] for line in lines if line["status"] == STATUS_FAILED and line["line_key"] in expected_line_keys
    )
    mocked_or_skipped_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["requires_worker"] is True
        and line["line_key"] in expected_line_keys
        and (line["mocked"] is not False or line["skipped"] is not False)
    )
    incomplete_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and line["check_status"] != STATUS_PASSED
    )

    structural_failures: list[str] = []
    if schema_version != ARTIFACT_SCHEMA_VERSION:
        structural_failures.append("schema_version")
    if artifact_status not in {STATUS_PASSED, STATUS_BLOCKED, STATUS_FAILED}:
        structural_failures.append("artifact_status")
    if artifact_status == STATUS_FAILED:
        structural_failures.append("failed_artifact_status")
    if missing_line_keys:
        structural_failures.append("missing_line_keys")
    if unexpected_line_keys:
        structural_failures.append("unexpected_line_keys")
    if duplicate_line_keys:
        structural_failures.append("duplicate_line_keys")
    if mocked_or_skipped_line_keys:
        structural_failures.append("line_mocked_or_skipped_fields")
    if incomplete_line_keys:
        structural_failures.append("line_async_readiness_fields")

    status = classify_status(
        artifact_status=artifact_status,
        structural_failures=structural_failures,
        failed_line_keys=failed_line_keys,
        incomplete_line_keys=incomplete_line_keys,
    )

    row.update(
        {
            "status": status,
            "artifact_status": artifact_status,
            "schema_version": schema_version,
            "structural_failures": structural_failures,
            "observed_line_keys": sorted(observed_line_key_set),
            "expected_line_keys": list(REQUIRED_LINE_KEYS),
            "summary": {
                "expected_line_count": len(REQUIRED_LINE_KEYS),
                "observed_line_count": len(lines),
                "missing_line_keys": missing_line_keys,
                "unexpected_line_keys": unexpected_line_keys,
                "duplicate_line_keys": duplicate_line_keys,
                "blocked_line_keys": blocked_line_keys,
                "failed_line_keys": failed_line_keys,
                "requires_worker_line_keys": requires_worker_line_keys,
                "mocked_or_skipped_line_keys": mocked_or_skipped_line_keys,
                "incomplete_line_keys": incomplete_line_keys,
            },
            "lines": lines,
        }
    )
    return row


def build_report(
    path: Path, *, root: Path | None = None, observed_at: str | None = None
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=async_readiness_artifact "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    root = root or repo_root()
    observed_at = observed_at or utc_now()
    artifact = inspect_artifact(path, root, observed_at)
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "status": artifact["status"],
        "observed_at": observed_at,
        "artifact": artifact,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(Path(args.artifact))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        artifact = report["artifact"]
        print(
            "business_line_async_readiness_check="
            f"{report['status']} artifact={artifact['artifact_path']}"
        )
    if report["status"] == STATUS_PASSED:
        return 0
    if report["status"] == STATUS_BLOCKED and args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
