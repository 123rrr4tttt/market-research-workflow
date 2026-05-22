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


DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22"
PROJECT_ID = "lancedb-benchmark"


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
    keyword_query = "rare alpha keyword benchmark proof"
    vector_query = "semantic vector quality benchmark"
    hybrid_query = "hybrid fusion ranking benchmark"
    return [
        LocalIndexChunk(
            chunk_id="kw-primary",
            document_id="doc-kw-primary",
            project_id=PROJECT_ID,
            source_id="source-alpha",
            title="Keyword primary",
            content=f"{keyword_query} {keyword_query} {keyword_query} robotics policy evidence.",
            vector=_deterministic_vector("keyword primary decoy vector"),
        ),
        LocalIndexChunk(
            chunk_id="kw-secondary",
            document_id="doc-kw-secondary",
            project_id=PROJECT_ID,
            source_id="source-alpha",
            title="Keyword secondary",
            content=f"{keyword_query} secondary evidence.",
            vector=_deterministic_vector("keyword secondary decoy vector"),
        ),
        LocalIndexChunk(
            chunk_id="kw-foreign-source",
            document_id="doc-kw-foreign-source",
            project_id=PROJECT_ID,
            source_id="source-beta",
            title="Keyword foreign source",
            content=f"{keyword_query} {keyword_query} excluded by source_id.",
            vector=_deterministic_vector("keyword foreign source decoy vector"),
        ),
        LocalIndexChunk(
            chunk_id="kw-foreign-project",
            document_id="doc-kw-foreign-project",
            project_id="other-project",
            source_id="source-alpha",
            title="Keyword foreign project",
            content=f"{keyword_query} {keyword_query} excluded by project_id.",
            vector=_deterministic_vector("keyword foreign project decoy vector"),
        ),
        LocalIndexChunk(
            chunk_id="vec-primary",
            document_id="doc-vec-primary",
            project_id=PROJECT_ID,
            source_id="source-vector",
            title="Vector primary",
            content="Controlled vector quality primary material.",
            vector=_deterministic_vector(vector_query),
        ),
        LocalIndexChunk(
            chunk_id="vec-secondary",
            document_id="doc-vec-secondary",
            project_id=PROJECT_ID,
            source_id="source-vector",
            title="Vector secondary",
            content="Controlled vector quality secondary material.",
            vector=_deterministic_vector("nearby vector quality benchmark secondary"),
        ),
        LocalIndexChunk(
            chunk_id="vec-foreign-source",
            document_id="doc-vec-foreign-source",
            project_id=PROJECT_ID,
            source_id="source-beta",
            title="Vector foreign source",
            content="Controlled vector quality foreign source material.",
            vector=_deterministic_vector(vector_query),
        ),
        LocalIndexChunk(
            chunk_id="vec-foreign-project",
            document_id="doc-vec-foreign-project",
            project_id="other-project",
            source_id="source-vector",
            title="Vector foreign project",
            content="Controlled vector quality foreign project material.",
            vector=_deterministic_vector(vector_query),
        ),
        LocalIndexChunk(
            chunk_id="hybrid-primary",
            document_id="doc-hybrid-primary",
            project_id=PROJECT_ID,
            source_id="source-hybrid",
            title="Hybrid primary",
            content=f"{hybrid_query} robotics governance {hybrid_query} robotics governance.",
            vector=_deterministic_vector(hybrid_query),
        ),
        LocalIndexChunk(
            chunk_id="hybrid-secondary",
            document_id="doc-hybrid-secondary",
            project_id=PROJECT_ID,
            source_id="source-hybrid",
            title="Hybrid secondary",
            content=f"{hybrid_query} secondary governance.",
            vector=_deterministic_vector("hybrid secondary decoy vector"),
        ),
        LocalIndexChunk(
            chunk_id="hybrid-foreign-source",
            document_id="doc-hybrid-foreign-source",
            project_id=PROJECT_ID,
            source_id="source-beta",
            title="Hybrid foreign source",
            content=f"{hybrid_query} robotics governance excluded by source_id.",
            vector=_deterministic_vector(hybrid_query),
        ),
        LocalIndexChunk(
            chunk_id="hybrid-foreign-project",
            document_id="doc-hybrid-foreign-project",
            project_id="other-project",
            source_id="source-hybrid",
            title="Hybrid foreign project",
            content=f"{hybrid_query} robotics governance excluded by project_id.",
            vector=_deterministic_vector(hybrid_query),
        ),
    ]


