#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.local_index import (  # noqa: E402
    LOCAL_INDEX_QUERY_MODES,
    LocalIndexChunk,
    LocalIndexQuery,
    LocalIndexSearchResult,
    LocalIndexService,
)
from app.services.local_index.adapters.lancedb_adapter import _deterministic_vector  # noqa: E402


DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave18-vectorization-hybrid-readback/2026-05-22"
WAVE8_CONTRACT = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/wave8-search-vectorization-contract/2026-05-22/contract_summary.json"
)
WAVE10_CONTRACT = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22/contract_summary.json"
)
WAVE12_PROVIDER_READINESS = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/wave12-provider-readiness/2026-05-22/provider_readiness_summary.json"
)
WAVE14_PROVIDER_CAPABILITY = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/wave14-vectorization-provider-capability/2026-05-22/provider_capability_summary.json"
)

TARGET_TOPICS = [
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-01-open-source-platform-integration",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-global-vectorization-general-foundation",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-05-oss-node-platform-io-plan",
]
LOCAL_INDEX_MODES = ["keyword", "vector", "hybrid"]
REQUIRED_TRACE_FIELDS = [
    "adapter",
    "requested_mode",
    "executed_mode",
    "query_family",
    "project_id",
    "source_id",
    "top_k",
    "quality_trace",
    "readback",
]
REQUIRED_GAP_CODES = [
    "live_provider_quality_not_closed",
    "semantic_embedding_quality_not_proven",
    "oss_node_platform_io_sla_not_closed",
]


class RepoLocalHybridReadbackAdapter:
    """Deterministic local adapter used only by the Wave18 checker."""

    def __init__(self) -> None:
        self._chunks: list[LocalIndexChunk] = []

    def upsert_chunks(self, chunks: list[LocalIndexChunk]) -> dict[str, int | bool | str | None]:
        self._chunks = list(chunks)
        return {
            "ok": True,
            "chunk_count": len(self._chunks),
            "adapter": "repo_local_hybrid_readback_fixture",
        }

    def search(self, query: LocalIndexQuery) -> list[LocalIndexSearchResult]:
        candidates = [
            chunk
            for chunk in self._chunks
            if chunk.project_id == query.project_id
            and (not query.source_id or chunk.source_id == query.source_id)
        ]
        limit = max(1, min(50, int(query.top_k or 10)))
        scored = [_score_chunk(chunk, query) for chunk in candidates]
        scored.sort(key=lambda item: (-item["score"], item["chunk"].chunk_id))
        return [
            _result_from_scored(
                scored_row,
                query=query,
                rank=rank,
                limit=limit,
            )
            for rank, scored_row in enumerate(scored[:limit], start=1)
        ]


