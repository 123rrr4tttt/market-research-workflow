#!/usr/bin/env python3
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

from app.services.local_index import LOCAL_INDEX_QUERY_MODES, LocalIndexQuery
from app.services.local_index.adapters.lancedb_adapter import LanceDBLocalIndexAdapter


DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22"
SEARCH_PROVIDER_TRACE = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/search-provider-trace-artifacts/2026-05-22/search_provider_trace_contract.json"
)
LOCAL_INDEX_RUNTIME = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/local-index-lancedb-runtime-smoke/2026-05-22/runtime_smoke_results.json"
)
LOCAL_INDEX_BENCHMARK = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22/benchmark_quality_results.json"
)

TARGET_TOPICS = [
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-01-open-source-platform-integration",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-05-oss-node-platform-io-plan",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-global-vectorization-general-foundation",
]
LOCAL_OPEN_SEARCH_PROVIDERS = ["searxng", "yacy"]
LOCAL_INDEX_MODES = ["keyword", "vector", "hybrid"]
REQUIRED_PROVIDER_FIELDS = ["provider_route", "provider_family", "provider_auto_included", "backend_trace"]
REQUIRED_BENCHMARK_TRACE_FIELDS = [
    "adapter",
    "requested_mode",
    "executed_mode",
    "query_family",
    "project_id",
    "source_id",
    "top_k",
]
QUALITY_THRESHOLDS = {
    "min_ranking_cases": 3,
    "min_filter_cases": 3,
    "min_repeats_per_ranking_case": 3,
    "required_modes": LOCAL_INDEX_MODES,
    "max_failures": 0,
}
REQUIRED_REMAINING_BLOCKERS = ["global_vector_contract_not_closed", "semantic_embedding_quality_not_proven"]


class _FakeLanceQuery:
    def __init__(self, rows: list[dict[str, Any]], call: dict[str, Any]) -> None:
        self.rows = rows
        self.call = call
        self.limit_value: int | None = None

    def text(self, value: str) -> "_FakeLanceQuery":
        self.call["builder_text"] = value
        return self

    def vector(self, value: list[float]) -> "_FakeLanceQuery":
        self.call["builder_vector"] = value
        return self

    def where(self, predicate: str) -> "_FakeLanceQuery":
        self.call["predicate"] = predicate
        return self

    def limit(self, limit_value: int) -> "_FakeLanceQuery":
        self.limit_value = limit_value
        self.call["limit"] = limit_value
        return self

    def to_list(self) -> list[dict[str, Any]]:
        return self.rows[: self.limit_value]


