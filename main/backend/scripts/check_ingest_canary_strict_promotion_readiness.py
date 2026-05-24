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
    OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER,
    OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION,
    PRODUCTION_24H_BLOCKERS,
    PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER,
    PRODUCTION_24H_METRICS_CONTRACT_VERSION,
    build_strict_promotion_readiness,
    validate_strict_promotion_readiness,
)
from check_ingest_canary_24h_metrics_artifact import build_24h_metrics_artifact  # noqa: E402


TOPIC_ID = "2026-03-02-meaningful-ingest-guardrails-plan"
TOPIC_DIR = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED") / TOPIC_ID
EVIDENCE_DOC = TOPIC_DIR / "12_wave55-strict-promotion-readiness-2026-05-24.md"
FINAL_GATE_DOC = TOPIC_DIR / "13_wave56-strict-promotion-final-gate-2026-05-24.md"


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


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _read_json_artifact(path: Path | None) -> tuple[dict[str, Any] | None, str | None, str | None]:
    if path is None:
        return None, None, None
    full_path = _resolve_path(path)
    try:
        payload = json.loads(full_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, str(full_path), f"{exc.__class__.__name__}: {exc}"
    if not isinstance(payload, dict):
        return None, str(full_path), "artifact JSON must be an object"
    return payload, str(full_path), None


def build_check(
    *,
    project_key: str | None = None,
    production_metrics_artifact_path: Path | None = None,
    ops_promotion_artifact_path: Path | None = None,
    closure_claim: bool = False,
) -> dict[str, Any]:
    live_result = run_repo_local_production_like_handoff_canary(project_key=project_key)
    live_evidence = live_result.get("evidence") if isinstance(live_result.get("evidence"), dict) else {}
    resolved_project_key = str(live_result.get("project_key") or project_key or "demo_proj")
    deterministic_metrics_artifact = build_24h_metrics_artifact(project_key=resolved_project_key)
    production_metrics_artifact, production_metrics_path, production_metrics_error = _read_json_artifact(
        production_metrics_artifact_path
    )
    ops_promotion_evidence, ops_promotion_path, ops_promotion_error = _read_json_artifact(
        ops_promotion_artifact_path
    )
    metrics_artifact = production_metrics_artifact or deterministic_metrics_artifact
    if production_metrics_artifact_path is not None and production_metrics_artifact is None:
        metrics_artifact = {
            "_artifact_load_error": production_metrics_error,
            "contract_version": None,
        }
    if ops_promotion_artifact_path is not None and ops_promotion_evidence is None:
        ops_promotion_evidence = {
            "_artifact_load_error": ops_promotion_error,
            "contract_version": None,
        }
    readiness = build_strict_promotion_readiness(
        project_key=resolved_project_key,
        live_canary_evidence=live_evidence,
        metrics_artifact=metrics_artifact,
        ops_promotion_evidence=ops_promotion_evidence,
        closure_claim=closure_claim,
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
                "PRODUCTION_24H_METRICS_CONTRACT_VERSION",
                "OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION",
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
                "--production-metrics-artifact",
                "--ops-promotion-artifact",
                "--claim-closure",
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
        _token_check(
            FINAL_GATE_DOC,
            (
                "Wave56 Strict Promotion Final Gate",
                "production_24h_metrics_artifact_optional",
                "ops_strict_gate_promotion_artifact_optional",
                "closure_claim_requires_both_artifacts",
                "closure_claim=false",
            ),
        ),
    ]
    production_blockers = set(PRODUCTION_24H_BLOCKERS) | {PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER}
    ops_blockers = set(OPS_PROMOTION_BLOCKERS) | {OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER}
    production_remaining = sorted(blocker for blocker in remaining_ids if blocker in production_blockers)
    ops_remaining = sorted(blocker for blocker in remaining_ids if blocker in ops_blockers)
    production_artifact_was_supplied = production_metrics_artifact_path is not None
    ops_artifact_was_supplied = ops_promotion_artifact_path is not None
    ops_boundary = next(
        (
            boundary
            for boundary in report.get("boundaries", [])
            if isinstance(boundary, dict) and boundary.get("name") == "ops_strict_gate_promotion"
        ),
        {},
    )
    ops_boundary_validated = ops_boundary.get("validated") is True
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
            "name": "24h_metric_shape_validated",
            "passed": report.get("repo_local_metric_24h_shape_validated") is True,
            "evidence": {
                "deterministic_fixture": metrics_artifact.get("deterministic_fixture"),
                "contract_version": metrics_artifact.get("contract_version"),
                "artifact_kind": metrics_artifact.get("artifact_kind"),
                "source_path": production_metrics_path,
                "window_hours": (metrics_artifact.get("window") or {}).get("window_hours"),
                "rejection_rate": (metrics_artifact.get("metrics_24h") or {}).get("rejection_rate"),
                "inserted_valid_ratio": (metrics_artifact.get("metrics_24h") or {}).get("inserted_valid_ratio"),
            },
        },
        {
            "name": "production_24h_metrics_gate",
            "passed": (
                report.get("production_24h_metrics_satisfied") is True
                if production_artifact_was_supplied
                else set(PRODUCTION_24H_BLOCKERS).issubset(remaining_ids)
            ),
            "evidence": {
                "artifact_supplied": production_artifact_was_supplied,
                "source_path": production_metrics_path,
                "load_error": production_metrics_error,
                "production_24h_metrics_satisfied": report.get("production_24h_metrics_satisfied"),
                "remaining_production_blockers": production_remaining,
                "required_contract_version": PRODUCTION_24H_METRICS_CONTRACT_VERSION,
            },
        },
        {
            "name": "ops_strict_gate_promotion_gate",
            "passed": (
                ops_boundary_validated
                if ops_artifact_was_supplied
                else bool(ops_remaining)
            ),
            "evidence": {
                "artifact_supplied": ops_artifact_was_supplied,
                "source_path": ops_promotion_path,
                "load_error": ops_promotion_error,
                "strict_gate_promotion_satisfied": report.get("strict_gate_promotion_satisfied"),
                "remaining_ops_blockers": ops_remaining,
                "required_contract_version": OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION,
            },
        },
        {
            "name": "final_classification_consistent",
            "passed": (
                (
                    report.get("status") == "closed"
                    and report.get("closure_claim") is True
                    and report.get("remaining_external_blockers") == []
                    and report.get("production_24h_metrics_satisfied") is True
                    and report.get("strict_gate_promotion_satisfied") is True
                )
                or (
                    not closure_claim
                    and report.get("status") == "external_blocked"
                    and report.get("closure_claim") is False
                    and bool(report.get("remaining_external_blockers"))
                )
            ),
            "evidence": {
                "closure_requested": closure_claim,
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
        "final_gate_doc": str(FINAL_GATE_DOC),
        "token_results": token_results,
        "runtime_results": runtime_results,
        "validation_errors": validation_errors,
        "readiness_report": report,
        "closure_requested": closure_claim,
        "evidence_inputs": {
            "production_metrics_artifact_path": production_metrics_path,
            "production_metrics_artifact_error": production_metrics_error,
            "ops_promotion_artifact_path": ops_promotion_path,
            "ops_promotion_artifact_error": ops_promotion_error,
        },
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
    parser.add_argument("--production-metrics-artifact", type=Path, default=None, help="optional production 24h metrics artifact")
    parser.add_argument("--ops-promotion-artifact", type=Path, default=None, help="optional ops strict-gate promotion artifact")
    parser.add_argument("--claim-closure", action="store_true", help="claim closure only when production and ops artifacts pass")
    args = parser.parse_args(argv)

    result = build_check(
        project_key=args.project_key,
        production_metrics_artifact_path=args.production_metrics_artifact,
        ops_promotion_artifact_path=args.ops_promotion_artifact,
        closure_claim=args.claim_closure,
    )
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
