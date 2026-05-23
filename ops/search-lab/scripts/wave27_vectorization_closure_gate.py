#!/usr/bin/env python3
"""Wave27 vectorization closure gate.

This gate aggregates the repo-local provider manifest, quality, and readback
evidence for the three CURRENT_DEV vectorization-adjacent topics. It decides
whether the directories are eligible for ARCHIVE_EXTERNAL_BLOCKED, without
calling live providers or changing topic directories.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave27-vectorization-closure/2026-05-23"

ARTIFACTS = {
    "wave10_quality_gate": {
        "path": "development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22/contract_summary.json",
        "expected_status": "passed",
        "expected_contract_version": "wave10-vectorization-quality-gate.v1",
    },
    "wave14_provider_capability": {
        "path": "development/latest-dev-docs/automation-runs/wave14-vectorization-provider-capability/2026-05-22/provider_capability_summary.json",
        "expected_status": "passed",
        "expected_contract_version": "wave14-vectorization-provider-capability.v1",
    },
    "wave18_hybrid_readback": {
        "path": "development/latest-dev-docs/automation-runs/wave18-vectorization-hybrid-readback/2026-05-22/hybrid_readback_contract.json",
        "expected_status": "passed",
        "expected_contract_version": "wave18-vectorization-hybrid-readback.v1",
    },
    "wave19_provider_manifest": {
        "path": "development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22/provider_manifest_readback.json",
        "expected_status": "passed",
        "expected_contract_version": "wave19-vectorization-provider-manifest.v1",
    },
    "lancedb_runtime_smoke": {
        "path": "development/latest-dev-docs/automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/runtime_smoke_results.json",
        "expected_status": "passed",
        "expected_contract_version": None,
    },
    "lancedb_benchmark_quality": {
        "path": "development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22/benchmark_quality_results.json",
        "expected_status": "passed",
        "expected_contract_version": None,
    },
}

TARGET_TOPICS = [
    {
        "slug": "2026-03-01-open-source-platform-integration",
        "title": "2026-03-01 Open Source Platform Integration",
        "path": "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-01-open-source-platform-integration",
        "existing_docs": [
            "06_wave19-vectorization-provider-manifest-2026-05-22.md",
            "07_wave22-vectorization-provider-external-blocked-decision-2026-05-22.md",
        ],
        "decision": "retain_current_dev",
        "archive_external_blocked_eligible": False,
        "repo_local_blockers": [
            "directory_scope_still_depends_on_retained_global_vector_contract",
            "directory_scope_still_depends_on_oss_node_platform_io_boundary",
        ],
        "external_conditions": [
            "external_embedding_provider_live_not_verified",
            "local_open_search_live_quality_not_sealed",
            "semantic_embedding_quality_not_proven",
            "oss_node_platform_io_sla_not_closed",
        ],
        "notes": (
            "The provider/vectorization slice is repo-local green, but this parent topic still references "
            "global vector schema and OSS-node IO closure surfaces that remain active elsewhere."
        ),
    },
    {
        "slug": "2026-05-14-global-vectorization-general-foundation",
        "title": "2026-05-14 Global Vectorization General Foundation",
        "path": "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-global-vectorization-general-foundation",
        "existing_docs": [
            "07_wave19-vectorization-provider-manifest-2026-05-22.md",
            "08_wave22-vectorization-provider-external-blocked-decision-2026-05-22.md",
        ],
        "decision": "retain_current_dev",
        "archive_external_blocked_eligible": False,
        "repo_local_blockers": [
            "unified_vector_object_contract_not_frozen",
            "retrieval_runs_branches_hits_persistence_not_implemented",
            "embedding_qdrant_pgvector_payload_provenance_not_unified",
            "main_search_evidence_hit_contract_not_aligned",
            "agent_matrix_and_main_search_schema_not_joined",
        ],
        "external_conditions": [
            "external_embedding_provider_live_not_verified",
            "semantic_embedding_quality_not_proven",
            "production_vector_quality_not_proven",
        ],
        "notes": (
            "This topic still owns repo-local vector object, retrieval persistence, provenance payload, "
            "and evidence-hit schema work. It is not just waiting on live provider quality."
        ),
    },
    {
        "slug": "2026-03-05-oss-node-platform-io-plan",
        "title": "2026-03-05 OSS Node Platform IO Plan",
        "path": "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-05-oss-node-platform-io-plan",
        "existing_docs": [
            "06_wave19-vectorization-provider-manifest-2026-05-22.md",
        ],
        "decision": "retain_current_dev",
        "archive_external_blocked_eligible": False,
        "repo_local_blockers": [
            "node_schema_runtime_persistence_platformization_scope_not_closed",
            "vector_search_node_manifest_consumption_not_live_replayed",
        ],
        "external_conditions": [
            "external_embedding_provider_live_not_verified",
            "local_open_search_live_quality_not_sealed",
            "semantic_embedding_quality_not_proven",
            "live_scheduler_tenant_db_ui_sla_not_proven",
        ],
        "notes": (
            "The vectorization provider manifest is consumable by nodes, but the original node-platform IO "
            "directory still has repo-local platformization scope beyond provider quality."
        ),
    },
]

REQUIRED_PROVIDER_MODES = {"keyword", "vector", "hybrid"}
REQUIRED_EXTERNAL_GAPS = {
    "external_embedding_provider_live_not_verified",
    "local_open_search_live_quality_not_sealed",
    "oss_node_platform_io_sla_not_closed",
    "provider_auto_promotion_not_allowed",
    "semantic_embedding_quality_not_proven",
}


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _resolve_artifact_path(name: str, overrides: dict[str, Path] | None) -> Path:
    if overrides and name in overrides:
        return overrides[name]
    return REPO_ROOT / str(ARTIFACTS[name]["path"])


def _load_artifact(name: str, overrides: dict[str, Path] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = ARTIFACTS[name]
    path = _resolve_artifact_path(name, overrides)
    row: dict[str, Any] = {
        "name": name,
        "path": display_path(path),
        "status": "running",
        "failures": [],
    }

    if not path.exists():
        row["status"] = "missing"
        row["failures"].append(f"{name}: artifact missing at {display_path(path)}")
        return {}, row

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        row["status"] = "failed"
        row["failures"].append(f"{name}: invalid JSON: {exc}")
        return {}, row

    failures: list[str] = []
    expected_status = spec["expected_status"]
    if data.get("status") != expected_status:
        failures.append(f"{name}: status expected {expected_status!r}, got {data.get('status')!r}")
    expected_contract_version = spec["expected_contract_version"]
    if expected_contract_version is not None and data.get("contract_version") != expected_contract_version:
        failures.append(
            f"{name}: contract_version expected {expected_contract_version!r}, got {data.get('contract_version')!r}"
        )

    row.update(
        {
            "status": "passed" if not failures else "failed",
            "contract_version": data.get("contract_version"),
            "input_status": data.get("status"),
            "failures": failures,
        }
    )
    return data, row


def _validate_provider_manifest(provider_manifest: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    if provider_manifest.get("closure_claim_allowed") is not False:
        failures.append("wave19 closure_claim_allowed must remain false")
    if provider_manifest.get("provider_live_closure_claim_allowed") is not False:
        failures.append("wave19 provider_live_closure_claim_allowed must remain false")
    if provider_manifest.get("semantic_quality_claim_allowed") is not False:
        failures.append("wave19 semantic_quality_claim_allowed must remain false")

    manifest = provider_manifest.get("provider_manifest") or {}
    modes = manifest.get("modes") or []
    mode_names = {str(row.get("mode")) for row in modes}
    if manifest.get("status") != "passed":
        failures.append(f"provider_manifest.status expected 'passed', got {manifest.get('status')!r}")
    missing_modes = sorted(REQUIRED_PROVIDER_MODES - mode_names)
    if missing_modes:
        failures.append(f"provider_manifest missing modes: {missing_modes}")

    for row in modes:
        mode = row.get("mode")
        if row.get("closure_claim_allowed") is not False:
            failures.append(f"{mode}: closure_claim_allowed must remain false")
        capabilities = row.get("capabilities") or {}
        if capabilities.get("live_provider_verified") is not False:
            failures.append(f"{mode}: live_provider_verified must remain false")
        if capabilities.get("semantic_quality_claim_allowed") is not False:
            failures.append(f"{mode}: semantic_quality_claim_allowed must remain false")
        trace_quality = row.get("trace_quality") or {}
        if trace_quality.get("status") != "passed":
            failures.append(f"{mode}: trace_quality.status expected 'passed'")
        if trace_quality.get("provider_live_verified") is not False:
            failures.append(f"{mode}: trace_quality.provider_live_verified must remain false")
        if trace_quality.get("semantic_quality_claim_allowed") is not False:
            failures.append(f"{mode}: trace_quality.semantic_quality_claim_allowed must remain false")

    boundary = provider_manifest.get("external_provider_boundary") or {}
    gap_codes = set(str(code) for code in boundary.get("gap_codes") or [])
    if boundary.get("status") != "passed":
        failures.append(f"external_provider_boundary.status expected 'passed', got {boundary.get('status')!r}")
    missing_gaps = sorted(REQUIRED_EXTERNAL_GAPS - gap_codes)
    if missing_gaps:
        failures.append(f"external_provider_boundary missing gaps: {missing_gaps}")

    return (
        {
            "status": "passed" if not failures else "failed",
            "provider_modes": sorted(mode_names),
            "required_external_gap_codes": sorted(REQUIRED_EXTERNAL_GAPS),
            "observed_external_gap_codes": sorted(gap_codes),
            "closure_claim_allowed": provider_manifest.get("closure_claim_allowed"),
            "provider_live_closure_claim_allowed": provider_manifest.get("provider_live_closure_claim_allowed"),
            "semantic_quality_claim_allowed": provider_manifest.get("semantic_quality_claim_allowed"),
        },
        failures,
    )


def _validate_quality_and_readback(artifacts: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    wave14 = artifacts["wave14_provider_capability"]
    wave18 = artifacts["wave18_hybrid_readback"]
    benchmark = artifacts["lancedb_benchmark_quality"]

    if wave14.get("closure_claim_allowed") is not False:
        failures.append("wave14 closure_claim_allowed must remain false")
    if wave18.get("closure_claim_allowed") is not False:
        failures.append("wave18 closure_claim_allowed must remain false")
    if wave18.get("semantic_quality_claim_allowed") is not False:
        failures.append("wave18 semantic_quality_claim_allowed must remain false")

    benchmark_blocker_codes = {str(row.get("code")) for row in benchmark.get("remaining_blockers") or []}
    if "semantic_embedding_quality_not_proven" not in benchmark_blocker_codes:
        failures.append("lancedb benchmark must preserve semantic_embedding_quality_not_proven")
    if "global_vector_contract_not_closed" not in benchmark_blocker_codes:
        failures.append("lancedb benchmark must preserve global_vector_contract_not_closed")

    return (
        {
            "status": "passed" if not failures else "failed",
            "wave14_closure_claim_allowed": wave14.get("closure_claim_allowed"),
            "wave18_closure_claim_allowed": wave18.get("closure_claim_allowed"),
            "wave18_semantic_quality_claim_allowed": wave18.get("semantic_quality_claim_allowed"),
            "benchmark_remaining_blocker_codes": sorted(benchmark_blocker_codes),
        },
        failures,
    )


def _build_topic_decisions(gate_status: str) -> tuple[list[dict[str, Any]], list[str]]:
    decisions: list[dict[str, Any]] = []
    failures: list[str] = []

    for topic in TARGET_TOPICS:
        topic_path = REPO_ROOT / topic["path"]
        existing_docs = []
        for doc_name in topic["existing_docs"]:
            doc_path = topic_path / doc_name
            exists = doc_path.exists()
            existing_docs.append({"path": display_path(doc_path), "exists": exists})
            if not exists:
                failures.append(f"{topic['slug']}: required existing doc missing: {doc_name}")

        repo_local_blockers = list(topic["repo_local_blockers"])
        decisions.append(
            {
                "slug": topic["slug"],
                "title": topic["title"],
                "path": topic["path"],
                "exists": topic_path.exists(),
                "existing_docs": existing_docs,
                "provider_manifest_quality_readback_gate": gate_status,
                "provider_slice_repo_local_closed": gate_status == "passed",
                "decision": topic["decision"],
                "archive_external_blocked_eligible": bool(topic["archive_external_blocked_eligible"]),
                "repo_local_blockers": repo_local_blockers,
                "external_conditions": list(topic["external_conditions"]),
                "notes": topic["notes"],
            }
        )
        if not topic_path.exists():
            failures.append(f"{topic['slug']}: topic path missing: {topic['path']}")
        if topic["archive_external_blocked_eligible"] and repo_local_blockers:
            failures.append(f"{topic['slug']}: eligible topic cannot keep repo_local_blockers")

    return decisions, failures


def build_contract(*, artifact_overrides: dict[str, Path] | None = None) -> dict[str, Any]:
    artifacts: dict[str, dict[str, Any]] = {}
    artifact_rows: dict[str, dict[str, Any]] = {}
    failures: list[str] = []

    for name in ARTIFACTS:
        data, row = _load_artifact(name, artifact_overrides)
        artifacts[name] = data
        artifact_rows[name] = row
        failures.extend(row.get("failures", []))

    provider_manifest_check, provider_failures = _validate_provider_manifest(artifacts["wave19_provider_manifest"])
    quality_readback_check, quality_failures = _validate_quality_and_readback(artifacts)
    failures.extend(f"provider_manifest_check: {failure}" for failure in provider_failures)
    failures.extend(f"quality_readback_check: {failure}" for failure in quality_failures)

    gate_status = "passed" if not provider_failures and not quality_failures else "failed"
    topic_decisions, topic_failures = _build_topic_decisions(gate_status)
    failures.extend(f"topic_decisions: {failure}" for failure in topic_failures)

    retained_topics = [row for row in topic_decisions if row["decision"] == "retain_current_dev"]
    archive_candidates = [row for row in topic_decisions if row["archive_external_blocked_eligible"]]

    return {
        "contract_version": "wave27-vectorization-closure-gate.v1",
        "generated_by": "ops/search-lab/scripts/wave27_vectorization_closure_gate.py",
        "status": "passed" if not failures else "failed",
        "scope": "current_dev_vectorization_provider_manifest_quality_readback_closure_decision",
        "artifact_inputs": artifact_rows,
        "provider_manifest_check": provider_manifest_check,
        "quality_readback_check": quality_readback_check,
        "topic_decisions": topic_decisions,
        "summary": {
            "topic_count": len(topic_decisions),
            "retained_current_dev_count": len(retained_topics),
            "archive_external_blocked_candidate_count": len(archive_candidates),
            "archive_external_blocked_patch_prepared": bool(archive_candidates),
            "provider_slice_repo_local_closed_count": sum(
                1 for row in topic_decisions if row["provider_slice_repo_local_closed"]
            ),
            "topics_with_repo_local_blockers": [
                row["slug"] for row in topic_decisions if row["repo_local_blockers"]
            ],
        },
        "gate_semantics": {
            "status_passed_means": (
                "provider manifest, deterministic quality, and readback artifacts are present, passed, "
                "and still preserve no-live-provider/no-semantic-quality closure claims"
            ),
            "status_passed_does_not_mean": (
                "the three CURRENT_DEV directories can migrate; directory-level repo-local blockers are "
                "reported separately in topic_decisions"
            ),
        },
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "vectorization_closure_gate.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    topic_rows = []
    for row in contract["topic_decisions"]:
        blockers = ", ".join(f"`{code}`" for code in row["repo_local_blockers"]) or "none"
        external = ", ".join(f"`{code}`" for code in row["external_conditions"])
        topic_rows.append(
            "| {slug} | {decision} | {eligible} | {gate} | {blockers} | {external} |".format(
                slug=row["slug"],
                decision=f"`{row['decision']}`",
                eligible=str(bool(row["archive_external_blocked_eligible"])).lower(),
                gate=f"`{row['provider_manifest_quality_readback_gate']}`",
                blockers=blockers,
                external=external,
            )
        )

    readme = [
        "# Wave27 Vectorization Closure Gate",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        f"- archive_external_blocked_patch_prepared: `{str(bool(contract['summary']['archive_external_blocked_patch_prepared'])).lower()}`",
        "",
        "## Decision Matrix",
        "",
        "| topic | decision | archive_external_blocked_eligible | provider/quality/readback gate | repo-local blockers | external conditions |",
        "|---|---|---:|---|---|---|",
        *topic_rows,
        "",
        "## Gate Semantics",
        "",
        f"- status passed means: {contract['gate_semantics']['status_passed_means']}",
        f"- status passed does not mean: {contract['gate_semantics']['status_passed_does_not_mean']}",
        "",
        "## Rerun",
        "",
        "```bash",
        f"PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave27_vectorization_closure_gate.py --out-dir {display_path(out_dir)}",
        "PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave27_vectorization_closure_gate_unittest.py",
        "```",
        "",
        "Full deterministic output is in `vectorization_closure_gate.json`.",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    contract = build_contract()
    write_outputs(out_dir, contract)
    print(
        json.dumps(
            {
                "status": contract["status"],
                "contract_version": contract["contract_version"],
                "retained_current_dev_count": contract["summary"]["retained_current_dev_count"],
                "archive_external_blocked_candidate_count": contract["summary"][
                    "archive_external_blocked_candidate_count"
                ],
                "out_dir": display_path(out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
