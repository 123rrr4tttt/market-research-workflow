#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch


CONTRACT_VERSION = "ingest_canary_handoff.wave12.check.v1"
TOPIC_DOCS = [
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-ingest-platformization-assessment/"
        "03_wave12-ingest-canary-handoff-evidence-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-single-url-first-ingest-allocation-plan/"
        "04_wave12-single-url-canary-handoff-evidence-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-meaningful-ingest-guardrails-plan/"
        "04_wave12-meaningful-ingest-canary-handoff-evidence-2026-05-22.md"
    ),
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _token_check(root: Path, path: str, tokens: tuple[str, ...]) -> dict[str, Any]:
    full_path = root / path
    exists = full_path.is_file()
    text = _read_text(full_path) if exists else ""
    missing = [token for token in tokens if token not in text]
    return {
        "path": path,
        "exists": exists,
        "tokens_checked": list(tokens),
        "missing_tokens": missing,
        "passed": bool(exists and not missing),
    }


def _runtime_checks() -> list[dict[str, Any]]:
    sys.path.insert(0, str(_backend_root()))

    from app.services.ingest.canary_handoff import CANARY_HANDOFF_CONTRACT_VERSION
    from app.services.ingest.frontdoor_ingress import build_frontdoor_ingress_envelope
    from app.services.ingest.postprocess_frontdoor import run_postprocess_frontdoor

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
    handoff = data.get("canary_handoff") if isinstance(data.get("canary_handoff"), dict) else {}
    metrics = handoff.get("metrics_snapshot") if isinstance(handoff.get("metrics_snapshot"), dict) else {}
    rollout = handoff.get("rollout") if isinstance(handoff.get("rollout"), dict) else {}
    metrics_rollout = metrics.get("guardrail_rollout") if isinstance(metrics.get("guardrail_rollout"), dict) else {}
    strict_gate = handoff.get("strict_gate_state") if isinstance(handoff.get("strict_gate_state"), dict) else {}

    return [
        {
            "name": "postprocess_emits_canary_handoff_contract",
            "passed": handoff.get("contract_version") == CANARY_HANDOFF_CONTRACT_VERSION
            and handoff.get("handoff_state") == "partial_live_gap_open",
            "evidence": {
                "contract_version": handoff.get("contract_version"),
                "handoff_state": handoff.get("handoff_state"),
            },
        },
        {
            "name": "handoff_exposes_strict_gate_state_and_rollout_channel",
            "passed": strict_gate.get("state") == "strict_blocked"
            and strict_gate.get("strict_gate_enabled") is True
            and rollout.get("channel") == "canary"
            and rollout.get("canary_matched") is True,
            "evidence": {
                "strict_gate_state": strict_gate,
                "rollout": rollout,
            },
        },
        {
            "name": "handoff_metrics_snapshot_keeps_canary_counts",
            "passed": metrics.get("sample_size") == 1
            and metrics_rollout.get("strict_enabled_samples") == 1
            and metrics_rollout.get("canary_matched_samples") == 1
            and metrics_rollout.get("closure_claim") is False,
            "evidence": metrics,
        },
        {
            "name": "handoff_keeps_live_canary_gap_open",
            "passed": handoff.get("live_canary_validated") is False
            and handoff.get("closure_claim") is False
            and bool(handoff.get("remaining_live_run_gaps")),
            "evidence": {
                "live_canary_validated": handoff.get("live_canary_validated"),
                "closure_claim": handoff.get("closure_claim"),
                "remaining_live_run_gaps": handoff.get("remaining_live_run_gaps"),
            },
        },
    ]


def run_check() -> dict[str, Any]:
    root = _repo_root()
    token_results = [
        _token_check(
            root,
            "main/backend/app/services/ingest/canary_handoff.py",
            (
                "CANARY_HANDOFF_CONTRACT_VERSION",
                "strict_gate_state",
                "metrics_snapshot",
                "remaining_live_run_gaps",
            ),
        ),
        _token_check(
            root,
            "main/backend/app/services/ingest/postprocess_frontdoor.py",
            (
                "build_single_url_canary_handoff",
                "canary_handoff",
                "_attach_canary_handoff",
            ),
        ),
        _token_check(
            root,
            "main/backend/app/services/ingest/url_pool.py",
            (
                "canary_handoff",
                "source_library_frontdoor",
                "postprocess_frontdoor",
            ),
        ),
    ]
    for doc in TOPIC_DOCS:
        token_results.append(
            _token_check(
                root,
                str(doc),
                (
                    "Wave12 Ingest Canary Handoff Evidence",
                    "partial remains",
                    "live canary was not run",
                    "remaining live-run gaps",
                ),
            )
        )

    runtime_results = _runtime_checks()
    passed = all(item["passed"] for item in token_results) and all(item["passed"] for item in runtime_results)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if passed else "failed",
        "topic_docs": [str(path) for path in TOPIC_DOCS],
        "token_results": token_results,
        "runtime_results": runtime_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave12 ingest canary handoff contract")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    args = parser.parse_args(argv)

    result = run_check()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"token_checks={len(result['token_results'])} runtime_checks={len(result['runtime_results'])}"
        )
        if result["status"] != "passed":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
