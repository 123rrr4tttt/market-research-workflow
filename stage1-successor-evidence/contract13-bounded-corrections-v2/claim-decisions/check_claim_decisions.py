#!/usr/bin/env python3
"""Validate the Contract 13 claim decision table and emit a receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent
TABLE_PATH = OUT_DIR / "claim-decisions.v2.json"
MD_PATH = OUT_DIR / "claim-decisions.v2.md"
INVENTORY_PATH = REPO_ROOT / "stage1-successor-evidence/residual-disposition-v1/inventory/backend_failure_inventory.root-input.v1.json"
CRAWLER_PATH = REPO_ROOT / "stage1-successor-evidence/residual-disposition-v1/missing-evidence/crawler-source/crawler-source-missing-evidence-provenance.v1.json"
VECTOR_PATH = REPO_ROOT / "stage1-successor-evidence/residual-disposition-v1/missing-evidence/opensearch-vector/opensearch-vector-missing-evidence-provenance.v1.json"
ALLOWED = {
    "ACTUAL_HISTORICAL_RECEIPT_REQUIRED",
    "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE",
    "LIVE_OBSERVATION_REQUIRED",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-receipt", action="store_true")
    args = parser.parse_args(argv)
    errors: list[str] = []
    table = read_json(TABLE_PATH)
    inventory = read_json(INVENTORY_PATH)
    crawler = read_json(CRAWLER_PATH)
    vector = read_json(VECTOR_PATH)

    expected = sorted(row["nodeid"] for row in inventory["failures"] if row["category"] == "missing_evidence")
    actual = [nodeid for claim in table["claims"] for nodeid in claim["dependent_nodeids"]]
    counts = Counter(actual)
    if sorted(actual) != expected:
        errors.append("claim nodeid union does not exactly equal frozen missing_evidence inventory")
    duplicates = sorted(nodeid for nodeid, count in counts.items() if count != 1)
    if duplicates:
        errors.append(f"nodeids not covered exactly once: {duplicates}")
    if len(expected) != 30:
        errors.append(f"expected frozen inventory count 30, got {len(expected)}")
    if len({claim["claim_id"] for claim in table["claims"]}) != len(table["claims"]):
        errors.append("duplicate claim_id")
    if len({claim["claim_key"] for claim in table["claims"]}) != len(table["claims"]):
        errors.append("duplicate claim_key")
    if len({claim["claim_fingerprint_sha256"] for claim in table["claims"]}) != len(table["claims"]):
        errors.append("duplicate claim fingerprint")

    provenance_entries = set()
    for entry in crawler["inventory"]["entries"]:
        provenance_entries.add(("crawler", entry.get("entry_id"), entry["old_path"]))
    for entry in vector["missing_sources"]:
        provenance_entries.add(("vector", entry.get("entry_id"), entry["path"]))

    for claim in table["claims"]:
        decision = claim.get("decision")
        if decision not in ALLOWED:
            errors.append(f"{claim['claim_id']}: invalid decision {decision!r}")
        if claim.get("dependent_nodeid_count") != len(claim["dependent_nodeids"]):
            errors.append(f"{claim['claim_id']}: dependent_nodeid_count mismatch")
        present_payloads = sum(
            key in claim for key in ("fresh_proposal", "recovery_authority_boundary", "rerun_authority_boundary")
        )
        if present_payloads != 1:
            errors.append(f"{claim['claim_id']}: decision payloads are not mutually exclusive")
        if decision == "FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE":
            proposal = claim.get("fresh_proposal", {})
            required = {
                "existing_generators",
                "existing_generator_refs",
                "allowed_inputs",
                "expected_artifacts",
                "status_authority_ceiling",
                "dependent_nodeids",
                "write_boundary",
            }
            missing = sorted(required - set(proposal))
            if missing:
                errors.append(f"{claim['claim_id']}: fresh proposal missing {missing}")
            if proposal.get("dependent_nodeids") != claim["dependent_nodeids"]:
                errors.append(f"{claim['claim_id']}: fresh proposal nodeids differ")
            for ref in proposal.get("existing_generator_refs", []):
                path = REPO_ROOT / ref["path"]
                if not path.is_file() or sha256(path) != ref["sha256"]:
                    errors.append(f"{claim['claim_id']}: generator ref missing/drifted: {ref['path']}")
        elif "missing_specific_evidence" not in claim:
            errors.append(f"{claim['claim_id']}: missing concrete evidence description")

        for anchor in claim.get("canonical_anchors", []):
            path = REPO_ROOT / anchor["path"]
            if not path.is_file() or sha256(path) != anchor["sha256"]:
                errors.append(f"{claim['claim_id']}: canonical anchor missing/drifted: {anchor['path']}")
        for req in claim.get("source_requirements", []):
            kind = "crawler" if "crawler-source" in req["provenance_file"] else "vector"
            if (kind, req.get("provenance_entry_id"), req["missing_path"]) not in provenance_entries:
                errors.append(f"{claim['claim_id']}: unresolved provenance entry for {req['missing_path']}")
            provenance_path = REPO_ROOT / req["provenance_file"]
            if not provenance_path.is_file() or sha256(provenance_path) != req["provenance_file_sha256"]:
                errors.append(f"{claim['claim_id']}: provenance file missing/drifted")

    input_hash_errors = []
    for item in table["inputs"]:
        path = REPO_ROOT / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"]:
            input_hash_errors.append(item["path"])
    if input_hash_errors:
        errors.append(f"input files missing/drifted: {input_hash_errors}")
    if table["classification_contract"].get("synthetic_fixture_may_close_factual_claim") is not False:
        errors.append("synthetic fixture closure policy is not false")
    if table.get("closure_claim_allowed") is not False or table.get("production_release_authorized") is not False:
        errors.append("authority ceilings were widened")

    decision_nodeids = Counter()
    for claim in table["claims"]:
        decision_nodeids[claim["decision"]] += len(claim["dependent_nodeids"])
    checks = {
        "frozen_missing_evidence_nodeid_count_is_30": len(expected) == 30,
        "nodeid_union_exact": sorted(actual) == expected,
        "nodeids_exactly_once": not duplicates,
        "claim_keys_unique": len({c["claim_key"] for c in table["claims"]}) == len(table["claims"]),
        "decision_payloads_mutually_exclusive": all(
            sum(key in c for key in ("fresh_proposal", "recovery_authority_boundary", "rerun_authority_boundary")) == 1
            for c in table["claims"]
        ),
        "fresh_proposal_fields_complete": not any("fresh proposal" in error for error in errors),
        "referenced_inputs_generators_anchors_and_provenance_resolve": not any(
            token in error for error in errors for token in ("missing/drifted", "unresolved provenance")
        ),
        "synthetic_fixture_cannot_close_fact": table["classification_contract"].get("synthetic_fixture_may_close_factual_claim") is False,
        "authority_not_widened": table.get("closure_claim_allowed") is False and table.get("production_release_authorized") is False,
    }
    receipt = {
        "schema_version": "mrw.contract13.claim_decisions.validation.v2",
        "record_id": "contract13-claim-decisions-validation-2026-09-06",
        "status": "passed" if not errors else "failed",
        "validation_passed": not errors,
        "errors": errors,
        "checks": checks,
        "counts": {
            "expected_nodeids": len(expected),
            "covered_nodeids": len(actual),
            "unique_claims": len(table["claims"]),
            "decision_nodeid_counts": dict(sorted(decision_nodeids.items())),
        },
        "artifacts": [
            {"path": TABLE_PATH.relative_to(REPO_ROOT).as_posix(), "sha256": sha256(TABLE_PATH)},
            {"path": MD_PATH.relative_to(REPO_ROOT).as_posix(), "sha256": sha256(MD_PATH)},
            {"path": Path(__file__).relative_to(REPO_ROOT).as_posix(), "sha256": sha256(Path(__file__))},
            {"path": (OUT_DIR / "generate_claim_decisions.py").relative_to(REPO_ROOT).as_posix(), "sha256": sha256(OUT_DIR / "generate_claim_decisions.py")},
        ],
        "authority_ceiling": table["authority_ceiling"],
    }
    if args.write_receipt:
        (OUT_DIR / "validation-receipt.v2.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
