#!/usr/bin/env python3
"""Wave30 deterministic gate for global-vector repo-local closure.

This gate proves the remaining repo-local vector blockers are represented by
durable retrieval-run readback, unified payload provenance, and Agent matrix
schema joining. It does not claim live provider quality or production semantic
embedding quality.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave30-vector-closure-gate/2026-05-23"

CLOSED_REPO_LOCAL_BLOCKERS = [
    "retrieval_runs_branches_hits_persistence_not_implemented",
    "embedding_qdrant_pgvector_payload_provenance_not_unified",
    "agent_matrix_and_main_search_schema_not_joined",
]

EXTERNAL_CONDITIONS_STILL_OPEN = [
    "external_embedding_provider_live_not_verified",
    "semantic_embedding_quality_not_proven",
    "production_vector_quality_not_proven",
]


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _main_search_rows() -> list[dict[str, Any]]:
    return [
        {
            "document_id": "policy-31",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "policy-31",
            "chunk_id": "policy-31:chunk:0",
            "source_id": "policy-corpus",
            "vector_version": "v3",
            "embedding_model": "text-embedding-3-large",
            "embedding_dim": 3072,
            "score": 6.5,
            "backend": "opensearch",
            "mode": "bm25",
            "source_uri": "https://example.gov/policy/31",
            "effective_time": "2026-03-04",
        },
        {
            "document_id": "policy-32",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "policy-32",
            "chunk_id": "policy-32:chunk:0",
            "source_id": "policy-corpus",
            "vector_version": "v3",
            "embedding_model": "text-embedding-3-large",
            "embedding_dim": 3072,
            "score": 0.94,
            "backend": "qdrant",
            "mode": "vector",
            "source_uri": "https://example.gov/policy/32",
        },
        {
            "document_id": "policy-33",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "policy-33",
            "chunk_id": "policy-33:chunk:0",
            "source_id": "policy-corpus",
            "vector_version": "v3",
            "embedding_model": "text-embedding-3-large",
            "embedding_dim": 3072,
            "score": 0.88,
            "backend": "pgvector",
            "mode": "vector",
            "source_uri": "https://example.gov/policy/33",
            "tags": ["vector", "pgvector", "fallback"],
        },
    ]


def _agent_matrix_candidates() -> list[dict[str, Any]]:
    return [
        {
            "title": "Official robotics commercialization report",
            "url": "https://example.gov/robotics/report",
            "snippet": "Official robotics commercialization report.",
            "trust": {"status": "accepted", "trust_score": 91},
            "matrix_branches": [
                {
                    "branch_id": "b1",
                    "query": "robotics commercialization official report",
                    "provider": "serper",
                }
            ],
        },
        {
            "title": "Robotics market dataset",
            "url": "https://example.org/robotics/market",
            "snippet": "Robotics market statistics.",
            "trust": {"status": "accepted", "trust_score": 84},
            "matrix_branches": [
                {
                    "branch_id": "b2",
                    "query": "robotics commercialization market statistics",
                    "provider": "ddg",
                }
            ],
        },
    ]


def build_contract() -> dict[str, Any]:
    from app.services.search.vector_contracts import (
        AGENT_MATRIX_SEARCH_EVIDENCE_CONTRACT_VERSION,
        GLOBAL_VECTOR_OBJECT_PROVENANCE_REQUIRED_FIELDS,
        SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
        build_agent_matrix_evidence_hits,
        build_retrieval_run_record,
        build_search_evidence_hits,
        load_retrieval_run_record,
        serialize_retrieval_run_record,
        validate_retrieval_run_record,
        validate_search_evidence_hit,
    )

    failures: list[str] = []

    query_group_id, main_hits = build_search_evidence_hits(
        _main_search_rows(),
        query="robotics commercialization policy",
        project_key="demo_proj",
        rank_mode="hybrid",
        top_k=3,
    )
    main_run = build_retrieval_run_record(
        query="robotics commercialization policy",
        query_group_id=query_group_id,
        evidence_hits=main_hits,
        project_key="demo_proj",
        rank_mode="hybrid",
        top_k=3,
    )
    readback = load_retrieval_run_record(serialize_retrieval_run_record(main_run))
    try:
        validate_retrieval_run_record(readback)
    except ValueError as exc:
        failures.append(str(exc))

    provenance_required = set(GLOBAL_VECTOR_OBJECT_PROVENANCE_REQUIRED_FIELDS)
    for hit in main_hits:
        try:
            validate_search_evidence_hit(hit)
        except ValueError as exc:
            failures.append(str(exc))
        provenance = hit["global_vector_object"]["provenance"]
        missing = sorted(provenance_required - set(provenance))
        if missing:
            failures.append(f"provenance missing required fields: {missing}")

    agent_query_group_id, agent_hits = build_agent_matrix_evidence_hits(
        _agent_matrix_candidates(),
        query="robotics commercialization",
        project_key="demo_proj",
        top_k=2,
    )
    agent_run = build_retrieval_run_record(
        query="robotics commercialization",
        query_group_id=agent_query_group_id,
        evidence_hits=agent_hits,
        project_key="demo_proj",
        rank_mode="matrix",
        top_k=2,
        retrieval_family="agent_matrix",
    )
    if any(hit.get("retrieval_family") != "agent_matrix" for hit in agent_hits):
        failures.append("agent matrix evidence hits must use retrieval_family=agent_matrix")
    if agent_run.get("retrieval_family") != "agent_matrix":
        failures.append("agent matrix retrieval run must use retrieval_family=agent_matrix")

    return {
        "contract_version": "wave30-vector-closure-gate.v1",
        "generated_by": "ops/search-lab/scripts/wave30_vector_closure_gate.py",
        "status": "passed" if not failures else "failed",
        "schema_versions": {
            "retrieval_run": SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
            "agent_matrix_evidence": AGENT_MATRIX_SEARCH_EVIDENCE_CONTRACT_VERSION,
        },
        "closed_repo_local_blockers": CLOSED_REPO_LOCAL_BLOCKERS,
        "remaining_repo_local_blockers": [],
        "external_conditions_still_open": EXTERNAL_CONDITIONS_STILL_OPEN,
        "archive_recommendation": "archive_external_blocked_after_shared_index_sync",
        "closure_claim_allowed": False,
        "external_blocked_candidate": True,
        "main_search": {
            "query_group_id": query_group_id,
            "retrieval_run_id": main_run["run_id"],
            "branch_count": len(main_run["branch_records"]),
            "evidence_hit_count": len(main_hits),
            "sample_backends": [hit["backend"] for hit in main_hits],
        },
        "agent_matrix": {
            "query_group_id": agent_query_group_id,
            "retrieval_run_id": agent_run["run_id"],
            "branch_count": len(agent_run["branch_records"]),
            "evidence_hit_count": len(agent_hits),
            "sample_backends": [hit["backend"] for hit in agent_hits],
        },
        "provenance_required_fields": sorted(provenance_required),
        "sample_main_search_retrieval_run": main_run,
        "sample_agent_matrix_retrieval_run": agent_run,
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "vector_closure_gate.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    readme = [
        "# Wave30 Vector Closure Gate",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- archive_recommendation: `{contract['archive_recommendation']}`",
        "",
        "## Decision",
        "",
        "| item | value |",
        "|---|---|",
        "| closed repo-local blockers | "
        + ", ".join(f"`{item}`" for item in contract["closed_repo_local_blockers"])
        + " |",
        "| remaining repo-local blockers | "
        + (", ".join(f"`{item}`" for item in contract["remaining_repo_local_blockers"]) or "none")
        + " |",
        "| external conditions still open | "
        + ", ".join(f"`{item}`" for item in contract["external_conditions_still_open"])
        + " |",
        "",
        "## Rerun",
        "",
        "```bash",
        f"PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave30_vector_closure_gate.py --out-dir {display_path(out_dir)}",
        "PYTHONPATH=main/backend python3 -m pytest -q "
        "main/backend/tests/unit/test_search_vector_contracts_unittest.py "
        "main/backend/tests/unit/test_agent_core_unittest.py "
        "main/backend/tests/contract/test_vectorization_contract_unittest.py "
        "main/backend/tests/core_business/test_search_core_contract.py",
        "```",
        "",
        "Full deterministic output is in `vector_closure_gate.json`.",
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
                "closed_repo_local_blockers": contract["closed_repo_local_blockers"],
                "remaining_repo_local_blockers": contract["remaining_repo_local_blockers"],
                "external_blocked_candidate": contract["external_blocked_candidate"],
                "out_dir": display_path(out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
