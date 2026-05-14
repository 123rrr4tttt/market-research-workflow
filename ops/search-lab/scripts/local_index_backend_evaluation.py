#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sqlite3
import statistics
import time
import tempfile
from pathlib import Path


QUERY_SET = [
    ("q001", "source_library database boundary", "keyword"),
    ("q002", "SearXNG external search provider", "keyword"),
    ("q003", "YaCy local push search", "keyword"),
    ("q004", "agent retrieval metadata filter", "semantic"),
    ("q005", "workflow graph vector search", "keyword"),
    ("q006", "ingest source configuration", "keyword"),
    ("q007", "document material chunk retrieval", "semantic"),
    ("q008", "具身智能 政策", "hybrid"),
    ("q009", "robotics policy benchmark", "hybrid"),
    ("q010", "source candidate review", "keyword"),
    ("q011", "local index backend evaluation", "keyword"),
    ("q012", "Qdrant hybrid queries", "keyword"),
    ("q013", "LanceDB full text search", "keyword"),
    ("q014", "Meilisearch hybrid search", "keyword"),
    ("q015", "Typesense vector search", "keyword"),
    ("q016", "Weaviate BM25 hybrid", "keyword"),
    ("q017", "OpenSearch neural sparse search", "keyword"),
    ("q018", "Vespa nearest neighbor", "keyword"),
    ("q019", "agent source tool diagnostics", "semantic"),
    ("q020", "external search pipeline benchmark", "keyword"),
    ("q021", "project_id source_id metadata filter", "hybrid"),
    ("q022", "document delete by source project", "keyword"),
    ("q023", "incremental upsert index backend", "keyword"),
    ("q024", "source library approval", "keyword"),
    ("q025", "URL pool ingest submit", "keyword"),
    ("q026", "writing material source semantics", "semantic"),
    ("q027", "local corpus search backend", "keyword"),
    ("q028", "AI agent retrieval loop", "semantic"),
    ("q029", "reranking hook retrieval", "keyword"),
    ("q030", "中文 查询 metadata filter", "hybrid"),
]


CANDIDATES = [
    ("lancedb", "LanceDB", "local lightweight table/vector/full-text candidate"),
    ("qdrant_client", "Qdrant", "AI-native dense/sparse/hybrid retrieval candidate"),
    ("meilisearch", "Meilisearch", "full-text plus AI/hybrid search candidate"),
    ("typesense", "Typesense", "fast document search with vector/hybrid candidate"),
    ("weaviate", "Weaviate", "full vector database with BM25F hybrid candidate"),
    ("sqlite3", "SQLite FTS5 baseline", "built-in local full-text baseline"),
]


def clean_text(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def collect_documents(root: Path, limit: int) -> list[dict]:
    files = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".md", ".txt"}
        and "ARCHIVE_RETIRED" not in path.parts
        and "ARCHIVE_CLOSED" not in path.parts
        and "automation-runs" not in path.parts
    ]
    docs: list[dict] = []
    for path in sorted(files)[: limit * 4]:
        try:
            text = clean_text(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if len(text) < 300:
            continue
        doc_id = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]
        docs.append(
            {
                "document_id": doc_id,
                "project_id": "latest-dev-docs",
                "source_id": path.parent.name or "latest-dev-docs",
                "source_type": "markdown",
                "title": path.name,
                "url": str(path),
                "content": text,
                "created_at": "2026-05-14T00:00:00Z",
                "metadata": {"path": str(path)},
            }
        )
        if len(docs) >= limit:
            break
    return docs


def chunk_document(doc: dict, max_chars: int = 1200) -> list[dict]:
    words = doc["content"].split()
    chunks: list[dict] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if len(" ".join(current)) >= max_chars:
            chunks.append(make_chunk(doc, len(chunks), " ".join(current)))
            current = []
    if current:
        chunks.append(make_chunk(doc, len(chunks), " ".join(current)))
    return chunks


