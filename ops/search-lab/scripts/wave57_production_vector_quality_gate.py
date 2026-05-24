#!/usr/bin/env python3
"""Wave57 production-like vector quality gate for global vectorization.

This gate replays the repo-local live embedding provider through the optional
LanceDB vector-store adapter against a production-like MRW devdocs corpus. The
corpus is built from the target blocker docs plus existing local-index/LanceDB
and vectorization automation artifacts, so the evidence is portable with the
target topic without updating global indexes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave57-production-vector-quality-gate/2026-05-23"
TARGET_TOPIC = (
    "docs/development/development-plans/ARCHIVE_CLOSED/"
    "2026-05-14-global-vectorization-general-foundation"
)
PROJECT_ID = "global-vectorization-production-quality"

WAVE56_SEMANTIC_GATE = (
    "development/latest-dev-docs/automation-runs/wave56-semantic-vector-quality-gate/"
    "2026-05-23/semantic_vector_quality_gate.json"
)
EXISTING_LANCEDB_JSONL_ARTIFACTS = (
    "development/latest-dev-docs/automation-runs/deisolation-project-coherence/"
    "2026-05-14/local_index_lancedb_project_prototype.jsonl",
    "development/latest-dev-docs/automation-runs/frontend-coherence-and-searxng-gate/"
    "2026-05-14/local_index_lancedb_project_prototype.jsonl",
)
AUTOMATION_ARTIFACT_READMES = (
    "development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22/README.md",
    "development/latest-dev-docs/automation-runs/wave55-live-embedding-provider/2026-05-23/README.md",
    "development/latest-dev-docs/automation-runs/wave56-semantic-vector-quality-gate/2026-05-23/README.md",
    "development/latest-dev-docs/automation-runs/wave30-vector-closure-gate/2026-05-23/README.md",
)

PRODUCTION_VECTOR_CLOSED_CONDITION = "production_vector_quality_not_proven"
QUALITY_THRESHOLDS = {
    "min_corpus_rows": 20,
    "min_distinct_documents": 20,
    "min_source_groups": 3,
    "min_cases": 6,
    "repeat_count": 3,
    "min_top1_accuracy": 1.0,
    "min_recall_at_3": 1.0,
    "min_mrr": 1.0,
    "min_lancedb_top2_margin": 0.02,
    "min_lancedb_hard_negative_margin": 0.02,
    "min_direct_top2_margin": 0.01,
    "min_direct_hard_negative_margin": 0.01,
    "required_retrieval_mode": "vector",
}

QUALITY_CASES = (
    {
        "case_id": "live-provider-artifact-readback",
        "query": "live embedding provider readback repo local vector retrieval wiring",
        "expected_chunk_id": "artifact-wave55-live-embedding-provider-2026-05-23",
        "hard_negative_chunk_ids": [
            "12_wave55-live-embedding-provider-closure-2026-05-23",
            "08_wave22-vectorization-provider-external-blocked-decision-2026-05-22",
        ],
    },
    {
        "case_id": "semantic-quality-target-doc",
        "query": "semantic vector quality hard negative margin repeat stability",
        "expected_chunk_id": "13_wave56-semantic-vector-quality-gate-2026-05-23",
        "hard_negative_chunk_ids": [
            "artifact-wave56-semantic-vector-quality-gate-2026-05-23",
            "03_wave10-vectorization-quality-gate-2026-05-22",
        ],
    },
    {
        "case_id": "schema-provenance-target-doc",
        "query": "qdrant pgvector payload provenance global vector object schema alignment",
        "expected_chunk_id": "10_wave29-vector-schema-alignment-2026-05-23",
        "hard_negative_chunk_ids": [
            "11_wave30-vector-closure-external-blocked-decision-2026-05-23",
            "09_wave27-vectorization-closure-decision-2026-05-23",
        ],
    },
    {
        "case_id": "wave30-persistence-target-doc",
        "query": "Wave30 external blocked decision retrieval runs branches hits persistence closed",
        "expected_chunk_id": "11_wave30-vector-closure-external-blocked-decision-2026-05-23",
        "hard_negative_chunk_ids": [
            "10_wave29-vector-schema-alignment-2026-05-23",
            "09_wave27-vectorization-closure-decision-2026-05-23",
        ],
    },
    {
        "case_id": "provider-manifest-target-doc",
        "query": "provider manifest openai azure embedding branches env readiness",
        "expected_chunk_id": "07_wave19-vectorization-provider-manifest-2026-05-22",
        "hard_negative_chunk_ids": [
            "05_wave14-vectorization-provider-capability-2026-05-22",
            "08_wave22-vectorization-provider-external-blocked-decision-2026-05-22",
        ],
    },
    {
        "case_id": "lancedb-benchmark-artifact",
        "query": "LanceDB Local Index Benchmark Quality optional environment ranking stability filter guards",
        "expected_chunk_id": "artifact-local-index-lancedb-benchmark-2026-05-22",
        "hard_negative_chunk_ids": [
            "02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14",
            "03_wave10-vectorization-quality-gate-2026-05-22",
        ],
    },
)


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _sha16(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace"), usedforsecurity=False).hexdigest()[:16]


def _read_text(path: Path, *, limit: int = 6000) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit]


def _json_load(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
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
        row["failures"].append(f"invalid JSON artifact: {display_path(path)}: {exc}")
        return {}, row
    row["status"] = "loaded"
    return data, row


def _target_topic_rows() -> tuple[list[dict[str, Any]], list[str]]:
    topic_dir = REPO_ROOT / TARGET_TOPIC
    failures: list[str] = []
    if not topic_dir.exists():
        return [], [f"target topic missing: {TARGET_TOPIC}"]

    rows: list[dict[str, Any]] = []
    for path in sorted(topic_dir.glob("*.md")):
        if path.name == "INDEX.md" or path.name.startswith("14_") or "wave57" in path.name:
            continue
        rows.append(
            {
                "chunk_id": path.stem,
                "document_id": path.stem,
                "project_id": PROJECT_ID,
                "source_id": "global-vectorization-target-docs",
                "source_group": "target_blocker_docs",
                "source_type": "markdown",
                "title": path.name,
                "content": _read_text(path),
                "url": display_path(path),
                "object_type": "devdoc_chunk",
                "object_id": path.stem,
            }
        )
    if not rows:
        failures.append("target topic produced no markdown corpus rows")
    return rows, failures


def _existing_lancedb_jsonl_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    readback: list[dict[str, Any]] = []
    failures: list[str] = []
    seen_digests: set[str] = set()

    for rel_path in EXISTING_LANCEDB_JSONL_ARTIFACTS:
        path = REPO_ROOT / rel_path
        artifact_row: dict[str, Any] = {
            "path": rel_path,
            "exists": path.exists(),
            "status": "missing",
            "row_count": 0,
            "loaded_rows": 0,
            "failures": [],
        }
        if not path.exists():
            artifact_row["failures"].append(f"missing JSONL artifact: {rel_path}")
            failures.extend(artifact_row["failures"])
            readback.append(artifact_row)
            continue

        artifact_row["status"] = "loaded"
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if not line.strip():
                continue
            artifact_row["row_count"] += 1
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                artifact_row["failures"].append(f"line {line_no}: invalid JSON: {exc}")
                continue
            content = str(data.get("content") or "")
            title = str(data.get("title") or data.get("url") or "local-index-jsonl-row")
            digest = _sha16(f"{data.get('url') or ''}\n{title}\n{content}")
            if digest in seen_digests:
                continue
            seen_digests.add(digest)
            chunk_id = f"jsonl-{digest[:12]}"
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": chunk_id,
                    "project_id": PROJECT_ID,
                    "source_id": "existing-lancedb-jsonl-artifact",
                    "source_group": "existing_lancedb_jsonl_artifact",
                    "source_type": str(data.get("source_type") or "artifact_jsonl"),
                    "title": title,
                    "content": content[:6000],
                    "url": str(data.get("url") or rel_path),
                    "object_type": "artifact_chunk",
                    "object_id": chunk_id,
                    "artifact_source_path": rel_path,
                    "artifact_score": data.get("score"),
                    "artifact_metadata": data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
                }
            )
            artifact_row["loaded_rows"] += 1
        if artifact_row["failures"]:
            artifact_row["status"] = "failed"
            failures.extend(str(item) for item in artifact_row["failures"])
        readback.append(artifact_row)
    return rows, readback, failures


def _automation_artifact_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    readback: list[dict[str, Any]] = []
    failures: list[str] = []
    for rel_path in AUTOMATION_ARTIFACT_READMES:
        path = REPO_ROOT / rel_path
        row = {
            "path": rel_path,
            "exists": path.exists(),
            "status": "loaded" if path.exists() else "missing",
            "failures": [],
        }
        if not path.exists():
            row["failures"].append(f"missing automation artifact README: {rel_path}")
            failures.extend(row["failures"])
            readback.append(row)
            continue
        parent = path.parent
        run_name = parent.parent.name
        run_date = parent.name
        chunk_id = f"artifact-{run_name}-{run_date}"
        rows.append(
            {
                "chunk_id": chunk_id,
                "document_id": chunk_id,
                "project_id": PROJECT_ID,
                "source_id": "automation-run-artifacts",
                "source_group": "automation_run_artifact",
                "source_type": "markdown_artifact",
                "title": f"{path.name} {run_name}",
                "content": _read_text(path),
                "url": rel_path,
                "object_type": "artifact_readme",
                "object_id": chunk_id,
            }
        )
        readback.append(row)
    return rows, readback, failures


def build_production_like_corpus() -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []

    target_rows, target_failures = _target_topic_rows()
    jsonl_rows, jsonl_readback, jsonl_failures = _existing_lancedb_jsonl_rows()
    artifact_rows, artifact_readback, artifact_failures = _automation_artifact_rows()
    rows.extend(target_rows)
    rows.extend(jsonl_rows)
    rows.extend(artifact_rows)
    failures.extend(target_failures)
    failures.extend(jsonl_failures)
    failures.extend(artifact_failures)

    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        chunk_id = str(row["chunk_id"])
        if chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        deduped.append(row)

    source_groups = sorted({str(row.get("source_group") or "unknown") for row in deduped})
    corpus_readback = {
        "status": "passed",
        "project_id": PROJECT_ID,
        "row_count": len(deduped),
        "distinct_document_count": len({row["document_id"] for row in deduped}),
        "source_groups": source_groups,
        "source_group_count": len(source_groups),
        "target_topic": TARGET_TOPIC,
        "target_topic_row_count": len(target_rows),
        "existing_lancedb_jsonl_row_count": len(jsonl_rows),
        "automation_artifact_row_count": len(artifact_rows),
        "existing_lancedb_jsonl_artifacts": jsonl_readback,
        "automation_artifacts": artifact_readback,
        "thresholds": {
            "min_corpus_rows": QUALITY_THRESHOLDS["min_corpus_rows"],
            "min_distinct_documents": QUALITY_THRESHOLDS["min_distinct_documents"],
            "min_source_groups": QUALITY_THRESHOLDS["min_source_groups"],
        },
        "failures": [],
    }
    if corpus_readback["row_count"] < QUALITY_THRESHOLDS["min_corpus_rows"]:
        failures.append(f"corpus row count below threshold: {corpus_readback['row_count']}")
    if corpus_readback["distinct_document_count"] < QUALITY_THRESHOLDS["min_distinct_documents"]:
        failures.append(f"distinct document count below threshold: {corpus_readback['distinct_document_count']}")
    if corpus_readback["source_group_count"] < QUALITY_THRESHOLDS["min_source_groups"]:
        failures.append(f"source group count below threshold: {corpus_readback['source_group_count']}")
    corpus_readback["failures"] = failures[:]
    corpus_readback["status"] = "passed" if not failures else "failed"
    return deduped, corpus_readback, failures


class VectorQualityBackend:
    def __init__(
        self,
        *,
        backend: str,
        provider: Any,
        corpus_rows: list[dict[str, Any]],
        service: Any | None = None,
        db_path: str | None = None,
        upsert_status: dict[str, Any] | None = None,
    ) -> None:
        self.backend = backend
        self.provider = provider
        self.corpus_rows = corpus_rows
        self.row_by_chunk_id = {row["chunk_id"]: row for row in corpus_rows}
        self.service = service
        self.db_path = db_path
        self.upsert_status = upsert_status or {}

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        if self.backend == "lancedb":
            return self._search_lancedb(query, top_k)
        return self._search_direct(query, top_k)

    def _search_lancedb(self, query: str, top_k: int) -> list[dict[str, Any]]:
        from app.services.local_index import LocalIndexQuery

        results = self.service.search(  # type: ignore[union-attr]
            LocalIndexQuery(query=query, project_id=PROJECT_ID, mode="vector", top_k=top_k)
        )
        ranked: list[dict[str, Any]] = []
        provider_meta = self.provider.metadata()
        for rank, result in enumerate(results, start=1):
            base = self.row_by_chunk_id.get(result.chunk_id)
            if base is None:
                continue
            raw_score = float(result.score if result.score is not None else 0.0)
            ranked.append(
                _ranked_row(
                    base,
                    provider_meta=provider_meta,
                    backend="lancedb_vector_store",
                    retrieval_mode=result.retrieval_mode,
                    rank=rank,
                    raw_score=raw_score,
                    quality_score=-raw_score,
                    score_semantics="lower_distance_is_better",
                    trace=result.trace,
                )
            )
        return ranked

    def _search_direct(self, query: str, top_k: int) -> list[dict[str, Any]]:
        from app.services.local_index import cosine_similarity

        provider_meta = self.provider.metadata()
        query_vector = self.provider.embed_query(query)
        ranked: list[dict[str, Any]] = []
        for row in self.corpus_rows:
            vector = self.provider.embed_text(f"{row['title']}\n{row['content']}")
            raw_score = round(cosine_similarity(query_vector, vector), 6)
            ranked.append(
                _ranked_row(
                    row,
                    provider_meta=provider_meta,
                    backend="repo_local_direct_vector",
                    retrieval_mode="vector",
                    rank=0,
                    raw_score=raw_score,
                    quality_score=raw_score,
                    score_semantics="higher_cosine_is_better",
                    trace={
                        "adapter": "repo_local_direct_vector",
                        "requested_mode": "vector",
                        "executed_mode": "vector",
                        "provider_live_verified": True,
                    },
                )
            )
        ranked.sort(key=lambda item: (-float(item["quality_score"]), str(item["chunk_id"])))
        for index, row in enumerate(ranked, start=1):
            row["rank"] = index
        return ranked[:top_k]


def _ranked_row(
    row: dict[str, Any],
    *,
    provider_meta: dict[str, Any],
    backend: str,
    retrieval_mode: str,
    rank: int,
    raw_score: float,
    quality_score: float,
    score_semantics: str,
    trace: dict[str, Any],
) -> dict[str, Any]:
    provenance = {
        "provider": provider_meta["provider_id"],
        "backend": backend,
        "retrieval_mode": retrieval_mode,
        "provider_payload_kind": "repo_local_embedding_vector",
        "embedding_model": provider_meta["model"],
        "embedding_model_version": provider_meta["model_version"],
        "embedding_dim": provider_meta["embedding_dim"],
        "vector_version": provider_meta["vector_version"],
        "source": row["source_id"],
        "source_id": row["source_id"],
        "source_reference": row["url"],
        "reference": row["url"],
        "source_uri": row["url"],
        "score": quality_score,
        "fallback_reason": None,
    }
    return {
        **row,
        "rank": rank,
        "summary": row["title"],
        "score": round(float(quality_score), 6),
        "raw_score": round(float(raw_score), 6),
        "quality_score": round(float(quality_score), 6),
        "score_semantics": score_semantics,
        "backend": backend,
        "mode": retrieval_mode,
        "retrieval_mode": retrieval_mode,
        "retrieval_family": "local_index",
        "embedding_provider": provider_meta["provider_id"],
        "embedding_model": provider_meta["model"],
        "embedding_model_version": provider_meta["model_version"],
        "embedding_dim": provider_meta["embedding_dim"],
        "vector_version": provider_meta["vector_version"],
        "provider_payload_kind": "repo_local_embedding_vector",
        "payload_provenance": provenance,
        "provenance": provenance,
        "rank_features": {
            "provider": provider_meta["provider_id"],
            "backend": backend,
            "score_semantics": score_semantics,
            "source_group": row.get("source_group"),
        },
        "trace": dict(trace or {}),
        "tags": ["vector", "production_like_replay", str(row.get("source_group") or "unknown")],
    }


def _build_vector_backend(
    corpus_rows: list[dict[str, Any]],
    provider: Any,
    *,
    require_vector_store: bool,
) -> tuple[VectorQualityBackend, dict[str, Any], list[str]]:
    failures: list[str] = []
    packages = {
        "lancedb": package_version("lancedb"),
        "pyarrow": package_version("pyarrow"),
    }
    readback: dict[str, Any] = {
        "status": "running",
        "backend": None,
        "packages": packages,
        "attempted_lancedb": True,
        "require_vector_store": require_vector_store,
        "failures": [],
    }
    try:
        from app.services.local_index import LocalIndexChunk, LocalIndexService
        from app.services.local_index.adapters import LanceDBLocalIndexAdapter, is_lancedb_available

        if is_lancedb_available() and importlib.util.find_spec("pyarrow") is not None:
            db_path = tempfile.mkdtemp(prefix="mrw-wave57-production-vector-quality-")
            adapter = LanceDBLocalIndexAdapter(db_path=db_path, table_name="chunks", embedding_provider=provider)
            service = LocalIndexService(adapter)
            chunks = [
                LocalIndexChunk(
                    chunk_id=str(row["chunk_id"]),
                    document_id=str(row["document_id"]),
                    project_id=PROJECT_ID,
                    source_id=str(row["source_id"]),
                    title=str(row["title"]),
                    content=str(row["content"]),
                    url=str(row.get("url") or ""),
                    source_type=str(row.get("source_type") or "material"),
                    metadata={
                        "source_group": row.get("source_group"),
                        "object_type": row.get("object_type"),
                        "object_id": row.get("object_id"),
                    },
                )
                for row in corpus_rows
            ]
            upsert_status = service.upsert_chunks(chunks)
            backend = VectorQualityBackend(
                backend="lancedb",
                provider=provider,
                corpus_rows=corpus_rows,
                service=service,
                db_path=db_path,
                upsert_status=dict(upsert_status or {}),
            )
            readback.update(
                {
                    "status": "passed",
                    "backend": "lancedb",
                    "db_path": db_path,
                    "upsert_status": upsert_status,
                    "corpus_row_count": len(corpus_rows),
                    "strict_vector_store_runtime": True,
                }
            )
            return backend, readback, failures
        failures.append("lancedb_or_pyarrow_not_importable")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"lancedb_vector_store_init_failed: {exc.__class__.__name__}: {exc}")

    if require_vector_store:
        readback.update(
            {
                "status": "failed",
                "backend": None,
                "strict_vector_store_runtime": False,
                "failures": failures[:],
            }
        )
        return VectorQualityBackend(backend="direct", provider=provider, corpus_rows=corpus_rows), readback, failures

    readback.update(
        {
            "status": "passed",
            "backend": "repo_local_direct_vector",
            "strict_vector_store_runtime": False,
            "fallback_reason": "; ".join(failures),
            "corpus_row_count": len(corpus_rows),
            "failures": [],
        }
    )
    return VectorQualityBackend(backend="direct", provider=provider, corpus_rows=corpus_rows), readback, []


def _input_artifact_readback() -> tuple[dict[str, Any], list[str]]:
    wave56, wave56_row = _json_load(REPO_ROOT / WAVE56_SEMANTIC_GATE)
    failures: list[str] = []
    failures.extend(str(item) for item in wave56_row.get("failures") or [])
    if wave56:
        if wave56.get("contract_version") != "wave56-semantic-vector-quality-gate.v1":
            failures.append("wave56 semantic gate contract_version mismatch")
        if wave56.get("status") != "passed":
            failures.append("wave56 semantic gate did not pass")
        if wave56.get("semantic_quality_claim_allowed") is not True:
            failures.append("wave56 semantic_quality_claim_allowed must be true")
        if wave56.get("production_quality_claim_allowed") is not False:
            failures.append("wave56 must not already claim production quality")
    return (
        {
            "status": "passed" if not failures else "failed",
            "wave56_semantic_vector_quality_gate": {
                **wave56_row,
                "contract_version": wave56.get("contract_version"),
                "gate_status": wave56.get("status"),
                "semantic_quality_claim_allowed": wave56.get("semantic_quality_claim_allowed"),
                "production_quality_claim_allowed": wave56.get("production_quality_claim_allowed"),
                "closed_conditions": wave56.get("closed_conditions"),
                "reduced_conditions": wave56.get("reduced_conditions"),
            },
        },
        failures,
    )


def _margin_thresholds(backend_name: str) -> tuple[float, float]:
    if backend_name == "lancedb":
        return (
            float(QUALITY_THRESHOLDS["min_lancedb_top2_margin"]),
            float(QUALITY_THRESHOLDS["min_lancedb_hard_negative_margin"]),
        )
    return (
        float(QUALITY_THRESHOLDS["min_direct_top2_margin"]),
        float(QUALITY_THRESHOLDS["min_direct_hard_negative_margin"]),
    )


def _evaluate_quality(backend: VectorQualityBackend) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    case_rows: list[dict[str, Any]] = []
    top_rows: list[dict[str, Any]] = []
    top1_hits = 0
    recall_at_3_hits = 0
    reciprocal_ranks: list[float] = []
    top2_margins: list[float] = []
    hard_negative_margins: list[float] = []
    min_top2_margin_threshold, min_hard_negative_margin_threshold = _margin_thresholds(backend.backend)

    for case in QUALITY_CASES:
        repeated_orders: list[list[str]] = []
        repeated_scores: list[list[tuple[str, float]]] = []
        for _ in range(int(QUALITY_THRESHOLDS["repeat_count"])):
            ranked = backend.search(str(case["query"]), top_k=len(backend.corpus_rows))
            repeated_orders.append([str(row["chunk_id"]) for row in ranked[:10]])
            repeated_scores.append([(str(row["chunk_id"]), float(row["quality_score"])) for row in ranked[:10]])

        ranked = backend.search(str(case["query"]), top_k=len(backend.corpus_rows))
        order = [str(row["chunk_id"]) for row in ranked]
        expected_chunk_id = str(case["expected_chunk_id"])
        expected_rank = order.index(expected_chunk_id) + 1 if expected_chunk_id in order else 0
        expected_row = next((row for row in ranked if row["chunk_id"] == expected_chunk_id), None)
        second_row = ranked[1] if len(ranked) > 1 else ranked[0]
        stable_order = all(order_sample == repeated_orders[0] for order_sample in repeated_orders)
        top2_margin = 0.0
        hard_negative_margin = 0.0
        if expected_row is not None and expected_rank == 1:
            top2_margin = round(float(expected_row["quality_score"]) - float(second_row["quality_score"]), 6)
            hard_negative_scores = [
                float(row["quality_score"])
                for row in ranked
                if row["chunk_id"] in set(case["hard_negative_chunk_ids"])
            ]
            if hard_negative_scores:
                hard_negative_margin = round(float(expected_row["quality_score"]) - max(hard_negative_scores), 6)

        retrieval_mode = str(ranked[0].get("retrieval_mode") or "")
        passed = (
            expected_rank == 1
            and stable_order
            and retrieval_mode == QUALITY_THRESHOLDS["required_retrieval_mode"]
            and top2_margin >= min_top2_margin_threshold
            and hard_negative_margin >= min_hard_negative_margin_threshold
        )
        if expected_rank == 1:
            top1_hits += 1
            top_rows.append(ranked[0])
        if 1 <= expected_rank <= 3:
            recall_at_3_hits += 1
        reciprocal_ranks.append(1.0 / expected_rank if expected_rank else 0.0)
        top2_margins.append(top2_margin)
        hard_negative_margins.append(hard_negative_margin)
        if expected_rank != 1:
            failures.append(f"{case['case_id']}: expected rank 1, got rank {expected_rank}")
        if retrieval_mode != QUALITY_THRESHOLDS["required_retrieval_mode"]:
            failures.append(f"{case['case_id']}: top retrieval_mode mismatch: {retrieval_mode}")
        if top2_margin < min_top2_margin_threshold:
            failures.append(f"{case['case_id']}: top2 margin below threshold: {top2_margin}")
        if hard_negative_margin < min_hard_negative_margin_threshold:
            failures.append(f"{case['case_id']}: hard-negative margin below threshold: {hard_negative_margin}")
        if not stable_order:
            failures.append(f"{case['case_id']}: top-10 ranking order was not stable across repeats")
        case_rows.append(
            {
                "case_id": case["case_id"],
                "query": case["query"],
                "expected_chunk_id": expected_chunk_id,
                "expected_rank": expected_rank,
                "top_chunk_id": ranked[0]["chunk_id"],
                "top_document_id": ranked[0]["document_id"],
                "top_score": ranked[0]["quality_score"],
                "top_raw_score": ranked[0]["raw_score"],
                "second_chunk_id": second_row["chunk_id"],
                "second_score": second_row["quality_score"],
                "second_raw_score": second_row["raw_score"],
                "score_semantics": ranked[0]["score_semantics"],
                "retrieval_mode": retrieval_mode,
                "backend": ranked[0]["backend"],
                "top2_margin": top2_margin,
                "hard_negative_chunk_ids": case["hard_negative_chunk_ids"],
                "hard_negative_margin": hard_negative_margin,
                "stable_order": stable_order,
                "repeat_count": QUALITY_THRESHOLDS["repeat_count"],
                "top5_chunk_ids": order[:5],
                "repeat_score_samples": repeated_scores,
                "passed": passed,
            }
        )

    case_count = len(case_rows)
    top1_accuracy = round(top1_hits / case_count, 6) if case_count else 0.0
    recall_at_3 = round(recall_at_3_hits / case_count, 6) if case_count else 0.0
    mrr = round(sum(reciprocal_ranks) / case_count, 6) if case_count else 0.0
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
            "backend": backend.backend,
            "case_count": case_count,
            "top1_accuracy": top1_accuracy,
            "recall_at_3": recall_at_3,
            "mrr": mrr,
            "min_top2_margin": min(top2_margins) if top2_margins else 0.0,
            "min_hard_negative_margin": min(hard_negative_margins) if hard_negative_margins else 0.0,
            "margin_thresholds": {
                "min_top2_margin": min_top2_margin_threshold,
                "min_hard_negative_margin": min_hard_negative_margin_threshold,
            },
            "thresholds": QUALITY_THRESHOLDS,
            "cases": case_rows,
        },
        failures,
        top_rows,
    )


def _retrieval_contract_readback(top_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
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
        top_rows,
        query="wave57 production-like devdocs vector quality replay",
        project_key=PROJECT_ID,
        rank_mode="vector",
        top_k=len(top_rows),
    )
    for hit in evidence_hits:
        try:
            validate_search_evidence_hit(hit)
        except ValueError as exc:
            failures.append(str(exc))
    retrieval_run = build_retrieval_run_record(
        query="wave57 production-like devdocs vector quality replay",
        query_group_id=query_group_id,
        evidence_hits=evidence_hits,
        project_key=PROJECT_ID,
        rank_mode="vector",
        top_k=len(top_rows),
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


def build_contract(*, require_vector_store: bool = False) -> dict[str, Any]:
    from app.services.local_index import RepoLocalHashingEmbeddingProvider

    started = time.perf_counter()
    generated_at = datetime.now(UTC).isoformat()
    input_readback, input_failures = _input_artifact_readback()
    corpus_rows, corpus_readback, corpus_failures = build_production_like_corpus()
    provider = RepoLocalHashingEmbeddingProvider()
    provider_texts = [f"{row['title']}\n{row['content']}" for row in corpus_rows] + [
        str(case["query"]) for case in QUALITY_CASES
    ]
    provider_readback = provider.readback(provider_texts)
    backend, vector_store_readback, backend_failures = _build_vector_backend(
        corpus_rows,
        provider,
        require_vector_store=require_vector_store,
    )
    quality, quality_failures, top_rows = _evaluate_quality(backend)
    retrieval_contracts, retrieval_failures = _retrieval_contract_readback(top_rows)

    failures = [
        *input_failures,
        *corpus_failures,
        *backend_failures,
        *quality_failures,
        *retrieval_failures,
    ]
    if provider_readback.get("status") != "passed":
        failures.append("provider readback failed")
    if require_vector_store and vector_store_readback.get("backend") != "lancedb":
        failures.append("required LanceDB vector-store runtime was not available")

    production_claim_allowed = not failures and vector_store_readback.get("backend") == "lancedb"
    return {
        "contract_version": "wave57-production-vector-quality-gate.v1",
        "generated_at": generated_at,
        "generated_by": "ops/search-lab/scripts/wave57_production_vector_quality_gate.py",
        "status": "passed" if not failures else "failed",
        "scope": "production_like_devdocs_corpus_lancedb_vector_store_replay",
        "target_topic": {"path": TARGET_TOPIC, "exists": (REPO_ROOT / TARGET_TOPIC).exists()},
        "input_artifact_readback": input_readback,
        "corpus_readback": corpus_readback,
        "provider_readback": provider_readback,
        "vector_store_readback": vector_store_readback,
        "quality_evaluation": quality,
        "retrieval_contracts": retrieval_contracts,
        "closed_conditions": [PRODUCTION_VECTOR_CLOSED_CONDITION] if production_claim_allowed else [],
        "closed_condition_scope": {
            PRODUCTION_VECTOR_CLOSED_CONDITION: (
                "closed for target-topic migration scope by replaying a production-like MRW devdocs corpus "
                "through the repo-local live embedding provider and LanceDB vector-store adapter"
            )
        }
        if production_claim_allowed
        else {},
        "remaining_conditions": []
        if production_claim_allowed
        else [
            {
                "code": PRODUCTION_VECTOR_CLOSED_CONDITION,
                "remaining_scope": "strict LanceDB vector-store replay is required before claiming target-topic closure",
            }
        ],
        "production_like_vector_quality_claim_allowed": production_claim_allowed,
        "production_traffic_claim_allowed": False,
        "global_manifest_update_performed": False,
        "target_topic_migration_ready": production_claim_allowed,
        "archive_closed_recommendation": (
            "target_topic_evidence_ready_for_archive_closed_migration_without_global_index_update"
            if production_claim_allowed
            else "do_not_mark_archive_closed_until_strict_vector_store_replay_passes"
        ),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "production_vector_quality_gate.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    quality = contract["quality_evaluation"]
    corpus = contract["corpus_readback"]
    vector_store = contract["vector_store_readback"]
    readme = [
        "# Wave57 Production Vector Quality Gate",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        f"- vector_store_backend: `{vector_store.get('backend')}`",
        f"- production_like_vector_quality_claim_allowed: `{str(bool(contract['production_like_vector_quality_claim_allowed'])).lower()}`",
        f"- production_traffic_claim_allowed: `{str(bool(contract['production_traffic_claim_allowed'])).lower()}`",
        f"- target_topic_migration_ready: `{str(bool(contract['target_topic_migration_ready'])).lower()}`",
        f"- global_manifest_update_performed: `{str(bool(contract['global_manifest_update_performed'])).lower()}`",
        "",
        "## Corpus",
        "",
        f"- rows: `{corpus['row_count']}`",
        f"- distinct_documents: `{corpus['distinct_document_count']}`",
        f"- source_groups: `{', '.join(corpus['source_groups'])}`",
        f"- target_topic_rows: `{corpus['target_topic_row_count']}`",
        f"- existing_lancedb_jsonl_rows: `{corpus['existing_lancedb_jsonl_row_count']}`",
        f"- automation_artifact_rows: `{corpus['automation_artifact_row_count']}`",
        "",
        "## Provider And Vector Store",
        "",
        f"- provider_id: `{contract['provider_readback']['provider_id']}`",
        f"- model: `{contract['provider_readback']['model']}`",
        f"- model_version: `{contract['provider_readback']['model_version']}`",
        f"- embedding_dim: `{contract['provider_readback']['embedding_dim']}`",
        f"- vector_version: `{contract['provider_readback']['vector_version']}`",
        f"- lancedb: `{vector_store.get('packages', {}).get('lancedb')}`",
        f"- pyarrow: `{vector_store.get('packages', {}).get('pyarrow')}`",
        "",
        "## Quality Metrics",
        "",
        f"- cases: `{quality['case_count']}`",
        f"- top1_accuracy: `{quality['top1_accuracy']}`",
        f"- recall_at_3: `{quality['recall_at_3']}`",
        f"- mrr: `{quality['mrr']}`",
        f"- min_top2_margin: `{quality['min_top2_margin']}`",
        f"- min_hard_negative_margin: `{quality['min_hard_negative_margin']}`",
        "",
        "## Decision",
        "",
        "- closed condition: " + (", ".join(f"`{item}`" for item in contract["closed_conditions"]) or "`none`"),
        "- remaining condition: "
        + (
            ", ".join(f"`{item['code']}`" for item in contract["remaining_conditions"])
            if contract["remaining_conditions"]
            else "`none`"
        ),
        "- global manifest/index update: `not performed`",
        "",
        "## Rerun",
        "",
        "```bash",
        "PYTHONPATH=main/backend main/backend/.venv311/bin/python "
        f"ops/search-lab/scripts/wave57_production_vector_quality_gate.py --require-vector-store --out-dir {display_path(out_dir)}",
        "PYTHONPATH=main/backend main/backend/.venv311/bin/python -m pytest -q "
        "main/backend/tests/unit/test_wave57_production_vector_quality_gate_unittest.py",
        "```",
        "",
        "Full deterministic output is in `production_vector_quality_gate.json`.",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--require-vector-store", action="store_true")
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    contract = build_contract(require_vector_store=bool(args.require_vector_store))
    write_outputs(out_dir, contract)
    print(
        json.dumps(
            {
                "status": contract["status"],
                "contract_version": contract["contract_version"],
                "closed_conditions": contract["closed_conditions"],
                "remaining_conditions": [item["code"] for item in contract["remaining_conditions"]],
                "target_topic_migration_ready": contract["target_topic_migration_ready"],
                "vector_store_backend": contract["vector_store_readback"].get("backend"),
                "out_dir": display_path(out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
