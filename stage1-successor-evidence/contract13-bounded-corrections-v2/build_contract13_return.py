#!/usr/bin/env python3
"""Create or verify the create-only Contract 13 bounded-correction return."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
TOP_LEVEL_OUTPUTS = {
    "changed-paths.v2.json",
    "artifact-manifest.v2.json",
    "return.v2.json",
    "return-validation.v2.json",
}
AUTHORITY_CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def load_json(relative_path: str) -> dict[str, Any]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def ref(relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    return {"path": relative_path, "sha256": sha256(path), "bytes": path.stat().st_size}


def input_ref(relative_path: str) -> dict[str, Any]:
    item = ref(relative_path)
    item.pop("bytes")
    return item


def evidence_members() -> list[Path]:
    members = []
    for path in OUT.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.parent == OUT and path.name in TOP_LEVEL_OUTPUTS:
            continue
        members.append(path)
    return sorted(members, key=lambda path: path.relative_to(ROOT).as_posix())


def build_changed_paths() -> dict[str, Any]:
    entries = []
    for path in evidence_members():
        relative = path.relative_to(ROOT).as_posix()
        entries.append(
            {
                "path": relative,
                "change_kind": "CREATE_ONLY",
                "before_sha256": None,
                "after_sha256": sha256(path),
                "bytes": path.stat().st_size,
                "scope": "contract_13_bounded_evidence_correction",
            }
        )
    return {
        "schema_version": "mrw.stage1.contract13.changed-paths.v2",
        "authoritative": False,
        "authority_ceiling": AUTHORITY_CEILING,
        "entry_count": len(entries),
        "entries": entries,
        "product_or_historical_candidate_files_mutated_by_contract_13": False,
        "note": (
            "This list covers create-only Contract 13 evidence members. Product changes inherited "
            "from Contract 12 remain frozen in changed-paths.v1.json and were audited read-only."
        ),
    }


def build_manifest(changed_paths_bytes: bytes) -> dict[str, Any]:
    artifacts = [ref(path.relative_to(ROOT).as_posix()) for path in evidence_members()]
    changed_path = OUT / "changed-paths.v2.json"
    artifacts.append(
        {
            "path": changed_path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(changed_paths_bytes).hexdigest(),
            "bytes": len(changed_paths_bytes),
        }
    )
    artifacts.sort(key=lambda item: item["path"])
    return {
        "schema_version": "mrw.stage1.contract13.artifact-manifest.v2",
        "authoritative": False,
        "authority_ceiling": AUTHORITY_CEILING,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "excluded_non_evidence": ["__pycache__", "*.pyc", *sorted(TOP_LEVEL_OUTPUTS - {"changed-paths.v2.json"})],
    }


def build_return(changed_paths_bytes: bytes, manifest_bytes: bytes) -> dict[str, Any]:
    process_path = "stage1-successor-evidence/contract13-bounded-corrections-v2/process-api/process-task-id-fallback-disposition.v2.json"
    process_witness = "stage1-successor-evidence/contract13-bounded-corrections-v2/process-api/process-task-id-overlay-witness-results.v2.json"
    historical_path = "stage1-successor-evidence/contract13-bounded-corrections-v2/historical-candidates/historical-candidates-readonly-verification.v1.json"
    binding_path = "stage1-successor-evidence/contract13-bounded-corrections-v2/binding-impact/binding-impact-audit.corrected.v2.json"
    binding_validation = "stage1-successor-evidence/contract13-bounded-corrections-v2/binding-impact/binding-impact-audit.validation.corrected.v2.json"
    startup_path = "stage1-successor-evidence/contract13-bounded-corrections-v2/startup-preservation/startup-preservation.v2.json"
    claims_path = "stage1-successor-evidence/contract13-bounded-corrections-v2/claim-decisions/claim-decisions.v2.json"
    claims_validation = "stage1-successor-evidence/contract13-bounded-corrections-v2/claim-decisions/validation-receipt.v2.json"
    process = load_json(process_path)
    witness = load_json(process_witness)
    historical = load_json(historical_path)
    historical_candidates = {item["version"]: item for item in historical["candidates"]}
    binding = load_json(binding_path)
    startup = load_json(startup_path)
    claims = load_json(claims_path)
    return {
        "schema_version": "mrw.stage1.contract13.return.v2",
        "RETURN_RESULT": "BLOCKED",
        "authoritative": False,
        "authority_ceiling": AUTHORITY_CEILING,
        "return_scope": "CONTRACT_13_BOUNDED_CORRECTIONS_ONLY",
        "input_source_identity_and_hashes": {
            "contract_10": input_ref("development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/10_stage1-stage2-source-and-static-closure-return-contract.v1.md"),
            "contract_11": input_ref("development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/11_stage1-backend-unit-remediation-return-contract.v1.md"),
            "contract_12": input_ref("development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/12_stage1-residual-disposition-return-contract.v1.md"),
            "contract_13": input_ref("development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/13_contract12-supervisor-review-and-return.v1.md"),
            "contract_12_return": input_ref("stage1-successor-evidence/residual-disposition-v1/return.v1.json"),
            "contract_12_validation": input_ref("stage1-successor-evidence/residual-disposition-v1/return-validation.v1.json"),
            "process_py": input_ref("main/backend/app/api/process.py"),
        },
        "changed_paths": {
            "path": (OUT / "changed-paths.v2.json").relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(changed_paths_bytes).hexdigest(),
            "entry_count": len(json.loads(changed_paths_bytes)["entries"]),
        },
        "artifact_manifest": {
            "path": (OUT / "artifact-manifest.v2.json").relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "artifact_count": len(json.loads(manifest_bytes)["artifacts"]),
        },
        "bounded_corrections": {
            "process_api": {
                "status": process["status"],
                "disposition": "CORRECTION_REQUIRED",
                "receipt": input_ref(process_path),
                "isolated_witness": input_ref(process_witness),
                "query_default_direct_call": {
                    "type": witness["query_default"]["type"],
                    "repr": witness["query_default"]["repr"],
                    "truthy": witness["query_default"]["truthy"],
                    "is_none": witness["query_default"]["is_none"],
                    "interpretation": witness["query_default"]["interpretation"]["direct_python_omitted"],
                },
                "source_mutated": False,
                "current_sha256": sha256(ROOT / "main/backend/app/api/process.py"),
                "proposed_sha256": process["proposed_source_transition"]["proposed_after_sha256"],
            },
            "historical_stage2_candidates": {
                "status": historical["status"],
                "disposition": "READ_ONLY_VERIFIED",
                "receipt": input_ref(historical_path),
                "v3_commit": historical_candidates["v3"]["actual_commit"],
                "v3_tree": historical_candidates["v3"]["actual_tree"],
                "v4_commit": historical_candidates["v4"]["actual_commit"],
                "v4_tree": historical_candidates["v4"]["actual_tree"],
                "historical_roots_mutated": False,
            },
            "binding_impact": {
                "status": binding["status"],
                "disposition": "CORRECTION_REQUIRED_ADDITIVE_REBIND_NOT_AUTHORIZED",
                "canonical_receipt": input_ref(binding_path),
                "validation": input_ref(binding_validation),
                "summary": binding["summary"],
                "superseded_initial_receipt_retained": True,
                "binding_or_registry_write": False,
            },
            "startup_preservation": {
                "status": startup["status"],
                "disposition": "BOUNDED_LOCAL_REPAIR_EVIDENCE_WITH_EXPLICIT_GAPS",
                "receipt": input_ref(startup_path),
                "proven": ["FASTAPI_STARTUP_ORDER", "SINGLE_PROCESS_FIRST_OPERATION_FAIL_CLOSED_FALLBACK_RETRY", "SINGLE_PROCESS_CONCURRENT_FIRST_USE"],
                "local_acceptance_gaps": ["CELERY_AND_GENERIC_CLI_SCHEMA_INITIALIZATION", "CROSS_PROCESS_POSTGRES_DDL_RACE_AND_FAILURE_RECOVERY"],
                "shared_runtime_mutated_by_contract_13": False,
            },
            "factual_claim_decisions": {
                "status": claims["status"],
                "disposition": "EVIDENCE_GENERATION_AND_EXTERNAL_AUTHORITY_PARTITIONED",
                "receipt": input_ref(claims_path),
                "validation": input_ref(claims_validation),
                "summary": claims["summary"],
                "fresh_proposals_executed": False,
                "live_observations_executed": False,
                "deleted_evidence_restored": False,
            },
        },
        "backend_unit_gate_result": {
            "status": "FAIL_RETAINED_NOT_RERUN",
            "selector": "unit and not external and not flaky",
            "last_completed_execution": {"failed": 55, "passed": 1712, "skipped": 0, "deselected": 2328, "warnings": 14, "subtests_passed": 42, "exit_code": 1},
            "rerun_reason": "Contract 13 directs focused verification while known factual blockers remain.",
        },
        "evidence_authority_partition": {
            "bounded_local_repairs_completed": ["process_api_behavioral_correction_receipt", "historical_candidate_read_only_verification", "binding_impact_audit", "startup_preservation_isolated_analysis", "claim_level_decision_table"],
            "fresh_local_deterministic_evidence_proposals": {"claim_count": 8, "dependent_nodeid_count": 13, "executed": False},
            "actual_historical_receipt_requirements": {"claim_count": 5, "dependent_nodeid_count": 8, "recovered": False},
            "live_observation_requirements": {"claim_count": 3, "dependent_nodeid_count": 9, "executed": False},
            "genuinely_missing_human_or_external_authority": ["PROCESS_API_ADDITIVE_EXACT_BYTE_REBIND", "HISTORICAL_RECEIPT_RECOVERY_OR_REBIND", "LIVE_PROVIDER_OR_DATABASE_OBSERVATION"],
            "synthetic_fixture_may_close_factual_claim": False,
        },
        "source_closure_checker_and_results": "UNCHANGED_FROM_CONTRACT_12_FOCUSED_PASS_NOT_STAGE1_ACCEPTANCE",
        "static_stage3_readiness_results": "NOT_RUN_PHASE_A_UNACCEPTED",
        "stage1_remediation_record_and_sha256": None,
        "stage1_focused_tests_lint_compile": {
            "contract_13_process_witness": "PASS_6_ASSERTIONS",
            "contract_13_binding_check": "PASS_105_OF_105_91_OF_91_8_OF_8",
            "contract_13_claim_decision_check": "PASS_30_NODEIDS_EXACTLY_ONCE",
            "contract_13_startup_witness": "12_PASSED_10_WARNINGS",
            "full_selector": "NOT_RERUN_BY_CONTRACT_13",
        },
        "historical_v3_v4_unchanged": {"status": "PASS", "receipt": input_ref(historical_path), "task_writes": False},
        "successor_candidate_root": None,
        "successor_commit": None,
        "successor_tree": None,
        "successor_manifest_path_and_sha256": None,
        "successor_closure_path_and_sha256": None,
        "successor_r1_r2_r3_paths_and_sha256": None,
        "successor_record_path_and_sha256": None,
        "primary_replay_receipts_and_sha256": None,
        "v5_fresh_checks": "NOT_RUN_PHASE_A_UNACCEPTED",
        "warning_skip_deselect_inventory": {"scope": "last completed required-selector execution", "skipped": 0, "deselected": 2328, "warnings": 14},
        "external_effects": {"network": False, "live_database": False, "live_provider": False, "historical_candidate_import": False, "external_delivery": False},
        "cleanup_and_recovery_status": {
            "destructive_cleanup": False,
            "historical_restore": False,
            "generated_cache_removed": True,
            "v1_package_retained": True,
            "initial_invalid_integration_outputs_retained": True,
            "initial_invalid_reason": "Validation checked the virtual changed-path artifact before first write; the four original bytes are retained under initial-invalid and are not canonical.",
        },
        "residual_blockers": [
            {"blocker": "PROCESS_API_EXACT_BYTE_REBIND_REQUIRED", "disposition": "CORRECTION_REQUIRED", "phase_b_c_v5_gated": True},
            {"blocker": "TWO_CURRENT_BINDING_DRIFTS_REQUIRE_ADDITIVE_SUCCESSORS", "paths": ["main/backend/app/models/base.py", "main/backend/app/services/workflow_graph/runtime.py"], "phase_b_c_v5_gated": True},
            {"blocker": "FACTUAL_EVIDENCE_NOT_YET_SATISFIED", "fresh_local_nodeids": 13, "historical_receipt_nodeids": 8, "live_observation_nodeids": 9, "phase_b_c_v5_gated": True},
            {"blocker": "STARTUP_PRESERVATION_LOCAL_ACCEPTANCE_GAPS", "gaps": ["CELERY_AND_GENERIC_CLI_SCHEMA_INITIALIZATION", "CROSS_PROCESS_POSTGRES_DDL_RACE_AND_FAILURE_RECOVERY"], "phase_b_c_v5_gated": True},
            {"blocker": "REQUIRED_SELECTOR_NOT_GREEN", "last_exit_code": 1, "phase_b_c_v5_gated": True},
        ],
        "phase_b_c_v5_gated": True,
        "recommended_next_action": (
            "Supervisor should accept or revise this bounded v2 disposition, authorize only the "
            "necessary additive rebinds, and separately authorize fresh deterministic generation, "
            "historical receipt recovery, or live observation by claim class. Do not rerun the full "
            "selector or create v5 until factual blockers and startup acceptance gaps are resolved."
        ),
    }


def validate(
    changed_paths: dict[str, Any], manifest: dict[str, Any], return_value: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    if any("__pycache__" in path.parts or path.suffix == ".pyc" for path in OUT.rglob("*")):
        errors.append("generated cache exists under Contract 13 evidence root")
    changed_path_relative = (OUT / "changed-paths.v2.json").relative_to(ROOT).as_posix()
    changed_path_payload = json_bytes(changed_paths)
    for item in manifest["artifacts"]:
        if item["path"] == changed_path_relative:
            if hashlib.sha256(changed_path_payload).hexdigest() != item["sha256"] or len(changed_path_payload) != item["bytes"]:
                errors.append("virtual changed-path artifact hash or size mismatch")
            continue
        path = ROOT / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            errors.append(f"artifact missing or drifted: {item['path']}")
    if changed_paths["entry_count"] != len(changed_paths["entries"]):
        errors.append("changed-path entry count mismatch")
    if return_value["input_source_identity_and_hashes"]["process_py"]["sha256"] != "790b6cb90086d6ba1171309e572b7e7be4c906db3705170dbd4a12ca7ea16c63":
        errors.append("process.py drifted from Contract 13 input binding")
    if return_value["bounded_corrections"]["historical_stage2_candidates"]["v3_commit"] != "f8d84afc2784cf91784da957e353e2b0c0d6952c":
        errors.append("v3 commit mismatch")
    if return_value["bounded_corrections"]["historical_stage2_candidates"]["v3_tree"] != "1be3dcbc009332ec225297d1b94430862287d816":
        errors.append("v3 tree mismatch")
    if return_value["bounded_corrections"]["historical_stage2_candidates"]["v4_commit"] != "e1aa59708a22e4238c4d9beaf7b7bd2d2095d483":
        errors.append("v4 commit mismatch")
    if return_value["bounded_corrections"]["historical_stage2_candidates"]["v4_tree"] != "d2003fbb8e54c8dd743fa4e84907a8a978ef5107":
        errors.append("v4 tree mismatch")
    binding_summary = return_value["bounded_corrections"]["binding_impact"]["summary"]
    if [binding_summary[key] for key in ("changed_path_entry_count", "code_contract_checker_audited_count", "import_boundary_path_count", "drifted_bound_path_count")] != [105, 91, 8, 2]:
        errors.append("binding audit summary mismatch")
    claim_summary = return_value["bounded_corrections"]["factual_claim_decisions"]["summary"]
    if claim_summary["inventory_missing_evidence_nodeid_count"] != 30 or not claim_summary["nodeids_covered_exactly_once"]:
        errors.append("claim decision coverage mismatch")
    if return_value["RETURN_RESULT"] != "BLOCKED" or not return_value["phase_b_c_v5_gated"]:
        errors.append("return incorrectly widens acceptance")
    return errors


def expected_documents() -> dict[str, bytes]:
    changed_paths = build_changed_paths()
    changed_paths_bytes = json_bytes(changed_paths)
    manifest = build_manifest(changed_paths_bytes)
    manifest_bytes = json_bytes(manifest)
    return_value = build_return(changed_paths_bytes, manifest_bytes)
    return_bytes = json_bytes(return_value)
    errors = validate(changed_paths, manifest, return_value)
    validation = {
        "schema_version": "mrw.stage1.contract13.return-validation.v2",
        "status": "PASS" if not errors else "FAIL",
        "authoritative": False,
        "authority_ceiling": AUTHORITY_CEILING,
        "errors": errors,
        "return_path": (OUT / "return.v2.json").relative_to(ROOT).as_posix(),
        "return_sha256": hashlib.sha256(return_bytes).hexdigest(),
        "artifact_count": manifest["artifact_count"],
        "changed_path_count": changed_paths["entry_count"],
        "checks": {
            "artifact_hashes_and_sizes_match": not any(error.startswith("artifact") for error in errors),
            "process_py_input_binding_matches": not any("process.py" in error for error in errors),
            "historical_v3_v4_identities_match": not any(error.startswith(("v3", "v4")) for error in errors),
            "binding_coverage_is_105_91_8_with_2_drifts": not any("binding audit" in error for error in errors),
            "claim_nodeids_partition_30_exactly_once": not any("claim decision" in error for error in errors),
            "phase_b_c_v5_remain_gated": return_value["phase_b_c_v5_gated"],
            "no_generated_cache": not any("cache" in error for error in errors),
        },
    }
    return {
        "changed-paths.v2.json": changed_paths_bytes,
        "artifact-manifest.v2.json": manifest_bytes,
        "return.v2.json": return_bytes,
        "return-validation.v2.json": json_bytes(validation),
    }


def write_create_only(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    documents = expected_documents()
    if args.check:
        for name, payload in documents.items():
            path = OUT / name
            if not path.is_file() or path.read_bytes() != payload:
                raise SystemExit(f"DRIFT: {name}")
        print("PASS: Contract 13 v2 return is deterministic and internally consistent")
        return 0
    existing = [name for name in documents if (OUT / name).exists()]
    if existing:
        raise SystemExit(f"TARGET_ALREADY_EXISTS: {', '.join(existing)}")
    for name, payload in documents.items():
        write_create_only(OUT / name, payload)
    print("CREATED: " + ", ".join(documents))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