class _FallbackLanceTable:
    def __init__(self, *, fail_modes: set[str]) -> None:
        self.fail_modes = set(fail_modes)
        self.calls: list[dict[str, Any]] = []
        self.rows = [
            {
                "chunk_id": "fallback-keyword-row",
                "document_id": "doc-fallback",
                "project_id": "quality-gate",
                "source_id": "fallback-source",
                "title": "Fallback proof",
                "content": "fallback keyword material row",
                "_score": 1.0,
            }
        ]

    def search(self, query: str | list[float] | None, **kwargs: Any) -> _FakeLanceQuery:
        query_type = str(kwargs.get("query_type") or "vector")
        call = {"query": query, "kwargs": dict(kwargs), "query_type": query_type}
        self.calls.append(call)
        if query_type in self.fail_modes:
            raise RuntimeError(f"{query_type} unavailable for quality gate")
        return _FakeLanceQuery(self.rows, call)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def check_search_provider_trace(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {"path": display_path(path), "status": "running", "failures": []}
    if not path.exists():
        row["status"] = "missing"
        row["failures"].append("search provider trace artifact missing")
        return row

    data = load_json(path)
    failures: list[str] = []
    if data.get("contract_version") != "search-provider-trace-artifacts.v1":
        failures.append("unexpected search provider trace contract_version")
    if data.get("scope") != "offline_unit_contract_no_containers":
        failures.append("search provider trace must remain offline/no-container")
    if data.get("required_result_fields") != REQUIRED_PROVIDER_FIELDS:
        failures.append(f"required_result_fields expected {REQUIRED_PROVIDER_FIELDS!r}, got {data.get('required_result_fields')!r}")

    excluded = (data.get("provider_auto_policy") or {}).get("excluded_local_open_search_providers")
    if excluded != LOCAL_OPEN_SEARCH_PROVIDERS:
        failures.append(f"excluded_local_open_search_providers expected {LOCAL_OPEN_SEARCH_PROVIDERS!r}, got {excluded!r}")

    explicit_results = data.get("explicit_results") or {}
    for provider in LOCAL_OPEN_SEARCH_PROVIDERS:
        result = explicit_results.get(provider) or {}
        trace = result.get("backend_trace") or {}
        for key in REQUIRED_PROVIDER_FIELDS:
            if key not in result:
                failures.append(f"{provider}.{key} missing")
        expected_route = f"explicit:{provider}"
        expected_values = {
            "source": provider,
            "provider_route": expected_route,
            "provider_family": "local_open_search",
            "provider_auto_included": False,
        }
        for key, expected in expected_values.items():
            if result.get(key) != expected:
                failures.append(f"{provider}.{key} expected {expected!r}, got {result.get(key)!r}")
        expected_trace = {
            "provider": provider,
            "provider_route": expected_route,
            "provider_family": "local_open_search",
            "auto_included": False,
        }
        for key, expected in expected_trace.items():
            if trace.get(key) != expected:
                failures.append(f"{provider}.backend_trace.{key} expected {expected!r}, got {trace.get(key)!r}")

    auto_route = data.get("auto_route") or {}
    if auto_route.get("local_open_search_called") is not False:
        failures.append("provider=auto called a local open-search provider")
    for provider in LOCAL_OPEN_SEARCH_PROVIDERS:
        if auto_route.get(f"{provider}_called") is not False:
            failures.append(f"provider=auto called {provider}")

    row.update(
        {
            "status": "passed" if not failures else "failed",
            "contract_version": data.get("contract_version"),
            "scope": data.get("scope"),
            "explicit_providers": LOCAL_OPEN_SEARCH_PROVIDERS,
            "required_result_fields": data.get("required_result_fields"),
            "auto_local_open_search_called": auto_route.get("local_open_search_called"),
            "failures": failures,
        }
    )
    return row


def check_runtime_smoke(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {"path": display_path(path), "status": "running", "failures": []}
    if not path.exists():
        row["status"] = "missing"
        row["failures"].append("local_index runtime smoke artifact missing")
        return row

    data = load_json(path)
    failures: list[str] = []
    if data.get("status") != "passed":
        failures.append(f"runtime smoke status={data.get('status')!r}")
    modes: dict[str, Any] = {}
    for mode in LOCAL_INDEX_MODES:
        mode_row = (data.get("modes") or {}).get(mode) or {}
        trace = mode_row.get("trace") or {}
        mode_failures: list[str] = []
        if mode_row.get("executed_mode") != mode:
            mode_failures.append("executed_mode mismatch")
        if mode_row.get("retrieval_mode") != mode:
            mode_failures.append("retrieval_mode mismatch")
        if mode_row.get("top_chunk_id") != mode_row.get("expected_chunk_id"):
            mode_failures.append("top_chunk_id mismatch")
        if trace.get("requested_mode") != mode or trace.get("executed_mode") != mode:
            mode_failures.append("trace mode mismatch")
        if "fallback_from" in trace or "fallback_reason" in trace:
            mode_failures.append("unexpected fallback trace in runtime smoke")
        modes[mode] = {
            "expected_chunk_id": mode_row.get("expected_chunk_id"),
            "top_chunk_id": mode_row.get("top_chunk_id"),
            "executed_mode": mode_row.get("executed_mode"),
            "retrieval_mode": mode_row.get("retrieval_mode"),
            "trace": trace,
            "failures": mode_failures,
        }
        failures.extend(f"{mode}: {failure}" for failure in mode_failures)

    row.update(
        {
            "status": "passed" if not failures else "failed",
            "packages": data.get("packages"),
            "modes": modes,
            "failures": failures,
        }
    )
    return row


def check_benchmark_quality(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": display_path(path),
        "status": "running",
        "threshold_status": "running",
        "quality_thresholds": QUALITY_THRESHOLDS,
        "failures": [],
    }
    if not path.exists():
        row["status"] = "missing"
        row["threshold_status"] = "failed"
        row["failures"].append("local_index benchmark artifact missing")
        return row

    data = load_json(path)
    failures: list[str] = []
    if data.get("status") != "passed":
        failures.append(f"benchmark status={data.get('status')!r}")

    ranking_cases = data.get("ranking_cases") or []
    filter_cases = data.get("filter_cases") or []
    if len(ranking_cases) < QUALITY_THRESHOLDS["min_ranking_cases"]:
        failures.append(f"ranking case count below threshold: {len(ranking_cases)}")
    if len(filter_cases) < QUALITY_THRESHOLDS["min_filter_cases"]:
        failures.append(f"filter case count below threshold: {len(filter_cases)}")

    ranking_modes = sorted({str(case.get("mode")) for case in ranking_cases})
    filter_modes = sorted({str(case.get("mode")) for case in filter_cases})
    expected_modes = sorted(LOCAL_INDEX_MODES)
    if ranking_modes != expected_modes:
        failures.append(f"ranking modes expected {expected_modes!r}, got {ranking_modes!r}")
    if filter_modes != expected_modes:
        failures.append(f"filter modes expected {expected_modes!r}, got {filter_modes!r}")

    for case in ranking_cases:
        case_id = str(case.get("case_id") or "unknown")
        if case.get("passed") is not True:
            failures.append(f"ranking case {case_id} did not pass")
        repeats = case.get("repeats") or []
        if len(repeats) < QUALITY_THRESHOLDS["min_repeats_per_ranking_case"]:
            failures.append(f"ranking case {case_id} repeat count below threshold: {len(repeats)}")
        if case.get("stable_order") != case.get("expected_order"):
            failures.append(f"ranking case {case_id} stable_order differs from expected_order")
        for repeat in repeats:
            if repeat.get("score_order_ok") is not True:
                failures.append(f"ranking case {case_id} repeat {repeat.get('repeat')} score_order_ok is not true")
            for trace in repeat.get("trace") or []:
                failures.extend(_validate_benchmark_trace(trace, str(case.get("mode")), case_id))

    for case in filter_cases:
        case_id = str(case.get("case_id") or "unknown")
        if case.get("passed") is not True:
            failures.append(f"filter case {case_id} did not pass")
        for result in case.get("results") or []:
            failures.extend(_validate_benchmark_trace(result.get("trace") or {}, str(case.get("mode")), case_id))
        returned = set(str(item) for item in case.get("chunk_order") or [])
        forbidden = set(str(item) for item in case.get("forbidden_chunk_ids") or [])
        leaked = sorted(returned & forbidden)
        if leaked:
            failures.append(f"filter case {case_id} returned forbidden chunks: {leaked}")

    remaining_codes = sorted(str(item.get("code")) for item in data.get("remaining_blockers") or [])
    for code in REQUIRED_REMAINING_BLOCKERS:
        if code not in remaining_codes:
            failures.append(f"remaining blocker {code!r} is missing")

    row.update(
        {
            "status": "passed" if data.get("status") == "passed" else "failed",
            "threshold_status": "passed" if not failures else "failed",
            "packages": data.get("packages"),
            "ranking_modes": ranking_modes,
            "filter_modes": filter_modes,
            "ranking_case_count": len(ranking_cases),
            "filter_case_count": len(filter_cases),
            "remaining_blockers": data.get("remaining_blockers", []),
            "failures": failures,
        }
    )
    return row


def _validate_benchmark_trace(trace: dict[str, Any], mode: str, case_id: str) -> list[str]:
    failures: list[str] = []
    for field in REQUIRED_BENCHMARK_TRACE_FIELDS:
        if field not in trace:
            failures.append(f"{case_id}: trace field {field!r} missing")
    if trace.get("requested_mode") != mode:
        failures.append(f"{case_id}: trace requested_mode expected {mode!r}, got {trace.get('requested_mode')!r}")
    if trace.get("executed_mode") != mode:
        failures.append(f"{case_id}: trace executed_mode expected {mode!r}, got {trace.get('executed_mode')!r}")
    if "fallback_from" in trace or "fallback_reason" in trace:
        failures.append(f"{case_id}: benchmark trace unexpectedly contains fallback metadata")
    return failures


def check_local_index_fallback_contract() -> dict[str, Any]:
    failures: list[str] = []
    mode_set = set(LOCAL_INDEX_QUERY_MODES)
    if mode_set != set(LOCAL_INDEX_MODES):
        failures.append(f"LOCAL_INDEX_QUERY_MODES expected {set(LOCAL_INDEX_MODES)!r}, got {mode_set!r}")

    fallback_cases = []
    for requested_mode in ("vector", "hybrid"):
        adapter = object.__new__(LanceDBLocalIndexAdapter)
        table = _FallbackLanceTable(fail_modes={requested_mode})
        adapter._table = table
        results = adapter.search(
            LocalIndexQuery(
                query="fallback keyword material",
                project_id="quality-gate",
                source_id="fallback-source",
                mode=requested_mode,
                top_k=1,
            )
        )
        result = results[0].to_dict() if results else {}
        trace = result.get("trace") or {}
        case_failures: list[str] = []
        if result.get("retrieval_mode") != "keyword":
            case_failures.append(f"retrieval_mode expected 'keyword', got {result.get('retrieval_mode')!r}")
        if trace.get("requested_mode") != requested_mode:
            case_failures.append(f"trace requested_mode expected {requested_mode!r}, got {trace.get('requested_mode')!r}")
        if trace.get("executed_mode") != "keyword":
            case_failures.append(f"trace executed_mode expected 'keyword', got {trace.get('executed_mode')!r}")
        if trace.get("fallback_from") != requested_mode:
            case_failures.append(f"trace fallback_from expected {requested_mode!r}, got {trace.get('fallback_from')!r}")
        if trace.get("fallback_reason") != "RuntimeError":
            case_failures.append(f"trace fallback_reason expected 'RuntimeError', got {trace.get('fallback_reason')!r}")
        query_types = [call["query_type"] for call in table.calls]
        if query_types != [requested_mode, "fts"]:
            case_failures.append(f"query dispatch expected {[requested_mode, 'fts']!r}, got {query_types!r}")
        fallback_cases.append(
            {
                "requested_mode": requested_mode,
                "status": "passed" if not case_failures else "failed",
                "query_types": query_types,
                "retrieval_mode": result.get("retrieval_mode"),
                "trace": trace,
                "failures": case_failures,
            }
        )
        failures.extend(f"{requested_mode}: {failure}" for failure in case_failures)

    return {
        "status": "passed" if not failures else "failed",
        "modes": LOCAL_INDEX_MODES,
        "fallback_cases": fallback_cases,
        "failures": failures,
    }


def build_contract() -> dict[str, Any]:
    evidence = {
        "search_provider_trace": check_search_provider_trace(SEARCH_PROVIDER_TRACE),
        "local_index_runtime_smoke": check_runtime_smoke(LOCAL_INDEX_RUNTIME),
        "local_index_benchmark_quality": check_benchmark_quality(LOCAL_INDEX_BENCHMARK),
        "local_index_fallback_contract": check_local_index_fallback_contract(),
    }
    target_topics = [{"path": topic, "exists": (REPO_ROOT / topic).exists()} for topic in TARGET_TOPICS]
    failures = [
        f"{name}: {failure}"
        for name, row in evidence.items()
        for failure in row.get("failures", [])
    ]
    failures.extend(f"target topic missing: {row['path']}" for row in target_topics if not row["exists"])
    return {
        "contract_version": "wave10-vectorization-quality-gate.v1",
        "scope": "deterministic_local_fixture_no_network_no_container_start",
        "generated_by": "ops/search-lab/scripts/wave10_vectorization_quality_gate.py",
        "status": "passed" if not failures else "failed",
        "target_topics": target_topics,
        "quality_thresholds": QUALITY_THRESHOLDS,
        "assertions": [
            "search provider trace keeps local open-search providers explicit-only and provider=auto excludes them",
            "local_index keyword, vector, and hybrid runtime evidence executed without fallback in captured LanceDB smoke",
            "benchmark fixture meets deterministic case/repeat thresholds for keyword, vector, and hybrid modes",
            "benchmark fixture trace includes project/source/top_k and mode fields for all result rows",
            "vector and hybrid runtime exceptions fall back to keyword with explicit fallback_from and fallback_reason metadata",
            "fixture benchmark is not treated as production embedding semantic quality evidence",
        ],
        "evidence": evidence,
        "remaining_gaps": [
            {
                "code": "current_container_availability_not_replayed",
                "message": "This gate reads recorded provider evidence and does not start or probe SearXNG/YaCy containers.",
            },
            {
                "code": "semantic_embedding_quality_not_proven",
                "message": "The benchmark fixture uses deterministic vectors and does not prove production embedding relevance quality.",
            },
            {
                "code": "global_vector_contract_not_closed",
                "message": "Unified vector object schema, embedding provenance, and main search evidence contract remain CURRENT_DEV work.",
            },
        ],
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "contract_summary.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    evidence = contract["evidence"]
    readme = [
        "# Wave10 Vectorization Quality Gate",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        "",
        "## Deterministic Assertions",
        "",
        *[f"- {item}" for item in contract["assertions"]],
        "",
        "## Evidence Inputs",
        "",
        f"- search provider trace: `{evidence['search_provider_trace']['status']}`",
        f"- local_index runtime smoke: `{evidence['local_index_runtime_smoke']['status']}`",
        f"- local_index benchmark threshold: `{evidence['local_index_benchmark_quality']['threshold_status']}`",
        f"- local_index fallback contract: `{evidence['local_index_fallback_contract']['status']}`",
        "",
        "## Quality Thresholds",
        "",
        f"- required modes: `{', '.join(QUALITY_THRESHOLDS['required_modes'])}`",
        f"- min ranking cases: `{QUALITY_THRESHOLDS['min_ranking_cases']}`",
        f"- min filter cases: `{QUALITY_THRESHOLDS['min_filter_cases']}`",
        f"- min repeats per ranking case: `{QUALITY_THRESHOLDS['min_repeats_per_ranking_case']}`",
        "",
        "## Remaining Gaps",
        "",
        *[f"- `{item['code']}`: {item['message']}" for item in contract["remaining_gaps"]],
        "",
        "## Rerun",
        "",
        "```bash",
        f"{sys.executable} ops/search-lab/scripts/wave10_vectorization_quality_gate.py --out-dir {display_path(out_dir)}",
        "```",
        "",
        "Full deterministic output is in `contract_summary.json`.",
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
                "out_dir": display_path(out_dir),
                "contract_version": contract["contract_version"],
                "quality_thresholds": contract["quality_thresholds"],
                "remaining_gaps": [item["code"] for item in contract["remaining_gaps"]],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