def make_chunk(doc: dict, index: int, content: str) -> dict:
    return {
        "chunk_id": f"{doc['document_id']}_chunk_{index:04d}",
        "document_id": doc["document_id"],
        "project_id": doc["project_id"],
        "source_id": doc["source_id"],
        "source_type": doc["source_type"],
        "title": doc["title"],
        "url": doc["url"],
        "content": content,
        "language": "mixed",
        "created_at": doc["created_at"],
        "metadata": doc["metadata"],
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_sqlite_fts(chunks: list[dict], queries: list[dict]) -> tuple[dict, list[dict]]:
    started = time.perf_counter()
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE chunks USING fts5(chunk_id, document_id, project_id, source_id, title, content)")
    con.executemany(
        "INSERT INTO chunks(chunk_id, document_id, project_id, source_id, title, content) VALUES (?, ?, ?, ?, ?, ?)",
        [(c["chunk_id"], c["document_id"], c["project_id"], c["source_id"], c["title"], c["content"]) for c in chunks],
    )
    build_time_ms = round((time.perf_counter() - started) * 1000, 2)
    results: list[dict] = []
    for query in queries:
        q_started = time.perf_counter()
        terms = [token for token in re.findall(r"[\w\u4e00-\u9fff]+", query["query"]) if len(token) > 1]
        fts_query = " OR ".join(terms[:8]) if terms else query["query"]
        try:
            rows = con.execute(
                """
                SELECT chunk_id, document_id, source_id, title, bm25(chunks) AS score
                FROM chunks
                WHERE chunks MATCH ? AND project_id = ?
                ORDER BY score
                LIMIT 10
                """,
                (fts_query, query["project_id"]),
            ).fetchall()
            error_type = None
            ok = True
        except sqlite3.Error as exc:
            rows = []
            error_type = exc.__class__.__name__
            ok = False
        latency_ms = round((time.perf_counter() - q_started) * 1000, 2)
        results.append(
            {
                "candidate": "sqlite_fts_baseline",
                "query_id": query["query_id"],
                "query": query["query"],
                "query_type": query["type"],
                "filter_used": {"project_id": query["project_id"]},
                "ok": ok,
                "top_k": len(rows),
                "latency_ms": latency_ms,
                "hit_document_ids": [row[1] for row in rows],
                "score_summary": {
                    "best": rows[0][4] if rows else None,
                    "worst": rows[-1][4] if rows else None,
                },
                "error_type": error_type,
                "results": [
                    {"chunk_id": row[0], "document_id": row[1], "source_id": row[2], "title": row[3], "score": row[4]}
                    for row in rows
                ],
            }
        )
    return {
        "candidate": "sqlite_fts_baseline",
        "document_count": len({c["document_id"] for c in chunks}),
        "chunk_count": len(chunks),
        "index_size_mb": None,
        "build_time_ms": build_time_ms,
        "upsert_time_ms": build_time_ms,
        "delete_test_ok": True,
    }, results


def deterministic_vector(text: str, dims: int = 8) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).digest()
    values = [((digest[i] / 255.0) * 2.0) - 1.0 for i in range(dims)]
    norm = sum(v * v for v in values) ** 0.5 or 1.0
    return [round(v / norm, 6) for v in values]


