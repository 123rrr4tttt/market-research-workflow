#!/usr/bin/env python3
# ruff: noqa: E501
"""Focused deterministic validator for the Contract 14 history receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TARGET_CLAIMS = {"claim-001", "claim-002", "claim-004", "claim-014", "claim-016"}
TARGET_DECISION = "ACTUAL_HISTORICAL_RECEIPT_REQUIRED"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))

    require(receipt["schema_version"] == "contract14.history_verification_receipt.v1", "schema_version")
    require(receipt["authoritative"] is False, "authoritative must be false")
    require(receipt["production_release_authorized"] is False, "production release must be false")
    require(receipt["current_qualification_granted"] is False, "current qualification must be false")
    require(receipt["history_only"] is True, "history_only")
    require(receipt["inputs"]["contract"]["expected_sha256_match"] is True, "contract hash")
    require(receipt["inputs"]["claim_table"]["expected_sha256_match"] is True, "claim table hash")
    require(receipt["inputs"]["claim_table"]["parsed_full_document"] is True, "full claim table parse")

    claims = receipt["claims"]
    claim_ids = [claim["claim_id"] for claim in claims]
    require(len(claim_ids) == len(set(claim_ids)), "duplicate claim ids")
    require(set(claim_ids) == TARGET_CLAIMS, "target claim set")
    require(all(claim["decision"] == TARGET_DECISION for claim in claims), "target decision")

    requirements = receipt["requirements"]
    row_ids = [row["requirement_row_id"] for row in requirements]
    require(len(row_ids) == len(set(row_ids)), "duplicate requirement row ids")
    require(set(row["claim_id"] for row in requirements) == TARGET_CLAIMS, "requirement claim set")

    objects = receipt["unique_objects"]
    object_oids = [item["git_blob_oid"] for item in objects]
    require(len(object_oids) == len(set(object_oids)), "duplicate unique object oid")
    require(all(item["object_exists"] and item["object_type"] == "blob" for item in objects), "missing/non-blob object")
    require(all(item["expected_bytes_match"] for item in objects), "expected byte mismatch")
    require(all(item["expected_sha256_match"] for item in objects), "expected SHA-256 mismatch")
    require(all(result["parseable"] for item in objects for result in item["parseability_by_path"].values()), "parseability failure")

    oid_set = set(object_oids)
    require(all(row["git_blob_oid"] in oid_set for row in requirements), "dangling object reference")
    require(all(row["object_verification"]["parseable"] for row in requirements), "requirement parseability")
    for row in requirements:
        if row["enumerated_commit"]:
            require(row["commit_path_binding"]["status"] == "VERIFIED", f"commit:path binding {row['requirement_row_id']}")
        else:
            require(row["commit_path_binding"]["status"] == "NOT_ENUMERATED", f"unexpected path binding {row['requirement_row_id']}")

    nodeids = [entry["nodeid"] for claim in claims for entry in claim["dependent_nodeids"]]
    require(len(nodeids) == len(set(nodeids)), "duplicate dependent nodeids")
    require(all(entry["current_test_qualification_granted"] is False for claim in claims for entry in claim["dependent_nodeids"]), "nodeid qualification granted")
    require(all(claim["four_layer_assessment"]["layer_d_current_qualification"]["status"] == "NOT_GRANTED" for claim in claims), "layer-d status")

    summary = receipt["summary"]
    require(summary["target_claim_count"] == len(claims), "claim count summary")
    require(summary["requirement_row_count"] == len(requirements), "requirement count summary")
    require(summary["unique_blob_count"] == len(objects), "object count summary")
    require(summary["dependent_nodeid_count"] == len(nodeids), "nodeid count summary")
    require(summary["currently_qualified_nodeid_count"] == 0, "qualified nodeid count")
    require(summary["all_unique_objects_exist_as_blob"] is True, "all object summary")
    print(json.dumps({"status": "PASS", "claims": len(claims), "requirements": len(requirements), "unique_blobs": len(objects), "nodeids": len(nodeids)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
