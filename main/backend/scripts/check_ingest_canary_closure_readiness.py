#!/usr/bin/env python3
"""Evaluate Wave27 ingest canary closure readiness for adjacent CURRENT_DEV topics."""

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

from check_ingest_canary_24h_metrics_artifact import run_check as run_24h_artifact_check  # noqa: E402
from check_ingest_canary_metrics_readback import run_check as run_metrics_readback_check  # noqa: E402


CONTRACT_VERSION = "ingest.canary_closure_readiness.v1"
CURRENT_DEV_ROOT = Path("development/latest-dev-docs/development-plans/CURRENT_DEV")
ARCHIVE_EXTERNAL_BLOCKED_ROOT = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED")
CURRENT_DEV_INDEX = CURRENT_DEV_ROOT / "INDEX.md"


@dataclass(frozen=True)
class TopicSpec:
    slug: str
    title: str
    primary_doc: Path
    decision_doc: Path
    wave17_doc: Path
    wave19_doc: Path
    decision_marker: str
    repo_local_blockers: tuple[dict[str, str], ...]
    external_live_conditions: tuple[str, ...]

    @property
    def directory(self) -> Path:
        return CURRENT_DEV_ROOT / self.slug


TOPICS = (
    TopicSpec(
        slug="2026-03-02-ingest-platformization-assessment",
        title="Ingest Platformization Assessment",
        primary_doc=Path("01_ingest-platformization-assessment-and-roadmap-2026-03-02.md"),
        decision_doc=Path("07_wave22-external-blocked-migration-decision-2026-05-22.md"),
        wave17_doc=Path("05_wave17-ingest-canary-metrics-readback-2026-05-22.md"),
        wave19_doc=Path("06_wave19-ingest-canary-24h-metrics-artifact-2026-05-22.md"),
        decision_marker="wave22_retain_current_dev_repo_local_blockers_open",
        repo_local_blockers=(
            {
                "code": "broader_fetch_router_decomposition_open",
                "source_token": "broader fetch-router decomposition",
            },
            {
                "code": "shared_gate_service_rule_source_consolidation_open",
                "source_token": "shared GateService/rule-source consolidation",
            },
            {
                "code": "default_propagation_drift_control_open",
                "source_token": "default propagation drift control",
            },
            {
                "code": "replay_slo_observability_open",
                "source_token": "replay/SLO observability",
            },
            {
                "code": "frontend_ops_entry_closure_open",
                "source_token": "frontend/ops entry closure",
            },
        ),
        external_live_conditions=(
            "demo_proj live canary execution against configured services",
            "production 24h rejection-rate readback",
            "production 24h inserted-valid ratio readback",
            "operations approval before all-project strict-gate promotion",
        ),
    ),
    TopicSpec(
        slug="2026-03-02-meaningful-ingest-guardrails-plan",
        title="Meaningful Ingest Guardrails Plan",
        primary_doc=Path("01_meaningful-ingest-guardrails-plan-2026-03-02.md"),
        decision_doc=Path("08_wave22-external-blocked-migration-decision-2026-05-22.md"),
        wave17_doc=Path("06_wave17-meaningful-ingest-canary-metrics-readback-2026-05-22.md"),
        wave19_doc=Path("07_wave19-meaningful-ingest-canary-24h-metrics-artifact-2026-05-22.md"),
        decision_marker="wave22_retain_current_dev_policy_tuning_after_live_canary",
        repo_local_blockers=(
            {
                "code": "source_policy_tuning_successor_not_split",
                "source_token": "source-policy tuning remains attached to the same topic",
            },
        ),
        external_live_conditions=(
            "live guardrail rollout canary against configured services",
            "production 24h rejection-rate readback",
            "production 24h inserted-valid ratio readback",
            "production guardrail rollout counts readback",
            "operations-owned strict-gate promotion decision",
        ),
    ),
    TopicSpec(
        slug="2026-03-02-single-url-first-ingest-allocation-plan",
        title="Single URL First Ingest Allocation Plan",
        primary_doc=Path("01_single-url-first-ingest-allocation-plan-2026-03-02.md"),
        decision_doc=Path("08_wave22-external-blocked-migration-decision-2026-05-22.md"),
        wave17_doc=Path("06_wave17-single-url-canary-metrics-readback-2026-05-22.md"),
        wave19_doc=Path("07_wave19-single-url-canary-24h-metrics-artifact-2026-05-22.md"),
        decision_marker="wave22_retain_current_dev_fetch_router_dashboard_blockers_open",
        repo_local_blockers=(
            {
                "code": "browser_crawler_first_fetch_router_coverage_open",
                "source_token": "broader browser/crawler-first fetch-router coverage",
            },
            {
                "code": "official_api_adapter_maturity_open",
                "source_token": "official API adapter maturity",
            },
            {
                "code": "frontend_dashboard_tri_state_alignment_open",
                "source_token": "frontend/dashboard tri-state alignment",
            },
        ),
        external_live_conditions=(
            "configured-service single-URL canary for demo_proj",
            "production 24h metrics from URL pool output",
            "operations-owned all-project strict-gate promotion decision",
        ),
    ),
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _token_result(path: Path, tokens: tuple[str, ...]) -> dict[str, Any]:
    text = _read_text(path)
    missing = [token for token in tokens if token not in text]
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "exists": path.is_file(),
        "tokens_checked": list(tokens),
        "missing_tokens": missing,
        "passed": path.is_file() and not missing,
    }


