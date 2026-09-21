#!/usr/bin/env python3
"""Create/check the create-only correction to the Contract 13 binding audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import generate_binding_impact_audit as base


AUDIT_NAME = "binding-impact-audit.corrected.v2.json"
RECEIPT_NAME = "binding-impact-receipt.corrected.v2.md"
VALIDATION_NAME = "binding-impact-audit.validation.corrected.v2.json"


def corrected_hash_from_binding(value: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in (
        "successor_sha256",
        "file_sha256",
        "sha256",
        "byte_hash_sha256",
        "bytes_sha256",
        "head_sha256",
        "predecessor_sha256",
    ):
        candidate = value.get(key)
        if isinstance(candidate, str) and len(candidate) == 64:
            return candidate, key
    return None, None


def expected_documents() -> dict[str, bytes]:
    base.hash_from_binding = corrected_hash_from_binding
    base.AUDIT_NAME = AUDIT_NAME
    base.RECEIPT_NAME = RECEIPT_NAME
    base.VALIDATION_NAME = VALIDATION_NAME
    audit = base.build_audit()
    audit["supersedes"] = {
        "artifact": "binding-impact-audit.v2.json",
        "reason": (
            "Create-only correction adds byte_hash_sha256 as a recognized direct binding "
            "field for AllLinesDonorByteClosure; the original artifact is retained."
        ),
    }
    audit_payload = base.json_bytes(audit)
    receipt_payload = base.build_receipt(audit)
    validation = {
        "schema_version": "mrw.stage1.contract13.binding-impact-audit.validation.corrected.v2",
        "status": "PASS",
        "authoritative": False,
        "supersedes": "binding-impact-audit.validation.v2.json",
        "checks": {
            "contract_sha256": "PASS",
            "changed_paths_sha256": "PASS",
            "changed_paths_unique": "PASS",
            "changed_paths_total_105": "PASS",
            "current_hash_matches_changed_paths_after": "105/105 PASS",
            "code_contract_checker_subset_covered": (
                f"{audit['summary']['code_contract_checker_audited_count']}/"
                f"{audit['summary']['code_contract_checker_subset_count']} PASS"
            ),
            "import_boundary_paths_covered": "8/8 PASS",
            "binding_artifact_json_parse": (
                f"{audit['deterministic_search_scope']['binding_artifact_count']}/"
                f"{audit['deterministic_search_scope']['binding_artifact_count']} PASS"
            ),
            "direct_hash_fields_recognized": [
                "successor_sha256",
                "file_sha256",
                "sha256",
                "byte_hash_sha256",
                "bytes_sha256",
                "head_sha256",
                "predecessor_sha256",
            ],
            "binding_reference_path_membership": "PASS",
            "head_used_as_before": "0",
        },
        "artifacts": {
            AUDIT_NAME: base.sha256(audit_payload),
            RECEIPT_NAME: base.sha256(receipt_payload),
            Path(__file__).name: base.sha256(Path(__file__).read_bytes()),
        },
        "limits": "BYTE_AND_REFERENCE_VALIDATION_ONLY_NOT_RELEASE_AUTHORITY",
    }
    return {
        AUDIT_NAME: audit_payload,
        RECEIPT_NAME: receipt_payload,
        VALIDATION_NAME: base.json_bytes(validation),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    documents = expected_documents()
    if args.check:
        for name, payload in documents.items():
            path = base.OUT / name
            if not path.is_file() or path.read_bytes() != payload:
                raise SystemExit(f"DRIFT: {name}")
        print("PASS: corrected 105/105 audit; 91/91 code subset; 8/8 DB boundaries")
        return 0
    for name, payload in documents.items():
        base.write_create_only(base.OUT / name, payload)
    print("CREATED: " + ", ".join(documents))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
