#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.http.client import HttpClient  # noqa: E402
from app.services.local_index import LocalIndexChunk, LocalIndexQuery, LocalIndexService  # noqa: E402
from app.services.local_index.adapters import LanceDBLocalIndexAdapter, is_lancedb_available  # noqa: E402
from app.services.local_index.adapters.lancedb_adapter import _deterministic_vector  # noqa: E402
from app.services.search import web  # noqa: E402


DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave12-provider-readiness/2026-05-22"
WAVE10_GATE = REPO_ROOT / "ops/search-lab/scripts/wave10_vectorization_quality_gate.py"

TARGET_TOPICS = [
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-01-open-source-platform-integration",
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-05-oss-node-platform-io-plan",
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-05-14-global-vectorization-general-foundation",
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-05-14-local-open-search-provider-isolation",
]
LOCAL_INDEX_MODES = ["keyword", "vector", "hybrid"]
LOCAL_OPEN_SEARCH_PROVIDERS = ["searxng", "yacy"]
REQUIRED_PROVIDER_TRACE_FIELDS = ["provider_route", "provider_family", "provider_auto_included", "backend_trace"]
DEFAULT_PROBE_KEYWORD = "marketworkflow wave12 readiness"


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


def _load_wave10_gate_module() -> Any:
    spec = importlib.util.spec_from_file_location("wave10_vectorization_quality_gate", WAVE10_GATE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Wave10 gate module: {WAVE10_GATE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _probe_chunks() -> list[LocalIndexChunk]:
    vector_query = "wave12 vector provider readiness"
    hybrid_query = "wave12 hybrid provider readiness"
    return [
        LocalIndexChunk(
            chunk_id="wave12-keyword",
            document_id="wave12-doc-keyword",
            project_id="wave12-readiness",
            source_id="wave12-keyword-source",
            title="Wave12 keyword readiness",
            content="wave12-keyword-sentinel proves keyword readiness.",
            metadata={"expected_mode": "keyword"},
        ),
        LocalIndexChunk(
            chunk_id="wave12-vector",
            document_id="wave12-doc-vector",
            project_id="wave12-readiness",
            source_id="wave12-vector-source",
            title="Wave12 vector readiness",
            content="A local vector probe row for Wave12 readiness.",
            metadata={"expected_mode": "vector"},
            vector=_deterministic_vector(vector_query),
        ),
        LocalIndexChunk(
            chunk_id="wave12-hybrid",
            document_id="wave12-doc-hybrid",
            project_id="wave12-readiness",
            source_id="wave12-hybrid-source",
            title="Wave12 hybrid readiness",
            content=f"{hybrid_query} appears in text and vector form.",
            metadata={"expected_mode": "hybrid"},
            vector=_deterministic_vector(hybrid_query),
        ),
    ]


def probe_local_index_modes() -> dict[str, Any]:
    packages = {
        "lancedb": package_version("lancedb"),
        "pyarrow": package_version("pyarrow"),
    }
    result: dict[str, Any] = {
        "status": "running",
        "probe_type": "current_local_lancedb_temp_table_no_network",
        "packages": packages,
        "modes": {},
        "failures": [],
    }
    if not is_lancedb_available() or importlib.util.find_spec("pyarrow") is None:
        result["status"] = "blocked"
        for mode in LOCAL_INDEX_MODES:
            result["modes"][mode] = {
                "live_probe_status": "blocked",
                "fallback_reason": "missing_optional_dependency",
                "message": "lancedb and pyarrow must both be importable before live local-index mode readiness can be claimed",
            }
        return result

    db_path = tempfile.mkdtemp(prefix="mrw-wave12-provider-readiness-")
    started = time.perf_counter()
    try:
        service = LocalIndexService(LanceDBLocalIndexAdapter(db_path=db_path, table_name="chunks"))
        service.upsert_chunks(_probe_chunks())
        checks = {
            "keyword": {
                "query": "wave12-keyword-sentinel",
                "source_id": "wave12-keyword-source",
                "expected_chunk_id": "wave12-keyword",
            },
            "vector": {
                "query": "wave12 vector provider readiness",
                "source_id": "wave12-vector-source",
                "expected_chunk_id": "wave12-vector",
            },
            "hybrid": {
                "query": "wave12 hybrid provider readiness",
                "source_id": "wave12-hybrid-source",
                "expected_chunk_id": "wave12-hybrid",
            },
        }
        for mode, check in checks.items():
            mode_started = time.perf_counter()
            try:
                rows = service.search(
                    LocalIndexQuery(
                        query=check["query"],
                        project_id="wave12-readiness",
                        source_id=check["source_id"],
                        mode=mode,
                        top_k=3,
                    )
                )
                records = [row.to_dict() for row in rows]
                top = records[0] if records else {}
                trace = top.get("trace") or {}
                fallback_reason = trace.get("fallback_reason")
                live_status = "ready"
                mode_failures: list[str] = []
                if not top:
                    live_status = "empty"
                    fallback_reason = "NoResults"
                    mode_failures.append("no result returned")
                if top and top.get("chunk_id") != check["expected_chunk_id"]:
                    live_status = "failed"
                    mode_failures.append(f"top chunk expected {check['expected_chunk_id']!r}, got {top.get('chunk_id')!r}")
                if top and (top.get("retrieval_mode") != mode or trace.get("executed_mode") != mode):
                    live_status = "fallback"
                    fallback_reason = fallback_reason or "executed_mode_mismatch"
                    mode_failures.append(
                        f"expected executed mode {mode!r}, got retrieval={top.get('retrieval_mode')!r} trace={trace.get('executed_mode')!r}"
                    )
                result["modes"][mode] = {
                    "live_probe_status": live_status,
                    "latency_ms": round((time.perf_counter() - mode_started) * 1000, 2),
                    "expected_chunk_id": check["expected_chunk_id"],
                    "top_chunk_id": top.get("chunk_id"),
                    "retrieval_mode": top.get("retrieval_mode"),
                    "executed_mode": trace.get("executed_mode"),
                    "fallback_from": trace.get("fallback_from"),
                    "fallback_reason": fallback_reason,
                    "trace": trace,
                    "failures": mode_failures,
                }
                result["failures"].extend(f"{mode}: {failure}" for failure in mode_failures)
            except Exception as exc:  # noqa: BLE001 - readiness reports the actual blocker.
                result["modes"][mode] = {
                    "live_probe_status": "error",
                    "fallback_reason": exc.__class__.__name__,
                    "error": str(exc),
                    "failures": [str(exc)],
                }
                result["failures"].append(f"{mode}: {exc.__class__.__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["fallback_reason"] = exc.__class__.__name__
        result["error"] = str(exc)
        for mode in LOCAL_INDEX_MODES:
            result["modes"].setdefault(
                mode,
                {
                    "live_probe_status": "error",
                    "fallback_reason": exc.__class__.__name__,
                    "error": str(exc),
                },
            )
        return result

    result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    result["status"] = "ready" if not result["failures"] else "partial"
    return result


def _validate_provider_trace(provider: str, item: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for field in REQUIRED_PROVIDER_TRACE_FIELDS:
        if field not in item:
            failures.append(f"missing:{field}")
    expected_route = f"explicit:{provider}"
    if item.get("provider_route") != expected_route:
        failures.append(f"provider_route expected {expected_route!r}, got {item.get('provider_route')!r}")
    if item.get("provider_family") != "local_open_search":
        failures.append(f"provider_family expected 'local_open_search', got {item.get('provider_family')!r}")
    if item.get("provider_auto_included") is not False:
        failures.append("provider_auto_included must be false")
    trace = item.get("backend_trace")
    if not isinstance(trace, dict):
        failures.append("backend_trace:not_dict")
        return failures
    if trace.get("provider") != provider:
        failures.append(f"backend_trace.provider expected {provider!r}, got {trace.get('provider')!r}")
    if trace.get("provider_route") != expected_route:
        failures.append(f"backend_trace.provider_route expected {expected_route!r}, got {trace.get('provider_route')!r}")
    if trace.get("provider_family") != "local_open_search":
        failures.append("backend_trace.provider_family expected 'local_open_search'")
    if trace.get("auto_included") is not False:
        failures.append("backend_trace.auto_included must be false")
    return failures


def probe_provider(provider: str, *, timeout: float, keyword: str = DEFAULT_PROBE_KEYWORD) -> dict[str, Any]:
    if provider not in set(LOCAL_OPEN_SEARCH_PROVIDERS):
        return {
            "provider": provider,
            "live_probe_status": "unsupported",
            "fallback_reason": "unsupported_provider",
        }

    env_key = "SEARXNG_BASE_URL" if provider == "searxng" else "YACY_BASE_URL"
    default_base_url = "http://127.0.0.1:8088" if provider == "searxng" else "http://127.0.0.1:8090"
    base_url = os.getenv(env_key, default_base_url).strip() or default_base_url
    yacy_resource = os.getenv("YACY_RESOURCE_MODE", "local").strip() or "local"
    client = HttpClient(timeout=timeout, max_retries=0)
    original_client = web.default_http_client
    web.default_http_client = client
    started = time.perf_counter()
    try:
        if provider == "searxng":
            rows = web._searxng_search(keyword, base_url, 1, language="en")
        else:
            rows = web._yacy_search(keyword, base_url, 1, resource_mode=yacy_resource)
        trace_failures = _validate_provider_trace(provider, rows[0]) if rows else ["NoResults"]
        if not rows:
            live_status = "empty"
        else:
            live_status = "ready" if not trace_failures else "trace_failed"
        fallback_reason = None if rows else "NoResults"
        return {
            "provider": provider,
            "base_url": base_url,
            "keyword": keyword,
            "live_probe_status": live_status,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "result_count": len(rows),
            "sample_result": rows[0] if rows else None,
            "trace_failures": trace_failures,
            "fallback_reason": fallback_reason,
        }
    except Exception as exc:  # noqa: BLE001 - readiness reports the actual blocker.
        return {
            "provider": provider,
            "base_url": base_url,
            "keyword": keyword,
            "live_probe_status": "unavailable",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "result_count": 0,
            "fallback_reason": exc.__class__.__name__,
            "error": str(exc),
        }
    finally:
        web.default_http_client = original_client
        try:
            client._client.close()
        except Exception:
            pass


def _fallback_cases_by_mode(wave10_contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fallback = wave10_contract.get("evidence", {}).get("local_index_fallback_contract", {})
    by_mode: dict[str, dict[str, Any]] = {}
    for case in fallback.get("fallback_cases") or []:
        mode = str(case.get("requested_mode") or "")
        if mode:
            by_mode[mode] = case
    return by_mode


def build_mode_availability(wave10_contract: dict[str, Any], live_probe: dict[str, Any]) -> dict[str, Any]:
    evidence = wave10_contract.get("evidence", {})
    runtime_modes = (evidence.get("local_index_runtime_smoke") or {}).get("modes") or {}
    benchmark = evidence.get("local_index_benchmark_quality") or {}
    fallback_cases = _fallback_cases_by_mode(wave10_contract)
    mode_rows: dict[str, Any] = {}
    for mode in LOCAL_INDEX_MODES:
        runtime = runtime_modes.get(mode) or {}
        fallback_case = fallback_cases.get(mode) or {}
        live = (live_probe.get("modes") or {}).get(mode) or {"live_probe_status": "not_run"}
        recorded_runtime_available = (
            runtime.get("executed_mode") == mode
            and runtime.get("retrieval_mode") == mode
            and not runtime.get("failures")
        )
        recorded_benchmark_available = (
            mode in (benchmark.get("ranking_modes") or [])
            and mode in (benchmark.get("filter_modes") or [])
            and benchmark.get("threshold_status") == "passed"
        )
        mode_rows[mode] = {
            "mode": mode,
            "availability_state": "ready" if live.get("live_probe_status") == "ready" else "recorded_only",
            "recorded_runtime_available": recorded_runtime_available,
            "recorded_benchmark_available": recorded_benchmark_available,
            "live_probe_status": live.get("live_probe_status"),
            "live_executed_mode": live.get("executed_mode"),
            "live_fallback_from": live.get("fallback_from"),
            "live_fallback_reason": live.get("fallback_reason"),
            "fallback_contract_visible": bool(fallback_case) if mode != "keyword" else True,
            "fallback_contract_reason": (fallback_case.get("trace") or {}).get("fallback_reason"),
            "fallback_contract_executed_mode": fallback_case.get("retrieval_mode"),
            "unsupported_claim": None
            if live.get("live_probe_status") == "ready"
            else "current live mode readiness is not proven by this run",
        }
    return {
        "source": "wave10_recorded_evidence_plus_wave12_current_probe",
        "live_probe": live_probe,
        "modes": mode_rows,
    }


def build_provider_availability(
    wave10_contract: dict[str, Any],
    provider_live_probes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    provider_trace = wave10_contract.get("evidence", {}).get("search_provider_trace") or {}
    provider_rows: dict[str, Any] = {}
    for provider in LOCAL_OPEN_SEARCH_PROVIDERS:
        live = provider_live_probes.get(provider) or {"live_probe_status": "not_run"}
        provider_rows[provider] = {
            "provider": provider,
            "availability_state": "ready" if live.get("live_probe_status") == "ready" else "explicit_recorded_only",
            "provider_route": f"explicit:{provider}",
            "provider_family": "local_open_search",
            "provider_auto_included": False,
            "recorded_trace_status": provider_trace.get("status"),
            "auto_route_excluded": provider_trace.get("auto_local_open_search_called") is False,
            "live_probe_status": live.get("live_probe_status"),
            "live_result_count": live.get("result_count"),
            "live_fallback_reason": live.get("fallback_reason"),
            "live_error": live.get("error"),
            "unsupported_claim": None
            if live.get("live_probe_status") == "ready"
            else "current provider availability is not proven by this run",
        }
    return {
        "source": "search_provider_trace_contract_plus_wave12_current_probe",
        "probe_type": "backend_adapter_to_current_local_endpoint_no_container_start",
        "providers": provider_rows,
    }


def build_unsupported_claims(
    *,
    mode_availability: dict[str, Any],
    provider_availability: dict[str, Any],
) -> list[dict[str, str]]:
    provider_statuses = {
        name: row.get("live_probe_status")
        for name, row in (provider_availability.get("providers") or {}).items()
    }
    mode_statuses = {
        name: row.get("live_probe_status")
        for name, row in (mode_availability.get("modes") or {}).items()
    }
    return [
        {
            "code": "provider_auto_quality_not_closed",
            "claim": "SearXNG and YaCy can be promoted into provider=auto.",
            "reason": "The accepted contract still keeps local open-search providers explicit-only pending quality, timeout, approval-gate, and operator policy evidence.",
            "required_next_evidence": "A separate provider=auto rollout gate with live success rate, latency, timeout, and review policy thresholds.",
        },
        {
            "code": "current_provider_live_quality_not_closed",
            "claim": "Current SearXNG and YaCy live provider quality is proven.",
            "reason": f"Wave12 only records current probe status without starting containers: {provider_statuses}.",
            "required_next_evidence": "Fresh container replay with result quality assertions and zero trace failures.",
        },
        {
            "code": "current_local_index_live_quality_not_closed",
            "claim": "Current keyword/vector/hybrid local-index quality is fully proven.",
            "reason": f"Wave12 mode probes are bounded local readiness checks, not production corpus relevance tests: {mode_statuses}.",
            "required_next_evidence": "Production-like corpus benchmark with embedding provenance, ranking relevance, and fallback-rate thresholds.",
        },
        {
            "code": "semantic_embedding_quality_not_closed",
            "claim": "Deterministic vector fixtures prove production embedding semantic quality.",
            "reason": "Wave8/Wave10 fixtures prove adapter wiring, mode routing, filter behavior, and trace visibility only.",
            "required_next_evidence": "Embedding model/version contract and human-reviewable relevance benchmark.",
        },
        {
            "code": "oss_node_platform_io_not_closed",
            "claim": "OSS node platform IO can consume search/vector outputs as a live SLA-backed primitive.",
            "reason": "Node IO can consume explicit trace fields, but live provider readiness and global vector object provenance remain partial.",
            "required_next_evidence": "Node-level IO contract replay that includes provider live status, mode fallback metadata, and unsupported-claim propagation.",
        },
    ]


def build_contract(*, enable_live_probes: bool = True, probe_timeout: float = 1.5) -> dict[str, Any]:
    failures: list[str] = []
    try:
        wave10_contract = _load_wave10_gate_module().build_contract()
    except Exception as exc:  # noqa: BLE001
        wave10_contract = {
            "status": "failed",
            "failures": [f"{exc.__class__.__name__}: {exc}"],
            "evidence": {},
        }
        failures.append(f"wave10 baseline failed to load: {exc.__class__.__name__}: {exc}")

    if wave10_contract.get("status") != "passed":
        failures.extend(f"wave10 baseline: {failure}" for failure in wave10_contract.get("failures", []))

    target_topics = [{"path": topic, "exists": (REPO_ROOT / topic).exists()} for topic in TARGET_TOPICS]
    failures.extend(f"target topic missing: {row['path']}" for row in target_topics if not row["exists"])

    if enable_live_probes:
        local_index_live_probe = probe_local_index_modes()
        provider_live_probes = {
            provider: probe_provider(provider, timeout=probe_timeout)
            for provider in LOCAL_OPEN_SEARCH_PROVIDERS
        }
    else:
        local_index_live_probe = {
            "status": "not_run",
            "probe_type": "disabled",
            "modes": {mode: {"live_probe_status": "not_run"} for mode in LOCAL_INDEX_MODES},
        }
        provider_live_probes = {
            provider: {"provider": provider, "live_probe_status": "not_run", "fallback_reason": "live_probe_disabled"}
            for provider in LOCAL_OPEN_SEARCH_PROVIDERS
        }

    mode_availability = build_mode_availability(wave10_contract, local_index_live_probe)
    provider_availability = build_provider_availability(wave10_contract, provider_live_probes)
    unsupported_claims = build_unsupported_claims(
        mode_availability=mode_availability,
        provider_availability=provider_availability,
    )
    live_provider_statuses = [
        row.get("live_probe_status")
        for row in (provider_availability.get("providers") or {}).values()
    ]
    live_mode_statuses = [
        row.get("live_probe_status")
        for row in (mode_availability.get("modes") or {}).values()
    ]
    readiness_state = (
        "ready"
        if all(status == "ready" for status in live_provider_statuses + live_mode_statuses)
        and not unsupported_claims
        else "partial"
    )
    return {
        "contract_version": "wave12-provider-readiness-gate.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "ops/search-lab/scripts/wave12_provider_readiness_gate.py",
        "status": "passed" if not failures else "failed",
        "readiness_state": readiness_state,
        "scope": "bounded_repo_controlled_current_probe_no_container_start_no_auto_promotion",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "target_topics": target_topics,
        "baseline": {
            "wave10_contract_version": wave10_contract.get("contract_version"),
            "wave10_status": wave10_contract.get("status"),
            "wave10_remaining_gaps": wave10_contract.get("remaining_gaps", []),
        },
        "mode_availability": mode_availability,
        "provider_availability": provider_availability,
        "unsupported_claims": unsupported_claims,
        "gate_semantics": {
            "status_passed_means": "required recorded contracts and report shape are valid",
            "status_passed_does_not_mean": "live provider quality, provider=auto promotion, semantic embedding quality, or OSS node SLA closure",
            "live_probe_failures_are": "reported as readiness gaps unless recorded contract evidence is missing or malformed",
        },
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "provider_readiness_summary.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    mode_rows = []
    for mode, row in contract["mode_availability"]["modes"].items():
        mode_rows.append(
            "| {mode} | {recorded} | {benchmark} | {live} | {executed} | {fallback_from} | {fallback_reason} |".format(
                mode=mode,
                recorded=str(bool(row.get("recorded_runtime_available"))).lower(),
                benchmark=str(bool(row.get("recorded_benchmark_available"))).lower(),
                live=row.get("live_probe_status") or "",
                executed=row.get("live_executed_mode") or "",
                fallback_from=row.get("live_fallback_from") or "",
                fallback_reason=row.get("live_fallback_reason") or "",
            )
        )

    provider_rows = []
    for provider, row in contract["provider_availability"]["providers"].items():
        provider_rows.append(
            "| {provider} | {route} | {auto} | {live} | {count} | {fallback_reason} |".format(
                provider=provider,
                route=row.get("provider_route") or "",
                auto=str(bool(row.get("provider_auto_included"))).lower(),
                live=row.get("live_probe_status") or "",
                count=row.get("live_result_count"),
                fallback_reason=row.get("live_fallback_reason") or "",
            )
        )

    readme = [
        "# Wave12 Provider Readiness Gate",
        "",
        f"- status: `{contract['status']}`",
        f"- readiness_state: `{contract['readiness_state']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        "",
        "## Gate Semantics",
        "",
        f"- status passed means: {contract['gate_semantics']['status_passed_means']}",
        f"- status passed does not mean: {contract['gate_semantics']['status_passed_does_not_mean']}",
        f"- live probe failures are: {contract['gate_semantics']['live_probe_failures_are']}",
        "",
        "## Mode Availability",
        "",
        "| mode | recorded_runtime | recorded_benchmark | live_probe | live_executed_mode | fallback_from | fallback_reason |",
        "|---|---:|---:|---|---|---|---|",
        *mode_rows,
        "",
        "## Provider Availability",
        "",
        "| provider | route | auto_included | live_probe | live_result_count | fallback_reason |",
        "|---|---|---:|---|---:|---|",
        *provider_rows,
        "",
        "## Unsupported Claims",
        "",
        *[f"- `{item['code']}`: {item['claim']} Reason: {item['reason']}" for item in contract["unsupported_claims"]],
        "",
        "## Rerun",
        "",
        "```bash",
        f"{sys.executable} ops/search-lab/scripts/wave12_provider_readiness_gate.py --out-dir {display_path(out_dir)}",
        "```",
        "",
        "Full JSON evidence is in `provider_readiness_summary.json`.",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--probe-timeout", type=float, default=1.5)
    parser.add_argument("--skip-live-probes", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    contract = build_contract(enable_live_probes=not args.skip_live_probes, probe_timeout=args.probe_timeout)
    write_outputs(out_dir, contract)
    print(
        json.dumps(
            {
                "status": contract["status"],
                "readiness_state": contract["readiness_state"],
                "out_dir": display_path(out_dir),
                "provider_live": {
                    key: row.get("live_probe_status")
                    for key, row in contract["provider_availability"]["providers"].items()
                },
                "mode_live": {
                    key: row.get("live_probe_status")
                    for key, row in contract["mode_availability"]["modes"].items()
                },
                "unsupported_claims": [item["code"] for item in contract["unsupported_claims"]],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