def _summarize_gate(result: Mapping[str, Any]) -> dict[str, Any]:
    token_results = result.get("token_results") if isinstance(result.get("token_results"), list) else []
    runtime_results = result.get("runtime_results") if isinstance(result.get("runtime_results"), list) else []
    return {
        "contract_version": result.get("contract_version"),
        "status": result.get("status"),
        "token_results_passed": sum(1 for item in token_results if isinstance(item, Mapping) and item.get("passed")),
        "token_results_total": len(token_results),
        "runtime_results": [
            {
                "name": item.get("name"),
                "passed": item.get("passed"),
                "evidence": item.get("evidence", {}),
            }
            for item in runtime_results
            if isinstance(item, Mapping)
        ],
    }


def _topic_result(
    *,
    topic: TopicSpec,
    current_index_text: str,
    canary_gate_sufficient: bool,
) -> dict[str, Any]:
    directory = REPO_ROOT / topic.directory
    archive_directory = REPO_ROOT / ARCHIVE_EXTERNAL_BLOCKED_ROOT / topic.slug
    decision_path = directory / topic.decision_doc
    decision_text = _read_text(decision_path)
    index_line = next((line for line in current_index_text.splitlines() if topic.slug in line), "")

    blocker_results = [
        {
            "code": blocker["code"],
            "source_token": blocker["source_token"],
            "present_in_decision_doc": blocker["source_token"] in decision_text,
        }
        for blocker in topic.repo_local_blockers
    ]
    documentation_checks = [
        _token_result(
            decision_path,
            (
                topic.decision_marker,
                "Wave17",
                "Wave19",
                "live_production_canary_claim=false",
                "metric_24h_live_readback_claim=false",
                "closure_claim=false",
                "Remaining Boundary",
            ),
        ),
        _token_result(
            directory / topic.wave17_doc,
            (
                "contract_version: ingest.canary_metrics_readback.v1",
                "deterministic_readback: true",
                "live_production_canary_claim: false",
                "metric_24h_live_readback_claim: false",
                "closure_claim: false",
            ),
        ),
        _token_result(
            directory / topic.wave19_doc,
            (
                "contract_version: ingest.canary_24h_metrics_artifact.v1",
                "deterministic_fixture: true",
                "window_hours: 24",
                "live_production_canary_claim: false",
                "metric_24h_live_readback_claim: false",
                "closure_claim: false",
            ),
        ),
    ]
    repo_local_blockers_open = any(not item["present_in_decision_doc"] for item in blocker_results) is False
    external_blocked_migration_ready = canary_gate_sufficient and not repo_local_blockers_open
    return {
        "slug": topic.slug,
        "title": topic.title,
        "status": "retained_partial_repo_local_blockers_open",
        "current_dev_directory_exists": directory.is_dir(),
        "archive_external_blocked_directory_exists": archive_directory.exists(),
        "current_dev_index_row_present": bool(index_line),
        "current_dev_index_row": index_line,
        "canary_repo_local_gate_sufficient": canary_gate_sufficient,
        "repo_local_blockers_open": repo_local_blockers_open,
        "repo_local_blockers": blocker_results,
        "external_live_conditions": list(topic.external_live_conditions),
        "external_blocked_migration_ready": external_blocked_migration_ready,
        "recommended_location": "CURRENT_DEV",
        "documentation_checks": documentation_checks,
    }


