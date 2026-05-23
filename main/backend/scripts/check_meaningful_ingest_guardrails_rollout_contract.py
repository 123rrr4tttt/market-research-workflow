#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch


CONTRACT_VERSION = "meaningful_ingest_guardrails.wave11_rollout.check.v1"
TOPIC_DOC = Path(
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
    "2026-03-02-meaningful-ingest-guardrails-plan/"
    "03_wave11-ingest-guardrails-rollout-evidence-2026-05-22.md"
)


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


def _candidate() -> dict[str, Any]:
    return {
        "uri": "https://example.com/search?q=robotics",
        "title": "Search page",
        "summary": "summary",
        "content": "Robotics market update with enough meaningful context. " * 8,
        "source_base_url": "example.com",
        "doc_type": "market",
    }


def _context(project_key: str) -> dict[str, Any]:
    return {
        "project_key": project_key,
        "source_mode": "url_execution",
        "ingestion_entrypoint": "ingest.url_pool",
        "capability_profile": {"entry_type": "search_template"},
        "content_extraction": {"page_family": "article"},
        "http_status": 200,
        "light_filter": {"filter_decision": "accept", "filter_reason_code": "ok", "filter_score": 92},
        "meaningful_gate_config": {"min_semantic_len": 20},
    }


def _runtime_checks() -> list[dict[str, Any]]:
    sys.path.insert(0, str(_backend_root()))

    from app.services.ingest.guardrail_rollout import build_ingest_guardrail_rollout_readiness
    from app.services.ingest.metrics_payload import build_metrics_payload_from_summary, new_metrics_summary, record_metrics_observation
    from app.services.ingest.postprocess_frontdoor import _evaluate_quality_frontdoor

    with (
        patch("app.services.ingest.postprocess_frontdoor.settings.ingest_enable_strict_gate", False),
        patch("app.services.ingest.guardrail_rollout.settings.ingest_enable_strict_gate", False),
        patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_rollout_mode", "canary"),
        patch("app.services.ingest.guardrail_rollout.settings.ingest_guardrail_canary_projects", "demo_proj"),
    ):
        canary_result = _evaluate_quality_frontdoor(
            document_candidate=_candidate(),
            terminal_context=_context("demo_proj"),
        )
        non_canary_result = _evaluate_quality_frontdoor(
            document_candidate=_candidate(),
            terminal_context=_context("other_proj"),
        )

    canary_gate = (canary_result.get("quality_gates") or {}).get("gate_config") or {}
    canary_rollout = canary_gate.get("guardrail_rollout") or {}
    non_canary_gate = (non_canary_result.get("quality_gates") or {}).get("gate_config") or {}
    non_canary_rollout = non_canary_gate.get("guardrail_rollout") or {}

    summary = new_metrics_summary()
    record_metrics_observation(
        summary,
        {
            "inserted_valid": 0,
            "reason_code": canary_result.get("reason_code"),
            "guardrail_rollout": canary_rollout,
        },
        fallback_adapter="source_library_frontdoor",
    )
    metrics_payload = build_metrics_payload_from_summary(summary)
    metrics_rollout = metrics_payload.get("guardrail_rollout") or {}
    readiness = build_ingest_guardrail_rollout_readiness(
        rollout_mode="canary",
        canary_projects=["demo_proj"],
        response_visibility_fields=[
            "quality_assessment.strict_gate_enabled",
            "quality_assessment.strict_gate_source",
            "quality_gates.gate_config.guardrail_rollout",
        ],
        metrics_visibility_fields=[
            "metrics_payload.guardrail_rollout.strict_enabled_samples",
            "metrics_payload.guardrail_rollout.canary_matched_samples",
            "metrics_payload.guardrail_rollout.strict_gate_source_counts",
        ],
    ).to_dict()

    return [
        {
            "name": "canary_project_enables_guardrail_without_request_strict_mode",
            "passed": canary_result.get("admission") == "reject"
            and canary_rollout.get("enable_strict_gate") is True
            and canary_rollout.get("strict_gate_source") == "settings.ingest_guardrail_rollout_mode:canary"
            and canary_rollout.get("canary_matched") is True,
            "evidence": {
                "admission": canary_result.get("admission"),
                "reason_code": canary_result.get("reason_code"),
                "guardrail_rollout": canary_rollout,
            },
        },
        {
            "name": "non_canary_project_keeps_rollout_disabled",
            "passed": non_canary_result.get("admission") == "accept"
            and non_canary_rollout.get("enable_strict_gate") is False
            and non_canary_rollout.get("strict_gate_source") == "disabled",
            "evidence": {
                "admission": non_canary_result.get("admission"),
                "guardrail_rollout": non_canary_rollout,
            },
        },
        {
            "name": "metrics_payload_exposes_canary_rollout_counts",
            "passed": metrics_rollout.get("sample_size") == 1
            and metrics_rollout.get("strict_enabled_samples") == 1
            and metrics_rollout.get("canary_matched_samples") == 1
            and metrics_rollout.get("closure_claim") is False,
            "evidence": metrics_rollout,
        },
        {
            "name": "readiness_remains_pre_live_without_closure_claim",
            "passed": readiness.get("ready_for_repo_rollout") is True
            and readiness.get("live_canary_validated") is False
            and readiness.get("closure_claim") is False
            and bool(readiness.get("remaining_live_gap")),
            "evidence": readiness,
        },
    ]


def run_check() -> dict[str, Any]:
    root = _repo_root()
    token_results = [
        _token_check(
            root,
            "main/backend/app/services/ingest/guardrail_rollout.py",
            (
                "ROLLOUT_CONTRACT_VERSION",
                "resolve_ingest_guardrail_rollout_decision",
                "build_ingest_guardrail_rollout_readiness",
                "closure_claim=False",
            ),
        ),
        _token_check(
            root,
            "main/backend/app/services/ingest/postprocess_frontdoor.py",
            (
                "guardrail_rollout",
                "guardrail_canary_matched",
                "resolve_ingest_guardrail_rollout_decision",
            ),
        ),
        _token_check(
            root,
            "main/backend/app/services/ingest/metrics_payload.py",
            (
                "guardrail_rollout",
                "strict_enabled_samples",
                "canary_matched_samples",
                "strict_gate_source_counts",
            ),
        ),
        _token_check(
            root,
            str(TOPIC_DOC),
            (
                "Wave11 Ingest Guardrails Rollout Evidence",
                "closed_narrow_rollout_contract",
                "production all-project strict enablement remains partial",
            ),
        ),
    ]
    runtime_results = _runtime_checks()
    passed = all(item["passed"] for item in token_results) and all(item["passed"] for item in runtime_results)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if passed else "failed",
        "topic_doc": str(TOPIC_DOC),
        "token_results": token_results,
        "runtime_results": runtime_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave11 meaningful ingest guardrail rollout contract")
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
