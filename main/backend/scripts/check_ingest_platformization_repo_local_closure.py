#!/usr/bin/env python3
"""Check Wave29 repo-local closure for the ingest platformization CURRENT_DEV topic."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parents[0]
REPO_ROOT = BACKEND_ROOT.parents[1]
for path in (BACKEND_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.ingest.frontdoor_slo import (  # noqa: E402
    build_frontdoor_slo_payload,
    new_frontdoor_slo_summary,
    record_frontdoor_slo_observation,
)
from check_fetch_router_gap_closure import build_check as build_fetch_router_check  # noqa: E402
from check_ingest_canary_24h_metrics_artifact import run_check as run_24h_artifact_check  # noqa: E402
from check_ingest_canary_metrics_readback import run_check as run_metrics_readback_check  # noqa: E402


CONTRACT_VERSION = "ingest.platformization_repo_local_closure.wave29.v1"
TOPIC_SLUG = "2026-03-02-ingest-platformization-assessment"
TOPIC_DIR = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED") / TOPIC_SLUG
WAVE27_DOC = TOPIC_DIR / "08_wave27-ingest-canary-closure-readiness-2026-05-23.md"
PROTECTED_SHARED_INDEXES = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
)
EXTERNAL_LIVE_CONDITIONS = (
    "configured-service demo_proj canary execution",
    "production 24h rejection-rate readback",
    "production 24h inserted-valid ratio readback",
    "operations approval before all-project strict-gate promotion",
)


@dataclass(frozen=True)
class Anchor:
    path: Path
    tokens: tuple[str, ...]


BLOCKER_ANCHORS: dict[str, tuple[Anchor, ...]] = {
    "broader_fetch_router_decomposition": (
        Anchor(
            Path("main/backend/scripts/check_fetch_router_gap_closure.py"),
            ("frontdoor_fetch_router_contract", "tri_state_status_projection", "closed_narrow_runtime_contract"),
        ),
        Anchor(
            Path("main/backend/app/services/ingest/frontdoor_router_contract.py"),
            ("ingest.frontdoor_fetch_router.v1", "TRI_STATE_STATUSES", "needs_browser_runtime"),
        ),
        Anchor(
            Path("main/backend/tests/unit/test_frontdoor_fetch_router_contract_unittest.py"),
            ("test_high_js_profile_marks_needs_browser_without_public_replay", "degraded_success"),
        ),
    ),
    "shared_gate_service_rule_source_consolidation": (
        Anchor(
            Path("main/backend/app/services/ingest/meaningful_gate.py"),
            ("class GateDecision", "url_policy_check", "content_quality_check", "build_gateplus_snapshot"),
        ),
        Anchor(
            Path("main/backend/app/services/ingest/postprocess_frontdoor.py"),
            ("_frontdoor_gate_config", "url_policy_check", "content_quality_check", "strict_gate_source"),
        ),
        Anchor(
            Path("main/backend/app/services/ingest/gate_reason_codes.py"),
            ("REASON_CODE_CATALOG", "reason_category", "normalize_reason_code"),
        ),
        Anchor(
            Path("main/backend/tests/unit/test_postprocess_frontdoor_unittest.py"),
            ("test_frontdoor_quality_gate_strict_mode_forces_request_level_gate", "quality_gates"),
        ),
    ),
    "default_propagation_drift_control": (
        Anchor(
            Path("main/backend/app/services/ingest/guardrail_rollout.py"),
            ("_DEFAULT_ROLLOUT_MODE = \"canary\"", "ingest_guardrail_canary_projects", "closure_claim=False"),
        ),
        Anchor(
            Path("main/backend/app/services/ingest/metrics_payload.py"),
            ("strict_gate_source_counts", "live_canary_validated", "closure_claim"),
        ),
        Anchor(
            Path("main/backend/tests/unit/test_ingest_frontdoor_rollout_unittest.py"),
            ("test_guardrail_rollout_readiness_keeps_live_closure_open", "ready_for_repo_rollout"),
        ),
    ),
    "replay_slo_observability": (
        Anchor(
            Path("main/backend/app/services/ingest/retry_policy.py"),
            ("build_retry_observability", "retry_count_by_reason", "retryable"),
        ),
        Anchor(
            Path("main/backend/app/services/ingest/frontdoor_slo.py"),
            ("ingest.frontdoor_slo.v1", "p95_latency_ms", "success_or_degraded_rate"),
        ),
        Anchor(
            Path("main/backend/app/services/ingest/url_pool.py"),
            ("_build_frontdoor_status_projection", "_attach_frontdoor_slo", "complete_job(job_id, result=result)"),
        ),
        Anchor(
            Path("main/backend/app/api/workflow_graph.py"),
            ("/runs/{run_id}/replay", "replay_workflow_graph_run"),
        ),
    ),
    "frontend_ops_entry_closure": (
        Anchor(
            Path("main/backend/tests/integration/test_frontend_ingest_flow_smoke_unittest.py"),
            ("test_frontend_ingest_flow_contract_smoke", "/api/v1/ingest/source-library/run", "/api/v1/ingest/url/single"),
        ),
        Anchor(
            Path("main/backend/tests/integration/test_ingest_baseline_matrix_unittest.py"),
            ("test_ingest_route_inventory_contains_core_modes", "/api/v1/ingest/graph/structured-search"),
        ),
        Anchor(
            Path("main/backend/tests/integration/test_runtime_ops_error_contract_unittest.py"),
            ("test_process_retry_non_db_job_returns_structured_invalid_input", "process_retry"),
        ),
    ),
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _anchor_result(root: Path, anchor: Anchor) -> dict[str, Any]:
    path = root / anchor.path
    text = _read_text(path) if path.is_file() else ""
    missing = [token for token in anchor.tokens if token not in text]
    return {
        "path": _rel(path, root),
        "exists": path.is_file(),
        "tokens_checked": list(anchor.tokens),
        "missing_tokens": missing,
        "passed": path.is_file() and not missing,
    }


def _summarize_canary_gate(metrics_readback: Mapping[str, Any], metrics_24h: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metrics_readback_status": metrics_readback.get("status"),
        "metrics_24h_artifact_status": metrics_24h.get("status"),
        "canary_repo_local_gate_sufficient": metrics_readback.get("status") == "passed"
        and metrics_24h.get("status") == "passed",
        "live_production_canary_claim": False,
        "metric_24h_live_readback_claim": False,
        "closure_claim": False,
    }


def _slo_fixture() -> dict[str, Any]:
    summary = new_frontdoor_slo_summary()
    record_frontdoor_slo_observation(
        summary,
        {"dashboard_status": "success", "latency_ms": 80, "retryable": False, "reason_code": "ok"},
    )
    record_frontdoor_slo_observation(
        summary,
        {
            "dashboard_status": "degraded_success",
            "latency_ms": 240,
            "retryable": True,
            "reason_code": "fetch_failed",
            "retry_observability": {
                "retry_count_by_reason": {"fetch_failed": 1},
                "retry_count_by_class": {"transient": 1, "permanent": 0},
            },
        },
    )
    return build_frontdoor_slo_payload(summary)


def _fetch_router_closed(fetch_router_check: Mapping[str, Any]) -> bool:
    if fetch_router_check.get("status") != "passed":
        return False
    for topic in fetch_router_check.get("topics") or []:
        if not isinstance(topic, Mapping):
            continue
        if topic.get("topic_id") == TOPIC_SLUG:
            return topic.get("status") == "closed_narrow_runtime_contract"
    return False


def _blocker_result(
    *,
    root: Path,
    code: str,
    fetch_router_check: Mapping[str, Any],
    slo_payload: Mapping[str, Any],
) -> dict[str, Any]:
    anchors = [_anchor_result(root, anchor) for anchor in BLOCKER_ANCHORS[code]]
    dynamic_passed = True
    dynamic_evidence: dict[str, Any] = {}
    if code == "broader_fetch_router_decomposition":
        dynamic_passed = _fetch_router_closed(fetch_router_check)
        dynamic_evidence["fetch_router_gap_closure_status"] = fetch_router_check.get("status")
    if code == "replay_slo_observability":
        dynamic_passed = bool(
            slo_payload.get("contract_version") == "ingest.frontdoor_slo.v1"
            and slo_payload.get("p95_latency_ms") is not None
            and slo_payload.get("closure_claim") is False
        )
        dynamic_evidence["frontdoor_slo_fixture"] = dict(slo_payload)

    closed = all(anchor["passed"] for anchor in anchors) and dynamic_passed
    return {
        "code": code,
        "status": "closed_repo_local" if closed else "open_missing_repo_evidence",
        "closed_repo_local": closed,
        "anchors": anchors,
        "dynamic_evidence": dynamic_evidence,
    }


def validate_report(report: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version mismatch")
    if report.get("topic_slug") != TOPIC_SLUG:
        errors.append("topic_slug mismatch")
    if report.get("canary_gate", {}).get("canary_repo_local_gate_sufficient") is not True:
        errors.append("canary repo-local gate must be sufficient")
    blockers = report.get("repo_local_blockers") if isinstance(report.get("repo_local_blockers"), list) else []
    if set(item.get("code") for item in blockers if isinstance(item, Mapping)) != set(BLOCKER_ANCHORS):
        errors.append("repo-local blocker set mismatch")
    for blocker in blockers:
        if not isinstance(blocker, Mapping):
            errors.append("blocker result must be object")
            continue
        if blocker.get("closed_repo_local") is not True:
            errors.append(f"{blocker.get('code')}: blocker must be closed repo-local")
        for anchor in blocker.get("anchors") or []:
            if isinstance(anchor, Mapping) and anchor.get("passed") is not True:
                errors.append(f"{blocker.get('code')}: anchor failed: {anchor.get('path')}")
    if report.get("repo_local_blockers_open") != []:
        errors.append("repo_local_blockers_open must be empty")
    if report.get("archive_recommendation") != "external_blocked":
        errors.append("archive_recommendation must be external_blocked after repo-local blockers close")
    live_conditions = " ".join(str(item) for item in report.get("remaining_external_live_conditions") or [])
    if "canary" not in live_conditions or "24h" not in live_conditions:
        errors.append("remaining external live conditions must mention canary and 24h")
    if report.get("protected_shared_indexes_edited") is not False:
        errors.append("protected shared indexes must not be edited by this checker")
    return errors


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    root = root.resolve()
    metrics_readback = run_metrics_readback_check()
    metrics_24h = run_24h_artifact_check()
    canary_gate = _summarize_canary_gate(metrics_readback, metrics_24h)
    fetch_router_check = build_fetch_router_check(root)
    slo_payload = _slo_fixture()

    blocker_results = [
        _blocker_result(
            root=root,
            code=code,
            fetch_router_check=fetch_router_check,
            slo_payload=slo_payload,
        )
        for code in BLOCKER_ANCHORS
    ]
    open_blockers = [
        blocker["code"]
        for blocker in blocker_results
        if blocker.get("closed_repo_local") is not True
    ]
    archive_recommendation = (
        "external_blocked"
        if canary_gate["canary_repo_local_gate_sufficient"] and not open_blockers
        else "retain_current_dev"
    )
    report: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "topic_slug": TOPIC_SLUG,
        "status": "passed",
        "wave27_doc": str(WAVE27_DOC),
        "canary_gate": canary_gate,
        "repo_local_blockers": blocker_results,
        "repo_local_blockers_open": open_blockers,
        "remaining_external_live_conditions": list(EXTERNAL_LIVE_CONDITIONS),
        "archive_recommendation": archive_recommendation,
        "recommended_location": "ARCHIVE_EXTERNAL_BLOCKED" if archive_recommendation == "external_blocked" else "CURRENT_DEV",
        "migration_note": "Wave29 supervisor integration moved the directory to ARCHIVE_EXTERNAL_BLOCKED and synchronized shared indexes.",
        "protected_shared_indexes": list(PROTECTED_SHARED_INDEXES),
        "protected_shared_indexes_edited": False,
        "validation_commands": [
            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_platformization_repo_local_closure.py",
            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_platformization_repo_local_closure_unittest.py main/backend/tests/unit/test_ingest_frontdoor_slo_unittest.py",
        ],
    }
    errors = validate_report(report)
    report["validation_errors"] = errors
    report["status"] = "passed" if not errors else "failed"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave29 ingest platformization repo-local closure.")
    parser.add_argument("--json", action="store_true", help="print full JSON report")
    parser.add_argument("--output", type=Path, default=None, help="optional JSON report path")
    args = parser.parse_args(argv)

    report = build_check()
    if args.output is not None:
        output = args.output if args.output.is_absolute() else REPO_ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status'].upper()} {CONTRACT_VERSION} "
            f"topic={TOPIC_SLUG} "
            f"repo_local_blockers_open={len(report['repo_local_blockers_open'])} "
            f"archive_recommendation={report['archive_recommendation']}"
        )
        if report["status"] != "passed":
            print(json.dumps(report["validation_errors"], ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
