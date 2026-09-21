#!/usr/bin/env python3
"""Build the create-only Contract 14 integration return."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)
GENERATED = {
    "artifact-manifest.v1.json",
    "changed-paths.v1.json",
    "return-validation.v1.json",
    "return.v1.json",
    "supervisor-dispatch-receipt.v1.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: str | Path) -> Any:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return json.loads(candidate.read_text(encoding="utf-8"))


def ref(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return {
        "path": candidate.relative_to(ROOT).as_posix(),
        "sha256": sha256(candidate),
        "bytes": candidate.stat().st_size,
    }


def write_create_only(path: Path, payload: Any) -> bytes:
    if path.exists():
        raise SystemExit(f"TARGET_ALREADY_EXISTS: {path}")
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(data)
    return data


def artifact_paths(*, include_changed_paths: bool) -> list[Path]:
    result: list[Path] = []
    for path in OUT.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.parent == OUT and path.name in GENERATED:
            if include_changed_paths and path.name == "changed-paths.v1.json":
                result.append(path)
            continue
        result.append(path)
    return sorted(result)


def claim_index(claim_table: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {claim["claim_id"]: claim for claim in claim_table["claims"]}


def claim_row(
    claim: dict[str, Any],
    *,
    status: str,
    execution: str,
    evidence: list[dict[str, Any]],
    blockers: list[str] | None = None,
    actual_scope: str | None = None,
) -> dict[str, Any]:
    return {
        "claim_id": claim["claim_id"],
        "claim_key": claim["claim_key"],
        "decision": claim["decision"],
        "status": status,
        "execution": execution,
        "dependent_nodeids": claim["dependent_nodeids"],
        "dependent_nodeid_count": len(claim["dependent_nodeids"]),
        "actual_scope": actual_scope,
        "evidence": evidence,
        "blockers": blockers or [],
        "authoritative": False,
        "current_qualification_granted": False,
        "production_release_authorized": False,
    }


def main() -> None:
    contract14_path = (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/"
        "14_stage1-local-evidence-execution-contract.v1.md"
    )
    return13_path = (
        "stage1-successor-evidence/contract13-bounded-corrections-v2/return.v2.json"
    )
    claims_path = (
        "stage1-successor-evidence/contract13-bounded-corrections-v2/"
        "claim-decisions/claim-decisions.v2.json"
    )
    history_path = (
        "stage1-successor-evidence/contract14-local-execution-v1/history/"
        "history-verification-receipt.v1.json"
    )
    vector_path = (
        "stage1-successor-evidence/contract14-local-execution-v1/local/"
        "vector-upstream/receipt.json"
    )
    claim003_path = (
        "stage1-successor-evidence/contract14-local-execution-v1/local/"
        "claim-003/execution-receipt.json"
    )
    claim003_validation = (
        "stage1-successor-evidence/contract14-local-execution-v1/local/"
        "claim-003/execution-validation.v1.json"
    )
    wave55_path = (
        "stage1-successor-evidence/contract14-local-execution-v1/local/"
        "search-quality/wave55/execution-receipt.json"
    )
    wave57_path = (
        "stage1-successor-evidence/contract14-local-execution-v1/local/"
        "search-quality/wave57/execution-receipt.json"
    )

    expected_inputs = {
        contract14_path: "3252e21452e78c73fc9fef9b8b7435c2c3e0ab4466a6b411fe567010d4ea28e7",
        return13_path: "0b9dda0595b84176bd38c60b69030b930a128146c98a8da893ce4aec897b1bbc",
        claims_path: "8362b368b5f4d944bb1bddf70f397e73c1b3716bc0bdb6244e61699b38e719b3",
    }
    for path, expected in expected_inputs.items():
        actual = sha256(ROOT / path)
        if actual != expected:
            raise SystemExit(f"INPUT_DRIFT: {path}: expected {expected}, got {actual}")

    claim_table = load_json(claims_path)
    claims = claim_index(claim_table)
    history = load_json(history_path)
    vector = load_json(vector_path)
    claim003 = load_json(claim003_path)
    wave55 = load_json(wave55_path)
    wave57 = load_json(wave57_path)

    dispositions: list[dict[str, Any]] = []
    dispositions.append(
        claim_row(
            claims["claim-003"],
            status="COMPLETED_LOCAL_DETERMINISTIC",
            execution="EXECUTED_EXIT_0",
            evidence=[ref(claim003_path), ref(claim003_validation), ref(OUT / "local/claim-003/report.json")],
            actual_scope=claim003["scope"],
        )
    )
    for claim_id in ("claim-005", "claim-008"):
        vector_claim = vector["claims"][claim_id]
        dispositions.append(
            claim_row(
                claims[claim_id],
                status="BLOCKED_LOCAL_OBSERVATION_RETAINED",
                execution="EXECUTED_NONZERO_RETAINED",
                evidence=[ref(vector_path)],
                blockers=vector_claim["blockers"],
                actual_scope=vector_claim["scope"],
            )
        )
    downstream_blockers = {
        "claim-009": [
            "Fresh Wave8 receipt unavailable; historical claim-016 PASS was not reused.",
            "Fresh Wave10 and Wave12 prerequisites failed.",
            "Fresh Wave14 status is failed and closure_claim_allowed=false.",
        ],
        "claim-010": ["Fresh Wave14 failed; fresh Wave18 was not executed because its prerequisites failed."],
        "claim-011": ["Fresh Wave19 was not executed because fresh Wave14/Wave18 prerequisites were unavailable."],
    }
    for claim_id in ("claim-009", "claim-010", "claim-011"):
        dispositions.append(
            claim_row(
                claims[claim_id],
                status="BLOCKED_BY_FAILED_FRESH_PREREQUISITE",
                execution="NOT_RUN_FAIL_CLOSED",
                evidence=[ref(vector_path)],
                blockers=downstream_blockers[claim_id],
                actual_scope="No downstream generator executed; no historical receipt substituted.",
            )
        )
    dispositions.append(
        claim_row(
            claims["claim-013"],
            status="COMPLETED_LOCAL_DETERMINISTIC",
            execution="EXECUTED_EXIT_0",
            evidence=[ref(wave55_path), ref(OUT / "local/search-quality/wave55/oss_node_search_quality_gate.json")],
            actual_scope=wave55["scope"],
        )
    )
    dispositions.append(
        claim_row(
            claims["claim-015"],
            status="COMPLETED_LOCAL_DETERMINISTIC",
            execution="EXECUTED_EXIT_0",
            evidence=[ref(wave57_path), ref(OUT / "local/search-quality/wave57/oss_node_public_corpus_semantic_relevance_gate.json")],
            actual_scope=wave57["scope"],
        )
    )

    history_by_id = {row["claim_id"]: row for row in history["claims"]}
    for claim_id in ("claim-001", "claim-002", "claim-004", "claim-014", "claim-016"):
        history_claim = history_by_id[claim_id]
        dispositions.append(
            claim_row(
                claims[claim_id],
                status="HISTORY_INSPECTED_CURRENT_QUALIFICATION_NOT_GRANTED",
                execution="GIT_OBJECT_READ_ONLY",
                evidence=[ref(history_path)],
                blockers=history_claim["gaps_and_contradictions"],
                actual_scope=json.dumps(history_claim["four_layer_assessment"], sort_keys=True),
            )
        )

    for claim_id in ("claim-006", "claim-007", "claim-012"):
        dispositions.append(
            claim_row(
                claims[claim_id],
                status="OPEN_LIVE_OBSERVATION_REQUIRED",
                execution="NOT_RUN_ZERO_LIVE_EXECUTION",
                evidence=[],
                blockers=["Contract 14 does not authorize live database/provider/platform execution."],
                actual_scope="No live observation was attempted.",
            )
        )

    dispositions.sort(key=lambda row: row["claim_id"])
    all_nodeids = [nodeid for row in dispositions for nodeid in row["dependent_nodeids"]]
    expected_nodeids = [nodeid for claim in claim_table["claims"] for nodeid in claim["dependent_nodeids"]]
    if sorted(all_nodeids) != sorted(expected_nodeids) or len(all_nodeids) != len(set(all_nodeids)):
        raise SystemExit("CLAIM_COVERAGE_INVALID")

    payload_paths = artifact_paths(include_changed_paths=False)
    changed = {
        "schema_version": "mrw.stage1.contract14.changed-paths.v1",
        "authoritative": False,
        "authority_ceiling": CEILING,
        "entry_count": len(payload_paths),
        "entries": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "change_kind": "CREATE_ONLY",
                "before_sha256": None,
                "after_sha256": sha256(path),
                "bytes": path.stat().st_size,
                "scope": "contract_14_local_execution_evidence",
            }
            for path in payload_paths
        ],
    }
    changed_bytes = write_create_only(OUT / "changed-paths.v1.json", changed)

    manifest_paths = artifact_paths(include_changed_paths=True)
    manifest = {
        "schema_version": "mrw.stage1.contract14.artifact-manifest.v1",
        "authoritative": False,
        "authority_ceiling": CEILING,
        "artifact_count": len(manifest_paths),
        "artifacts": [ref(path) for path in manifest_paths],
        "excluded_non_evidence": [
            "__pycache__",
            "*.pyc",
            "artifact-manifest.v1.json",
            "return-validation.v1.json",
            "return.v1.json",
            "supervisor-dispatch-receipt.v1.json",
        ],
    }
    manifest_bytes = write_create_only(OUT / "artifact-manifest.v1.json", manifest)

    return_payload = {
        "schema_version": "mrw.stage1.contract14.return.v1",
        "RETURN_RESULT": "BLOCKED",
        "return_scope": "CONTRACT_14_LOCAL_EXECUTION_AND_HISTORY_INSPECTION_ONLY",
        "authoritative": False,
        "production_release_authorized": False,
        "authority_ceiling": CEILING,
        "input_source_identity_and_hashes": {
            "contract_14": ref(contract14_path),
            "contract_13_return": ref(return13_path),
            "claim_table": ref(claims_path),
        },
        "changed_paths": {
            "path": (OUT / "changed-paths.v1.json").relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(changed_bytes).hexdigest(),
            "entry_count": changed["entry_count"],
        },
        "artifact_manifest": {
            "path": (OUT / "artifact-manifest.v1.json").relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "artifact_count": manifest["artifact_count"],
        },
        "claim_dispositions": dispositions,
        "claim_summary": {
            "claim_count": len(dispositions),
            "dependent_nodeid_count": len(all_nodeids),
            "nodeids_covered_exactly_once": True,
            "completed_local_claims": ["claim-003", "claim-013", "claim-015"],
            "blocked_local_claims": ["claim-005", "claim-008", "claim-009", "claim-010", "claim-011"],
            "history_inspected_claims": ["claim-001", "claim-002", "claim-004", "claim-014", "claim-016"],
            "open_live_claims": ["claim-006", "claim-007", "claim-012"],
            "completed_local_nodeid_count": 4,
            "blocked_local_nodeid_count": 9,
            "history_nodeid_count": 8,
            "open_live_nodeid_count": 9,
        },
        "history_verification": {
            "receipt": ref(history_path),
            "status": history["status"],
            "summary": history["summary"],
            "four_levels": {
                "object_bytes": "32/32 unique objects exist as blobs; 62/62 requirements parseable.",
                "stored_assertions": "Recorded per claim without treating assertions as execution truth.",
                "independent_run_identity": "Only crawler public output/log has partial corroboration.",
                "current_qualification": "0 nodeids granted current qualification.",
            },
        },
        "focused_verification": {
            "claim_003": "generator exit 0; receipt validation PASS",
            "vector_upstream": vector["verification"],
            "search_quality": "13 focused tests passed; wrapper ruff and py_compile passed; receipt hash and unique-ID checks passed",
            "history": "validator PASS; ruff PASS; py_compile PASS; deterministic replay byte-identical",
            "full_selector": "NOT_RERUN_BY_CONTRACT_14",
        },
        "resource_cleanup": {
            "temporary_resources_removed": True,
            "generated_cache_removed": True,
            "destructive_cleanup": False,
            "historical_restore": False,
            "downstream_vector_generators_executed": False,
        },
        "external_effects": {
            "network": False,
            "dns": False,
            "live_database": False,
            "live_provider": False,
            "containers_or_services_started": False,
            "model_download": False,
            "external_delivery": False,
            "production_write": False,
        },
        "unchanged_source_runtime_and_bindings": {
            "process_py": ref("main/backend/app/api/process.py"),
            "models_base_py": ref("main/backend/app/models/base.py"),
            "workflow_graph_runtime_py": ref("main/backend/app/services/workflow_graph/runtime.py"),
            "contract_14_modified": False,
            "binding_or_registry_write": False,
        },
        "historical_v3_v4_unchanged": {
            "status": "PASS_RECHECKED_READ_ONLY",
            "v3": {
                "commit": "f8d84afc2784cf91784da957e353e2b0c0d6952c",
                "tree": "1be3dcbc009332ec225297d1b94430862287d816",
                "dirty_path_count": 0,
            },
            "v4": {
                "commit": "e1aa59708a22e4238c4d9beaf7b7bd2d2095d483",
                "tree": "d2003fbb8e54c8dd743fa4e84907a8a978ef5107",
                "dirty_path_count": 0,
            },
            "task_writes": False,
        },
        "backend_unit_gate_result": "FAIL_RETAINED_55_FAILED_1712_PASSED_NOT_RERUN",
        "phase_b_c_v5_gated": True,
        "residual_blockers": [
            "PROCESS_API_EXACT_BYTE_REBIND_REQUIRED",
            "TWO_CURRENT_BINDING_DRIFTS_REQUIRE_ADDITIVE_SUCCESSORS",
            "CELERY_AND_GENERIC_CLI_SCHEMA_INITIALIZATION",
            "CROSS_PROCESS_POSTGRES_DDL_RACE_AND_FAILURE_RECOVERY",
            "LANCEDB_VECTOR_DIMENSION_MISMATCH_8_VS_512",
            "FRESH_WAVE8_WAVE10_WAVE12_WAVE14_CHAIN_UNAVAILABLE_FOR_CLAIMS_009_010_011",
            "HISTORICAL_REVIEW_RUN_AND_LINEAGE_GAPS_FOR_CLAIMS_001_002_004_014_016",
            "LIVE_OBSERVATIONS_OPEN_FOR_CLAIMS_006_007_012",
            "FULL_SELECTOR_RETAINS_55_FAILURES",
        ],
        "supervisor_dispatch": "PENDING_ACTUAL_SUCCESSFUL_TASK_MESSAGE",
        "recommended_next_action": (
            "Supervisor should disposition the LanceDB 8-vs-512 vector mismatch and the existing additive rebind/startup gaps. "
            "Do not enter Phase B/C or create v5; authorize live work separately by claim if desired."
        ),
    }
    write_create_only(OUT / "return.v1.json", return_payload)


if __name__ == "__main__":
    main()
