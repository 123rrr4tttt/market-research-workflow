#!/usr/bin/env python3
"""Build the create-only Contract 12 residual disposition return package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
CONTRACT_DIR = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release"
)
CONTRACT_10 = CONTRACT_DIR / "10_stage1-stage2-source-and-static-closure-return-contract.v1.md"
CONTRACT_11 = CONTRACT_DIR / "11_stage1-backend-unit-remediation-return-contract.v1.md"
CONTRACT_12 = CONTRACT_DIR / "12_stage1-residual-disposition-return-contract.v1.md"
AUTHORITY_CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)


EARLIER_REMEDIATION_PATHS = [
    "main/backend/tests/unit/test_resource_pool_unified_search_unittest.py",
    "main/backend/app/services/agent_runtime/read_only_tools.py",
    "main/backend/tests/unit/test_agent_core_unittest.py",
    "main/backend/scripts/check_crawler_policy_matrix.py",
    "main/backend/scripts/check_meaningful_ingest_source_policy_attachment.py",
    "main/backend/app/models/base.py",
    "main/backend/app/startup_hooks.py",
    "main/backend/app/services/workflow_graph/__init__.py",
    "main/backend/app/services/workflow_graph/runtime.py",
    "main/backend/app/services/workflow_graph/executors/__init__.py",
    "main/backend/app/services/workflow_graph/handoff_store.py",
    "main/backend/tests/unit/test_schema_startup_boundary_unittest.py",
    "main/backend/tests/unit/test_workflow_graph_import_boundary_unittest.py",
    "main/backend/tests/successor_runtime/i1_binding_candidate_support.py",
    "main/backend/tests/successor_runtime/test_i1_micro_specimens.py",
    "main/backend/tests/successor_runtime/test_i1_rollback_rehearsal.py",
    "main/backend/tests/unit/test_interactive_agent_runtime_unittest.py",
    "main/backend/tests/unit/test_policy_indexer_vector_contract_unittest.py",
    "scripts/formal_release/source_closure.py",
    "scripts/formal_release/stage2_candidate_intake.py",
    "scripts/formal_release/materialize_stage2_candidate.py",
    "tests/formal_release/test_source_closure.py",
    "tests/formal_release/test_stage2_candidate_intake.py",
    "tests/formal_release/test_materialize_stage2_candidate.py",
    "main/backend/tests/unit/test_raw_import_structuring_unittest.py",
    "main/backend/tests/unit/test_source_library_real_probe_fixture_unittest.py",
    "main/backend/scripts/check_graph_typed_writing_consumer_status_boundary.py",
    "main/backend/tests/unit/test_graph_typed_writing_consumer_status_boundary_unittest.py",
    "main/backend/scripts/check_ingest_canary_closure_readiness.py",
    "main/backend/tests/unit/test_ingest_canary_closure_readiness_unittest.py",
    "main/backend/scripts/check_typed_writing_live_boundary.py",
    "main/backend/tests/unit/test_typed_writing_live_boundary_checker_unittest.py",
    "main/backend/app/services/workflow_graph/governance_contract.py",
]

CRAWLER_SOURCE_PATHS = [
    "main/backend/scripts/check_evidence_source_availability.py",
    "main/backend/scripts/build_crawler_public_replay_shard_outputs.py",
    "main/backend/scripts/check_crawler_public_replay_gate.py",
    "main/backend/scripts/check_crawler_public_replay_shards.py",
    "main/backend/scripts/check_crawler_source_expansion_closure.py",
    "main/backend/scripts/check_llm_crawler_replay_fixture.py",
    "main/backend/scripts/check_llm_crawler_replay_manifest.py",
    "main/backend/scripts/check_source_library_public_replay_a5_gate.py",
    "main/backend/scripts/check_source_library_review_closure_batch.py",
    "main/backend/scripts/check_source_library_review_closure_batch2.py",
    "main/backend/scripts/check_source_library_review_closure_batch3.py",
    "main/backend/scripts/check_source_library_review_closure_batch4.py",
    "main/backend/scripts/check_source_library_search_governance.py",
    "main/backend/tests/unit/test_build_crawler_public_replay_shard_outputs_unittest.py",
    "main/backend/tests/unit/test_crawler_public_replay_gate_unittest.py",
    "main/backend/tests/unit/test_crawler_public_replay_shards_unittest.py",
    "main/backend/tests/unit/test_crawler_source_expansion_closure_check_unittest.py",
    "main/backend/tests/unit/test_llm_crawler_replay_fixture_check_unittest.py",
    "main/backend/tests/unit/test_llm_crawler_replay_manifest_check_unittest.py",
    "main/backend/tests/unit/test_source_library_public_replay_a5_gate_unittest.py",
    "main/backend/tests/unit/test_source_library_review_closure_batch_unittest.py",
    "main/backend/tests/unit/test_source_library_review_closure_batch2_unittest.py",
    "main/backend/tests/unit/test_source_library_review_closure_batch3_unittest.py",
    "main/backend/tests/unit/test_source_library_review_closure_batch4_unittest.py",
    "main/backend/tests/unit/test_source_library_search_governance_check_unittest.py",
]

OPENSEARCH_VECTOR_PATHS = [
    "main/backend/scripts/evidence_source_contract.py",
    "main/backend/scripts/check_open_search_runtime_boundary.py",
    "main/backend/scripts/check_open_search_health_artifact.py",
    "main/backend/scripts/check_open_search_health_artifact_schema_readback.py",
    "main/backend/scripts/check_wave14_vectorization_provider_capability.py",
    "ops/search-lab/scripts/wave8_search_vectorization_contract.py",
    "ops/search-lab/scripts/wave10_vectorization_quality_gate.py",
    "ops/search-lab/scripts/wave12_provider_readiness_gate.py",
    "ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py",
    "ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py",
    "ops/search-lab/scripts/wave27_vectorization_closure_gate.py",
    "ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py",
    "ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py",
    "ops/search-lab/scripts/wave57_oss_node_public_corpus_semantic_relevance_gate.py",
    "ops/search-lab/scripts/wave57_production_vector_quality_gate.py",
    "main/backend/tests/unit/_evidence_source_assertions.py",
    "main/backend/tests/unit/test_open_search_health_artifact_unittest.py",
    "main/backend/tests/unit/test_open_search_health_artifact_schema_readback_unittest.py",
    "main/backend/tests/unit/test_open_search_runtime_boundary_unittest.py",
    "main/backend/tests/unit/test_wave14_vectorization_provider_capability_unittest.py",
    "main/backend/tests/unit/test_wave8_search_vectorization_contract_unittest.py",
    "main/backend/tests/unit/test_wave10_vectorization_quality_gate_unittest.py",
    "main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py",
    "main/backend/tests/unit/test_wave18_vectorization_hybrid_readback_unittest.py",
    "main/backend/tests/unit/test_wave19_vectorization_provider_manifest_readback_unittest.py",
    "main/backend/tests/unit/test_wave27_vectorization_closure_gate_unittest.py",
    "main/backend/tests/unit/test_wave29_oss_node_vector_manifest_replay_unittest.py",
    "main/backend/tests/unit/test_wave55_oss_node_search_quality_gate_unittest.py",
    "main/backend/tests/unit/test_wave57_oss_node_public_corpus_semantic_relevance_gate_unittest.py",
    "main/backend/tests/unit/test_wave57_production_vector_quality_gate_unittest.py",
]

CANONICAL_EVIDENCE_PATHS = [
    "stage1-successor-evidence/residual-disposition-v1/build_contract12_return.py",
    "stage1-successor-evidence/residual-disposition-v1/raw-gate/backend-unit-final.log",
    "stage1-successor-evidence/residual-disposition-v1/raw-gate/backend-unit-final.xml",
    "stage1-successor-evidence/residual-disposition-v1/raw-gate/receipt.v1.json",
    "stage1-successor-evidence/residual-disposition-v1/inventory/generate_backend_failure_inventory.py",
    "stage1-successor-evidence/residual-disposition-v1/inventory/check_backend_failure_inventory.py",
    "stage1-successor-evidence/residual-disposition-v1/inventory/backend_failure_inventory.v1.json",
    "stage1-successor-evidence/residual-disposition-v1/inventory/backend_failure_inventory.validation.v1.json",
    "stage1-successor-evidence/residual-disposition-v1/inventory/backend_failure_inventory.root-input.v1.json",
    "stage1-successor-evidence/residual-disposition-v1/inventory/backend_failure_inventory.root-input.validation.v1.json",
    "stage1-successor-evidence/residual-disposition-v1/process-api/process-task-id-fallback.patch",
    "stage1-successor-evidence/residual-disposition-v1/process-api/process-task-id-fallback-disposition.v1.json",
    "stage1-successor-evidence/residual-disposition-v1/process-api/process-task-id-fallback-disposition.v1.md",
    "stage1-successor-evidence/residual-disposition-v1/effects/import-time-db-effects.v1.json",
    "stage1-successor-evidence/residual-disposition-v1/semantic-decisions/stale-status-checkers-v2-disposition.md",
    "stage1-successor-evidence/residual-disposition-v1/missing-evidence/crawler-source/crawler-source-missing-evidence-provenance.v1.json",
    "stage1-successor-evidence/residual-disposition-v1/missing-evidence/opensearch-vector/opensearch-vector-missing-evidence-provenance.v1.json",
]

RECORDED_BEFORE = {
    "main/backend/tests/unit/test_resource_pool_unified_search_unittest.py": (
        "38fabfc2a147b9da78aaaa4ba81f815bf457673f5f638d02e959be5fdb89ed95"
    ),
    "main/backend/tests/unit/test_interactive_agent_runtime_unittest.py": (
        "d99762d8be0be3ee76da22fa47e4cfb1f9c4d1a725de868d7b8c6ea8949ff31b"
    ),
    "main/backend/tests/unit/test_source_library_real_probe_fixture_unittest.py": (
        "6f572ca0fb21ab75aa71ef6dff7330b640dc8f2122caee71340576ca38003a5c"
    ),
    "main/backend/app/services/workflow_graph/governance_contract.py": (
        "bd38ed4b63d48858551f8271e320cb9d83e1bef499c1a2b18e0839f317875829"
    ),
    "main/backend/app/services/workflow_graph/__init__.py": (
        "de7d79ec3e12c5e83a953b7886408584f6e74a95930fb7c066e32c92414a8533"
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def write_create_only(path: Path, body: bytes) -> None:
    if path.exists():
        if path.read_bytes() != body:
            raise FileExistsError(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(body)


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def git_status(path: str) -> str:
    result = subprocess.run(
        ["git", "status", "--short", "--", path],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or "CLEAN_OR_IGNORED"


def path_entry(path: str, *, group: str, reason: str) -> dict[str, Any]:
    absolute = REPO_ROOT / path
    if not absolute.is_file():
        raise FileNotFoundError(absolute)
    entry: dict[str, Any] = {
        "path": path,
        "group": group,
        "owner": group,
        "reason": reason,
        "status_at_return": git_status(path),
        "after_sha256": sha256_file(absolute),
        "before_sha256": RECORDED_BEFORE.get(path),
        "before_hash_kind": "task_start" if path in RECORDED_BEFORE else "NOT_RECORDED",
        "frozen_binding_impact": "REVIEW_REQUIRED_BEFORE_ANY_ADDITIVE_REBIND",
    }
    return entry


def build_changed_paths() -> dict[str, Any]:
    rows = [
        *(
            path_entry(
                path,
                group="contract_11_12_remediation",
                reason="repair a proven source, fixture, projection, status, or import-effect cause",
            )
            for path in EARLIER_REMEDIATION_PATHS
        ),
        *(
            path_entry(
                path,
                group="crawler_source_missing_evidence",
                reason="propagate explicit EVIDENCE_SOURCE_UNAVAILABLE without synthetic closure",
            )
            for path in CRAWLER_SOURCE_PATHS
        ),
        *(
            path_entry(
                path,
                group="opensearch_vector_missing_evidence",
                reason="propagate explicit EVIDENCE_SOURCE_UNAVAILABLE and NOT_LIVE",
            )
            for path in OPENSEARCH_VECTOR_PATHS
        ),
        *(
            path_entry(
                path,
                group="contract_12_create_only_evidence",
                reason="create-only residual disposition evidence or deterministic tooling",
            )
            for path in CANONICAL_EVIDENCE_PATHS
        ),
    ]
    return {
        "schema_version": "mrw.stage1.contract12.changed-paths.v1",
        "authoritative": False,
        "contract_12": {"path": CONTRACT_12.as_posix(), "sha256": sha256_file(REPO_ROOT / CONTRACT_12)},
        "entry_count": len(rows),
        "entries": rows,
        "before_hash_policy": (
            "Only exact task-start hashes recorded by the owning work package are labeled before_sha256; "
            "HEAD hashes and truncated prefixes are not substituted for a dirty-worktree task-start identity."
        ),
        "authority_ceiling": AUTHORITY_CEILING,
    }


def build_artifact_manifest() -> dict[str, Any]:
    excluded = {
        "artifact-manifest.v1.json",
        "return.v1.json",
        "return-validation.v1.json",
    }
    artifacts = []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT).as_posix()
        if not path.is_file() or path.suffix == ".pyc" or "__pycache__" in path.parts:
            continue
        if relative in excluded:
            continue
        artifacts.append(
            {
                "path": f"stage1-successor-evidence/residual-disposition-v1/{relative}",
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return {
        "schema_version": "mrw.stage1.contract12.artifact-manifest.v1",
        "authoritative": False,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "excluded_non_evidence": ["__pycache__", "*.pyc"],
        "authority_ceiling": AUTHORITY_CEILING,
    }


def artifact_ref(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    return {
        "path": f"stage1-successor-evidence/residual-disposition-v1/{relative}",
        "sha256": sha256_file(path),
    }


def build_return(changed_path: Path, manifest_path: Path) -> dict[str, Any]:
    completion_v3 = REPO_ROOT / CONTRACT_DIR / "stage0-evidence/functorial-refactor-completion.v3.json"
    completion_v4 = REPO_ROOT / CONTRACT_DIR / "stage0-evidence/functorial-refactor-completion.v4.json"
    return {
        "schema_version": "mrw.stage1.contract12.return.v1",
        "RETURN_RESULT": "AWAITING_HUMAN_AUTHORITY",
        "return_scope": "STAGE_1_SOURCE_AND_STATIC_CLOSURE_AND_STAGE_2_V5_SUCCESSOR",
        "input_source_identity_and_hashes": {
            "current_head": git_value("rev-parse", "HEAD"),
            "current_head_tree": git_value("rev-parse", "HEAD^{tree}"),
            "dispatch_head": "3706655f372f6d34fc62683551b8c3d1f4ff8146",
            "dispatch_tree": "5840bf9ba906c49f70020d226c54446f4ba5aa33",
            "contract_10": {"path": CONTRACT_10.as_posix(), "sha256": sha256_file(REPO_ROOT / CONTRACT_10)},
            "contract_11": {"path": CONTRACT_11.as_posix(), "sha256": sha256_file(REPO_ROOT / CONTRACT_11)},
            "contract_12": {"path": CONTRACT_12.as_posix(), "sha256": sha256_file(REPO_ROOT / CONTRACT_12)},
            "process_py": {
                "path": "main/backend/app/api/process.py",
                "sha256": sha256_file(REPO_ROOT / "main/backend/app/api/process.py"),
                "modified_by_contract_12": False,
            },
        },
        "changed_paths": {
            "path": changed_path.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(changed_path),
            "entry_count": json.loads(changed_path.read_text(encoding="utf-8"))["entry_count"],
        },
        "source_closure_checker_and_results": {
            "status": "FOCUSED_PASS_NOT_STAGE1_ACCEPTANCE",
            "projected_model": "exact base tree plus ordered UPSERT/DELETE overlay",
            "properties": [
                "base-only MRW candidates are detected",
                "cross-clone base blobs are read from the bound object store",
                "all manifest entries are exact-compared",
                "MRW package omission and DELETE cannot use checkout bytes as fallback",
            ],
            "integrated_focused_receipt": "375 passed, 53 warnings in 40.18s",
        },
        "backend_unit_gate_result": {
            "status": "FAIL_RETAINED_NOT_RERUN",
            "selector": "unit and not external and not flaky",
            "last_completed_execution": {
                "failed": 55,
                "passed": 1712,
                "skipped": 0,
                "deselected": 2328,
                "warnings": 14,
                "subtests_passed": 42,
                "exit_code": 1,
            },
            "raw_log": artifact_ref("raw-gate/backend-unit-final.log"),
            "junit": artifact_ref("raw-gate/backend-unit-final.xml"),
            "rerun_reason": (
                "Not rerun because 30 missing-evidence failures remain explicitly fail-closed and the "
                "exact-bound process.py production projection defect requires additive rebind authority."
            ),
        },
        "static_stage3_readiness_results": "NOT_RUN_PHASE_A_UNACCEPTED",
        "stage1_remediation_record_and_sha256": None,
        "stage1_focused_tests_lint_compile": {
            "integrated_pytest": "375 passed, 53 warnings in 40.18s",
            "focused_ruff": "PASS",
            "scoped_git_diff_check": "PASS",
            "scoped_compileall": "PASS",
            "broad_compileall_observation": (
                "NOT_A_GATE: unrelated pre-existing SyntaxError in main/backend/scripts/reinforce_numeric_data.py:258"
            ),
        },
        "successor_candidate_root": None,
        "successor_commit": None,
        "successor_tree": None,
        "successor_manifest_path_and_sha256": None,
        "successor_closure_path_and_sha256": None,
        "successor_r1_r2_r3_paths_and_sha256": None,
        "successor_record_path_and_sha256": None,
        "primary_replay_receipts_and_sha256": None,
        "v5_fresh_checks": "NOT_RUN_PHASE_A_UNACCEPTED",
        "historical_v3_v4_unchanged": {
            "task_writes": False,
            "v3_completion": {
                "path": completion_v3.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(completion_v3),
            },
            "v4_completion": {
                "path": completion_v4.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(completion_v4),
            },
            "v4_expected_sha256": "4911df1c6450d9802ac7bd6b0669ef3a7343e3ce308d33f0a46dde2c4cb62dda",
        },
        "warning_skip_deselect_inventory": {
            "warnings": 14,
            "skipped": 0,
            "deselected": 2328,
            "scope": "last completed required-selector execution",
        },
        "external_effects": {
            "network": False,
            "live_provider": False,
            "live_database": False,
            "external_delivery": False,
            "effect_isolation": artifact_ref("effects/import-time-db-effects.v1.json"),
        },
        "cleanup_and_recovery_status": {
            "destructive_cleanup": False,
            "historical_restore": False,
            "noncanonical_initial_path_copies_retained": True,
            "note": (
                "Initial create-only copies under the contract-directory nested evidence root were retained; "
                "canonical return references only the repository-root evidence package."
            ),
        },
        "residual_blockers": [
            {
                "blocker": "PROCESS_API_EXACT_BYTE_REBIND_AUTHORITY_REQUIRED",
                "current_sha256": "790b6cb90086d6ba1171309e572b7e7be4c906db3705170dbd4a12ca7ea16c63",
                "proposed_sha256": "5687389bdad57881a0f96543ba32ac4eaaaeef0f7939f8f7e36e16316ed7ee61",
                "patch": artifact_ref("process-api/process-task-id-fallback.patch"),
            },
            {
                "blocker": "EVIDENCE_SOURCE_UNAVAILABLE",
                "backend_inventory_nodeids": 30,
                "crawler_source_unique_paths": 68,
                "opensearch_vector_unique_paths": 19,
                "synthetic_fixture_may_close_claim": False,
            },
            {
                "blocker": "REQUIRED_SELECTOR_NOT_GREEN",
                "last_exit_code": 1,
                "phase_b_c_v5_gated": True,
            },
        ],
        "authority_ceiling": AUTHORITY_CEILING,
        "recommended_next_action": (
            "Supervisor should independently accept this disposition, then either grant a create-only C5.4/I1 "
            "exact-byte rebind for process.py and supply authorized current evidence, or keep Stage 1 unaccepted. "
            "Only after those blockers are resolved should the full selector be rerun."
        ),
        "backend_failure_inventory": {
            "canonical": artifact_ref("inventory/backend_failure_inventory.root-input.v1.json"),
            "validation": artifact_ref("inventory/backend_failure_inventory.root-input.validation.v1.json"),
            "failure_count": 55,
            "category_counts": {
                "missing_evidence": 30,
                "test_fixture_defect": 19,
                "source_defect": 3,
                "stale_expected_semantics": 3,
            },
            "nodeids_unique": True,
            "junit_set_equal": True,
            "invalid_references": 0,
        },
        "effect_isolation_receipt": artifact_ref("effects/import-time-db-effects.v1.json"),
        "history_binding_disposition": {
            "i1_current": "B23 live projection",
            "i1_predecessor": "B22 history-only",
            "historical_bytes_modified": False,
            "process_api": artifact_ref("process-api/process-task-id-fallback-disposition.v1.json"),
        },
        "workflow_environment_equivalence": {
            "last_selector_workflow_equivalent": False,
            "differences": [
                "existing local dependency environment was reused",
                "existing .env state was reused",
                "four DB/store flags were explicitly false",
                "--tb=short changed presentation only",
                "dirty checkout contains deleted historical evidence",
            ],
            "unit_collection_after_import_isolation": "1313 collected, exit 0, no DB transaction or DDL",
        },
        "source_gate_negative_receipts": {
            "status": "PASS",
            "coverage": [
                "checkout/base divergence",
                "DELETE and omission",
                "missing package init",
                "base-only MRW detection",
                "cross-clone base blobs",
                "wrong base OID",
                "UPSERT bytes/mode/sha/blob drift",
                "DELETE base-mode/base-blob drift",
            ],
        },
        "missing_evidence_provenance": {
            "crawler_source": artifact_ref(
                "missing-evidence/crawler-source/crawler-source-missing-evidence-provenance.v1.json"
            ),
            "crawler_source_unique_paths": 68,
            "crawler_source_dependent_nodeids": 26,
            "opensearch_vector": artifact_ref(
                "missing-evidence/opensearch-vector/opensearch-vector-missing-evidence-provenance.v1.json"
            ),
            "opensearch_vector_unique_paths": 19,
            "opensearch_vector_dependent_nodeids": 24,
            "note": "Dependent nodeid sets overlap; the backend inventory has 30 unique missing-evidence failures.",
        },
        "semantic_decisions": artifact_ref(
            "semantic-decisions/stale-status-checkers-v2-disposition.md"
        ),
        "artifact_manifest": {
            "path": manifest_path.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(manifest_path),
        },
    }


def validate_package(return_path: Path, changed_path: Path, manifest_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    changed = json.loads(changed_path.read_text(encoding="utf-8"))
    for row in changed["entries"]:
        path = REPO_ROOT / row["path"]
        if not path.is_file() or sha256_file(path) != row["after_sha256"]:
            errors.append(f"changed_path_hash_mismatch:{row['path']}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["artifacts"]:
        path = REPO_ROOT / row["path"]
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            errors.append(f"artifact_hash_mismatch:{row['path']}")
    inventory = json.loads((ROOT / "inventory/backend_failure_inventory.root-input.v1.json").read_text())
    nodeids = [row["nodeid"] for row in inventory["failures"]]
    if inventory["failure_count"] != 55 or len(nodeids) != 55 or len(set(nodeids)) != 55:
        errors.append("backend_inventory_totals_or_uniqueness")
    if inventory["category_counts"] != {
        "missing_evidence": 30,
        "source_defect": 3,
        "stale_expected_semantics": 3,
        "test_fixture_defect": 19,
    }:
        errors.append("backend_inventory_category_counts")
    crawler = json.loads(
        (ROOT / "missing-evidence/crawler-source/crawler-source-missing-evidence-provenance.v1.json").read_text()
    )
    crawler_rows = crawler["inventory"]["entries"]
    crawler_nodeids = {nodeid for row in crawler_rows for nodeid in row["dependent_nodeids"]}
    if len(crawler_rows) != 68 or len(crawler_nodeids) != 26:
        errors.append("crawler_provenance_counts")
    if any(row["classification"] != "EVIDENCE_SOURCE_UNAVAILABLE" for row in crawler_rows):
        errors.append("crawler_provenance_classification")
    vector = json.loads(
        (ROOT / "missing-evidence/opensearch-vector/opensearch-vector-missing-evidence-provenance.v1.json").read_text()
    )
    if len(vector["missing_sources"]) != 19 or len(vector["nodeids"]) != 24:
        errors.append("opensearch_vector_provenance_counts")
    if vector["status"] != "EVIDENCE_SOURCE_UNAVAILABLE" or vector["execution_status"] != "NOT_LIVE":
        errors.append("opensearch_vector_provenance_status")
    returned = json.loads(return_path.read_text(encoding="utf-8"))
    if returned["RETURN_RESULT"] != "AWAITING_HUMAN_AUTHORITY":
        errors.append("return_result")
    if returned["input_source_identity_and_hashes"]["process_py"]["sha256"] != (
        "790b6cb90086d6ba1171309e572b7e7be4c906db3705170dbd4a12ca7ea16c63"
    ):
        errors.append("process_py_frozen_hash")
    return {
        "schema_version": "mrw.stage1.contract12.return-validation.v1",
        "authoritative": False,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "changed_path_count": changed["entry_count"],
        "artifact_count": manifest["artifact_count"],
        "backend_failure_nodeids": len(nodeids),
        "backend_failure_nodeids_unique": len(set(nodeids)) == len(nodeids),
        "crawler_source_unique_paths": len(crawler_rows),
        "crawler_source_dependent_nodeids": len(crawler_nodeids),
        "opensearch_vector_unique_paths": len(vector["missing_sources"]),
        "opensearch_vector_dependent_nodeids": len(vector["nodeids"]),
        "return_path": return_path.relative_to(REPO_ROOT).as_posix(),
        "return_sha256": sha256_file(return_path),
        "authority_ceiling": AUTHORITY_CEILING,
    }


def main() -> int:
    changed_path = ROOT / "changed-paths.v1.json"
    manifest_path = ROOT / "artifact-manifest.v1.json"
    return_path = ROOT / "return.v1.json"
    validation_path = ROOT / "return-validation.v1.json"

    write_create_only(changed_path, json_bytes(build_changed_paths()))
    write_create_only(manifest_path, json_bytes(build_artifact_manifest()))
    write_create_only(return_path, json_bytes(build_return(changed_path, manifest_path)))
    validation = validate_package(return_path, changed_path, manifest_path)
    write_create_only(validation_path, json_bytes(validation))
    print(
        json.dumps(
            {
                "status": validation["status"],
                "return": str(return_path),
                "return_sha256": validation["return_sha256"],
                "changed_path_count": validation["changed_path_count"],
                "artifact_count": validation["artifact_count"],
            },
            sort_keys=True,
        )
    )
    return 0 if validation["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
