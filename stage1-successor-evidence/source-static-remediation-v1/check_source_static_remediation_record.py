#!/usr/bin/env python3
"""Fail-closed checker for the Stage 1 source/static remediation package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_REL = Path("stage1-successor-evidence/source-static-remediation-v1")
RECORD_REL = EVIDENCE_REL / "stage1-source-static-remediation-record.v1.json"
MANIFEST_REL = EVIDENCE_REL / "artifact-manifest.v1.json"
VALIDATION_REL = EVIDENCE_REL / "validation-receipt.v1.json"
RAW_LOG_REL = EVIDENCE_REL / "raw/backend-unit-final.log"
RAW_XML_REL = EVIDENCE_REL / "raw/backend-unit-final.xml"
PHASE_B_REL = EVIDENCE_REL / "phase-b/static-production-contract.v1.json"
AUTHORITY_CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)
EXPECTED_REQUIRED_GAPS = {
    "frontend_component_e2e_required",
    "frontend_dependency_audit_required",
    "three_artifact_role_identities",
    "three_role_sbom_provenance_signature_attestation",
    "three_role_image_vulnerability_scan",
    "required_branch_and_convergence_propagation",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def validate_manifest(manifest: dict[str, Any]) -> None:
    require(manifest.get("schema_version") == "mrw.stage1.source_static_remediation_manifest.v1", "MANIFEST_SCHEMA")
    require(manifest.get("status") == "COMPLETE_NOT_AUTHORITY", "MANIFEST_STATUS")
    require(manifest.get("authoritative") is False, "MANIFEST_AUTHORITY")
    require(manifest.get("authority_ceiling") == AUTHORITY_CEILING, "MANIFEST_CEILING")
    members = manifest.get("members")
    require(isinstance(members, list) and manifest.get("member_count") == len(members) == 13, "MANIFEST_COUNT")
    paths = [row.get("path") for row in members if isinstance(row, dict)]
    require(len(paths) == len(members) and len(paths) == len(set(paths)), "MANIFEST_DUPLICATE_OR_BAD_PATH")
    require(paths == sorted(paths), "MANIFEST_NOT_SORTED")
    for row in members:
        path = ROOT / row["path"]
        require(path.is_file(), f"MANIFEST_MISSING:{row['path']}")
        require(path.stat().st_size == row.get("bytes"), f"MANIFEST_SIZE:{row['path']}")
        require(sha256(path) == row.get("sha256"), f"MANIFEST_HASH:{row['path']}")


def validate_phase_a(record: dict[str, Any]) -> None:
    phase_a = record["phase_a_source_closure"]
    require(phase_a.get("status") == "PASS", "PHASE_A_STATUS")
    gate = phase_a["projected_source_gate"]
    require(gate["focused_tests"] == {"passed": 194, "failed": 0}, "SOURCE_FOCUSED_COUNTS")
    require(gate["reviewer_tests"] == {"passed": 13, "failed": 0}, "SOURCE_REVIEWER_COUNTS")
    required_negative = {
        "missing_w07_semantics",
        "missing_agent_service_semantics",
        "unknown_exported_name",
        "source_manifest_omission",
        "projected_delete_cannot_fall_back_to_checkout",
        "wrong_base_index_binding",
        "upsert_metadata_or_bytes_drift",
    }
    require(set(gate.get("negative_gates", [])) == required_negative, "SOURCE_NEGATIVE_GATES")
    backend = phase_a["workflow_equivalent_backend_unit"]
    expected = {
        "exit_code": 0,
        "collection_errors": 0,
        "collected_selector_population": 4122,
        "passed": 1793,
        "failed": 0,
        "skipped": 0,
        "deselected": 2329,
        "warnings": 25,
        "subtests_passed": 52,
        "junit_testsuite_tests_including_subtests": 1845,
        "junit_testcase_elements": 1793,
        "junit_failures": 0,
        "junit_errors": 0,
        "junit_skipped": 0,
    }
    for key, value in expected.items():
        require(backend.get(key) == value, f"BACKEND_COUNT:{key}")
    require(backend.get("selector") == "unit and not external and not flaky", "BACKEND_SELECTOR")
    require(backend["raw_log"]["sha256"] == sha256(ROOT / RAW_LOG_REL), "RAW_LOG_REF")
    require(backend["junit_xml"]["sha256"] == sha256(ROOT / RAW_XML_REL), "RAW_XML_REF")
    log = (ROOT / RAW_LOG_REL).read_text(encoding="utf-8")
    require(
        "1793 passed, 2329 deselected, 25 warnings, 52 subtests passed in 41.33s" in log,
        "RAW_LOG_TERMINAL_TOTALS",
    )
    suite = ET.parse(ROOT / RAW_XML_REL).getroot().find("testsuite")
    require(suite is not None, "JUNIT_TESTSUITE")
    require(suite.attrib.get("tests") == "1845", "JUNIT_TESTS")
    require(suite.attrib.get("failures") == "0", "JUNIT_FAILURES")
    require(suite.attrib.get("errors") == "0", "JUNIT_ERRORS")
    require(suite.attrib.get("skipped") == "0", "JUNIT_SKIPPED")
    require(len(suite.findall("testcase")) == 1793, "JUNIT_TESTCASES")
    warning_families = backend["inventory"]["warning_families"]
    require(sum(row["count"] for row in warning_families) == 25, "WARNING_TOTAL")
    require(backend["inventory"]["skip_owner"] == "none", "SKIP_OWNER")


def validate_phase_b(record: dict[str, Any]) -> None:
    phase_b = record["phase_b_static_readiness"]
    require(phase_b.get("status") == "PASS_STATIC_CONTRACT_EXTERNAL_EXECUTION_NOT_RUN", "PHASE_B_STATUS")
    require(phase_b.get("required_gap_count") == 6, "PHASE_B_GAP_COUNT")
    gaps = phase_b.get("required_gaps")
    require(isinstance(gaps, list), "PHASE_B_GAPS_TYPE")
    ids = [row.get("gap_id") for row in gaps if isinstance(row, dict)]
    require(len(ids) == 6 and len(ids) == len(set(ids)), "PHASE_B_GAP_DUPLICATE")
    require(set(ids) == EXPECTED_REQUIRED_GAPS, "PHASE_B_GAP_IDS")
    require(all(row.get("status") == "STATIC_CONTRACT_PASS" for row in gaps), "PHASE_B_GAP_STATUS")
    require(phase_b["focused_contract_tests"] == {"passed": 16, "failed": 0, "subtests_passed": 22}, "PHASE_B_TESTS")
    snapshot = load_json(ROOT / PHASE_B_REL)
    require(snapshot.get("status") == "PASS" and snapshot.get("authoritative") is False, "PHASE_B_SNAPSHOT")
    finding_ids = [row.get("check_id") for row in snapshot.get("findings", [])]
    require(len(finding_ids) == len(set(finding_ids)), "PHASE_B_FINDING_DUPLICATE")
    require(all(row.get("status") == "PASS" for row in snapshot.get("findings", [])), "PHASE_B_FINDING_STATUS")
    required_findings = {row["finding_id"] for row in gaps}
    require(required_findings.issubset(set(finding_ids)), "PHASE_B_FINDING_MISSING")
    external = phase_b["external_stage3_actions"]
    require(all(value.startswith("NOT_RUN") for value in external.values()), "PHASE_B_EXTERNAL_ACTION")
    with tempfile.TemporaryDirectory(prefix="mrw-source-static-check-") as temporary:
        output = Path(temporary) / "static.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/formal_release/check_static_production_contract.py"),
                "--repo-root",
                str(ROOT),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        require(completed.returncode == 0, f"PHASE_B_CURRENT_CHECKER:{completed.stderr.strip()}")
        require(load_json(output) == snapshot, "PHASE_B_CURRENT_SNAPSHOT_DRIFT")


def validate_changed_paths(record: dict[str, Any]) -> None:
    changed = record["changed_paths"]
    prior = changed["prior_residual_inventory"]
    prior_path = ROOT / prior["path"]
    require(prior_path.is_file(), "PRIOR_RESIDUAL_MISSING")
    require(sha256(prior_path) == prior["sha256"], "PRIOR_RESIDUAL_HASH")
    prior_json = load_json(prior_path)
    prior_entries = prior_json.get("entries")
    require(
        isinstance(prior_entries, list) and len(prior_entries) == prior.get("entry_count") == 105,
        "PRIOR_RESIDUAL_COUNT",
    )
    prior_paths = [row.get("path") for row in prior_entries if isinstance(row, dict)]
    require(len(prior_paths) == 105 and len(prior_paths) == len(set(prior_paths)), "PRIOR_RESIDUAL_DUPLICATES")
    require(
        all(isinstance(row.get("after_sha256"), str) and len(row["after_sha256"]) == 64 for row in prior_entries),
        "PRIOR_RESIDUAL_HASH_SCHEMA",
    )
    rows = changed.get("post_residual")
    require(
        isinstance(rows, list) and len(rows) == changed.get("post_residual_entry_count") == 25, "POST_RESIDUAL_COUNT"
    )
    paths = [row.get("path") for row in rows if isinstance(row, dict)]
    require(len(paths) == 25 and len(paths) == len(set(paths)), "POST_RESIDUAL_DUPLICATES")
    require(paths == sorted(paths), "POST_RESIDUAL_NOT_SORTED")
    allowed_before_sentinels = {"ABSENT", "UNKNOWN_NOT_ATTRIBUTED"}
    for row in rows:
        require(
            set(row) == {"path", "before_sha256", "current_sha256", "evidence", "workstream", "disposition"},
            f"POST_RESIDUAL_SCHEMA:{row.get('path')}",
        )
        before = row["before_sha256"]
        require(
            before in allowed_before_sentinels or (len(before) == 64 and all(c in "0123456789abcdef" for c in before)),
            f"BEFORE_HASH:{row['path']}",
        )
        path = ROOT / row["path"]
        require(path.is_file(), f"CURRENT_PATH_MISSING:{row['path']}")
        require(sha256(path) == row["current_sha256"], f"CURRENT_PATH_HASH:{row['path']}")
    startup_absent = {
        "main/backend/app/services/projects/schema_initialization.py",
        "main/backend/tests/integration/test_schema_startup_postgres_concurrency.py",
    }
    require(
        {row["path"] for row in rows if row["before_sha256"] == "ABSENT"} == startup_absent, "ABSENT_EVIDENCE_SCOPE"
    )


def validate_history(record: dict[str, Any]) -> None:
    disposition = record["binding_and_history_disposition"]
    registry = disposition["binding_registry"]
    require(registry.get("status") == "PASS_4_SOURCES_10_SUCCESSORS", "BINDING_STATUS")
    require(registry.get("authoritative") is False, "BINDING_AUTHORITY")
    require(sha256(ROOT / registry["path"]) == registry["sha256"], "BINDING_HASH")
    receipt_ref = disposition["historical_verification"]
    require(sha256(ROOT / receipt_ref["path"]) == receipt_ref["sha256"], "HISTORY_RECEIPT_HASH")
    receipt = load_json(ROOT / receipt_ref["path"])
    require(receipt.get("status") == "PASS", "HISTORY_RECEIPT_STATUS")
    require(
        receipt.get("conclusion") == "HISTORICAL_V3_V4_EXACT_AND_CLEAN_ALL_CONTRACT10_BOUND_HASHES_MATCH",
        "HISTORY_CONCLUSION",
    )
    candidates = {row["version"]: row for row in receipt.get("candidates", [])}
    require(set(candidates) == {"v3", "v4"}, "HISTORY_CANDIDATES")
    for version, expected in (
        ("v3", disposition["v3"]),
        ("v4", disposition["v4"]),
    ):
        row = candidates[version]
        require(row.get("actual_commit") == expected["commit"], f"HISTORY_COMMIT:{version}")
        require(row.get("actual_tree") == expected["tree"], f"HISTORY_TREE:{version}")
        require(row.get("clean_status") == "PASS", f"HISTORY_CLEAN:{version}")
        root = Path(row["root"])
        require(root.is_dir(), f"HISTORY_ROOT:{version}")
        completed = subprocess.run(
            ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", "rev-parse", "HEAD", "HEAD^{tree}"],
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            check=False,
            capture_output=True,
            text=True,
        )
        require(completed.returncode == 0, f"HISTORY_GIT:{version}")
        require(
            completed.stdout.splitlines() == [expected["commit"], expected["tree"]], f"HISTORY_LIVE_IDENTITY:{version}"
        )
    for evidence in receipt.get("stage2_evidence", []):
        expected = evidence.get("expected_sha256")
        if expected is not None:
            require(sha256(Path(evidence["path"])) == expected, f"HISTORY_EVIDENCE:{evidence['path']}")


def validate_record(record: dict[str, Any]) -> None:
    required_top = {
        "schema_version",
        "record_id",
        "status",
        "authoritative",
        "production_release_authorized",
        "contracts",
        "source_identity",
        "phase_a_source_closure",
        "phase_b_static_readiness",
        "binding_and_history_disposition",
        "changed_paths",
        "referenced_stage1_evidence",
        "preserved_evidence_ceiling",
        "external_effects",
        "cleanup_status",
        "remaining_gaps",
        "authority_ceiling",
    }
    require(set(record) == required_top, "RECORD_TOP_LEVEL_SCHEMA")
    require(record.get("schema_version") == "mrw.stage1.source_static_remediation_record.v1", "RECORD_SCHEMA")
    require(record.get("status") == "PASS_STAGE1_SOURCE_STATIC_REMEDIATION_NOT_AUTHORITY", "RECORD_STATUS")
    require(record.get("authoritative") is False, "RECORD_AUTHORITY")
    require(record.get("production_release_authorized") is False, "RELEASE_AUTHORITY")
    require(record.get("authority_ceiling") == AUTHORITY_CEILING, "RECORD_CEILING")
    identity = record["source_identity"]
    require(identity.get("head") == "3706655f372f6d34fc62683551b8c3d1f4ff8146", "SOURCE_HEAD")
    require(identity.get("tree") == "5840bf9ba906c49f70020d226c54446f4ba5aa33", "SOURCE_TREE")
    git = subprocess.run(
        ["git", "rev-parse", "HEAD", "HEAD^{tree}"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    require(git == [identity["head"], identity["tree"]], "SOURCE_IDENTITY_DRIFT")
    for ref in record["contracts"] + record["referenced_stage1_evidence"]:
        require(sha256(ROOT / ref["path"]) == ref["sha256"], f"REFERENCE_HASH:{ref['path']}")
    require(all(value is False for value in record["external_effects"].values()), "EXTERNAL_EFFECTS")
    require("PRODUCTION_RELEASE_NOT_AUTHORIZED" in record["remaining_gaps"], "RELEASE_GAP")
    require(
        record["preserved_evidence_ceiling"]["contract14_history_currently_qualified_nodeids"] == 0,
        "HISTORY_QUALIFICATION_CEILING",
    )
    require(
        record["preserved_evidence_ceiling"]["startup_skip_owner"]["status"] == "NOT_RUN_NOT_LIVE",
        "STARTUP_SKIP_CEILING",
    )
    validate_phase_a(record)
    validate_phase_b(record)
    validate_changed_paths(record)
    validate_history(record)


def validation_receipt(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "mrw.stage1.source_static_remediation_validation.v1",
        "status": "PASS",
        "authoritative": False,
        "record": {"path": RECORD_REL.as_posix(), "sha256": sha256(ROOT / RECORD_REL)},
        "artifact_manifest": {"path": MANIFEST_REL.as_posix(), "sha256": sha256(ROOT / MANIFEST_REL)},
        "checks": {
            "schema_fail_closed": True,
            "duplicate_paths_and_ids_rejected": True,
            "artifact_hashes_and_refs_match": True,
            "enumerated_current_paths_fresh": True,
            "prior_residual_inventory_hash_and_schema_match": True,
            "historical_v3_v4_identity_and_evidence_match": True,
            "phase_a_raw_log_and_junit_totals_match": True,
            "phase_b_six_required_gaps_pass_static_contract": True,
            "external_actions_remain_not_run": True,
            "authoritative_and_release_flags_false": True,
            "authority_ceiling_exact": True,
        },
        "authority_ceiling": AUTHORITY_CEILING,
    }


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def write_create_only(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-receipt", action="store_true")
    parser.add_argument("--check-receipt", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_json(ROOT / MANIFEST_REL)
    record = load_json(ROOT / RECORD_REL)
    validate_manifest(manifest)
    validate_record(record)
    receipt = validation_receipt(record)
    if args.write_receipt:
        write_create_only(ROOT / VALIDATION_REL, canonical_bytes(receipt))
    if args.check_receipt:
        require((ROOT / VALIDATION_REL).read_bytes() == canonical_bytes(receipt), "VALIDATION_RECEIPT_DRIFT")
    print(
        json.dumps(
            {
                "status": "PASS",
                "authoritative": False,
                "current_path_count": 25,
                "phase_a_passed": 1793,
                "phase_b_gap_count": 6,
                "authority_ceiling": AUTHORITY_CEILING,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError, ET.ParseError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1) from exc
