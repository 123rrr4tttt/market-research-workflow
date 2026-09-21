#!/usr/bin/env python3
"""Validate the frozen Contract 14 integration return without external effects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
RETURN = OUT / "return.v1.json"
VALIDATION = OUT / "return-validation.v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    if VALIDATION.exists():
        raise SystemExit(f"TARGET_ALREADY_EXISTS: {VALIDATION}")
    result = load(RETURN)
    errors: list[str] = []

    if result.get("schema_version") != "mrw.stage1.contract14.return.v1":
        errors.append("schema_version")
    if result.get("RETURN_RESULT") != "BLOCKED":
        errors.append("return_result")
    if result.get("authoritative") is not False:
        errors.append("authoritative")
    if result.get("production_release_authorized") is not False:
        errors.append("production_release_authorized")
    if result.get("phase_b_c_v5_gated") is not True:
        errors.append("phase_b_c_v5_gated")

    for key, expected in {
        "contract_14": "3252e21452e78c73fc9fef9b8b7435c2c3e0ab4466a6b411fe567010d4ea28e7",
        "contract_13_return": "0b9dda0595b84176bd38c60b69030b930a128146c98a8da893ce4aec897b1bbc",
        "claim_table": "8362b368b5f4d944bb1bddf70f397e73c1b3716bc0bdb6244e61699b38e719b3",
    }.items():
        row = result["input_source_identity_and_hashes"][key]
        path = ROOT / row["path"]
        if sha256(path) != expected or row["sha256"] != expected:
            errors.append(f"input_hash:{key}")

    manifest_ref = result["artifact_manifest"]
    manifest_path = ROOT / manifest_ref["path"]
    manifest = load(manifest_path)
    if sha256(manifest_path) != manifest_ref["sha256"]:
        errors.append("manifest_hash")
    if manifest["artifact_count"] != len(manifest["artifacts"]):
        errors.append("manifest_count")
    manifest_paths: list[str] = []
    for row in manifest["artifacts"]:
        path = ROOT / row["path"]
        manifest_paths.append(row["path"])
        if not path.is_file():
            errors.append(f"missing_artifact:{row['path']}")
        elif sha256(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
            errors.append(f"artifact_drift:{row['path']}")
    if len(manifest_paths) != len(set(manifest_paths)):
        errors.append("manifest_duplicate_path")

    changed_ref = result["changed_paths"]
    changed_path = ROOT / changed_ref["path"]
    changed = load(changed_path)
    if sha256(changed_path) != changed_ref["sha256"]:
        errors.append("changed_paths_hash")
    if changed["entry_count"] != len(changed["entries"]):
        errors.append("changed_paths_count")
    if any(row["change_kind"] != "CREATE_ONLY" for row in changed["entries"]):
        errors.append("non_create_only_entry")

    claims = result["claim_dispositions"]
    claim_ids = [row["claim_id"] for row in claims]
    nodeids = [nodeid for row in claims for nodeid in row["dependent_nodeids"]]
    expected_claim_ids = [f"claim-{index:03d}" for index in range(1, 17)]
    if claim_ids != expected_claim_ids:
        errors.append("claim_id_coverage")
    if len(nodeids) != 30 or len(nodeids) != len(set(nodeids)):
        errors.append("nodeid_coverage")
    if result["claim_summary"] != {
        "claim_count": 16,
        "dependent_nodeid_count": 30,
        "nodeids_covered_exactly_once": True,
        "completed_local_claims": ["claim-003", "claim-013", "claim-015"],
        "blocked_local_claims": ["claim-005", "claim-008", "claim-009", "claim-010", "claim-011"],
        "history_inspected_claims": ["claim-001", "claim-002", "claim-004", "claim-014", "claim-016"],
        "open_live_claims": ["claim-006", "claim-007", "claim-012"],
        "completed_local_nodeid_count": 4,
        "blocked_local_nodeid_count": 9,
        "history_nodeid_count": 8,
        "open_live_nodeid_count": 9,
    }:
        errors.append("claim_summary")
    if any(row["current_qualification_granted"] for row in claims):
        errors.append("current_qualification_granted")
    if any(row["authoritative"] or row["production_release_authorized"] for row in claims):
        errors.append("claim_authority")

    if list(OUT.rglob("__pycache__")) or list(OUT.rglob("*.pyc")):
        errors.append("generated_cache_present")
    if (OUT / "local/vector-downstream").exists():
        errors.append("blocked_downstream_was_created")

    expected_source_hashes = {
        "process_py": "790b6cb90086d6ba1171309e572b7e7be4c906db3705170dbd4a12ca7ea16c63",
        "models_base_py": "173d95722cef7411f4b1e4606f8dbdbf850d74fbae9847b942b13be1e56c8308",
        "workflow_graph_runtime_py": "15c22d898b1c90205c43585aae4e3d83a425782e57676926507b92e6b8fb68ca",
    }
    for key, expected in expected_source_hashes.items():
        row = result["unchanged_source_runtime_and_bindings"][key]
        if row["sha256"] != expected or sha256(ROOT / row["path"]) != expected:
            errors.append(f"source_drift:{key}")

    receipt = {
        "schema_version": "mrw.stage1.contract14.return-validation.v1",
        "status": "PASS" if not errors else "FAIL",
        "authoritative": False,
        "production_release_authorized": False,
        "return": {
            "path": RETURN.relative_to(ROOT).as_posix(),
            "sha256": sha256(RETURN),
            "bytes": RETURN.stat().st_size,
        },
        "checks": {
            "input_hashes": "PASS" if not any(e.startswith("input_hash") for e in errors) else "FAIL",
            "artifact_manifest": "PASS" if not any(e.startswith(("manifest", "missing_artifact", "artifact_drift")) for e in errors) else "FAIL",
            "claim_and_nodeid_coverage": "PASS" if not any(e in {"claim_id_coverage", "nodeid_coverage", "claim_summary"} for e in errors) else "FAIL",
            "authority_ceiling": "PASS" if not any(e in {"authoritative", "production_release_authorized", "phase_b_c_v5_gated", "claim_authority", "current_qualification_granted"} for e in errors) else "FAIL",
            "source_runtime_unchanged": "PASS" if not any(e.startswith("source_drift") for e in errors) else "FAIL",
            "cleanup_and_blocked_downstream": "PASS" if not any(e in {"generated_cache_present", "blocked_downstream_was_created"} for e in errors) else "FAIL",
        },
        "errors": errors,
        "authority_ceiling": result["authority_ceiling"],
    }
    VALIDATION.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit("VALIDATION_FAILED: " + ", ".join(errors))


if __name__ == "__main__":
    main()
