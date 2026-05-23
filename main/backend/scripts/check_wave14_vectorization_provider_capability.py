#!/usr/bin/env python3
"""Wave14 deterministic vectorization provider capability gate.

This gate deliberately avoids live network probes and container startup. It
validates repo-controlled local vectorization evidence, then reports the live
and external provider gaps that prevent a closure claim.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.local_index import LOCAL_INDEX_QUERY_MODES  # noqa: E402
from app.services.local_index.adapters import is_lancedb_available  # noqa: E402
from app.services.local_index.adapters.lancedb_adapter import _deterministic_vector  # noqa: E402


DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave14-vectorization-provider-capability/2026-05-22"
WAVE10_CONTRACT = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22/contract_summary.json"
)
WAVE12_PROVIDER_READINESS = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/wave12-provider-readiness/2026-05-22/provider_readiness_summary.json"
)

TARGET_TOPICS = [
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-01-open-source-platform-integration",
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-05-oss-node-platform-io-plan",
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-05-14-global-vectorization-general-foundation",
]
LOCAL_INDEX_MODES = ["keyword", "vector", "hybrid"]
LOCAL_OPEN_SEARCH_PROVIDERS = ["searxng", "yacy"]
EMBEDDING_PROVIDER_BRANCHES = [
    {
        "provider": "openai",
        "config_required": ["OPENAI_API_KEY"],
        "live_verified_by_gate": False,
    },
    {
        "provider": "azure",
        "config_required": ["AZURE_API_BASE", "AZURE_API_KEY", "AZURE_API_VERSION", "AZURE_EMBEDDING_DEPLOYMENT"],
        "live_verified_by_gate": False,
    },
    {
        "provider": "ollama",
        "config_required": ["OLLAMA_BASE_URL"],
        "live_verified_by_gate": False,
    },
    {
        "provider": "litellm",
        "config_required": ["LITELLM_API_BASE", "LITELLM_API_KEY"],
        "live_verified_by_gate": False,
    },
]
REQUIRED_UNSUPPORTED_CLAIMS = {
    "provider_auto_quality_not_closed",
    "current_provider_live_quality_not_closed",
    "current_local_index_live_quality_not_closed",
    "semantic_embedding_quality_not_closed",
    "oss_node_platform_io_not_closed",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_artifact(path: Path, *, label: str) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {}, [f"{label} artifact missing: {display_path(path)}"]
    try:
        return load_json(path), []
    except json.JSONDecodeError as exc:
        return {}, [f"{label} artifact is not valid JSON: {exc}"]


def _wave10_mode_rows(wave10_contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    runtime = (
        wave10_contract.get("evidence", {})
        .get("local_index_runtime_smoke", {})
        .get("modes", {})
    )
    benchmark = wave10_contract.get("evidence", {}).get("local_index_benchmark_quality", {})
    ranking_modes = set(str(mode) for mode in benchmark.get("ranking_modes") or [])
    filter_modes = set(str(mode) for mode in benchmark.get("filter_modes") or [])
    fallback_cases = {
        str(case.get("requested_mode")): case
        for case in (
            wave10_contract.get("evidence", {})
            .get("local_index_fallback_contract", {})
            .get("fallback_cases", [])
        )
    }
    rows: dict[str, dict[str, Any]] = {}
    for mode in LOCAL_INDEX_MODES:
        runtime_row = runtime.get(mode) or {}
        fallback_case = fallback_cases.get(mode) or {}
        rows[mode] = {
            "mode": mode,
            "recorded_runtime_available": (
                runtime_row.get("executed_mode") == mode
                and runtime_row.get("retrieval_mode") == mode
                and not runtime_row.get("failures")
            ),
            "recorded_benchmark_available": (
                mode in ranking_modes
                and mode in filter_modes
                and benchmark.get("threshold_status") == "passed"
            ),
            "fallback_visible": True
            if mode == "keyword"
            else (
                (fallback_case.get("trace") or {}).get("fallback_from") == mode
                and (fallback_case.get("trace") or {}).get("fallback_reason") == "RuntimeError"
                and fallback_case.get("retrieval_mode") == "keyword"
            ),
            "fallback_reason": None
            if mode == "keyword"
            else (fallback_case.get("trace") or {}).get("fallback_reason"),
        }
    return rows


def _wave12_mode_statuses(wave12_summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        mode: row
        for mode, row in (
            wave12_summary.get("mode_availability", {}).get("modes", {}) or {}
        ).items()
        if mode in LOCAL_INDEX_MODES
    }


def _validate_provider_trace(wave10_contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    trace = wave10_contract.get("evidence", {}).get("search_provider_trace", {})
    providers: dict[str, Any] = {}
    if trace.get("status") != "passed":
        failures.append("wave10 search provider trace did not pass")
    if trace.get("auto_local_open_search_called") is not False:
        failures.append("provider=auto local open-search exclusion is not recorded")
    for provider in LOCAL_OPEN_SEARCH_PROVIDERS:
        providers[provider] = {
            "provider": provider,
            "provider_route": f"explicit:{provider}",
            "provider_family": "local_open_search",
            "provider_auto_included": False,
            "recorded_trace_status": trace.get("status"),
            "auto_route_excluded": trace.get("auto_local_open_search_called") is False,
        }
    return providers, failures


def _build_local_capability(
    *,
    wave10_contract: dict[str, Any],
    wave12_summary: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    exported_modes = sorted(str(mode) for mode in LOCAL_INDEX_QUERY_MODES)
    if exported_modes != sorted(LOCAL_INDEX_MODES):
        failures.append(f"LOCAL_INDEX_QUERY_MODES expected {sorted(LOCAL_INDEX_MODES)!r}, got {exported_modes!r}")

    mode_rows = _wave10_mode_rows(wave10_contract)
    live_rows = _wave12_mode_statuses(wave12_summary)
    for mode in LOCAL_INDEX_MODES:
        row = mode_rows.get(mode) or {}
        if not row.get("recorded_runtime_available"):
            failures.append(f"{mode} recorded runtime evidence is not available")
        if not row.get("recorded_benchmark_available"):
            failures.append(f"{mode} recorded benchmark evidence is not available")
        if not row.get("fallback_visible"):
            failures.append(f"{mode} fallback visibility is missing")
        live = live_rows.get(mode) or {}
        row["current_live_probe_status"] = live.get("live_probe_status", "not_recorded")
        row["current_live_fallback_reason"] = live.get("live_fallback_reason")

    probe_vector = _deterministic_vector("wave14 vectorization provider capability")
    deterministic_vector_provider = {
        "provider": "repo_deterministic_hash_vector",
        "available": bool(probe_vector) and probe_vector == _deterministic_vector("wave14 vectorization provider capability"),
        "dimensions": len(probe_vector),
        "external_dependency": False,
        "semantic_quality_claim_allowed": False,
        "production_embedding_provider": False,
    }
    if not deterministic_vector_provider["available"]:
        failures.append("deterministic local vector provider is not stable")

    current_runtime_import = {
        "lancedb": is_lancedb_available(),
        "pyarrow": importlib.util.find_spec("pyarrow") is not None,
    }
    current_runtime_import["live_runtime_ready"] = bool(
        current_runtime_import["lancedb"] and current_runtime_import["pyarrow"]
    )

    return (
        {
            "status": "passed" if not failures else "failed",
            "claim_scope": "local_repo_controlled_vectorization_contract_only",
            "mode_contract_exported": exported_modes == sorted(LOCAL_INDEX_MODES),
            "supported_modes": LOCAL_INDEX_MODES,
            "modes": mode_rows,
            "deterministic_vector_provider": deterministic_vector_provider,
            "current_runtime_import": current_runtime_import,
            "local_capability_claim_allowed": True,
            "semantic_quality_claim_allowed": False,
        },
        failures,
    )


def _build_external_provider_gap(
    *,
    wave10_contract: dict[str, Any],
    wave12_summary: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    providers, failures = _validate_provider_trace(wave10_contract)
    wave12_provider_rows = wave12_summary.get("provider_availability", {}).get("providers", {}) or {}
    for provider, row in providers.items():
        live = wave12_provider_rows.get(provider) or {}
        row["current_live_probe_status"] = live.get("live_probe_status", "not_recorded")
        row["current_live_result_count"] = live.get("live_result_count")
        row["current_live_fallback_reason"] = live.get("live_fallback_reason")
        row["external_provider_claim_allowed"] = False

    unsupported_claims = wave12_summary.get("unsupported_claims") or []
    unsupported_codes = {str(item.get("code")) for item in unsupported_claims}
    missing_claims = sorted(REQUIRED_UNSUPPORTED_CLAIMS - unsupported_codes)
    if missing_claims:
        failures.append(f"required unsupported claims missing: {missing_claims}")

    gap_codes = [
        "external_embedding_provider_live_not_verified",
        "provider_auto_promotion_not_allowed",
        "local_open_search_live_quality_not_sealed",
        "semantic_embedding_quality_not_proven",
        "oss_node_platform_io_sla_not_closed",
    ]
    return (
        {
            "external_provider_sealed": False,
            "provider_auto_promotion_allowed": False,
            "embedding_provider_branches": EMBEDDING_PROVIDER_BRANCHES,
            "local_open_search_providers": providers,
            "unsupported_claim_codes": sorted(unsupported_codes),
            "gap_codes": gap_codes,
            "required_next_evidence": [
                "live external embedding provider probes with configured credentials or local model endpoint",
                "fresh SearXNG/YaCy replay with quality, latency, timeout, and approval-gate thresholds before provider=auto promotion",
                "embedding model/version/provenance contract plus production-like semantic relevance benchmark",
                "OSS node IO replay that propagates provider live status, fallback metadata, unsupported claims, and closure_claim_allowed=false",
            ],
        },
        failures,
    )


def build_contract(
    *,
    wave10_path: Path | None = None,
    wave12_path: Path | None = None,
) -> dict[str, Any]:
    failures: list[str] = []
    resolved_wave10_path = wave10_path or WAVE10_CONTRACT
    resolved_wave12_path = wave12_path or WAVE12_PROVIDER_READINESS
    wave10_contract, artifact_failures = _load_artifact(resolved_wave10_path, label="wave10")
    failures.extend(artifact_failures)
    wave12_summary, artifact_failures = _load_artifact(resolved_wave12_path, label="wave12")
    failures.extend(artifact_failures)

    if wave10_contract and wave10_contract.get("status") != "passed":
        failures.append(f"wave10 baseline status is {wave10_contract.get('status')!r}")
    if wave12_summary and wave12_summary.get("status") != "passed":
        failures.append(f"wave12 provider readiness status is {wave12_summary.get('status')!r}")

    target_topics = [{"path": topic, "exists": (REPO_ROOT / topic).exists()} for topic in TARGET_TOPICS]
    failures.extend(f"target topic missing: {row['path']}" for row in target_topics if not row["exists"])

    local_capability, local_failures = _build_local_capability(
        wave10_contract=wave10_contract,
        wave12_summary=wave12_summary,
    )
    failures.extend(f"local_capability: {failure}" for failure in local_failures)
    external_provider_gap, external_failures = _build_external_provider_gap(
        wave10_contract=wave10_contract,
        wave12_summary=wave12_summary,
    )
    failures.extend(f"external_provider_gap: {failure}" for failure in external_failures)

    closure_claim_allowed = False
    return {
        "contract_version": "wave14-vectorization-provider-capability.v1",
        "generated_by": "main/backend/scripts/check_wave14_vectorization_provider_capability.py",
        "status": "passed" if not failures else "failed",
        "capability_state": "partial",
        "scope": "deterministic_repo_contract_no_network_no_container_start_no_external_provider_seal",
        "target_topics": target_topics,
        "inputs": {
            "wave10_contract": display_path(resolved_wave10_path),
            "wave12_provider_readiness": display_path(resolved_wave12_path),
        },
        "local_capability": local_capability,
        "external_provider_gap": external_provider_gap,
        "oss_node_platform_io": {
            "can_consume_local_fields": [
                "retrieval_mode",
                "retrieval_family",
                "trace.requested_mode",
                "trace.executed_mode",
                "trace.project_id",
                "trace.source_id",
                "trace.top_k",
            ],
            "must_propagate_gap_fields": [
                "trace.fallback_from",
                "trace.fallback_reason",
                "provider_auto_included=false",
                "unsupported_claim_codes",
                "closure_claim_allowed=false",
            ],
            "closure_claim_allowed": closure_claim_allowed,
        },
        "closure_claim_allowed": closure_claim_allowed,
        "gate_semantics": {
            "status_passed_means": "repo-controlled local capability contract, recorded evidence, and external gap reporting are valid",
            "status_passed_does_not_mean": "external embedding providers, SearXNG/YaCy live quality, provider=auto promotion, semantic quality, or OSS node SLA are sealed",
        },
        "assertions": [
            "local capability is limited to deterministic local-index mode contract and recorded evidence",
            "external provider gap is explicit and blocks closure",
            "provider=auto promotion remains disallowed for local open-search providers",
            "closure_claim_allowed=false",
        ],
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "provider_capability_summary.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    mode_rows = []
    for mode, row in contract["local_capability"]["modes"].items():
        mode_rows.append(
            "| {mode} | {runtime} | {benchmark} | {fallback} | {live} | {reason} |".format(
                mode=mode,
                runtime=str(bool(row.get("recorded_runtime_available"))).lower(),
                benchmark=str(bool(row.get("recorded_benchmark_available"))).lower(),
                fallback=str(bool(row.get("fallback_visible"))).lower(),
                live=row.get("current_live_probe_status") or "",
                reason=row.get("current_live_fallback_reason") or "",
            )
        )

    provider_rows = []
    for provider, row in contract["external_provider_gap"]["local_open_search_providers"].items():
        provider_rows.append(
            "| {provider} | {route} | {auto} | {live} | {reason} | {claim} |".format(
                provider=provider,
                route=row.get("provider_route") or "",
                auto=str(bool(row.get("provider_auto_included"))).lower(),
                live=row.get("current_live_probe_status") or "",
                reason=row.get("current_live_fallback_reason") or "",
                claim=str(bool(row.get("external_provider_claim_allowed"))).lower(),
            )
        )

    embedding_rows = []
    for row in contract["external_provider_gap"]["embedding_provider_branches"]:
        embedding_rows.append(
            "| {provider} | {config} | {live} |".format(
                provider=row["provider"],
                config=", ".join(row["config_required"]),
                live=str(bool(row["live_verified_by_gate"])).lower(),
            )
        )

    readme = [
        "# Wave14 Vectorization Provider Capability Gate",
        "",
        f"- status: `{contract['status']}`",
        f"- capability_state: `{contract['capability_state']}`",
        f"- closure_claim_allowed: `{str(bool(contract['closure_claim_allowed'])).lower()}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        "",
        "## Gate Semantics",
        "",
        f"- status passed means: {contract['gate_semantics']['status_passed_means']}",
        f"- status passed does not mean: {contract['gate_semantics']['status_passed_does_not_mean']}",
        "",
        "## Local Capability",
        "",
        "| mode | recorded_runtime | recorded_benchmark | fallback_visible | current_live_probe | current_live_gap |",
        "|---|---:|---:|---:|---|---|",
        *mode_rows,
        "",
        "## External Provider Gap",
        "",
        "| provider | route | auto_included | current_live_probe | current_live_gap | claim_allowed |",
        "|---|---|---:|---|---|---:|",
        *provider_rows,
        "",
        "## Embedding Provider Branches",
        "",
        "| provider | required config | live_verified_by_gate |",
        "|---|---|---:|",
        *embedding_rows,
        "",
        "## Gap Codes",
        "",
        *[f"- `{code}`" for code in contract["external_provider_gap"]["gap_codes"]],
        "",
        "## Rerun",
        "",
        "```bash",
        f"PYTHONPATH=main/backend python3 main/backend/scripts/check_wave14_vectorization_provider_capability.py --out-dir {display_path(out_dir)}",
        "```",
        "",
        "Full deterministic output is in `provider_capability_summary.json`.",
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
                "capability_state": contract["capability_state"],
                "local_capability": contract["local_capability"]["status"],
                "external_provider_gap": contract["external_provider_gap"]["gap_codes"],
                "closure_claim_allowed": contract["closure_claim_allowed"],
                "out_dir": display_path(out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
