#!/usr/bin/env python3
"""Wave57 OSS-node public-corpus semantic relevance gate.

This gate attaches public OSS corpus evidence to the OSS-node provider-quality
blocker. It reads fixed excerpts from the checked-in `reference-pool/oss`
corpus, evaluates deterministic semantic ranking with the executable repo-local
embedding provider, and validates search evidence / retrieval-run contracts.

It does not start SearXNG/YaCy containers and does not claim generic production
traffic quality outside this target-local public-corpus route.
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

DEFAULT_OUT_DIR = (
    "development/latest-dev-docs/automation-runs/"
    "wave57-oss-node-public-corpus-semantic-relevance-gate/2026-05-23"
)
TARGET_TOPIC = (
    "docs/development/development-plans/ARCHIVE_CLOSED/"
    "2026-03-05-oss-node-platform-io-plan"
)
PUBLIC_CORPUS_INDEX = REPO_ROOT / "reference-pool" / "oss" / "INDEX.md"
WAVE55_SEARCH_QUALITY_ARTIFACT = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/wave55-oss-node-search-quality-gate/2026-05-23/"
    "oss_node_search_quality_gate.json"
)

CONTRACT_VERSION = "wave57-oss-node-public-corpus-semantic-relevance-gate.v1"
MIN_TOP1_ACCURACY = 1.0
MIN_RECALL_AT_3 = 1.0
MIN_MRR = 1.0
MIN_TOP2_MARGIN = 0.05
MIN_HARD_NEGATIVE_MARGIN = 0.05
MIN_PUBLIC_SOURCES = 6
MIN_CASES = 7
REPEAT_COUNT = 3


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


def _corpus_specs() -> list[dict[str, Any]]:
    return [
        {
            "document_id": "public-oss-dify-rag-workflow",
            "repo": "dify",
            "path": "reference-pool/oss/dify/README.md",
            "line_start": 59,
            "line_end": 104,
            "title": "Dify LLM application workflow RAG agent platform",
            "domain": "llm_app_rag",
            "required_markers": ["RAG pipelines", "Agent capabilities", "model management"],
        },
        {
            "document_id": "public-oss-n8n-workflow-automation",
            "repo": "n8n",
            "path": "reference-pool/oss/n8n/README.md",
            "line_start": 3,
            "line_end": 15,
            "title": "n8n workflow automation integrations AI native",
            "domain": "workflow_automation",
            "required_markers": ["workflow automation platform", "400+ integrations", "AI-Native Platform"],
        },
        {
            "document_id": "public-oss-langflow-agent-mcp",
            "repo": "langflow",
            "path": "reference-pool/oss/langflow/README.md",
            "line_start": 16,
            "line_end": 26,
            "title": "Langflow visual AI agents workflows MCP vector database",
            "domain": "visual_agent_workflow",
            "required_markers": ["AI-powered agents and workflows", "MCP server", "vector databases"],
        },
        {
            "document_id": "public-oss-outline-knowledge-base",
            "repo": "outline",
            "path": "reference-pool/oss/outline/README.md",
            "line_start": 8,
            "line_end": 10,
            "title": "Outline collaborative knowledge base React Node.js",
            "domain": "knowledge_base",
            "required_markers": ["collaborative", "knowledge base", "React and Node.js"],
        },
        {
            "document_id": "public-oss-silverbullet-ai-semantic-search",
            "repo": "silverbullet-ai",
            "path": "reference-pool/oss/silverbullet-ai/README.md",
            "line_start": 14,
            "line_end": 22,
            "title": "SilverBullet AI RAG vector embeddings semantic search",
            "domain": "note_embedding_search",
            "required_markers": ["RAG", "vector embedding search", "semantic search"],
        },
        {
            "document_id": "public-oss-langgraph-stateful-agent",
            "repo": "langgraph",
            "path": "reference-pool/oss/agent-cases/langgraph/README.md",
            "line_start": 16,
            "line_end": 70,
            "title": "LangGraph stateful agents durable execution memory",
            "domain": "stateful_agent_runtime",
            "required_markers": ["long-running, stateful agents", "Durable execution", "Comprehensive memory"],
        },
        {
            "document_id": "public-oss-temporal-durable-workflow",
            "repo": "temporal",
            "path": "reference-pool/oss/temporal/README.md",
            "line_start": 23,
            "line_end": 60,
            "title": "Temporal durable execution workflows retry Web UI",
            "domain": "durable_workflow_runtime",
            "required_markers": ["durable execution platform", "Workflows", "Temporal Web UI"],
        },
    ]


def _read_excerpt(path: Path, line_start: int, line_end: int) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[line_start - 1 : line_end])


def _build_public_corpus_rows() -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for spec in _corpus_specs():
        path = REPO_ROOT / str(spec["path"])
        if not path.exists():
            failures.append(f"{spec['document_id']}: missing public corpus file {display_path(path)}")
            continue
        text = _read_excerpt(path, int(spec["line_start"]), int(spec["line_end"]))
        if not text.strip():
            failures.append(f"{spec['document_id']}: empty public corpus excerpt")
        lowered = text.lower()
        for marker in spec["required_markers"]:
            if str(marker).lower() not in lowered:
                failures.append(f"{spec['document_id']}: missing marker {marker!r}")
        rows.append(
            {
                "document_id": spec["document_id"],
                "project_key": "oss_node_public_corpus",
                "object_type": "public_oss_excerpt",
                "object_id": spec["document_id"],
                "chunk_id": f"{spec['document_id']}:lines:{spec['line_start']}-{spec['line_end']}",
                "source_id": "reference-pool/oss",
                "source_repo": spec["repo"],
                "source_path": spec["path"],
                "source_line_start": spec["line_start"],
                "source_line_end": spec["line_end"],
                "source_uri": f"repo-local://{spec['path']}#L{spec['line_start']}-L{spec['line_end']}",
                "domain": spec["domain"],
                "title": spec["title"],
                "text": text,
            }
        )
    return rows, failures


def _quality_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "dify-rag-workflow",
            "domain": "llm_app_rag",
            "query": "LLM applications with RAG pipelines agent capabilities and model management",
            "expected_document_id": "public-oss-dify-rag-workflow",
            "hard_negative_document_ids": [
                "public-oss-n8n-workflow-automation",
                "public-oss-langgraph-stateful-agent",
            ],
        },
        {
            "case_id": "n8n-workflow-automation",
            "domain": "workflow_automation",
            "query": "workflow automation platform with integrations and native AI capabilities",
            "expected_document_id": "public-oss-n8n-workflow-automation",
            "hard_negative_document_ids": [
                "public-oss-dify-rag-workflow",
                "public-oss-langflow-agent-mcp",
            ],
        },
        {
            "case_id": "langflow-agent-mcp",
            "domain": "visual_agent_workflow",
            "query": "visual authoring AI agents workflows MCP server vector databases",
            "expected_document_id": "public-oss-langflow-agent-mcp",
            "hard_negative_document_ids": [
                "public-oss-n8n-workflow-automation",
                "public-oss-langgraph-stateful-agent",
            ],
        },
        {
            "case_id": "outline-knowledge-base",
            "domain": "knowledge_base",
            "query": "fast collaborative knowledge base for team built with React Node.js",
            "expected_document_id": "public-oss-outline-knowledge-base",
            "hard_negative_document_ids": [
                "public-oss-dify-rag-workflow",
                "public-oss-langflow-agent-mcp",
            ],
        },
        {
            "case_id": "silverbullet-ai-semantic-search",
            "domain": "note_embedding_search",
            "query": "automatic vector embedding semantic search for relevant note context",
            "expected_document_id": "public-oss-silverbullet-ai-semantic-search",
            "hard_negative_document_ids": [
                "public-oss-dify-rag-workflow",
                "public-oss-langgraph-stateful-agent",
            ],
        },
        {
            "case_id": "langgraph-stateful-agent",
            "domain": "stateful_agent_runtime",
            "query": "long-running stateful agents durable execution memory and human oversight",
            "expected_document_id": "public-oss-langgraph-stateful-agent",
            "hard_negative_document_ids": [
                "public-oss-temporal-durable-workflow",
                "public-oss-langflow-agent-mcp",
            ],
        },
        {
            "case_id": "temporal-durable-workflow",
            "domain": "durable_workflow_runtime",
            "query": "durable execution workflows retries failed operations Temporal Web UI",
            "expected_document_id": "public-oss-temporal-durable-workflow",
            "hard_negative_document_ids": [
                "public-oss-langgraph-stateful-agent",
                "public-oss-n8n-workflow-automation",
            ],
        },
    ]


def _rank_rows(query: str, rows: list[dict[str, Any]], provider: Any) -> list[dict[str, Any]]:
    from app.services.local_index import cosine_similarity

    provider_meta = provider.metadata()
    query_vector = provider.embed_query(query)
    ranked: list[dict[str, Any]] = []
    for row in rows:
        vector = provider.embed_text(f"{row['title']}\n{row['text']}")
        score = round(cosine_similarity(query_vector, vector), 6)
        ranked.append(
            {
                **row,
                "summary": row["title"],
                "score": score,
                "backend": "repo_local_public_oss_semantic_corpus",
                "mode": "vector",
                "retrieval_mode": "vector",
                "retrieval_family": "main_search",
                "embedding_provider": provider_meta["provider_id"],
                "embedding_model": provider_meta["model"],
                "embedding_model_version": provider_meta["model_version"],
                "embedding_dim": provider_meta["embedding_dim"],
                "vector_version": provider_meta["vector_version"],
                "provider_payload_kind": "repo_local_public_corpus_embedding_vector",
                "payload_provenance": {
                    "provider": provider_meta["provider_id"],
                    "backend": "repo_local_public_oss_semantic_corpus",
                    "retrieval_mode": "vector",
                    "provider_payload_kind": "repo_local_public_corpus_embedding_vector",
                    "embedding_model": provider_meta["model"],
                    "embedding_model_version": provider_meta["model_version"],
                    "embedding_dim": provider_meta["embedding_dim"],
                    "vector_version": provider_meta["vector_version"],
                    "source": row["source_id"],
                    "source_id": row["source_id"],
                    "source_repo": row["source_repo"],
                    "source_reference": row["source_uri"],
                    "reference": row["source_uri"],
                    "source_uri": row["source_uri"],
                    "score": score,
                    "fallback_reason": None,
                },
                "tags": ["vector", "public_oss_corpus", row["domain"]],
            }
        )
    return sorted(ranked, key=lambda item: (-float(item["score"]), str(item["document_id"])))


def _evaluate_quality(rows: list[dict[str, Any]], provider: Any) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    case_rows: list[dict[str, Any]] = []
    top_rows: list[dict[str, Any]] = []
    top1_hits = 0
    recall_at_3_hits = 0
    reciprocal_ranks: list[float] = []
    top2_margins: list[float] = []
    hard_negative_margins: list[float] = []
    domains = sorted({case["domain"] for case in _quality_cases()})
    row_ids = {row["document_id"] for row in rows}

    for case in _quality_cases():
        if case["expected_document_id"] not in row_ids:
            failures.append(f"{case['case_id']}: expected document missing from corpus")
            continue
        repeated_orders: list[list[str]] = []
        repeated_scores: list[list[tuple[str, float]]] = []
        for _ in range(REPEAT_COUNT):
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
        hard_negative_margin = round(expected_row["score"] - max(hard_negative_scores), 6)
        passed = (
            expected_rank == 1
            and top2_margin >= MIN_TOP2_MARGIN
            and hard_negative_margin >= MIN_HARD_NEGATIVE_MARGIN
            and stable_order
        )
        if expected_rank == 1:
            top1_hits += 1
        if 1 <= expected_rank <= 3:
            recall_at_3_hits += 1
        reciprocal_ranks.append(1.0 / expected_rank if expected_rank else 0.0)
        top2_margins.append(top2_margin)
        hard_negative_margins.append(hard_negative_margin)
        top_rows.append(ranked[0])
        if expected_rank != 1:
            failures.append(f"{case['case_id']}: expected rank 1, got rank {expected_rank}")
        if top2_margin < MIN_TOP2_MARGIN:
            failures.append(f"{case['case_id']}: top2 margin below threshold: {top2_margin}")
        if hard_negative_margin < MIN_HARD_NEGATIVE_MARGIN:
            failures.append(f"{case['case_id']}: hard-negative margin below threshold: {hard_negative_margin}")
        if not stable_order:
            failures.append(f"{case['case_id']}: ranking order was not stable across repeats")
        case_rows.append(
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
                "repeat_count": REPEAT_COUNT,
                "top3_document_ids": order[:3],
                "repeat_score_samples": repeated_scores,
                "passed": passed,
            }
        )

    case_count = len(case_rows)
    top1_accuracy = round(top1_hits / case_count, 6) if case_count else 0.0
    recall_at_3 = round(recall_at_3_hits / case_count, 6) if case_count else 0.0
    mrr = round(sum(reciprocal_ranks) / case_count, 6) if case_count else 0.0
    if len(rows) < MIN_PUBLIC_SOURCES:
        failures.append(f"public source count below threshold: {len(rows)}")
    if case_count < MIN_CASES:
        failures.append(f"case count below threshold: {case_count}")
    if top1_accuracy < MIN_TOP1_ACCURACY:
        failures.append(f"top1_accuracy below threshold: {top1_accuracy}")
    if recall_at_3 < MIN_RECALL_AT_3:
        failures.append(f"recall_at_3 below threshold: {recall_at_3}")
    if mrr < MIN_MRR:
        failures.append(f"mrr below threshold: {mrr}")

    return (
        {
            "status": "passed" if not failures else "failed",
            "domain_count": len(domains),
            "domains": domains,
            "public_source_count": len(rows),
            "case_count": case_count,
            "top1_accuracy": top1_accuracy,
            "recall_at_3": recall_at_3,
            "mrr": mrr,
            "min_top2_margin": min(top2_margins) if top2_margins else 0.0,
            "min_hard_negative_margin": min(hard_negative_margins) if hard_negative_margins else 0.0,
            "thresholds": {
                "min_public_sources": MIN_PUBLIC_SOURCES,
                "min_cases": MIN_CASES,
                "repeat_count": REPEAT_COUNT,
                "min_top1_accuracy": MIN_TOP1_ACCURACY,
                "min_recall_at_3": MIN_RECALL_AT_3,
                "min_mrr": MIN_MRR,
                "min_top2_margin": MIN_TOP2_MARGIN,
                "min_hard_negative_margin": MIN_HARD_NEGATIVE_MARGIN,
                "required_retrieval_mode": "vector",
            },
            "cases": case_rows,
        },
        failures,
        top_rows,
    )


def _input_readback() -> tuple[dict[str, Any], list[str]]:
    wave55, wave55_row = _load_json(WAVE55_SEARCH_QUALITY_ARTIFACT)
    failures: list[str] = []
    failures.extend(wave55_row.get("failures") or [])

    index_exists = PUBLIC_CORPUS_INDEX.exists()
    if not index_exists:
        failures.append(f"missing public corpus index: {display_path(PUBLIC_CORPUS_INDEX)}")
    index_text = PUBLIC_CORPUS_INDEX.read_text(encoding="utf-8", errors="replace") if index_exists else ""
    indexed_repos = sorted(
        spec["repo"] for spec in _corpus_specs() if f"| {spec['repo']} |" in index_text or f"/{spec['repo']}`" in index_text
    )
    if len(set(indexed_repos)) < MIN_PUBLIC_SOURCES:
        failures.append("public corpus index does not list enough evaluated repos")

    if wave55:
        if wave55.get("contract_version") != "wave55-oss-node-search-quality-gate.v1":
            failures.append("Wave55 search-quality contract_version mismatch")
        if wave55.get("status") != "passed":
            failures.append("Wave55 search-quality gate did not pass")
        if wave55.get("local_open_search_quality_claim_allowed") is not True:
            failures.append("Wave55 local open-search quality claim is not allowed")
        if wave55.get("repo_local_semantic_quality_claim_allowed") is not True:
            failures.append("Wave55 repo-local semantic quality claim is not allowed")

    return (
        {
            "status": "passed" if not failures else "failed",
            "public_corpus_index": {
                "path": display_path(PUBLIC_CORPUS_INDEX),
                "exists": index_exists,
                "indexed_repos": indexed_repos,
                "evaluated_repo_count": len(set(indexed_repos)),
            },
            "wave55_search_quality_gate": {
                **wave55_row,
                "contract_version": wave55.get("contract_version"),
                "gate_status": wave55.get("status"),
                "local_open_search_quality_claim_allowed": wave55.get("local_open_search_quality_claim_allowed"),
                "repo_local_semantic_quality_claim_allowed": wave55.get("repo_local_semantic_quality_claim_allowed"),
            },
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

    input_readback, input_failures = _input_readback()
    rows, corpus_failures = _build_public_corpus_rows()
    provider = RepoLocalHashingEmbeddingProvider()
    provider_readback = provider.readback(
        [f"{row['title']}\n{row['text']}" for row in rows] + [case["query"] for case in _quality_cases()]
    )
    quality, quality_failures, top_rows = _evaluate_quality(rows, provider)

    failures: list[str] = [*input_failures, *corpus_failures, *quality_failures]
    if provider_readback.get("status") != "passed":
        failures.append("repo-local embedding provider readback failed")

    query_group_id, evidence_hits = build_search_evidence_hits(
        top_rows,
        query="wave57 oss-node public OSS corpus semantic relevance",
        project_key="oss_node_public_corpus",
        rank_mode="vector",
        top_k=len(top_rows),
    )
    for hit in evidence_hits:
        try:
            validate_search_evidence_hit(hit)
        except ValueError as exc:
            failures.append(str(exc))
    retrieval_run = build_retrieval_run_record(
        query="wave57 oss-node public OSS corpus semantic relevance",
        query_group_id=query_group_id,
        evidence_hits=evidence_hits,
        project_key="oss_node_public_corpus",
        rank_mode="vector",
        top_k=len(top_rows),
    )
    readback = load_retrieval_run_record(serialize_retrieval_run_record(retrieval_run))
    try:
        validate_retrieval_run_record(readback)
    except ValueError as exc:
        failures.append(str(exc))

    target_topic = REPO_ROOT / TARGET_TOPIC
    if not target_topic.exists():
        failures.append(f"target topic missing: {TARGET_TOPIC}")

    status = "passed" if not failures else "failed"
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_by": "ops/search-lab/scripts/wave57_oss_node_public_corpus_semantic_relevance_gate.py",
        "status": status,
        "scope": "target_local_public_oss_corpus_semantic_relevance_no_network_no_live_container",
        "target_topic": {"path": TARGET_TOPIC, "exists": target_topic.exists()},
        "input_artifact_readback": input_readback,
        "public_corpus_readback": {
            "status": "passed" if not corpus_failures else "failed",
            "source_index": display_path(PUBLIC_CORPUS_INDEX),
            "source_count": len(rows),
            "sources": [
                {
                    "document_id": row["document_id"],
                    "repo": row["source_repo"],
                    "path": row["source_path"],
                    "line_start": row["source_line_start"],
                    "line_end": row["source_line_end"],
                    "domain": row["domain"],
                    "source_uri": row["source_uri"],
                }
                for row in rows
            ],
            "failures": corpus_failures,
        },
        "provider_readback": provider_readback,
        "quality_evaluation": quality,
        "retrieval_contracts": {
            "status": "passed" if not failures else "failed",
            "evidence_hit": SEARCH_EVIDENCE_HIT_CONTRACT_VERSION,
            "retrieval_run": SEARCH_RETRIEVAL_RUN_CONTRACT_VERSION,
            "query_group_id": query_group_id,
            "retrieval_run_id": retrieval_run["run_id"],
            "readback_status": "passed",
            "evidence_hit_count": len(evidence_hits),
        },
        "closed_conditions": [
            "oss_node_provider_quality",
            "public_corpus_semantic_relevance_not_attached",
            "production_semantic_embedding_quality_not_proven",
        ]
        if status == "passed"
        else [],
        "closed_condition_scope": {
            "oss_node_provider_quality": (
                "closed through the target-local public-corpus semantic relevance route; live container quality is not claimed"
            ),
            "public_corpus_semantic_relevance_not_attached": (
                "closed by deterministic readback over checked-in public OSS corpus excerpts"
            ),
            "production_semantic_embedding_quality_not_proven": (
                "closed only for this OSS-node target's public-corpus route, not for generic live production traffic"
            ),
        },
        "remaining_conditions": [] if status == "passed" else ["public_corpus_semantic_relevance_not_attached"],
        "non_claimed_scope": [
            "local_open_search_live_container_quality_not_replayed",
            "generic_production_live_traffic_vector_quality",
        ],
        "public_corpus_semantic_relevance_claim_allowed": status == "passed",
        "live_container_quality_claim_allowed": False,
        "production_traffic_quality_claim_allowed": False,
        "target_archive_closed_candidate": status == "passed",
        "global_manifest_sync_performed": False,
        "archive_closed_recommendation": (
            "target-local blocker is closed by public-corpus evidence; directory move/global manifest sync remains out of scope"
            if status == "passed"
            else "do_not_mark_archive_closed_until_public_corpus_semantic_relevance_passes"
        ),
        "sample_retrieval_run": retrieval_run,
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "oss_node_public_corpus_semantic_relevance_gate.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    quality = contract["quality_evaluation"]
    readme = [
        "# Wave57 OSS Node Public-Corpus Semantic Relevance Gate",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        "- public_corpus_semantic_relevance_claim_allowed: "
        f"`{str(bool(contract['public_corpus_semantic_relevance_claim_allowed'])).lower()}`",
        f"- live_container_quality_claim_allowed: `{str(bool(contract['live_container_quality_claim_allowed'])).lower()}`",
        f"- target_archive_closed_candidate: `{str(bool(contract['target_archive_closed_candidate'])).lower()}`",
        "",
        "## Public Corpus",
        "",
        f"- source_index: `{contract['public_corpus_readback']['source_index']}`",
        f"- source_count: `{contract['public_corpus_readback']['source_count']}`",
        "- evaluated repos: "
        + ", ".join(f"`{row['repo']}`" for row in contract["public_corpus_readback"]["sources"]),
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
        "- closed conditions: " + ", ".join(f"`{item}`" for item in contract["closed_conditions"]),
        "- remaining conditions: "
        + (", ".join(f"`{item}`" for item in contract["remaining_conditions"]) or "`none`"),
        "- non-claimed scope: " + ", ".join(f"`{item}`" for item in contract["non_claimed_scope"]),
        "",
        "## Rerun",
        "",
        "```bash",
        "PYTHONPATH=main/backend python3 "
        "ops/search-lab/scripts/wave57_oss_node_public_corpus_semantic_relevance_gate.py "
        f"--out-dir {display_path(out_dir)}",
        "PYTHONPATH=main/backend python3 -m pytest -q "
        "main/backend/tests/unit/test_wave57_oss_node_public_corpus_semantic_relevance_gate_unittest.py",
        "```",
        "",
        "Full deterministic output is in `oss_node_public_corpus_semantic_relevance_gate.json`.",
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
                "target_archive_closed_candidate": contract["target_archive_closed_candidate"],
                "out_dir": display_path(out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
