#!/usr/bin/env python3
"""Report or apply an evidence-gated functorial architecture baseline delta."""

from __future__ import annotations

import argparse
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _current_fail_keys(root: Path) -> list[str]:
    from functorial_kit import scan_project, violation_key

    scan = scan_project(root)
    return sorted({violation_key(item) for item in scan.violations if item.severity == "fail"})


def _delta(baseline: list[str], current: list[str]) -> dict[str, list[str]]:
    baseline_set = set(baseline)
    current_set = set(current)
    return {
        "new": sorted(current_set - baseline_set),
        "removed": sorted(baseline_set - current_set),
        "unchanged": sorted(baseline_set & current_set),
        "present": sorted(current_set),
    }


def _packet_owner_by_key(packet_document: dict[str, Any]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for packet in packet_document["packets"]:
        for key in packet["expected_removed_keys"]:
            if key in owners:
                raise ValueError(f"duplicate packet owner for {key}")
            owners[key] = packet["id"]
    return owners


def _resolution_errors(
    removed: list[str],
    packet_document: dict[str, Any],
    resolution_document: dict[str, Any],
) -> list[str]:
    owners = _packet_owner_by_key(packet_document)
    entries = resolution_document.get("entries", {})
    errors: list[str] = []
    for key in removed:
        entry = entries.get(key)
        if not isinstance(entry, dict):
            errors.append(f"missing resolution: {key}")
            continue
        if entry.get("status") != "ACCEPTED":
            errors.append(f"resolution is not ACCEPTED: {key}")
        if entry.get("packet_id") != owners.get(key):
            errors.append(f"packet owner mismatch: {key}")
        if not entry.get("resolution_class"):
            errors.append(f"resolution_class missing: {key}")
        if not entry.get("evidence"):
            errors.append(f"evidence missing: {key}")
        if not entry.get("witnesses"):
            errors.append(f"witnesses missing: {key}")
        if entry.get("authority_ceiling") != "IMPLEMENTATION_ONLY_NOT_PROMOTION_NOT_PRODUCTION_NOT_LIVE_NOT_CUTOVER":
            errors.append(f"authority ceiling mismatch: {key}")
    return errors


def _atomic_json_write(path: Path, value: Any) -> None:
    encoded = (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--packets", type=Path, default=PACKETS)
    parser.add_argument("--resolutions", type=Path, default=RESOLUTIONS)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--expected-baseline-sha256")
    args = parser.parse_args(argv)

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    current = _current_fail_keys(args.root)
    delta = _delta(baseline, current)
    report: dict[str, Any] = {
        "schema": "mrw.functorial_architecture_baseline_delta.v1",
        "status": "passed" if not delta["new"] else "new_fail_keys",
        "baseline_sha256": _sha256(args.baseline),
        "counts": {name: len(values) for name, values in delta.items()},
        **delta,
        "baseline_written": False,
        "authority_ceiling": "IMPLEMENTATION_ONLY_NOT_PROMOTION_NOT_PRODUCTION_NOT_LIVE_NOT_CUTOVER",
    }

    if args.write_baseline:
        if not args.expected_baseline_sha256:
            report["status"] = "write_rejected_expected_sha_required"
        elif args.expected_baseline_sha256 != report["baseline_sha256"]:
            report["status"] = "write_rejected_baseline_sha_mismatch"
        elif delta["new"]:
            report["status"] = "write_rejected_new_fail_keys"
        else:
            packet_document = json.loads(args.packets.read_text(encoding="utf-8"))
            resolution_document = json.loads(args.resolutions.read_text(encoding="utf-8"))
            errors = _resolution_errors(delta["removed"], packet_document, resolution_document)
            if errors:
                report["status"] = "write_rejected_resolution_evidence"
                report["resolution_errors"] = errors
            else:
                _atomic_json_write(args.baseline, delta["present"])
                report["status"] = "baseline_written"
                report["baseline_written"] = True
                report["written_baseline_sha256"] = _sha256(args.baseline)

    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] in {"passed", "baseline_written"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
