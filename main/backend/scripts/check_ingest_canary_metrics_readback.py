#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ingest.canary_metrics_readback import CONTRACT_VERSION  # noqa: E402
from app.services.ingest.canary_metrics_readback import run_canary_metrics_readback_gate  # noqa: E402
from app.services.ingest.frontdoor_ingress import build_frontdoor_ingress_envelope  # noqa: E402
from app.services.ingest.postprocess_frontdoor import run_postprocess_frontdoor  # noqa: E402


TOPIC_DOCS = [
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-ingest-platformization-assessment/"
        "05_wave17-ingest-canary-metrics-readback-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-single-url-first-ingest-allocation-plan/"
        "06_wave17-single-url-canary-metrics-readback-2026-05-22.md"
    ),
    Path(
        "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
        "2026-03-02-meaningful-ingest-guardrails-plan/"
        "06_wave17-meaningful-ingest-canary-metrics-readback-2026-05-22.md"
    ),
]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


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


def run_check(*, record_path: Path | None = None) -> dict[str, Any]:
    token_results = [
        _token_check(
            REPO_ROOT / "main/backend/app/services/ingest/canary_metrics_readback.py",
            (
                "CONTRACT_VERSION",
                "build_canary_metrics_readback_record",
                "run_canary_metrics_readback_gate",
                "live_production_canary_claim",
                "metric_24h_live_readback_claim",
            ),
        ),
        _token_check(
            REPO_ROOT / "main/backend/scripts/check_ingest_canary_metrics_readback.py",
            (
                "run_canary_metrics_readback_gate",
                "write_performed",
                "readback_performed",
            ),
        ),
    ]
    for doc in TOPIC_DOCS:
        token_results.append(
            _token_check(
                REPO_ROOT / doc,
                (
                    "Wave17 Ingest Canary Metrics Readback",
                    "contract_version: ingest.canary_metrics_readback.v1",
                    "deterministic_readback: true",
                    "live_production_canary_claim: false",
                    "metric_24h_live_readback_claim: false",
                    "closure_claim: false",
                ),
            )
        )

    if record_path is None:
        with tempfile.TemporaryDirectory(prefix="ingest-canary-metrics-readback-") as tmp_dir:
            gate = run_canary_metrics_readback_gate(handoff=_build_demo_handoff(), path=Path(tmp_dir) / "snapshot.json")
    else:
        gate = run_canary_metrics_readback_gate(handoff=_build_demo_handoff(), path=record_path)

    validation = gate["validation"]
    runtime_results = [
        {
            "name": "write_read_validate_deterministic_metrics_snapshot",
            "passed": gate["write_performed"] is True and gate["readback_performed"] is True and validation["passed"] is True,
            "evidence": {
                "record_path": gate["record_path"],
                "snapshot_digest": validation["snapshot_digest"],
            },
        },
        {
            "name": "live_canary_and_24h_readback_claims_stay_open",
            "passed": gate["readback_record"]["live_production_canary_claim"] is False
            and gate["readback_record"]["metric_24h_live_readback_claim"] is False
            and gate["readback_record"]["closure_claim"] is False,
            "evidence": {
                "live_production_canary_claim": gate["readback_record"]["live_production_canary_claim"],
                "metric_24h_live_readback_claim": gate["readback_record"]["metric_24h_live_readback_claim"],
                "closure_claim": gate["readback_record"]["closure_claim"],
            },
        },
    ]
    passed = all(item["passed"] for item in token_results) and all(item["passed"] for item in runtime_results)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if passed else "failed",
        "topic_docs": [str(path) for path in TOPIC_DOCS],
        "token_results": token_results,
        "runtime_results": runtime_results,
        "gate": gate,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check deterministic ingest canary metrics readback")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    parser.add_argument("--write-record", type=Path, default=None, help="write the deterministic readback record to this path")
    args = parser.parse_args(argv)

    result = run_check(record_path=args.write_record)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        validation = result["gate"]["validation"]
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"write_performed={str(result['gate']['write_performed']).lower()} "
            f"readback_performed={str(result['gate']['readback_performed']).lower()} "
            f"validated={str(validation['passed']).lower()} "
            f"live_production_canary_claim=false metric_24h_live_readback_claim=false closure_claim=false"
        )
        if result["status"] != "passed":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