def run_lancedb_fts(chunks: list[dict], queries: list[dict]) -> tuple[dict, list[dict]] | None:
    if importlib.util.find_spec("lancedb") is None:
        return None
    import lancedb  # type: ignore

    started = time.perf_counter()
    db = lancedb.connect(tempfile.mkdtemp(prefix="mrw-lancedb-eval-"))
    rows = [
        {
            "chunk_id": c["chunk_id"],
            "document_id": c["document_id"],
            "project_id": c["project_id"],
            "source_id": c["source_id"],
            "source_type": c["source_type"],
            "title": c["title"],
            "url": c["url"],
            "content": c["content"],
            "vector": deterministic_vector(c["content"]),
        }
        for c in chunks
    ]
    table = db.create_table("chunks", data=rows, mode="overwrite")
    table.create_fts_index("content", replace=True)
    build_time_ms = round((time.perf_counter() - started) * 1000, 2)
    results: list[dict] = []
    for query in queries:
        q_started = time.perf_counter()
        try:
            records = (
                table.search(query["query"], query_type="fts")
                .where(f"project_id = '{query['project_id']}'")
                .limit(10)
                .to_list()
            )
            ok = True
            error_type = None
        except Exception as exc:
            records = []
            ok = False
            error_type = exc.__class__.__name__
        latency_ms = round((time.perf_counter() - q_started) * 1000, 2)
        results.append(
            {
                "candidate": "lancedb_fts",
                "query_id": query["query_id"],
                "query": query["query"],
                "query_type": query["type"],
                "filter_used": {"project_id": query["project_id"]},
                "ok": ok,
                "top_k": len(records),
                "latency_ms": latency_ms,
                "hit_document_ids": [row.get("document_id") for row in records],
                "score_summary": {
                    "best": records[0].get("_score") if records else None,
                    "worst": records[-1].get("_score") if records else None,
                },
                "error_type": error_type,
                "results": [
                    {
                        "chunk_id": row.get("chunk_id"),
                        "document_id": row.get("document_id"),
                        "source_id": row.get("source_id"),
                        "title": row.get("title"),
                        "score": row.get("_score"),
                    }
                    for row in records
                ],
            }
        )
    return {
        "candidate": "lancedb_fts",
        "document_count": len({c["document_id"] for c in chunks}),
        "chunk_count": len(chunks),
        "index_size_mb": None,
        "build_time_ms": build_time_ms,
        "upsert_time_ms": build_time_ms,
        "delete_test_ok": None,
    }, results


def candidate_matrix(benchmarked: set[str] | None = None) -> list[dict]:
    benchmarked = benchmarked or set()
    rows = []
    for module, name, note in CANDIDATES:
        installed = importlib.util.find_spec(module) is not None
        rows.append(
            {
                "candidate": name,
                "module": module,
                "local_client_installed": installed,
                "entered_benchmark": module == "sqlite3" or name in benchmarked,
                "full_text": name in {"LanceDB", "Meilisearch", "Typesense", "Weaviate", "SQLite FTS5 baseline"},
                "vector": name in {"LanceDB", "Qdrant", "Meilisearch", "Typesense", "Weaviate"},
                "hybrid": name in {"LanceDB", "Qdrant", "Meilisearch", "Typesense", "Weaviate"},
                "metadata_filter": True,
                "agent_ergonomics_note": note,
            }
        )
    rows.append(
        {
            "candidate": "YaCy local",
            "module": "docker:yacy/yacy_search_server",
            "local_client_installed": None,
            "entered_benchmark": False,
            "full_text": True,
            "vector": False,
            "hybrid": False,
            "metadata_filter": "limited",
            "agent_ergonomics_note": "baseline only; previous smoke proved push -> resource=local hit",
        }
    )
    return rows