RANKING_CASES: list[dict[str, Any]] = [
    {
        "case_id": "keyword_source_top2",
        "mode": "keyword",
        "query": "rare alpha keyword benchmark proof",
        "project_id": PROJECT_ID,
        "source_id": "source-alpha",
        "top_k": 2,
        "expected_order": ["kw-primary", "kw-secondary"],
        "forbidden_chunk_ids": ["kw-foreign-source", "kw-foreign-project"],
        "score_order": "nonincreasing",
    },
    {
        "case_id": "vector_source_top2",
        "mode": "vector",
        "query": "semantic vector quality benchmark",
        "project_id": PROJECT_ID,
        "source_id": "source-vector",
        "top_k": 2,
        "expected_order": ["vec-primary", "vec-secondary"],
        "forbidden_chunk_ids": ["vec-foreign-source", "vec-foreign-project"],
        "score_order": "nondecreasing",
    },
    {
        "case_id": "hybrid_source_top2",
        "mode": "hybrid",
        "query": "hybrid fusion ranking benchmark",
        "project_id": PROJECT_ID,
        "source_id": "source-hybrid",
        "top_k": 2,
        "expected_order": ["hybrid-primary", "hybrid-secondary"],
        "forbidden_chunk_ids": ["hybrid-foreign-source", "hybrid-foreign-project"],
        "score_order": "nonincreasing",
    },
]


PROJECT_FILTER_CASES: list[dict[str, Any]] = [
    {
        "case_id": "keyword_project_filter",
        "mode": "keyword",
        "query": "rare alpha keyword benchmark proof",
        "project_id": PROJECT_ID,
        "source_id": None,
        "top_k": 5,
        "forbidden_chunk_ids": ["kw-foreign-project"],
    },
    {
        "case_id": "vector_project_filter",
        "mode": "vector",
        "query": "semantic vector quality benchmark",
        "project_id": PROJECT_ID,
        "source_id": None,
        "top_k": 5,
        "forbidden_chunk_ids": ["vec-foreign-project"],
    },
    {
        "case_id": "hybrid_project_filter",
        "mode": "hybrid",
        "query": "hybrid fusion ranking benchmark",
        "project_id": PROJECT_ID,
        "source_id": None,
        "top_k": 5,
        "forbidden_chunk_ids": ["hybrid-foreign-project"],
    },
]


def run_benchmark(out_dir: Path, repeats: int) -> tuple[int, dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = tempfile.mkdtemp(prefix="mrw-local-index-lancedb-benchmark-")
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
            "ops/search-lab/scripts/local_index_lancedb_benchmark_quality.py "
            f"--out-dir {display_path(out_dir)}"
        ),
        "assertions": [],
        "remaining_blockers": [
            {
                "code": "semantic_embedding_quality_not_proven",
                "message": (
                    "This benchmark uses deterministic vectors to prove LanceDB ranking wiring and stable "
                    "top-k behavior. It does not prove production embedding model relevance quality."
                ),
            },
            {
                "code": "global_vector_contract_not_closed",
                "message": (
                    "Unified vector object schema, embedding model/version provenance, and main search "
                    "evidence contract alignment remain open in CURRENT_DEV."
                ),
            },
        ],
        "blockers": [],
        "upsert": None,
        "ranking_cases": [],
        "filter_cases": [],
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

    failures: list[str] = []
    for case in RANKING_CASES:
        row, row_failures = run_ranking_case(service, case, repeats)
        report["ranking_cases"].append(row)
        failures.extend(row_failures)
    for case in PROJECT_FILTER_CASES:
        row, row_failures = run_filter_case(service, case)
        report["filter_cases"].append(row)
        failures.extend(row_failures)

    report["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    report["assertions"] = [
        "lancedb and pyarrow importable only in the optional benchmark environment",
        "controlled dataset indexed through LocalIndexService and LanceDBLocalIndexAdapter",
        "keyword, vector, and hybrid repeated top-k order remains stable",
        "project_id and source_id filters exclude exact-match foreign rows",
        "result trace includes adapter, requested/executed mode, query family, project_id, source_id, and top_k",
        "vector and hybrid cases execute without keyword fallback",
    ]
    if failures:
        report["status"] = "failed"
        report["failures"] = failures
        write_report(out_dir, report)
        return 1, report

    report["status"] = "passed"
    write_report(out_dir, report)
    return 0, report


