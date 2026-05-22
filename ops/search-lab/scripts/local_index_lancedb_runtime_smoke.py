#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import platform
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

from app.services.local_index import LocalIndexChunk, LocalIndexQuery, LocalIndexService
from app.services.local_index.adapters import LanceDBLocalIndexAdapter, is_lancedb_available
from app.services.local_index.adapters.lancedb_adapter import _deterministic_vector


DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/local-index-lancedb-runtime-smoke/2026-05-22"


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def build_chunks() -> list[LocalIndexChunk]:
    vector_query = "semantic vector target robotics benchmark"
    hybrid_query = "hybrid retrieval fusion robotics policy"
    return [
        LocalIndexChunk(
            chunk_id="chunk-keyword",
            document_id="doc-keyword",
            project_id="runtime-smoke",
            source_id="source-keyword",
            title="Keyword runtime proof",
            content="rare-lancedb-keyword-proof appears in this real table row for FTS validation.",
            metadata={"expected_mode": "keyword"},
        ),
        LocalIndexChunk(
            chunk_id="chunk-vector",
            document_id="doc-vector",
            project_id="runtime-smoke",
            source_id="source-vector",
            title="Vector runtime proof",
            content="A row for semantic vector target robotics benchmark validation.",
            metadata={"expected_mode": "vector"},
            vector=_deterministic_vector(vector_query),
        ),
        LocalIndexChunk(
            chunk_id="chunk-hybrid",
            document_id="doc-hybrid",
            project_id="runtime-smoke",
            source_id="source-hybrid",
            title="Hybrid runtime proof",
            content=f"{hybrid_query} appears in the text and uses a matching vector.",
            metadata={"expected_mode": "hybrid"},
            vector=_deterministic_vector(hybrid_query),
        ),
        LocalIndexChunk(
            chunk_id="chunk-foreign-project",
            document_id="doc-foreign",
            project_id="other-project",
            source_id="source-foreign",
            title="Foreign project row",
            content="rare-lancedb-keyword-proof should be filtered out by project_id.",
            metadata={"expected_mode": "filter_guard"},
        ),
    ]


