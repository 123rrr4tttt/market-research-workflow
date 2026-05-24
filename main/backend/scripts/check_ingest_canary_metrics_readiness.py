#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ingest.canary_metrics import (  # noqa: E402
    CONTRACT_VERSION,
    build_ingest_canary_metrics_readiness,
)
from app.services.ingest.frontdoor_ingress import build_frontdoor_ingress_envelope  # noqa: E402
from app.services.ingest.postprocess_frontdoor import run_postprocess_frontdoor  # noqa: E402


TOPIC_DOCS = [
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-ingest-platformization-assessment/"
        "04_wave14-ingest-canary-metrics-readiness-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-single-url-first-ingest-allocation-plan/"
        "05_wave14-single-url-canary-metrics-readiness-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-meaningful-ingest-guardrails-plan/"
        "05_wave14-meaningful-ingest-canary-metrics-readiness-2026-05-22.md"
    ),
]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"_evidence_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_evidence_read_error": "evidence JSON must be an object"}


def _token_check(path: Path, tokens: tuple[str, ...]) -> dict[str, Any]:
    exists = path.is_file()
    text = _read_text(path) if exists else ""
    missing = [token for token in tokens if token not in text]
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "exists": exists,
        "tokens_checked": list(tokens),
        "missing_tokens": missing,
        "passed": bool(exists and not missing),
    }


def _build_demo_handoff() -> dict[str, Any]:
    ingress = build_frontdoor_ingress_envelope(
        ingress_type="source_library",
        entrypoint="ingest.url_pool",
        source_mode="url_execution",
        project_key="demo_proj",
        source_ref={
            "url": "https://example.com/search?q=robotics",
            "frontdoor_route_hint": "search_shell",
            "fetch_strategy": "search_candidate_route",
        },
        collection_payload={
            "document_candidate": {
                "uri": "https://example.com/search?q=robotics",
                "title": "Search page",
                "summary": "summary",
                "content": "Robotics market update with enough meaningful context. " * 8,
                "source_base_url": "example.com",
                "doc_type": "market",
            },
            "terminal_context": {
                "project_key": "demo_proj",
                "source_mode": "url_execution",
                "ingestion_entrypoint": "ingest.url_pool",
                "capability_profile": {"source_library_collect_only": True},
                "content_extraction": {"page_family": "article"},
                "http_status": 200,
                "light_filter": {"filter_decision": "accept", "filter_reason_code": "ok", "filter_score": 92},
                "meaningful_gate_config": {"min_semantic_len": 20},
            },
        },
    )
    with (
        patch("app.services.ingest.postprocess_frontdoor.settings.ingest_enable_strict_gate", False),
        patch("app.services.ingest.guardrail_rollout.settings.ingest_enable_strict_gate", False),
        patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_rollout_mode", "canary"),
        patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_canary_projects", "demo_proj"),
    ):
        result = run_postprocess_frontdoor(ingress_envelope=ingress, run_writer=True)
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    handoff = data.get("canary_handoff")
    return handoff if isinstance(handoff, dict) else {}


def run_check(
    *,
    live_canary_evidence: dict[str, Any] | None = None,
    metric_readback_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token_results = [
        _token_check(
            REPO_ROOT / "main/backend/app/services/ingest/canary_metrics.py",
            (
                "CONTRACT_VERSION",
                "CONFIGURED_PROVIDER_CANARY_CONTRACT_VERSION",
                "CONFIGURED_PROVIDER_CANARY_EVIDENCE_FIELDS",
                "LIVE_CANARY_EVIDENCE_FIELDS",
                "METRIC_24H_EVIDENCE_FIELDS",
                "configured_provider_canary_boundary",
                "demo_proj_live_canary_open",
                "metric_24h_readback_open",
            ),
        ),
        _token_check(
            REPO_ROOT / "main/backend/scripts/check_ingest_canary_metrics_readiness.py",
            (
                "build_ingest_canary_metrics_readiness",
                "demo_proj_live_canary=",
                "metric_24h_readback=",
            ),
        ),
    ]
    for doc in TOPIC_DOCS:
        token_results.append(
            _token_check(
                REPO_ROOT / doc,
                (
                    "Wave14 Ingest Canary Metrics Readiness",
                    "demo_proj_live_canary_open",
                    "metric_24h_readback_open",
                    "closure_claim=false",
                ),
            )
        )

    report = build_ingest_canary_metrics_readiness(
        handoff=_build_demo_handoff(),
        live_canary_evidence=live_canary_evidence,
        metric_readback_evidence=metric_readback_evidence,
    )
    default_open_expected = live_canary_evidence is None and metric_readback_evidence is None
    boundary = report.configured_provider_canary_boundary
    boundary_validation = boundary.get("validation", {}) if isinstance(boundary.get("validation"), dict) else {}
    boundary_passed = boundary_validation.get("passed") is True
    runtime_results = [
        {
            "name": "deterministic_canary_metrics_ready",
            "passed": report.deterministic_metrics_ready and report.status == "ok",
            "evidence": report.metrics_snapshot,
        },
        {
            "name": "demo_proj_live_canary_gap_retained",
            "passed": (not default_open_expected) or report.demo_proj_live_canary_open,
            "evidence": {
                "demo_proj_live_canary_open": report.demo_proj_live_canary_open,
                "live_canary_validated": report.live_canary_validated,
            },
        },
        {
            "name": "configured_provider_canary_boundary_is_explicit",
            "passed": (
                boundary.get("status") == "missing_evidence"
                and boundary_validation.get("passed") is False
            )
            if default_open_expected
            else boundary_passed == report.live_canary_validated,
            "evidence": {
                "boundary_status": boundary.get("status"),
                "boundary_passed": boundary_validation.get("passed"),
            },
        },
        {
            "name": "metric_24h_readback_gap_retained",
            "passed": (not default_open_expected) or report.metric_24h_readback_open,
            "evidence": {
                "metric_24h_readback_open": report.metric_24h_readback_open,
                "metric_24h_readback_validated": report.metric_24h_readback_validated,
            },
        },
        {
            "name": "no_closure_claim",
            "passed": report.closure_claim is False,
            "evidence": {"closure_claim": report.closure_claim},
        },
    ]
    passed = all(item["passed"] for item in token_results) and all(item["passed"] for item in runtime_results)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if passed else "failed",
        "topic_docs": [str(path) for path in TOPIC_DOCS],
        "token_results": token_results,
        "runtime_results": runtime_results,
        "readiness_report": report.to_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave14 ingest canary metrics readiness boundary")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    parser.add_argument("--write-report", type=Path, default=None, help="write readiness report JSON")
    parser.add_argument("--live-canary-evidence-json", default="", help="optional live canary evidence JSON")
    parser.add_argument("--metric-readback-evidence-json", default="", help="optional 24h metric readback evidence JSON")
    args = parser.parse_args(argv)

    result = run_check(
        live_canary_evidence=_read_json(args.live_canary_evidence_json),
        metric_readback_evidence=_read_json(args.metric_readback_evidence_json),
    )
    if args.write_report is not None:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(json.dumps(result["readiness_report"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        report = result["readiness_report"]
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"deterministic_metrics_ready={str(report['deterministic_metrics_ready']).lower()} "
            f"demo_proj_live_canary={'open' if report['demo_proj_live_canary_open'] else 'validated'} "
            f"metric_24h_readback={'open' if report['metric_24h_readback_open'] else 'validated'} "
            f"closure_claim={str(report['closure_claim']).lower()} "
            f"remaining_live_gaps={len(report['remaining_live_gaps'])}"
        )
        if result["status"] != "passed":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