def build_chunks() -> list[LocalIndexChunk]:
    vector_query = "wave18 vector identity proof"
    hybrid_query = "wave18 hybrid identity proof"
    return [
        LocalIndexChunk(
            chunk_id="kw-primary",
            document_id="doc-kw-primary",
            project_id="wave18-readback",
            source_id="source-keyword",
            title="Keyword identity primary",
            content=(
                "wave18 keyword identity proof wave18 keyword identity proof "
                "repo local readback row."
            ),
            vector=_mutated_vector("keyword decoy vector"),
        ),
        LocalIndexChunk(
            chunk_id="kw-secondary",
            document_id="doc-kw-secondary",
            project_id="wave18-readback",
            source_id="source-keyword",
            title="Keyword identity secondary",
            content="wave18 keyword identity proof secondary row.",
            vector=_mutated_vector("keyword secondary decoy vector"),
        ),
        LocalIndexChunk(
            chunk_id="kw-foreign-project",
            document_id="doc-kw-foreign-project",
            project_id="other-project",
            source_id="source-keyword",
            title="Keyword foreign project",
            content="wave18 keyword identity proof must not leak across project_id.",
            vector=_deterministic_vector("wave18 keyword identity proof"),
        ),
        LocalIndexChunk(
            chunk_id="vec-primary",
            document_id="doc-vec-primary",
            project_id="wave18-readback",
            source_id="source-vector",
            title="Vector identity primary",
            content="Controlled vector identity primary material.",
            vector=_deterministic_vector(vector_query),
        ),
        LocalIndexChunk(
            chunk_id="vec-secondary",
            document_id="doc-vec-secondary",
            project_id="wave18-readback",
            source_id="source-vector",
            title="Vector identity secondary",
            content="Controlled vector identity secondary material.",
            vector=_mutated_vector(vector_query),
        ),
        LocalIndexChunk(
            chunk_id="vec-foreign-source",
            document_id="doc-vec-foreign-source",
            project_id="wave18-readback",
            source_id="source-foreign",
            title="Vector foreign source",
            content="Controlled vector identity foreign source material.",
            vector=_deterministic_vector(vector_query),
        ),
        LocalIndexChunk(
            chunk_id="hybrid-primary",
            document_id="doc-hybrid-primary",
            project_id="wave18-readback",
            source_id="source-hybrid",
            title="Hybrid identity primary",
            content=(
                "wave18 hybrid identity proof wave18 hybrid identity proof "
                "repo local readback row."
            ),
            vector=_deterministic_vector(hybrid_query),
        ),
        LocalIndexChunk(
            chunk_id="hybrid-secondary",
            document_id="doc-hybrid-secondary",
            project_id="wave18-readback",
            source_id="source-hybrid",
            title="Hybrid identity secondary",
            content="wave18 hybrid identity proof secondary row.",
            vector=_mutated_vector(hybrid_query),
        ),
        LocalIndexChunk(
            chunk_id="hybrid-foreign-project",
            document_id="doc-hybrid-foreign-project",
            project_id="other-project",
            source_id="source-hybrid",
            title="Hybrid foreign project",
            content="wave18 hybrid identity proof must not leak across project_id.",
            vector=_deterministic_vector(hybrid_query),
        ),
    ]


IDENTITY_CASES: list[dict[str, Any]] = [
    {
        "case_id": "keyword_identity_readback",
        "mode": "keyword",
        "query": "wave18 keyword identity proof",
        "source_id": "source-keyword",
        "expected_order": ["kw-primary", "kw-secondary"],
        "forbidden_chunk_ids": ["kw-foreign-project"],
        "required_components": ["keyword_score"],
    },
    {
        "case_id": "vector_identity_readback",
        "mode": "vector",
        "query": "wave18 vector identity proof",
        "source_id": "source-vector",
        "expected_order": ["vec-primary", "vec-secondary"],
        "forbidden_chunk_ids": ["vec-foreign-source"],
        "required_components": ["vector_score"],
    },
    {
        "case_id": "hybrid_identity_readback",
        "mode": "hybrid",
        "query": "wave18 hybrid identity proof",
        "source_id": "source-hybrid",
        "expected_order": ["hybrid-primary", "hybrid-secondary"],
        "forbidden_chunk_ids": ["hybrid-foreign-project"],
        "required_components": ["keyword_score", "vector_score", "hybrid_score"],
    },
]


def _mutated_vector(text: str) -> list[float]:
    vector = _deterministic_vector(text)
    if not vector:
        return vector
    mutated = [-vector[0], *vector[1:]]
    norm = math.sqrt(sum(value * value for value in mutated)) or 1.0
    return [round(value / norm, 6) for value in mutated]


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[\w]+", text) if token.strip()]


def _keyword_score(query: str, chunk: LocalIndexChunk) -> float:
    terms = _tokenize(query)
    if not terms:
        return 0.0
    text = " ".join([chunk.title, chunk.content]).lower()
    return round(sum(text.count(term) for term in terms) / len(terms), 6)


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = math.sqrt(sum(value * value for value in left[:size])) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right[:size])) or 1.0
    return round(dot / (left_norm * right_norm), 6)


def _score_chunk(chunk: LocalIndexChunk, query: LocalIndexQuery) -> dict[str, Any]:
    keyword_score = _keyword_score(query.query, chunk)
    vector_score = _cosine(_deterministic_vector(query.query), chunk.vector or _deterministic_vector(chunk.content))
    normalized_vector_score = round((vector_score + 1.0) / 2.0, 6)
    if query.mode == "keyword":
        score = keyword_score
    elif query.mode == "vector":
        score = normalized_vector_score
    else:
        score = round((0.55 * keyword_score) + (0.45 * normalized_vector_score), 6)
    return {
        "chunk": chunk,
        "score": score,
        "components": {
            "keyword_score": keyword_score,
            "vector_score": vector_score,
            "normalized_vector_score": normalized_vector_score,
            "hybrid_score": score if query.mode == "hybrid" else None,
        },
    }


