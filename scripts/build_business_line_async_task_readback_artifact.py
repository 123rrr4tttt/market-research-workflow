#!/usr/bin/env python3
"""Build async task consumption/readback evidence for canonical business lines."""

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
        utc_now,
        write_json,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import (
        CANONICAL_LINE_KEYS,
        WORKER_REQUIRED_LINE_KEYS,
        utc_now,
        write_json,
    )


ARTIFACT_SCHEMA_VERSION = "business_line_async_task_readback.v1"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

SUCCESS_TERMINAL_STATUSES = ("completed", "succeeded", "applied", "available", "healthy")
WORKER_SUCCESS_TERMINAL_STATUSES = ("completed", "succeeded")

REQUIRED_LINE_KEYS = CANONICAL_LINE_KEYS


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-matrix", required=True, type=Path, help="Business-line evidence matrix JSON.")
    parser.add_argument(
        "--task-readback-samples",
        type=Path,
        help="Optional JSON file containing line-level async task readback samples.",
    )
    parser.add_argument("--output", required=True, type=Path, help="Path to write the async task readback artifact.")
    parser.add_argument("--json", action="store_true", help="Print the artifact JSON after writing.")
    return parser.parse_args(argv)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def payload_roots(payload: Any) -> list[Any]:
    roots = [payload]
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        roots.append(payload["data"])
    return roots


def normalize_line_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def normalize_status(value: object) -> str:
    return str(value).strip().lower()


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


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def extract_evidence_lines(payload: Any) -> list[dict[str, Any]]:
    for root in payload_roots(payload):
        if not isinstance(root, dict):
            continue
        lines = root.get("lines")
        if isinstance(lines, list):
            return [line for line in lines if isinstance(line, dict)]
        if isinstance(lines, dict):
            return [dict(value, line_key=key) for key, value in lines.items() if isinstance(value, dict)]
    return []


def evidence_by_line(evidence_payload: Any) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    lines: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    unexpected: list[str] = []
    for line in extract_evidence_lines(evidence_payload):
        raw_line_key = line.get("line_key")
        if not is_present(raw_line_key):
            unexpected.append("<missing>")
            continue
        line_key = normalize_line_key(raw_line_key)
        if line_key not in REQUIRED_LINE_KEYS:
            unexpected.append(line_key)
            continue
        if line_key in lines:
            duplicates.append(line_key)
            continue
        lines[line_key] = line
    return lines, sorted(set(duplicates)), sorted(set(unexpected))


