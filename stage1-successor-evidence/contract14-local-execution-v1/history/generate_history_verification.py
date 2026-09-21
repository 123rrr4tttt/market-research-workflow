#!/usr/bin/env python3
# ruff: noqa: E501, TRY003, TRY004
"""Generate Contract 14 work-package H evidence from read-only Git objects."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


CONTRACT_BLOB = "cd93b304dc137c691d25f8fcb59807a3aa376227"
CONTRACT_SHA256 = "3252e21452e78c73fc9fef9b8b7435c2c3e0ab4466a6b411fe567010d4ea28e7"
CLAIM_TABLE_BLOB = "0898c3375d92e0580d23c097943d4a48678f7f92"
CLAIM_TABLE_SHA256 = "8362b368b5f4d944bb1bddf70f397e73c1b3716bc0bdb6244e61699b38e719b3"
TARGET_DECISION = "ACTUAL_HISTORICAL_RECEIPT_REQUIRED"
TARGET_CLAIMS = ["claim-001", "claim-002", "claim-004", "claim-014", "claim-016"]
AUTHORITY_CEILING = (
    "NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_"
    "NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_"
    "NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE"
)


def git(repo: Path, *args: str, check: bool = True) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({completed.returncode}): "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return completed.stdout


def blob(repo: Path, oid: str) -> bytes:
    return git(repo, "cat-file", "blob", oid)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parseability(path: str, data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {"kind": "UTF8_TEXT", "parseable": False, "error": str(exc)}

    suffix = Path(path).suffix.lower()
    try:
        if suffix == ".json":
            parsed = json.loads(text)
            return {
                "kind": "JSON",
                "parseable": True,
                "root_type": type(parsed).__name__,
                "top_level_keys": sorted(parsed) if isinstance(parsed, dict) else [],
            }
        if suffix == ".jsonl":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
            return {
                "kind": "JSONL",
                "parseable": True,
                "row_count": len(rows),
                "root_types": sorted({type(row).__name__ for row in rows}),
            }
        return {
            "kind": "UTF8_TEXT",
            "parseable": True,
            "line_count": len(text.splitlines()),
        }
    except (json.JSONDecodeError, TypeError) as exc:
        return {"kind": "JSON" if suffix == ".json" else "JSONL", "parseable": False, "error": str(exc)}


def object_oid(requirement: dict[str, Any]) -> str:
    historical = requirement["historical_object"]
    return historical.get("git_blob_oid") or historical.get("git_object_sha1")


def parse_json(data_by_path: dict[str, bytes], suffix: str) -> dict[str, Any]:
    matches = [data for path, data in data_by_path.items() if path.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected one historical object ending with {suffix!r}, found {len(matches)}")
    value = json.loads(matches[0])
    if not isinstance(value, dict):
        raise ValueError(f"historical JSON {suffix!r} is not an object")
    return value


def parse_log_header(data_by_path: dict[str, bytes], suffix: str) -> dict[str, str]:
    matches = [data for path, data in data_by_path.items() if path.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected one historical log ending with {suffix!r}, found {len(matches)}")
    result: dict[str, str] = {}
    for line in matches[0].decode("utf-8").splitlines():
        if line.startswith(("target=", "blocker ")):
            break
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def source_replay_observation(data_by_path: dict[str, bytes]) -> dict[str, Any]:
    input_doc = parse_json(data_by_path, "source-library-replay-scaleout/2026-05-22/input.json")
    public_doc = parse_json(data_by_path, "source-library-replay-scaleout/2026-05-22/output.public.json")
    public_log = parse_log_header(data_by_path, "source-library-replay-scaleout/2026-05-22/logs/output.public.log")
    input_target_ids = [target.get("target_id") for target in input_doc.get("targets", [])]
    output_target_ids = [
        row.get("target", {}).get("target_id")
        for row in public_doc.get("outputs", {}).get("target_results", [])
    ]
    output_probe_id = public_doc.get("probe_id")
    output_started = public_doc.get("started_at")
    output_finished = public_doc.get("finished_at")
    attempted = public_doc.get("outputs", {}).get("public_targets_attempted")
    return {
        "input_target_count": len(input_target_ids),
        "output_target_count": len(output_target_ids),
        "input_output_target_ids_equal_in_order": input_target_ids == output_target_ids,
        "output_assertions": {
            "probe_id": output_probe_id,
            "started_at": output_started,
            "finished_at": output_finished,
            "allow_public_network": public_doc.get("mode", {}).get("allow_public_network"),
            "public_targets_attempted": attempted,
            "full_historical_manifest": public_doc.get("validation", {}).get("full_historical_manifest"),
            "validation_passed": public_doc.get("validation", {}).get("passed"),
            "live_evidence_sufficient": public_doc.get("validation", {}).get("live_evidence_sufficient"),
            "warnings": public_doc.get("validation", {}).get("warnings", []),
        },
        "log_output_identity_equal": {
            "probe_id": public_log.get("probe_id") == output_probe_id,
            "started_at": public_log.get("started_at") == output_started,
            "finished_at": public_log.get("finished_at") == output_finished,
            "allow_public_network": public_log.get("allow_public_network") == str(public_doc.get("mode", {}).get("allow_public_network")),
            "target_count": public_log.get("target_count") == str(len(output_target_ids)),
            "public_targets_attempted": public_log.get("public_targets_attempted") == str(attempted),
        },
    }


def assessment_for(claim_id: str, data_by_path: dict[str, bytes]) -> dict[str, Any]:
    no_current = {
        "status": "NOT_GRANTED",
        "authoritative": False,
        "production_release_authorized": False,
        "reason": "Contract 14 work package H is history-only and cannot grant current qualification.",
    }
    if claim_id in {"claim-001", "claim-002", "claim-004"}:
        replay = source_replay_observation(data_by_path)
    else:
        replay = None

    if claim_id == "claim-001":
        manifest = parse_json(data_by_path, "crawler-public-replay-gate/2026-05-22/manifest.json")
        check = parse_json(data_by_path, "crawler-public-replay-gate/2026-05-22/crawler_public_replay_gate_check.json")
        present_paths = set(data_by_path)
        required = set(manifest.get("required_artifacts", {}).values())
        return {
            "layer_a_object_bytes": "VERIFIED_FOR_ALL_ENUMERATED_REQUIREMENTS",
            "layer_b_stored_assertions": {
                "status": "RUN_ASSERTED_BUT_REVIEW_NOT_ASSERTED_BY_AN_ENUMERATED_RECEIPT",
                "details": replay,
            },
            "layer_c_independent_run_identity": {
                "status": "PARTIALLY_CORROBORATED",
                "reason": "output.public.json and output.public.log agree on probe id, timestamps, target count, and attempted count; no enumerated review receipt or post-run gate binds that run to a reviewed PASS.",
            },
            "layer_d_current_qualification": no_current,
            "relationship_findings": {
                "manifest_contract_version_matches_check_embedding": manifest.get("contract_version") == check.get("manifest", {}).get("contract_version"),
                "check_manifest_path_matches": check.get("manifest_path") == "development/latest-dev-docs/automation-runs/crawler-public-replay-gate/2026-05-22/manifest.json",
                "manifest_required_artifact_count": len(required),
                "manifest_required_artifacts_enumerated_for_this_claim": len(required & present_paths),
                "manifest_missing_from_exact_claim_set": sorted(required - present_paths),
                "gate_check_asserted_evidence_present": check.get("live_public_replay", {}).get("evidence_present"),
                "gate_check_asserted_status": check.get("live_public_replay", {}).get("status"),
                "gate_check_asserted_closure_claim": check.get("live_public_replay", {}).get("closure_claim"),
            },
            "support_level": "PARTIAL_RUN_IDENTITY_REVIEW_AND_GATE_PASS_UNSUPPORTED",
            "gaps_and_contradictions": [
                "The enumerated gate check records evidence_present=false, status=not_closed_missing_real_evidence, and closure_claim=not_closed.",
                "A later output.public.json and matching log assert a 40-target public run, but no enumerated post-run gate result binds it to PASS.",
                "No enumerated relevance-review receipt establishes that the 30 term-fallback candidates were reviewed.",
                "Two of five manifest-required artifacts are absent from claim-001's exact requirement set.",
            ],
        }
    if claim_id == "claim-002":
        early = parse_json(data_by_path, "crawler-provider-handoff/2026-05-22/crawler_source_expansion_closure_check.json")
        late = parse_json(data_by_path, "crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/crawler_source_expansion_closure_check.json")
        a5 = parse_json(data_by_path, "crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/a5_public_replay_gate_check.json")
        late_statuses = {task.get("task_id"): task.get("status") for task in late.get("tasks", [])}
        return {
            "layer_a_object_bytes": "VERIFIED_FOR_ALL_ENUMERATED_REQUIREMENTS",
            "layer_b_stored_assertions": {
                "status": "PLAN_TASK_MAPPING_ASSERTED_BUT_TOPIC_CLOSURE_DENIED",
                "details": {
                    "early_overall_status": early.get("overall_status"),
                    "late_overall_status": late.get("overall_status"),
                    "late_task_statuses": late_statuses,
                    "a5_gate_status": a5.get("a5_status"),
                    "a5_gate_public_network_attempted": a5.get("validation", {}).get("public_network_attempted"),
                    "source_replay": replay,
                },
            },
            "layer_c_independent_run_identity": {
                "status": "PUBLIC_RUN_PARTIALLY_CORROBORATED_CLOSURE_NOT_CORROBORATED",
                "reason": "Public output/log identity agrees, but the exact closure and A5 records predate or exclude that run and retain external blocking; no post-run review-bound closure record is enumerated.",
            },
            "layer_d_current_qualification": no_current,
            "relationship_findings": {
                "late_validation_passed": late.get("validation", {}).get("passed"),
                "late_overall_status": late.get("overall_status"),
                "late_a5_status": late_statuses.get("A5"),
                "late_a7_status": late_statuses.get("A7"),
                "a5_external_blocker": a5.get("external_blocker"),
            },
            "support_level": "PARTIAL_MAPPING_AND_RUN_IDENTITY_RECORDED_CLOSURE_UNSUPPORTED",
            "gaps_and_contradictions": [
                "The later closure record says overall_status=external_blocked and A5=blocked_external, although A7 is closed.",
                "The A5 gate records public_network_attempted=false and says the full public output is absent from that worktree.",
                "A later public output/log pair exists, but no enumerated post-public-replay relevance review or closure checker binds it into topic closure.",
            ],
        }
    if claim_id == "claim-004":
        return {
            "layer_a_object_bytes": "VERIFIED_FOR_ALL_ENUMERATED_REQUIREMENTS",
            "layer_b_stored_assertions": {
                "status": "PUBLIC_RUN_ASSERTED_RELEVANCE_REVIEW_REMAINS_REQUIRED",
                "details": replay,
            },
            "layer_c_independent_run_identity": {
                "status": "PUBLIC_RUN_CORROBORATED_REVIEW_NOT_CORROBORATED",
                "reason": "Frozen target ordering is equal across input/output and the public log matches output run identity, but no relevance-review receipt is enumerated.",
            },
            "layer_d_current_qualification": no_current,
            "relationship_findings": {
                "frozen_input_to_output_target_identity": replay["input_output_target_ids_equal_in_order"],
                "log_output_identity_equal": replay["log_output_identity_equal"],
                "review_warning": replay["output_assertions"]["warnings"],
            },
            "support_level": "PARTIAL_FROZEN_INPUT_RUN_CORROBORATED_REVIEW_UNSUPPORTED",
            "gaps_and_contradictions": [
                "The public output warns that term-fallback targets require relevance review before closure.",
                "No enumerated receipt records reviewer identity, reviewed rows, decision, or binding hash.",
            ],
        }
    if claim_id == "claim-014":
        gate = parse_json(data_by_path, "wave56-semantic-vector-quality-gate/2026-05-23/semantic_vector_quality_gate.json")
        wave57_objects = [path for path in data_by_path if "wave57" in path.lower()]
        return {
            "layer_a_object_bytes": "BLOB_OIDS_EXIST_AND_BYTES_DERIVED_PATH_COMMITS_NOT_ENUMERATED",
            "layer_b_stored_assertions": {
                "status": "SOURCE_OBJECTS_AND_WAVE56_SCOPE_ASSERTED_NO_WAVE57_RECEIPT",
                "details": {
                    "wave56_contract_version": gate.get("contract_version"),
                    "wave56_status": gate.get("status"),
                    "wave56_scope": gate.get("scope"),
                    "wave56_production_quality_claim_allowed": gate.get("production_quality_claim_allowed"),
                    "wave56_archive_closed_recommendation": gate.get("archive_closed_recommendation"),
                },
            },
            "layer_c_independent_run_identity": {
                "status": "NOT_CORROBORATED_FOR_WAVE57",
                "reason": "The exact claim set contains no Wave57 receipt, corpus manifest, run id, or exact commit:path binding for these blobs.",
            },
            "layer_d_current_qualification": no_current,
            "relationship_findings": {
                "wave57_named_objects_in_exact_claim_set": wave57_objects,
                "wave56_gate_is_repo_local_no_network": gate.get("scope") == "repo_local_production_like_semantic_vector_quality_no_network_no_live_traffic",
                "wave56_production_quality_claim_allowed": gate.get("production_quality_claim_allowed"),
            },
            "support_level": "SOURCE_BLOBS_ONLY_WAVE57_LINEAGE_AND_RUN_UNSUPPORTED",
            "gaps_and_contradictions": [
                "No Wave57 execution receipt or corpus manifest is enumerated, so the claimed Wave57 input lineage cannot be bound.",
                "No commit identity is enumerated for these path/blob pairs; object existence does not prove either historical path mapping.",
                "Two different historical JSONL paths are assigned the same blob OID; without a commit tree this proves byte identity, not both path identities.",
                "The Wave56 record explicitly sets production_quality_claim_allowed=false and requires live production replay before archive closure.",
            ],
        }
    if claim_id == "claim-016":
        benchmark = parse_json(data_by_path, "local-index-lancedb-benchmark/2026-05-22/benchmark_quality_results.json")
        runtime = parse_json(data_by_path, "local-index-lancedb-runtime-smoke/2026-05-22/runtime_smoke_results.json")
        replay_doc = parse_json(data_by_path, "search-provider-container-replay/2026-05-22/provider_trace_replay_summary.json")
        trace = parse_json(data_by_path, "search-provider-trace-artifacts/2026-05-22/search_provider_trace_contract.json")
        return {
            "layer_a_object_bytes": "BLOB_OIDS_EXIST_AND_BYTES_DERIVED_PATH_COMMITS_NOT_ENUMERATED",
            "layer_b_stored_assertions": {
                "status": "FOUR_SOURCE_RECORDS_ASSERT_PASS_OR_OK_AGGREGATE_REUSE_NOT_ASSERTED",
                "details": {
                    "benchmark_status": benchmark.get("status"),
                    "runtime_status": runtime.get("status"),
                    "container_replay_ok": replay_doc.get("ok"),
                    "container_replay_passed_rows": replay_doc.get("passed_rows"),
                    "container_replay_failed_rows": replay_doc.get("failed_rows"),
                    "trace_contract_version": trace.get("contract_version"),
                    "trace_scope": trace.get("scope"),
                    "auto_route": trace.get("auto_route"),
                },
            },
            "layer_c_independent_run_identity": {
                "status": "NOT_CORROBORATED_FOR_WAVE8_AGGREGATE",
                "reason": "The four blobs are separate source records; no enumerated Wave8 aggregate, manifest, shared run id, hash binding, or commit:path identity connects their reuse.",
            },
            "layer_d_current_qualification": no_current,
            "relationship_findings": {
                "aggregate_wave8_objects_in_exact_claim_set": [path for path in data_by_path if "wave8" in path.lower()],
                "benchmark_remaining_blockers": benchmark.get("remaining_blockers", []),
            },
            "support_level": "FOUR_SOURCE_ASSERTIONS_ONLY_AGGREGATE_REUSE_UNSUPPORTED",
            "gaps_and_contradictions": [
                "The exact set omits the aggregate Wave8 contract required by the claim's own missing_specific_evidence field.",
                "No exact commit identity is enumerated for the four path/blob pairs.",
                "The benchmark record retains semantic_embedding_quality_not_proven and global_vector_contract_not_closed.",
            ],
        }
    raise ValueError(f"unexpected target claim: {claim_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = args.output if args.output.is_absolute() else repo / args.output

    contract_bytes = blob(repo, CONTRACT_BLOB)
    claim_table_bytes = blob(repo, CLAIM_TABLE_BLOB)
    if sha256(contract_bytes) != CONTRACT_SHA256:
        raise ValueError("contract blob SHA-256 mismatch")
    if sha256(claim_table_bytes) != CLAIM_TABLE_SHA256:
        raise ValueError("claim table blob SHA-256 mismatch")
    claim_table = json.loads(claim_table_bytes)
    claims = [claim for claim in claim_table["claims"] if claim.get("decision") == TARGET_DECISION]
    if [claim["claim_id"] for claim in claims] != TARGET_CLAIMS:
        raise ValueError("target claim identities/order differ from the exact claim table")

    occurrences_by_oid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    requirement_rows: list[dict[str, Any]] = []
    for claim in claims:
        for index, requirement in enumerate(claim["source_requirements"]):
            oid = object_oid(requirement)
            row_id = f"{claim['claim_id']}::source-{index + 1:02d}"
            row = {
                "requirement_row_id": row_id,
                "claim_id": claim["claim_id"],
                "provenance_entry_id": requirement.get("provenance_entry_id"),
                "missing_path": requirement["missing_path"],
                "required_factual_claim": requirement["required_factual_claim"],
                "classification_at_source": requirement["classification_at_source"],
                "git_blob_oid": oid,
                "enumerated_commit": requirement["historical_object"].get("head_commit"),
                "expected_bytes": requirement["historical_object"].get("bytes"),
                "expected_sha256": requirement["historical_object"].get("sha256"),
            }
            requirement_rows.append(row)
            occurrences_by_oid[oid].append(row)

    object_results: list[dict[str, Any]] = []
    bytes_by_oid: dict[str, bytes] = {}
    for oid in sorted(occurrences_by_oid):
        rows = occurrences_by_oid[oid]
        exists = subprocess.run(
            ["git", "cat-file", "-e", oid], cwd=repo, capture_output=True
        ).returncode == 0
        if not exists:
            object_results.append({"git_blob_oid": oid, "object_exists": False, "occurrence_row_ids": [row["requirement_row_id"] for row in rows]})
            continue
        object_type = git(repo, "cat-file", "-t", oid).decode().strip()
        data = blob(repo, oid) if object_type == "blob" else b""
        bytes_by_oid[oid] = data
        actual_size = int(git(repo, "cat-file", "-s", oid).decode().strip())
        actual_hash = sha256(data)
        expected_sizes = sorted({row["expected_bytes"] for row in rows if row["expected_bytes"] is not None})
        expected_hashes = sorted({row["expected_sha256"] for row in rows if row["expected_sha256"] is not None})
        paths = sorted({row["missing_path"] for row in rows})
        parse_results = {path: parseability(path, data) for path in paths}
        object_results.append(
            {
                "git_blob_oid": oid,
                "object_exists": True,
                "object_type": object_type,
                "actual_bytes": actual_size,
                "actual_sha256": actual_hash,
                "expected_bytes_values": expected_sizes,
                "expected_sha256_values": expected_hashes,
                "expected_bytes_match": all(size == actual_size for size in expected_sizes),
                "expected_sha256_match": all(value == actual_hash for value in expected_hashes),
                "parseability_by_path": parse_results,
                "occurrence_row_ids": [row["requirement_row_id"] for row in rows],
            }
        )

    object_by_oid = {item["git_blob_oid"]: item for item in object_results}
    for row in requirement_rows:
        obj = object_by_oid[row["git_blob_oid"]]
        commit = row["enumerated_commit"]
        if commit:
            completed = subprocess.run(
                ["git", "rev-parse", f"{commit}:{row['missing_path']}"],
                cwd=repo,
                capture_output=True,
            )
            resolved = completed.stdout.decode().strip() if completed.returncode == 0 else None
            row["commit_path_binding"] = {
                "status": "VERIFIED" if resolved == row["git_blob_oid"] else "MISMATCH_OR_MISSING",
                "resolved_git_oid": resolved,
                "matches_enumerated_blob": resolved == row["git_blob_oid"],
            }
        else:
            row["commit_path_binding"] = {
                "status": "NOT_ENUMERATED",
                "resolved_git_oid": None,
                "matches_enumerated_blob": None,
            }
        row["object_verification"] = {
            "object_exists": obj.get("object_exists", False),
            "object_type": obj.get("object_type"),
            "actual_bytes": obj.get("actual_bytes"),
            "actual_sha256": obj.get("actual_sha256"),
            "expected_bytes_match": row["expected_bytes"] is None or row["expected_bytes"] == obj.get("actual_bytes"),
            "expected_sha256_match": row["expected_sha256"] is None or row["expected_sha256"] == obj.get("actual_sha256"),
            "parseable": obj.get("parseability_by_path", {}).get(row["missing_path"], {}).get("parseable", False),
        }

    claim_receipts: list[dict[str, Any]] = []
    for claim in claims:
        rows = [row for row in requirement_rows if row["claim_id"] == claim["claim_id"]]
        data_by_path = {row["missing_path"]: bytes_by_oid[row["git_blob_oid"]] for row in rows if row["git_blob_oid"] in bytes_by_oid}
        assessment = assessment_for(claim["claim_id"], data_by_path)
        claim_receipts.append(
            {
                "claim_id": claim["claim_id"],
                "claim_key": claim["claim_key"],
                "claim_fingerprint_sha256": claim["claim_fingerprint_sha256"],
                "decision": claim["decision"],
                "factual_claim": claim["factual_claim"],
                "missing_specific_evidence": claim["missing_specific_evidence"],
                "dependent_nodeid_count": claim["dependent_nodeid_count"],
                "dependent_nodeids": [
                    {
                        "nodeid": nodeid,
                        "support_level": assessment["support_level"],
                        "current_test_qualification_granted": False,
                    }
                    for nodeid in claim["dependent_nodeids"]
                ],
                "requirement_row_ids": [row["requirement_row_id"] for row in rows],
                "four_layer_assessment": {
                    key: value for key, value in assessment.items() if key.startswith("layer_")
                },
                "relationship_findings": assessment["relationship_findings"],
                "gaps_and_contradictions": assessment["gaps_and_contradictions"],
            }
        )

    exact_comparable = [row for row in requirement_rows if row["expected_bytes"] is not None and row["expected_sha256"] is not None]
    enumerated_bindings = [row for row in requirement_rows if row["enumerated_commit"]]
    receipt = {
        "schema_version": "contract14.history_verification_receipt.v1",
        "record_id": "contract14-work-package-h-history-verification-v1",
        "status": "COMPLETED_WITH_PRESERVED_GAPS",
        "authoritative": False,
        "production_release_authorized": False,
        "current_qualification_granted": False,
        "history_only": True,
        "authority_ceiling": AUTHORITY_CEILING,
        "inputs": {
            "contract": {"git_blob_oid": CONTRACT_BLOB, "bytes": len(contract_bytes), "sha256": sha256(contract_bytes), "expected_sha256_match": True},
            "claim_table": {"git_blob_oid": CLAIM_TABLE_BLOB, "bytes": len(claim_table_bytes), "sha256": sha256(claim_table_bytes), "expected_sha256_match": True, "parsed_full_document": True},
        },
        "read_policy": {
            "interface": "Git read-only object interface",
            "commands": ["git cat-file -e <oid>", "git cat-file -t <oid>", "git cat-file -s <oid>", "git cat-file blob <oid>", "git rev-parse <commit>:<path>"],
            "historical_code_executed": False,
            "checkout_restore_or_copy_performed": False,
        },
        "summary": {
            "target_claim_count": len(claim_receipts),
            "requirement_row_count": len(requirement_rows),
            "unique_blob_count": len(object_results),
            "objects_existing_as_blob": sum(item.get("object_exists") and item.get("object_type") == "blob" for item in object_results),
            "all_unique_objects_exist_as_blob": all(item.get("object_exists") and item.get("object_type") == "blob" for item in object_results),
            "exact_size_sha_comparable_requirement_count": len(exact_comparable),
            "exact_size_sha_matches": sum(row["object_verification"]["expected_bytes_match"] and row["object_verification"]["expected_sha256_match"] for row in exact_comparable),
            "parseable_requirement_count": sum(row["object_verification"]["parseable"] for row in requirement_rows),
            "enumerated_commit_path_binding_count": len(enumerated_bindings),
            "verified_commit_path_binding_count": sum(row["commit_path_binding"]["status"] == "VERIFIED" for row in enumerated_bindings),
            "unbound_path_requirement_count": sum(row["commit_path_binding"]["status"] == "NOT_ENUMERATED" for row in requirement_rows),
            "dependent_nodeid_count": sum(claim["dependent_nodeid_count"] for claim in claim_receipts),
            "currently_qualified_nodeid_count": 0,
        },
        "claims": claim_receipts,
        "requirements": requirement_rows,
        "unique_objects": object_results,
        "scope_note": "Object and stored-record facts only. No historical receipt is made current; no live execution occurred.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
