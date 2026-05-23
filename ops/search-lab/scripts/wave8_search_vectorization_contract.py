#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave8-search-vectorization-contract/2026-05-22"

SEARCH_PROVIDER_TRACE = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/search-provider-trace-artifacts/2026-05-22/search_provider_trace_contract.json"
)
SEARCH_PROVIDER_CONTAINER_REPLAY = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/search-provider-container-replay/2026-05-22/provider_trace_replay_summary.json"
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
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-05-14-global-vectorization-general-foundation",
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-05-14-local-open-search-provider-isolation",
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-01-open-source-platform-integration",
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-05-oss-node-platform-io-plan",
]
LOCAL_OPEN_SEARCH_PROVIDERS = ["searxng", "yacy"]
LOCAL_INDEX_MODES = ["keyword", "vector", "hybrid"]


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
        row["failures"].append("artifact missing")
        return row

    data = load_json(path)
    failures: list[str] = []
    if data.get("contract_version") != "search-provider-trace-artifacts.v1":
        failures.append("unexpected contract_version")
    if data.get("scope") != "offline_unit_contract_no_containers":
        failures.append("unexpected scope")
    excluded = data.get("provider_auto_policy", {}).get("excluded_local_open_search_providers")
    if excluded != LOCAL_OPEN_SEARCH_PROVIDERS:
        failures.append(f"provider_auto_policy.excluded_local_open_search_providers={excluded!r}")

    explicit_results = data.get("explicit_results") or {}
    for provider in LOCAL_OPEN_SEARCH_PROVIDERS:
        result = explicit_results.get(provider) or {}
        trace = result.get("backend_trace") or {}
        expected_route = f"explicit:{provider}"
        checks = {
            "source": provider,
            "provider_route": expected_route,
            "provider_family": "local_open_search",
            "provider_auto_included": False,
        }
        for key, expected in checks.items():
            if result.get(key) != expected:
                failures.append(f"{provider}.{key} expected {expected!r}, got {result.get(key)!r}")
        for key, expected in {
            "provider": provider,
            "provider_route": expected_route,
            "provider_family": "local_open_search",
            "auto_included": False,
        }.items():
            if trace.get(key) != expected:
                failures.append(f"{provider}.backend_trace.{key} expected {expected!r}, got {trace.get(key)!r}")

    auto_route = data.get("auto_route") or {}
    if auto_route.get("searxng_called") is not False:
        failures.append("provider=auto called searxng")
    if auto_route.get("yacy_called") is not False:
        failures.append("provider=auto called yacy")
    if auto_route.get("local_open_search_called") is not False:
        failures.append("provider=auto called local open-search provider")

    row.update(
        {
            "status": "passed" if not failures else "failed",
            "contract_version": data.get("contract_version"),
            "scope": data.get("scope"),
            "explicit_providers": LOCAL_OPEN_SEARCH_PROVIDERS,
            "auto_local_open_search_called": auto_route.get("local_open_search_called"),
            "failures": failures,
        }
    )
    return row


def check_container_replay(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": display_path(path),
        "status": "not_checked",
        "source": "preexisting_artifact_only",
        "current_container_availability_asserted": False,
        "failures": [],
    }
    if not path.exists():
        row["status"] = "missing"
        row["failures"].append("container replay artifact missing")
        return row
    data = load_json(path)
    failures: list[str] = []
    if data.get("ok") is not True:
        failures.append("container replay summary ok is not true")
    if int(data.get("failed_rows") or 0) != 0:
        failures.append("container replay has failed rows")
    if int(data.get("rows") or 0) != int(data.get("passed_rows") or -1):
        failures.append("container replay rows and passed_rows differ")
    row.update(
        {
            "status": "passed" if not failures else "failed",
            "rows": data.get("rows"),
            "passed_rows": data.get("passed_rows"),
            "failed_rows": data.get("failed_rows"),
            "docker_compose_ok_at_capture": data.get("docker_compose_ok"),
            "docker_container_count_at_capture": data.get("docker_container_count"),
            "failures": failures,
        }
    )
    return row


