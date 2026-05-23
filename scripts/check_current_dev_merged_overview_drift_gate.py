#!/usr/bin/env python3
"""Validate the CURRENT_DEV MERGED_OVERVIEW RAG drift gate.

This checker is intentionally bounded to the Wave13 worker scope. It does not
update shared navigation files; it verifies that the topic-local evidence maps
the retired RAG Round2 anchors to the current local_index/vectorization gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOPIC_DIR = REPO_ROOT / "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/MERGED_OVERVIEW"
LEGACY_DOC = TOPIC_DIR / "02_rag-incremental-best-practice-pool-round2.md"
EVIDENCE_DOC = TOPIC_DIR / "03_wave13-current-merged-overview-rag-drift-gate-2026-05-22.md"

OLD_RAG_ANCHORS = [
    "main/backend/app/services/rag/minimal_rag.py",
    "main/backend/scripts/rag_eval.py",
    "main/backend/tests/unit/test_minimal_rag_unittest.py",
]


@dataclass(frozen=True)
class Anchor:
    path: str
    required_text: tuple[str, ...]


CURRENT_ANCHORS = [
    Anchor(
        "main/backend/app/services/local_index/schema.py",
        (
            "LOCAL_INDEX_QUERY_MODES",
            "LocalIndexChunk",
            "LocalIndexQuery",
            "LocalIndexSearchResult",
            "normalize_local_index_mode",
            "metadata",
        ),
    ),
    Anchor(
        "main/backend/app/services/local_index/service.py",
        (
            "LocalIndexService",
            "normalize_local_index_mode",
            "upsert_chunks",
            "search",
        ),
    ),
    Anchor(
        "main/backend/app/services/local_index/adapters/lancedb_adapter.py",
        (
            "LanceDBLocalIndexAdapter",
            "_deterministic_vector",
            "query_type=\"fts\"",
            "query_type=\"hybrid\"",
            "fallback_from",
            "fallback_reason",
        ),
    ),
    Anchor(
        "main/backend/tests/unit/test_local_index_service_unittest.py",
        (
            "test_query_mode_contract_is_exported_and_normalized",
            "test_lancedb_adapter_dispatches_keyword_vector_and_hybrid_modes",
            "test_lancedb_adapter_falls_back_to_keyword_when_vector_runtime_is_unavailable",
            "test_lancedb_adapter_falls_back_to_keyword_when_hybrid_runtime_is_unavailable",
        ),
    ),
    Anchor(
        "ops/search-lab/scripts/wave8_search_vectorization_contract.py",
        (
            "wave8-search-vectorization-runtime-contract.v1",
            "local_index_runtime_smoke",
            "local_index_benchmark",
            "semantic_embedding_quality_not_proven",
        ),
    ),
    Anchor(
        "main/backend/tests/unit/test_wave8_search_vectorization_contract_unittest.py",
        (
            "test_wave8_contract_reuses_recorded_evidence_without_claiming_live_services",
            "current_container_availability_not_replayed",
            "semantic_embedding_quality_not_proven",
        ),
    ),
    Anchor(
        "ops/search-lab/scripts/wave10_vectorization_quality_gate.py",
        (
            "wave10-vectorization-quality-gate.v1",
            "REQUIRED_BENCHMARK_TRACE_FIELDS",
            "check_local_index_fallback_contract",
            "semantic_embedding_quality_not_proven",
        ),
    ),
    Anchor(
        "main/backend/tests/unit/test_wave10_vectorization_quality_gate_unittest.py",
        (
            "test_gate_checks_provider_trace_modes_thresholds_and_fallback_reason",
            "fallback_reason",
            "semantic_embedding_quality_not_proven",
        ),
    ),
    Anchor(
        "ops/search-lab/scripts/wave12_provider_readiness_gate.py",
        (
            "wave12-provider-readiness-gate.v1",
            "readiness_state",
            "missing_optional_dependency",
            "semantic_embedding_quality_not_closed",
        ),
    ),
    Anchor(
        "main/backend/tests/unit/test_wave12_provider_readiness_gate_unittest.py",
        (
            "test_gate_reports_live_probe_status_fallbacks_and_unsupported_claims",
            "wave12-provider-readiness-gate.v1",
            "readiness_state",
        ),
    ),
    Anchor(
        "development/latest-dev-docs/automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/runtime_smoke_results.json",
        (
            "\"status\": \"passed\"",
            "\"keyword\"",
            "\"vector\"",
            "\"hybrid\"",
        ),
    ),
    Anchor(
        "development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22/benchmark_quality_results.json",
        (
            "\"status\": \"passed\"",
            "semantic_embedding_quality_not_proven",
            "global_vector_contract_not_closed",
        ),
    ),
    Anchor(
        "development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22/contract_summary.json",
        (
            "\"contract_version\": \"wave10-vectorization-quality-gate.v1\"",
            "\"status\": \"passed\"",
            "local_index_fallback_contract",
        ),
    ),
    Anchor(
        "development/latest-dev-docs/automation-runs/wave12-provider-readiness/2026-05-22/provider_readiness_summary.json",
        (
            "\"contract_version\": \"wave12-provider-readiness-gate.v1\"",
            "\"readiness_state\": \"partial\"",
            "unsupported_claims",
        ),
    ),
]

EVIDENCE_REQUIRED_TEXT = (
    "status: partial; drift gate advanced",
    "missing_current_repo_anchor",
    "current bounded gate",
    "No top-level MERGED_OVERVIEW.md edits",
    "semantic_embedding_quality_not_proven",
    "semantic_embedding_quality_not_closed",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_required_text(path: Path, tokens: tuple[str, ...], failures: list[str]) -> None:
    if not path.is_file():
        failures.append(f"missing file: {display(path)}")
        return
    text = read_text(path)
    for token in tokens:
        if token not in text:
            failures.append(f"{display(path)} missing required text: {token}")


def display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    failures: list[str] = []

    if not LEGACY_DOC.is_file():
        failures.append(f"missing legacy topic doc: {display(LEGACY_DOC)}")
        legacy_text = ""
    else:
        legacy_text = read_text(LEGACY_DOC)

    for old_anchor in OLD_RAG_ANCHORS:
        if old_anchor not in legacy_text:
            failures.append(f"legacy doc no longer records old anchor: {old_anchor}")
        if (REPO_ROOT / old_anchor).exists():
            failures.append(f"old anchor unexpectedly exists and needs remapping review: {old_anchor}")

    for anchor in CURRENT_ANCHORS:
        check_required_text(REPO_ROOT / anchor.path, anchor.required_text, failures)

    check_required_text(EVIDENCE_DOC, EVIDENCE_REQUIRED_TEXT, failures)
    if EVIDENCE_DOC.is_file():
        evidence_text = read_text(EVIDENCE_DOC)
        for anchor in CURRENT_ANCHORS:
            if anchor.path not in evidence_text:
                failures.append(f"evidence doc does not cite current anchor: {anchor.path}")

    if failures:
        for failure in failures:
            print(f"FAIL current_dev_merged_overview_drift_gate: {failure}")
        return 1

    print(
        "OK current_dev_merged_overview_drift_gate=passed "
        f"old_missing={len(OLD_RAG_ANCHORS)} current_anchors={len(CURRENT_ANCHORS)} "
        f"evidence_doc={display(EVIDENCE_DOC)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
