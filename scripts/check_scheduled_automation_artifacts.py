#!/usr/bin/env python3
"""Check whether nightly automation artifacts prove a real scheduled run."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

try:
    from scripts._automation_runtime import repo_root, utc_now
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _automation_runtime import repo_root, utc_now


SCHEMA_VERSION = "scheduled_automation_artifact_evidence.v1"
CLASS_SCHEDULED = "scheduled_run_evidence"
CLASS_SCHEDULED_BLOCKED = "scheduled_run_blocked"
CLASS_MANUAL = "manual_dry_run"
CLASS_MISSING = "missing"
TRIAGE_SCHEDULER_NOT_OBSERVED = "scheduler_not_observed"
TRIAGE_SCHEDULER_CONFIGURED_PENDING_RUN = "scheduler_configured_pending_run"
TRIAGE_SCHEDULER_RAN_NO_ARTIFACT = "scheduler_ran_no_artifact"
TRIAGE_ARTIFACT_WRONG_PATH = "artifact_wrong_path"
TRIAGE_ARTIFACT_PRESENT_CHECKER_MISMATCH = "artifact_present_checker_mismatch"
TRIAGE_SCHEDULED_RUN_BLOCKED = "scheduled_run_blocked"
STATUS_PASSED = "passed"
STATUS_BLOCKED = "blocked"
MATRIX_LANE = "business_line_worker_readback_project_matrix_nightly"
IDENTITY_WARNING_SEVERITY_RANKS = {
    "warning": 1,
}
MATRIX_VALID_STATUSES = {"passed", "partial"}
AUTOMATION_SPEC_NAME = "automation-spec.json"


@dataclass(frozen=True)
class LaneSpec:
    lane: str
    base_dir: str
    artifact_globs: tuple[str, ...]
    recommended_command: str


DEFAULT_LANES: tuple[LaneSpec, ...] = (
    LaneSpec(
        lane="performance_capacity_baseline_nightly",
        base_dir="development/latest-dev-docs/automation-runs/performance-capacity-baseline",
        artifact_globs=(
            "development/latest-dev-docs/automation-runs/performance-capacity-baseline/*/nightly-manifest.json",
            "development/latest-dev-docs/automation-runs/performance-capacity-baseline/*/performance-baseline.json",
        ),
        recommended_command=(
            "Wait for Codex app automation mrw-performance-capacity-baseline-nightly "
            "to produce a scheduler-marked artifact, then rerun: "
            "python3 scripts/check_scheduled_automation_artifacts.py --json"
        ),
    ),
    LaneSpec(
        lane="llm_report_token_state_retention_nightly",
        base_dir="development/latest-dev-docs/automation-runs/llm-report-token-state-retention",
        artifact_globs=(
            "development/latest-dev-docs/automation-runs/llm-report-token-state-retention/*/nightly-manifest.json",
            "development/latest-dev-docs/automation-runs/llm-report-token-state-retention/*/retention-report.json",
        ),
        recommended_command=(
            "Wait for Codex app automation mrw-llm-report-token-state-retention-nightly "
            "to produce a scheduler-marked artifact, then rerun: "
            "python3 scripts/check_scheduled_automation_artifacts.py --json"
        ),
    ),
    LaneSpec(
        lane="business_line_worker_readback_project_matrix_nightly",
        base_dir=(
            "development/latest-dev-docs/automation-runs/"
            "business-line-worker-readback-project-matrix"
        ),
        artifact_globs=(
            "development/latest-dev-docs/automation-runs/"
            "business-line-worker-readback-project-matrix/*/nightly-manifest.json",
            "development/latest-dev-docs/automation-runs/"
            "business-line-worker-readback-project-matrix/*/"
            "business-line-worker-readback-project-matrix-report.json",
        ),
        recommended_command=(
            "Wait for the matrix nightly scheduler to produce a scheduler-marked artifact "
            "for business_line_worker_readback_project_matrix_nightly, then rerun: "
            "python3 scripts/check_scheduled_automation_artifacts.py --json"
        ),
    ),
)


SCHEDULE_SOURCE_KEYS = {
    "trigger",
    "run_trigger",
    "source",
    "run_source",
    "execution_source",
    "invocation_source",
    "origin",
    "created_by",
}
SCHEDULE_SOURCE_VALUES = {
    "scheduled",
    "scheduler",
    "cron",
    "codex_app",
    "codex_app_scheduler",
    "codex_app_cron",
    "scheduled_run",
    "scheduled_run_evidence",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Repository root. Defaults to this script's repo.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Return exit code 0 even when scheduled evidence is missing; JSON status remains blocked.",
    )
    return parser.parse_args()


def iso_mtime(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
    except OSError:
        return None


def file_identity(path: Path) -> dict[str, int | str | None]:
    try:
        size_bytes = path.stat().st_size
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"size_bytes": size_bytes, "sha256": digest.hexdigest()}
    except OSError:
        return {"size_bytes": None, "sha256": None}


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def load_toml(path: Path) -> dict[str, Any] | None:
    try:
        loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def normalize(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def has_scheduled_marker(value: Any) -> bool:
    if isinstance(value, dict):
        for raw_key, raw_value in value.items():
            key = normalize(raw_key)
            if key == CLASS_SCHEDULED and raw_value is True:
                return True
            if key in {"scheduled", "is_scheduled"} and raw_value is True:
                return True
            if key in SCHEDULE_SOURCE_KEYS and normalize(raw_value) in SCHEDULE_SOURCE_VALUES:
                return True
            if isinstance(raw_value, (dict, list)) and has_scheduled_marker(raw_value):
                return True
        return False
    if isinstance(value, list):
        return any(has_scheduled_marker(item) for item in value)
    return False


def has_manual_dry_run_marker(value: Any) -> bool:
    if isinstance(value, dict):
        for raw_key, raw_value in value.items():
            key = normalize(raw_key)
            if key == "mode" and normalize(raw_value) == "dry_run":
                return True
            if key == "dry_run" and raw_value is True:
                return True
            if isinstance(raw_value, (dict, list)) and has_manual_dry_run_marker(raw_value):
                return True
        return False
    if isinstance(value, list):
        return any(has_manual_dry_run_marker(item) for item in value)
    return False


def has_non_empty_string_list(value: Any) -> bool:
    return isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value)


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def non_empty_string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def string_keyed_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def compact_diagnostic_projects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    projects: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            projects.append(
                {
                    "project_key": item.get("project_key"),
                    "status": item.get("status"),
                    "reason": item.get("reason"),
                    "stopped_at": item.get("stopped_at"),
                    "exit_code": item.get("exit_code"),
                    "trigger_smoke_status": item.get("trigger_smoke_status"),
                }
            )
        elif isinstance(item, str) and item.strip():
            projects.append(
                {
                    "project_key": item,
                    "status": None,
                    "reason": None,
                    "stopped_at": None,
                    "exit_code": None,
                    "trigger_smoke_status": None,
                }
            )
    return projects


def first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def matrix_payload_evidence(payload: dict[str, Any]) -> tuple[bool, str]:
    missing: list[str] = []
    status = normalize(payload.get("status"))
    matrix_report_status = normalize(payload.get("matrix_report_status"))
    if status not in MATRIX_VALID_STATUSES and matrix_report_status not in MATRIX_VALID_STATUSES:
        missing.append("status passed/partial")

    project_selection = payload.get("project_selection")
    project_keys = project_selection.get("project_keys") if isinstance(project_selection, dict) else None
    if not has_non_empty_string_list(project_keys):
        missing.append("non-empty project_selection.project_keys")

    summary = payload.get("summary")
    summary_total = summary.get("total") if isinstance(summary, dict) else None
    summary_total_projects = summary.get("total_projects") if isinstance(summary, dict) else None
    if not (positive_int(summary_total) or positive_int(summary_total_projects) or positive_int(payload.get("total_projects"))):
        missing.append("summary.total or total_projects > 0")

    if missing:
        return False, "matrix scheduled marker lacks payload evidence: " + ", ".join(missing)
    return True, "artifact contains scheduled marker and matrix project-selection/summary evidence"


def matrix_blocked_payload_evidence(payload: dict[str, Any]) -> tuple[bool, str]:
    status = normalize(payload.get("status"))
    matrix_report_status = normalize(payload.get("matrix_report_status"))
    if status in MATRIX_VALID_STATUSES or matrix_report_status in MATRIX_VALID_STATUSES:
        return False, "matrix scheduled marker has passed/partial status"

    project_selection = payload.get("project_selection")
    project_keys = project_selection.get("project_keys") if isinstance(project_selection, dict) else None
    if not has_non_empty_string_list(project_keys):
        return False, "matrix scheduled marker lacks payload evidence: non-empty project_selection.project_keys"

    summary = payload.get("summary")
    summary_total = summary.get("total") if isinstance(summary, dict) else None
    summary_total_projects = summary.get("total_projects") if isinstance(summary, dict) else None
    if not (positive_int(summary_total) or positive_int(summary_total_projects) or positive_int(payload.get("total_projects"))):
        return False, "matrix scheduled marker lacks payload evidence: summary.total or total_projects > 0"

    return (
        True,
        "matrix scheduler artifact present with project-selection/summary evidence, "
        "but status/matrix_report_status is not passed/partial",
    )


def matrix_artifact_diagnostics(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "matrix_status": None,
            "matrix_report_status": None,
            "matrix_exit_code": None,
            "runtime_preflight_status": None,
            "runtime_preflight_start_exit_code": None,
            "project_keys": [],
            "projects_api_url": None,
            "summary_total": None,
            "duration_seconds": None,
            "blocked_project_count": None,
            "failed_project_count": None,
            "blocked_projects": [],
            "failed_projects": [],
            "stopped_at_counts": {},
            "reason_counts": {},
            "first_blocked_reason": None,
        }

    matrix_diagnostics = payload.get("matrix_diagnostics")
    if not isinstance(matrix_diagnostics, dict):
        matrix_diagnostics = {}
    runtime_preflight = payload.get("runtime_preflight")
    if not isinstance(runtime_preflight, dict):
        runtime_preflight = {}
    project_selection = payload.get("project_selection")
    if not isinstance(project_selection, dict):
        project_selection = {}
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}

    project_keys = first_present(
        matrix_diagnostics.get("project_keys"),
        project_selection.get("project_keys"),
    )
    summary_total = first_present(
        matrix_diagnostics.get("summary_total"),
        summary.get("total"),
        summary.get("total_projects"),
        payload.get("total_projects"),
    )

    return {
        "matrix_status": first_present(matrix_diagnostics.get("matrix_status"), payload.get("status")),
        "matrix_report_status": first_present(
            matrix_diagnostics.get("matrix_report_status"),
            payload.get("matrix_report_status"),
        ),
        "matrix_exit_code": first_present(
            matrix_diagnostics.get("matrix_exit_code"),
            payload.get("matrix_exit_code"),
        ),
        "runtime_preflight_status": first_present(
            matrix_diagnostics.get("runtime_preflight_status"),
            runtime_preflight.get("status"),
        ),
        "runtime_preflight_start_exit_code": first_present(
            matrix_diagnostics.get("runtime_preflight_start_exit_code"),
            runtime_preflight.get("start_exit_code"),
        ),
        "project_keys": non_empty_string_items(project_keys),
        "projects_api_url": first_present(
            matrix_diagnostics.get("projects_api_url"),
            project_selection.get("projects_api_url"),
            payload.get("projects_api_url"),
        ),
        "summary_total": summary_total,
        "duration_seconds": first_present(
            matrix_diagnostics.get("duration_seconds"),
            payload.get("duration_seconds"),
        ),
        "blocked_project_count": first_present(
            matrix_diagnostics.get("blocked_project_count"),
            summary.get("blocked_project_count"),
            summary.get("blocked_by_environment"),
            summary.get("blocked"),
            payload.get("blocked_project_count"),
        ),
        "failed_project_count": first_present(
            matrix_diagnostics.get("failed_project_count"),
            summary.get("failed_project_count"),
            summary.get("failed"),
            payload.get("failed_project_count"),
        ),
        "blocked_projects": compact_diagnostic_projects(
            first_present(
                matrix_diagnostics.get("blocked_projects"),
                summary.get("blocked_projects"),
                payload.get("blocked_projects"),
            )
        ),
        "failed_projects": compact_diagnostic_projects(
            first_present(
                matrix_diagnostics.get("failed_projects"),
                summary.get("failed_projects"),
                payload.get("failed_projects"),
            )
        ),
        "stopped_at_counts": string_keyed_mapping(
            first_present(
                matrix_diagnostics.get("stopped_at_counts"),
                summary.get("stopped_at_counts"),
                payload.get("stopped_at_counts"),
            )
        ),
        "reason_counts": string_keyed_mapping(
            first_present(
                matrix_diagnostics.get("reason_counts"),
                summary.get("reason_counts"),
                payload.get("reason_counts"),
            )
        ),
        "first_blocked_reason": first_present(
            matrix_diagnostics.get("first_blocked_reason"),
            summary.get("first_blocked_reason"),
            payload.get("first_blocked_reason"),
        ),
    }


def artifact_row(path: Path, root: Path, observed_at: str, lane: str) -> dict[str, Any]:
    payload = load_json(path)
    has_schedule_evidence = payload is not None and has_scheduled_marker(payload)
    has_dry_run_evidence = payload is not None and has_manual_dry_run_marker(payload)
    if has_dry_run_evidence:
        classification = CLASS_MANUAL
        if has_schedule_evidence:
            reason = "artifact has scheduler marker but is marked dry_run and cannot close live scheduled evidence"
        else:
            reason = "artifact is marked dry_run and cannot close scheduled evidence"
    elif has_schedule_evidence and lane == MATRIX_LANE:
        has_payload_evidence, payload_reason = matrix_payload_evidence(payload)
        if has_payload_evidence:
            classification = CLASS_SCHEDULED
            reason = payload_reason
        else:
            has_blocked_evidence, blocked_reason = matrix_blocked_payload_evidence(payload)
            if has_blocked_evidence:
                classification = CLASS_SCHEDULED_BLOCKED
                reason = blocked_reason
            else:
                classification = CLASS_MANUAL
                reason = payload_reason
    elif has_schedule_evidence:
        classification = CLASS_SCHEDULED
        reason = "artifact contains an explicit scheduled-run marker"
    else:
        classification = CLASS_MANUAL
        reason = "artifact exists but lacks an explicit scheduled-run marker"

    try:
        artifact_path = path.relative_to(root).as_posix()
    except ValueError:
        artifact_path = str(path)
    row = {
        "artifact_path": artifact_path,
        "absolute_path": str(path),
        "mtime": iso_mtime(path),
        **file_identity(path),
        "observed_at": observed_at,
        "classification": classification,
        "reason": reason,
    }
    if lane == MATRIX_LANE:
        row["diagnostics"] = matrix_artifact_diagnostics(payload)
    return row


def artifact_identity(row: dict[str, Any]) -> tuple[Any, Any]:
    return row.get("size_bytes"), row.get("sha256")


def has_artifact_identity(row: dict[str, Any]) -> bool:
    size_bytes, sha256 = artifact_identity(row)
    return size_bytes is not None and sha256 is not None


def apply_freshness_window(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not artifacts:
        return artifacts

    latest = artifacts[0]
    latest_identity = artifact_identity(latest)
    latest_path = latest.get("artifact_path")
    for index, row in enumerate(artifacts, start=1):
        row["freshness_rank"] = index
        row["freshness_window_size"] = len(artifacts)
        row["is_latest_for_lane"] = index == 1
        row["latest_artifact_path"] = latest_path
        row["identity_matches_latest"] = artifact_identity(row) == latest_identity
        row["identity_warning"] = None
        row["identity_warning_severity"] = None
        row["identity_warning_message"] = None
        if not has_artifact_identity(row):
            row["identity_status"] = "unknown"
        elif row["is_latest_for_lane"]:
            row["identity_status"] = "latest"
        elif row["identity_matches_latest"]:
            row["identity_status"] = "same_as_latest"
        else:
            row["identity_status"] = "differs_from_latest"
            row["identity_warning"] = "artifact_identity_differs_from_latest"
            row["identity_warning_severity"] = "warning"
            row["identity_warning_message"] = (
                "Stale artifact identity differs from the latest artifact."
            )
    return artifacts


def summarize_identity_warnings(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    warnings = [row.get("identity_warning") for row in artifacts if row.get("identity_warning")]
    status_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    for row in artifacts:
        status = row.get("identity_status")
        if isinstance(status, str) and status:
            status_counts[status] = status_counts.get(status, 0) + 1
        severity = row.get("identity_warning_severity")
        if isinstance(severity, str) and severity:
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
    severity_order = sorted(
        severity_counts,
        key=lambda severity: (IDENTITY_WARNING_SEVERITY_RANKS.get(severity, 0), severity),
    )
    highest_severity = severity_order[-1] if severity_order else None
    highest_severity_rank = (
        IDENTITY_WARNING_SEVERITY_RANKS.get(highest_severity)
        if highest_severity is not None
        else None
    )
    return {
        "identity_warning_count": len(warnings),
        "identity_warning_types": sorted(
            {warning for warning in warnings if isinstance(warning, str)}
        ),
        "identity_warning_severity_counts": severity_counts,
        "identity_warning_severity_order": severity_order,
        "identity_warning_highest_severity": highest_severity,
        "identity_warning_highest_severity_rank": highest_severity_rank,
        "identity_status_counts": status_counts,
    }


def discover_related_lanes(root: Path) -> list[LaneSpec]:
    known_bases = {spec.base_dir for spec in DEFAULT_LANES}
    discovered: list[LaneSpec] = []
    for manifest in sorted(
        (root / "development/latest-dev-docs/automation-runs").glob("*/*/nightly-manifest.json")
    ):
        base = manifest.parents[1]
        try:
            base_rel = base.relative_to(root).as_posix()
        except ValueError:
            continue
        if base_rel in known_bases:
            continue
        lane_name = base.name.replace("-", "_") + "_nightly"
        discovered.append(
            LaneSpec(
                lane=lane_name,
                base_dir=base_rel,
                artifact_globs=(f"{base_rel}/*/nightly-manifest.json",),
                recommended_command=(
                    "Wait for the related nightly scheduler to produce a scheduler-marked artifact, "
                    "then rerun: python3 scripts/check_scheduled_automation_artifacts.py --json"
                ),
            )
        )
    unique: dict[str, LaneSpec] = {}
    for spec in discovered:
        unique.setdefault(spec.base_dir, spec)
    return list(unique.values())


def scheduler_config_evidence(root: Path, spec: LaneSpec) -> dict[str, Any]:
    spec_path = root / spec.base_dir / AUTOMATION_SPEC_NAME
    evidence: dict[str, Any] = {
        "status": "not_configured",
        "spec_path": relpath(spec_path, root),
        "spec_exists": spec_path.is_file(),
        "configured": False,
        "problems": [],
    }
    if not spec_path.is_file():
        evidence["problems"].append("automation_spec_missing")
        return evidence

    spec_payload = load_json(spec_path)
    if spec_payload is None:
        evidence.update({"status": "misconfigured"})
        evidence["problems"].append("automation_spec_invalid_json")
        return evidence

    codex_app = spec_payload.get("codex_app")
    install_status = spec_payload.get("install_status")
    evidence["install_status"] = install_status
    if install_status != "installed_codex_app" or not isinstance(codex_app, dict):
        evidence.update({"status": "not_configured"})
        evidence["problems"].append("codex_app_installation_not_declared")
        return evidence

    automation_id = codex_app.get("automation_id")
    config_path_raw = codex_app.get("config_path")
    expected_status = codex_app.get("status")
    expected_rrule = codex_app.get("rrule")
    expected_cwd = codex_app.get("cwd")
    evidence.update(
        {
            "automation_id": automation_id,
            "config_path": config_path_raw,
            "expected_status": expected_status,
            "expected_rrule": expected_rrule,
            "expected_cwd": expected_cwd,
        }
    )
    if not isinstance(config_path_raw, str) or not config_path_raw:
        evidence.update({"status": "misconfigured"})
        evidence["problems"].append("codex_app_config_path_missing")
        return evidence

    config_path = Path(config_path_raw).expanduser()
    if not config_path.is_file():
        evidence.update({"status": "misconfigured"})
        evidence["problems"].append("codex_app_config_path_not_found")
        return evidence

    automation_config = load_toml(config_path)
    if automation_config is None:
        evidence.update({"status": "misconfigured"})
        evidence["problems"].append("codex_app_config_unreadable")
        return evidence

    actual_cwds = automation_config.get("cwds")
    cwd_matches = (
        isinstance(expected_cwd, str)
        and isinstance(actual_cwds, list)
        and expected_cwd in actual_cwds
    )
    actual = {
        "automation_id": automation_config.get("id"),
        "status": automation_config.get("status"),
        "rrule": automation_config.get("rrule"),
        "kind": automation_config.get("kind"),
        "execution_environment": automation_config.get("execution_environment"),
        "cwds": actual_cwds if isinstance(actual_cwds, list) else [],
    }
    evidence.update(
        {
            "actual": actual,
            "cwd_matches": cwd_matches,
        }
    )
    if isinstance(automation_id, str) and actual["automation_id"] != automation_id:
        evidence["problems"].append("codex_app_automation_id_mismatch")
    if isinstance(expected_status, str) and actual["status"] != expected_status:
        evidence["problems"].append("codex_app_status_mismatch")
    if isinstance(expected_rrule, str) and actual["rrule"] != expected_rrule:
        evidence["problems"].append("codex_app_rrule_mismatch")
    if not cwd_matches:
        evidence["problems"].append("codex_app_cwd_mismatch")

    if evidence["problems"]:
        evidence.update({"status": "misconfigured", "configured": False})
    elif actual["status"] == "ACTIVE":
        evidence.update({"status": "configured_pending_run", "configured": True})
    else:
        evidence.update({"status": "not_active", "configured": False})
        evidence["problems"].append("codex_app_not_active")
    return evidence


def collect_lane(root: Path, spec: LaneSpec, observed_at: str) -> dict[str, Any]:
    paths: dict[str, Path] = {}
    for pattern in spec.artifact_globs:
        for path in root.glob(pattern):
            if path.is_file():
                paths[str(path)] = path

    artifacts = sorted(
        (artifact_row(path, root, observed_at, spec.lane) for path in paths.values()),
        key=lambda row: row["mtime"] or "",
        reverse=True,
    )
    artifacts = apply_freshness_window(artifacts)
    scheduler_evidence = scheduler_config_evidence(root, spec)
    if not artifacts:
        classification = CLASS_MISSING
        if scheduler_evidence.get("status") == "configured_pending_run":
            reason = "scheduler automation is configured, but no expected nightly artifact files were found"
            blocker_classification = TRIAGE_SCHEDULER_CONFIGURED_PENDING_RUN
            first_missing_reason = "scheduler_configured_but_no_expected_nightly_artifact_files_found"
        else:
            reason = "no expected nightly artifact files were found"
            blocker_classification = TRIAGE_SCHEDULER_NOT_OBSERVED
            first_missing_reason = "no_expected_nightly_artifact_files_found"
        artifact_path = None
        mtime = None
        diagnostics = None
    elif any(row["classification"] == CLASS_SCHEDULED for row in artifacts):
        classification = CLASS_SCHEDULED
        reason = "at least one artifact contains explicit scheduled-run evidence"
        scheduled = next(row for row in artifacts if row["classification"] == CLASS_SCHEDULED)
        artifact_path = scheduled["artifact_path"]
        mtime = scheduled["mtime"]
        diagnostics = scheduled.get("diagnostics")
        blocker_classification = None
        first_missing_reason = None
    elif any(row["classification"] == CLASS_SCHEDULED_BLOCKED for row in artifacts):
        classification = CLASS_SCHEDULED_BLOCKED
        blocked = next(row for row in artifacts if row["classification"] == CLASS_SCHEDULED_BLOCKED)
        reason = blocked.get("reason") or "scheduled artifact exists, but did not pass"
        artifact_path = blocked["artifact_path"]
        mtime = blocked["mtime"]
        diagnostics = blocked.get("diagnostics")
        blocker_classification = TRIAGE_SCHEDULED_RUN_BLOCKED
        first_missing_reason = reason
    else:
        classification = CLASS_MANUAL
        reason = artifacts[0].get("reason") or "artifacts exist, but none prove scheduler/cron origin"
        artifact_path = artifacts[0]["artifact_path"]
        mtime = artifacts[0]["mtime"]
        diagnostics = artifacts[0].get("diagnostics")
        blocker_classification = TRIAGE_ARTIFACT_PRESENT_CHECKER_MISMATCH
        first_missing_reason = reason

    lane = {
        "lane": spec.lane,
        "base_dir": spec.base_dir,
        "expected_paths": list(spec.artifact_globs),
        "classification": classification,
        "blocker_classification": blocker_classification,
        "first_missing_reason": first_missing_reason,
        "reason": reason,
        "artifact_path": artifact_path,
        "mtime": mtime,
        "observed_at": observed_at,
        "recommended_command": spec.recommended_command,
        "scheduler_config": scheduler_evidence,
        "artifacts": artifacts,
        **summarize_identity_warnings(artifacts),
    }
    if spec.lane == MATRIX_LANE and diagnostics is not None:
        lane["diagnostics"] = diagnostics
    return lane


def build_report(root: Path) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=scheduled_automation_artifacts+repository_metadata "
    "witness=test:test_w11_non_authoritative_metadata",
]:
    observed_at = utc_now()
    lane_specs = [*DEFAULT_LANES, *discover_related_lanes(root)]
    lanes = [collect_lane(root, spec, observed_at) for spec in lane_specs]
    scheduled_count = sum(1 for lane in lanes if lane["classification"] == CLASS_SCHEDULED)
    scheduled_blocked_count = sum(
        1 for lane in lanes if lane["classification"] == CLASS_SCHEDULED_BLOCKED
    )
    manual_count = sum(1 for lane in lanes if lane["classification"] == CLASS_MANUAL)
    missing_count = sum(1 for lane in lanes if lane["classification"] == CLASS_MISSING)
    blocker_classification_counts: dict[str, int] = {}
    for lane in lanes:
        blocker_classification = lane.get("blocker_classification")
        if isinstance(blocker_classification, str) and blocker_classification:
            blocker_classification_counts[blocker_classification] = (
                blocker_classification_counts.get(blocker_classification, 0) + 1
            )
    blocker_priority = {
        TRIAGE_SCHEDULED_RUN_BLOCKED: 0,
        TRIAGE_ARTIFACT_PRESENT_CHECKER_MISMATCH: 1,
        TRIAGE_ARTIFACT_WRONG_PATH: 2,
        TRIAGE_SCHEDULER_RAN_NO_ARTIFACT: 3,
        TRIAGE_SCHEDULER_CONFIGURED_PENDING_RUN: 4,
        TRIAGE_SCHEDULER_NOT_OBSERVED: 5,
    }
    blocked_lanes = [lane for lane in lanes if isinstance(lane.get("blocker_classification"), str)]
    first_blocked_lane = min(
        blocked_lanes,
        key=lambda lane: blocker_priority.get(str(lane.get("blocker_classification")), 99),
    ) if blocked_lanes else None
    status = STATUS_PASSED if scheduled_count else STATUS_BLOCKED
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "observed_at": observed_at,
        "classifications": [CLASS_SCHEDULED, CLASS_SCHEDULED_BLOCKED, CLASS_MANUAL, CLASS_MISSING],
        "blocker_classifications": [
            TRIAGE_SCHEDULER_NOT_OBSERVED,
            TRIAGE_SCHEDULER_CONFIGURED_PENDING_RUN,
            TRIAGE_SCHEDULER_RAN_NO_ARTIFACT,
            TRIAGE_ARTIFACT_WRONG_PATH,
            TRIAGE_ARTIFACT_PRESENT_CHECKER_MISMATCH,
            TRIAGE_SCHEDULED_RUN_BLOCKED,
        ],
        "summary": {
            "scheduled_run_evidence_count": scheduled_count,
            "scheduled_run_blocked_count": scheduled_blocked_count,
            "manual_dry_run_count": manual_count,
            "missing_count": missing_count,
            "lane_count": len(lanes),
            "blocker_classification_counts": blocker_classification_counts,
            "first_blocker_classification": (
                first_blocked_lane.get("blocker_classification")
                if first_blocked_lane is not None
                else None
            ),
            "first_missing_reason": (
                first_blocked_lane.get("first_missing_reason")
                if first_blocked_lane is not None
                else None
            ),
            "first_blocked_lane": first_blocked_lane.get("lane") if first_blocked_lane is not None else None,
        },
        "recommended_command": "python3 scripts/check_scheduled_automation_artifacts.py --json",
        "lanes": lanes,
    }


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve() if args.root else repo_root()
    report = build_report(root)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    elif report["status"] == STATUS_PASSED:
        print("OK scheduled automation artifact evidence found")
    else:
        print("BLOCKED scheduled automation artifact evidence missing")
        for lane in report["lanes"]:
            print(
                f"- {lane['lane']}: {lane['classification']} "
                f"artifact={lane['artifact_path'] or '<missing>'}"
            )

    if report["status"] == STATUS_PASSED or args.allow_missing:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
