#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
SCRIPT_DIR = BACKEND_ROOT / "scripts"
for path in (BACKEND_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.ingest.canary_handoff_live import run_repo_local_production_like_handoff_canary  # noqa: E402
from app.services.ingest.canary_strict_promotion import (  # noqa: E402
    CONTRACT_VERSION,
    OPS_PROMOTION_BLOCKERS,
    PRODUCTION_24H_BLOCKERS,
    build_strict_promotion_readiness,
    validate_strict_promotion_readiness,
)
from check_ingest_canary_24h_metrics_artifact import build_24h_metrics_artifact  # noqa: E402


TOPIC_ID = "2026-03-02-meaningful-ingest-guardrails-plan"
TOPIC_DIR = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED") / TOPIC_ID
EVIDENCE_DOC = TOPIC_DIR / "12_wave55-strict-promotion-readiness-2026-05-24.md"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _token_check(path: Path, tokens: tuple[str, ...]) -> dict[str, Any]:
    full_path = REPO_ROOT / path
    exists = full_path.is_file()
    text = _read_text(full_path) if exists else ""
    missing = [token for token in tokens if token not in text]
    return {
        "path": str(path),
        "exists": exists,
        "tokens_checked": list(tokens),
        "missing_tokens": missing,
        "passed": bool(exists and not missing),
    }


def build_check(*, project_key: str | None = None) -> dict[str, Any]:
    live_result = run_repo_local_production_like_handoff_canary(project_key=project_key)
    live_evidence = live_result.get("evidence") if isinstance(live_result.get("evidence"), dict) else {}
    resolved_project_key = str(live_result.get("project_key") or project_key or "demo_proj")
    metrics_artifact = build_24h_metrics_artifact(project_key=resolved_project_key)
    readiness = build_strict_promotion_readiness(
        project_key=resolved_project_key,
        live_canary_evidence=live_evidence,
        metrics_artifact=metrics_artifact,
    )
    report = readiness.to_dict()
    validation_errors = validate_strict_promotion_readiness(report)
    remaining_ids = {
        item.get("id")
        for item in report.get("remaining_external_blockers", [])
        if isinstance(item, dict)
    }
    token_results = [
        _token_check(
            Path("main/backend/app/services/ingest/canary_strict_promotion.py"),
            (
                "CONTRACT_VERSION",
                "PRODUCTION_24H_BLOCKERS",
                "OPS_PROMOTION_BLOCKERS",
                "build_strict_promotion_readiness",
                "validate_strict_promotion_readiness",
            ),
        ),
        _token_check(
            Path("main/backend/scripts/check_ingest_canary_strict_promotion_readiness.py"),
            (
                "run_repo_local_production_like_handoff_canary",
                "build_24h_metrics_artifact",
                "build_strict_promotion_readiness",
            ),
        ),
        _token_check(
            EVIDENCE_DOC,
            (
                "Wave55 Strict Promotion Readiness",
                "repo_local_preflight_passed=true",
                "production_24h_metrics_satisfied=false",
                "strict_gate_promotion_satisfied=false",
                "closure_claim=false",
            ),
        ),
    ]
    runtime_results = [
        {
            "name": "repo_local_live_canary_validated",
            "passed": live_result.get("status") == "passed" and report.get("repo_local_live_canary_validated") is True,
            "evidence": {
                "live_result_status": live_result.get("status"),
                "project_key": live_result.get("project_key"),
                "accepted_response_status_code": live_result.get("accepted_response_status_code"),
                "rejected_response_status_code": live_result.get("rejected_response_status_code"),
            },
        },
        {
            "name": "repo_local_24h_metric_shape_validated",
            "passed": report.get("repo_local_metric_24h_shape_validated") is True
            and metrics_artifact.get("deterministic_fixture") is True,
            "evidence": {
                "deterministic_fixture": metrics_artifact.get("deterministic_fixture"),
                "window_hours": (metrics_artifact.get("window") or {}).get("window_hours"),
                "rejection_rate": (metrics_artifact.get("metrics_24h") or {}).get("rejection_rate"),
                "inserted_valid_ratio": (metrics_artifact.get("metrics_24h") or {}).get("inserted_valid_ratio"),
            },
        },
        {
            "name": "production_and_ops_blockers_remain_explicit",
            "passed": report.get("status") == "external_blocked"
            and report.get("closure_claim") is False
            and set(PRODUCTION_24H_BLOCKERS).issubset(remaining_ids)
            and set(OPS_PROMOTION_BLOCKERS).issubset(remaining_ids),
            "evidence": {
                "status": report.get("status"),
                "closure_claim": report.get("closure_claim"),
                "remaining_external_blockers": report.get("remaining_external_blockers"),
            },
        },
    ]
    passed = (
        not validation_errors
        and all(item["passed"] for item in token_results)
        and all(item["passed"] for item in runtime_results)
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if passed else "failed",
        "topic_id": TOPIC_ID,
        "topic_dir": str(TOPIC_DIR),
        "evidence_doc": str(EVIDENCE_DOC),
        "token_results": token_results,
        "runtime_results": runtime_results,
        "validation_errors": validation_errors,
        "readiness_report": report,
        "live_canary_result": {
            "contract_version": live_result.get("contract_version"),
            "status": live_result.get("status"),
            "project_key": live_result.get("project_key"),
            "validation": live_result.get("validation"),
            "cleanup": live_result.get("cleanup"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check meaningful-ingest strict-gate promotion readiness.")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    parser.add_argument("--output", type=Path, default=None, help="write full check output JSON")
    parser.add_argument("--project-key", default=None, help="optional explicit project key; defaults to an isolated temp key")
    args = parser.parse_args(argv)

    result = build_check(project_key=args.project_key)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        report = result["readiness_report"]
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"readiness_status={report['status']} "
            f"repo_local_preflight_passed={str(report['repo_local_preflight_passed']).lower()} "
            f"production_24h_metrics_satisfied={str(report['production_24h_metrics_satisfied']).lower()} "
            f"strict_gate_promotion_satisfied={str(report['strict_gate_promotion_satisfied']).lower()} "
            f"closure_claim={str(report['closure_claim']).lower()}"
        )
        if result["status"] != "passed":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
