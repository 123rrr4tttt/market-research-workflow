#!/usr/bin/env python3
"""Qualify worker-required task readback manifests as real candidate evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Annotated, Any, Sequence

try:
    from scripts._automation_runtime import repo_root, utc_now
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import repo_root, utc_now


SCHEMA_VERSION = "business_line_task_readback_manifest_check.v1"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked"

REQUIRED_LINE_KEYS = (
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "writing_knowledge_graph_agent",
)

MANIFEST_CONTAINER_KEYS = (
    "items",
    "samples",
    "task_readback_samples",
    "task_readback_manifest",
    "manifest",
    "lines",
)

REQUIRED_SAMPLE_FIELDS = (
    "line_key",
    "worker_name",
    "queue",
    "trace_id",
    "status",
    "events",
)

SUCCESS_TERMINAL_STATUSES = {
    "completed",
    "succeeded",
    "applied",
    "available",
    "healthy",
}

BLOCKED_STATUSES = {
    "blocked",
    "blocked_by_environment",
}

SYNTHETIC_MARKER_PATTERN = re.compile(
    r"(^|[^a-z0-9])(synthetic|fixture|fake|mock|mocked|generated|dummy|test[-_]placeholder)([^a-z0-9]|$)",
    re.IGNORECASE,
)

MANIFEST_SYNTHETIC_FIELDS = ("manifest_kind", "source_kind", "proof_level")
SAMPLE_SYNTHETIC_FIELDS = (
    "manifest_kind",
    "source_kind",
    "proof_level",
    "task_id",
    "run_id",
    "worker_name",
    "trace_id",
    "readback_endpoint",
    "readback_path",
    "events",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Worker-required task readback manifest JSON path.")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 when the manifest file is missing or unreadable.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def normalize_line_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def normalize_status(value: object) -> str:
    return str(value).strip().lower()


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
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


def load_json_file(path: Path) -> tuple[Any | None, str | None, bool]:
    if not path.exists():
        return None, "manifest file does not exist", True
    try:
        return json.loads(path.read_text(encoding="utf-8")), None, False
    except json.JSONDecodeError as exc:
        return None, f"manifest is not valid JSON: {exc}", False
    except OSError as exc:
        return None, f"manifest could not be read: {exc}", True


def payload_roots(payload: Any) -> list[Any]:
    roots = [payload]
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        roots.append(payload["data"])
    return roots


def items_from_mapping(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line_key, value in mapping.items():
        if not isinstance(value, dict):
            continue
        item = dict(value)
        item.setdefault("line_key", line_key)
        items.append(item)
    return items


def extract_items_from_container(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    if is_present(value.get("line_key")):
        return [value]
    for key in MANIFEST_CONTAINER_KEYS:
        nested = value.get(key)
        nested_items = extract_items_from_container(nested)
        if nested_items:
            return nested_items
    return items_from_mapping(value)


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
        for key in MANIFEST_CONTAINER_KEYS:
            items = extract_items_from_container(root.get(key))
            if items:
                return items
    return []


def string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(string_values(item))
        return values
    if isinstance(value, dict):
        values = []
        for item in value.values():
            values.extend(string_values(item))
        return values
    return []


def has_synthetic_marker(value: Any) -> bool:
    return any(SYNTHETIC_MARKER_PATTERN.search(text) is not None for text in string_values(value))


def root_synthetic_marker_fields(payload: Any) -> list[str]:
    fields: list[str] = []
    for root in payload_roots(payload):
        if not isinstance(root, dict):
            continue
        for field in MANIFEST_SYNTHETIC_FIELDS:
            if field in root and has_synthetic_marker(root[field]) and field not in fields:
                fields.append(field)
    return fields


def event_terminal_status(event: Any) -> str | None:
    if isinstance(event, str):
        status = normalize_status(event)
        return status if status in SUCCESS_TERMINAL_STATUSES else None
    if not isinstance(event, dict):
        return None
    for key in ("status", "terminal_status", "event", "event_type", "name", "type"):
        if key in event:
            status = normalize_status(event[key])
            if status in SUCCESS_TERMINAL_STATUSES:
                return status
    return None


def has_terminal_event(events: Any) -> bool:
    if not isinstance(events, list):
        return False
    return any(event_terminal_status(event) is not None for event in events)


def sample_synthetic_fields(sample: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for field in SAMPLE_SYNTHETIC_FIELDS:
        if field in sample and has_synthetic_marker(sample[field]):
            fields.append(field)
    return fields


def sample_is_mocked_or_skipped(sample: dict[str, Any]) -> bool:
    mocked = normalize_bool(sample.get("mocked")) if "mocked" in sample else False
    skipped = normalize_bool(sample.get("skipped")) if "skipped" in sample else False
    return mocked is True or skipped is True


def check_sample(sample: dict[str, Any], *, global_synthetic_fields: Sequence[str]) -> dict[str, Any]:
    raw_line_key = sample.get("line_key")
    line_key = normalize_line_key(raw_line_key) if is_present(raw_line_key) else "<missing>"
    status = normalize_status(sample.get("status")) if is_present(sample.get("status")) else None
    missing_fields = [field for field in REQUIRED_SAMPLE_FIELDS if not is_present(sample.get(field))]

    if not (is_present(sample.get("task_id")) or is_present(sample.get("run_id"))):
        missing_fields.append("task_id_or_run_id")
    if not (is_present(sample.get("readback_endpoint")) or is_present(sample.get("readback_path"))):
        missing_fields.append("readback_endpoint_or_readback_path")

    violations: list[str] = []
    if status not in SUCCESS_TERMINAL_STATUSES:
        violations.append("success_status")
    if not has_terminal_event(sample.get("events")):
        violations.append("terminal_event")
    if sample_is_mocked_or_skipped(sample):
        violations.append("mocked_or_skipped")

    synthetic_fields = [*global_synthetic_fields, *sample_synthetic_fields(sample)]
    if synthetic_fields:
        violations.append("synthetic_marker")

    failures: list[str] = []
    for field in [*missing_fields, *violations]:
        if field not in failures:
            failures.append(field)

    return {
        "line_key": line_key,
        "raw_line_key": raw_line_key,
        "status": status,
        "has_task_or_run_id": is_present(sample.get("task_id")) or is_present(sample.get("run_id")),
        "has_readback_location": is_present(sample.get("readback_endpoint")) or is_present(sample.get("readback_path")),
        "has_terminal_event": has_terminal_event(sample.get("events")),
        "mocked": normalize_bool(sample.get("mocked")) if "mocked" in sample else False,
        "skipped": normalize_bool(sample.get("skipped")) if "skipped" in sample else False,
        "synthetic_fields": sorted(set(synthetic_fields)),
        "check_status": STATUS_PASSED if not failures else STATUS_FAILED,
        "missing_fields": missing_fields,
        "violations": violations,
    }


def summarize_lines(lines: Sequence[dict[str, Any]]) -> dict[str, Any]:
    expected = set(REQUIRED_LINE_KEYS)
    observed_line_keys = [line["line_key"] for line in lines if line["line_key"] != "<missing>"]
    observed_expected_keys = [line_key for line_key in observed_line_keys if line_key in expected]
    duplicate_line_keys = sorted({key for key in observed_expected_keys if observed_expected_keys.count(key) > 1})
    missing_line_keys = sorted(expected - set(observed_expected_keys))
    unexpected_line_keys = sorted({key for key in observed_line_keys if key not in expected})
    if any(line["line_key"] == "<missing>" for line in lines):
        unexpected_line_keys.insert(0, "<missing>")

    blocked_line_keys = sorted(
        {
            line["line_key"]
            for line in lines
            if line["line_key"] in expected and line["status"] in BLOCKED_STATUSES
        }
    )
    synthetic_line_keys = sorted(
        {
            line["line_key"]
            for line in lines
            if line["line_key"] in expected and line["synthetic_fields"]
        }
    )
    mocked_or_skipped_line_keys = sorted(
        {
            line["line_key"]
            for line in lines
            if line["line_key"] in expected and (line["mocked"] is True or line["skipped"] is True)
        }
    )
    terminal_event_missing_line_keys = sorted(
        {
            line["line_key"]
            for line in lines
            if line["line_key"] in expected and "terminal_event" in line["violations"]
        }
    )
    failed_line_keys = sorted(
        {
            line["line_key"]
            for line in lines
            if line["line_key"] in expected and line["check_status"] != STATUS_PASSED
        }
        | set(missing_line_keys)
        | set(duplicate_line_keys)
    )
    passed_line_keys = sorted(
        {
            line["line_key"]
            for line in lines
            if line["line_key"] in expected
            and line["line_key"] not in failed_line_keys
            and line["line_key"] not in duplicate_line_keys
            and line["check_status"] == STATUS_PASSED
        }
    )
    line_failures = {
        line["line_key"]: [*line["missing_fields"], *line["violations"]]
        for line in lines
        if line["line_key"] in expected and line["check_status"] != STATUS_PASSED
    }

    return {
        "expected_line_count": len(REQUIRED_LINE_KEYS),
        "observed_line_count": len(lines),
        "passed_line_keys": passed_line_keys,
        "qualified_line_keys": passed_line_keys,
        "failed_line_keys": failed_line_keys,
        "invalid_line_keys": failed_line_keys,
        "blocked_line_keys": blocked_line_keys,
        "missing_line_keys": missing_line_keys,
        "duplicate_line_keys": duplicate_line_keys,
        "unexpected_line_keys": unexpected_line_keys,
        "synthetic_line_keys": synthetic_line_keys,
        "mocked_or_skipped_line_keys": mocked_or_skipped_line_keys,
        "terminal_event_missing_line_keys": terminal_event_missing_line_keys,
        "line_failures": line_failures,
    }


def structural_failures(summary: dict[str, Any], lines: Sequence[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    for key in ("missing_line_keys", "duplicate_line_keys", "unexpected_line_keys"):
        if summary[key]:
            failures.append(key)
    if summary["synthetic_line_keys"]:
        failures.append("synthetic_markers")
    if summary["mocked_or_skipped_line_keys"]:
        failures.append("mocked_or_skipped_fields")
    if any("terminal_event" in line["violations"] for line in lines):
        failures.append("terminal_task_readback_evidence")
    if any(line["missing_fields"] for line in lines):
        failures.append("line_required_fields")
    if any("success_status" in line["violations"] for line in lines):
        failures.append("success_status")
    return failures


def blocked_summary() -> dict[str, Any]:
    return {
        "expected_line_count": len(REQUIRED_LINE_KEYS),
        "observed_line_count": 0,
        "passed_line_keys": [],
        "qualified_line_keys": [],
        "failed_line_keys": [],
        "invalid_line_keys": [],
        "blocked_line_keys": list(REQUIRED_LINE_KEYS),
        "missing_line_keys": list(REQUIRED_LINE_KEYS),
        "duplicate_line_keys": [],
        "unexpected_line_keys": [],
        "synthetic_line_keys": [],
        "mocked_or_skipped_line_keys": [],
        "terminal_event_missing_line_keys": [],
        "line_failures": {},
    }


def inspect_manifest(path: Path, root: Path, observed_at: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "manifest_path": relative_path(path, root),
        "absolute_path": str(path.resolve()),
        "observed_at": observed_at,
    }
    payload, load_error, input_blocked = load_json_file(path)
    if load_error is not None:
        status = STATUS_BLOCKED if input_blocked else STATUS_FAILED
        summary = blocked_summary() if input_blocked else summarize_lines([])
        row.update(
            {
                "status": status,
                "reason": "manifest_input_unavailable" if input_blocked else "manifest_json_invalid",
                "error": load_error,
                "structural_failures": [] if input_blocked else ["valid_json"],
                "expected_line_keys": list(REQUIRED_LINE_KEYS),
                "observed_line_keys": [],
                "summary": summary,
                "lines": [],
            }
        )
        return row

    assert payload is not None
    global_synthetic_fields = root_synthetic_marker_fields(payload)
    lines = [
        check_sample(item, global_synthetic_fields=global_synthetic_fields)
        for item in extract_manifest_items(payload)
    ]
    summary = summarize_lines(lines)
    failures = structural_failures(summary, lines)
    status = STATUS_PASSED if not failures and len(summary["passed_line_keys"]) == len(REQUIRED_LINE_KEYS) else STATUS_FAILED

    row.update(
        {
            "status": status,
            "reason": None,
            "error": None,
            "structural_failures": failures,
            "expected_line_keys": list(REQUIRED_LINE_KEYS),
            "observed_line_keys": sorted({line["line_key"] for line in lines if line["line_key"] != "<missing>"}),
            "summary": summary,
            "lines": lines,
        }
    )
    return row


def build_report(
    path: Path, *, root: Path | None = None, observed_at: str | None = None
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=task_readback_manifest_artifact "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    root = root or repo_root()
    observed_at = observed_at or utc_now()
    manifest = inspect_manifest(path, root, observed_at)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": manifest["status"],
        "observed_at": observed_at,
        "summary": manifest["summary"],
        "manifest": manifest,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(Path(args.manifest))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        manifest = report["manifest"]
        print(f"business_line_task_readback_manifest_check={report['status']} manifest={manifest['manifest_path']}")
    if report["status"] == STATUS_PASSED:
        return 0
    if report["status"] == STATUS_BLOCKED and args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