def run_ranking_case(service: LocalIndexService, case: dict[str, Any], repeats: int) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    repeat_rows = []
    first_order: list[str] | None = None
    for repeat_index in range(repeats):
        records, latency_ms = search_records(service, case)
        ids = [record["chunk_id"] for record in records]
        expected_order = list(case["expected_order"])
        order_prefix = ids[: len(expected_order)]
        if first_order is None:
            first_order = order_prefix
        if order_prefix != expected_order:
            failures.append(f"{case['case_id']} repeat {repeat_index}: expected {expected_order}, got {order_prefix}")
        if order_prefix != first_order:
            failures.append(f"{case['case_id']} repeat {repeat_index}: order changed from {first_order} to {order_prefix}")
        failures.extend(validate_filters_and_trace(case, records, f"{case['case_id']} repeat {repeat_index}"))
        score_order_ok = validate_score_order(records, case["score_order"])
        if not score_order_ok:
            failures.append(f"{case['case_id']} repeat {repeat_index}: score order is not {case['score_order']}")
        repeat_rows.append(
            {
                "repeat": repeat_index,
                "latency_ms": latency_ms,
                "chunk_order": ids,
                "scores": [record.get("score") for record in records],
                "score_order_ok": score_order_ok,
                "trace": [record.get("trace") for record in records],
            }
        )
    return (
        {
            "case_id": case["case_id"],
            "mode": case["mode"],
            "query": case["query"],
            "project_id": case["project_id"],
            "source_id": case.get("source_id"),
            "top_k": case["top_k"],
            "expected_order": case["expected_order"],
            "stable_order": first_order,
            "passed": not failures,
            "repeats": repeat_rows,
        },
        failures,
    )


