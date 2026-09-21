#!/usr/bin/env python3
"""Atomically record one final functorial architecture remediation batch."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "arch-baseline.json"
PACKETS = ROOT / "docs/governance/functorial-debt-zero-baseline-packets.v1.json"
RESOLUTIONS = ROOT / "docs/governance/functorial-debt-zero-baseline-resolutions.v1.json"
AUTHORITY_CEILING = (
    "IMPLEMENTATION_ONLY_NOT_PROMOTION_NOT_PRODUCTION_NOT_LIVE_NOT_CUTOVER"
)
PACKET_WITNESSES = {
    "K0d": "test:test_INVARIANT__registered_c7_failure_family_is_closed_and_nonempty",
    "W01": "test:test_w01_failure_constructors_use_registered_families",
    "W02": "test:test_FAILURE_PRESERVED__w02_fail_returns_kit_failure_values",
    "W03": "test:test_FAILURE_PRESERVED__w03_members_are_closed_and_unknown_codes_rejected",
    "W04": "test:test_FAILURE_PRESERVED__w04_fail_returns_kit_failure_structure",
    "W05": "test:test_INVARIANT__w05_failure_returns_closed_kit_failure",
    "W06": "test:test_FAILURE_PRESERVED__w06_fail_returns_kit_failure",
    "W07": "test:test_INVARIANT__w07_failures_are_values_with_exact_identity",
}


class ResolutionError(RuntimeError):
    """The final batch is not safe to record."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _current_fail_keys(root: Path) -> list[str]:
    from functorial_kit import scan_project, violation_key

    return sorted(
        {
            violation_key(item)
            for item in scan_project(root).violations
            if item.severity == "fail"
        }
    )


def _packet_owners(packet_document: dict[str, Any]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for packet in packet_document["packets"]:
        packet_id = packet["id"]
        for key in packet["expected_removed_keys"]:
            if key in owners:
                raise ResolutionError(f"duplicate packet owner: {key}")
            owners[key] = packet_id
    return owners


def _test_functions(root: Path) -> set[str]:
    names: set[str] = set()
    roots = (root / "tests", root / "main/backend/tests")
    for test_root in roots:
        for path in test_root.rglob("test*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeError, SyntaxError) as exc:
                raise ResolutionError(f"cannot inspect witness file {path}: {exc}") from exc
            names.update(
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")
            )
    return names


def _validate_witnesses(root: Path) -> None:
    available = _test_functions(root)
    required = set(PACKET_WITNESSES.values())
    missing = sorted(
        witness for witness in required if witness.removeprefix("test:") not in available
    )
    if missing:
        raise ResolutionError(f"witness test functions missing: {missing}")


def _resolution_class(root: Path, key: str) -> str:
    try:
        relative = key.split("|", 2)[1]
    except IndexError as exc:
        raise ResolutionError(f"malformed architecture key: {key}") from exc
    source = (root / relative).read_text(encoding="utf-8")
    if "kit:boundary" in source:
        return "TYPED_FAILURE_SEMANTICS_WITH_EXPLICIT_BOUNDARY"
    return "TOTAL_TYPED_FAILURE_SEMANTICS"


def _entry(root: Path, key: str, packet_id: str) -> dict[str, Any]:
    relative = key.split("|", 2)[1]
    witnesses = [PACKET_WITNESSES[packet_id]]
    return {
        "status": "ACCEPTED",
        "packet_id": packet_id,
        "resolution_class": _resolution_class(root, key),
        "evidence": [
            f"{relative}: latest-kit no-throw-in-core finding removed",
            f"packet={packet_id}: shared failure-family migration with focused semantic and ABI witnesses",
        ],
        "witnesses": witnesses,
        "authority_ceiling": AUTHORITY_CEILING,
    }


def _atomic_json_write(path: Path, value: Any) -> None:
    payload = (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--packets", type=Path, default=PACKETS)
    parser.add_argument("--resolutions", type=Path, default=RESOLUTIONS)
    parser.add_argument("--expected-removed", type=int, default=210)
    parser.add_argument("--expected-resolution-sha256")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    baseline = _load(args.baseline)
    packet_document = _load(args.packets)
    resolution_document = _load(args.resolutions)
    if not isinstance(baseline, list) or not all(isinstance(key, str) for key in baseline):
        raise ResolutionError("baseline must be an array of architecture keys")
    if resolution_document.get("authority_ceiling") != AUTHORITY_CEILING:
        raise ResolutionError("resolution ledger authority ceiling mismatch")

    current = _current_fail_keys(root)
    baseline_set = set(baseline)
    current_set = set(current)
    new = sorted(current_set - baseline_set)
    removed = sorted(baseline_set - current_set)
    unchanged = sorted(baseline_set & current_set)
    if new:
        raise ResolutionError(f"new architecture fail keys: {new}")
    if len(removed) != args.expected_removed or unchanged:
        raise ResolutionError(
            f"final batch incomplete: removed={len(removed)} unchanged={len(unchanged)}"
        )

    owners = _packet_owners(packet_document)
    unsupported_packets = sorted({owners.get(key) for key in removed} - set(PACKET_WITNESSES))
    if unsupported_packets:
        raise ResolutionError(f"final batch has unsupported packet owners: {unsupported_packets}")
    _validate_witnesses(root)

    entries = resolution_document.get("entries")
    if not isinstance(entries, dict):
        raise ResolutionError("resolution ledger entries must be an object")
    additions = {key: _entry(root, key, owners[key]) for key in removed}
    conflicting = sorted(
        key for key, value in additions.items() if key in entries and entries[key] != value
    )
    if conflicting:
        raise ResolutionError(f"existing resolution entries conflict: {conflicting}")

    report = {
        "schema": "mrw.functorial_debt_zero_baseline.resolution_batch.v1",
        "status": "ready",
        "baseline_sha256": _sha256(args.baseline),
        "resolution_sha256_before": _sha256(args.resolutions),
        "counts": {
            "new": len(new),
            "removed": len(removed),
            "unchanged": len(unchanged),
            "existing_entries": len(entries),
            "additions": len(additions),
        },
        "authority_ceiling": AUTHORITY_CEILING,
    }
    if args.write:
        expected = args.expected_resolution_sha256
        if not expected:
            raise ResolutionError("--expected-resolution-sha256 is required with --write")
        if expected != report["resolution_sha256_before"]:
            raise ResolutionError(
                "resolution ledger SHA mismatch: "
                f"expected={expected} actual={report['resolution_sha256_before']}"
            )
        resolution_document["entries"] = {**entries, **additions}
        _atomic_json_write(args.resolutions, resolution_document)
        report["status"] = "written"
        report["resolution_sha256_after"] = _sha256(args.resolutions)
        report["counts"]["entries_after"] = len(resolution_document["entries"])

    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
