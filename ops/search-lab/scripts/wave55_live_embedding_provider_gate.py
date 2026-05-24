#!/usr/bin/env python3
"""Wave55 repo-local live embedding provider gate.

This gate verifies an executable, no-network local embedding provider, readback
metadata, controlled retrieval quality, and search evidence/retrieval-run
contracts. It does not claim production semantic quality.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave55-live-embedding-provider/2026-05-23"

LOCAL_PROVIDER_CLOSED_CONDITIONS = [
    "external_embedding_provider_live_not_verified",
]

REMAINING_PRODUCTION_CONDITIONS = [
    "semantic_embedding_quality_not_proven",
    "production_vector_quality_not_proven",
]


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _corpus_rows() -> list[dict[str, Any]]:
    return [
        {
            "document_id": "wave55-robotics-policy",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave55-robotics-policy",
            "chunk_id": "wave55-robotics-policy:chunk:0",
            "source_id": "wave55-controlled-corpus",
            "title": "Robotics commercialization policy grants",
            "text": (
                "Robotics commercialization policy grant program for autonomous "
                "automation procurement and market deployment."
            ),
            "source_uri": "repo-local://wave55/robotics-policy",
            "expected_queries": ["robotics commercialization policy grant"],
        },
        {
            "document_id": "wave55-agriculture-risk",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave55-agriculture-risk",
            "chunk_id": "wave55-agriculture-risk:chunk:0",
            "source_id": "wave55-controlled-corpus",
            "title": "Agricultural commodity futures insurance",
            "text": (
                "Agricultural commodity futures insurance and crop risk policy "
                "for market volatility."
            ),
            "source_uri": "repo-local://wave55/agriculture-risk",
            "expected_queries": ["agricultural commodity futures insurance"],
        },
        {
            "document_id": "wave55-energy-storage",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave55-energy-storage",
            "chunk_id": "wave55-energy-storage:chunk:0",
            "source_id": "wave55-controlled-corpus",
            "title": "Renewable energy storage procurement",
            "text": (
                "Renewable energy storage battery procurement for grid resilience "
                "and public infrastructure."
            ),
            "source_uri": "repo-local://wave55/energy-storage",
            "expected_queries": ["renewable energy storage procurement"],
        },
        {
            "document_id": "wave55-unrelated-events",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave55-unrelated-events",
            "chunk_id": "wave55-unrelated-events:chunk:0",
            "source_id": "wave55-controlled-corpus",
            "title": "Festival ticketing operations",
            "text": "Music festival ticketing, venue staffing, food vendors, and weekend attendance.",
            "source_uri": "repo-local://wave55/unrelated-events",
            "expected_queries": [],
        },
    ]


def _quality_queries() -> list[dict[str, str]]:
    return [
        {
            "query": "robotics commercialization policy grant",
            "expected_document_id": "wave55-robotics-policy",
        },
        {
            "query": "agricultural commodity futures insurance",
            "expected_document_id": "wave55-agriculture-risk",
        },
        {
            "query": "renewable energy storage procurement",
            "expected_document_id": "wave55-energy-storage",
        },
    ]


def _rank_rows(query: str, rows: list[dict[str, Any]], provider: Any) -> list[dict[str, Any]]:
    from app.services.local_index import cosine_similarity

    query_vector = provider.embed_query(query)
    ranked: list[dict[str, Any]] = []
    provider_meta = provider.metadata()
    for row in rows:
        text = f"{row['title']}\n{row['text']}"
        vector = provider.embed_text(text)
        score = cosine_similarity(query_vector, vector)
        ranked.append(
            {
                **row,
                "summary": row["title"],
                "score": round(score, 6),
                "backend": "repo_local_live_embedding",
                "mode": "vector",
                "retrieval_mode": "vector",
                "embedding_provider": provider_meta["provider_id"],
                "embedding_model": provider_meta["model"],
                "embedding_model_version": provider_meta["model_version"],
                "embedding_dim": provider_meta["embedding_dim"],
                "vector_version": provider_meta["vector_version"],
                "provider_payload_kind": "repo_local_embedding_vector",
                "payload_provenance": {
                    "provider": provider_meta["provider_id"],
                    "backend": "repo_local_live_embedding",
                    "retrieval_mode": "vector",
                    "provider_payload_kind": "repo_local_embedding_vector",
                    "embedding_model": provider_meta["model"],
                    "embedding_model_version": provider_meta["model_version"],
                    "embedding_dim": provider_meta["embedding_dim"],
                    "vector_version": provider_meta["vector_version"],
                    "source": row["source_id"],
                    "source_id": row["source_id"],
                    "source_reference": row["source_uri"],
                    "reference": row["source_uri"],
                    "source_uri": row["source_uri"],
                    "score": round(score, 6),
                    "fallback_reason": None,
                },
                "tags": ["vector", "repo_local_live_embedding"],
            }
        )
    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def _quality_readback(rows: list[dict[str, Any]], provider: Any) -> tuple[dict[str, Any], list[str]]:
    cases: list[dict[str, Any]] = []
    failures: list[str] = []
    top1_hits = 0
    margins: list[float] = []
    for case in _quality_queries():
        ranked = _rank_rows(case["query"], rows, provider)
        top = ranked[0]
        second = ranked[1]
        passed = top["document_id"] == case["expected_document_id"]
        if passed:
            top1_hits += 1
        margin = round(float(top["score"]) - float(second["score"]), 6)
        margins.append(margin)
        if not passed:
            failures.append(
                f"{case['query']}: expected {case['expected_document_id']}, got {top['document_id']}"
            )
        if margin <= 0.02:
            failures.append(f"{case['query']}: top score margin too low: {margin}")
        cases.append(
            {
                "query": case["query"],
                "expected_document_id": case["expected_document_id"],
                "top_document_id": top["document_id"],
                "top_score": top["score"],
                "second_document_id": second["document_id"],
                "second_score": second["score"],
                "top_margin": margin,
                "passed": passed,
            }
        )
    top1_accuracy = round(top1_hits / len(cases), 6) if cases else 0.0
    if top1_accuracy < 1.0:
        failures.append(f"top1_accuracy below threshold: {top1_accuracy}")
    return (
        {
            "status": "passed" if not failures else "failed",
            "query_count": len(cases),
            "top1_accuracy": top1_accuracy,
            "top1_accuracy_threshold": 1.0,
            "min_top_margin": min(margins) if margins else 0.0,
            "min_top_margin_threshold": 0.02,
            "cases": cases,
        },
        failures,
    )


def build_contract() -> dict[str, Any]:
    from app.services.local_index import RepoLocalHashingEmbeddingProvider
    from app.services.search.vector_contracts import (
        SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
        SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
        build_retrieval_run_record,
        build_search_evidence_hits,
        load_retrieval_run_record,
        serialize_retrieval_run_record,
        validate_retrieval_run_record,
        validate_search_evidence_hit,
    )

    provider = RepoLocalHashingEmbeddingProvider()
    rows = _corpus_rows()
    provider_readback = provider.readback([row["text"] for row in rows] + [case["query"] for case in _quality_queries()])
    quality, quality_failures = _quality_readback(rows, provider)
    failures: list[str] = []
    if provider_readback.get("status") != "passed":
        failures.append("provider readback failed")
    failures.extend(quality_failures)

    top_rows = [_rank_rows(case["query"], rows, provider)[0] for case in _quality_queries()]
    query_group_id, evidence_hits = build_search_evidence_hits(
        top_rows,
        query="wave55 controlled live embedding quality set",
        project_key="demo_proj",
        rank_mode="vector",
        top_k=len(top_rows),
    )
    for hit in evidence_hits:
        try:
            validate_search_evidence_hit(hit)
        except ValueError as exc:
            failures.append(str(exc))
    retrieval_run = build_retrieval_run_record(
        query="wave55 controlled live embedding quality set",
        query_group_id=query_group_id,
        evidence_hits=evidence_hits,
        project_key="demo_proj",
        rank_mode="vector",
        top_k=len(top_rows),
    )
    readback = load_retrieval_run_record(serialize_retrieval_run_record(retrieval_run))
    try:
        validate_retrieval_run_record(readback)
    except ValueError as exc:
        failures.append(str(exc))

    return {
        "contract_version": "wave55-live-embedding-provider-gate.v1",
        "generated_by": "ops/search-lab/scripts/wave55_live_embedding_provider_gate.py",
        "status": "passed" if not failures else "failed",
        "scope": "repo_local_live_embedding_provider_no_network_no_external_api",
        "provider_readback": provider_readback,
        "quality_readback": quality,
        "retrieval_contracts": {
            "evidence_hit": SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
            "retrieval_run": SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
            "query_group_id": query_group_id,
            "retrieval_run_id": retrieval_run["run_id"],
            "readback_status": "passed",
            "evidence_hit_count": len(evidence_hits),
        },
        "closed_conditions": LOCAL_PROVIDER_CLOSED_CONDITIONS,
        "closed_condition_scope": {
            "external_embedding_provider_live_not_verified": (
                "closed for the executable repo-local provider path only; no external API/key/provider is claimed"
            ),
        },
        "remaining_conditions": REMAINING_PRODUCTION_CONDITIONS,
        "local_provider_closure_claim_allowed": True,
        "production_quality_claim_allowed": False,
        "archive_closed_recommendation": "do_not_mark_archive_closed_until_production_quality_evidence_exists",
        "sample_retrieval_run": retrieval_run,
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "live_embedding_provider_gate.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    quality = contract["quality_readback"]
    readme = [
        "# Wave55 Live Embedding Provider Gate",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        f"- local_provider_closure_claim_allowed: `{str(bool(contract['local_provider_closure_claim_allowed'])).lower()}`",
        f"- production_quality_claim_allowed: `{str(bool(contract['production_quality_claim_allowed'])).lower()}`",
        "",
        "## Provider",
        "",
        f"- provider_id: `{contract['provider_readback']['provider_id']}`",
        f"- model: `{contract['provider_readback']['model']}`",
        f"- model_version: `{contract['provider_readback']['model_version']}`",
        f"- embedding_dim: `{contract['provider_readback']['embedding_dim']}`",
        f"- network_required: `{str(bool(contract['provider_readback']['network_required'])).lower()}`",
        f"- live_provider_verified: `{str(bool(contract['provider_readback']['live_provider_verified'])).lower()}`",
        "",
        "## Quality Readback",
        "",
        f"- query_count: `{quality['query_count']}`",
        f"- top1_accuracy: `{quality['top1_accuracy']}`",
        f"- min_top_margin: `{quality['min_top_margin']}`",
        "",
        "## Decision",
        "",
        "- closed for repo-local provider scope: "
        + ", ".join(f"`{item}`" for item in contract["closed_conditions"]),
        "- still open for production: "
        + ", ".join(f"`{item}`" for item in contract["remaining_conditions"]),
        "",
        "## Rerun",
        "",
        "```bash",
        f"PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave55_live_embedding_provider_gate.py --out-dir {display_path(out_dir)}",
        "PYTHONPATH=main/backend python3 -m pytest -q "
        "main/backend/tests/unit/test_local_index_service_unittest.py "
        "main/backend/tests/unit/test_wave55_live_embedding_provider_gate_unittest.py",
        "```",
        "",
        "Full deterministic output is in `live_embedding_provider_gate.json`.",
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
                "closed_conditions": contract["closed_conditions"],
                "remaining_conditions": contract["remaining_conditions"],
                "out_dir": display_path(out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