def run_smoke(out_dir: Path) -> tuple[int, dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = tempfile.mkdtemp(prefix="mrw-local-index-lancedb-runtime-")
    started = time.perf_counter()
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {
            "lancedb": package_version("lancedb"),
            "pyarrow": package_version("pyarrow"),
        },
        "db_path": db_path,
        "out_dir": display_path(out_dir),
        "rerun_command": (
            "main/backend/.venv311/bin/python "
            "ops/search-lab/scripts/local_index_lancedb_runtime_smoke.py "
            f"--out-dir {display_path(out_dir)}"
        ),
        "blockers": [],
        "upsert": None,
        "modes": {},
        "assertions": [],
    }

    if not is_lancedb_available() or importlib.util.find_spec("pyarrow") is None:
        report["status"] = "blocked"
        report["blockers"].append(
            {
                "code": "missing_optional_dependency",
                "message": "lancedb and pyarrow must both be importable in main/backend/.venv311.",
                "install_command": "scripts/optional-enhancements.sh install-lancedb",
            }
        )
        write_report(out_dir, report)
        return 2, report

    service = LocalIndexService(LanceDBLocalIndexAdapter(db_path=db_path, table_name="chunks"))
    chunks = build_chunks()
    report["upsert"] = service.upsert_chunks(chunks)

    checks = [
        {
            "mode": "keyword",
            "query": "rare-lancedb-keyword-proof",
            "expected_chunk_id": "chunk-keyword",
            "expected_source_id": "source-keyword",
        },
        {
            "mode": "vector",
            "query": "semantic vector target robotics benchmark",
            "expected_chunk_id": "chunk-vector",
            "expected_source_id": "source-vector",
        },
        {
            "mode": "hybrid",
            "query": "hybrid retrieval fusion robotics policy",
            "expected_chunk_id": "chunk-hybrid",
            "expected_source_id": "source-hybrid",
        },
    ]

    failures: list[str] = []
    for check in checks:
        mode = check["mode"]
        query_started = time.perf_counter()
        results = service.search(
            LocalIndexQuery(
                query=check["query"],
                project_id="runtime-smoke",
                source_id=check["expected_source_id"],
                mode=mode,
                top_k=3,
            )
        )
        latency_ms = round((time.perf_counter() - query_started) * 1000, 2)
        records = [result.to_dict() for result in results]
        top = records[0] if records else None
        executed_mode = (top or {}).get("trace", {}).get("executed_mode")
        report["modes"][mode] = {
            "query": check["query"],
            "expected_chunk_id": check["expected_chunk_id"],
            "expected_source_id": check["expected_source_id"],
            "latency_ms": latency_ms,
            "top_k": len(records),
            "top_chunk_id": (top or {}).get("chunk_id"),
            "top_source_id": (top or {}).get("source_id"),
            "top_score": (top or {}).get("score"),
            "executed_mode": executed_mode,
            "retrieval_mode": (top or {}).get("retrieval_mode"),
            "trace": (top or {}).get("trace"),
            "results": records,
        }
        if not top:
            failures.append(f"{mode}: no result returned")
            continue
        if top.get("chunk_id") != check["expected_chunk_id"]:
            failures.append(f"{mode}: expected {check['expected_chunk_id']} as top result, got {top.get('chunk_id')}")
        if top.get("source_id") != check["expected_source_id"]:
            failures.append(f"{mode}: expected source filter {check['expected_source_id']}, got {top.get('source_id')}")
        if top.get("retrieval_mode") != mode or executed_mode != mode:
            failures.append(f"{mode}: expected real {mode} execution, got retrieval={top.get('retrieval_mode')} executed={executed_mode}")

    report["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    report["assertions"] = [
        "lancedb and pyarrow importable",
        "real LanceDB table created through LanceDBLocalIndexAdapter",
        "project_id and source_id filters applied through LanceDB where predicate",
        "keyword, vector, and hybrid modes each returned the expected top row without fallback",
    ]
    if failures:
        report["status"] = "failed"
        report["failures"] = failures
        write_report(out_dir, report)
        return 1, report

    report["status"] = "passed"
    write_report(out_dir, report)
    return 0, report


def write_report(out_dir: Path, report: dict[str, Any]) -> None:
    (out_dir / "runtime_smoke_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    mode_lines = []
    for mode, row in report.get("modes", {}).items():
        mode_lines.append(
            "| {mode} | {executed} | {chunk} | {source} | {top_k} | {latency} |".format(
                mode=mode,
                executed=row.get("executed_mode"),
                chunk=row.get("top_chunk_id"),
                source=row.get("top_source_id"),
                top_k=row.get("top_k"),
                latency=row.get("latency_ms"),
            )
        )
    if not mode_lines:
        mode_lines.append("| n/a | n/a | n/a | n/a | n/a | n/a |")
    blockers = report.get("blockers") or []
    blocker_lines = [f"- `{item['code']}`: {item['message']}" for item in blockers] or ["- none"]
    readme = [
        "# LanceDB Local Index Runtime Smoke",
        "",
        f"- status: `{report.get('status')}`",
        f"- generated_at: `{report.get('generated_at')}`",
        f"- lancedb: `{report.get('packages', {}).get('lancedb')}`",
        f"- pyarrow: `{report.get('packages', {}).get('pyarrow')}`",
        f"- db_path: `{report.get('db_path')}`",
        "",
        "## Mode Evidence",
        "",
        "| mode | executed_mode | top_chunk_id | top_source_id | top_k | latency_ms |",
        "|---|---|---|---|---:|---:|",
        *mode_lines,
        "",
        "## Blockers",
        "",
        *blocker_lines,
        "",
        "## Rerun",
        "",
        "```bash",
        str(report.get("rerun_command")),
        "```",
        "",
        "Full JSON evidence is in `runtime_smoke_results.json`.",
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
    code, report = run_smoke(out_dir)
    print(json.dumps({"status": report.get("status"), "out_dir": display_path(out_dir), "modes": report.get("modes", {})}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
