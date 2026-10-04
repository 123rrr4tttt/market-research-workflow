#!/usr/bin/env python3
"""Build async/worker readiness evidence for canonical business lines."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Sequence

try:
    from scripts._automation_runtime import CANONICAL_LINE_KEYS, utc_now, write_json
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import CANONICAL_LINE_KEYS, utc_now, write_json


ARTIFACT_SCHEMA_VERSION = "business_line_async_readiness.v1"

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked_by_environment"

REQUIRED_LINE_KEYS = CANONICAL_LINE_KEYS


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-matrix", required=True, type=Path, help="Business-line evidence matrix JSON.")
    parser.add_argument("--runtime-matrix", required=True, type=Path, help="runtime_health_matrix.py JSON output.")
    parser.add_argument("--output", required=True, type=Path, help="Path to write the async readiness artifact.")
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


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
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


def extract_runtime_modes(payload: Any) -> list[dict[str, Any]]:
    for root in payload_roots(payload):
        if isinstance(root, dict) and isinstance(root.get("runtime_modes"), list):
            return [mode for mode in root["runtime_modes"] if isinstance(mode, dict)]
    return []


def local_runtime_mode(runtime_payload: Any) -> dict[str, Any] | None:
    for mode in extract_runtime_modes(runtime_payload):
        if str(mode.get("mode") or "").strip().lower() == "local":
            return mode
    return None


def local_worker_probe(local_mode: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(local_mode, dict):
        return None
    checks = local_mode.get("checked_async_readiness")
    if not isinstance(checks, list):
        return None
    for check in checks:
        if isinstance(check, dict) and str(check.get("check_id") or "") == "celery_worker_process_stats":
            return check
    for check in checks:
        if isinstance(check, dict):
            return check
    return None


def classify_worker_readiness(runtime_payload: Any) -> dict[str, Any]:
    local_mode = local_runtime_mode(runtime_payload)
    if local_mode is None:
        return {
            "status": STATUS_FAILED,
            "reason": "missing_local_runtime_mode",
            "runtime_mode": None,
            "worker_probe": None,
        }

    mode_status = normalize_status(local_mode.get("status")) if is_present(local_mode.get("status")) else None
    worker_probe = local_worker_probe(local_mode)
    worker_status = normalize_status(worker_probe.get("status")) if isinstance(worker_probe, dict) else None
    worker_reason = str(worker_probe.get("reason") or "").strip() if isinstance(worker_probe, dict) else ""

    if worker_status == STATUS_PASSED or (worker_probe is None and mode_status == STATUS_PASSED):
        status = STATUS_PASSED
        reason = "local_worker_readiness_passed"
    elif mode_status == "worker_blocked" or worker_reason == "celery_worker_unavailable":
        status = STATUS_BLOCKED
        reason = worker_reason or "worker_blocked"
    elif worker_status == STATUS_BLOCKED:
        status = STATUS_BLOCKED
        reason = worker_reason or "worker_blocked"
    elif worker_status == STATUS_FAILED or mode_status == STATUS_FAILED:
        status = STATUS_FAILED
        reason = worker_reason or "worker_readiness_failed"
    else:
        status = STATUS_FAILED
        reason = "missing_worker_readiness_probe"

    return {
        "status": status,
        "reason": reason,
        "runtime_mode": {
            "mode": "local",
            "status": mode_status,
        },
        "worker_probe": worker_probe,
    }


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


def line_async_readiness(line: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(line, dict):
        return {}
    readiness = line.get("async_execution_readiness")
    return readiness if isinstance(readiness, dict) else {}


def build_line(
    line_key: str,
    *,
    evidence_line: dict[str, Any] | None,
    worker_readiness: dict[str, Any],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=evidence_matrix_function_input "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    readiness = line_async_readiness(evidence_line)
    requires_worker = bool(readiness.get("requires_worker")) if "requires_worker" in readiness else None
    async_surfaces = readiness.get("async_surfaces") if isinstance(readiness.get("async_surfaces"), list) else []
    verification_artifact = readiness.get("verification_artifact")

    if evidence_line is None:
        status = STATUS_FAILED
        reason = "missing_evidence_line"
    elif requires_worker is None:
        status = STATUS_FAILED
        reason = "missing_requires_worker"
    elif requires_worker:
        status = str(worker_readiness["status"])
        reason = str(worker_readiness["reason"])
    else:
        status = STATUS_PASSED
        reason = "sync_or_read_only_async_not_required"

    return {
        "line_key": line_key,
        "status": status,
        "requires_worker": requires_worker,
        "mocked": False,
        "skipped": False,
        "reason": reason,
        "async_surfaces": async_surfaces,
        "verification_artifact": verification_artifact,
        "runtime_mode": worker_readiness.get("runtime_mode"),
        "worker_probe": worker_readiness.get("worker_probe") if requires_worker else None,
    }


def build_artifact(
    evidence_matrix: Any,
    runtime_matrix: Any,
    *,
    evidence_matrix_path: Path,
    runtime_matrix_path: Path,
    observed_at: str,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=evidence_matrix+runtime_matrix_function_inputs "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    by_line, duplicate_line_keys, unexpected_line_keys = evidence_by_line(evidence_matrix)
    worker_readiness = classify_worker_readiness(runtime_matrix)

    lines = [
        build_line(line_key, evidence_line=by_line.get(line_key), worker_readiness=worker_readiness)
        for line_key in REQUIRED_LINE_KEYS
    ]
    missing_line_keys = [line_key for line_key in REQUIRED_LINE_KEYS if line_key not in by_line]
    requires_worker_line_keys = [
        line["line_key"] for line in lines if line.get("requires_worker") is True
    ]
    blocked_line_keys = [line["line_key"] for line in lines if line["status"] == STATUS_BLOCKED]
    failed_line_keys = [line["line_key"] for line in lines if line["status"] == STATUS_FAILED]
    passed_line_keys = [line["line_key"] for line in lines if line["status"] == STATUS_PASSED]

    if failed_line_keys or missing_line_keys or duplicate_line_keys or unexpected_line_keys:
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
            "kind": "evidence_matrix_plus_runtime_health_matrix",
            "evidence_matrix_path": str(evidence_matrix_path),
            "runtime_matrix_path": str(runtime_matrix_path),
            "runtime_schema_version": detect_schema_version(runtime_matrix),
        },
        "expected_line_keys": list(REQUIRED_LINE_KEYS),
        "summary": {
            "expected_line_count": len(REQUIRED_LINE_KEYS),
            "observed_line_count": len(lines),
            "passed_line_keys": passed_line_keys,
            "blocked_line_keys": blocked_line_keys,
            "failed_line_keys": failed_line_keys,
            "requires_worker_line_keys": requires_worker_line_keys,
            "missing_line_keys": missing_line_keys,
            "unexpected_line_keys": unexpected_line_keys,
            "duplicate_line_keys": duplicate_line_keys,
            "worker_readiness_status": worker_readiness["status"],
            "worker_readiness_reason": worker_readiness["reason"],
        },
        "lines": lines,
    }


def detect_schema_version(payload: Any) -> str | None:
    for root in payload_roots(payload):
        if isinstance(root, dict) and is_present(root.get("schema_version")):
            return str(root["schema_version"])
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    evidence_matrix = load_json(args.evidence_matrix)
    runtime_matrix = load_json(args.runtime_matrix)
    artifact = build_artifact(
        evidence_matrix,
        runtime_matrix,
        evidence_matrix_path=args.evidence_matrix,
        runtime_matrix_path=args.runtime_matrix,
        observed_at=utc_now(),
    )
    write_json(args.output, artifact)
    if args.json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"business_line_async_readiness={artifact['status']} output={args.output}")
    return 0 if artifact["status"] == STATUS_PASSED else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
