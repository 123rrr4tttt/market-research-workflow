#!/usr/bin/env python3
"""Validate and assemble the 30-cell P1 eligibility evidence artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXPECTED_FAMILIES = {
    "C1": ("C1.1", "C1.2", "C1.3"),
    "C2": ("C2.1", "C2.2", "C2.3", "C2.4"),
    "C3": ("C3.1", "C3.2"),
    "C4": ("C4.1", "C4.2", "C4.3"),
    "C5": ("C5.1", "C5.2", "C5.3", "C5.4"),
    "C6": ("C6.1", "C6.2", "C6.3"),
    "C7": ("C7.1", "C7.2", "C7.3", "C7.4"),
    "C8": ("C8.1", "C8.2", "C8.3", "C8.4"),
    "C9": ("C9.1", "C9.2", "C9.3"),
}
ALLOWED_DISPOSITIONS = {
    "ADAPT",
    "EXTRACT_AND_REWRITE",
    "REIMPLEMENT",
    "REJECT",
}
REQUIRED_CELL_FIELDS = {
    "cell",
    "boundary",
    "locator_paths",
    "locator_status",
    "observed_symbols",
    "object_types",
    "atom_kind",
    "payload_schema",
    "program_combinators",
    "failure_return_union",
    "canonical_owner",
    "effect_profile",
    "authority_profile",
    "resource_profile",
    "legacy_interpreter",
    "successor_interpreter_candidate",
    "observation_profile",
    "fixture_ids",
    "rollback_observation",
    "disposition",
    "rationale",
    "prerequisites",
    "risk",
    "source_evidence",
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return _sha256(raw)


def _git(worktree: Path, *args: str, allow_failure: bool = False) -> str:
    result = subprocess.run(
        ("git", "-C", str(worktree), *args),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode and not allow_failure:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _worktree_census(repository: Path, target: Path) -> dict[str, object]:
    raw = _git(repository, "worktree", "list", "--porcelain")
    paths = [
        Path(line.removeprefix("worktree "))
        for line in raw.splitlines()
        if line.startswith("worktree ")
    ]
    valid: list[dict[str, object]] = []
    unavailable: list[str] = []
    for path in paths:
        inside = _git(
            path,
            "rev-parse",
            "--is-inside-work-tree",
            allow_failure=True,
        )
        if inside != "true":
            unavailable.append(str(path))
            continue
        status = _git(
            path,
            "status",
            "--porcelain=v1",
            "--untracked-files=normal",
        )
        valid.append(
            {
                "path": str(path),
                "branch": _git(path, "branch", "--show-current"),
                "head": _git(path, "rev-parse", "HEAD"),
                "dirty_entry_count": len(status.splitlines()) if status else 0,
                "target": path.resolve() == target.resolve(),
                "adoption_disposition": (
                    "P1_TARGET_WORKTREE"
                    if path.resolve() == target.resolve()
                    else "READ_ONLY_EVIDENCE_NOT_ADOPTED"
                ),
            }
        )
    return {
        "registered_total": len(paths),
        "valid_count": len(valid),
        "unavailable_or_prunable_count": len(unavailable),
        "valid_worktrees": valid,
        "unavailable_or_prunable_paths": sorted(unavailable),
        "blind_merge_all": False,
        "adoption_rule": "capability packet only after eligibility and exact review",
    }


def _risk_level(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("level", "risk"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
    return "UNSPECIFIED"


def assemble(
    *,
    repository: Path,
    target: Path,
    inventory_path: Path,
    fragments_dir: Path,
    generated_at: datetime,
) -> dict[str, object]:
    inventory_raw = inventory_path.read_bytes()
    inventory = json.loads(inventory_raw)
    frozen_cells = {item["cell"]: item for item in inventory["cells"]}
    expected_cells = tuple(
        cell for family in EXPECTED_FAMILIES.values() for cell in family
    )
    if tuple(sorted(frozen_cells)) != tuple(sorted(expected_cells)):
        raise ValueError("frozen inventory is not the exact 30-cell set")

    fragment_bindings: list[dict[str, object]] = []
    cells: list[dict[str, Any]] = []
    for family, family_cells in EXPECTED_FAMILIES.items():
        path = fragments_dir / f"{family}.json"
        raw = path.read_bytes()
        value = json.loads(raw)
        if not isinstance(value, list):
            raise TypeError(f"{path} root must be an array")
        observed = tuple(item.get("cell") for item in value if isinstance(item, dict))
        if tuple(sorted(observed)) != tuple(sorted(family_cells)):
            raise ValueError(f"{path} does not contain the exact family cells")
        fragment_bindings.append(
            {
                "family": family,
                "path": str(path.relative_to(target)),
                "sha256": _sha256(raw),
                "bytes": len(raw),
                "cell_count": len(value),
            }
        )
        cells.extend(value)

    seen: set[str] = set()
    for item in cells:
        missing = REQUIRED_CELL_FIELDS - set(item)
        if missing:
            raise ValueError(f"{item.get('cell')} missing fields: {sorted(missing)}")
        cell = str(item["cell"])
        if cell in seen:
            raise ValueError(f"duplicate eligibility cell: {cell}")
        seen.add(cell)
        if item["disposition"] not in ALLOWED_DISPOSITIONS:
            raise ValueError(f"invalid disposition for {cell}")
        if not isinstance(item["source_evidence"], list) or not item["source_evidence"]:
            raise ValueError(f"{cell} lacks source evidence")
        frozen = frozen_cells[cell]
        if str(item["boundary"]) != str(frozen["boundary"]):
            raise ValueError(f"{cell} boundary differs from frozen locator")
        locator_paths = {str(path) for path in item["locator_paths"]}
        if not set(frozen["paths"]).issubset(locator_paths):
            raise ValueError(f"{cell} omitted a frozen locator path")
    if seen != set(expected_cells):
        raise ValueError("assembled eligibility evidence is not complete")

    ordered_cells = sorted(cells, key=lambda item: item["cell"])
    disposition_counts = Counter(item["disposition"] for item in ordered_cells)
    risk_counts = Counter(_risk_level(item["risk"]) for item in ordered_cells)
    payload: dict[str, object] = {
        "schema": "mrw.functorial_successor.p1_eligibility.v1",
        "status": "P1_REVIEW_COMPLETE_P2_SELECTION_PENDING",
        "generated_at_utc": generated_at.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "goal_id": "01a0504c-47ef-77e1-9783-454dbcbe3697",
        "worktree": str(target),
        "branch": _git(target, "branch", "--show-current"),
        "baseline_head": _git(target, "rev-parse", "HEAD"),
        "baseline_tree": _git(target, "rev-parse", "HEAD^{tree}"),
        "frozen_locator_inventory": {
            "path": str(inventory_path.relative_to(target)),
            "sha256": _sha256(inventory_raw),
            "status": inventory["status"],
            "eligibility_dispositions_frozen": inventory[
                "eligibility_dispositions_frozen"
            ],
        },
        "worktree_census": _worktree_census(repository, target),
        "fragment_bindings": fragment_bindings,
        "cell_count": len(ordered_cells),
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "risk_counts": dict(sorted(risk_counts.items())),
        "cells": ordered_cells,
        "p2_selection": {
            "state": "PENDING",
            "selected_cell": None,
            "selection_rule": inventory["selection_rule_for_p2"],
        },
        "authority": {
            "business_authority_migrated": False,
            "successor_claim_enabled_for_c1_c9": False,
            "live_provider": False,
            "external_delivery": False,
            "cutover": False,
            "authority_transfer": False,
        },
    }
    payload["content_digest"] = _canonical_digest(payload)
    return payload


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exact = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(exact)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--fragments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args()
    generated_at = datetime.fromisoformat(args.generated_at.replace("Z", "+00:00"))
    if generated_at.tzinfo is None:
        raise SystemExit("--generated-at must be timezone-aware")
    payload = assemble(
        repository=args.repository.resolve(),
        target=args.target.resolve(),
        inventory_path=args.inventory.resolve(),
        fragments_dir=args.fragments.resolve(),
        generated_at=generated_at,
    )
    _write_atomic(args.output.resolve(), payload)
    print(
        json.dumps(
            {
                "ok": True,
                "cell_count": payload["cell_count"],
                "content_digest": payload["content_digest"],
                "output": str(args.output.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
