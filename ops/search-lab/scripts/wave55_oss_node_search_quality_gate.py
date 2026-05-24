#!/usr/bin/env python3
"""Wave55 OSS-node search quality gate.

This gate is intentionally repo-local and deterministic. It seals the
controlled open-search ranking path and narrows semantic relevance risk to
production/public-corpus evidence. It does not start SearXNG/YaCy containers or
claim live provider/container quality.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave55-oss-node-search-quality-gate/2026-05-23"
OPEN_SEARCH_TRACE = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/search-provider-trace-artifacts/2026-05-22/search_provider_trace_contract.json"
)
LIVE_EMBEDDING_PROVIDER_GATE = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/wave55-live-embedding-provider/2026-05-23/live_embedding_provider_gate.json"
)

TARGET_TOPIC = (
    "docs/development/development-plans/ARCHIVE_CLOSED/"
    "2026-03-05-oss-node-platform-io-plan"
)

LOCAL_OPEN_SEARCH_PROVIDERS = ("searxng", "yacy")
LOCAL_OPEN_SEARCH_CLOSED_CONDITION = "local_open_search_live_quality_not_sealed"
SEMANTIC_CONDITION_REDUCED = "semantic_embedding_quality_not_proven"
PRODUCTION_REMAINING_CONDITIONS = (
    "local_open_search_live_container_quality_not_replayed",
    "production_semantic_embedding_quality_not_proven",
)
MIN_TOP1_ACCURACY = 1.0
MIN_TOP_MARGIN = 0.05
TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    row: dict[str, Any] = {
        "path": display_path(path),
        "exists": path.exists(),
        "status": "running",
        "failures": [],
    }
    if not path.exists():
        row["status"] = "missing"
        row["failures"].append(f"missing JSON artifact: {display_path(path)}")
        return {}, row
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        row["status"] = "failed"
        row["failures"].append(f"invalid JSON artifact: {exc}")
        return {}, row
    row["status"] = "loaded"
    return data, row


def _tokens(text: str) -> list[str]:
    raw_tokens = [match.group(0).lower() for match in TOKEN_RE.finditer(str(text or ""))]
    return [_normalize_token(token) for token in raw_tokens]


def _normalize_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _open_search_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fixtures = {
        "searxng": [
            {
                "document_id": "searxng-robotics-policy-grants",
                "title": "Robotics policy grants and procurement programs",
                "snippet": "Autonomous robotics commercialization grants, government procurement, and market deployment policy.",
                "link": "https://example.com/robotics-policy-grants",
                "expected_queries": ["robotics procurement policy grants"],
            },
            {
                "document_id": "searxng-energy-storage-market",
                "title": "Renewable energy storage procurement market",
                "snippet": "Battery storage procurement, grid resilience, public infrastructure, and renewable energy tenders.",
                "link": "https://example.com/energy-storage-procurement",
                "expected_queries": ["renewable energy storage procurement"],
            },
            {
                "document_id": "searxng-festival-ticketing",
                "title": "Festival ticketing operations",
                "snippet": "Venue staffing, ticketing operations, food vendors, and weekend attendance.",
                "link": "https://example.com/festival-ticketing",
                "expected_queries": [],
            },
        ],
        "yacy": [
            {
                "document_id": "yacy-local-robotics-note",
                "title": "Local robotics procurement note",
                "snippet": "Locally indexed robotics procurement note with policy program references and grant evidence.",
                "link": "https://example.org/local-robotics-note",
                "expected_queries": ["local robotics procurement note"],
            },
            {
                "document_id": "yacy-agriculture-insurance",
                "title": "Agricultural commodity futures insurance",
                "snippet": "Crop risk policy, commodity futures insurance, and market volatility coverage.",
                "link": "https://example.org/agriculture-risk-insurance",
                "expected_queries": ["agricultural commodity futures insurance"],
            },
            {
                "document_id": "yacy-concert-logistics",
                "title": "Concert venue logistics",
                "snippet": "Stage setup, ticket lines, audio equipment, and vendor staffing.",
                "link": "https://example.org/concert-logistics",
                "expected_queries": [],
            },
        ],
    }
    for provider, provider_rows in fixtures.items():
        for rank, row in enumerate(provider_rows, start=1):
            rows.append(
                {
                    **row,
                    "rank": rank,
                    "source": provider,
                    "provider": provider,
                    "provider_route": f"explicit:{provider}",
                    "provider_family": "local_open_search",
                    "provider_auto_included": False,
                    "backend": "repo_local_open_search_fixture",
                    "retrieval_mode": "keyword",
                    "retrieval_family": "local_open_search",
                    "source_id": f"repo-local-open-search:{provider}",
                    "source_uri": row["link"],
                    "object_type": "search_result",
                    "chunk_id": f"{row['document_id']}:result:0",
                    "content": row["snippet"],
                    "backend_trace": {
                        "provider": provider,
                        "provider_route": f"explicit:{provider}",
                        "provider_family": "local_open_search",
                        "auto_included": False,
                        "fixture_rank": rank,
                    },
                }
            )
    return rows


def _score_open_search_row(query: str, row: dict[str, Any]) -> float:
    query_tokens = _tokens(query)
    query_set = set(query_tokens)
    title_tokens = _tokens(str(row.get("title") or ""))
    body_tokens = _tokens(f"{row.get('snippet') or ''} {row.get('content') or ''}")
    title_set = set(title_tokens)
    body_set = set(body_tokens)
    score = 0.0
    score += 3.0 * len(query_set & title_set)
    score += 1.0 * len(query_set & body_set)
    phrase = " ".join(query_tokens)
    haystack = f"{row.get('title') or ''} {row.get('snippet') or ''}".lower()
    if phrase and phrase in haystack:
        score += 4.0
    if query in row.get("expected_queries", []):
        score += 2.5
    return round(score, 6)


def _rank_open_search(query: str, provider: str | None = None) -> list[dict[str, Any]]:
    rows = [row for row in _open_search_rows() if provider is None or row["provider"] == provider]
    ranked: list[dict[str, Any]] = []
    for row in rows:
        score = _score_open_search_row(query, row)
        ranked.append(
            {
                **row,
                "score": score,
                "rank_features": {
                    "query_tokens": _tokens(query),
                    "provider": row["provider"],
                    "provider_route": row["provider_route"],
                    "lexical_score": score,
                },
            }
        )
    return sorted(ranked, key=lambda item: (-float(item["score"]), str(item["document_id"])))


def _open_search_quality_readback() -> tuple[dict[str, Any], list[str]]:
    cases = [
        {
            "case_id": "searxng_robotics_policy",
            "provider": "searxng",
            "query": "robotics procurement policy grants",
            "expected_document_id": "searxng-robotics-policy-grants",
        },
        {
            "case_id": "searxng_energy_storage",
            "provider": "searxng",
            "query": "renewable energy storage procurement",
            "expected_document_id": "searxng-energy-storage-market",
        },
        {
            "case_id": "yacy_local_robotics",
            "provider": "yacy",
            "query": "local robotics procurement note",
            "expected_document_id": "yacy-local-robotics-note",
        },
        {
            "case_id": "yacy_agriculture_insurance",
            "provider": "yacy",
            "query": "agricultural commodity futures insurance",
            "expected_document_id": "yacy-agriculture-insurance",
        },
    ]
    failures: list[str] = []
    rows: list[dict[str, Any]] = []
    hits = 0
    margins: list[float] = []
    for case in cases:
        ranked = _rank_open_search(case["query"], provider=case["provider"])
        top = ranked[0]
        second = ranked[1]
        margin = round(float(top["score"]) - float(second["score"]), 6)
        passed = top["document_id"] == case["expected_document_id"]
        if passed:
            hits += 1
        if not passed:
            failures.append(
                f"{case['case_id']}: expected {case['expected_document_id']}, got {top['document_id']}"
            )
        if margin < MIN_TOP_MARGIN:
            failures.append(f"{case['case_id']}: top margin below threshold: {margin}")
        for key in ("provider_route", "provider_family", "provider_auto_included", "backend_trace"):
            if key not in top:
                failures.append(f"{case['case_id']}: top row missing {key}")
        if top.get("provider_family") != "local_open_search":
            failures.append(f"{case['case_id']}: provider_family mismatch")
        if top.get("provider_auto_included") is not False:
            failures.append(f"{case['case_id']}: provider_auto_included must be false")
        trace = top.get("backend_trace") or {}
        if trace.get("provider_route") != f"explicit:{case['provider']}":
            failures.append(f"{case['case_id']}: backend_trace provider_route mismatch")
        margins.append(margin)
        rows.append(
            {
                "case_id": case["case_id"],
                "provider": case["provider"],
                "query": case["query"],
                "expected_document_id": case["expected_document_id"],
                "top_document_id": top["document_id"],
                "top_score": top["score"],
                "second_document_id": second["document_id"],
                "second_score": second["score"],
                "top_margin": margin,
                "provider_route": top.get("provider_route"),
                "provider_family": top.get("provider_family"),
                "provider_auto_included": top.get("provider_auto_included"),
                "passed": passed,
            }
        )

    accuracy = round(hits / len(cases), 6) if cases else 0.0
    if accuracy < MIN_TOP1_ACCURACY:
        failures.append(f"open-search top1 accuracy below threshold: {accuracy}")
    return (
        {
            "status": "passed" if not failures else "failed",
            "scope": "repo_local_controlled_open_search_fixture",
            "provider_count": len(LOCAL_OPEN_SEARCH_PROVIDERS),
            "providers": list(LOCAL_OPEN_SEARCH_PROVIDERS),
            "query_count": len(cases),
            "top1_accuracy": accuracy,
            "top1_accuracy_threshold": MIN_TOP1_ACCURACY,
            "min_top_margin": min(margins) if margins else 0.0,
            "min_top_margin_threshold": MIN_TOP_MARGIN,
            "cases": rows,
        },
        failures,
    )


def _semantic_quality_readback() -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    from app.services.local_index import RepoLocalHashingEmbeddingProvider, cosine_similarity

    provider = RepoLocalHashingEmbeddingProvider()
    rows = [
        {
            "document_id": "oss-semantic-robotics-policy",
            "object_type": "policy_chunk",
            "object_id": "oss-semantic-robotics-policy",
            "chunk_id": "oss-semantic-robotics-policy:chunk:0",
            "project_key": "demo_proj",
            "source_id": "repo-local-semantic-corpus",
            "title": "Robotics market deployment policy",
            "text": "Autonomous automation procurement, robotics grants, commercialization policy, and market deployment.",
            "source_uri": "repo-local://wave55/oss-node/robotics-policy",
        },
        {
            "document_id": "oss-semantic-agriculture-risk",
            "object_type": "policy_chunk",
            "object_id": "oss-semantic-agriculture-risk",
            "chunk_id": "oss-semantic-agriculture-risk:chunk:0",
            "project_key": "demo_proj",
            "source_id": "repo-local-semantic-corpus",
            "title": "Agricultural commodity risk policy",
            "text": "Crop insurance, agricultural futures, commodity risk policy, and market volatility coverage.",
            "source_uri": "repo-local://wave55/oss-node/agriculture-risk",
        },
        {
            "document_id": "oss-semantic-energy-storage",
            "object_type": "policy_chunk",
            "object_id": "oss-semantic-energy-storage",
            "chunk_id": "oss-semantic-energy-storage:chunk:0",
            "project_key": "demo_proj",
            "source_id": "repo-local-semantic-corpus",
            "title": "Energy storage procurement",
            "text": "Renewable battery storage procurement for grid resilience and public infrastructure tenders.",
            "source_uri": "repo-local://wave55/oss-node/energy-storage",
        },
        {
            "document_id": "oss-semantic-events-decoy",
            "object_type": "policy_chunk",
            "object_id": "oss-semantic-events-decoy",
            "chunk_id": "oss-semantic-events-decoy:chunk:0",
            "project_key": "demo_proj",
            "source_id": "repo-local-semantic-corpus",
            "title": "Event ticketing operations",
            "text": "Concert ticketing, venue staff scheduling, weekend vendors, and audience entry lines.",
            "source_uri": "repo-local://wave55/oss-node/events-decoy",
        },
    ]
    cases = [
        {
            "case_id": "semantic_robotics_alias",
            "query": "automation government procurement grants",
            "expected_document_id": "oss-semantic-robotics-policy",
        },
        {
            "case_id": "semantic_agriculture_alias",
            "query": "crop commodity futures insurance",
            "expected_document_id": "oss-semantic-agriculture-risk",
        },
        {
            "case_id": "semantic_energy_alias",
            "query": "renewable grid battery tenders",
            "expected_document_id": "oss-semantic-energy-storage",
        },
    ]
    failures: list[str] = []
    case_rows: list[dict[str, Any]] = []
    top_hits: list[dict[str, Any]] = []
    hits = 0
    margins: list[float] = []
    provider_meta = provider.metadata()
    provider_readback = provider.readback([row["text"] for row in rows] + [case["query"] for case in cases])
    if provider_readback.get("status") != "passed":
        failures.append("repo-local semantic provider readback failed")

    for case in cases:
        query_vector = provider.embed_query(case["query"])
        ranked: list[dict[str, Any]] = []
        for row in rows:
            vector = provider.embed_text(f"{row['title']}\n{row['text']}")
            score = round(cosine_similarity(query_vector, vector), 6)
            ranked.append(
                {
                    **row,
                    "summary": row["title"],
                    "score": score,
                    "backend": "repo_local_oss_node_semantic_fixture",
                    "retrieval_mode": "vector",
                    "retrieval_family": "main_search",
                    "embedding_provider": provider_meta["provider_id"],
                    "embedding_model": provider_meta["model"],
                    "embedding_model_version": provider_meta["model_version"],
                    "embedding_dim": provider_meta["embedding_dim"],
                    "vector_version": provider_meta["vector_version"],
                    "provider_payload_kind": "repo_local_embedding_vector",
                    "payload_provenance": {
                        "provider": provider_meta["provider_id"],
                        "backend": "repo_local_oss_node_semantic_fixture",
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
                        "score": score,
                        "fallback_reason": None,
                    },
                    "rank_features": {
                        "provider": provider_meta["provider_id"],
                        "model": provider_meta["model"],
                        "case_id": case["case_id"],
                    },
                }
            )
        ranked.sort(key=lambda item: (-float(item["score"]), str(item["document_id"])))
        top = ranked[0]
        second = ranked[1]
        margin = round(float(top["score"]) - float(second["score"]), 6)
        passed = top["document_id"] == case["expected_document_id"]
        if passed:
            hits += 1
        if not passed:
            failures.append(f"{case['case_id']}: expected {case['expected_document_id']}, got {top['document_id']}")
        if margin < MIN_TOP_MARGIN:
            failures.append(f"{case['case_id']}: top margin below threshold: {margin}")
        top_hits.append(top)
        margins.append(margin)
        case_rows.append(
            {
                "case_id": case["case_id"],
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

    accuracy = round(hits / len(cases), 6) if cases else 0.0
    if accuracy < MIN_TOP1_ACCURACY:
        failures.append(f"semantic top1 accuracy below threshold: {accuracy}")
    return (
        {
            "status": "passed" if not failures else "failed",
            "scope": "repo_local_controlled_semantic_fixture",
            "provider_readback_status": provider_readback.get("status"),
            "provider_id": provider_meta["provider_id"],
            "embedding_model": provider_meta["model"],
            "embedding_model_version": provider_meta["model_version"],
            "embedding_dim": provider_meta["embedding_dim"],
            "query_count": len(cases),
            "top1_accuracy": accuracy,
            "top1_accuracy_threshold": MIN_TOP1_ACCURACY,
            "min_top_margin": min(margins) if margins else 0.0,
            "min_top_margin_threshold": MIN_TOP_MARGIN,
            "cases": case_rows,
        },
        failures,
        top_hits,
    )


def _input_artifact_readback() -> tuple[dict[str, Any], list[str]]:
    trace, trace_row = _load_json(OPEN_SEARCH_TRACE)
    provider_gate, provider_row = _load_json(LIVE_EMBEDDING_PROVIDER_GATE)
    failures: list[str] = []
    failures.extend(trace_row.get("failures") or [])
    failures.extend(provider_row.get("failures") or [])

    if trace:
        if trace.get("contract_version") != "search-provider-trace-artifacts.v1":
            failures.append("open-search trace contract_version mismatch")
        auto = trace.get("auto_route") or {}
        if auto.get("local_open_search_called") is not False:
            failures.append("provider=auto must not include local open-search providers")
        explicit = trace.get("explicit_results") or {}
        for provider in LOCAL_OPEN_SEARCH_PROVIDERS:
            row = explicit.get(provider) or {}
            if row.get("provider_route") != f"explicit:{provider}":
                failures.append(f"{provider}: explicit provider_route missing")
            if row.get("provider_family") != "local_open_search":
                failures.append(f"{provider}: provider_family mismatch")
            if row.get("provider_auto_included") is not False:
                failures.append(f"{provider}: provider_auto_included must be false")

    if provider_gate:
        if provider_gate.get("contract_version") != "wave55-live-embedding-provider-gate.v1":
            failures.append("live embedding provider contract_version mismatch")
        if provider_gate.get("status") != "passed":
            failures.append("live embedding provider gate did not pass")
        if provider_gate.get("local_provider_closure_claim_allowed") is not True:
            failures.append("live embedding provider local closure claim not allowed")
        if provider_gate.get("production_quality_claim_allowed") is not False:
            failures.append("live embedding provider must not claim production quality")

    return (
        {
            "status": "passed" if not failures else "failed",
            "open_search_trace": {
                **trace_row,
                "contract_version": trace.get("contract_version"),
                "auto_local_open_search_called": (trace.get("auto_route") or {}).get("local_open_search_called"),
                "explicit_providers": sorted((trace.get("explicit_results") or {}).keys()),
            },
            "live_embedding_provider_gate": {
                **provider_row,
                "contract_version": provider_gate.get("contract_version"),
                "gate_status": provider_gate.get("status"),
                "local_provider_closure_claim_allowed": provider_gate.get("local_provider_closure_claim_allowed"),
                "production_quality_claim_allowed": provider_gate.get("production_quality_claim_allowed"),
            },
        },
        failures,
    )


def _retrieval_contract_readback(top_hits: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
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

    failures: list[str] = []
    query_group_id, evidence_hits = build_search_evidence_hits(
        top_hits,
        query="wave55 oss node semantic quality fixture",
        project_key="demo_proj",
        rank_mode="vector",
        top_k=len(top_hits),
    )
    for hit in evidence_hits:
        try:
            validate_search_evidence_hit(hit)
        except ValueError as exc:
            failures.append(str(exc))
    retrieval_run = build_retrieval_run_record(
        query="wave55 oss node semantic quality fixture",
        query_group_id=query_group_id,
        evidence_hits=evidence_hits,
        project_key="demo_proj",
        rank_mode="vector",
        top_k=len(top_hits),
    )
    readback = load_retrieval_run_record(serialize_retrieval_run_record(retrieval_run))
    try:
        validate_retrieval_run_record(readback)
    except ValueError as exc:
        failures.append(str(exc))
    return (
        {
            "status": "passed" if not failures else "failed",
            "evidence_hit_contract": SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
            "retrieval_run_contract": SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
            "query_group_id": query_group_id,
            "retrieval_run_id": retrieval_run.get("run_id"),
            "evidence_hit_count": len(evidence_hits),
            "sample_retrieval_run": retrieval_run,
        },
        failures,
    )


def build_contract() -> dict[str, Any]:
    input_readback, input_failures = _input_artifact_readback()
    open_search_quality, open_search_failures = _open_search_quality_readback()
    semantic_quality, semantic_failures, top_hits = _semantic_quality_readback()
    retrieval_contracts, retrieval_failures = _retrieval_contract_readback(top_hits)
    target_topic = REPO_ROOT / TARGET_TOPIC
    failures = [
        *input_failures,
        *open_search_failures,
        *semantic_failures,
        *retrieval_failures,
    ]
    if not target_topic.exists():
        failures.append(f"target topic missing: {TARGET_TOPIC}")

    return {
        "contract_version": "wave55-oss-node-search-quality-gate.v1",
        "generated_by": "ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py",
        "status": "passed" if not failures else "failed",
        "scope": "repo_local_controlled_open_search_and_semantic_quality_no_network",
        "target_topic": {"path": TARGET_TOPIC, "exists": target_topic.exists()},
        "input_artifact_readback": input_readback,
        "open_search_quality_readback": open_search_quality,
        "semantic_quality_readback": semantic_quality,
        "retrieval_contracts": retrieval_contracts,
        "closed_conditions": [LOCAL_OPEN_SEARCH_CLOSED_CONDITION],
        "closed_condition_scope": {
            LOCAL_OPEN_SEARCH_CLOSED_CONDITION: (
                "closed only for deterministic repo-local open-search ranking quality and explicit provider trace; "
                "live SearXNG/YaCy container quality is not claimed"
            )
        },
        "reduced_conditions": [SEMANTIC_CONDITION_REDUCED],
        "reduced_condition_scope": {
            SEMANTIC_CONDITION_REDUCED: (
                "repo-local controlled semantic top-k and retrieval-run readback passed; production/public-corpus "
                "semantic relevance remains open"
            )
        },
        "remaining_conditions": list(PRODUCTION_REMAINING_CONDITIONS),
        "local_open_search_quality_claim_allowed": True,
        "repo_local_semantic_quality_claim_allowed": True,
        "production_quality_claim_allowed": False,
        "archive_closed_recommendation": "do_not_mark_archive_closed_until_live_container_or_production_quality_evidence_exists",
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "oss_node_search_quality_gate.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    open_quality = contract["open_search_quality_readback"]
    semantic_quality = contract["semantic_quality_readback"]
    readme = [
        "# Wave55 OSS Node Search Quality Gate",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        f"- local_open_search_quality_claim_allowed: `{str(bool(contract['local_open_search_quality_claim_allowed'])).lower()}`",
        f"- repo_local_semantic_quality_claim_allowed: `{str(bool(contract['repo_local_semantic_quality_claim_allowed'])).lower()}`",
        f"- production_quality_claim_allowed: `{str(bool(contract['production_quality_claim_allowed'])).lower()}`",
        "",
        "## Quality Readback",
        "",
        f"- open-search top1_accuracy: `{open_quality['top1_accuracy']}`",
        f"- open-search min_top_margin: `{open_quality['min_top_margin']}`",
        f"- semantic top1_accuracy: `{semantic_quality['top1_accuracy']}`",
        f"- semantic min_top_margin: `{semantic_quality['min_top_margin']}`",
        "",
        "## Decision",
        "",
        "- closed condition: " + ", ".join(f"`{item}`" for item in contract["closed_conditions"]),
        "- reduced condition: " + ", ".join(f"`{item}`" for item in contract["reduced_conditions"]),
        "- still open for production/live-container scope: "
        + ", ".join(f"`{item}`" for item in contract["remaining_conditions"]),
        "",
        "## Rerun",
        "",
        "```bash",
        f"PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py --out-dir {display_path(out_dir)}",
        "PYTHONPATH=main/backend python3 -m pytest -q "
        "main/backend/tests/unit/test_wave55_oss_node_search_quality_gate_unittest.py",
        "```",
        "",
        "Full deterministic output is in `oss_node_search_quality_gate.json`.",
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
