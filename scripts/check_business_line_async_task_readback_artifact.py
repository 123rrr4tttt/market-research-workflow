#!/usr/bin/env python3
"""Check async task consumption/readback artifacts for canonical business lines."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Sequence

try:
    from scripts._automation_runtime import (
        CANONICAL_LINE_KEYS,
        WORKER_REQUIRED_LINE_KEYS,
        repo_root,
        utc_now,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import (
        CANONICAL_LINE_KEYS,
        WORKER_REQUIRED_LINE_KEYS,
        repo_root,
        utc_now,
    )


ARTIFACT_SCHEMA_VERSION = "business_line_async_task_readback.v1"
CHECK_SCHEMA_VERSION = "business_line_async_task_readback_check.v1"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

SUCCESS_TERMINAL_STATUSES = ("completed", "succeeded", "applied", "available", "healthy")
WORKER_SUCCESS_TERMINAL_STATUSES = ("completed", "succeeded")

REQUIRED_LINE_KEYS = CANONICAL_LINE_KEYS

MANIFEST_CONTAINER_KEYS = (
    "items",
    "samples",
    "task_readback_samples",
    "task_readback_manifest",
    "manifest",
    "lines",
)

REQUIRED_LINE_FIELDS = ("line_key", "status", "requires_worker_readback", "mocked", "skipped")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="Business-line async task readback JSON artifact path.")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 when the artifact is blocked by environment, while failed remains non-zero.",
    )
    parser.add_argument(
        "--task-readback-manifest",
        help="Optional worker-required task readback manifest used to validate passed artifact samples.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


def normalize_line_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def normalize_status(value: object) -> str:
    return str(value).strip().lower()


def normalize_scalar(value: object) -> str:
    return str(value).strip()


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


def load_manifest(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, "manifest file does not exist"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"manifest could not be read: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"manifest is not valid JSON: {exc}"


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


def manifest_items_from_mapping(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line_key, value in mapping.items():
        if not isinstance(value, dict):
            continue
        item = dict(value)
        item.setdefault("line_key", line_key)
        items.append(item)
    return items


def extract_manifest_items_from_container(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    if is_present(value.get("line_key")):
        return [value]
    for key in MANIFEST_CONTAINER_KEYS:
        nested_items = extract_manifest_items_from_container(value.get(key))
        if nested_items:
            return nested_items
    return manifest_items_from_mapping(value)


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
            items = extract_manifest_items_from_container(root.get(key))
            if items:
                return items
    return []


def event_terminal_status(event: Any, *, success_statuses: Sequence[str]) -> str | None:
    if isinstance(event, str):
        status = normalize_status(event)
        return status if status in success_statuses else None
    if not isinstance(event, dict):
        return None
    for key in ("status", "event", "event_type", "name", "type"):
        if key in event and normalize_status(event[key]) in success_statuses:
            return normalize_status(event[key])
    return None


def has_terminal_event(events: Any, *, success_statuses: Sequence[str]) -> bool:
    if not isinstance(events, list):
        return False
    return any(event_terminal_status(event, success_statuses=success_statuses) is not None for event in events)


def line_success_terminal_statuses(line: dict[str, Any]) -> list[str]:
    states = line.get("success_terminal_states")
    if isinstance(states, list):
        normalized = [normalize_status(state) for state in states if is_present(state)]
        if normalized:
            return normalized
    states = line.get("terminal_states")
    if isinstance(states, list):
        normalized = [normalize_status(state) for state in states if is_present(state)]
        success = [state for state in SUCCESS_TERMINAL_STATUSES if state in normalized]
        if success:
            return success
    return list(SUCCESS_TERMINAL_STATUSES)


def sample_has_terminal_evidence(sample: Any, *, success_statuses: Sequence[str]) -> bool:
    if not isinstance(sample, dict):
        return False
    status = normalize_status(sample.get("status")) if is_present(sample.get("status")) else None
    return status in success_statuses and has_terminal_event(sample.get("events"), success_statuses=success_statuses)


def sample_has_worker_identity(sample: Any) -> bool:
    return isinstance(sample, dict) and (is_present(sample.get("task_id")) or is_present(sample.get("run_id")))


def sample_has_worker_context(sample: Any) -> bool:
    return isinstance(sample, dict) and is_present(sample.get("worker_name")) and is_present(sample.get("queue"))


def sample_has_worker_name(sample: Any) -> bool:
    return isinstance(sample, dict) and is_present(sample.get("worker_name"))


def sample_has_worker_queue(sample: Any) -> bool:
    return isinstance(sample, dict) and is_present(sample.get("queue"))


def sample_has_worker_trace(sample: Any) -> bool:
    return isinstance(sample, dict) and is_present(sample.get("trace_id"))


def sample_has_readback_location(sample: Any) -> bool:
    return isinstance(sample, dict) and (
        is_present(sample.get("readback_path")) or is_present(sample.get("readback_endpoint"))
    )


def event_tokens(event: Any) -> set[str]:
    if isinstance(event, str):
        token = normalize_status(event)
        return {token} if token else set()
    if not isinstance(event, dict):
        return set()
    tokens: set[str] = set()
    for key in ("status", "event", "event_type", "name", "type"):
        if key in event and is_present(event[key]):
            tokens.add(normalize_status(event[key]))
    return tokens


def sample_event_tokens(sample: Any) -> set[str]:
    if not isinstance(sample, dict) or not isinstance(sample.get("events"), list):
        return set()
    tokens: set[str] = set()
    for event in sample["events"]:
        tokens.update(event_tokens(event))
    return tokens


def line_required_events(line: dict[str, Any]) -> list[str]:
    events = line.get("required_events")
    if not isinstance(events, list):
        return []
    return [normalize_status(event) for event in events if is_present(event)]


def sample_has_required_events(sample: Any, *, required_events: Sequence[str]) -> bool:
    if not required_events:
        return False
    return set(required_events).issubset(sample_event_tokens(sample))


def scalar_field_matches(sample: dict[str, Any], manifest: dict[str, Any], field: str) -> bool:
    if not is_present(sample.get(field)) or not is_present(manifest.get(field)):
        return False
    return normalize_scalar(sample[field]) == normalize_scalar(manifest[field])


def status_field_matches(sample: dict[str, Any], manifest: dict[str, Any]) -> bool:
    if not is_present(sample.get("status")) or not is_present(manifest.get("status")):
        return False
    return normalize_status(sample["status"]) == normalize_status(manifest["status"])


def identity_matches_manifest(sample: dict[str, Any], manifest: dict[str, Any]) -> bool:
    matched = False
    for field in ("task_id", "run_id"):
        sample_has_field = is_present(sample.get(field))
        manifest_has_field = is_present(manifest.get(field))
        if sample_has_field and manifest_has_field:
            if normalize_scalar(sample[field]) != normalize_scalar(manifest[field]):
                return False
            matched = True
    return matched


def readback_location_matches_manifest(sample: dict[str, Any], manifest: dict[str, Any]) -> bool:
    matched = False
    for field in ("readback_endpoint", "readback_path"):
        sample_has_field = is_present(sample.get(field))
        manifest_has_field = is_present(manifest.get(field))
        if sample_has_field and manifest_has_field:
            if normalize_scalar(sample[field]) != normalize_scalar(manifest[field]):
                return False
            matched = True

    sample_locations = {
        normalize_scalar(sample[field])
        for field in ("readback_endpoint", "readback_path")
        if is_present(sample.get(field))
    }
    manifest_locations = {
        normalize_scalar(manifest[field])
        for field in ("readback_endpoint", "readback_path")
        if is_present(manifest.get(field))
    }
    return matched or bool(sample_locations & manifest_locations)


def manifest_reference_samples(manifest_item: dict[str, Any]) -> list[dict[str, Any]]:
    nested: list[dict[str, Any]] = []
    for key in MANIFEST_CONTAINER_KEYS:
        value = manifest_item.get(key)
        if isinstance(value, list):
            nested.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            nested.extend(extract_manifest_items_from_container(value))

    useful_nested = [
        item
        for item in nested
        if any(is_present(item.get(field)) for field in ("task_id", "run_id", "status", "events"))
    ]
    if useful_nested:
        return useful_nested
    return [manifest_item]


def manifest_event_tokens(manifest: dict[str, Any]) -> set[str]:
    tokens = sample_event_tokens(manifest)
    if tokens:
        return tokens
    events = manifest.get("required_events")
    if isinstance(events, list):
        return {normalize_status(event) for event in events if is_present(event)}
    return set()


def events_cover_manifest(sample: dict[str, Any], manifest: dict[str, Any]) -> bool:
    expected = manifest_event_tokens(manifest)
    if not expected:
        return False
    return sample_event_tokens(sample) == expected


def manifest_sample_consistency(sample: dict[str, Any], manifest: dict[str, Any]) -> dict[str, bool]:
    return {
        "identity": identity_matches_manifest(sample, manifest),
        "worker": scalar_field_matches(sample, manifest, "worker_name"),
        "queue": scalar_field_matches(sample, manifest, "queue"),
        "trace": scalar_field_matches(sample, manifest, "trace_id"),
        "readback_location": readback_location_matches_manifest(sample, manifest),
        "status": status_field_matches(sample, manifest),
        "events": events_cover_manifest(sample, manifest),
    }


def manifest_consistency_result(
    terminal_samples: Sequence[Any],
    manifest_item: dict[str, Any] | None,
) -> dict[str, Any]:
    categories = (
        "identity",
        "worker",
        "queue",
        "trace",
        "readback_location",
        "status",
        "events",
    )
    if manifest_item is None:
        return {
            "ok": False,
            "missing": True,
            "checks": {category: False for category in categories},
        }

    comparable_samples = [sample for sample in terminal_samples if isinstance(sample, dict)]
    manifest_samples = manifest_reference_samples(manifest_item)
    per_category = {category: False for category in categories}
    for sample in comparable_samples:
        for manifest_sample in manifest_samples:
            checks = manifest_sample_consistency(sample, manifest_sample)
            for category, ok in checks.items():
                per_category[category] = per_category[category] or ok
            if all(checks.values()):
                return {"ok": True, "missing": False, "checks": {category: True for category in categories}}

    return {"ok": False, "missing": False, "checks": per_category}


def build_manifest_index(payload: Any) -> Annotated[
    tuple[dict[str, dict[str, Any]], list[str], list[str]],
    "kit:non-authoritative derived_as=view "
    "fact_source=task_readback_artifact_payload "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    index: dict[str, dict[str, Any]] = {}
    observed: list[str] = []
    duplicate: list[str] = []
    for item in extract_manifest_items(payload):
        if not is_present(item.get("line_key")):
            continue
        line_key = normalize_line_key(item["line_key"])
        observed.append(line_key)
        if line_key in index:
            duplicate.append(line_key)
            continue
        index[line_key] = item
    return index, sorted(set(observed)), sorted(set(duplicate))


def inspect_manifest_input(path: Path, root: Path) -> dict[str, Any]:
    payload, error = load_manifest(path)
    row: dict[str, Any] = {
        "manifest_path": relative_artifact_path(path, root),
        "absolute_path": str(path.resolve()),
        "status": STATUS_FAILED if error else STATUS_PASSED,
        "error": error,
        "observed_line_keys": [],
        "duplicate_line_keys": [],
        "index": {},
    }
    if error is not None:
        return row
    assert payload is not None
    index, observed, duplicate = build_manifest_index(payload)
    row.update(
        {
            "observed_line_keys": observed,
            "duplicate_line_keys": duplicate,
            "index": index,
        }
    )
    return row


def sample_is_mocked_or_skipped(sample: Any) -> bool:
    if not isinstance(sample, dict):
        return False
    mocked = normalize_bool(sample.get("mocked")) if "mocked" in sample else False
    skipped = normalize_bool(sample.get("skipped")) if "skipped" in sample else False
    return mocked is not False or skipped is not False


def check_line(
    line: dict[str, Any],
    *,
    artifact_status: str | None,
    manifest_item: dict[str, Any] | None = None,
    manifest_consistency_required: bool = False,
) -> dict[str, Any]:
    raw_line_key = line.get("line_key")
    line_key = normalize_line_key(raw_line_key) if is_present(raw_line_key) else "<missing>"
    status = normalize_status(line.get("status")) if is_present(line.get("status")) else None
    requires_worker_readback = (
        line.get("requires_worker_readback") if isinstance(line.get("requires_worker_readback"), bool) else None
    )
    canonical_worker_required = line_key in WORKER_REQUIRED_LINE_KEYS
    mocked = normalize_bool(line.get("mocked")) if "mocked" in line else None
    skipped = normalize_bool(line.get("skipped")) if "skipped" in line else None
    samples = line.get("samples") if isinstance(line.get("samples"), list) else []
    success_statuses = (
        list(WORKER_SUCCESS_TERMINAL_STATUSES)
        if canonical_worker_required
        else line_success_terminal_statuses(line)
    )
    terminal_evidence = any(
        sample_has_terminal_evidence(sample, success_statuses=success_statuses) for sample in samples
    )
    terminal_samples = [
        sample for sample in samples if sample_has_terminal_evidence(sample, success_statuses=success_statuses)
    ]
    worker_strict_required = canonical_worker_required and status == STATUS_PASSED
    required_events = line_required_events(line)
    worker_identity = (
        any(sample_has_worker_identity(sample) for sample in terminal_samples) if worker_strict_required else None
    )
    worker_name = any(sample_has_worker_name(sample) for sample in terminal_samples) if worker_strict_required else None
    worker_queue = any(sample_has_worker_queue(sample) for sample in terminal_samples) if worker_strict_required else None
    worker_context = (
        any(sample_has_worker_context(sample) for sample in terminal_samples) if worker_strict_required else None
    )
    worker_trace = any(sample_has_worker_trace(sample) for sample in terminal_samples) if worker_strict_required else None
    worker_readback_location = (
        any(sample_has_readback_location(sample) for sample in terminal_samples) if worker_strict_required else None
    )
    worker_required_events = (
        any(sample_has_required_events(sample, required_events=required_events) for sample in terminal_samples)
        if worker_strict_required
        else None
    )
    worker_strict_contract = (
        any(
            sample_has_worker_identity(sample)
            and sample_has_worker_context(sample)
            and sample_has_worker_trace(sample)
            and sample_has_readback_location(sample)
            and sample_has_required_events(sample, required_events=required_events)
            for sample in terminal_samples
        )
        if worker_strict_required
        else None
    )
    manifest_consistency = (
        manifest_consistency_result(terminal_samples, manifest_item)
        if manifest_consistency_required and canonical_worker_required and status == STATUS_PASSED
        else None
    )
    sample_mocked_or_skipped = any(sample_is_mocked_or_skipped(sample) for sample in samples)

    missing_fields = [field for field in REQUIRED_LINE_FIELDS if field not in line or line[field] is None]
    if not is_present(raw_line_key) and "line_key" not in missing_fields:
        missing_fields.insert(0, "line_key")
    if not is_present(line.get("status")) and "status" not in missing_fields:
        missing_fields.append("status")

    violations: list[str] = []
    if status == STATUS_FAILED:
        violations.append("failed_status")
    if mocked is not False:
        violations.append("not_mocked")
    if skipped is not False:
        violations.append("not_skipped")
    if sample_mocked_or_skipped:
        violations.append("sample_mocked_or_skipped")
    if canonical_worker_required and requires_worker_readback is not True:
        violations.append("worker_required_flag_mismatch")

    if artifact_status == STATUS_PASSED:
        if status != STATUS_PASSED:
            violations.append("passed_artifact_requires_passed_lines")
        if not samples:
            violations.append("readback_sample_required")
        if not terminal_evidence:
            violations.append("terminal_task_readback_evidence")
    elif artifact_status == STATUS_BLOCKED:
        if status not in {STATUS_PASSED, STATUS_BLOCKED, None}:
            violations.append("valid_blocked_line_status")
        if status == STATUS_PASSED and not terminal_evidence:
            violations.append("passed_line_requires_terminal_readback")
    elif artifact_status == STATUS_FAILED:
        violations.append("failed_artifact_status")
    else:
        violations.append("valid_artifact_status")

    if worker_strict_required:
        if not required_events:
            violations.append("required_events_missing")
        if worker_identity is not True:
            violations.append("worker_identity_missing")
        if worker_name is not True or worker_queue is not True:
            violations.append("worker_context_missing")
        if worker_trace is not True:
            violations.append("worker_trace_missing")
        if worker_readback_location is not True:
            violations.append("worker_readback_location_missing")
        if worker_required_events is not True:
            violations.append("required_events_missing")
        if worker_strict_contract is not True:
            violations.append("worker_strict_contract")

    if manifest_consistency is not None:
        checks = manifest_consistency["checks"]
        if manifest_consistency["missing"]:
            violations.append("manifest_missing")
        if checks["identity"] is not True:
            violations.append("manifest_identity_mismatch")
        if checks["worker"] is not True:
            violations.append("manifest_worker_mismatch")
        if checks["queue"] is not True:
            violations.append("manifest_queue_mismatch")
        if checks["trace"] is not True:
            violations.append("manifest_trace_mismatch")
        if checks["readback_location"] is not True:
            violations.append("manifest_readback_location_mismatch")
        if checks["status"] is not True:
            violations.append("manifest_status_mismatch")
        if checks["events"] is not True:
            violations.append("manifest_events_mismatch")
        if manifest_consistency["ok"] is not True:
            violations.append("manifest_consistency_mismatch")

    line_failures = []
    for field in [*missing_fields, *violations]:
        if field not in line_failures:
            line_failures.append(field)

    return {
        "line_key": line_key,
        "raw_line_key": raw_line_key,
        "status": status,
        "requires_worker_readback": requires_worker_readback,
        "canonical_worker_required": canonical_worker_required,
        "mocked": mocked,
        "skipped": skipped,
        "sample_count": len(samples),
        "terminal_evidence": terminal_evidence,
        "worker_identity": worker_identity,
        "worker_name": worker_name,
        "worker_queue": worker_queue,
        "worker_context": worker_context,
        "worker_trace": worker_trace,
        "worker_readback_location": worker_readback_location,
        "worker_required_events": worker_required_events,
        "worker_strict_contract": worker_strict_contract,
        "manifest_consistency": manifest_consistency,
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


def inspect_artifact(
    path: Path,
    root: Path,
    observed_at: str,
    *,
    task_readback_manifest: Path | None = None,
) -> dict[str, Any]:
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
    manifest_input = inspect_manifest_input(task_readback_manifest, root) if task_readback_manifest else None
    manifest_index: dict[str, dict[str, Any]] = {}
    if manifest_input is not None and manifest_input["status"] == STATUS_PASSED:
        manifest_index = manifest_input["index"]
    manifest_consistency_required = manifest_input is not None and artifact_status == STATUS_PASSED
    lines = [
        check_line(
            line,
            artifact_status=artifact_status,
            manifest_item=manifest_index.get(normalize_line_key(line.get("line_key"))) if is_present(line.get("line_key")) else None,
            manifest_consistency_required=manifest_consistency_required,
        )
        for line in extract_lines(payload)
    ]

    observed_line_keys = [line["line_key"] for line in lines if line["line_key"] != "<missing>"]
    expected_line_keys = set(REQUIRED_LINE_KEYS)
    observed_line_key_set = set(observed_line_keys)
    duplicate_line_keys = sorted(
        line_key for line_key in observed_line_key_set if observed_line_keys.count(line_key) > 1
    )
    missing_line_keys = sorted(expected_line_keys - observed_line_key_set)
    unexpected_line_keys = sorted(observed_line_key_set - expected_line_keys)
    requires_worker_readback_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["requires_worker_readback"] is True and line["line_key"] in expected_line_keys
    )
    canonical_worker_required_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["canonical_worker_required"] is True and line["line_key"] in expected_line_keys
    )
    worker_required_flag_mismatch_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and "worker_required_flag_mismatch" in line["violations"]
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
        if line["line_key"] in expected_line_keys and (line["mocked"] is not False or line["skipped"] is not False)
    )
    terminal_evidence_missing_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys
        and artifact_status == STATUS_PASSED
        and line["terminal_evidence"] is not True
    )
    sample_missing_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys
        and artifact_status == STATUS_PASSED
        and line["sample_count"] == 0
    )
    worker_identity_missing_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and line["worker_identity"] is False
    )
    worker_context_missing_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and line["worker_context"] is False
    )
    worker_name_missing_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and line["worker_name"] is False
    )
    worker_queue_missing_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and line["worker_queue"] is False
    )
    worker_trace_missing_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and line["worker_trace"] is False
    )
    worker_readback_location_missing_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and line["worker_readback_location"] is False
    )
    required_events_missing_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and line["worker_required_events"] is False
    )
    manifest_missing_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and "manifest_missing" in line["violations"]
    )
    manifest_identity_mismatch_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and "manifest_identity_mismatch" in line["violations"]
    )
    manifest_worker_mismatch_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and "manifest_worker_mismatch" in line["violations"]
    )
    manifest_queue_mismatch_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and "manifest_queue_mismatch" in line["violations"]
    )
    manifest_trace_mismatch_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and "manifest_trace_mismatch" in line["violations"]
    )
    manifest_readback_location_mismatch_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and "manifest_readback_location_mismatch" in line["violations"]
    )
    manifest_status_mismatch_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and "manifest_status_mismatch" in line["violations"]
    )
    manifest_events_mismatch_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and "manifest_events_mismatch" in line["violations"]
    )
    manifest_consistency_mismatch_line_keys = sorted(
        line["line_key"]
        for line in lines
        if line["line_key"] in expected_line_keys and "manifest_consistency_mismatch" in line["violations"]
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
    if worker_required_flag_mismatch_line_keys:
        structural_failures.append("worker_required_flag_mismatch")
    if terminal_evidence_missing_line_keys:
        structural_failures.append("terminal_task_readback_evidence")
    if sample_missing_line_keys:
        structural_failures.append("readback_sample_required")
    if worker_identity_missing_line_keys:
        structural_failures.append("worker_identity_missing")
        structural_failures.append("worker_readback_identity")
    if worker_context_missing_line_keys:
        structural_failures.append("worker_context_missing")
    if worker_name_missing_line_keys:
        structural_failures.append("worker_readback_worker_name")
    if worker_queue_missing_line_keys:
        structural_failures.append("worker_readback_queue")
    if worker_trace_missing_line_keys:
        structural_failures.append("worker_trace_missing")
        structural_failures.append("worker_readback_trace_id")
    if worker_readback_location_missing_line_keys:
        structural_failures.append("worker_readback_location_missing")
        structural_failures.append("worker_readback_location")
    if required_events_missing_line_keys:
        structural_failures.append("required_events_missing")
        structural_failures.append("worker_readback_required_events")
    if manifest_input is not None and artifact_status == STATUS_PASSED:
        if manifest_input["status"] != STATUS_PASSED:
            structural_failures.append("task_readback_manifest")
            structural_failures.append("task_readback_manifest_available")
        if manifest_input.get("duplicate_line_keys"):
            structural_failures.append("task_readback_manifest_duplicate_line_keys")
    if manifest_missing_line_keys:
        structural_failures.append("manifest_missing_line_keys")
        structural_failures.append("task_readback_manifest_missing_line")
    if manifest_identity_mismatch_line_keys:
        structural_failures.append("manifest_identity_mismatch")
        structural_failures.append("task_readback_manifest_identity_mismatch")
    if manifest_worker_mismatch_line_keys:
        structural_failures.append("manifest_worker_mismatch")
        structural_failures.append("task_readback_manifest_worker_name_mismatch")
    if manifest_queue_mismatch_line_keys:
        structural_failures.append("manifest_queue_mismatch")
        structural_failures.append("task_readback_manifest_queue_mismatch")
    if manifest_trace_mismatch_line_keys:
        structural_failures.append("manifest_trace_mismatch")
        structural_failures.append("task_readback_manifest_trace_mismatch")
    if manifest_readback_location_mismatch_line_keys:
        structural_failures.append("manifest_readback_location_mismatch")
        structural_failures.append("task_readback_manifest_readback_location_mismatch")
    if manifest_status_mismatch_line_keys:
        structural_failures.append("manifest_status_mismatch")
        structural_failures.append("task_readback_manifest_status_mismatch")
    if manifest_events_mismatch_line_keys:
        structural_failures.append("manifest_events_mismatch")
        structural_failures.append("task_readback_manifest_events_mismatch")
    if manifest_consistency_mismatch_line_keys:
        structural_failures.append("manifest_consistency_mismatch")
    if incomplete_line_keys:
        structural_failures.append("line_async_task_readback_fields")

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
                "requires_worker_readback_line_keys": requires_worker_readback_line_keys,
                "canonical_worker_required_line_keys": canonical_worker_required_line_keys,
                "worker_required_flag_mismatch_line_keys": worker_required_flag_mismatch_line_keys,
                "mocked_or_skipped_line_keys": mocked_or_skipped_line_keys,
                "terminal_evidence_missing_line_keys": terminal_evidence_missing_line_keys,
                "sample_missing_line_keys": sample_missing_line_keys,
                "worker_identity_missing_line_keys": worker_identity_missing_line_keys,
                "worker_context_missing_line_keys": worker_context_missing_line_keys,
                "worker_name_missing_line_keys": worker_name_missing_line_keys,
                "worker_queue_missing_line_keys": worker_queue_missing_line_keys,
                "worker_trace_missing_line_keys": worker_trace_missing_line_keys,
                "worker_readback_location_missing_line_keys": worker_readback_location_missing_line_keys,
                "required_events_missing_line_keys": required_events_missing_line_keys,
                "manifest_missing_line_keys": manifest_missing_line_keys,
                "manifest_identity_mismatch_line_keys": manifest_identity_mismatch_line_keys,
                "manifest_worker_mismatch_line_keys": manifest_worker_mismatch_line_keys,
                "manifest_worker_name_mismatch_line_keys": manifest_worker_mismatch_line_keys,
                "manifest_queue_mismatch_line_keys": manifest_queue_mismatch_line_keys,
                "manifest_trace_mismatch_line_keys": manifest_trace_mismatch_line_keys,
                "manifest_readback_location_mismatch_line_keys": manifest_readback_location_mismatch_line_keys,
                "manifest_status_mismatch_line_keys": manifest_status_mismatch_line_keys,
                "manifest_events_mismatch_line_keys": manifest_events_mismatch_line_keys,
                "manifest_consistency_mismatch_line_keys": manifest_consistency_mismatch_line_keys,
                "incomplete_line_keys": incomplete_line_keys,
            },
            "lines": lines,
        }
    )
    if manifest_input is not None:
        row["task_readback_manifest"] = {
            key: value for key, value in manifest_input.items() if key != "index"
        }
    return row


def build_report(
    path: Path,
    *,
    root: Path | None = None,
    observed_at: str | None = None,
    task_readback_manifest: Path | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=async_task_readback_artifacts "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    root = root or repo_root()
    observed_at = observed_at or utc_now()
    artifact = inspect_artifact(path, root, observed_at, task_readback_manifest=task_readback_manifest)
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "status": artifact["status"],
        "observed_at": observed_at,
        "artifact": artifact,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        Path(args.artifact),
        task_readback_manifest=Path(args.task_readback_manifest) if args.task_readback_manifest else None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        artifact = report["artifact"]
        print(
            "business_line_async_task_readback_check="
            f"{report['status']} artifact={artifact['artifact_path']}"
        )
    if report["status"] == STATUS_PASSED:
        return 0
    if report["status"] == STATUS_BLOCKED and args.allow_blocked:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