def check_local_index_runtime(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {"path": display_path(path), "status": "running", "failures": []}
    if not path.exists():
        row["status"] = "missing"
        row["failures"].append("runtime smoke artifact missing")
        return row
    data = load_json(path)
    failures: list[str] = []
    if data.get("status") != "passed":
        failures.append(f"runtime status={data.get('status')!r}")
    packages = data.get("packages") or {}
    if not packages.get("lancedb") or not packages.get("pyarrow"):
        failures.append("runtime packages must include lancedb and pyarrow")

    modes: dict[str, Any] = {}
    for mode in LOCAL_INDEX_MODES:
        mode_row = (data.get("modes") or {}).get(mode) or {}
        trace = mode_row.get("trace") or {}
        mode_failures: list[str] = []
        if mode_row.get("top_chunk_id") != mode_row.get("expected_chunk_id"):
            mode_failures.append("top_chunk_id does not match expected_chunk_id")
        if mode_row.get("top_source_id") != mode_row.get("expected_source_id"):
            mode_failures.append("top_source_id does not match expected_source_id")
        if mode_row.get("executed_mode") != mode or mode_row.get("retrieval_mode") != mode:
            mode_failures.append("mode did not execute without fallback")
        if trace.get("requested_mode") != mode or trace.get("executed_mode") != mode:
            mode_failures.append("trace mode fields do not match")
        if "fallback_from" in trace:
            mode_failures.append("unexpected fallback trace")
        modes[mode] = {
            "expected_chunk_id": mode_row.get("expected_chunk_id"),
            "top_chunk_id": mode_row.get("top_chunk_id"),
            "executed_mode": mode_row.get("executed_mode"),
            "retrieval_mode": mode_row.get("retrieval_mode"),
            "failures": mode_failures,
        }
        failures.extend(f"{mode}: {failure}" for failure in mode_failures)

    row.update(
        {
            "status": "passed" if not failures else "failed",
            "packages": packages,
            "modes": modes,
            "failures": failures,
        }
    )
    return row


def check_local_index_benchmark(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {"path": display_path(path), "status": "running", "failures": []}
    if not path.exists():
        row["status"] = "missing"
        row["failures"].append("benchmark artifact missing")
        return row
    data = load_json(path)
    failures: list[str] = []
    if data.get("status") != "passed":
        failures.append(f"benchmark status={data.get('status')!r}")

    ranking_modes = sorted({str(case.get("mode")) for case in data.get("ranking_cases", [])})
    if ranking_modes != sorted(LOCAL_INDEX_MODES):
        failures.append(f"ranking modes expected {sorted(LOCAL_INDEX_MODES)!r}, got {ranking_modes!r}")
    filter_modes = sorted({str(case.get("mode")) for case in data.get("filter_cases", [])})
    if filter_modes != sorted(LOCAL_INDEX_MODES):
        failures.append(f"filter modes expected {sorted(LOCAL_INDEX_MODES)!r}, got {filter_modes!r}")

    for group_name in ("ranking_cases", "filter_cases"):
        for case in data.get(group_name, []):
            if case.get("passed") is not True:
                failures.append(f"{group_name}.{case.get('case_id')} did not pass")
            for repeat in case.get("repeats", []):
                for trace in repeat.get("trace", []):
                    if trace.get("requested_mode") != case.get("mode") or trace.get("executed_mode") != case.get("mode"):
                        failures.append(f"{case.get('case_id')} repeat trace mode mismatch")
                    if "fallback_from" in trace:
                        failures.append(f"{case.get('case_id')} repeat unexpectedly fell back")

    remaining_codes = sorted({str(item.get("code")) for item in data.get("remaining_blockers", [])})
    expected_remaining = sorted(["global_vector_contract_not_closed", "semantic_embedding_quality_not_proven"])
    if remaining_codes != expected_remaining:
        failures.append(f"remaining blockers expected {expected_remaining!r}, got {remaining_codes!r}")

    row.update(
        {
            "status": "passed" if not failures else "failed",
            "packages": data.get("packages"),
            "ranking_modes": ranking_modes,
            "filter_modes": filter_modes,
            "remaining_blockers": data.get("remaining_blockers", []),
            "failures": failures,
        }
    )
    return row


def build_contract() -> dict[str, Any]:
    evidence = {
        "search_provider_trace": check_search_provider_trace(SEARCH_PROVIDER_TRACE),
        "search_provider_container_replay": check_container_replay(SEARCH_PROVIDER_CONTAINER_REPLAY),
        "local_index_runtime_smoke": check_local_index_runtime(LOCAL_INDEX_RUNTIME),
        "local_index_benchmark": check_local_index_benchmark(LOCAL_INDEX_BENCHMARK),
    }
    target_topics = [{"path": topic, "exists": (REPO_ROOT / topic).exists()} for topic in TARGET_TOPICS]
    failures = [
        f"{name}: {failure}"
        for name, row in evidence.items()
        for failure in row.get("failures", [])
    ]
    failures.extend(f"target topic missing: {row['path']}" for row in target_topics if not row["exists"])
    return {
        "contract_version": "wave8-search-vectorization-runtime-contract.v1",
        "scope": "deterministic_reuse_no_network_no_container_start",
        "generated_by": "ops/search-lab/scripts/wave8_search_vectorization_contract.py",
        "status": "passed" if not failures else "failed",
        "target_topics": target_topics,
        "assertions": [
            "explicit SearXNG and YaCy results keep provider trace fields and remain excluded from provider=auto",
            "container replay is reused only as captured evidence; this gate does not assert current container availability",
            "local_index keyword, vector, and hybrid runtime smoke executed without fallback in captured LanceDB evidence",
            "local_index benchmark proves deterministic top-k, project/source filters, and trace fields for all three modes",
            "semantic embedding quality and global vector object/schema alignment remain open blockers",
        ],
        "evidence": evidence,
        "remaining_gaps": [
            {
                "code": "current_container_availability_not_replayed",
                "message": "This deterministic gate reads recorded replay evidence and does not start or probe SearXNG/YaCy containers.",
            },
            {
                "code": "semantic_embedding_quality_not_proven",
                "message": "LanceDB benchmark uses deterministic vectors and does not prove production embedding relevance quality.",
            },
            {
                "code": "global_vector_contract_not_closed",
                "message": "Unified vector object schema, embedding model provenance, and main search evidence contract remain CURRENT_DEV work.",
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
        "# Wave8 Search / Vectorization Contract",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        "",
        "## Evidence Inputs",
        "",
        f"- search provider trace: `{evidence['search_provider_trace']['status']}`",
        f"- search provider container replay: `{evidence['search_provider_container_replay']['status']}` (captured artifact only)",
        f"- local_index runtime smoke: `{evidence['local_index_runtime_smoke']['status']}`",
        f"- local_index benchmark: `{evidence['local_index_benchmark']['status']}`",
        "",
        "## Remaining Gaps",
        "",
        *[f"- `{item['code']}`: {item['message']}" for item in contract["remaining_gaps"]],
        "",
        "## Rerun",
        "",
        "```bash",
        f"{sys.executable} ops/search-lab/scripts/wave8_search_vectorization_contract.py --out-dir {display_path(out_dir)}",
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
                "remaining_gaps": [item["code"] for item in contract["remaining_gaps"]],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