def validate_report(report: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version mismatch")
    if report.get("metrics_readback_check", {}).get("status") != "passed":
        errors.append("metrics_readback_check must pass")
    if report.get("metrics_24h_artifact_check", {}).get("status") != "passed":
        errors.append("metrics_24h_artifact_check must pass")
    if report.get("canary_repo_local_gate_sufficient") is not True:
        errors.append("canary_repo_local_gate_sufficient must be true")
    if report.get("external_blocked_migration_candidates") != []:
        errors.append("external_blocked_migration_candidates must be empty while repo-local blockers remain")

    topics = report.get("topics") if isinstance(report.get("topics"), list) else []
    if len(topics) != len(TOPICS):
        errors.append(f"expected {len(TOPICS)} topic results, got {len(topics)}")
    for topic in topics:
        if not isinstance(topic, Mapping):
            errors.append("topic result must be an object")
            continue
        slug = str(topic.get("slug") or "<missing>")
        if topic.get("status") != "retained_partial_repo_local_blockers_open":
            errors.append(f"{slug}: status must remain retained_partial_repo_local_blockers_open")
        if topic.get("recommended_location") != "CURRENT_DEV":
            errors.append(f"{slug}: recommended_location must be CURRENT_DEV")
        if topic.get("current_dev_directory_exists") is not True:
            errors.append(f"{slug}: CURRENT_DEV directory must exist")
        if topic.get("archive_external_blocked_directory_exists") is not False:
            errors.append(f"{slug}: must not already exist under ARCHIVE_EXTERNAL_BLOCKED")
        if topic.get("current_dev_index_row_present") is not True:
            errors.append(f"{slug}: CURRENT_DEV index row must be present")
        if topic.get("canary_repo_local_gate_sufficient") is not True:
            errors.append(f"{slug}: canary repo-local gate must be sufficient")
        if topic.get("repo_local_blockers_open") is not True:
            errors.append(f"{slug}: repo-local blockers must remain open")
        if topic.get("external_blocked_migration_ready") is not False:
            errors.append(f"{slug}: must not be ready for external_blocked migration")
        blockers = topic.get("repo_local_blockers") if isinstance(topic.get("repo_local_blockers"), list) else []
        if not blockers:
            errors.append(f"{slug}: must record at least one repo-local blocker")
        for blocker in blockers:
            if isinstance(blocker, Mapping) and blocker.get("present_in_decision_doc") is not True:
                errors.append(f"{slug}: blocker token missing from decision doc: {blocker.get('code')}")
        doc_checks = topic.get("documentation_checks") if isinstance(topic.get("documentation_checks"), list) else []
        if not doc_checks:
            errors.append(f"{slug}: documentation_checks must be present")
        for check in doc_checks:
            if isinstance(check, Mapping) and check.get("passed") is not True:
                errors.append(f"{slug}: documentation check failed for {check.get('path')}: {check.get('missing_tokens')}")
        live_conditions = " ".join(str(item) for item in topic.get("external_live_conditions") or [])
        if "24h" not in live_conditions or "canary" not in live_conditions:
            errors.append(f"{slug}: external live conditions must mention canary and 24h metrics")
    return errors


def run_check(*, write_output: Path | None = None) -> dict[str, Any]:
    metrics_readback = run_metrics_readback_check()
    metrics_24h = run_24h_artifact_check()
    canary_gate_sufficient = metrics_readback["status"] == "passed" and metrics_24h["status"] == "passed"
    current_index_text = _read_text(REPO_ROOT / CURRENT_DEV_INDEX)
    topics = [
        _topic_result(
            topic=topic,
            current_index_text=current_index_text,
            canary_gate_sufficient=canary_gate_sufficient,
        )
        for topic in TOPICS
    ]
    migration_candidates = [
        topic["slug"]
        for topic in topics
        if topic["external_blocked_migration_ready"] is True
    ]
    report: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "status": "passed",
        "scope": [topic.slug for topic in TOPICS],
        "canary_repo_local_gate_sufficient": canary_gate_sufficient,
        "metrics_readback_check": _summarize_gate(metrics_readback),
        "metrics_24h_artifact_check": _summarize_gate(metrics_24h),
        "external_blocked_migration_candidates": migration_candidates,
        "topics": topics,
    }
    errors = validate_report(report)
    report["validation_errors"] = errors
    report["status"] = "passed" if not errors else "failed"
    if write_output is not None:
        output = write_output if write_output.is_absolute() else REPO_ROOT / write_output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave27 ingest canary closure readiness")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    parser.add_argument("--write-output", type=Path, default=None, help="optional JSON report path")
    args = parser.parse_args(argv)

    report = run_check(write_output=args.write_output)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status'].upper()} {CONTRACT_VERSION} "
            f"canary_repo_local_gate_sufficient={str(report['canary_repo_local_gate_sufficient']).lower()} "
            f"topics={len(report['topics'])} "
            f"external_blocked_candidates={len(report['external_blocked_migration_candidates'])} "
            f"recommended_location=CURRENT_DEV"
        )
        if report["status"] != "passed":
            print(json.dumps(report["validation_errors"], ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