def run_filter_case(service: LocalIndexService, case: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    records, latency_ms = search_records(service, case)
    failures = validate_filters_and_trace(case, records, case["case_id"])
    return (
        {
            "case_id": case["case_id"],
            "mode": case["mode"],
            "query": case["query"],
            "project_id": case["project_id"],
            "source_id": case.get("source_id"),
            "top_k": case["top_k"],
            "latency_ms": latency_ms,
            "chunk_order": [record["chunk_id"] for record in records],
            "forbidden_chunk_ids": case["forbidden_chunk_ids"],
            "passed": not failures,
            "results": records,
        },
        failures,
    )


def search_records(service: LocalIndexService, case: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    results = service.search(
        LocalIndexQuery(
            query=case["query"],
            project_id=case["project_id"],
            source_id=case.get("source_id"),
            mode=case["mode"],
            top_k=case["top_k"],
        )
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return [result.to_dict() for result in results], latency_ms


def validate_filters_and_trace(case: dict[str, Any], records: list[dict[str, Any]], label: str) -> list[str]:
    failures: list[str] = []
    ids = [record["chunk_id"] for record in records]
    for forbidden in case.get("forbidden_chunk_ids", []):
        if forbidden in ids:
            failures.append(f"{label}: forbidden chunk {forbidden} was returned")
    for record in records:
        if record.get("project_id") != case["project_id"]:
            failures.append(f"{label}: project filter leaked {record.get('chunk_id')} from {record.get('project_id')}")
        if case.get("source_id") and record.get("source_id") != case["source_id"]:
            failures.append(f"{label}: source filter leaked {record.get('chunk_id')} from {record.get('source_id')}")
        trace = record.get("trace") or {}
        expected_trace = {
            "adapter": "lancedb",
            "requested_mode": case["mode"],
            "executed_mode": case["mode"],
            "query_family": "local_material",
            "project_id": case["project_id"],
            "source_id": case.get("source_id"),
            "top_k": case["top_k"],
        }
        for key, expected_value in expected_trace.items():
            if trace.get(key) != expected_value:
                failures.append(
                    f"{label}: trace[{key}] expected {expected_value!r}, got {trace.get(key)!r} on {record.get('chunk_id')}"
                )
        if "fallback_from" in trace:
            failures.append(f"{label}: unexpected fallback trace on {record.get('chunk_id')}: {trace}")
    return failures


def validate_score_order(records: list[dict[str, Any]], direction: str) -> bool:
    scores = [record.get("score") for record in records]
    if len(scores) < 2 or any(score is None for score in scores):
        return False
    numeric_scores = [float(score) for score in scores]
    pairs = zip(numeric_scores, numeric_scores[1:], strict=False)
    if direction == "nondecreasing":
        return all(left <= right for left, right in pairs)
    return all(left >= right for left, right in pairs)


def write_report(out_dir: Path, report: dict[str, Any]) -> None:
    (out_dir / "benchmark_quality_results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ranking_lines = []
    for row in report.get("ranking_cases", []):
        latencies = [repeat["latency_ms"] for repeat in row.get("repeats", [])]
        ranking_lines.append(
            "| {mode} | {case_id} | {passed} | {expected} | {stable} | {latency} |".format(
                mode=row.get("mode"),
                case_id=row.get("case_id"),
                passed=row.get("passed"),
                expected=", ".join(row.get("expected_order") or []),
                stable=", ".join(row.get("stable_order") or []),
                latency=", ".join(str(value) for value in latencies),
            )
        )
    if not ranking_lines:
        ranking_lines.append("| n/a | n/a | n/a | n/a | n/a | n/a |")

    filter_lines = []
    for row in report.get("filter_cases", []):
        filter_lines.append(
            "| {mode} | {case_id} | {passed} | {returned} | {forbidden} |".format(
                mode=row.get("mode"),
                case_id=row.get("case_id"),
                passed=row.get("passed"),
                returned=", ".join(row.get("chunk_order") or []),
                forbidden=", ".join(row.get("forbidden_chunk_ids") or []),
            )
        )
    if not filter_lines:
        filter_lines.append("| n/a | n/a | n/a | n/a | n/a |")

    blockers = report.get("blockers") or []
    blocker_lines = [f"- `{item['code']}`: {item['message']}" for item in blockers] or ["- none"]
    remaining = report.get("remaining_blockers") or []
    remaining_lines = [f"- `{item['code']}`: {item['message']}" for item in remaining] or ["- none"]

    readme = [
        "# LanceDB Local Index Benchmark Quality",
        "",
        f"- status: `{report.get('status')}`",
        f"- generated_at: `{report.get('generated_at')}`",
        f"- lancedb: `{report.get('packages', {}).get('lancedb')}`",
        f"- pyarrow: `{report.get('packages', {}).get('pyarrow')}`",
        f"- db_path: `{report.get('db_path')}`",
        "",
        "## Scope",
        "",
        "This is a controlled LanceDB benchmark-quality gate for the optional `local_index` adapter. It verifies repeatable ranking behavior and adapter evidence fields without adding LanceDB to default project dependencies.",
        "",
        "## Ranking Stability",
        "",
        "| mode | case | passed | expected_top_order | stable_top_order | latency_ms_by_repeat |",
        "|---|---|---:|---|---|---|",
        *ranking_lines,
        "",
        "## Filter Guards",
        "",
        "| mode | case | passed | returned_chunks | forbidden_chunks |",
        "|---|---|---:|---|---|",
        *filter_lines,
        "",
        "## Runtime Blockers",
        "",
        *blocker_lines,
        "",
        "## Remaining Blockers",
        "",
        *remaining_lines,
        "",
        "## Rerun",
        "",
        "```bash",
        str(report.get("rerun_command")),
        "```",
        "",
        "Full JSON evidence is in `benchmark_quality_results.json`.",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    repeats = max(2, int(args.repeats or 3))
    code, report = run_benchmark(out_dir, repeats)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "out_dir": display_path(out_dir),
                "ranking_cases": [
                    {"case_id": row.get("case_id"), "passed": row.get("passed")}
                    for row in report.get("ranking_cases", [])
                ],
                "filter_cases": [
                    {"case_id": row.get("case_id"), "passed": row.get("passed")}
                    for row in report.get("filter_cases", [])
                ],
                "remaining_blockers": [item.get("code") for item in report.get("remaining_blockers", [])],
            },
            ensure_ascii=False,
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
