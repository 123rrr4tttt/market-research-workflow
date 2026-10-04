from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter
from mrw_functorial_kit.business_line_vocabulary import (
    BUSINESS_LINE_KEYS as CANONICAL_BUSINESS_LINE_KEYS,
    BUSINESS_LINE_VOCABULARY_VERSION,
    WORKER_REQUIRED_BUSINESS_LINE_KEYS as CANONICAL_WORKER_REQUIRED_BUSINESS_LINE_KEYS,
)

from ..contracts import ApiEnvelope, ok


router = APIRouter(prefix="/business-lines", tags=["business-lines"])

CONTRACT_VERSION = "business_line.evidence_matrix.v2"
SCHEDULED_MATRIX_ARTIFACT_SUMMARY_CONTRACT_VERSION = (
    "business_line.scheduled_matrix_artifact_summary.v1"
)
SCHEDULED_ARTIFACT_SUMMARIES_CONTRACT_VERSION = (
    "business_line.scheduled_artifact_summaries.v1"
)
SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION = (
    "business_line.scheduled_artifact_drilldown.v1"
)
SCHEDULED_ARTIFACT_CHECKER_SCRIPT = "scripts/check_scheduled_automation_artifacts.py"
SCHEDULED_MATRIX_LANE = "business_line_worker_readback_project_matrix_nightly"
REAL_BACKEND_BROWSER_SMOKE_TEST_FILE = "main/frontend-modern/tests/e2e/real-backend-business-lines.spec.ts"
PROCESS_STATS_PROBE_PATH = "/api/v1/process/stats"
ASYNC_TASK_READBACK_LIVE_SAMPLE_RUNNER_SCRIPT = (
    "scripts/run_business_line_async_task_readback_live_samples.py"
)
ASYNC_TASK_READBACK_WORKER_MANIFEST_CLI = "--task-readback-manifest"
ASYNC_TASK_READBACK_WORKER_MANIFEST_CHECKER_SCRIPT = (
    "scripts/check_business_line_task_readback_manifest.py"
)
ASYNC_TASK_READBACK_WORKER_MANIFEST_CANDIDATE_BUILDER_SCRIPT = (
    "scripts/build_business_line_task_readback_manifest_from_runtime.py"
)
ASYNC_TASK_READBACK_WORKER_EVIDENCE_CHAIN_SCRIPT = (
    "scripts/run_business_line_worker_readback_evidence_chain.py"
)
ASYNC_TASK_READBACK_ARTIFACT_CHECKER_SCRIPT = (
    "scripts/check_business_line_async_task_readback_artifact.py"
)
TRACE_BASELINE_CONTRACT_VERSION = "business_line.trace_baseline.v1"
TRACE_BASELINE_RUNNER_SCRIPT = "scripts/run_business_line_trace_baseline_live.py"
TRACE_BASELINE_DEFAULT_SLOW_THRESHOLD_MS = 1000
TRACE_BASELINE_BODY_TRACE_EXEMPT_PROBE_PATHS = [
    "/api/v1/health",
    "/api/v1/health/deep",
]
TRACE_BASELINE_RECOMMENDED_COMMAND = (
    "python3 scripts/run_business_line_trace_baseline_live.py "
    "--base-url http://127.0.0.1:8000 "
    "--output /tmp/business-line-trace-baseline-live.json "
    "--trace-prefix business-line-trace "
    f"--slow-threshold-ms {TRACE_BASELINE_DEFAULT_SLOW_THRESHOLD_MS} "
    "--json"
)
WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS = list(
    CANONICAL_WORKER_REQUIRED_BUSINESS_LINE_KEYS
)
MATRIX_DIAGNOSTICS_REQUIRED_FIELDS = [
    "runtime_preflight_status",
    "matrix_exit_code",
    "project_keys",
    "summary_total",
    "first_blocked_reason",
    "reason_counts",
]
MATRIX_DIAGNOSTICS_BLOCKED_PROJECT_FIELDS = [
    "project_key",
    "status",
    "reason",
    "stopped_at",
    "exit_code",
    "trigger_smoke_status",
]
MATRIX_DIAGNOSTICS_RECOMMENDED_DISPLAY_ORDER = [
    "runtime_preflight_status",
    "matrix_exit_code",
    "project_keys",
    "summary_total",
    "first_blocked_reason",
    "reason_counts",
    "blocked_projects",
    "failed_projects",
]

LINE_KEYS = list(CANONICAL_BUSINESS_LINE_KEYS)

BLOCKED_BY_ENVIRONMENT_SEMANTICS = (
    "connection refused or timeout means blocked_by_environment: the backend runtime is unreachable, "
    "so the live smoke is not passed and must be retried after the environment is started."
)
READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS: dict[str, Any] = {
    "not_report_proof": True,
    "not_quality_gate_input": True,
    "not_scheduled_run_evidence_proof": True,
    "scheduled_evidence_write": "none",
    "scheduled_completion_proof_behavior": "unchanged",
    "audit_outcome_behavior": "unchanged",
}


def _read_only_context_proof_boundary(**extra: Any) -> dict[str, Any]:
    return {**READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS, **extra}


def _business_line_project_root() -> Path:
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if (parent / SCHEDULED_ARTIFACT_CHECKER_SCRIPT).is_file():
            return parent
    # A packaged backend may not contain repository-level scheduler evidence.
    # The callers report that absence as checker_unavailable.
    return module_path.parents[2]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _scheduled_matrix_completion_boundary() -> dict[str, str]:
    return {
        "scheduled_run_blocked": (
            "scheduled_run_blocked is scheduler-lane blocked evidence for triage, "
            "not completion proof and not sufficient to close scheduled evidence."
        ),
        "manual_dry_run": (
            "manual_dry_run can support debugging, but is not completion proof and cannot close "
            "scheduled evidence."
        ),
        "missing": (
            "missing means no scheduled artifact was found; it is not completion proof and cannot close "
            "scheduled evidence."
        ),
        "scheduled_run_evidence": (
            "Only scheduled_run_evidence can close scheduled evidence."
        ),
        "completion_claim": "does_not_claim_real_scheduler_run",
    }


def _scheduled_summary_counts() -> dict[str, int]:
    return {
        "scheduled_run_evidence_count": 0,
        "scheduled_run_blocked_count": 0,
        "manual_dry_run_count": 0,
        "missing_count": 0,
        "lane_count": 0,
    }


def _scheduled_checker_unavailable_summaries(
    *, reason: str, observed_at: str | None = None
) -> dict[str, Any]:
    return {
        "contract_version": SCHEDULED_ARTIFACT_SUMMARIES_CONTRACT_VERSION,
        "source_checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
        "status": "checker_unavailable",
        "reason": reason,
        "summary": _scheduled_summary_counts(),
        "lanes": [],
        "observed_at": observed_at or _utc_now(),
        "recommended_command": "python3 scripts/check_scheduled_automation_artifacts.py --json",
        "whitelisted_lanes": [],
        "completion_boundary": _scheduled_matrix_completion_boundary(),
    }


def _scheduled_checker_unavailable_drilldown(
    *, reason: str, observed_at: str | None = None
) -> dict[str, Any]:
    return {
        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
        "source_checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
        "status": "checker_unavailable",
        "reason": reason,
        "summary": _scheduled_summary_counts(),
        "lanes": [],
        "observed_at": observed_at or _utc_now(),
        "recommended_command": "python3 scripts/check_scheduled_automation_artifacts.py --json",
        "completion_boundary": _scheduled_matrix_completion_boundary(),
    }


