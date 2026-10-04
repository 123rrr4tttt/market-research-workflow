#!/usr/bin/env python3
"""Gate offline evidence-matrix artifacts for full business-line batch coverage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Sequence

try:
    from scripts._automation_runtime import (
        CANONICAL_LINE_KEYS,
        repo_root,
        utc_now,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import CANONICAL_LINE_KEYS, repo_root, utc_now


CONTRACT_VERSION = "business_line.evidence_matrix.v1"
SCHEMA_VERSION = "business_line_batch_coverage_check.v1"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"

REQUIRED_LINE_KEYS = CANONICAL_LINE_KEYS

REQUIRED_LINE_FIELDS = ("current_gaps", "next_remediation", "verification_commands")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", help="JSON evidence matrix artifact path(s).")
    parser.add_argument("--root", default=None, help="Repository root used for relative artifact paths.")
    return parser.parse_args(argv)


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


def normalize_line_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


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


def detect_contract_version(payload: Any) -> str | None:
    for root in payload_roots(payload):
        if isinstance(root, dict) and is_present(root.get("contract_version")):
            return str(root["contract_version"])
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
        if is_present(root.get("line_key")):
            return [root]
        for key in ("lines", "business_lines", "items", "evidence_matrix", "matrix"):
            value = root.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return line_items_from_mapping(value)
    return []


def check_line(line: dict[str, Any]) -> dict[str, Any]:
    raw_line_key = line.get("line_key")
    line_key = normalize_line_key(raw_line_key)
    missing_fields = [field for field in REQUIRED_LINE_FIELDS if not is_present(line.get(field))]
    if not is_present(raw_line_key):
        missing_fields.insert(0, "line_key")
    return {
        "line_key": line_key if line_key else "<missing>",
        "status": STATUS_PASSED if not missing_fields else STATUS_FAILED,
        "missing_fields": missing_fields,
    }


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
                "contract_version": None,
                "missing_contract_fields": ["artifact_file"],
                "lines": [],
            }
        )
        return row

    payload, error = load_artifact(path)
    if error is not None:
        row.update(
            {
                "status": STATUS_FAILED,
                "contract_version": None,
                "missing_contract_fields": ["valid_json"],
                "reason": error,
                "lines": [],
            }
        )
        return row

    contract_version = detect_contract_version(payload)
    lines = [check_line(line) for line in extract_lines(payload)]
    missing_contract_fields: list[str] = []
    if contract_version != CONTRACT_VERSION:
        missing_contract_fields.append("contract_version")
    if not lines:
        missing_contract_fields.append("lines")

    line_failures = [line for line in lines if line["status"] == STATUS_FAILED]
    row.update(
        {
            "status": STATUS_PASSED if not missing_contract_fields and not line_failures else STATUS_FAILED,
            "contract_version": contract_version,
            "expected_contract_version": CONTRACT_VERSION,
            "missing_contract_fields": missing_contract_fields,
            "lines": lines,
        }
    )
    return row


def build_report(
    artifact_paths: Sequence[str | Path], root: Path | None = None
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=evidence_matrix_artifacts "
    "witness=test:test_INVARIANT__c16_business_cli_authority_metadata",
]:
    resolved_root = root.resolve() if root else repo_root()
    observed_at = utc_now()
    artifacts = [inspect_artifact(Path(path), resolved_root, observed_at) for path in artifact_paths]

    observed_line_keys: set[str] = set()
    line_rows: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        for line in artifact["lines"]:
            line_key = line["line_key"]
            if line_key == "<missing>":
                continue
            observed_line_keys.add(line_key)
            line_rows.setdefault(line_key, []).append(
                {
                    "artifact_path": artifact["artifact_path"],
                    "status": line["status"],
                    "missing_fields": line["missing_fields"],
                }
            )

    expected_line_keys = set(REQUIRED_LINE_KEYS)
    missing_line_keys = sorted(expected_line_keys - observed_line_keys)
    unexpected_line_keys = sorted(observed_line_keys - expected_line_keys)
    duplicate_line_keys = sorted(line_key for line_key, rows in line_rows.items() if len(rows) > 1)
    incomplete_line_keys = sorted(
        line_key
        for line_key, rows in line_rows.items()
        if line_key in expected_line_keys and any(row["status"] == STATUS_FAILED for row in rows)
    )
    failed_artifacts = [artifact for artifact in artifacts if artifact["status"] == STATUS_FAILED]
    status = (
        STATUS_PASSED
        if artifacts
        and not failed_artifacts
        and not missing_line_keys
        and not unexpected_line_keys
        and not duplicate_line_keys
        and not incomplete_line_keys
        else STATUS_FAILED
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "observed_at": observed_at,
        "contract_version": CONTRACT_VERSION,
        "summary": {
            "artifact_count": len(artifacts),
            "expected_line_count": len(REQUIRED_LINE_KEYS),
            "observed_line_count": len(observed_line_keys),
            "failed_artifact_count": len(failed_artifacts),
            "missing_line_keys": missing_line_keys,
            "unexpected_line_keys": unexpected_line_keys,
            "duplicate_line_keys": duplicate_line_keys,
            "incomplete_line_keys": incomplete_line_keys,
            "required_line_fields": list(REQUIRED_LINE_FIELDS),
        },
        "expected_line_keys": list(REQUIRED_LINE_KEYS),
        "observed_line_keys": sorted(observed_line_keys),
        "line_rows": line_rows,
        "artifacts": artifacts,
        "recommended_command": "python3 scripts/check_business_line_batch_coverage.py <artifact.json> [...]",
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve() if args.root else repo_root()
    report = build_report(args.artifacts, root=root)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == STATUS_PASSED else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