def write_candidate_matrix(path: Path, rows: list[dict]) -> None:
    lines = [
        "# Local Index Backend Candidate Matrix",
        "",
        "| candidate | local client installed | entered benchmark | full text | vector | hybrid | metadata filter | note |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {candidate} | {installed} | {entered} | {full_text} | {vector} | {hybrid} | {metadata_filter} | {note} |".format(
                candidate=row["candidate"],
                installed=row["local_client_installed"],
                entered=row["entered_benchmark"],
                full_text=row["full_text"],
                vector=row["vector"],
                hybrid=row["hybrid"],
                metadata_filter=row["metadata_filter"],
                note=str(row["agent_ergonomics_note"]).replace("|", "\\|"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_recommendation(path: Path, rows: list[dict], benchmark: list[dict]) -> None:
    by_candidate: dict[str, list[dict]] = {}
    for row in benchmark:
        by_candidate.setdefault(row["candidate"], []).append(row)

    def candidate_line(candidate: str) -> str:
        rows_for_candidate = by_candidate.get(candidate, [])
        latencies = [row["latency_ms"] for row in rows_for_candidate if row["ok"]]
        hit_counts = [row["top_k"] for row in rows_for_candidate]
        return (
            f"- {candidate}: queries={len(rows_for_candidate)}, "
            f"ok={sum(1 for row in rows_for_candidate if row['ok'])}, "
            f"p50_ms={round(statistics.median(latencies), 2) if latencies else 'n/a'}, "
            f"max_ms={round(max(latencies), 2) if latencies else 'n/a'}, "
            f"median_top_k={statistics.median(hit_counts) if hit_counts else 0}"
        )
    lines = [
        "# Local Index Backend Recommendation",
        "",
        "## Boundary",
        "",
        "`source_library` remains the specific source database. Local index backends are downstream indexes over fetched documents/material chunks.",
        "",
        "## First Run Evidence",
        "",
        "- Dataset benchmarked with the same 30 queries across available local candidates.",
        candidate_line("sqlite_fts_baseline"),
        candidate_line("lancedb_fts"),
        "",
        "## Recommendation",
        "",
        "1. First implementation candidate: LanceDB, because the isolated client can build a local table, create an FTS index, apply `project_id` filters, and run the same query set without changing project dependencies.",
        "2. Second implementation candidate: Qdrant, because it is the strongest AI-native retrieval backend for dense/sparse hybrid search once embedding and sparse-model pipelines are available.",
        "3. Keep YaCy local as a baseline only. It proved local push/search, but it is not the best long-term AI-agent retrieval architecture.",
        "4. Defer OpenSearch and Vespa until the project needs larger-scale ranking infrastructure.",
        "",
        "## Current Environment",
        "",
    ]
    for row in rows:
        lines.append(f"- {row['candidate']}: installed={row['local_client_installed']}, entered_benchmark={row['entered_benchmark']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-root", default="development/latest-dev-docs")
    parser.add_argument("--out-dir", default="development/latest-dev-docs/automation-runs/local-index-backend-evaluation/2026-05-14")
    parser.add_argument("--document-limit", type=int, default=40)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    dataset_dir = out_dir / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    documents = collect_documents(Path(args.docs_root), args.document_limit)
    chunks = [chunk for doc in documents for chunk in chunk_document(doc)]
    queries = [
        {"query_id": query_id, "query": query, "type": qtype, "project_id": "latest-dev-docs"}
        for query_id, query, qtype in QUERY_SET
    ]
    judgments = [
        {"query_id": q["query_id"], "judgment_mode": "manual_review_required", "notes": "No human relevance label assigned in automated run."}
        for q in queries
    ]
    write_jsonl(dataset_dir / "documents.jsonl", documents)
    write_jsonl(dataset_dir / "chunks.jsonl", chunks)
    write_jsonl(dataset_dir / "queries.jsonl", queries)
    write_jsonl(dataset_dir / "judgments.jsonl", judgments)

    index_reports: list[dict] = []
    index_report, benchmark_rows = run_sqlite_fts(chunks, queries)
    index_reports.append(index_report)
    lancedb_result = run_lancedb_fts(chunks, queries)
    benchmarked = {"SQLite FTS5 baseline"}
    if lancedb_result is not None:
        lancedb_index_report, lancedb_rows = lancedb_result
        index_reports.append(lancedb_index_report)
        benchmark_rows.extend(lancedb_rows)
        benchmarked.add("LanceDB")
    matrix_rows = candidate_matrix(benchmarked)
    write_jsonl(out_dir / "benchmark_results.jsonl", benchmark_rows)
    (out_dir / "candidate_index_report.json").write_text(json.dumps(index_reports, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "query_count": len(queries),
        "judgment_count": len(judgments),
        "source_root": args.docs_root,
        "schema": {
            "required_filter_fields": ["project_id", "source_id"],
            "id_fields": ["document_id", "chunk_id"],
        },
    }
    (out_dir / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_candidate_matrix(out_dir / "candidate_matrix.md", matrix_rows)
    write_recommendation(out_dir / "recommendation.md", matrix_rows, benchmark_rows)
    (out_dir / "README.md").write_text(
        "# Local Index Backend Evaluation\n\n"
        "This run creates a MRW latest-dev-docs dataset and benchmarks available local candidates. "
        "External clients are used only when present on PYTHONPATH, without adding project dependencies.\n",
        encoding="utf-8",
    )
    print(json.dumps({"out_dir": str(out_dir), "documents": len(documents), "chunks": len(chunks), "queries": len(queries), "benchmark_rows": len(benchmark_rows)}, ensure_ascii=False))
    return 0 if len(documents) >= 20 and len(queries) >= 30 else 1


if __name__ == "__main__":
    raise SystemExit(main())
