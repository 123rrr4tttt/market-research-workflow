#!/usr/bin/env python3
"""Create or byte-compare the Stage 1 source/static remediation package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_REL = Path("stage1-successor-evidence/source-static-remediation-v1")
RECORD_REL = EVIDENCE_REL / "stage1-source-static-remediation-record.v1.json"
MANIFEST_REL = EVIDENCE_REL / "artifact-manifest.v1.json"
RAW_LOG_REL = EVIDENCE_REL / "raw/backend-unit-final.log"
RAW_XML_REL = EVIDENCE_REL / "raw/backend-unit-final.xml"
PHASE_B_REL = EVIDENCE_REL / "phase-b/static-production-contract.v1.json"
BUILDER_REL = EVIDENCE_REL / "build_source_static_remediation_record.py"
CHECKER_REL = EVIDENCE_REL / "check_source_static_remediation_record.py"
INITIAL_INVALID_RECORD_REL = (
    EVIDENCE_REL / "initial-invalid/stage1-source-static-remediation-record.initial-invalid.v1.json"
)
INITIAL_INVALID_MANIFEST_REL = EVIDENCE_REL / "initial-invalid/artifact-manifest.initial-invalid.v1.json"
INITIAL_INVALID_VALIDATION_REL = EVIDENCE_REL / "initial-invalid/validation.initial-invalid.v1.json"
PRE_LINT_RECORD_REL = EVIDENCE_REL / "pre-lint-snapshot/stage1-source-static-remediation-record.pre-lint.v1.json"
PRE_LINT_MANIFEST_REL = EVIDENCE_REL / "pre-lint-snapshot/artifact-manifest.pre-lint.v1.json"
PRE_LINT_VALIDATION_REL = EVIDENCE_REL / "pre-lint-snapshot/validation-receipt.pre-lint.v1.json"
PRE_LINT_NOTE_REL = EVIDENCE_REL / "pre-lint-snapshot/disposition.v1.json"

SCHEMA = "mrw.stage1.source_static_remediation_record.v1"
AUTHORITY_CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)
SOURCE_HEAD = "3706655f372f6d34fc62683551b8c3d1f4ff8146"
SOURCE_TREE = "5840bf9ba906c49f70020d226c54446f4ba5aa33"
EXPECTED_LOG_SHA = "2ab99e647b9be21987e914d153261273c3ab97a485a03e9eda4780600ac3adcc"
EXPECTED_XML_SHA = "0d215b2a746db7e65af30625039b6e0a4ed78196a560be76ebdc61eda349c35f"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def artifact_ref(path: str, expected_sha: str | None = None) -> dict[str, Any]:
    absolute = ROOT / path
    actual = sha256(absolute)
    if expected_sha is not None and actual != expected_sha:
        raise RuntimeError(f"INPUT_DRIFT:{path}:expected={expected_sha}:actual={actual}")
    return {"path": path, "sha256": actual, "bytes": absolute.stat().st_size}


def current_path(
    path: str,
    current_sha256: str,
    *,
    before_sha256: str,
    evidence: str,
    workstream: str,
    disposition: str = "CHANGED_AND_CURRENT_BOUND",
) -> dict[str, str]:
    actual = sha256(ROOT / path)
    if actual != current_sha256:
        raise RuntimeError(f"CURRENT_PATH_DRIFT:{path}:expected={current_sha256}:actual={actual}")
    return {
        "path": path,
        "before_sha256": before_sha256,
        "current_sha256": current_sha256,
        "evidence": evidence,
        "workstream": workstream,
        "disposition": disposition,
    }


def post_residual_paths() -> list[dict[str, str]]:
    residual = "stage1-successor-evidence/residual-disposition-v1/changed-paths.v1.json"
    startup = "stage1-successor-evidence/current-byte-remediation-v1/startup/startup-current-byte-remediation.v1.json"
    binding = "stage1-successor-evidence/current-byte-remediation-v1/bindings/current-byte-binding-successors.v1.json"
    contract10 = (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/"
        "10_stage1-stage2-source-and-static-closure-return-contract.v1.md"
    )
    phase_b_input = "contract10_phase_b_and_verified_current_gate_input"
    rows = [
        current_path(
            "src/mrw_functorial_kit/core/w07_semantics.py",
            "5afc74cc58d59ea2e788758a542906171f2fe82f4edbd87aa2edba24d6b29fe4",
            before_sha256="5afc74cc58d59ea2e788758a542906171f2fe82f4edbd87aa2edba24d6b29fe4",
            evidence=contract10,
            workstream="PHASE_A_SOURCE_INCLUSION",
            disposition="INCLUDED_UNMODIFIED_FROM_CONTRACT10_DISPATCH_BYTES",
        ),
        current_path(
            "src/mrw_functorial_kit/core/agent_service_semantics.py",
            "c23c3d7c303614b7d601d0f2cb40046e06b0c8f81814cb91d687219cce3a32dd",
            before_sha256="c23c3d7c303614b7d601d0f2cb40046e06b0c8f81814cb91d687219cce3a32dd",
            evidence=contract10,
            workstream="PHASE_A_SOURCE_INCLUSION",
            disposition="INCLUDED_UNMODIFIED_FROM_CONTRACT10_DISPATCH_BYTES",
        ),
        current_path(
            "scripts/formal_release/source_closure.py",
            "7b9a81c9cdf0ae0debc2b75aa6a2ecdc434f0f4ee210dfd282f45c7e51ea6eb4",
            before_sha256="061d3c3aa5183907f4fe043350ab79cefe998add7971c3c9a01a9894a3031bff",
            evidence=residual,
            workstream="PHASE_A_PROJECTED_SOURCE_GATE",
        ),
        current_path(
            "scripts/formal_release/stage2_candidate_intake.py",
            "977a58ec5a8c854dfc18daffe8f7af3e996118d53b205482ba049ccf697c57db",
            before_sha256="977a58ec5a8c854dfc18daffe8f7af3e996118d53b205482ba049ccf697c57db",
            evidence=residual,
            workstream="PHASE_A_PROJECTED_SOURCE_GATE",
            disposition="CURRENT_BYTES_EQUAL_RESIDUAL_CHECKPOINT",
        ),
        current_path(
            "scripts/formal_release/materialize_stage2_candidate.py",
            "486083e3309f83e74ec1be3526a46899b4f25f8002086475a487f0944ff7640b",
            before_sha256="486083e3309f83e74ec1be3526a46899b4f25f8002086475a487f0944ff7640b",
            evidence=residual,
            workstream="PHASE_A_PROJECTED_SOURCE_GATE",
            disposition="CURRENT_BYTES_EQUAL_RESIDUAL_CHECKPOINT",
        ),
        current_path(
            "tests/formal_release/test_source_closure.py",
            "21824548dbfd226ebd714feb7d337837c94af2ec6706732e3241568c86a3f1da",
            before_sha256="219eca68cb17be285ca078c14d8a4510e69f0bd69bb96c17d72d84b03731dcd9",
            evidence=residual,
            workstream="PHASE_A_PROJECTED_SOURCE_GATE",
        ),
        current_path(
            "tests/formal_release/test_stage2_candidate_intake.py",
            "9b7e2518f8812c0bbf70c471a1c1453bbe9fbab9b52856b1ee8d3704ebd5ca05",
            before_sha256="5fc071b97f62353386727a4215b2d24b8411d2dc88517dc75e8b5432415baa2e",
            evidence=residual,
            workstream="PHASE_A_PROJECTED_SOURCE_GATE",
        ),
        current_path(
            "tests/formal_release/test_materialize_stage2_candidate.py",
            "e3e6aa48688e86e00d2c03887a8ba6e938d8812650b57a4bb6671da6154d4fdd",
            before_sha256="53805282be077854f13d1ce646a26414ff9c7d7e20df69bf6c16f2309bc4c192",
            evidence=residual,
            workstream="PHASE_A_PROJECTED_SOURCE_GATE",
        ),
        current_path(
            "main/backend/app/services/projects/schema_initialization.py",
            "256faf88704948e94add6be75f8ccab76c506ad568feabd102f0f490bb574424",
            before_sha256="ABSENT",
            evidence=startup,
            workstream="STARTUP_CURRENT_BYTE_REMEDIATION",
        ),
        current_path(
            "main/backend/app/startup_hooks.py",
            "b0ece0fc0fd9ca2d775056ab0ecffed1cedb3400a2d249a416af899399176ba2",
            before_sha256="a1426fad870f3aefaf98236725d953f65f35e6b059603f9e29b9bdf0c1a98d74",
            evidence=startup,
            workstream="STARTUP_CURRENT_BYTE_REMEDIATION",
        ),
        current_path(
            "main/backend/app/celery_app.py",
            "013ddec4e03a28e9f15211a346db9481b624cb395b05cf8b05d741e54281b645",
            before_sha256="6766bc85cb01afd79b8f91793ec2b6020ee45ea0d4797ef0a589076072f2d49d",
            evidence=startup,
            workstream="STARTUP_CURRENT_BYTE_REMEDIATION_AND_BINDING_SUCCESSOR",
        ),
        current_path(
            "main/backend/app/services/projects/bootstrap.py",
            "7e3189f5ff916480f1243ff805ea2790075d6a187b348fbb2bfa48ee600bd08d",
            before_sha256="7d6ff118a0e4b9d552320d18e7122423ed66111d1deda3bcb7b242baca9aba1b",
            evidence=startup,
            workstream="STARTUP_CURRENT_BYTE_REMEDIATION",
        ),
        current_path(
            "main/backend/app/services/workflow_graph/store.py",
            "462133407d0a4d6f84864b44b3b3c9467a6879199149cd7e73868a02a9feaaed",
            before_sha256="UNKNOWN_NOT_ATTRIBUTED",
            evidence=startup,
            workstream="STARTUP_CURRENT_BYTE_REMEDIATION",
        ),
        current_path(
            "main/backend/scripts/_cli_runtime.py",
            "add9fa2d0aca3ab202dccbc313550ae6b04dc91a6e2ab671be5cfb42f412a24c",
            before_sha256="3cb9e57fec7ccb5614e891fbeea4fe9688fd1f61deacab589ffa66676eb4c397",
            evidence=startup,
            workstream="STARTUP_CURRENT_BYTE_REMEDIATION",
        ),
        current_path(
            "main/backend/tests/unit/test_schema_startup_boundary_unittest.py",
            "86c7dbb952a8ed97e8d55e87c56c2b1ba788405823c7aca6e2ac2491f32fc9fc",
            before_sha256="6bcdd014f81f1e6d0ebc0ce35dae46b2ae1c57d19ae51aa1a4d904e4602da824",
            evidence=startup,
            workstream="STARTUP_CURRENT_BYTE_REMEDIATION",
        ),
        current_path(
            "main/backend/tests/integration/test_schema_startup_postgres_concurrency.py",
            "619d821c18134af506c1cc8807c514f07015b8078cc66d551c0a6c540a717999",
            before_sha256="ABSENT",
            evidence=startup,
            workstream="STARTUP_CURRENT_BYTE_REMEDIATION",
        ),
        current_path(
            "main/backend/app/api/process.py",
            "5687389bdad57881a0f96543ba32ac4eaaaeef0f7939f8f7e36e16316ed7ee61",
            before_sha256="790b6cb90086d6ba1171309e572b7e7be4c906db3705170dbd4a12ca7ea16c63",
            evidence=binding,
            workstream="CURRENT_BYTE_BINDING_SUCCESSOR",
        ),
        current_path(
            "main/backend/app/services/workflow_graph/runtime.py",
            "15c22d898b1c90205c43585aae4e3d83a425782e57676926507b92e6b8fb68ca",
            before_sha256="cb4ae041aef79ce9b8d68a14615c4a85f1b9182319380a5462133534eeca67fc",
            evidence=binding,
            workstream="CURRENT_BYTE_BINDING_SUCCESSOR",
        ),
        current_path(
            "main/backend/app/models/base.py",
            "173d95722cef7411f4b1e4606f8dbdbf850d74fbae9847b942b13be1e56c8308",
            before_sha256="5b81ef9a41bf8e21c87f2d7a0e0239a4afa14c46de0eb7b37601d217422654f4",
            evidence=binding,
            workstream="CURRENT_BYTE_BINDING_SUCCESSOR",
        ),
        current_path(
            ".github/workflows/backend-tests.yml",
            "6c108b0842c600fe100ad560732740f347a5d357625fa753a1e052f0b33a7cc6",
            before_sha256="567fdca6904fbf0e5debc037c656e1b9f722f629a6d886a31c1282eba6f6877f",
            evidence=contract10,
            workstream="PHASE_B_STATIC_CLOSURE",
        ),
        current_path(
            ".github/branch-protection-required-checks.json",
            "696195d3a8ca59a23da069d56147732ea42b991299d088b3c78d3776612f6fff",
            before_sha256="cb4d61a900a626b71d089717a2210c6cac008ec943bfdac07590f31e618e6355",
            evidence=contract10,
            workstream="PHASE_B_STATIC_CLOSURE",
        ),
        current_path(
            "scripts/formal_release/check_static_production_contract.py",
            "df8257a37482cecb62797a21ac2323a9c72fcfe3f580c18cf1d8a27a4d2b9c75",
            before_sha256="UNKNOWN_NOT_ATTRIBUTED",
            evidence=phase_b_input,
            workstream="PHASE_B_STATIC_CLOSURE",
        ),
        current_path(
            "tests/formal_release/test_check_static_production_contract.py",
            "eee58d1ea75cd723aded98942ada1cb74004ccc26ae0a47d18a55ebe26f218ef",
            before_sha256="UNKNOWN_NOT_ATTRIBUTED",
            evidence=phase_b_input,
            workstream="PHASE_B_STATIC_CLOSURE",
        ),
        current_path(
            "main/backend/Dockerfile",
            "837b30116e81235c40e809a7ea0b9d0049bdf52a763b2262ed74f3cecc79c655",
            before_sha256="UNKNOWN_NOT_ATTRIBUTED",
            evidence=phase_b_input,
            workstream="PHASE_B_STATIC_CLOSURE",
        ),
        current_path(
            "main/frontend-modern/Dockerfile",
            "ae4132f1587973c4eeafbbda4f6c64be74563e968193b9b05d197f83c3a16e6b",
            before_sha256="UNKNOWN_NOT_ATTRIBUTED",
            evidence=phase_b_input,
            workstream="PHASE_B_STATIC_CLOSURE",
        ),
    ]
    paths = [row["path"] for row in rows]
    if len(paths) != len(set(paths)):
        raise RuntimeError("DUPLICATE_POST_RESIDUAL_PATH")
    return sorted(rows, key=lambda row: row["path"])


def build_record() -> dict[str, Any]:
    log_ref = artifact_ref(RAW_LOG_REL.as_posix(), EXPECTED_LOG_SHA)
    xml_ref = artifact_ref(RAW_XML_REL.as_posix(), EXPECTED_XML_SHA)
    phase_b_ref = artifact_ref(PHASE_B_REL.as_posix())
    phase_b = json.loads((ROOT / PHASE_B_REL).read_text(encoding="utf-8"))
    if phase_b.get("status") != "PASS" or phase_b.get("authoritative") is not False:
        raise RuntimeError("PHASE_B_SNAPSHOT_NOT_PASS_NON_AUTHORITY")
    contracts = [
        artifact_ref(
            "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/"
            "10_stage1-stage2-source-and-static-closure-return-contract.v1.md",
            "0c20328727fdefca6a3161e212490a2043efeee17e4bffc854f8ee17847cdd6b",
        ),
        artifact_ref(
            "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/"
            "11_stage1-backend-unit-remediation-return-contract.v1.md",
            "051dcf9be9b8f03d8bb603537bece6f37cdf8423fa8c6e4a4d6183f230227ca5",
        ),
        artifact_ref(
            "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/"
            "12_stage1-residual-disposition-return-contract.v1.md",
            "c11c96a68284085dfb2548cd9ce19062de22b5d4bbf5af9d2c2863a16dcf03f2",
        ),
    ]
    prior_residual = artifact_ref(
        "stage1-successor-evidence/residual-disposition-v1/changed-paths.v1.json",
        "d946cf88b022d21cc71c0a1ea424b9cb8f7d2c5a7975fe31c66c67f741790d9b",
    )
    historical = artifact_ref(
        "stage1-successor-evidence/contract13-bounded-corrections-v2/historical-candidates/"
        "historical-candidates-readonly-verification.v1.json",
        "b21bc780b140792cc96b5f358fc02c2e818af8b0b29da722d2a8e12857526d89",
    )
    references = [
        artifact_ref(
            "stage1-successor-evidence/contract13-bounded-corrections-v2/return.v2.json",
            "0b9dda0595b84176bd38c60b69030b930a128146c98a8da893ce4aec897b1bbc",
        ),
        artifact_ref(
            "stage1-successor-evidence/contract14-local-execution-v1/return.v1.json",
            "bf448d36c8cab520644fc2b662327e6a16febdc4eb4dd8134a7eed71d92aa4c4",
        ),
        artifact_ref(
            "stage1-successor-evidence/contract14-local-execution-v1/history/history-verification-receipt.v1.json",
            "2187771630e3fd041f73f7de2358d587a96803115f3076926e7def791a38905a",
        ),
        artifact_ref(
            "stage1-successor-evidence/current-byte-remediation-v1/startup/startup-current-byte-remediation.v1.json",
            "17951c1124e93832d6e7e727a91236fceebc2a362bceb1abf2e9307c00a2ddda",
        ),
        artifact_ref(
            "stage1-successor-evidence/current-byte-remediation-v1/bindings/current-byte-binding-successors.v1.json",
            "7e2a6d84ef37174bf52142a9e2560470a24e60c84549962e856688f4702e401b",
        ),
    ]
    required_phase_b_gaps = [
        {
            "gap_id": "frontend_component_e2e_required",
            "finding_id": "workflow.frontend_component_e2e",
            "status": "STATIC_CONTRACT_PASS",
        },
        {
            "gap_id": "frontend_dependency_audit_required",
            "finding_id": "workflow.security_scans",
            "status": "STATIC_CONTRACT_PASS",
        },
        {
            "gap_id": "three_artifact_role_identities",
            "finding_id": "artifact_metadata.immutable_release",
            "status": "STATIC_CONTRACT_PASS",
        },
        {
            "gap_id": "three_role_sbom_provenance_signature_attestation",
            "finding_id": "artifact_metadata.immutable_release",
            "status": "STATIC_CONTRACT_PASS",
        },
        {
            "gap_id": "three_role_image_vulnerability_scan",
            "finding_id": "workflow.image_vulnerability_scan",
            "status": "STATIC_CONTRACT_PASS",
        },
        {
            "gap_id": "required_branch_and_convergence_propagation",
            "finding_id": "workflow.required_convergence",
            "status": "STATIC_CONTRACT_PASS",
        },
    ]
    return {
        "schema_version": SCHEMA,
        "record_id": "stage1-source-static-remediation-20260906-v1",
        "status": "PASS_STAGE1_SOURCE_STATIC_REMEDIATION_NOT_AUTHORITY",
        "authoritative": False,
        "production_release_authorized": False,
        "contracts": contracts,
        "source_identity": {
            "root": str(ROOT),
            "head": SOURCE_HEAD,
            "tree": SOURCE_TREE,
            "identity_kind": "DISPATCH_AND_CURRENT_HEAD_TREE",
        },
        "phase_a_source_closure": {
            "status": "PASS",
            "projected_source_gate": {
                "focused_tests": {"passed": 194, "failed": 0},
                "reviewer_tests": {"passed": 13, "failed": 0},
                "negative_gates": [
                    "missing_w07_semantics",
                    "missing_agent_service_semantics",
                    "unknown_exported_name",
                    "source_manifest_omission",
                    "projected_delete_cannot_fall_back_to_checkout",
                    "wrong_base_index_binding",
                    "upsert_metadata_or_bytes_drift",
                ],
            },
            "workflow_equivalent_backend_unit": {
                "selector": "unit and not external and not flaky",
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
                "duration_seconds_from_log": 41.33,
                "raw_log": log_ref,
                "junit_xml": xml_ref,
                "environment": {
                    "python": "main/backend/.venv311/bin/python",
                    "PYTHONHASHSEED": "0",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": "repo/src",
                    "db_store_flags": {
                        "MRW_STORE_AUTO_CREATE": "false",
                        "MRW_VECTOR_STORE_AUTO_CREATE": "false",
                        "MRW_VECTOR_REQUIRE_PGVECTOR": "false",
                        "MRW_VECTOR_ENABLE_IVFFLAT": "false",
                    },
                    "pytest_cacheprovider": "disabled",
                    "dependency_install": "reused_existing_backend_venv",
                },
                "inventory": {
                    "deselected_owner": "required marker expression",
                    "skip_owner": "none",
                    "warning_families": [
                        {
                            "family": "PydanticDeprecatedSince20",
                            "count": 3,
                            "owner": "pydantic dependency and model declarations",
                        },
                        {
                            "family": "FastAPI on_event DeprecationWarning",
                            "count": 22,
                            "owner": "FastAPI dependency and application startup-hook declarations",
                        },
                    ],
                },
            },
        },
        "phase_b_static_readiness": {
            "status": "PASS_STATIC_CONTRACT_EXTERNAL_EXECUTION_NOT_RUN",
            "interpreter": "main/backend/.venv311/bin/python",
            "direct_checker": phase_b_ref,
            "focused_contract_tests": {"passed": 16, "failed": 0, "subtests_passed": 22},
            "required_gap_count": 6,
            "required_gaps": required_phase_b_gaps,
            "external_stage3_actions": {
                "image_build": "NOT_RUN_STAGE3_PENDING",
                "image_scan": "NOT_RUN_STAGE3_PENDING",
                "registry_publish": "NOT_RUN_FORBIDDEN",
                "sbom_generation": "NOT_RUN_STAGE3_PENDING",
                "provenance_generation": "NOT_RUN_STAGE3_PENDING",
                "signing": "NOT_RUN_FORBIDDEN",
                "attestation_publish": "NOT_RUN_FORBIDDEN",
            },
        },
        "binding_and_history_disposition": {
            "binding_registry": {
                "path": references[-1]["path"],
                "sha256": references[-1]["sha256"],
                "status": "PASS_4_SOURCES_10_SUCCESSORS",
                "authoritative": False,
            },
            "historical_verification": historical,
            "v3": {
                "commit": "f8d84afc2784cf91784da957e353e2b0c0d6952c",
                "tree": "1be3dcbc009332ec225297d1b94430862287d816",
                "status": "HISTORICAL_EXACT_CLEAN_READ_ONLY",
            },
            "v4": {
                "commit": "e1aa59708a22e4238c4d9beaf7b7bd2d2095d483",
                "tree": "d2003fbb8e54c8dd743fa4e84907a8a978ef5107",
                "manifest_sha256": "abc012b5c114d2d280db5bc5fc24c5591caa5bacc76840b154ec848dca5ae8b0",
                "closure_sha256": "6e3cf6dfd3ac7c336e81ab5c9b2e310373de7b981edce88109261ac031575c18",
                "r1_sha256": "79f7301e0c1e08553982ccc5c88f5854113825c81019ef6244da6bbd025260f0",
                "r2_sha256": "8e37eee14ea2eb865a048f57fec7ca55346da642509dc65ac99899b3d69a87ce",
                "r3_sha256": "86c67a4532a5a125f65c8f7405bd2b4b775472112e1577d85355fe6001ff5383",
                "record_sha256": "e2797d157c0a97f70b382d6ee6197bbcb073f6e55ac6ced5abe6946318345891",
                "stage3_index_sha256": "fbe1914ff111879edd1d1f5db02b7322232bdfa0bf05e752581ce2ea53992926",
                "status": "FAILED_STAGE3_HISTORY_IMMUTABLE",
            },
        },
        "changed_paths": {
            "scope_note": (
                "Only receipt-bound Stage 1 source/static/current-byte remediation paths are enumerated. "
                "Unrelated dirty user paths are excluded. UNKNOWN_NOT_ATTRIBUTED is used where no "
                "task-start hash receipt exists; ABSENT is used only where the startup before-hash receipt says ABSENT."
            ),
            "prior_residual_inventory": {**prior_residual, "entry_count": 105, "status": "HASH_AND_SCHEMA_BOUND"},
            "post_residual_entry_count": 25,
            "post_residual": post_residual_paths(),
        },
        "referenced_stage1_evidence": references,
        "preserved_evidence_ceiling": {
            "contract14_history_currently_qualified_nodeids": 0,
            "startup_local_focused": "52 passed, 1 skipped, 28 warnings",
            "startup_skip_owner": {
                "nodeid": "test_postgresql_cross_process_ddl_race_rolls_back_and_recovers",
                "reason": "MRW_TEST_POSTGRES_URL absent",
                "fixture_scope": "isolated localhost PostgreSQL with mrw_test_ database name",
                "status": "NOT_RUN_NOT_LIVE",
            },
            "local_or_historical_receipts_do_not_establish_live_or_production_authority": True,
        },
        "external_effects": {
            "network": False,
            "docker": False,
            "registry": False,
            "signing": False,
            "live_database": False,
            "live_provider": False,
            "deployment": False,
            "push_or_remote_mutation": False,
            "production_write": False,
        },
        "cleanup_status": {
            "temporary_services_started": False,
            "containers_started": False,
            "destructive_cleanup": False,
            "historical_paths_modified": False,
            "task_output_scope": EVIDENCE_REL.as_posix() + "/**",
        },
        "remaining_gaps": [
            "STAGE2_V5_NOT_CREATED_BY_THIS_RECORD",
            "STAGE3_ARTIFACT_BUILD_SCAN_SBOM_PROVENANCE_SIGNATURE_ATTESTATION_NOT_RUN",
            "LIVE_POSTGRES_STARTUP_CONCURRENCY_FIXTURE_NOT_RUN",
            "CONTRACT14_HISTORICAL_CLAIMS_NOT_CURRENTLY_QUALIFIED",
            "PRODUCTION_RELEASE_NOT_AUTHORIZED",
        ],
        "authority_ceiling": AUTHORITY_CEILING,
    }


def build_manifest() -> dict[str, Any]:
    members = [
        artifact_ref(BUILDER_REL.as_posix()),
        artifact_ref(CHECKER_REL.as_posix()),
        artifact_ref(RAW_LOG_REL.as_posix(), EXPECTED_LOG_SHA),
        artifact_ref(RAW_XML_REL.as_posix(), EXPECTED_XML_SHA),
        artifact_ref(PHASE_B_REL.as_posix()),
        artifact_ref(RECORD_REL.as_posix()),
        artifact_ref(INITIAL_INVALID_RECORD_REL.as_posix()),
        artifact_ref(INITIAL_INVALID_MANIFEST_REL.as_posix()),
        artifact_ref(INITIAL_INVALID_VALIDATION_REL.as_posix()),
        artifact_ref(PRE_LINT_RECORD_REL.as_posix()),
        artifact_ref(PRE_LINT_MANIFEST_REL.as_posix()),
        artifact_ref(PRE_LINT_VALIDATION_REL.as_posix()),
        artifact_ref(PRE_LINT_NOTE_REL.as_posix()),
    ]
    members.sort(key=lambda row: row["path"])
    return {
        "schema_version": "mrw.stage1.source_static_remediation_manifest.v1",
        "status": "COMPLETE_NOT_AUTHORITY",
        "authoritative": False,
        "member_count": len(members),
        "members": members,
        "authority_ceiling": AUTHORITY_CEILING,
    }


def write_create_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def copy_create_only(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_file() and source.read_bytes() == destination.read_bytes():
            return
        raise FileExistsError(f"CREATE_ONLY_INPUT_COLLISION:{destination}")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with source.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def compare(path: Path, expected: bytes) -> None:
    actual = path.read_bytes()
    if actual != expected:
        raise RuntimeError(f"REGENERATION_MISMATCH:{path.relative_to(ROOT)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare all deterministic generated bytes")
    parser.add_argument("--phase-a-log-source", type=Path)
    parser.add_argument("--phase-a-xml-source", type=Path)
    parser.add_argument("--phase-b-source", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        artifact_ref(RAW_LOG_REL.as_posix(), EXPECTED_LOG_SHA)
        artifact_ref(RAW_XML_REL.as_posix(), EXPECTED_XML_SHA)
        compare(ROOT / RECORD_REL, canonical_bytes(build_record()))
        compare(ROOT / MANIFEST_REL, canonical_bytes(build_manifest()))
        print(json.dumps({"status": "PASS", "mode": "CHECK", "record": RECORD_REL.as_posix()}, sort_keys=True))
        return 0
    for source, destination, expected_sha in (
        (args.phase_a_log_source, ROOT / RAW_LOG_REL, EXPECTED_LOG_SHA),
        (args.phase_a_xml_source, ROOT / RAW_XML_REL, EXPECTED_XML_SHA),
        (args.phase_b_source, ROOT / PHASE_B_REL, None),
    ):
        if source is None:
            raise RuntimeError("CREATE_MODE_REQUIRES_ALL_THREE_SOURCE_ARGUMENTS")
        if expected_sha is not None and sha256(source) != expected_sha:
            raise RuntimeError(f"SOURCE_HASH_MISMATCH:{source}")
        copy_create_only(source, destination)
    write_create_only(ROOT / RECORD_REL, canonical_bytes(build_record()))
    write_create_only(ROOT / MANIFEST_REL, canonical_bytes(build_manifest()))
    print(json.dumps({"status": "PASS", "mode": "CREATE", "record": RECORD_REL.as_posix()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
