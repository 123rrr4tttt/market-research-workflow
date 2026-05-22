#!/usr/bin/env python3
"""Wave19 deterministic vectorization provider manifest readback gate.

This checker turns the remaining provider capability boundary into a manifest
that downstream OSS-node and global-vectorization docs can read back. It only
uses repo-controlled artifacts and does not probe live providers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22"
WAVE14_PROVIDER_CAPABILITY = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/wave14-vectorization-provider-capability/2026-05-22/provider_capability_summary.json"
)
WAVE18_HYBRID_READBACK = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/wave18-vectorization-hybrid-readback/2026-05-22/hybrid_readback_contract.json"
)

TARGET_TOPICS = [
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-01-open-source-platform-integration",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-05-14-global-vectorization-general-foundation",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-05-oss-node-platform-io-plan",
]
LOCAL_INDEX_MODES = ["keyword", "vector", "hybrid"]
MODE_CAPABILITY_FLAGS = {
    "keyword": {
        "keyword": True,
        "vector": False,
        "hybrid": False,
    },
    "vector": {
        "keyword": False,
        "vector": True,
        "hybrid": False,
    },
    "hybrid": {
        "keyword": True,
        "vector": True,
        "hybrid": True,
    },
}
REQUIRED_TRACE_COMPONENTS = {
    "keyword": ["keyword_score"],
    "vector": ["vector_score"],
    "hybrid": ["keyword_score", "vector_score", "hybrid_score"],
}
REQUIRED_EXTERNAL_GAPS = {
    "external_embedding_provider_live_not_verified",
    "provider_auto_promotion_not_allowed",
    "local_open_search_live_quality_not_sealed",
    "semantic_embedding_quality_not_proven",
    "oss_node_platform_io_sla_not_closed",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_artifact(path: Path, *, label: str, expected_version: str) -> tuple[dict[str, Any], dict[str, Any]]:
    row: dict[str, Any] = {
        "label": label,
        "path": display_path(path),
        "status": "running",
        "failures": [],
    }
    if not path.exists():
        row["status"] = "missing"
        row["failures"].append(f"{label} artifact missing: {display_path(path)}")
        return {}, row
    try:
        data = load_json(path)
    except json.JSONDecodeError as exc:
        row["status"] = "failed"
        row["failures"].append(f"{label} artifact is not valid JSON: {exc}")
        return {}, row

    failures: list[str] = []
    if data.get("contract_version") != expected_version:
        failures.append(f"{label} contract_version expected {expected_version!r}, got {data.get('contract_version')!r}")
    if data.get("status") != "passed":
        failures.append(f"{label} status expected 'passed', got {data.get('status')!r}")
    if data.get("closure_claim_allowed") is not False:
        failures.append(f"{label} closure_claim_allowed must remain false")

    row.update(
        {
            "status": "passed" if not failures else "failed",
            "contract_version": data.get("contract_version"),
            "input_status": data.get("status"),
            "capability_state": data.get("capability_state"),
            "closure_claim_allowed": data.get("closure_claim_allowed"),
            "failures": failures,
        }
    )
    return data, row


def _case_by_mode(wave18_contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(case.get("mode")): case
        for case in wave18_contract.get("mode_identity_readback", {}).get("cases", [])
        if case.get("mode") in LOCAL_INDEX_MODES
    }


def _trace_quality_for_case(mode: str, case: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    trace_rows = case.get("trace_readback") or []
    required_components = REQUIRED_TRACE_COMPONENTS[mode]
    component_coverage = {component: True for component in required_components}
    provider_live_verified_values: list[Any] = []
    semantic_claim_values: list[Any] = []

    if case.get("failures"):
        failures.append(f"{mode}: source readback case has failures: {case.get('failures')!r}")
    if not trace_rows:
        failures.append(f"{mode}: trace_readback rows missing")

    for row in trace_rows:
        chunk_id = row.get("chunk_id")
        if row.get("retrieval_mode") != mode:
            failures.append(f"{mode}:{chunk_id}: retrieval_mode expected {mode!r}, got {row.get('retrieval_mode')!r}")
        trace = row.get("trace") or {}
        if trace.get("requested_mode") != mode or trace.get("executed_mode") != mode:
            failures.append(f"{mode}:{chunk_id}: requested/executed mode mismatch")
        quality_trace = trace.get("quality_trace") or {}
        components = quality_trace.get("score_components") or {}
        for component in required_components:
            if components.get(component) is None:
                component_coverage[component] = False
                failures.append(f"{mode}:{chunk_id}: quality component {component!r} missing")
        provider_live_verified_values.append(quality_trace.get("provider_live_verified"))
        semantic_claim_values.append(quality_trace.get("semantic_quality_claim_allowed"))
        if quality_trace.get("provider_live_verified") is not False:
            failures.append(f"{mode}:{chunk_id}: provider_live_verified must be false")
        if quality_trace.get("semantic_quality_claim_allowed") is not False:
            failures.append(f"{mode}:{chunk_id}: semantic_quality_claim_allowed must be false")
        readback = trace.get("readback") or {}
        if readback.get("chunk_id") != chunk_id:
            failures.append(f"{mode}:{chunk_id}: readback chunk_id mismatch")
        if readback.get("retrieval_mode") != mode:
            failures.append(f"{mode}:{chunk_id}: readback retrieval_mode expected {mode!r}")

    return (
        {
            "status": "passed" if not failures else "failed",
            "trace_row_count": len(trace_rows),
            "required_components": required_components,
            "component_coverage": component_coverage,
            "provider_live_verified": any(value is True for value in provider_live_verified_values),
            "provider_live_verified_all_false": all(value is False for value in provider_live_verified_values),
            "semantic_quality_claim_allowed": any(value is True for value in semantic_claim_values),
            "semantic_quality_claims_all_false": all(value is False for value in semantic_claim_values),
            "source_case_id": case.get("case_id"),
            "source_chunk_order": case.get("chunk_order") or [],
        },
        failures,
    )


def _fallback_for_mode(mode: str, capability_row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    fallback_visible = capability_row.get("fallback_visible") is True
    fallback_reason = capability_row.get("fallback_reason")
    fallback_mode = "none" if mode == "keyword" else "keyword"
    if not fallback_visible:
        failures.append(f"{mode}: fallback visibility must be true")
    if mode == "keyword" and fallback_reason is not None:
        failures.append(f"{mode}: keyword fallback_reason must be null")
    if mode in {"vector", "hybrid"} and fallback_reason != "RuntimeError":
        failures.append(f"{mode}: fallback_reason expected 'RuntimeError', got {fallback_reason!r}")
    return (
        {
            "fallback_visible": fallback_visible,
            "fallback_mode": fallback_mode,
            "fallback_reason": fallback_reason,
            "current_live_probe_status": capability_row.get("current_live_probe_status"),
            "current_live_fallback_reason": capability_row.get("current_live_fallback_reason"),
        },
        failures,
    )


def _build_mode_manifest(
    *,
    wave14_contract: dict[str, Any],
    wave18_contract: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    failures: list[str] = []
    capability_modes = wave14_contract.get("local_capability", {}).get("modes", {}) or {}
    readback_cases = _case_by_mode(wave18_contract)

    manifest_rows: list[dict[str, Any]] = []
    for mode in LOCAL_INDEX_MODES:
        capability_row = capability_modes.get(mode) or {}
        case = readback_cases.get(mode) or {}
        if not capability_row:
            failures.append(f"{mode}: Wave14 capability row missing")
        if not case:
            failures.append(f"{mode}: Wave18 readback case missing")

        fallback, fallback_failures = _fallback_for_mode(mode, capability_row)
        trace_quality, trace_failures = _trace_quality_for_case(mode, case)
        failures.extend(fallback_failures)
        failures.extend(trace_failures)

        manifest_rows.append(
            {
                "provider_id": f"local_index.{mode}",
                "provider_family": "local_index",
                "mode": mode,
                "capabilities": {
                    **MODE_CAPABILITY_FLAGS[mode],
                    "recorded_runtime_available": capability_row.get("recorded_runtime_available") is True,
                    "recorded_benchmark_available": capability_row.get("recorded_benchmark_available") is True,
                    "deterministic_repo_manifest_only": True,
                    "live_provider_verified": False,
                    "semantic_quality_claim_allowed": False,
                },
                "fallback": fallback,
                "trace_quality": trace_quality,
                "closure_claim_allowed": False,
            }
        )
        if capability_row.get("recorded_runtime_available") is not True:
            failures.append(f"{mode}: recorded_runtime_available must be true")
        if capability_row.get("recorded_benchmark_available") is not True:
            failures.append(f"{mode}: recorded_benchmark_available must be true")

    return manifest_rows, failures


def _build_external_boundary(wave14_contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    gap = wave14_contract.get("external_provider_gap") or {}
    gap_codes = set(str(code) for code in gap.get("gap_codes") or [])
    missing_gaps = sorted(REQUIRED_EXTERNAL_GAPS - gap_codes)
    if missing_gaps:
        failures.append(f"external gap codes missing: {missing_gaps}")
    if gap.get("external_provider_sealed") is not False:
        failures.append("external_provider_sealed must remain false")
    if gap.get("provider_auto_promotion_allowed") is not False:
        failures.append("provider_auto_promotion_allowed must remain false")

    embedding_branches = gap.get("embedding_provider_branches") or []
    for row in embedding_branches:
        if row.get("live_verified_by_gate") is not False:
            failures.append(f"embedding provider {row.get('provider')!r} live_verified_by_gate must be false")

    local_open_search = gap.get("local_open_search_providers") or {}
    for provider, row in local_open_search.items():
        if row.get("provider_auto_included") is not False:
            failures.append(f"{provider}: provider_auto_included must be false")
        if row.get("external_provider_claim_allowed") is not False:
            failures.append(f"{provider}: external_provider_claim_allowed must be false")

    return (
        {
            "status": "passed" if not failures else "failed",
            "external_provider_sealed": gap.get("external_provider_sealed") is True,
            "provider_auto_promotion_allowed": gap.get("provider_auto_promotion_allowed") is True,
            "embedding_provider_branches": embedding_branches,
            "local_open_search_providers": local_open_search,
            "gap_codes": sorted(gap_codes),
            "required_next_evidence": gap.get("required_next_evidence") or [],
        },
        failures,
    )


def build_contract(
    *,
    wave14_path: Path | None = None,
    wave18_path: Path | None = None,
) -> dict[str, Any]:
    resolved_wave14_path = wave14_path or WAVE14_PROVIDER_CAPABILITY
    resolved_wave18_path = wave18_path or WAVE18_HYBRID_READBACK
    wave14_contract, wave14_input = _load_artifact(
        resolved_wave14_path,
        label="wave14",
        expected_version="wave14-vectorization-provider-capability.v1",
    )
    wave18_contract, wave18_input = _load_artifact(
        resolved_wave18_path,
        label="wave18",
        expected_version="wave18-vectorization-hybrid-readback.v1",
    )

    target_topics = [{"path": topic, "exists": (REPO_ROOT / topic).exists()} for topic in TARGET_TOPICS]
    failures = [
        f"{name}: {failure}"
        for name, row in {"wave14": wave14_input, "wave18": wave18_input}.items()
        for failure in row.get("failures", [])
    ]
    failures.extend(f"target topic missing: {row['path']}" for row in target_topics if not row["exists"])

    provider_manifest, manifest_failures = _build_mode_manifest(
        wave14_contract=wave14_contract,
        wave18_contract=wave18_contract,
    )
    failures.extend(f"provider_manifest: {failure}" for failure in manifest_failures)
    external_boundary, external_failures = _build_external_boundary(wave14_contract)
    failures.extend(f"external_provider_boundary: {failure}" for failure in external_failures)

    return {
        "contract_version": "wave19-vectorization-provider-manifest.v1",
        "generated_by": "ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py",
        "status": "passed" if not failures else "failed",
        "manifest_state": "partial",
        "scope": "deterministic_repo_manifest_no_network_no_container_no_live_provider_closure",
        "target_topics": target_topics,
        "inputs": {
            "wave14": wave14_input,
            "wave18": wave18_input,
        },
        "provider_manifest": {
            "status": "passed" if not manifest_failures else "failed",
            "provider_family": "local_index",
            "modes": provider_manifest,
        },
        "external_provider_boundary": external_boundary,
        "oss_node_platform_io": {
            "can_consume_manifest_fields": [
                "provider_id",
                "mode",
                "capabilities.keyword",
                "capabilities.vector",
                "capabilities.hybrid",
                "fallback.fallback_mode",
                "fallback.fallback_reason",
                "trace_quality.required_components",
                "trace_quality.component_coverage",
                "trace_quality.provider_live_verified=false",
            ],
            "must_propagate_gap_fields": [
                "closure_claim_allowed=false",
                "live_provider_verified=false",
                "semantic_quality_claim_allowed=false",
                "external_provider_boundary.gap_codes",
            ],
            "closure_claim_allowed": False,
        },
        "closure_claim_allowed": False,
        "provider_live_closure_claim_allowed": False,
        "semantic_quality_claim_allowed": False,
        "gate_semantics": {
            "status_passed_means": (
                "keyword/vector/hybrid capability, fallback, and trace-quality manifest fields "
                "can be read back deterministically from repo-controlled artifacts"
            ),
            "status_passed_does_not_mean": (
                "live embedding providers, local open-search quality, provider=auto promotion, "
                "semantic relevance quality, or OSS node SLA are closed"
            ),
        },
        "remaining_gaps": [
            {
                "code": "live_provider_quality_not_closed",
                "message": "No external embedding provider, SearXNG, YaCy, or production search service is called.",
            },
            {
                "code": "semantic_embedding_quality_not_proven",
                "message": "Trace-quality manifest proves fields and deterministic scoring components, not production semantic relevance.",
            },
            {
                "code": "oss_node_platform_io_sla_not_closed",
                "message": "OSS nodes can consume the manifest but still need live node-level replay and SLA evidence.",
            },
        ],
        "assertions": [
            "provider manifest contains keyword, vector, and hybrid rows",
            "vector and hybrid rows record keyword fallback mode and RuntimeError fallback reason",
            "trace quality includes required score components and provider_live_verified=false",
            "external provider boundary remains unsealed",
            "closure_claim_allowed=false",
        ],
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "provider_manifest_readback.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest_rows = []
    for row in contract["provider_manifest"]["modes"]:
        capabilities = row["capabilities"]
        trace_quality = row["trace_quality"]
        manifest_rows.append(
            "| {mode} | {keyword} | {vector} | {hybrid} | {fallback_mode} | {fallback_reason} | {trace} | {live} |".format(
                mode=row["mode"],
                keyword=str(bool(capabilities["keyword"])).lower(),
                vector=str(bool(capabilities["vector"])).lower(),
                hybrid=str(bool(capabilities["hybrid"])).lower(),
                fallback_mode=row["fallback"]["fallback_mode"],
                fallback_reason=row["fallback"]["fallback_reason"] or "",
                trace=trace_quality["status"],
                live=str(bool(capabilities["live_provider_verified"])).lower(),
            )
        )

    gap_rows = [
        f"- `{code}`"
        for code in contract["external_provider_boundary"]["gap_codes"]
    ]

    readme = [
        "# Wave19 Vectorization Provider Manifest Readback",
        "",
        f"- status: `{contract['status']}`",
        f"- manifest_state: `{contract['manifest_state']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        f"- closure_claim_allowed: `{str(bool(contract['closure_claim_allowed'])).lower()}`",
        "",
        "## Manifest Rows",
        "",
        "| mode | keyword | vector | hybrid | fallback_mode | fallback_reason | trace_quality | live_provider_verified |",
        "|---|---:|---:|---:|---|---|---|---:|",
        *manifest_rows,
        "",
        "## External Provider Boundary",
        "",
        f"- external_provider_sealed: `{str(bool(contract['external_provider_boundary']['external_provider_sealed'])).lower()}`",
        f"- provider_auto_promotion_allowed: `{str(bool(contract['external_provider_boundary']['provider_auto_promotion_allowed'])).lower()}`",
        "",
        "## Gap Codes",
        "",
        *gap_rows,
        "",
        "## Gate Semantics",
        "",
        f"- status passed means: {contract['gate_semantics']['status_passed_means']}",
        f"- status passed does not mean: {contract['gate_semantics']['status_passed_does_not_mean']}",
        "",
        "## Rerun",
        "",
        "```bash",
        f"PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py --out-dir {display_path(out_dir)}",
        "```",
        "",
        "Full deterministic output is in `provider_manifest_readback.json`.",
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
                "manifest_state": contract["manifest_state"],
                "modes": [row["mode"] for row in contract["provider_manifest"]["modes"]],
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
