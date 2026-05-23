#!/usr/bin/env python3
"""Wave29 global vector object and evidence-hit schema alignment gate.

This deterministic gate freezes the repo-local schema bridge between
main-search rows and the global vector/evidence-hit contract. It does not start
containers, call live providers, or claim production embedding quality.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave29-vector-schema-alignment/2026-05-23"

CLOSED_REPO_LOCAL_BLOCKERS = [
    "unified_vector_object_contract_not_frozen",
    "main_search_evidence_hit_contract_not_aligned",
    "embedding_qdrant_pgvector_payload_provenance_not_unified",
]

REMAINING_REPO_LOCAL_BLOCKERS = [
    "retrieval_runs_branches_hits_persistence_not_implemented",
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


def _fixture_rows() -> list[dict[str, Any]]:
    return [
        {
            "document_id": 17,
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": 17,
            "chunk_index": 0,
            "source_id": "source-policy",
            "vector_version": "v2",
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-large",
            "embedding_model_version": "2026-05-embedding-manifest",
            "embedding_dim": 3072,
            "score": 5.5,
            "backend": "opensearch",
            "mode": "bm25",
            "source_uri": "https://example.org/policy/17",
            "source_domain": "example.org",
            "effective_time": "2026-03-03",
            "language": "en",
            "tags": ["lexical", "bm25"],
        },
        {
            "document_id": 18,
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": 18,
            "chunk_id": "policy-18-chunk-0",
            "source_id": "source-policy",
            "vector_version": "v2",
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-large",
            "embedding_model_version": "2026-05-embedding-manifest",
            "embedding_dim": 3072,
            "score": 0.93,
            "backend": "qdrant",
            "mode": "vector",
            "source_reference": "qdrant://policy_chunks/policy-18-chunk-0",
            "tags": ["vector", "qdrant"],
        },
        {
            "document_id": 19,
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": 19,
            "source_id": "source-policy",
            "vector_version": "v1",
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
            "embedding_model_version": "2026-05-embedding-manifest",
            "embedding_dim": 1536,
            "score": 0.82,
            "backend": "pgvector",
            "mode": "vector",
            "source_reference": "postgres://embeddings/19",
            "fallback_reason": "qdrant_unavailable: deterministic gate fallback",
            "tags": ["vector", "pgvector", "fallback"],
        },
    ]


def build_contract() -> dict[str, Any]:
    from app.services.search.vector_contracts import (
        GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
        GLOBAL_VECTOR_OBJECT_PROVENANCE_REQUIRED_FIELDS,
        GLOBAL_VECTOR_OBJECT_REQUIRED_FIELDS,
        SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
        SEARCH_EVIDENCE_HIT_REQUIRED_FIELDS,
        build_search_evidence_hits,
        validate_search_evidence_hit,
    )

    failures: list[str] = []
    query_group_id, hits = build_search_evidence_hits(
        _fixture_rows(),
        query="robotics policy market",
        project_key="demo_proj",
        rank_mode="hybrid",
        state="CA",
        modality="text",
        top_k=3,
    )

    for hit in hits:
        try:
            validate_search_evidence_hit(hit)
        except ValueError as exc:
            failures.append(str(exc))

    observed_backends = [hit["backend"] for hit in hits]
    expected_backends = ["opensearch_lexical", "qdrant_vector", "pgvector_fallback"]
    if observed_backends != expected_backends:
        failures.append(f"backend normalization mismatch: {observed_backends!r}")

    observed_modes = [hit["retrieval_mode"] for hit in hits]
    if observed_modes != ["keyword", "vector", "vector"]:
        failures.append(f"retrieval mode normalization mismatch: {observed_modes!r}")

    if any(not hit.get("matrix_branch_id") for hit in hits):
        failures.append("all evidence hits must expose matrix_branch_id")
    if any(hit.get("query_group_id") != query_group_id for hit in hits):
        failures.append("all evidence hits must share query_group_id")
    for hit in hits:
        provenance = hit["global_vector_object"]["provenance"]
        missing = [
            field
            for field in GLOBAL_VECTOR_OBJECT_PROVENANCE_REQUIRED_FIELDS
            if field not in provenance
        ]
        if missing:
            failures.append(f"{hit['backend']}: payload provenance missing fields: {missing!r}")
    qdrant_hit = next(hit for hit in hits if hit["backend"] == "qdrant_vector")
    pgvector_hit = next(hit for hit in hits if hit["backend"] == "pgvector_fallback")
    if qdrant_hit["global_vector_object"]["provenance"].get("provider") != "openai":
        failures.append("qdrant payload provenance provider mismatch")
    if pgvector_hit["global_vector_object"]["provenance"].get("fallback_reason") != (
        "qdrant_unavailable: deterministic gate fallback"
    ):
        failures.append("pgvector payload provenance fallback_reason mismatch")

    return {
        "contract_version": "wave29-vector-schema-alignment-gate.v1",
        "generated_by": "ops/search-lab/scripts/wave29_vector_schema_alignment_gate.py",
        "status": "passed" if not failures else "failed",
        "scope": "deterministic_repo_local_global_vector_object_and_search_evidence_hit_schema_alignment",
        "schema_versions": {
            "global_vector_object": GLOBAL_VECTOR_OBJECT_CONTRACT_VERSION,
            "search_evidence_hit": SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
        },
        "required_fields": {
            "global_vector_object": list(GLOBAL_VECTOR_OBJECT_REQUIRED_FIELDS),
            "global_vector_object_provenance": list(GLOBAL_VECTOR_OBJECT_PROVENANCE_REQUIRED_FIELDS),
            "search_evidence_hit": list(SEARCH_EVIDENCE_HIT_REQUIRED_FIELDS),
        },
        "query_group_id": query_group_id,
        "sample_hit_count": len(hits),
        "sample_backends": observed_backends,
        "sample_retrieval_modes": observed_modes,
        "closed_repo_local_blockers": CLOSED_REPO_LOCAL_BLOCKERS,
        "remaining_repo_local_blockers": REMAINING_REPO_LOCAL_BLOCKERS,
        "external_conditions_still_open": EXTERNAL_CONDITIONS_STILL_OPEN,
        "archive_recommendation": "retain_current_dev_until_persistence_and_agent_join_are_closed",
        "closure_claim_allowed": False,
        "provider_live_closure_claim_allowed": False,
        "semantic_quality_claim_allowed": False,
        "payload_provenance_repo_local_closed": True,
        "material_changes": [
            "main_search_response_exposes_evidence_hits",
            "global_vector_object_schema_builder_added",
            "evidence_hit_schema_validator_added",
            "qdrant_pgvector_payload_provenance_unified",
        ],
        "sample_evidence_hits": hits,
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "vector_schema_alignment_gate.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = [
        "| closed repo-local blockers | "
        + ", ".join(f"`{item}`" for item in contract["closed_repo_local_blockers"])
        + " |",
        "| remaining repo-local blockers | "
        + ", ".join(f"`{item}`" for item in contract["remaining_repo_local_blockers"])
        + " |",
        "| external conditions still open | "
        + ", ".join(f"`{item}`" for item in contract["external_conditions_still_open"])
        + " |",
    ]
    readme = [
        "# Wave29 Vector Schema Alignment Gate",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        f"- archive_recommendation: `{contract['archive_recommendation']}`",
        "",
        "## Decision",
        "",
        "| item | value |",
        "|---|---|",
        *rows,
        "",
        "## Rerun",
        "",
        "```bash",
        f"PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave29_vector_schema_alignment_gate.py --out-dir {display_path(out_dir)}",
        "PYTHONPATH=main/backend python3 -m pytest -q "
        "main/backend/tests/unit/test_search_vector_contracts_unittest.py "
        "main/backend/tests/unit/test_wave29_vector_schema_alignment_gate_unittest.py "
        "main/backend/tests/contract/test_vectorization_contract_unittest.py "
        "main/backend/tests/core_business/test_search_core_contract.py",
        "```",
        "",
        "Full deterministic output is in `vector_schema_alignment_gate.json`.",
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
                "out_dir": display_path(out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