def line_task_readback_contract(line: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(line, dict):
        return {}
    readback = line.get("async_task_readback")
    return readback if isinstance(readback, dict) else {}


def extract_samples(payload: Any | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [sample for sample in payload if isinstance(sample, dict)]
    for root in payload_roots(payload):
        if not isinstance(root, dict):
            continue
        for key in ("samples", "task_readback_samples", "lines", "items", "results"):
            value = root.get(key)
            if isinstance(value, list):
                return [sample for sample in value if isinstance(sample, dict)]
            if isinstance(value, dict):
                return [dict(sample, line_key=line_key) for line_key, sample in value.items() if isinstance(sample, dict)]
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


def normalize_sample(sample: dict[str, Any]) -> dict[str, Any]:
    raw_line_key = sample.get("line_key")
    status = normalize_status(sample.get("status")) if is_present(sample.get("status")) else None
    events = sample.get("events") if isinstance(sample.get("events"), list) else []
    return {
        "line_key": normalize_line_key(raw_line_key) if is_present(raw_line_key) else "<missing>",
        "task_id": sample.get("task_id"),
        "run_id": sample.get("run_id"),
        "status": status,
        "events": events,
        "worker_name": sample.get("worker_name"),
        "queue": sample.get("queue"),
        "trace_id": sample.get("trace_id"),
        "readback_path": sample.get("readback_path"),
        "readback_endpoint": sample.get("readback_endpoint"),
        "mocked": normalize_bool(sample.get("mocked")) if "mocked" in sample else False,
        "skipped": normalize_bool(sample.get("skipped")) if "skipped" in sample else False,
        "terminal_evidence": False,
    }


def samples_by_line(samples_payload: Any | None) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    by_line: dict[str, list[dict[str, Any]]] = {}
    unexpected: list[str] = []
    for raw_sample in extract_samples(samples_payload):
        sample = normalize_sample(raw_sample)
        line_key = str(sample["line_key"])
        if line_key not in REQUIRED_LINE_KEYS:
            unexpected.append(line_key)
            continue
        by_line.setdefault(line_key, []).append(sample)
    return by_line, sorted(set(unexpected))


def terminal_states(contract: dict[str, Any]) -> list[str]:
    states = contract.get("terminal_states")
    if isinstance(states, list):
        normalized = [normalize_status(state) for state in states if is_present(state)]
        if normalized:
            return normalized
    return list(SUCCESS_TERMINAL_STATUSES)


def success_terminal_states(contract: dict[str, Any]) -> list[str]:
    states = set(terminal_states(contract))
    success_states = [state for state in SUCCESS_TERMINAL_STATUSES if state in states]
    return success_states or list(SUCCESS_TERMINAL_STATUSES)


def worker_success_terminal_states() -> list[str]:
    return list(WORKER_SUCCESS_TERMINAL_STATUSES)


def sample_has_success_terminal_evidence(sample: dict[str, Any], *, success_statuses: Sequence[str]) -> bool:
    status = normalize_status(sample.get("status")) if is_present(sample.get("status")) else None
    events = sample.get("events") if isinstance(sample.get("events"), list) else []
    return status in success_statuses and has_terminal_event(events, success_statuses=success_statuses)


def sample_has_identity(sample: dict[str, Any]) -> bool:
    return is_present(sample.get("task_id")) or is_present(sample.get("run_id"))


def sample_has_readback_location(sample: dict[str, Any]) -> bool:
    return is_present(sample.get("readback_path")) or is_present(sample.get("readback_endpoint"))


def sample_has_worker_context(sample: dict[str, Any]) -> bool:
    return is_present(sample.get("worker_name")) and is_present(sample.get("queue"))


def sample_has_trace(sample: dict[str, Any]) -> bool:
    return is_present(sample.get("trace_id"))


def event_tokens(event: Any) -> set[str]:
    if isinstance(event, str):
        token = normalize_status(event)
        return {token} if token else set()
    if not isinstance(event, dict):
        return set()
    tokens: set[str] = set()
    for key in ("status", "event", "event_type", "name", "type"):
        value = event.get(key)
        if is_present(value):
            tokens.add(normalize_status(value))
    return tokens


def required_events(contract: dict[str, Any]) -> list[str]:
    events = contract.get("required_events")
    if not isinstance(events, list):
        return []
    return [normalize_status(event) for event in events if is_present(event)]


def sample_has_required_events(sample: dict[str, Any], *, required: Sequence[str]) -> bool:
    if not required:
        return False
    observed: set[str] = set()
    events = sample.get("events") if isinstance(sample.get("events"), list) else []
    for event in events:
        observed.update(event_tokens(event))
    return set(required).issubset(observed)


def sample_satisfies_worker_strict_contract(
    sample: dict[str, Any],
    *,
    required: Sequence[str],
    success_statuses: Sequence[str],
) -> bool:
    return (
        sample_has_identity(sample)
        and sample_has_readback_location(sample)
        and sample_has_worker_context(sample)
        and sample_has_trace(sample)
        and sample_has_required_events(sample, required=required)
        and sample_has_success_terminal_evidence(sample, success_statuses=success_statuses)
    )


def build_line(
    line_key: str,
    *,
    evidence_line: dict[str, Any] | None,
    samples: Sequence[dict[str, Any]],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=evidence_matrix+task_readback_samples_function_inputs "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    contract = line_task_readback_contract(evidence_line)
    contract_requires_worker_readback = (
        bool(contract.get("requires_worker_readback"))
        if "requires_worker_readback" in contract
        else None
    )
    canonical_worker_required = line_key in WORKER_REQUIRED_LINE_KEYS
    requires_worker_readback = True if canonical_worker_required else contract_requires_worker_readback
    success_statuses = worker_success_terminal_states() if canonical_worker_required else success_terminal_states(contract)
    required = required_events(contract)
    line_mocked = any(sample.get("mocked") is not False for sample in samples)
    line_skipped = any(sample.get("skipped") is not False for sample in samples)
    output_samples = [
        dict(
            sample,
            terminal_evidence=sample_has_success_terminal_evidence(sample, success_statuses=success_statuses),
        )
        for sample in samples
    ]
    terminal_samples = [sample for sample in output_samples if sample.get("terminal_evidence") is True]
    missing_identity = any(not sample_has_identity(sample) for sample in samples)
    missing_readback_location = any(not sample_has_readback_location(sample) for sample in samples)
    missing_worker_context = any(
        not sample_has_worker_context(sample) for sample in samples
    ) if requires_worker_readback is True else False
    missing_trace = any(not sample_has_trace(sample) for sample in samples) if requires_worker_readback is True else False
    missing_required_events = (
        not required
        or any(not sample_has_required_events(sample, required=required) for sample in samples)
    ) if requires_worker_readback is True else False
    has_worker_strict_sample = any(
        sample_satisfies_worker_strict_contract(
            sample,
            required=required,
            success_statuses=success_statuses,
        )
        for sample in samples
    ) if requires_worker_readback is True else bool(terminal_samples)

    if evidence_line is None:
        status = STATUS_FAILED
        reason = "missing_evidence_line"
    elif not contract:
        status = STATUS_FAILED
        reason = "missing_async_task_readback_contract"
    elif contract_requires_worker_readback is None and not canonical_worker_required:
        status = STATUS_FAILED
        reason = "missing_requires_worker_readback"
    elif canonical_worker_required and contract_requires_worker_readback is not True:
        status = STATUS_FAILED
        reason = "worker_required_flag_mismatch"
    elif line_mocked:
        status = STATUS_FAILED
        reason = "mocked_task_readback_sample"
    elif line_skipped:
        status = STATUS_FAILED
        reason = "skipped_task_readback_sample"
    elif not samples:
        status = STATUS_BLOCKED
        reason = "async_task_readback_missing"
    elif missing_identity:
        status = STATUS_FAILED
        reason = "missing_task_or_run_identity"
    elif missing_readback_location:
        status = STATUS_FAILED
        reason = "missing_readback_location"
    elif missing_worker_context:
        status = STATUS_FAILED
        reason = "missing_worker_queue_context"
    elif missing_trace:
        status = STATUS_FAILED
        reason = "missing_trace_id"
    elif missing_required_events:
        status = STATUS_FAILED
        reason = "missing_required_events"
    elif has_worker_strict_sample:
        status = STATUS_PASSED
        reason = "async_task_readback_completed" if requires_worker_readback else "process_config_audit_readback_completed"
    else:
        status = STATUS_BLOCKED
        reason = "terminal_task_readback_missing"

    return {
        "line_key": line_key,
        "status": status,
        "requires_worker_readback": requires_worker_readback,
        "mocked": line_mocked,
        "skipped": line_skipped,
        "reason": reason,
        "readback_artifact": contract.get("readback_artifact"),
        "readback_paths": contract.get("readback_paths") if isinstance(contract.get("readback_paths"), list) else [],
        "readback_endpoint": contract.get("readback_endpoint"),
        "required_events": contract.get("required_events") if isinstance(contract.get("required_events"), list) else [],
        "terminal_states": terminal_states(contract),
        "success_terminal_states": success_statuses,
        "canonical_worker_required": canonical_worker_required,
        "sample_count": len(samples),
        "terminal_sample_count": len(terminal_samples),
        "samples": output_samples,
    }


def detect_schema_version(payload: Any) -> str | None:
    for root in payload_roots(payload):
        if isinstance(root, dict) and is_present(root.get("schema_version")):
            return str(root["schema_version"])
        if isinstance(root, dict) and is_present(root.get("contract_version")):
            return str(root["contract_version"])
    return None


def build_artifact(
    evidence_matrix: Any,
    task_readback_samples: Any | None = None,
    *,
    evidence_matrix_path: Path,
    task_readback_samples_path: Path | None = None,
    observed_at: str,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=evidence_matrix+task_readback_samples_function_inputs "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    by_line, duplicate_line_keys, unexpected_line_keys = evidence_by_line(evidence_matrix)
    samples, unexpected_sample_line_keys = samples_by_line(task_readback_samples)

    lines = [
        build_line(line_key, evidence_line=by_line.get(line_key), samples=samples.get(line_key, []))
        for line_key in REQUIRED_LINE_KEYS
    ]
    missing_line_keys = [line_key for line_key in REQUIRED_LINE_KEYS if line_key not in by_line]
    requires_worker_readback_line_keys = [
        line["line_key"] for line in lines if line.get("requires_worker_readback") is True
    ]
    blocked_line_keys = [line["line_key"] for line in lines if line["status"] == STATUS_BLOCKED]
    failed_line_keys = [line["line_key"] for line in lines if line["status"] == STATUS_FAILED]
    passed_line_keys = [line["line_key"] for line in lines if line["status"] == STATUS_PASSED]

    if failed_line_keys or missing_line_keys or duplicate_line_keys or unexpected_line_keys or unexpected_sample_line_keys:
        status = STATUS_FAILED
    elif blocked_line_keys:
        status = STATUS_BLOCKED
    elif len(passed_line_keys) == len(REQUIRED_LINE_KEYS):
        status = STATUS_PASSED
    else:
        status = STATUS_FAILED

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "status": status,
        "observed_at": observed_at,
        "source": {
            "kind": "evidence_matrix_plus_task_readback_samples",
            "evidence_matrix_path": str(evidence_matrix_path),
            "task_readback_samples_path": str(task_readback_samples_path) if task_readback_samples_path else None,
            "evidence_matrix_schema_version": detect_schema_version(evidence_matrix),
            "sample_schema": {
                "required_identity": ["line_key", "task_id or run_id"],
                "supported_fields": [
                    "line_key",
                    "task_id",
                    "run_id",
                    "status",
                    "events",
                    "worker_name",
                    "queue",
                    "trace_id",
                    "readback_path",
                    "readback_endpoint",
                    "mocked",
                    "skipped",
                ],
            },
        },
        "expected_line_keys": list(REQUIRED_LINE_KEYS),
        "summary": {
            "expected_line_count": len(REQUIRED_LINE_KEYS),
            "observed_line_count": len(lines),
            "passed_line_keys": passed_line_keys,
            "blocked_line_keys": blocked_line_keys,
            "failed_line_keys": failed_line_keys,
            "requires_worker_readback_line_keys": requires_worker_readback_line_keys,
            "missing_line_keys": missing_line_keys,
            "unexpected_line_keys": unexpected_line_keys,
            "duplicate_line_keys": duplicate_line_keys,
            "unexpected_sample_line_keys": unexpected_sample_line_keys,
        },
        "lines": lines,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    evidence_matrix = load_json(args.evidence_matrix)
    task_readback_samples = load_json(args.task_readback_samples) if args.task_readback_samples else None
    artifact = build_artifact(
        evidence_matrix,
        task_readback_samples,
        evidence_matrix_path=args.evidence_matrix,
        task_readback_samples_path=args.task_readback_samples,
        observed_at=utc_now(),
    )
    write_json(args.output, artifact)
    if args.json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"business_line_async_task_readback={artifact['status']} output={args.output}")
    return 0 if artifact["status"] == STATUS_PASSED else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
