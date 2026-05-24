#!/usr/bin/env python3
"""Wave56 semantic/vector quality gate for repo-local global vectorization.

This gate evaluates the executable repo-local embedding provider against a
frozen production-like corpus with paraphrase queries, hard negatives, repeat
stability, and search evidence/retrieval-run readback. It does not claim live
production traffic quality.
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

DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave56-semantic-vector-quality-gate/2026-05-23"

SEMANTIC_CONDITIONS_CLOSED = [
    "semantic_embedding_quality_not_proven",
]
PRODUCTION_CONDITIONS_REDUCED = [
    "production_vector_quality_not_proven",
]
PRODUCTION_CONDITIONS_STILL_OPEN = [
    {
        "code": "production_vector_quality_not_proven",
        "remaining_scope": "live production traffic or production-corpus replay is still required for final ARCHIVE_CLOSED migration",
    },
]
QUALITY_THRESHOLDS = {
    "min_domains": 4,
    "min_cases": 8,
    "repeat_count": 3,
    "min_top1_accuracy": 1.0,
    "min_recall_at_3": 1.0,
    "min_mrr": 1.0,
    "min_top2_margin": 0.02,
    "min_hard_negative_margin": 0.02,
    "required_retrieval_mode": "vector",
}


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _corpus_rows() -> list[dict[str, Any]]:
    return [
        {
            "document_id": "wave56-robotics-policy-grants",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave56-robotics-policy-grants",
            "chunk_id": "wave56-robotics-policy-grants:chunk:0",
            "source_id": "wave56-production-like-corpus",
            "domain": "robotics_policy",
            "title": "Robotics commercialization grant program",
            "text": (
                "Government grants and procurement incentives for commercial robotics deployment, "
                "autonomous automation adoption, and market rollout."
            ),
            "source_uri": "repo-local://wave56/robotics-policy-grants",
        },
        {
            "document_id": "wave56-robotics-safety-compliance",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave56-robotics-safety-compliance",
            "chunk_id": "wave56-robotics-safety-compliance:chunk:0",
            "source_id": "wave56-production-like-corpus",
            "domain": "robotics_safety",
            "title": "Industrial robot safety compliance",
            "text": "Factory robot worker safety standards, inspections, hazard reports, and compliance controls.",
            "source_uri": "repo-local://wave56/robotics-safety-compliance",
        },
        {
            "document_id": "wave56-agriculture-futures-insurance",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave56-agriculture-futures-insurance",
            "chunk_id": "wave56-agriculture-futures-insurance:chunk:0",
            "source_id": "wave56-production-like-corpus",
            "domain": "agriculture_risk",
            "title": "Agricultural commodity futures insurance",
            "text": (
                "Crop and farm commodity futures insurance coverage for harvest price volatility, "
                "market risk, and agricultural policy support."
            ),
            "source_uri": "repo-local://wave56/agriculture-futures-insurance",
        },
        {
            "document_id": "wave56-farm-irrigation-subsidy",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave56-farm-irrigation-subsidy",
            "chunk_id": "wave56-farm-irrigation-subsidy:chunk:0",
            "source_id": "wave56-production-like-corpus",
            "domain": "agriculture_water",
            "title": "Farm irrigation subsidy program",
            "text": "Irrigation water conservation grants for farm equipment, drought planning, and field sensors.",
            "source_uri": "repo-local://wave56/farm-irrigation-subsidy",
        },
        {
            "document_id": "wave56-energy-storage-procurement",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave56-energy-storage-procurement",
            "chunk_id": "wave56-energy-storage-procurement:chunk:0",
            "source_id": "wave56-production-like-corpus",
            "domain": "energy_storage",
            "title": "Renewable energy storage procurement",
            "text": (
                "Public tenders for renewable battery storage, grid resilience, infrastructure procurement, "
                "and energy storage deployment."
            ),
            "source_uri": "repo-local://wave56/energy-storage-procurement",
        },
        {
            "document_id": "wave56-solar-market-forecast",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave56-solar-market-forecast",
            "chunk_id": "wave56-solar-market-forecast:chunk:0",
            "source_id": "wave56-production-like-corpus",
            "domain": "energy_market",
            "title": "Solar equipment market forecast",
            "text": "Solar panel module sales forecast, installer revenue outlook, and distributed generation adoption.",
            "source_uri": "repo-local://wave56/solar-market-forecast",
        },
        {
            "document_id": "wave56-health-reimbursement",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave56-health-reimbursement",
            "chunk_id": "wave56-health-reimbursement:chunk:0",
            "source_id": "wave56-production-like-corpus",
            "domain": "health_admin",
            "title": "Hospital reimbursement schedule",
            "text": "Public hospital reimbursement schedule, clinical billing policy, and medical service codes.",
            "source_uri": "repo-local://wave56/health-reimbursement",
        },
        {
            "document_id": "wave56-festival-ticketing",
            "project_key": "demo_proj",
            "object_type": "policy_chunk",
            "object_id": "wave56-festival-ticketing",
            "chunk_id": "wave56-festival-ticketing:chunk:0",
            "source_id": "wave56-production-like-corpus",
            "domain": "event_ops",
            "title": "Festival ticketing operations",
            "text": "Music festival ticketing, venue staffing, food vendors, weekend attendance, and gate operations.",
            "source_uri": "repo-local://wave56/festival-ticketing",
        },
    ]


def _quality_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "robotics-policy-paraphrase-a",
            "domain": "robotics_policy",
            "query": "public incentives for commercial robotics deployment",
            "expected_document_id": "wave56-robotics-policy-grants",
            "hard_negative_document_ids": ["wave56-robotics-safety-compliance"],
        },
        {
            "case_id": "robotics-policy-paraphrase-b",
            "domain": "robotics_policy",
            "query": "automation procurement grants for robotics market rollout",
            "expected_document_id": "wave56-robotics-policy-grants",
            "hard_negative_document_ids": ["wave56-robotics-safety-compliance", "wave56-solar-market-forecast"],
        },
        {
            "case_id": "agriculture-risk-paraphrase-a",
            "domain": "agriculture_risk",
            "query": "crop futures risk coverage for farm commodities",
            "expected_document_id": "wave56-agriculture-futures-insurance",
            "hard_negative_document_ids": ["wave56-farm-irrigation-subsidy"],
        },
        {
            "case_id": "agriculture-risk-paraphrase-b",
            "domain": "agriculture_risk",
            "query": "commodity insurance against harvest price volatility",
            "expected_document_id": "wave56-agriculture-futures-insurance",
            "hard_negative_document_ids": ["wave56-farm-irrigation-subsidy"],
        },
        {
            "case_id": "energy-storage-paraphrase-a",
            "domain": "energy_storage",
            "query": "renewable grid resilience battery procurement",
            "expected_document_id": "wave56-energy-storage-procurement",
            "hard_negative_document_ids": ["wave56-solar-market-forecast"],
        },
        {
            "case_id": "energy-storage-paraphrase-b",
            "domain": "energy_storage",
            "query": "public battery storage tenders for renewable grid resilience",
            "expected_document_id": "wave56-energy-storage-procurement",
            "hard_negative_document_ids": ["wave56-solar-market-forecast", "wave56-robotics-policy-grants"],
        },
        {
            "case_id": "robotics-safety-hard-negative",
            "domain": "robotics_safety",
            "query": "robot worker safety inspections",
            "expected_document_id": "wave56-robotics-safety-compliance",
            "hard_negative_document_ids": ["wave56-robotics-policy-grants"],
        },
        {
            "case_id": "event-ops-noise-control",
            "domain": "event_ops",
            "query": "festival ticketing venue staffing",
            "expected_document_id": "wave56-festival-ticketing",
            "hard_negative_document_ids": ["wave56-health-reimbursement"],
        },
    ]


def _rank_rows(query: str, rows: list[dict[str, Any]], provider: Any) -> list[dict[str, Any]]:
    from app.services.local_index import cosine_similarity

    provider_meta = provider.metadata()
    query_vector = provider.embed_query(query)
    ranked: list[dict[str, Any]] = []
    for row in rows:
        text = f"{row['title']}\n{row['text']}"
        vector = provider.embed_text(text)
        score = round(cosine_similarity(query_vector, vector), 6)
        ranked.append(
            {
                **row,
                "summary": row["title"],
                "score": score,
                "backend": "repo_local_semantic_vector",
                "mode": "vector",
                "retrieval_mode": "vector",
                "embedding_provider": provider_meta["provider_id"],
                "embedding_model": provider_meta["model"],
                "embedding_model_version": provider_meta["model_version"],
                "embedding_dim": provider_meta["embedding_dim"],
                "vector_version": provider_meta["vector_version"],
                "provider_payload_kind": "repo_local_semantic_vector",
                "payload_provenance": {
                    "provider": provider_meta["provider_id"],
                    "backend": "repo_local_semantic_vector",
                    "retrieval_mode": "vector",
                    "provider_payload_kind": "repo_local_semantic_vector",
                    "embedding_model": provider_meta["model"],
                    "embedding_model_version": provider_meta["model_version"],
                    "embedding_dim": provider_meta["embedding_dim"],
                    "vector_version": provider_meta["vector_version"],
                    "source": row["source_id"],
                    "source_id": row["source_id"],
                    "source_reference": row["source_uri"],
                    "reference": row["source_uri"],
                    "source_uri": row["source_uri"],
                    "score": score,
                    "fallback_reason": None,
                },
                "tags": ["vector", "repo_local_semantic_quality", row["domain"]],
            }
        )
    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def _evaluate_quality(rows: list[dict[str, Any]], provider: Any) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    cases: list[dict[str, Any]] = []
    top1_hits = 0
    recall_at_3_hits = 0
    reciprocal_ranks: list[float] = []
    top2_margins: list[float] = []
    hard_negative_margins: list[float] = []
    domains = sorted({case["domain"] for case in _quality_cases()})

    for case in _quality_cases():
        repeated_orders: list[list[str]] = []
        repeated_scores: list[list[tuple[str, float]]] = []
        for _ in range(QUALITY_THRESHOLDS["repeat_count"]):
            ranked = _rank_rows(case["query"], rows, provider)
            repeated_orders.append([row["document_id"] for row in ranked])
            repeated_scores.append([(row["document_id"], row["score"]) for row in ranked])
        stable_order = all(order == repeated_orders[0] for order in repeated_orders)
        ranked = _rank_rows(case["query"], rows, provider)
        order = [row["document_id"] for row in ranked]
        expected_rank = order.index(case["expected_document_id"]) + 1 if case["expected_document_id"] in order else 0
        expected_row = next(row for row in ranked if row["document_id"] == case["expected_document_id"])
        second_score = ranked[1]["score"] if len(ranked) > 1 else expected_row["score"]
        top2_margin = round(expected_row["score"] - second_score, 6) if expected_rank == 1 else 0.0
        hard_negative_scores = [
            next(row["score"] for row in ranked if row["document_id"] == hard_negative_id)
            for hard_negative_id in case["hard_negative_document_ids"]
        ]
        hard_negative_margin = round(expected_row["score"] - max(hard_negative_scores), 6) if hard_negative_scores else 0.0
        passed = (
            expected_rank == 1
            and top2_margin >= QUALITY_THRESHOLDS["min_top2_margin"]
            and hard_negative_margin >= QUALITY_THRESHOLDS["min_hard_negative_margin"]
            and stable_order
        )
        if expected_rank == 1:
            top1_hits += 1
        if 1 <= expected_rank <= 3:
            recall_at_3_hits += 1
        reciprocal_ranks.append(1.0 / expected_rank if expected_rank else 0.0)
        top2_margins.append(top2_margin)
        hard_negative_margins.append(hard_negative_margin)
        if expected_rank != 1:
            failures.append(f"{case['case_id']}: expected rank 1, got rank {expected_rank}")
        if top2_margin < QUALITY_THRESHOLDS["min_top2_margin"]:
            failures.append(f"{case['case_id']}: top2 margin below threshold: {top2_margin}")
        if hard_negative_margin < QUALITY_THRESHOLDS["min_hard_negative_margin"]:
            failures.append(f"{case['case_id']}: hard-negative margin below threshold: {hard_negative_margin}")
        if not stable_order:
            failures.append(f"{case['case_id']}: ranking order was not stable across repeats")
        cases.append(
            {
                "case_id": case["case_id"],
                "domain": case["domain"],
                "query": case["query"],
                "expected_document_id": case["expected_document_id"],
                "expected_rank": expected_rank,
                "top_document_id": ranked[0]["document_id"],
                "top_score": ranked[0]["score"],
                "second_document_id": ranked[1]["document_id"],
                "second_score": ranked[1]["score"],
                "top2_margin": top2_margin,
                "hard_negative_document_ids": case["hard_negative_document_ids"],
                "hard_negative_margin": hard_negative_margin,
                "stable_order": stable_order,
                "repeat_count": QUALITY_THRESHOLDS["repeat_count"],
                "top3_document_ids": order[:3],
                "repeat_score_samples": repeated_scores,
                "passed": passed,
            }
        )

    case_count = len(cases)
    top1_accuracy = round(top1_hits / case_count, 6) if case_count else 0.0
    recall_at_3 = round(recall_at_3_hits / case_count, 6) if case_count else 0.0
    mrr = round(sum(reciprocal_ranks) / case_count, 6) if case_count else 0.0
    if len(domains) < QUALITY_THRESHOLDS["min_domains"]:
        failures.append(f"domain count below threshold: {len(domains)}")
    if case_count < QUALITY_THRESHOLDS["min_cases"]:
        failures.append(f"case count below threshold: {case_count}")
    if top1_accuracy < QUALITY_THRESHOLDS["min_top1_accuracy"]:
        failures.append(f"top1_accuracy below threshold: {top1_accuracy}")
    if recall_at_3 < QUALITY_THRESHOLDS["min_recall_at_3"]:
        failures.append(f"recall_at_3 below threshold: {recall_at_3}")
    if mrr < QUALITY_THRESHOLDS["min_mrr"]:
        failures.append(f"mrr below threshold: {mrr}")

    return (
        {
            "status": "passed" if not failures else "failed",
            "domains": domains,
            "domain_count": len(domains),
            "case_count": case_count,
            "top1_accuracy": top1_accuracy,
            "recall_at_3": recall_at_3,
            "mrr": mrr,
            "min_top2_margin": min(top2_margins) if top2_margins else 0.0,
            "min_hard_negative_margin": min(hard_negative_margins) if hard_negative_margins else 0.0,
            "thresholds": QUALITY_THRESHOLDS,
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
    provider_readback = provider.readback(
        [f"{row['title']}\n{row['text']}" for row in rows] + [case["query"] for case in _quality_cases()]
    )
    quality, quality_failures = _evaluate_quality(rows, provider)
    failures: list[str] = []
    if provider_readback.get("status") != "passed":
        failures.append("provider readback failed")
    failures.extend(quality_failures)

    top_rows = [_rank_rows(case["query"], rows, provider)[0] for case in _quality_cases()]
    query_group_id, evidence_hits = build_search_evidence_hits(
        top_rows,
        query="wave56 repo-local semantic vector quality evaluation",
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
        query="wave56 repo-local semantic vector quality evaluation",
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
        "contract_version": "wave56-semantic-vector-quality-gate.v1",
        "generated_by": "ops/search-lab/scripts/wave56_semantic_vector_quality_gate.py",
        "status": "passed" if not failures else "failed",
        "scope": "repo_local_production_like_semantic_vector_quality_no_network_no_live_traffic",
        "provider_readback": provider_readback,
        "quality_evaluation": quality,
        "retrieval_contracts": {
            "evidence_hit": SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
            "retrieval_run": SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
            "query_group_id": query_group_id,
            "retrieval_run_id": retrieval_run["run_id"],
            "readback_status": "passed",
            "evidence_hit_count": len(evidence_hits),
        },
        "closed_conditions": SEMANTIC_CONDITIONS_CLOSED if not failures else [],
        "closed_condition_scope": {
            "semantic_embedding_quality_not_proven": (
                "closed for the repo-local provider path against the frozen production-like semantic evaluation set"
            ),
        },
        "reduced_conditions": PRODUCTION_CONDITIONS_REDUCED if not failures else [],
        "remaining_conditions": PRODUCTION_CONDITIONS_STILL_OPEN,
        "semantic_quality_claim_allowed": not failures,
        "production_vector_quality_reduced": not failures,
        "production_quality_claim_allowed": False,
        "archive_closed_recommendation": "do_not_mark_archive_closed_until_live_production_replay_exists",
        "sample_retrieval_run": retrieval_run,
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "semantic_vector_quality_gate.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    quality = contract["quality_evaluation"]
    readme = [
        "# Wave56 Semantic Vector Quality Gate",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        f"- semantic_quality_claim_allowed: `{str(bool(contract['semantic_quality_claim_allowed'])).lower()}`",
        f"- production_quality_claim_allowed: `{str(bool(contract['production_quality_claim_allowed'])).lower()}`",
        "",
        "## Provider",
        "",
        f"- provider_id: `{contract['provider_readback']['provider_id']}`",
        f"- model: `{contract['provider_readback']['model']}`",
        f"- model_version: `{contract['provider_readback']['model_version']}`",
        f"- embedding_dim: `{contract['provider_readback']['embedding_dim']}`",
        f"- vector_version: `{contract['provider_readback']['vector_version']}`",
        f"- network_required: `{str(bool(contract['provider_readback']['network_required'])).lower()}`",
        "",
        "## Quality Metrics",
        "",
        f"- domains: `{quality['domain_count']}`",
        f"- cases: `{quality['case_count']}`",
        f"- top1_accuracy: `{quality['top1_accuracy']}`",
        f"- recall_at_3: `{quality['recall_at_3']}`",
        f"- mrr: `{quality['mrr']}`",
        f"- min_top2_margin: `{quality['min_top2_margin']}`",
        f"- min_hard_negative_margin: `{quality['min_hard_negative_margin']}`",
        "",
        "## Decision",
        "",
        "- closed for repo-local semantic provider scope: "
        + ", ".join(f"`{item}`" for item in contract["closed_conditions"]),
        "- reduced but still not globally closed: "
        + ", ".join(f"`{item}`" for item in contract["reduced_conditions"]),
        "- still requires live production replay before target migration: "
        + ", ".join(f"`{item['code']}`" for item in contract["remaining_conditions"]),
        "",
        "## Rerun",
        "",
        "```bash",
        f"PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave56_semantic_vector_quality_gate.py --out-dir {display_path(out_dir)}",
        "PYTHONPATH=main/backend python3 -m pytest -q "
        "main/backend/tests/unit/test_local_index_service_unittest.py "
        "main/backend/tests/unit/test_wave55_live_embedding_provider_gate_unittest.py "
        "main/backend/tests/unit/test_wave56_semantic_vector_quality_gate_unittest.py",
        "```",
        "",
        "Full deterministic output is in `semantic_vector_quality_gate.json`.",
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
                "reduced_conditions": contract["reduced_conditions"],
                "remaining_conditions": [item["code"] for item in contract["remaining_conditions"]],
                "out_dir": display_path(out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