def _checker_unavailable_summary(*, reason: str, observed_at: str | None = None) -> dict[str, Any]:
    scheduled_summaries = _scheduled_checker_unavailable_summaries(
        reason=reason,
        observed_at=observed_at,
    )
    return {
        "contract_version": SCHEDULED_MATRIX_ARTIFACT_SUMMARY_CONTRACT_VERSION,
        "source_checker": scheduled_summaries["source_checker"],
        "lane": SCHEDULED_MATRIX_LANE,
        "status": scheduled_summaries["status"],
        "lane_classification": "checker_unavailable",
        "reason": reason,
        "artifact_path": None,
        "diagnostics": {},
        "summary": scheduled_summaries["summary"],
        "observed_at": scheduled_summaries["observed_at"],
        "recommended_command": scheduled_summaries["recommended_command"],
        "completion_boundary": scheduled_summaries["completion_boundary"],
    }


def _load_scheduled_artifact_checker(checker_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(
        "scheduled_automation_artifact_checker",
        checker_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("scheduled artifact checker import spec is unavailable")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _lane_status(lane_classification: str) -> str:
    return "passed" if lane_classification == "scheduled_run_evidence" else "blocked"


def _summarize_scheduled_lane(
    lane: dict[str, Any],
    *,
    fallback_observed_at: str,
    fallback_recommended_command: str,
) -> dict[str, Any]:
    lane_classification = str(lane.get("classification") or "missing")
    return {
        "lane": lane.get("lane"),
        "status": _lane_status(lane_classification),
        "lane_classification": lane_classification,
        "reason": lane.get("reason") or "scheduled lane has no checker reason",
        "artifact_path": lane.get("artifact_path"),
        "diagnostics": lane.get("diagnostics") or {},
        "observed_at": lane.get("observed_at") or fallback_observed_at,
        "recommended_command": lane.get("recommended_command") or fallback_recommended_command,
    }


def _scheduled_artifact_row(artifact: dict[str, Any]) -> dict[str, Any]:
    classification = str(artifact.get("classification") or "missing")
    return {
        "artifact_path": artifact.get("artifact_path"),
        "classification": classification,
        "scheduled_completion_proof": classification == "scheduled_run_evidence",
        "reason": artifact.get("reason") or "scheduled artifact has no checker reason",
        "mtime": artifact.get("mtime"),
        "observed_at": artifact.get("observed_at"),
        "size_bytes": artifact.get("size_bytes"),
        "sha256": artifact.get("sha256"),
        "freshness_rank": artifact.get("freshness_rank"),
        "freshness_window_size": artifact.get("freshness_window_size"),
        "is_latest_for_lane": artifact.get("is_latest_for_lane"),
        "identity_matches_latest": artifact.get("identity_matches_latest"),
        "latest_artifact_path": artifact.get("latest_artifact_path"),
        "identity_status": artifact.get("identity_status"),
        "identity_warning": artifact.get("identity_warning"),
        "identity_warning_message": artifact.get("identity_warning_message"),
        "identity_warning_severity": artifact.get("identity_warning_severity"),
    }


def _non_negative_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _optional_positive_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _non_negative_int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: count
        for key, count in value.items()
        if isinstance(key, str)
        and key
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
    }


def _drilldown_scheduled_lane(
    lane: dict[str, Any],
    *,
    fallback_observed_at: str,
    fallback_recommended_command: str,
) -> dict[str, Any]:
    lane_classification = str(lane.get("classification") or "missing")
    artifacts = lane.get("artifacts")
    sanitized_artifacts = [
        _scheduled_artifact_row(artifact)
        for artifact in artifacts
        if isinstance(artifact, dict)
    ] if isinstance(artifacts, list) else []
    if lane_classification == "missing":
        sanitized_artifacts = []

    return {
        "lane": lane.get("lane"),
        "status": _lane_status(lane_classification),
        "lane_classification": lane_classification,
        "scheduled_completion_proof": lane_classification == "scheduled_run_evidence",
        "reason": lane.get("reason") or "scheduled lane has no checker reason",
        "artifact_path": lane.get("artifact_path"),
        "base_dir": lane.get("base_dir"),
        "artifact_count": len(sanitized_artifacts),
        "artifacts": sanitized_artifacts,
        "identity_warning_count": _non_negative_int(lane.get("identity_warning_count")),
        "identity_warning_types": _string_list(lane.get("identity_warning_types")),
        "identity_status_counts": _non_negative_int_dict(
            lane.get("identity_status_counts")
        ),
        "identity_warning_severity_counts": _non_negative_int_dict(
            lane.get("identity_warning_severity_counts")
        ),
        "identity_warning_severity_order": _string_list(
            lane.get("identity_warning_severity_order")
        ),
        "identity_warning_highest_severity": _optional_string(
            lane.get("identity_warning_highest_severity")
        ),
        "identity_warning_highest_severity_rank": _optional_positive_int(
            lane.get("identity_warning_highest_severity_rank")
        ),
        "diagnostics": lane.get("diagnostics") or {},
        "observed_at": lane.get("observed_at") or fallback_observed_at,
        "recommended_command": lane.get("recommended_command") or fallback_recommended_command,
    }


def _checker_whitelisted_lanes(checker: Any, lanes: list[dict[str, Any]]) -> list[str]:
    default_lanes = getattr(checker, "DEFAULT_LANES", None)
    if isinstance(default_lanes, tuple):
        lane_names = [getattr(spec, "lane", None) for spec in default_lanes]
        whitelisted = [lane for lane in lane_names if isinstance(lane, str) and lane]
        if whitelisted:
            return whitelisted
    return [
        lane["lane"]
        for lane in lanes
        if isinstance(lane.get("lane"), str) and lane.get("lane")
    ]


def build_scheduled_artifact_summaries(
    root: Path | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=api.business_lines witness=test:test_w01_meta",
]:
    repo_root = (root or _business_line_project_root()).resolve()
    checker_path = repo_root / SCHEDULED_ARTIFACT_CHECKER_SCRIPT
    if not checker_path.is_file():
        return _scheduled_checker_unavailable_summaries(
            reason=f"scheduled artifact checker not found at {SCHEDULED_ARTIFACT_CHECKER_SCRIPT}"
        )

    try:
        checker = _load_scheduled_artifact_checker(checker_path)
        build_report = getattr(checker, "build_report", None)
        if not callable(build_report):
            return _scheduled_checker_unavailable_summaries(
                reason="scheduled artifact checker does not expose callable build_report"
            )

        report = build_report(repo_root)
    except Exception as exc:  # noqa: BLE001
        return _scheduled_checker_unavailable_summaries(
            reason=f"scheduled artifact checker failed: {exc.__class__.__name__}: {exc}"
        )

    observed_at = report.get("observed_at") if isinstance(report, dict) else None
    observed_at = observed_at if isinstance(observed_at, str) and observed_at else _utc_now()
    recommended_command = (
        report.get("recommended_command")
        if isinstance(report, dict)
        and isinstance(report.get("recommended_command"), str)
        and report.get("recommended_command")
        else "python3 scripts/check_scheduled_automation_artifacts.py --json"
    )
    raw_lanes = report.get("lanes") if isinstance(report, dict) else None
    lanes = [
        _summarize_scheduled_lane(
            lane,
            fallback_observed_at=observed_at,
            fallback_recommended_command=recommended_command,
        )
        for lane in raw_lanes
        if isinstance(lane, dict)
    ] if isinstance(raw_lanes, list) else []
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    scheduled_count = summary.get("scheduled_run_evidence_count")
    status = report.get("status") if isinstance(report, dict) else None
    if not isinstance(status, str) or not status:
        status = "passed" if isinstance(scheduled_count, int) and scheduled_count > 0 else "blocked"

    return {
        "contract_version": SCHEDULED_ARTIFACT_SUMMARIES_CONTRACT_VERSION,
        "source_checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
        "status": status,
        "summary": summary,
        "lanes": lanes,
        "observed_at": observed_at,
        "recommended_command": recommended_command,
        "whitelisted_lanes": _checker_whitelisted_lanes(checker, lanes),
        "completion_boundary": _scheduled_matrix_completion_boundary(),
    }


def build_scheduled_artifact_drilldown(
    root: Path | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=api.business_lines witness=test:test_w01_meta",
]:
    repo_root = (root or _business_line_project_root()).resolve()
    checker_path = repo_root / SCHEDULED_ARTIFACT_CHECKER_SCRIPT
    if not checker_path.is_file():
        return _scheduled_checker_unavailable_drilldown(
            reason=f"scheduled artifact checker not found at {SCHEDULED_ARTIFACT_CHECKER_SCRIPT}"
        )

    try:
        checker = _load_scheduled_artifact_checker(checker_path)
        build_report = getattr(checker, "build_report", None)
        if not callable(build_report):
            return _scheduled_checker_unavailable_drilldown(
                reason="scheduled artifact checker does not expose callable build_report"
            )

        report = build_report(repo_root)
    except Exception as exc:  # noqa: BLE001
        return _scheduled_checker_unavailable_drilldown(
            reason=f"scheduled artifact checker failed: {exc.__class__.__name__}: {exc}"
        )

    observed_at = report.get("observed_at") if isinstance(report, dict) else None
    observed_at = observed_at if isinstance(observed_at, str) and observed_at else _utc_now()
    recommended_command = (
        report.get("recommended_command")
        if isinstance(report, dict)
        and isinstance(report.get("recommended_command"), str)
        and report.get("recommended_command")
        else "python3 scripts/check_scheduled_automation_artifacts.py --json"
    )
    raw_lanes = report.get("lanes") if isinstance(report, dict) else None
    lanes = [
        _drilldown_scheduled_lane(
            lane,
            fallback_observed_at=observed_at,
            fallback_recommended_command=recommended_command,
        )
        for lane in raw_lanes
        if isinstance(lane, dict)
    ] if isinstance(raw_lanes, list) else []
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    scheduled_count = summary.get("scheduled_run_evidence_count")
    status = report.get("status") if isinstance(report, dict) else None
    if not isinstance(status, str) or not status:
        status = "passed" if isinstance(scheduled_count, int) and scheduled_count > 0 else "blocked"

    return {
        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
        "source_checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
        "status": status,
        "summary": summary,
        "lanes": lanes,
        "observed_at": observed_at,
        "recommended_command": recommended_command,
        "completion_boundary": _scheduled_matrix_completion_boundary(),
    }


def build_scheduled_matrix_artifact_summary(
    root: Path | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=api.business_lines witness=test:test_w01_meta",
]:
    scheduled_summaries = build_scheduled_artifact_summaries(root)
    if scheduled_summaries.get("status") == "checker_unavailable":
        return _checker_unavailable_summary(
            reason=str(
                scheduled_summaries.get("reason")
                or "scheduled artifact checker is unavailable"
            ),
            observed_at=(
                scheduled_summaries.get("observed_at")
                if isinstance(scheduled_summaries.get("observed_at"), str)
                else None
            ),
        )

    lanes = scheduled_summaries.get("lanes")
    matrix_lane = None
    if isinstance(lanes, list):
        matrix_lane = next(
            (
                lane
                for lane in lanes
                if isinstance(lane, dict) and lane.get("lane") == SCHEDULED_MATRIX_LANE
            ),
            None,
        )

    if matrix_lane is None:
        return {
            "contract_version": SCHEDULED_MATRIX_ARTIFACT_SUMMARY_CONTRACT_VERSION,
            "source_checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
            "lane": SCHEDULED_MATRIX_LANE,
            "status": "blocked",
            "lane_classification": "missing",
            "reason": "matrix lane is missing from scheduled artifact checker report",
            "artifact_path": None,
            "diagnostics": {},
            "summary": scheduled_summaries.get("summary", {}),
            "observed_at": scheduled_summaries.get("observed_at") or _utc_now(),
            "recommended_command": scheduled_summaries.get("recommended_command")
            or "python3 scripts/check_scheduled_automation_artifacts.py --json",
            "completion_boundary": scheduled_summaries.get("completion_boundary")
            or _scheduled_matrix_completion_boundary(),
        }

    return {
        "contract_version": SCHEDULED_MATRIX_ARTIFACT_SUMMARY_CONTRACT_VERSION,
        "source_checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
        "lane": SCHEDULED_MATRIX_LANE,
        "status": matrix_lane.get("status") or "blocked",
        "lane_classification": matrix_lane.get("lane_classification") or "missing",
        "reason": matrix_lane.get("reason") or "matrix lane has no checker reason",
        "artifact_path": matrix_lane.get("artifact_path"),
        "diagnostics": matrix_lane.get("diagnostics") or {},
        "summary": scheduled_summaries.get("summary", {}),
        "observed_at": matrix_lane.get("observed_at") or scheduled_summaries.get("observed_at"),
        "recommended_command": matrix_lane.get("recommended_command")
        or scheduled_summaries.get("recommended_command"),
        "completion_boundary": scheduled_summaries.get("completion_boundary")
        or _scheduled_matrix_completion_boundary(),
    }


def _live_smoke(
    *,
    probe_path: str,
    expected_statuses: list[int],
    recommended_command: str,
    response_assertions: dict[str, Any],
) -> dict[str, Any]:
    return {
        "probe_path": probe_path,
        "expected_statuses": expected_statuses,
        "proof_level": "live_backend_smoke_plan",
        "blocked_semantics": BLOCKED_BY_ENVIRONMENT_SEMANTICS,
        "recommended_command": recommended_command,
        "response_assertions": response_assertions,
    }


def _real_backend_browser_smoke(
    *,
    route_path: str,
    readiness_gate: str,
    browser_assertions: list[str],
) -> dict[str, Any]:
    return {
        "proof_level": "real_backend_browser_smoke_plan",
        "test_file": REAL_BACKEND_BROWSER_SMOKE_TEST_FILE,
        "route_path": route_path,
        "readiness_gate": readiness_gate,
        "blocked_semantics": (
            "Real-backend browser smoke requires frontend and backend readiness; "
            "SKIP_BACKEND_CHECK=1, backend unreachable, auth failure, or missing seed data must be classified "
            "as blocked_by_environment or data_setup_missing, not counted as passed. "
            "Mocked rails are not real proof, and this plan does not claim production, Docker, Celery, or scheduler completion."
        ),
        "browser_assertions": browser_assertions,
    }


def _async_execution_readiness(
    *,
    requires_worker: bool,
    async_surfaces: list[str],
    verification_artifact: str,
) -> dict[str, Any]:
    return {
        "proof_level": "async_worker_readiness_plan",
        "process_stats_probe": PROCESS_STATS_PROBE_PATH,
        "requires_worker": requires_worker,
        "async_surfaces": async_surfaces,
        "blocked_semantics": (
            "celery_worker_unavailable, process stats unreachable, missing queue heartbeat, or stale async task "
            "readback means blocked_by_environment or async_worker_readiness_missing, not passed. "
            "Backend/browser passed does not prove worker/async passed, and this plan does not claim Celery worker, "
            "scheduler, Docker, or production completion."
        ),
        "verification_artifact": verification_artifact,
    }


def _async_task_readback(
    *,
    requires_worker_readback: bool,
    readback_artifact: str,
    readback_paths: list[str],
    required_events: list[str],
    terminal_states: list[str],
    blocked_semantics: str,
) -> dict[str, Any]:
    return {
        "proof_level": "async_task_readback_contract",
        "requires_worker_readback": requires_worker_readback,
        "readback_artifact": readback_artifact,
        "readback_paths": readback_paths,
        "required_events": required_events,
        "terminal_states": terminal_states,
        "blocked_semantics": blocked_semantics,
    }


def _trace_baseline(*, live_smoke: dict[str, Any]) -> dict[str, Any]:
    probe_path = str(live_smoke.get("probe_path") or "")
    response_assertions = live_smoke.get("response_assertions")
    envelope_required = (
        response_assertions.get("envelope_required", True)
        if isinstance(response_assertions, dict)
        else True
    )
    body_meta_trace_required = bool(envelope_required)

    return {
        "contract_version": TRACE_BASELINE_CONTRACT_VERSION,
        "proof_level": "live_backend_trace_baseline_contract",
        "runner_script": TRACE_BASELINE_RUNNER_SCRIPT,
        "recommended_command": TRACE_BASELINE_RECOMMENDED_COMMAND,
        "probe_path": probe_path,
        "request_headers": {
            "x_trace_id": "required",
            "x_request_id": "required",
            "value_source": "runner generated per line trace id",
        },
        "response_headers": {
            "required": ["x-trace-id", "x-request-id"],
            "propagation_rule": "response header values must equal the request trace id",
        },
        "body_meta_trace": {
            "required": body_meta_trace_required,
            "field": "meta.trace_id",
            "exempt_probe_paths": (
                [] if body_meta_trace_required else list(TRACE_BASELINE_BODY_TRACE_EXEMPT_PROBE_PATHS)
            ),
            "exemption_reason": (
                None
                if body_meta_trace_required
                else "health/deep returns a non-envelope runtime payload; trace is asserted through headers"
            ),
        },
        "duration_evidence": {
            "required": True,
            "default_slow_threshold_ms": TRACE_BASELINE_DEFAULT_SLOW_THRESHOLD_MS,
            "required_artifact_fields": [
                "matrix.duration_ms",
                "lines[].duration_ms",
                "lines[].slow_request",
                "lines[].slow_threshold_ms",
                "summary.slow_request_count",
            ],
        },
        "failure_classification": {
            "endpoint_unreachable": "blocked_by_environment",
            "header_trace_id": "trace_propagation_failed",
            "header_request_id": "trace_propagation_failed",
            "body_meta_trace_id": "trace_envelope_meta_failed",
            "slow_request": "trace_latency_observation",
        },
        "completion_claim": "does_not_claim_production_or_scheduler_completion",
    }


def _response_assertions(
    *,
    required_data_paths: list[str],
    semantic_fields: list[str],
    failure_classification: dict[str, str],
    envelope_required: bool = True,
) -> dict[str, Any]:
    return {
        "envelope_required": envelope_required,
        "required_data_paths": required_data_paths,
        "semantic_fields": semantic_fields,
        "failure_classification": failure_classification,
    }


def _line(
    *,
    line_key: str,
    user_task: str,
    entrypoints: list[str],
    api_groups: list[str],
    evidence_contracts: list[str],
    current_gaps: list[str],
    next_remediation: list[str],
    robustness_controls: list[str],
    verification_commands: list[str],
    live_smoke: dict[str, Any],
    real_backend_browser_smoke: dict[str, Any],
    async_execution_readiness: dict[str, Any],
    async_task_readback: dict[str, Any],
) -> dict[str, Any]:
    return {
        "line_key": line_key,
        "user_task": user_task,
        "entrypoints": entrypoints,
        "api_groups": api_groups,
        "evidence_contracts": evidence_contracts,
        "current_gaps": current_gaps,
        "next_remediation": next_remediation,
        "robustness_controls": robustness_controls,
        "verification_commands": verification_commands,
        "live_smoke": live_smoke,
        "trace_baseline": _trace_baseline(live_smoke=live_smoke),
        "real_backend_browser_smoke": real_backend_browser_smoke,
        "async_execution_readiness": async_execution_readiness,
        "async_task_readback": async_task_readback,
    }


def build_evidence_matrix() -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=api.business_lines witness=test:test_w01_meta",
]:
    """Project the current static readiness contract without claiming observations."""

    return {
        "contract_version": CONTRACT_VERSION,
        "vocabulary_version": BUSINESS_LINE_VOCABULARY_VERSION,
        "matrix_diagnostics_guidance": {
            "source_lane": SCHEDULED_MATRIX_LANE,
            "source_artifact": "nightly-manifest.json:matrix_diagnostics",
            "consumer_surface": "OpsPage:/api/v1/business-lines/evidence-matrix",
            "recommended_display_order": list(MATRIX_DIAGNOSTICS_RECOMMENDED_DISPLAY_ORDER),
            "required_fields": list(MATRIX_DIAGNOSTICS_REQUIRED_FIELDS),
            "blocked_project_fields": list(MATRIX_DIAGNOSTICS_BLOCKED_PROJECT_FIELDS),
            "classification_boundary": {
                "scheduled_run_blocked": (
                    "scheduled_run_blocked is blocked scheduler-lane evidence for triage, "
                    "not completion proof."
                ),
                "scheduled_run_evidence": (
                    "Only scheduled_run_evidence can close scheduled evidence for the matrix lane."
                ),
                "completion_claim": "does_not_claim_real_scheduler_run",
            },
        },
        "coverage": {
            "covered_line_count": len(LINE_KEYS),
            "covered_line_keys": list(LINE_KEYS),
            "not_admin_only": True,
        },
        "worker_readback": {
            "contract_version": "business_line.worker_readback_contract.v2",
            "covered_line_keys": list(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
            "runner_script": ASYNC_TASK_READBACK_LIVE_SAMPLE_RUNNER_SCRIPT,
            "manifest_cli": ASYNC_TASK_READBACK_WORKER_MANIFEST_CLI,
            "manifest_checker_script": ASYNC_TASK_READBACK_WORKER_MANIFEST_CHECKER_SCRIPT,
            "candidate_builder_script": ASYNC_TASK_READBACK_WORKER_MANIFEST_CANDIDATE_BUILDER_SCRIPT,
            "evidence_chain_script": ASYNC_TASK_READBACK_WORKER_EVIDENCE_CHAIN_SCRIPT,
            "artifact_checker_script": ASYNC_TASK_READBACK_ARTIFACT_CHECKER_SCRIPT,
            "required_manifest_fields": [
                "line_key",
                "task_id_or_run_id",
                "worker_name",
                "queue",
                "trace_id",
                "readback_endpoint_or_path",
                "terminal_events",
            ],
            "required_live_readback_fields": [
                "matching_task_id_or_run_id",
                "worker_name",
                "queue",
                "trace_id",
                "success_status",
                "terminal_event",
                "required_events",
            ],
            "process_runtime_endpoints": [
                "/api/v1/process/tasks?line_key={line_key}&limit=...",
                "/api/v1/process/logs?line_key={line_key}&limit=...",
            ],
            "aggregation_contract": (
                "Matrix aggregation may report passed only when every selected project_key and every "
                "worker-required line has independently passed; any failed or blocked project row keeps "
                "the matrix result failed or blocked."
            ),
            "blocked_semantics": (
                "Missing real task_id_or_run_id, worker_name, queue, trace_id, readback location, "
                "worker-consumed terminal event, required event, exact runtime projection, or downstream "
                "artifact consistency means async_task_readback_missing, manifest_qualification_failed, or "
                "blocked_by_environment, not passed."
            ),
            "completion_claim": "not_observed_without_live_worker_readback",
        },
        "scheduled_observation": {
            "observation_status": "not_observed",
            "scheduled_run_evidence": "not_observed",
            "install_status": "unknown",
            "codex_retirement_status": "not_observed",
            "evidence_endpoint": "/api/v1/business-lines/scheduled-matrix-artifact-summary",
            "summary_contract_version": SCHEDULED_MATRIX_ARTIFACT_SUMMARY_CONTRACT_VERSION,
            "reason": (
                "This projection does not observe a scheduler run, repository configuration installation, "
                "or Codex retirement state. Read the scheduled summary endpoint for artifact observations."
            ),
            "completion_claim": "not_observed",
        },
        "ui_boundary": {
            "reset_telemetry": {
                "event_name": "reset_empty_warning_view",
                "event_scope": "ui_event_log_only",
                "filter_transition": {"from": "warning_only", "to": "all"},
                "sort_behavior": "unchanged",
                "api_payload_behavior": "unchanged",
                "scheduled_evidence_write": "none",
                "scheduled_completion_proof": False,
                "scheduled_evidence_controller": "scheduled_run_evidence",
                "telemetry_scope": (
                    "Ops reset telemetry records only the warning_only-to-all UI filter transition; "
                    "it keeps sort and API payload unchanged and writes no scheduled evidence."
                ),
            },
            "read_only_context": {
                **READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS,
                "scheduled_evidence_controller": "scheduled_run_evidence",
                "observation_status": "not_applicable_ui_boundary",
                "boundary": (
                    "UI-only read-only context is not report proof, quality gate input, or "
                    "scheduled_run_evidence proof. It is not report proof, is not quality gate input, "
                    "and is not scheduled_run_evidence proof; it does not change export audit outcome."
                ),
            },
        },
        "lines": [
            _line(
                            line_key="ingest",
                            user_task="Submit URLs and source materials, then inspect ingestion history, task state, failures, and logs.",
                            entrypoints=["IngestPage", "CrawlerManagePage"],
                            api_groups=["/api/v1/ingest/*", "/api/v1/process/*", "/api/v1/crawler/*"],
                            evidence_contracts=[
                                "tests/core_business/test_ingest_core_contract.py",
                                "tests/integration/test_frontend_ingest_flow_smoke_unittest.py",
                                "tests/e2e/ingest-single-url.spec.ts",
                            ],
                            current_gaps=[
                                "Submission, execution, indexing, and frontend feedback are not fully unified under one task model.",
                                "Provider degradation is not consistently visible to users.",
                            ],
                            next_remediation=[
                                "Define a unified ingestion submission object with idempotency and traceable lifecycle events.",
                                "Expose provider fallback and retry state in the task readback contract.",
                            ],
                            robustness_controls=[
                                "Idempotency key for repeated submissions.",
                                "Provider failure classification with recoverable user-facing status.",
                                "Trace chain from ingest request to search/index readback.",
                            ],
                            verification_commands=[
                                "python3.11 -m pytest tests/core_business/test_ingest_core_contract.py -q",
                                "python3.11 -m pytest tests/integration/test_frontend_ingest_flow_smoke_unittest.py -q",
                            ],
                            live_smoke=_live_smoke(
                                probe_path="/api/v1/ingest/history?limit=1",
                                expected_statuses=[200],
                                recommended_command=(
                                    "curl -sS -m 5 -o /tmp/business-line-ingest.json -w '%{http_code}\\n' "
                                    "http://127.0.0.1:8000/api/v1/ingest/history?limit=1"
                                ),
                                response_assertions=_response_assertions(
                                    required_data_paths=["status", "data", "error", "meta"],
                                    semantic_fields=["status", "data"],
                                    failure_classification={
                                        "transport": "blocked_by_environment",
                                        "missing_envelope": "response_contract_regression",
                                        "missing_required_path": "semantic_smoke_failed",
                                    },
                                ),
                            ),
                            real_backend_browser_smoke=_real_backend_browser_smoke(
                                route_path="/#/workbench/ingest",
                                readiness_gate=(
                                    "requireRealBackendReadiness must pass before the browser opens the ingest workbench; "
                                    "endpoint probes should include ingest history or crawler-backed source readiness."
                                ),
                                browser_assertions=[
                                    "The real backend browser run waits for ingest/crawler network responses instead of mocked fixtures.",
                                    "The ingest workbench or crawler-backed submission surface is visible with project_key context.",
                                    "Transport failures are classified as blocked_by_environment rather than a passed smoke.",
                                ],
                            ),
                            async_execution_readiness=_async_execution_readiness(
                                requires_worker=True,
                                async_surfaces=[
                                    "ingest submission task lifecycle",
                                    "crawler-backed fetch and parse queue",
                                    "index handoff and process history readback",
                                ],
                                verification_artifact="business_line_async_worker_readiness.ingest.v1",
                            ),
                            async_task_readback=_async_task_readback(
                                requires_worker_readback=True,
                                readback_artifact="business_line_async_task_readback.ingest.v1",
                                readback_paths=[
                                    "/api/v1/process/tasks/{task_id}",
                                    "/api/v1/ingest/history/{submission_id}",
                                    "/api/v1/process/logs?task_id={task_id}",
                                ],
                                required_events=[
                                    "submission_accepted",
                                    "task_queued",
                                    "worker_started",
                                    "source_fetch_completed",
                                    "index_handoff_recorded",
                                    "readback_persisted",
                                ],
                                terminal_states=[
                                    "completed",
                                    "failed",
                                    "retry_exhausted",
                                    "blocked_by_environment",
                                ],
                                blocked_semantics=(
                                    "A reachable worker or process stats endpoint is insufficient. Missing ingest task id, "
                                    "worker-consumed event chain, persisted history row, or terminal state means "
                                    "async_task_readback_missing or blocked_by_environment, not passed."
                                ),
                            ),
                        ),
                        _line(
                            line_key="search_discovery_index",
                            user_task="Search stored content, run discovery, initialize indexes, and inspect search analytics.",
                            entrypoints=["DashboardPage", "CatalogPage", "RawDataPage"],
                            api_groups=[
                                "/api/v1/search",
                                "/api/v1/discovery/*",
                                "/api/v1/indexer/policy",
                                "/api/v1/dashboard/search-analytics",
                            ],
                            evidence_contracts=[
                                "tests/core_business/test_search_core_contract.py",
                                "tests/integration/test_search_api_unittest.py",
                                "tests/contract/test_openapi_contracts_unittest.py",
                            ],
                            current_gaps=[
                                "Search, discovery, indexing, and dashboard analytics do not share one persisted search-run record.",
                                "Index freshness and provider trace are not consistently exposed at the frontend boundary.",
                            ],
                            next_remediation=[
                                "Persist a search run object that links query, provider trace, index freshness, and result quality.",
                                "Surface freshness explanation and retrieval quality metrics in the search response.",
                            ],
                            robustness_controls=[
                                "Provider timeout and fallback trace.",
                                "Index freshness readback contract.",
                                "Quality replay gate for retrieval regressions.",
                            ],
                            verification_commands=[
                                "python3.11 -m pytest tests/core_business/test_search_core_contract.py -q",
                                "python3.11 -m pytest tests/integration/test_search_api_unittest.py -q",
                            ],
                            live_smoke=_live_smoke(
                                probe_path="/api/v1/search?q=smoke&limit=1",
                                expected_statuses=[200],
                                recommended_command=(
                                    "curl -sS -m 5 -o /tmp/business-line-search.json -w '%{http_code}\\n' "
                                    "'http://127.0.0.1:8000/api/v1/search?q=smoke&limit=1'"
                                ),
                                response_assertions=_response_assertions(
                                    required_data_paths=["status", "data/query", "data/results", "data/top_k"],
                                    semantic_fields=["data/query", "data/results", "data/index_backend"],
                                    failure_classification={
                                        "transport": "blocked_by_environment",
                                        "backend_unavailable": "search_dependency_blocked",
                                        "missing_required_path": "semantic_smoke_failed",
                                    },
                                ),
                            ),
                            real_backend_browser_smoke=_real_backend_browser_smoke(
                                route_path="/#/visual/catalog",
                                readiness_gate=(
                                    "requireRealBackendReadiness must pass and catalog/search endpoints must respond before "
                                    "the browser assertion is counted as real-backend proof."
                                ),
                                browser_assertions=[
                                    "The browser reaches the catalog/search discovery surface with a live backend.",
                                    "The run observes a search, catalog, or dashboard analytics response from the real backend.",
                                    "Missing index/search data is classified as data_setup_missing, not as a successful smoke.",
                                ],
                            ),
                            async_execution_readiness=_async_execution_readiness(
                                requires_worker=True,
                                async_surfaces=[
                                    "discovery run scheduling",
                                    "index initialization and refresh",
                                    "retrieval quality replay over persisted search runs",
                                ],
                                verification_artifact="business_line_async_worker_readiness.search_discovery_index.v1",
                            ),
                            async_task_readback=_async_task_readback(
                                requires_worker_readback=True,
                                readback_artifact="business_line_async_task_readback.search_discovery_index.v1",
                                readback_paths=[
                                    "/api/v1/discovery/runs/{run_id}",
                                    "/api/v1/search/runs/{run_id}",
                                    "/api/v1/indexer/status?run_id={run_id}",
                                ],
                                required_events=[
                                    "search_or_discovery_run_accepted",
                                    "task_queued",
                                    "worker_started",
                                    "index_refresh_started",
                                    "index_refresh_completed",
                                    "results_readback_persisted",
                                ],
                                terminal_states=[
                                    "completed",
                                    "failed",
                                    "stale_index_blocked",
                                    "blocked_by_environment",
                                ],
                                blocked_semantics=(
                                    "Worker visibility does not prove discovery/index task consumption. Missing run id, "
                                    "index refresh events, persisted search run readback, or terminal state means "
                                    "async_task_readback_missing or blocked_by_environment, not passed."
                                ),
                            ),
                        ),
                        _line(
                            line_key="resource_source_library",
                            user_task="Manage site entries, URL pools, source-library items, recommendations, and candidate recovery.",
                            entrypoints=["ResourcePage", "CatalogPage"],
                            api_groups=["/api/v1/resource_pool/*", "/api/v1/source_library/*"],
                            evidence_contracts=[
                                "tests/core_business/test_resource_pool_core_contract.py",
                                "tests/core_business/test_source_library_core_contract.py",
                                "tests/unit/test_source_library_*",
                            ],
                            current_gaps=[
                                "Source metadata, executable resources, review lifecycle, and project reuse need a stronger product boundary.",
                                "External site availability and adapter quality still dominate runtime reliability.",
                            ],
                            next_remediation=[
                                "Unify source-library item state, executable plan, and review status into one read model.",
                                "Add project-scope reuse controls and stale-source lifecycle transitions.",
                            ],
                            robustness_controls=[
                                "Single-source guard for site entries.",
                                "Execution fact contract for resource actions.",
                                "Adapter failure mapping and retry-safe capture paths.",
                            ],
                            verification_commands=[
                                "python3.11 -m pytest tests/core_business/test_resource_pool_core_contract.py -q",
                                "python3.11 -m pytest tests/core_business/test_source_library_core_contract.py -q",
                            ],
                            live_smoke=_live_smoke(
                                probe_path="/api/v1/resource_pool/urls?limit=1",
                                expected_statuses=[200],
                                recommended_command=(
                                    "curl -sS -m 5 -o /tmp/business-line-resource.json -w '%{http_code}\\n' "
                                    "'http://127.0.0.1:8000/api/v1/resource_pool/urls?limit=1'"
                                ),
                                response_assertions=_response_assertions(
                                    required_data_paths=["status", "data/items", "meta/pagination"],
                                    semantic_fields=["data/items", "meta/pagination/total"],
                                    failure_classification={
                                        "transport": "blocked_by_environment",
                                        "scope_error": "resource_scope_resolution_failed",
                                        "missing_required_path": "semantic_smoke_failed",
                                    },
                                ),
                            ),
                            real_backend_browser_smoke=_real_backend_browser_smoke(
                                route_path="/#/admin/resources",
                                readiness_gate=(
                                    "requireRealBackendReadiness must pass; source_library and resource_pool endpoint probes "
                                    "must return usable payloads before UI assertions are credited."
                                ),
                                browser_assertions=[
                                    "The resource management page is visible while using real source_library/resource_pool responses.",
                                    "The run waits for source_library/items and resource_pool/site_entries network responses.",
                                    "Adapter or seed-data gaps are classified separately from browser rendering failures.",
                                ],
                            ),
                            async_execution_readiness=_async_execution_readiness(
                                requires_worker=True,
                                async_surfaces=[
                                    "source-library recommendation refresh",
                                    "resource adapter capture queue",
                                    "candidate recovery and stale-source lifecycle jobs",
                                ],
                                verification_artifact="business_line_async_worker_readiness.resource_source_library.v1",
                            ),
                            async_task_readback=_async_task_readback(
                                requires_worker_readback=True,
                                readback_artifact="business_line_async_task_readback.resource_source_library.v1",
                                readback_paths=[
                                    "/api/v1/source_library/items/{item_id}",
                                    "/api/v1/resource_pool/actions/{action_id}",
                                    "/api/v1/process/tasks/{task_id}",
                                ],
                                required_events=[
                                    "resource_action_accepted",
                                    "task_queued",
                                    "worker_started",
                                    "adapter_capture_completed",
                                    "source_lifecycle_updated",
                                    "readback_persisted",
                                ],
                                terminal_states=[
                                    "completed",
                                    "failed",
                                    "adapter_blocked",
                                    "blocked_by_environment",
                                ],
                                blocked_semantics=(
                                    "A ready worker is not sufficient for source-library proof. Missing action/task readback, "
                                    "adapter capture events, lifecycle state, or terminal state means "
                                    "async_task_readback_missing or blocked_by_environment, not passed."
                                ),
                            ),
                        ),
                        _line(
                            line_key="projects_config_workflow",
                            user_task="Create or switch projects, configure runtime settings and LLM providers, and inspect workflow history.",
                            entrypoints=["ProjectsPage", "SettingsPage", "ProcessPage"],
                            api_groups=[
                                "/api/v1/projects/*",
                                "/api/v1/config/*",
                                "/api/v1/project-customization/*",
                                "/api/v1/llm-config/*",
                                "/api/v1/process/*",
                            ],
                            evidence_contracts=[
                                "tests/core_business/test_projects_core_contract.py",
                                "tests/core_business/test_project_customization_core_contract.py",
                                "tests/integration/test_project_schema_guard_unittest.py",
                            ],
                            current_gaps=[
                                "Configuration versions, dry-run behavior, rollback semantics, and impact prompts remain incomplete.",
                                "Project context enforcement depends on several boundary checks instead of one visible contract.",
                            ],
                            next_remediation=[
                                "Add config version readback with dry-run diff and rollback target metadata.",
                                "Make project-context enforcement visible in process and customization responses.",
                            ],
                            robustness_controls=[
                                "Project schema guard.",
                                "Dry-run validation before mutating configuration.",
                                "Explicit project-key resolution and fallback headers.",
                            ],
                            verification_commands=[
                                "python3.11 -m pytest tests/core_business/test_projects_core_contract.py -q",
                                "python3.11 -m pytest tests/core_business/test_project_customization_core_contract.py -q",
                            ],
                            live_smoke=_live_smoke(
                                probe_path="/api/v1/projects",
                                expected_statuses=[200],
                                recommended_command=(
                                    "curl -sS -m 5 -o /tmp/business-line-projects.json -w '%{http_code}\\n' "
                                    "http://127.0.0.1:8000/api/v1/projects"
                                ),
                                response_assertions=_response_assertions(
                                    required_data_paths=["status", "data/items", "error", "meta"],
                                    semantic_fields=["data/items"],
                                    failure_classification={
                                        "transport": "blocked_by_environment",
                                        "control_plane_degraded": "projects_config_readback_degraded",
                                        "missing_required_path": "semantic_smoke_failed",
                                    },
                                ),
                            ),
                            real_backend_browser_smoke=_real_backend_browser_smoke(
                                route_path="/#/admin/projects",
                                readiness_gate=(
                                    "requireRealBackendReadiness must pass and /api/v1/projects must return project rows "
                                    "before the Projects browser smoke is considered real proof."
                                ),
                                browser_assertions=[
                                    "The projects page heading is visible after a real /api/v1/projects response.",
                                    "The projects list test id is visible without using mocked rail data.",
                                    "Empty or inaccessible project setup is classified as data_setup_missing or blocked_by_environment.",
                                ],
                            ),
                            async_execution_readiness=_async_execution_readiness(
                                requires_worker=False,
                                async_surfaces=[
                                    "process history readback for project-scoped configuration actions",
                                    "configuration impact preview artifacts",
                                    "rollback target verification records",
                                ],
                                verification_artifact="business_line_async_worker_readiness.projects_config_workflow.v1",
                            ),
                            async_task_readback=_async_task_readback(
                                requires_worker_readback=False,
                                readback_artifact="business_line_async_task_readback.projects_config_workflow.v1",
                                readback_paths=[
                                    "/api/v1/projects/{project_key}",
                                    "/api/v1/config/effective?project_key={project_key}",
                                    "/api/v1/process/history?entity=project_config",
                                ],
                                required_events=[
                                    "config_validation_started",
                                    "dry_run_recorded",
                                    "config_version_written",
                                    "project_scope_audit_recorded",
                                ],
                                terminal_states=[
                                    "applied",
                                    "rejected",
                                    "rollback_required",
                                    "blocked_by_environment",
                                ],
                                blocked_semantics=(
                                    "This line does not require worker readback, but process/config/audit readback is required. "
                                    "Missing effective config, dry-run evidence, version/audit record, or terminal state means "
                                    "process_config_audit_readback_missing or blocked_by_environment, not passed."
                                ),
                            ),
                        ),
                        _line(
                            line_key="dashboard_admin_governance",
                            user_task="Inspect metrics, reports, policy or market state, product and topic views, and governance actions.",
                            entrypoints=["DashboardPage", "PolicyPage", "OpsPage"],
                            api_groups=[
                                "/api/v1/dashboard/*",
                                "/api/v1/admin/*",
                                "/api/v1/policies/*",
                                "/api/v1/market/*",
                                "/api/v1/products",
                                "/api/v1/topics",
                                "/api/v1/reports",
                            ],
                            evidence_contracts=[
                                "tests/core_business/test_admin_dashboard_process_core_contract.py",
                                "tests/integration/test_admin_graph_standardization_unittest.py",
                                "tests/integration/test_llm_report_api_unittest.py",
                            ],
                            current_gaps=[
                                "Metric drilldown, report citation, governance preview, audit trail, and pending-action queues are not unified.",
                                "Data quality and metric definition drift can change dashboard interpretation.",
                            ],
                            next_remediation=[
                                "Connect dashboard metrics to source evidence and report citations.",
                                "Add governance preview and pending-action readback before admin mutations.",
                            ],
                            robustness_controls=[
                                "Audit trail for governance mutations.",
                                "Metric provenance and stale-data markers.",
                                "Admin action preview with validation errors mapped to envelope responses.",
                            ],
                            verification_commands=[
                                "python3.11 -m pytest tests/core_business/test_admin_dashboard_process_core_contract.py -q",
                                "python3.11 -m pytest tests/integration/test_llm_report_api_unittest.py -q",
                            ],
                            live_smoke=_live_smoke(
                                probe_path="/api/v1/dashboard/stats",
                                expected_statuses=[200],
                                recommended_command=(
                                    "curl -sS -m 5 -o /tmp/business-line-dashboard.json -w '%{http_code}\\n' "
                                    "http://127.0.0.1:8000/api/v1/dashboard/stats"
                                ),
                                response_assertions=_response_assertions(
                                    required_data_paths=[
                                        "status",
                                        "data/documents/total",
                                        "data/sources/total",
                                        "data/tasks/total",
                                    ],
                                    semantic_fields=["data/documents", "data/sources", "data/tasks"],
                                    failure_classification={
                                        "transport": "blocked_by_environment",
                                        "database_unavailable": "dashboard_dependency_blocked",
                                        "missing_required_path": "semantic_smoke_failed",
                                    },
                                ),
                            ),
                            real_backend_browser_smoke=_real_backend_browser_smoke(
                                route_path="/#/visual/dashboard",
                                readiness_gate=(
                                    "requireRealBackendReadiness must pass and dashboard stats must include documents, sources, "
                                    "or tasks evidence before the browser smoke is counted."
                                ),
                                browser_assertions=[
                                    "The dashboard page waits for a real /api/v1/dashboard/stats response.",
                                    "The data dashboard heading is visible after backend stats are loaded.",
                                    "Governance/dashboard data gaps are separated from transport blockers and UI failures.",
                                ],
                            ),
                            async_execution_readiness=_async_execution_readiness(
                                requires_worker=False,
                                async_surfaces=[
                                    "dashboard task metric aggregation",
                                    "report generation status readback",
                                    "governance pending-action audit queue",
                                ],
                                verification_artifact="business_line_async_worker_readiness.dashboard_admin_governance.v1",
                            ),
                            async_task_readback=_async_task_readback(
                                requires_worker_readback=False,
                                readback_artifact="business_line_async_task_readback.dashboard_admin_governance.v1",
                                readback_paths=[
                                    "/api/v1/dashboard/stats",
                                    "/api/v1/admin/audit?scope=governance",
                                    "/api/v1/reports?limit=1",
                                ],
                                required_events=[
                                    "metric_snapshot_requested",
                                    "provenance_loaded",
                                    "governance_preview_recorded",
                                    "audit_record_persisted",
                                ],
                                terminal_states=[
                                    "available",
                                    "stale_data_blocked",
                                    "rejected",
                                    "blocked_by_environment",
                                ],
                                blocked_semantics=(
                                    "This line does not require worker readback, but dashboard/report/governance audit "
                                    "readback is required. Missing metric provenance, report status, audit row, or terminal "
                                    "state means process_config_audit_readback_missing or blocked_by_environment, not passed."
                                ),
                            ),
                        ),
                        _line(
                            line_key="writing_knowledge_graph_agent",
                            user_task="Edit writing artifacts, use knowledge cards and graphs, chat with agents, and run agent batches.",
                            entrypoints=["WritingWorkbenchPage", "GraphPage", "CodexAgentPage", "LlmDesignerPage"],
                            api_groups=[
                                "/api/v1/writing/*",
                                "/api/v1/typed_knowledge/*",
                                "/api/v1/workflow_graph/*",
                                "/api/v1/agent-chat/*",
                                "/api/v1/agent-sessions/*",
                                "/api/v1/agent-batch/*",
                            ],
                            evidence_contracts=[
                                "tests/integration/test_writing_api_unittest.py",
                                "tests/integration/test_typed_knowledge_api_route_unittest.py",
                                "tests/integration/test_workflow_graph_api_unittest.py",
                                "tests/integration/test_agent_chat_api_unittest.py",
                                "tests/integration/test_agent_sessions_api_unittest.py",
                                "tests/integration/test_agent_batch_workflow_closure_unittest.py",
                            ],
                            current_gaps=[
                                "Evidence, knowledge, graph, writing, and agent tasks do not yet share one citation and approval model.",
                                "Async agent events and approval idempotency remain sensitive to context drift.",
                            ],
                            next_remediation=[
                                "Define a cross-artifact reference contract from knowledge handoff to writing and graph actions.",
                                "Add idempotent approval and rollback readback for long-running agent batches.",
                            ],
                            robustness_controls=[
                                "Context-boundary validation for typed knowledge handoff.",
                                "Agent session state readback.",
                                "Batch event stream with replay-safe approvals.",
                            ],
                            verification_commands=[
                                "python3.11 -m pytest tests/integration/test_writing_api_unittest.py -q",
                                "python3.11 -m pytest tests/integration/test_agent_batch_workflow_closure_unittest.py -q",
                            ],
                            live_smoke=_live_smoke(
                                probe_path="/api/v1/writing/templates",
                                expected_statuses=[200],
                                recommended_command=(
                                    "curl -sS -m 5 -o /tmp/business-line-writing.json -w '%{http_code}\\n' "
                                    "http://127.0.0.1:8000/api/v1/writing/templates"
                                ),
                                response_assertions=_response_assertions(
                                    required_data_paths=["status", "data/items", "error", "meta"],
                                    semantic_fields=["data/items", "data/items/template_key"],
                                    failure_classification={
                                        "transport": "blocked_by_environment",
                                        "missing_templates": "writing_template_contract_regression",
                                        "missing_required_path": "semantic_smoke_failed",
                                    },
                                ),
                            ),
                            real_backend_browser_smoke=_real_backend_browser_smoke(
                                route_path="/#/visual/graph/market",
                                readiness_gate=(
                                    "requireRealBackendReadiness must pass; graph config and market graph endpoint probes must "
                                    "succeed as the current real-backend browser page covering the graph side of the writing/knowledge/agent line."
                                ),
                                browser_assertions=[
                                    "The graph page waits for real project-customization graph config and admin market graph responses.",
                                    "The market graph heading and node-count affordance are visible with live backend data.",
                                    "This is graph-side real proof for the writing/knowledge/agent line and does not claim agent batch or scheduler completion.",
                                ],
                            ),
                            async_execution_readiness=_async_execution_readiness(
                                requires_worker=True,
                                async_surfaces=[
                                    "agent-batch execution queue",
                                    "agent session event stream replay",
                                    "writing approval and rollback task readback",
                                ],
                                verification_artifact="business_line_async_worker_readiness.writing_knowledge_graph_agent.v1",
                            ),
                            async_task_readback=_async_task_readback(
                                requires_worker_readback=True,
                                readback_artifact="business_line_async_task_readback.writing_knowledge_graph_agent.v1",
                                readback_paths=[
                                    "/api/v1/agent-batch/{batch_id}",
                                    "/api/v1/agent-sessions/{session_id}/events",
                                    "/api/v1/writing/artifacts/{artifact_id}/approvals",
                                ],
                                required_events=[
                                    "agent_batch_submitted",
                                    "task_queued",
                                    "worker_started",
                                    "agent_event_persisted",
                                    "approval_state_recorded",
                                    "artifact_readback_persisted",
                                ],
                                terminal_states=[
                                    "completed",
                                    "failed",
                                    "approval_required",
                                    "rollback_completed",
                                    "blocked_by_environment",
                                ],
                                blocked_semantics=(
                                    "Worker readiness does not prove agent or writing task consumption. Missing batch/session "
                                    "readback, persisted agent events, approval state, artifact readback, or terminal state means "
                                    "async_task_readback_missing or blocked_by_environment, not passed."
                                ),
                            ),
                        ),
                        _line(
                            line_key="runtime_ops",
                            user_task="Start, stop, inspect, and diagnose the Docker or local runtime stack.",
                            entrypoints=["OpsPage", "main/ops/start-all.sh", "main/ops/restart.sh", "main/ops/launcher-ui/*"],
                            api_groups=["/api/v1/health", "/api/v1/health/deep", "/metrics"],
                            evidence_contracts=[
                                "main/ops/test-docker-startup.sh",
                                "tests/integration/test_runtime_ops_error_contract_unittest.py",
                                "tests/e2e/test_deep_health_smoke_e2e.py",
                            ],
                            current_gaps=[
                                "Startup state, diagnostic bundles, recovery guidance, and e2e preconditions are not one runtime contract.",
                                "Mixed Docker/local environments and occupied ports remain common failure modes.",
                            ],
                            next_remediation=[
                                "Publish a startup contract that classifies runtime mode and missing dependencies.",
                                "Add a diagnostic bundle endpoint or artifact that links service health to recovery commands.",
                            ],
                            robustness_controls=[
                                "Runtime mode detection.",
                                "Dependency reachability probes.",
                                "Envelope-compatible error mapping for ops failures.",
                            ],
                            verification_commands=[
                                "python3.11 -m pytest tests/integration/test_runtime_ops_error_contract_unittest.py -q",
                                "python3.11 -m pytest tests/e2e/test_deep_health_smoke_e2e.py -q",
                            ],
                            live_smoke=_live_smoke(
                                probe_path="/api/v1/health/deep",
                                expected_statuses=[200],
                                recommended_command=(
                                    "curl -sS -m 5 -o /tmp/business-line-runtime.json -w '%{http_code}\\n' "
                                    "http://127.0.0.1:8000/api/v1/health/deep"
                                ),
                                response_assertions=_response_assertions(
                                    required_data_paths=["status", "details", "database"],
                                    semantic_fields=["status", "database", "elasticsearch"],
                                    failure_classification={
                                        "transport": "blocked_by_environment",
                                        "degraded": "runtime_dependency_degraded",
                                        "missing_required_path": "semantic_smoke_failed",
                                    },
                                    envelope_required=False,
                                ),
                            ),
                            real_backend_browser_smoke=_real_backend_browser_smoke(
                                route_path="/#/admin/ops",
                                readiness_gate=(
                                    "requireRealBackendReadiness must pass; health, admin stats, and document-list probes must "
                                    "return real backend payloads before ops browser assertions are credited."
                                ),
                                browser_assertions=[
                                    "The ops page waits for real /api/v1/health and /api/v1/admin/stats responses.",
                                    "The runtime status heading is visible after live backend readiness checks pass.",
                                    "Health degradation is classified as blocked_by_environment or functional_failure, not a mocked pass.",
                                ],
                            ),
                            async_execution_readiness=_async_execution_readiness(
                                requires_worker=False,
                                async_surfaces=[
                                    "process stats worker readiness probe",
                                    "queue heartbeat and stale task diagnostics",
                                    "runtime recovery artifact generation",
                                ],
                                verification_artifact="business_line_async_worker_readiness.runtime_ops.v1",
                            ),
                            async_task_readback=_async_task_readback(
                                requires_worker_readback=False,
                                readback_artifact="business_line_async_task_readback.runtime_ops.v1",
                                readback_paths=[
                                    PROCESS_STATS_PROBE_PATH,
                                    "/api/v1/health/deep",
                                    "/api/v1/process/history?scope=runtime_ops",
                                ],
                                required_events=[
                                    "runtime_probe_started",
                                    "process_stats_collected",
                                    "dependency_health_classified",
                                    "diagnostic_record_persisted",
                                ],
                                terminal_states=[
                                    "healthy",
                                    "degraded",
                                    "blocked_by_environment",
                                    "diagnostic_failed",
                                ],
                                blocked_semantics=(
                                    "This line does not require line-specific worker task consumption, but process/runtime "
                                    "diagnostic readback is required. Missing process stats, health classification, diagnostic "
                                    "record, or terminal state means process_config_audit_readback_missing or "
                                    "blocked_by_environment, not passed."
                                ),
                            ),
                        ),
                    ],
                }


BusinessLineEvidenceMatrixEnvelope = ApiEnvelope[dict[str, Any]]
ScheduledMatrixArtifactSummaryEnvelope = ApiEnvelope[dict[str, Any]]
ScheduledArtifactSummariesEnvelope = ApiEnvelope[dict[str, Any]]
ScheduledArtifactDrilldownEnvelope = ApiEnvelope[dict[str, Any]]


@router.get("/evidence-matrix", response_model=BusinessLineEvidenceMatrixEnvelope)
def get_business_line_evidence_matrix() -> dict[str, Any]:
    return ok(build_evidence_matrix())


@router.get(
    "/scheduled-matrix-artifact-summary",
    response_model=ScheduledMatrixArtifactSummaryEnvelope,
)
def get_scheduled_matrix_artifact_summary() -> dict[str, Any]:
    return ok(build_scheduled_matrix_artifact_summary())


@router.get(
    "/scheduled-artifact-summaries",
    response_model=ScheduledArtifactSummariesEnvelope,
)
def get_scheduled_artifact_summaries() -> dict[str, Any]:
    return ok(build_scheduled_artifact_summaries())


@router.get(
    "/scheduled-artifact-drilldown",
    response_model=ScheduledArtifactDrilldownEnvelope,
)
def get_scheduled_artifact_drilldown() -> dict[str, Any]:
    return ok(build_scheduled_artifact_drilldown())
