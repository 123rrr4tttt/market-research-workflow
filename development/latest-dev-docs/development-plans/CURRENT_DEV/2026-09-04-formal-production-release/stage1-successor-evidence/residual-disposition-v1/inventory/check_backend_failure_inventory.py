#!/usr/bin/env python3
"""Validate the Contract 12 backend failure inventory and emit a receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from generate_backend_failure_inventory import (
    AUTHORITY_CEILING,
    CATEGORIES,
    CONTRACT_REL,
    CONTRACT_SHA256,
    DEFAULT_JUNIT,
    DEFAULT_LOG,
    canonical_bytes,
    parse_failures,
    sha256_file,
)


DEFAULT_INVENTORY = Path(__file__).with_name("backend_failure_inventory.v1.json")
DEFAULT_RECEIPT = Path(__file__).with_name("backend_failure_inventory.validation.v1.json")
PATH_RE = re.compile(r"^(?:/|[A-Za-z0-9_.-]+/)[^\n]*$")


def _receipt_bytes(payload: dict[str, Any]) -> bytes:
    body = dict(payload)
    body.pop("receipt_sha256", None)
    return (json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def validate(inventory_path: Path, junit_path: Path, log_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    checks: dict[str, Any] = {}
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        checks["parseability"] = "PASS"
    except (OSError, json.JSONDecodeError) as exc:
        inventory = {}
        checks["parseability"] = f"FAIL: {exc}"
        errors.append(f"inventory parse failed: {exc}")
    expected = parse_failures(junit_path) if junit_path.is_file() else []
    actual = inventory.get("failures", []) if isinstance(inventory, dict) else []
    expected_ids = {row["nodeid"] for row in expected}
    actual_ids = {row.get("nodeid") for row in actual if isinstance(row, dict)}
    checks["uniqueness"] = len(actual) == len(actual_ids)
    checks["totals"] = {"junit_failures": len(expected), "inventory_failures": len(actual), "required": 55}
    if len(expected) != 55:
        errors.append(f"JUnit failure total is {len(expected)}, expected 55")
    if len(actual) != 55:
        errors.append(f"inventory failure total is {len(actual)}, expected 55")
    if len(actual_ids) != len(actual):
        errors.append("inventory nodeids are not unique")
    if expected_ids != actual_ids:
        errors.append(f"nodeid set mismatch: missing={sorted(expected_ids - actual_ids)} extra={sorted(actual_ids - expected_ids)}")
    if inventory.get("contract_12") != {"path": CONTRACT_REL, "sha256": CONTRACT_SHA256}:
        errors.append("Contract 12 reference mismatch")
    if inventory.get("authority_ceiling") != AUTHORITY_CEILING:
        errors.append("authority ceiling mismatch")
    if inventory.get("inventory_sha256") != hashlib.sha256(canonical_bytes(inventory)).hexdigest():
        errors.append("inventory_sha256 mismatch")
    categories = inventory.get("category_counts", {})
    checks["categories"] = categories
    if set(categories) != set(CATEGORIES) or sum(categories.values()) != len(actual):
        errors.append("category totals do not cover all failures")
    groups = inventory.get("groups", [])
    grouped_ids = [nodeid for group in groups for nodeid in group.get("nodeids", [])]
    if sorted(grouped_ids) != sorted(actual_ids):
        errors.append("group nodeids do not exactly cover failure nodeids")
    path_errors = 0
    for row in actual:
        if not isinstance(row, dict):
            errors.append("failure record is not an object")
            continue
        for key in ("nodeid", "owner", "primary_cause", "primary_input_path", "evidence_status", "authority_ceiling"):
            if not str(row.get(key) or "").strip():
                errors.append(f"record {row.get('nodeid')!r} missing {key}")
        if row.get("category") not in CATEGORIES:
            errors.append(f"record {row.get('nodeid')!r} has invalid category")
        refs = row.get("referenced_paths")
        if not isinstance(refs, list) or not refs:
            errors.append(f"record {row.get('nodeid')!r} has no referenced paths")
            continue
        for ref in refs:
            if not isinstance(ref, str) or not PATH_RE.match(ref):
                path_errors += 1
    checks["reference_checks"] = {"records": len(actual), "invalid_path_references": path_errors}
    if path_errors:
        errors.append(f"{path_errors} invalid path references")
    input_hashes = {
        "junit_sha256": sha256_file(junit_path) if junit_path.is_file() else None,
        "log_sha256": sha256_file(log_path) if log_path.is_file() else None,
        "inventory_sha256": inventory.get("inventory_sha256"),
    }
    checks["hashes"] = input_hashes
    source = inventory.get("source_execution", {})
    if source.get("junit_sha256") != input_hashes["junit_sha256"]:
        errors.append("JUnit hash reference mismatch")
    if source.get("log_sha256") != input_hashes["log_sha256"]:
        errors.append("log hash reference mismatch")
    return {
        "schema_version": "mrw.stage1.residual-disposition.backend-failure-inventory.validation.v1",
        "inventory_path": str(inventory_path),
        "junit_path": str(junit_path),
        "log_path": str(log_path),
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checks": checks,
        "inventory_sha256": inventory.get("inventory_sha256"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--junit", type=Path, default=DEFAULT_JUNIT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args(argv)
    receipt = validate(args.inventory, args.junit, args.log)
    receipt["receipt_sha256"] = hashlib.sha256(_receipt_bytes(receipt)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "output": str(args.output), "inventory_sha256": receipt.get("inventory_sha256")}, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