def _result_from_scored(
    scored_row: dict[str, Any],
    *,
    query: LocalIndexQuery,
    rank: int,
    limit: int,
) -> LocalIndexSearchResult:
    chunk: LocalIndexChunk = scored_row["chunk"]
    trace = {
        "adapter": "repo_local_hybrid_readback_fixture",
        "requested_mode": query.mode,
        "executed_mode": query.mode,
        "query_family": "local_material",
        "project_id": query.project_id,
        "source_id": query.source_id,
        "top_k": limit,
        "quality_trace": {
            "rank": rank,
            "score_components": scored_row["components"],
            "mode_identity": query.mode,
            "provider_live_verified": False,
            "semantic_quality_claim_allowed": False,
            "scoring_fixture": "repo_deterministic_hash_vector_and_keyword_terms",
        },
        "readback": {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "project_id": chunk.project_id,
            "source_id": chunk.source_id,
            "retrieval_mode": query.mode,
        },
    }
    return LocalIndexSearchResult(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        project_id=chunk.project_id,
        source_id=chunk.source_id,
        title=chunk.title,
        content=chunk.content,
        score=float(scored_row["score"]),
        url=chunk.url,
        source_type=chunk.source_type,
        metadata={"fixture": "wave18_vectorization_hybrid_readback"},
        retrieval_mode=query.mode,
        retrieval_family="local_index",
        trace=trace,
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def check_input_artifact(path: Path, *, label: str, expected_version: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "label": label,
        "path": display_path(path),
        "status": "running",
        "failures": [],
    }
    if not path.exists():
        row["status"] = "missing"
        row["failures"].append(f"{label} artifact missing")
        return row
    data = load_json(path)
    failures: list[str] = []
    if data.get("contract_version") != expected_version:
        failures.append(f"contract_version expected {expected_version!r}, got {data.get('contract_version')!r}")
    if data.get("status") != "passed":
        failures.append(f"status expected 'passed', got {data.get('status')!r}")
    if label == "wave12" and data.get("readiness_state") != "partial":
        failures.append(f"readiness_state expected 'partial', got {data.get('readiness_state')!r}")
    if label == "wave14" and data.get("closure_claim_allowed") is not False:
        failures.append("wave14 closure_claim_allowed must remain false")
    row.update(
        {
            "status": "passed" if not failures else "failed",
            "contract_version": data.get("contract_version"),
            "input_status": data.get("status"),
            "readiness_state": data.get("readiness_state"),
            "capability_state": data.get("capability_state"),
            "closure_claim_allowed": data.get("closure_claim_allowed"),
            "failures": failures,
        }
    )
    return row


def run_identity_readback() -> dict[str, Any]:
    service = LocalIndexService(RepoLocalHybridReadbackAdapter())
    upsert = service.upsert_chunks(build_chunks())
    cases = []
    failures: list[str] = []
    for case in IDENTITY_CASES:
        results = service.search(
            LocalIndexQuery(
                query=case["query"],
                project_id="wave18-readback",
                source_id=case["source_id"],
                mode=case["mode"],
                top_k=2,
            )
        )
        records = [result.to_dict() for result in results]
        case_failures = validate_case(case, records)
        failures.extend(f"{case['case_id']}: {failure}" for failure in case_failures)
        cases.append(
            {
                "case_id": case["case_id"],
                "mode": case["mode"],
                "query": case["query"],
                "source_id": case["source_id"],
                "expected_order": case["expected_order"],
                "chunk_order": [record["chunk_id"] for record in records],
                "scores": [record["score"] for record in records],
                "trace_readback": [
                    {
                        "chunk_id": record["chunk_id"],
                        "retrieval_mode": record["retrieval_mode"],
                        "trace": record["trace"],
                    }
                    for record in records
                ],
                "failures": case_failures,
            }
        )
    return {
        "status": "passed" if not failures else "failed",
        "upsert": upsert,
        "supported_modes": LOCAL_INDEX_MODES,
        "exported_modes": sorted(LOCAL_INDEX_QUERY_MODES),
        "cases": cases,
        "failures": failures,
    }


def validate_case(case: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    expected_order = list(case["expected_order"])
    actual_order = [record.get("chunk_id") for record in records]
    if actual_order != expected_order:
        failures.append(f"expected chunk order {expected_order!r}, got {actual_order!r}")
    leaked = sorted(set(actual_order) & set(case["forbidden_chunk_ids"]))
    if leaked:
        failures.append(f"forbidden chunks returned: {leaked}")
    scores = [record.get("score") for record in records]
    if any(score is None for score in scores):
        failures.append("all records must include numeric scores")
    elif any(float(left) < float(right) for left, right in zip(scores, scores[1:], strict=False)):
        failures.append(f"scores are not nonincreasing: {scores!r}")
    for record in records:
        failures.extend(validate_record_trace(case, record))
    return failures


def validate_record_trace(case: dict[str, Any], record: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    mode = case["mode"]
    if record.get("retrieval_mode") != mode:
        failures.append(f"{record.get('chunk_id')}: retrieval_mode expected {mode!r}")
    if record.get("retrieval_family") != "local_index":
        failures.append(f"{record.get('chunk_id')}: retrieval_family expected 'local_index'")
    trace = record.get("trace") or {}
    for field in REQUIRED_TRACE_FIELDS:
        if field not in trace:
            failures.append(f"{record.get('chunk_id')}: trace field {field!r} missing")
    if trace.get("requested_mode") != mode or trace.get("executed_mode") != mode:
        failures.append(f"{record.get('chunk_id')}: trace mode identity mismatch")
    if "fallback_from" in trace or "fallback_reason" in trace:
        failures.append(f"{record.get('chunk_id')}: fallback metadata is not allowed in identity readback")
    quality_trace = trace.get("quality_trace") or {}
    components = quality_trace.get("score_components") or {}
    for component in case["required_components"]:
        if components.get(component) is None:
            failures.append(f"{record.get('chunk_id')}: quality component {component!r} missing")
    if quality_trace.get("provider_live_verified") is not False:
        failures.append(f"{record.get('chunk_id')}: provider_live_verified must be false")
    if quality_trace.get("semantic_quality_claim_allowed") is not False:
        failures.append(f"{record.get('chunk_id')}: semantic_quality_claim_allowed must be false")
    readback = trace.get("readback") or {}
    readback_expected = {
        "chunk_id": record.get("chunk_id"),
        "document_id": record.get("document_id"),
        "project_id": record.get("project_id"),
        "source_id": record.get("source_id"),
        "retrieval_mode": record.get("retrieval_mode"),
    }
    for key, expected in readback_expected.items():
        if readback.get(key) != expected:
            failures.append(f"{record.get('chunk_id')}: readback[{key}] expected {expected!r}, got {readback.get(key)!r}")
    return failures


def build_contract() -> dict[str, Any]:
    inputs = {
        "wave8": check_input_artifact(
            WAVE8_CONTRACT,
            label="wave8",
            expected_version="wave8-search-vectorization-runtime-contract.v1",
        ),
        "wave10": check_input_artifact(
            WAVE10_CONTRACT,
            label="wave10",
            expected_version="wave10-vectorization-quality-gate.v1",
        ),
        "wave12": check_input_artifact(
            WAVE12_PROVIDER_READINESS,
            label="wave12",
            expected_version="wave12-provider-readiness-gate.v1",
        ),
        "wave14": check_input_artifact(
            WAVE14_PROVIDER_CAPABILITY,
            label="wave14",
            expected_version="wave14-vectorization-provider-capability.v1",
        ),
    }
    identity_readback = run_identity_readback()
    target_topics = [{"path": topic, "exists": (REPO_ROOT / topic).exists()} for topic in TARGET_TOPICS]
    failures = [
        f"{name}: {failure}"
        for name, row in inputs.items()
        for failure in row.get("failures", [])
    ]
    failures.extend(identity_readback["failures"])
    failures.extend(f"target topic missing: {row['path']}" for row in target_topics if not row["exists"])
    return {
        "contract_version": "wave18-vectorization-hybrid-readback.v1",
        "generated_by": "ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py",
        "status": "passed" if not failures else "failed",
        "scope": "deterministic_repo_local_fixture_no_network_no_container_no_live_provider_closure",
        "target_topics": target_topics,
        "inputs": inputs,
        "mode_identity_readback": identity_readback,
        "closure_claim_allowed": False,
        "provider_live_closure_claim_allowed": False,
        "semantic_quality_claim_allowed": False,
        "oss_node_platform_io": {
            "can_consume_readback_fields": [
                "retrieval_mode",
                "retrieval_family",
                "trace.requested_mode",
                "trace.executed_mode",
                "trace.quality_trace.score_components",
                "trace.readback.chunk_id",
                "trace.readback.project_id",
                "trace.readback.source_id",
            ],
            "must_propagate_gap_fields": [
                "provider_live_verified=false",
                "semantic_quality_claim_allowed=false",
                "closure_claim_allowed=false",
            ],
            "closure_claim_allowed": False,
        },
        "gate_semantics": {
            "status_passed_means": (
                "repo-local keyword/vector/hybrid identity, quality trace, and result readback contract "
                "are deterministic and machine-checkable"
            ),
            "status_passed_does_not_mean": (
                "live embedding providers, SearXNG/YaCy live quality, provider=auto promotion, "
                "semantic relevance quality, or OSS node SLA are sealed"
            ),
        },
        "remaining_gaps": [
            {
                "code": "live_provider_quality_not_closed",
                "message": "This checker does not call external embedding providers or local open-search services.",
            },
            {
                "code": "semantic_embedding_quality_not_proven",
                "message": "Deterministic vectors prove wiring and trace readback, not production semantic relevance.",
            },
            {
                "code": "oss_node_platform_io_sla_not_closed",
                "message": "OSS node IO can consume the readback fields but still needs node-level live SLA evidence.",
            },
        ],
        "assertions": [
            "LOCAL_INDEX_QUERY_MODES exports keyword, vector, and hybrid",
            "keyword, vector, and hybrid cases preserve requested/executed mode identity",
            "quality_trace exposes score components and disallows semantic quality claims",
            "trace.readback mirrors returned chunk/project/source/retrieval identity",
            "closure_claim_allowed=false",
        ],
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "hybrid_readback_contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    case_rows = []
    for case in contract["mode_identity_readback"]["cases"]:
        case_rows.append(
            "| {mode} | {case_id} | {order} | {scores} | {failures} |".format(
                mode=case["mode"],
                case_id=case["case_id"],
                order=", ".join(case["chunk_order"]),
                scores=", ".join(str(score) for score in case["scores"]),
                failures=len(case["failures"]),
            )
        )
    input_rows = []
    for name, row in contract["inputs"].items():
        input_rows.append(
            "| {name} | {status} | {version} | {state} | {closure} |".format(
                name=name,
                status=row.get("status"),
                version=row.get("contract_version"),
                state=row.get("readiness_state") or row.get("capability_state") or "",
                closure=row.get("closure_claim_allowed"),
            )
        )
    readme = [
        "# Wave18 Vectorization Hybrid Readback",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        f"- closure_claim_allowed: `{str(bool(contract['closure_claim_allowed'])).lower()}`",
        "",
        "## Inputs",
        "",
        "| input | status | contract_version | state | closure_claim_allowed |",
        "|---|---|---|---|---|",
        *input_rows,
        "",
        "## Mode Identity Readback",
        "",
        "| mode | case | chunk_order | scores | failures |",
        "|---|---|---|---|---:|",
        *case_rows,
        "",
        "## Gate Semantics",
        "",
        f"- status passed means: {contract['gate_semantics']['status_passed_means']}",
        f"- status passed does not mean: {contract['gate_semantics']['status_passed_does_not_mean']}",
        "",
        "## Remaining Gaps",
        "",
        *[f"- `{item['code']}`: {item['message']}" for item in contract["remaining_gaps"]],
        "",
        "## Rerun",
        "",
        "```bash",
        f"PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py --out-dir {display_path(out_dir)}",
        "```",
        "",
        "Full deterministic output is in `hybrid_readback_contract.json`.",
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
                "closure_claim_allowed": contract["closure_claim_allowed"],
                "modes": [
                    case["mode"]
                    for case in contract["mode_identity_readback"]["cases"]
                ],
                "out_dir": display_path(out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
