from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter

from ..contracts import ApiEnvelope, ok


router = APIRouter(prefix="/business-lines", tags=["business-lines"])

CONTRACT_VERSION = "business_line.evidence_matrix.v1"
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
WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS = [
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "writing_knowledge_graph_agent",
]
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

LINE_KEYS = [
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "projects_config_workflow",
    "dashboard_admin_governance",
    "writing_knowledge_graph_agent",
    "runtime_ops",
]

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
    return Path(__file__).resolve().parents[4]


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
    return {
        "contract_version": CONTRACT_VERSION,
        "source_report": (
            "development/latest-dev-docs/automation-runs/"
            "business-line-user-flow-audit/2026-05-23/README.md"
        ),
        "matrix_diagnostics_guidance": {
            "source_lane": "business_line_worker_readback_project_matrix_nightly",
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
        "batch_orchestration": {
            "batch": "66",
            "strategy": "implementation_boundary_all_lines",
            "statement": "本批按实现边界覆盖所有条线，不把下一批作为本批漏项修补",
            "covered_line_count": len(LINE_KEYS),
            "covered_line_keys": LINE_KEYS,
            "not_admin_only": True,
            "same_batch_live_smoke": {
                "batch": "67",
                "strategy": "same_batch_live_backend_smoke_plan",
                "statement": (
                    "第67批在同批 evidence matrix 中为每条业务线补充 live user-flow smoke 计划；"
                    "该计划只声明可执行后端探针与环境阻塞语义，不宣称生产证明。"
                    "第68批在保留第66批全条线覆盖与第67批 live smoke 语义的基础上，"
                    "补充 response_assertions，使 smoke 从 HTTP 可达升级为响应语义可校验。"
                ),
                "proof_level": "live_backend_smoke_plan",
                "blocked_semantics": BLOCKED_BY_ENVIRONMENT_SEMANTICS,
                "response_assertion_extension": {
                    "batch": "68",
                    "proof_level": "live_backend_response_semantics_plan",
                    "statement": (
                        "每条业务线的 live_smoke 必须声明 envelope、稳定响应路径、"
                        "语义字段和失败分类。"
                    ),
                },
                "real_backend_browser_smoke_extension": {
                    "batch": "69",
                    "proof_level": "real_backend_browser_smoke_plan",
                    "test_file": REAL_BACKEND_BROWSER_SMOKE_TEST_FILE,
                    "statement": (
                        "第69批为7条 canonical line_key 增加真实后端浏览器 smoke 计划字段；"
                        "该字段声明 readiness gate、真实页面路由和浏览器断言，不替代第66-68批字段，"
                        "不把 mocked rail 当 real proof，也不宣称生产、Docker、Celery 或 scheduler 完成。"
                    ),
                },
            },
            "async_execution_readiness_extension": {
                "batch": "70",
                "proof_level": "async_worker_readiness_plan",
                "process_stats_probe": PROCESS_STATS_PROBE_PATH,
                "statement": (
                    "第70批为7条 canonical line_key 增加 async_execution_readiness；"
                    "该字段声明每条业务线的 async surfaces、worker 依赖、process stats 探针和阻塞语义。"
                    "后端 live smoke 或真实后端浏览器 passed 不等于 Celery worker、异步执行、scheduler、"
                    "Docker 或 production 已完成。"
                ),
                "blocked_semantics": (
                    "celery_worker_unavailable must block async/worker readiness proof until process stats and "
                    "line-specific async readback artifacts are available."
                ),
            },
            "async_task_readback_extension": {
                "batch": "71",
                "proof_level": "async_task_readback_contract",
                "statement": (
                    "第71批为7条 canonical line_key 增加 async_task_readback gate/contract；"
                    "本批只定义具体业务异步任务消费、事件、终态和回读证据的契约，"
                    "不宣称真实任务消费、worker 执行或生产异步链路已经完成。"
                ),
                "blocked_semantics": (
                    "worker visibility alone is not proof of line-specific async task consumption; "
                    "missing task readback artifact, required events, or terminal states means "
                    "async_task_readback_missing or blocked_by_environment, not passed."
                ),
                "live_sample_runner_extension": {
                    "batch": "72",
                    "proof_level": "async_task_readback_live_sample_runner_metadata",
                    "script": ASYNC_TASK_READBACK_LIVE_SAMPLE_RUNNER_SCRIPT,
                    "statement": (
                        "第72批为 async_task_readback 接入 live sample runner metadata；"
                        "runner 只能从 live backend 采集 readback samples，覆盖非 worker 线的 "
                        "process/config/audit/diagnostic readback samples。"
                        "worker-required lines 在缺少真实 task/run id 时必须保持 blocked，"
                        "不能伪造真实 task 消费或宣称真实 task completion。"
                        "synthetic sample 不能关闭 live evidence。"
                    ),
                    "live_backend_only": True,
                    "non_worker_sample_scope": [
                        "process readback",
                        "config readback",
                        "audit readback",
                        "diagnostic readback",
                    ],
                    "worker_required_blocked_semantics": (
                        "worker-required lines must remain blocked without a real task/run id and live backend "
                        "readback; synthetic samples cannot close live evidence or prove real task consumption."
                    ),
                    "completion_claim": "does_not_claim_real_task_completion",
                },
                "worker_task_readback_manifest_extension": {
                    "batch": "73",
                    "proof_level": "worker_required_task_readback_manifest_metadata",
                    "script": ASYNC_TASK_READBACK_LIVE_SAMPLE_RUNNER_SCRIPT,
                    "manifest_cli": ASYNC_TASK_READBACK_WORKER_MANIFEST_CLI,
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "statement": (
                        "第73批为 worker-required async_task_readback 声明 manifest/probe 接入 metadata；"
                        "覆盖 ingest、search_discovery_index、resource_source_library、"
                        "writing_knowledge_graph_agent 四条 worker-required line。"
                        "该 metadata 与 live sample runner 的 manifest/probe CLI 对齐，"
                        "只允许接收真实 worker manifest，不宣称真实 task completion 或 worker 闭环已经完成。"
                    ),
                    "required_manifest_fields": [
                        "line_key",
                        "task_id",
                        "run_id",
                        "worker_name",
                        "queue",
                        "trace_id",
                        "readback_endpoint",
                    ],
                    "requires_real_task_identifiers": ["task_id_or_run_id"],
                    "requires_worker_probe_fields": ["worker_name", "queue"],
                    "requires_trace_readback_fields": ["trace_id", "readback_endpoint"],
                    "synthetic_samples_semantics": (
                        "synthetic samples, mocked task ids, generated run ids, or process visibility alone cannot "
                        "close worker-required async task readback evidence."
                    ),
                    "blocked_semantics": (
                        "Missing real task_id/run_id, worker_name, queue, trace_id, readback endpoint, worker-consumed "
                        "events, or terminal state must remain async_task_readback_missing or blocked_by_environment, "
                        "not passed."
                    ),
                    "completion_claim": "does_not_close_real_task_completion",
                },
                "worker_task_readback_manifest_qualification_extension": {
                    "batch": "74",
                    "proof_level": "worker_required_task_readback_manifest_qualification_metadata",
                    "checker": ASYNC_TASK_READBACK_WORKER_MANIFEST_CHECKER_SCRIPT,
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "worker_required_line_count": len(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
                    "statement": (
                        "第74批为 worker-required readback manifest 声明 qualification/checker gate；"
                        "覆盖 ingest、search_discovery_index、resource_source_library、"
                        "writing_knowledge_graph_agent 四条 worker-required line。"
                        "checker 已作为独立脚本落地，用于在 runner/build 前拒绝非真实 manifest。"
                        "synthetic/fixture/generated/mock ids 必须判定为 failed，避免合成 manifest fixture "
                        "被误认为真实任务闭环。"
                    ),
                    "must_fail_identifier_qualifiers": [
                        "synthetic",
                        "fixture",
                        "generated",
                        "mock",
                    ],
                    "requires_real_task_identifiers": ["task_id_or_run_id"],
                    "requires_worker_probe_fields": ["worker_name", "queue"],
                    "requires_trace_readback_fields": [
                        "trace_id",
                        "readback_endpoint_or_path",
                    ],
                    "requires_terminal_events": True,
                    "required_manifest_fields": [
                        "line_key",
                        "task_id_or_run_id",
                        "worker_name",
                        "queue",
                        "trace_id",
                        "readback_endpoint_or_path",
                        "terminal_events",
                    ],
                    "qualification_semantics": (
                        "A qualifying manifest must contain a real task_id_or_run_id, worker_name, queue, trace_id, "
                        "readback endpoint/path, and terminal events for each covered worker-required line."
                    ),
                    "failure_semantics": (
                        "Manifest rows with synthetic, fixture, generated, or mock identifiers must fail the checker; "
                        "missing real task_id_or_run_id, worker_name, queue, trace_id, readback endpoint/path, or "
                        "terminal events means async_task_readback_missing or manifest_qualification_failed, not passed."
                    ),
                    "completion_claim": "does_not_close_real_task_completion",
                },
                "worker_task_readback_manifest_candidate_builder_extension": {
                    "batch": "75",
                    "proof_level": "worker_required_task_readback_manifest_candidate_builder_metadata",
                    "script": ASYNC_TASK_READBACK_WORKER_MANIFEST_CANDIDATE_BUILDER_SCRIPT,
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "worker_required_line_count": len(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
                    "candidate_schema_name": "business_line_task_readback_manifest_candidate.v1",
                    "candidate_discovery_sources": [
                        "live_runtime_state",
                        "evidence_matrix",
                        "async_task_readback_paths",
                    ],
                    "statement": (
                        "第75批为 worker-required readback manifest 声明 runtime manifest candidate builder metadata；"
                        "覆盖 ingest、search_discovery_index、resource_source_library、"
                        "writing_knowledge_graph_agent 四条 worker-required line。"
                        "candidate builder 只能从 live runtime、evidence matrix 与 async_task_readback/readback paths "
                        "发现候选，不能伪造 task/run id，不能把 blocked 缺口计为 passed。"
                        "候选必须先经第74批 checker qualification，再交第73批 runner/manifest probe 和"
                        "第71批 async_task_readback builder/checker；本 metadata 不宣称真实 task completion。"
                    ),
                    "required_candidate_fields": [
                        "line_key",
                        "candidate_source",
                        "runtime_evidence_matrix_path",
                        "readback_paths",
                        "task_id_or_run_id",
                        "worker_name",
                        "queue",
                        "trace_id",
                        "readback_endpoint_or_path",
                        "terminal_events",
                        "qualification_status",
                        "blocked_reason",
                    ],
                    "candidate_source_semantics": (
                        "Candidates may only be discovered from live runtime state, evidence matrix metadata, and "
                        "declared async_task_readback readback paths; the builder must not synthesize, fixture, mock, "
                        "or invent task_id/run_id values."
                    ),
                    "blocked_semantics": (
                        "Missing live runtime evidence, missing real task_id_or_run_id, missing worker/readback fields, "
                        "qualification failure, or blocked readback gaps must remain async_task_readback_missing, "
                        "manifest_candidate_builder_blocked, or manifest_qualification_failed, not passed."
                    ),
                    "recommended_chain": [
                        "batch_75_build_candidates_from_live_runtime_evidence_matrix_and_readback_paths",
                        "batch_74_check_business_line_task_readback_manifest_qualification",
                        "batch_73_run_business_line_async_task_readback_live_samples_with_manifest_probe",
                        "batch_71_async_task_readback_builder_checker_contract",
                    ],
                    "completion_claim": "does_not_claim_real_task_completion",
                },
                "worker_task_readback_evidence_chain_extension": {
                    "batch": "76",
                    "proof_level": "worker_required_task_readback_evidence_chain_metadata",
                    "script": ASYNC_TASK_READBACK_WORKER_EVIDENCE_CHAIN_SCRIPT,
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "worker_required_line_count": len(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
                    "chain_order": [
                        "batch75_candidate_builder",
                        "batch74_manifest_checker",
                        "batch73_live_sample_runner",
                        "batch71_async_task_readback_builder",
                        "batch71_async_task_readback_checker",
                    ],
                    "statement": (
                        "第76批声明 worker-required evidence chain metadata，覆盖 ingest、"
                        "search_discovery_index、resource_source_library、writing_knowledge_graph_agent "
                        "四条 worker-required line。chain enforces batch75->74->73->71 order: "
                        "batch75_candidate_builder 先产生候选，batch74_manifest_checker 必须 passed 后，"
                        "才允许进入 batch73_live_sample_runner，再进入 batch71 async_task_readback builder/checker。"
                        "脚本不启动服务、不伪造 task/run id，也不把 blocked chain 当 completion。"
                    ),
                    "stop_semantics": (
                        "If batch74_manifest_checker is failed, missing, blocked, or otherwise not passed, the chain "
                        "must be stopped and must not run batch73 live sample runner or batch71 builder/checker steps."
                    ),
                    "allow_blocked_semantics": (
                        "Blocked chain output is allowed only as blocked/readback evidence gap reporting; "
                        "blocked_by_environment, async_task_readback_missing, manifest_candidate_builder_blocked, "
                        "or manifest_qualification_failed is not completion and must not be counted as passed."
                    ),
                    "runtime_semantics": (
                        "The chain runner must consume existing live runtime evidence only: it must not start backend, "
                        "Celery, scheduler, Docker, or any service, and must not forge task_id/run_id values."
                    ),
                    "completion_claim": "does_not_claim_worker_readback_completion",
                },
                "worker_task_readback_strict_semantics_extension": {
                    "batch": "77",
                    "proof_level": "worker_required_task_readback_strict_semantics_metadata",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "worker_required_line_count": len(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
                    "statement": (
                        "第77批声明 strict worker readback semantics：readback 2xx alone is not proof。"
                        "worker-required passed 必须由 readback response itself 证明，并包含匹配的 "
                        "task_id_or_run_id、worker_name、queue、trace_id、success status 与 terminal event。"
                        "第73 runner 不能从 manifest 或 contract 默认补 status/events/trace 来关闭证明。"
                    ),
                    "required_live_readback_fields": [
                        "matching_task_id_or_run_id",
                        "worker_name",
                        "queue",
                        "trace_id",
                        "success_status",
                        "terminal_event",
                        "required_events",
                    ],
                    "disallowed_fallbacks": [
                        "readback_2xx_only",
                        "request_id_as_trace_id",
                        "correlation_id_as_trace_id",
                        "manifest_default_status",
                        "manifest_default_events",
                        "manifest_default_trace",
                        "contract_default_status",
                        "contract_default_events",
                        "contract_default_trace",
                    ],
                    "failure_semantics": (
                        "Missing or mismatched task_id_or_run_id, worker_name, queue, trace_id, success status, "
                        "terminal event, or required_events in the readback response itself must be failed, not passed; "
                        "request_id/correlation_id aliases and manifest or contract defaults for events, status, "
                        "or trace cannot close worker-required proof."
                    ),
                    "completion_claim": "requires_strict_worker_readback_response_match",
                },
                "worker_task_readback_artifact_checker_strict_extension": {
                    "batch": "78",
                    "proof_level": "worker_required_task_readback_artifact_checker_strict_contract_metadata",
                    "checker": ASYNC_TASK_READBACK_ARTIFACT_CHECKER_SCRIPT,
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "worker_required_line_count": len(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
                    "statement": (
                        "第78批声明 downstream artifact checker strict contract；"
                        "scripts/check_business_line_async_task_readback_artifact.py 也必须校验 "
                        "worker-required artifact 的 identity、worker、queue、trace、"
                        "readback_location 与 required_events。"
                        "checker 必须以 canonical worker-required line set 为准，不能信任 artifact "
                        "自报 requires_worker_readback=false 或空 required_events。"
                        "该 metadata 只声明 checker gate，防止替换 artifact 或绕过 runner 后被误判 passed，"
                        "不宣称真实 worker completion。"
                    ),
                    "required_checker_fields": [
                        "canonical_worker_required_line_key",
                        "matching_task_id_or_run_id",
                        "worker_name",
                        "queue",
                        "trace_id",
                        "readback_location",
                        "non_empty_required_events",
                        "canonical_worker_success_terminal_status",
                    ],
                    "bypass_protection": [
                        "replaced_artifact",
                        "runner_bypass",
                        "requires_worker_readback_false_artifact",
                        "empty_required_events_artifact",
                        "weakened_success_terminal_states_artifact",
                        "manifest_only_artifact",
                        "contract_default_artifact",
                    ],
                    "failure_semantics": (
                        "Missing or mismatched canonical worker-required line, identity, worker_name, queue, trace_id, "
                        "readback_location, non-empty required_events, or canonical worker success terminal status "
                        "in worker-required downstream artifact must fail the checker, not passed; replaced artifacts, "
                        "runner bypass, requires_worker_readback=false artifacts, empty required_events artifacts, "
                        "weakened success terminal states, manifest-only artifacts, or contract-default artifacts "
                        "cannot close worker-required proof."
                    ),
                    "completion_claim": "checker_gate_only_does_not_claim_real_worker_completion",
                },
                "worker_task_readback_manifest_linked_artifact_checker_extension": {
                    "batch": "79",
                    "proof_level": "worker_required_manifest_linked_artifact_checker_contract_metadata",
                    "checker": ASYNC_TASK_READBACK_ARTIFACT_CHECKER_SCRIPT,
                    "checker_cli": ASYNC_TASK_READBACK_WORKER_MANIFEST_CLI,
                    "chain": ASYNC_TASK_READBACK_WORKER_EVIDENCE_CHAIN_SCRIPT,
                    "manifest_source_step": "batch75_candidate_builder",
                    "checker_step": "batch71_async_task_readback_checker",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "worker_required_line_count": len(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
                    "statement": (
                        "第79批声明 manifest-linked artifact consistency gate："
                        "scripts/check_business_line_async_task_readback_artifact.py 必须支持 "
                        "--task-readback-manifest，并用第75批 candidate manifest 校验第71批 "
                        "async_task_readback artifact。"
                        "scripts/run_business_line_worker_readback_evidence_chain.py 必须把 "
                        "batch75_candidate_builder 产出的 candidate manifest 传给 "
                        "batch71_async_task_readback_checker，防止 artifact 与 manifest 脱钩后仍 passed。"
                    ),
                    "required_consistency_fields": [
                        "line_key",
                        "task_id_or_run_id",
                        "worker_name",
                        "queue",
                        "trace_id",
                        "readback_location",
                        "status",
                        "events",
                    ],
                    "manifest_link_contract": {
                        "source": "batch75_candidate_manifest",
                        "consumer": "batch71_async_task_readback_checker",
                        "cli": ASYNC_TASK_READBACK_WORKER_MANIFEST_CLI,
                    },
                    "failure_semantics": (
                        "Artifact/manifest mismatch on line_key, task_id_or_run_id, worker_name, queue, trace_id, "
                        "readback_location, status, or events must fail the checker, not passed; missing "
                        "--task-readback-manifest coverage or a chain run that does not pass the batch75 candidate "
                        "manifest into the batch71 checker cannot close worker-required proof."
                    ),
                    "completion_claim": "manifest_linked_checker_gate_only_does_not_claim_real_worker_completion",
                },
                "worker_task_readback_process_runtime_projection_extension": {
                    "batch": "80",
                    "proof_level": "worker_required_process_runtime_readback_projection_contract_metadata",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "worker_required_line_count": len(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
                    "process_runtime_endpoints": [
                        "/api/v1/process/tasks?line_key={line_key}&limit=...",
                        "/api/v1/process/logs?line_key={line_key}&limit=...",
                    ],
                    "required_projection_fields": [
                        "line_key",
                        "task_id_or_run_id",
                        "worker_name",
                        "queue",
                        "trace_id",
                        "readback_location",
                        "status",
                        "events",
                    ],
                    "statement": (
                        "第80批声明 process runtime readback projection contract："
                        "/api/v1/process/tasks?line_key={line_key}&limit=... 与 "
                        "/api/v1/process/logs?line_key={line_key}&limit=... 必须提供 line_key 级 "
                        "runtime readback projection，覆盖 ingest、search_discovery_index、"
                        "resource_source_library、writing_knowledge_graph_agent 四条 worker-required line。"
                        "该 projection 用于修正 process readback 路径被 /{task_id} 动态路由吞掉的缺口，"
                        "只能暴露真实 runtime task/log evidence，不能硬编码 completion，也不宣称真实 worker completion。"
                    ),
                    "route_contract": (
                        "The line_key query projection endpoints must be reachable as collection routes and must not be "
                        "swallowed by a dynamic /api/v1/process/tasks/{task_id} route."
                    ),
                    "blocked_semantics": (
                        "Empty projection, missing line_key/task_id_or_run_id/worker_name/queue/trace_id/"
                        "readback_location/status/events, route collision, or unavailable process runtime evidence "
                        "must remain async_task_readback_missing or blocked_by_environment, not passed."
                    ),
                    "failure_semantics": (
                        "The process runtime projection must not synthesize or hardcode completion. Missing or empty "
                        "projection rows, missing required projection fields, dynamic-route capture, or non-runtime "
                        "defaults cannot close worker-required proof and must be reported as async_task_readback_missing "
                        "or blocked_by_environment."
                    ),
                    "completion_claim": "process_runtime_projection_only_does_not_claim_real_worker_completion",
                },
                "worker_task_readback_execution_record_write_extension": {
                    "batch": "81",
                    "proof_level": "worker_required_execution_record_write_contract_metadata",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "worker_required_line_count": len(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
                    "write_boundaries": [
                        "main/backend/app/api/agent_batch.py",
                        "main/backend/app/services/tasks.py",
                        "main/backend/app/services/job_logger.py",
                        "main/backend/app/services/collect_runtime/adapters/search_market.py",
                        "main/backend/app/services/collect_runtime/adapters/source_library.py",
                        "main/backend/app/services/ingest/market_web.py",
                        "main/backend/app/services/ingest/url_pool.py",
                        "main/backend/app/services/writing/llm_action_service.py",
                    ],
                    "runtime_readback_fields": [
                        "line_key",
                        "task_id_or_run_id",
                        "worker_name",
                        "queue",
                        "trace_id",
                        "status",
                        "events",
                        "readback_endpoint_or_readback_path",
                    ],
                    "statement": (
                        "第81批声明 execution record write contract：真实 dispatch 与任务完成写入边界必须把 "
                        "line_key、task/run identity、worker_name、queue、trace_id、status、events 写入 "
                        "Celery kwargs/result 或 EtlJobRun.params，使第80批 process runtime projection 能精确读回。"
                        "覆盖 ingest、search_discovery_index、resource_source_library、"
                        "writing_knowledge_graph_agent 四条 worker-required line。"
                    ),
                    "exact_readback_contract": (
                        "DB-backed runtime readback rows discovered from /api/v1/process/tasks|logs must point to an "
                        "exact /api/v1/process/db-job-{id} endpoint for live recheck; worker manifests must not use "
                        "collection list endpoints as the precise readback location."
                    ),
                    "failure_semantics": (
                        "Missing execution-record metadata, unexpected task kwargs rejection, collection endpoint used "
                        "as exact readback, missing terminal events, or unavailable backend/worker runtime must remain "
                        "async_task_readback_missing or blocked_by_environment, not passed."
                    ),
                    "completion_claim": "execution_record_write_contract_only_does_not_claim_real_worker_completion_until_live_chain_passes",
                },
                "worker_task_readback_project_scoped_live_chain_extension": {
                    "batch": "82",
                    "proof_level": "project_scoped_worker_readback_live_chain_passed",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "worker_required_line_count": len(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
                    "project_scope": "project_key-aware evidence matrix, process projection, exact db-job readback, and live sample runner",
                    "chain_steps": [
                        "batch82_project_schema_preflight",
                        "batch75_candidate_builder",
                        "batch74_manifest_checker",
                        "batch73_live_sample_runner",
                        "batch71_async_task_readback_builder",
                        "batch71_async_task_readback_checker",
                    ],
                    "required_runtime_fields": [
                        "line_key",
                        "task_id_or_run_id",
                        "worker_name",
                        "queue",
                        "trace_id",
                        "status",
                        "events",
                        "required_events",
                        "readback_endpoint_or_readback_path",
                    ],
                    "statement": (
                        "第82批把 worker readback evidence chain 改为 project_key 贯通，并在链路前增加 "
                        "project schema preflight；candidate builder、live sample runner 与 exact db-job readback "
                        "必须使用同一个 project_key。第75 candidate builder 也必须校验 async_task_readback.required_events，"
                        "避免把第73必失败的旧样本写入 manifest。"
                    ),
                    "live_evidence": {
                        "api_base": "http://127.0.0.1:8000",
                        "project_key": "demo_proj",
                        "artifact_dir": "/tmp/mrw_business_line_worker_readback_evidence_chain_batch82_final2",
                        "status": "passed",
                        "passed_line_keys": [
                            "ingest",
                            "search_discovery_index",
                            "resource_source_library",
                            "writing_knowledge_graph_agent",
                        ],
                    },
                    "completion_claim": "project_scoped_worker_required_readback_chain_passed_for_demo_proj_live_run",
                },
                "worker_task_readback_triggered_live_chain_extension": {
                    "batch": "83",
                    "proof_level": "project_scoped_worker_readback_triggered_live_chain_passed",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "worker_required_line_count": len(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
                    "trigger_mode": "chain-owned smoke trigger submissions before runtime candidate discovery",
                    "chain_steps": [
                        "batch82_project_schema_preflight",
                        "batch83_trigger_smoke",
                        "batch75_candidate_builder",
                        "batch74_manifest_checker",
                        "batch73_live_sample_runner",
                        "batch71_async_task_readback_builder",
                        "batch71_async_task_readback_checker",
                    ],
                    "trigger_contract": {
                        "does_long_poll": False,
                        "does_readback_validation": False,
                        "triggered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                        "source_library_smoke_mode": "url_pool.default with _source_library_smoke_only=true",
                    },
                    "statement": (
                        "第83批把四条 worker-required line 的 smoke submission 收进 evidence chain，"
                        "避免每次靠人工触发 search/source/writing/ingest 后再读回。trigger helper 只负责提交和记录 "
                        "task/run/job identity，不做长轮询；真实 worker 消费、required events、exact readback 与 manifest "
                        "一致性仍由第75、第74、第73、第71 gate 验收。"
                    ),
                    "live_evidence": {
                        "api_base": "http://127.0.0.1:8000",
                        "project_key": "demo_proj",
                        "artifact_dir": "/tmp/mrw_business_line_worker_readback_evidence_chain_batch83_trigger_live",
                        "status": "passed",
                        "trigger_smoke_status": "passed",
                        "passed_line_keys": [
                            "ingest",
                            "search_discovery_index",
                            "resource_source_library",
                            "writing_knowledge_graph_agent",
                        ],
                    },
                    "completion_claim": "project_scoped_worker_required_readback_chain_can_trigger_and_verify_demo_proj_live_run",
                },
                "worker_task_readback_multi_project_matrix_extension": {
                    "batch": "84",
                    "proof_level": "multi_project_worker_readback_matrix_capability_metadata",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "worker_required_line_count": len(WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS),
                    "matrix_input": {
                        "project_keys": "runner-supplied project_key list; demo_proj is only one matrix row, not a global proxy",
                        "artifact_dir_scope": "one independent artifact_dir per project_key",
                        "status_scope": "one independent status per project_key and per worker-required line",
                    },
                    "chain_steps": [
                        "batch82_project_schema_preflight",
                        "batch83_trigger_smoke_optional",
                        "batch75_candidate_builder",
                        "batch74_manifest_checker",
                        "batch73_live_sample_runner",
                        "batch71_async_task_readback_builder",
                        "batch71_async_task_readback_checker",
                    ],
                    "statement": (
                        "第84批声明 worker readback multi-project matrix runner capability：project_keys 是矩阵输入，"
                        "每个 project_key 必须使用独立 artifact_dir、独立 manifest/readback artifact 与独立状态汇总。"
                        "demo_proj 的 live pass 不能被泛化为其他 project 的 pass；batch83 trigger-smoke 可作为每个 "
                        "project 行的可选 chain step，但不替代 worker 消费、exact readback 与 required events 验收。"
                    ),
                    "aggregation_contract": (
                        "Matrix aggregation may report passed only when every selected project_key and every "
                        "worker-required line has independently passed; any failed or blocked project row must keep "
                        "the matrix result failed or blocked, not passed."
                    ),
                    "failure_semantics": (
                        "Missing project_keys, shared artifact_dir across projects, absent per-project manifests, "
                        "demo_proj-only evidence generalized to another project, failed rows, blocked rows, or missing "
                        "worker-required line evidence must not be aggregated into passed."
                    ),
                    "runtime_dispatch_trace_fix": (
                        "第84批同时修复 ingest.url.single 与 ingest.source_library.run 的异步 dispatch trace 注入，"
                        "确保非 demo project 的 trigger-smoke rows 可在 /api/v1/process/tasks|logs 中读回 trace_id。"
                    ),
                    "live_evidence": {
                        "api_base": "http://127.0.0.1:8000",
                        "artifact_dir": "/tmp/mrw_business_line_worker_readback_project_matrix_batch84_live_tracefix",
                        "status": "passed",
                        "trigger_smoke": True,
                        "project_keys": ["demo_proj", "demo_proj_1772384627"],
                        "summary": {
                            "total": 2,
                            "passed": 2,
                            "blocked_by_environment": 0,
                            "failed": 0,
                        },
                    },
                    "completion_claim": "multi_project_worker_readback_matrix_passed_for_selected_local_project_rows_after_dispatch_trace_fix",
                },
                "project_injection_and_matrix_inventory_extension": {
                    "batch": "85",
                    "proof_level": "project_copy_inventory_matrix_live_evidence",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "project_copy_contract": {
                        "copy_strategy": "column-aligned common-column insert instead of SELECT star",
                        "json_columns": "target json/jsonb columns use explicit source casts such as ::jsonb",
                        "schema_drift": "source-only and target-only columns are skipped rather than relying on column order",
                    },
                    "matrix_inventory_contract": {
                        "explicit_project_keys": "repeatable --project-key remains supported",
                        "projects_list_json": "enabled project_key values are selected from list or envelope data.items",
                        "dedupe": "explicit keys and inventory keys are merged in order and deduped",
                        "compact_default": "top-level matrix report keeps child summary/path/status but omits full stdout/stderr/chain_report by default",
                    },
                    "live_evidence": {
                        "api_base": "http://127.0.0.1:8000",
                        "injected_project_key": "batch85_matrix_proj",
                        "inject_initial_status": "passed",
                        "artifact_dir": "/tmp/mrw_business_line_worker_readback_project_matrix_batch85_live",
                        "projects_list_json": "/tmp/mrw_business_line_worker_readback_project_matrix_batch85_live/projects-list-subset.json",
                        "matrix_status": "passed",
                        "include_child_reports": False,
                        "project_keys": ["demo_proj", "batch85_matrix_proj"],
                        "summary": {
                            "total": 2,
                            "passed": 2,
                            "blocked_by_environment": 0,
                            "failed": 0,
                        },
                    },
                    "completion_claim": "inject_initial_copy_type_drift_closed_and_inventory_driven_compact_matrix_passed_for_demo_and_fresh_project",
                },
                "matrix_project_discovery_and_scheduler_evidence_extension": {
                    "batch": "86",
                    "proof_level": "projects_api_discovery_matrix_live_evidence_with_scheduler_gap_guard",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "project_discovery_contract": {
                        "projects_api_url": "runner can fetch /api/v1/projects directly via --projects-api-url",
                        "enabled_filter": "only enabled=true records with non-empty project_key are selected from API responses",
                        "selection_filters": "merged explicit/file/api keys can be narrowed by --project-key-regex, --exclude-project-key and --max-projects",
                        "selection_report": "top-level matrix report records project_selection inputs, merged keys and final project_keys",
                    },
                    "scheduler_evidence_contract": {
                        "lane": "business_line_worker_readback_project_matrix_nightly",
                        "checker": "scripts/check_scheduled_automation_artifacts.py",
                        "artifact_globs": [
                            "development/latest-dev-docs/automation-runs/business-line-worker-readback-project-matrix/*/nightly-manifest.json",
                            "development/latest-dev-docs/automation-runs/business-line-worker-readback-project-matrix/*/business-line-worker-readback-project-matrix-report.json",
                        ],
                        "gap_guard": "manual/live artifacts without scheduler marker remain manual or missing and cannot close scheduled evidence",
                    },
                    "live_evidence": {
                        "api_base": "http://127.0.0.1:8000",
                        "projects_api_url": "http://127.0.0.1:8000/api/v1/projects",
                        "injected_project_key": "batch86_discovered_proj",
                        "inject_initial_status": "passed",
                        "artifact_dir": "/tmp/mrw_business_line_worker_readback_project_matrix_batch86_live",
                        "project_key_regex": "^(demo_proj|batch86_discovered_proj)$",
                        "matrix_status": "passed",
                        "project_keys": ["demo_proj", "batch86_discovered_proj"],
                        "discovered_project_count": 9,
                        "summary": {
                            "total": 2,
                            "passed": 2,
                            "blocked_by_environment": 0,
                            "failed": 0,
                        },
                    },
                    "scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch86_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_evidence_count": 0,
                    },
                    "completion_claim": "projects_api_discovery_matrix_passed_for_selected_local_project_rows_scheduler_lane_guard_added_but_cron_run_not_claimed",
                },
                "matrix_nightly_wrapper_and_codex_automation_extension": {
                    "batch": "87",
                    "proof_level": "nightly_wrapper_spec_codex_app_installation_manual_live_evidence",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "wrapper_contract": {
                        "wrapper": "scripts/run_business_line_worker_readback_project_matrix_nightly.sh",
                        "default_projects_api_url": "${api_base}/api/v1/projects",
                        "default_project_key_regex": "^demo_proj$",
                        "outputs": [
                            "business-line-worker-readback-project-matrix-report.json",
                            "nightly-manifest.json",
                            "trend-history.jsonl",
                        ],
                        "scheduled_marker_guard": (
                            "scheduled_run_evidence is written only when Codex automation env or "
                            "MRW_SCHEDULED_RUN_EVIDENCE is present"
                        ),
                    },
                    "automation_spec": {
                        "spec": "development/latest-dev-docs/automation-runs/business-line-worker-readback-project-matrix/automation-spec.json",
                        "checker": "scripts/check_business_line_worker_readback_project_matrix_automation_spec.py",
                        "install_status": "installed_codex_app",
                        "automation_id": "mrw-business-line-worker-readback-project-matrix-nightly",
                        "config_path": "/Users/wangyiliang/.codex/automations/mrw-business-line-worker-readback-project-matrix-nightly/automation.toml",
                        "rrule": "FREQ=HOURLY;INTERVAL=24",
                    },
                    "ops_runtime_fix": {
                        "script": "scripts/local-deploy.sh",
                        "fix": "start/restart no longer expand empty START_LOCAL_ARGS under set -u",
                        "evidence": "./scripts/local-deploy.sh start succeeded without extra args",
                    },
                    "manual_live_evidence": {
                        "api_base": "http://127.0.0.1:8000",
                        "artifact_dir": "/tmp/mrw_business_line_worker_readback_project_matrix_batch87_manual",
                        "wrapper_status": "passed",
                        "matrix_status": "passed",
                        "matrix_exit_code": 0,
                        "has_scheduled_marker": False,
                        "project_keys": ["demo_proj"],
                        "summary": {
                            "total": 1,
                            "passed": 1,
                            "blocked_by_environment": 0,
                            "failed": 0,
                        },
                    },
                    "scheduled_evidence_boundary": (
                        "Codex app automation is installed and spec-verified, but this batch only produced "
                        "manual live artifact evidence; first scheduler-produced artifact is still required "
                        "before claiming scheduled run completion"
                    ),
                    "completion_claim": "matrix_nightly_wrapper_spec_and_codex_app_automation_installed_manual_live_wrapper_passed_without_cron_run_claim",
                },
                "agent_batch_web_first_and_matrix_checker_evidence_extension": {
                    "batch": "88",
                    "proof_level": "agent_batch_regression_closure_and_matrix_scheduled_evidence_hardening",
                    "covered_line_keys": [
                        "writing_knowledge_graph_agent",
                        *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    ],
                    "agent_batch_contract": {
                        "module": "main/backend/app/services/agent_batch/agent_loop.py",
                        "fix": (
                            "default hybrid market_news/regulatory_monitoring plans remain web-first and do not "
                            "auto-append source_library tasks unless source/library mode is explicit"
                        ),
                        "closed_regressions": [
                            "accepted_count no longer drifts below parsed.task_count because hidden source_library tasks were appended",
                            "bounded retry for a wide time window schedules the expected second search.market round",
                            "unsupported search override rejection remains a single rejected task instead of being inflated by appended source tasks",
                        ],
                    },
                    "matrix_scheduled_checker_contract": {
                        "checker": "scripts/check_scheduled_automation_artifacts.py",
                        "lane": "business_line_worker_readback_project_matrix_nightly",
                        "required_payload_evidence": [
                            "scheduled marker",
                            "status or matrix_report_status is passed/partial",
                            "non-empty project_selection.project_keys",
                            "summary.total or total_projects > 0",
                        ],
                        "gap_guard": (
                            "a scheduler marker alone is insufficient for matrix scheduled_run_evidence when "
                            "the matrix payload is empty or not passed/partial"
                        ),
                    },
                    "verification": {
                        "agent_batch_unit": "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_agent_batch_api_unittest.py -q",
                        "combined_gate": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/unit/test_agent_batch_api_unittest.py "
                            "main/backend/tests/unit/test_source_library_resolver_unittest.py "
                            "tests/checkers/test_check_scheduled_automation_artifacts_unittest.py "
                            "tests/checkers/test_run_business_line_worker_readback_project_matrix_nightly_unittest.py "
                            "tests/checkers/test_check_business_line_worker_readback_project_matrix_automation_spec_unittest.py -q"
                        ),
                        "combined_gate_result": "93 passed, 3 warnings",
                        "scheduled_checker_artifact": "/tmp/mrw_batch88_scheduled_automation_artifacts.json",
                        "scheduled_checker_status": "blocked",
                        "scheduled_run_evidence_count": 0,
                        "matrix_lane_classification": "missing",
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 88 strengthens checker semantics but still does not claim a real Codex scheduler "
                        "artifact exists for the matrix lane."
                    ),
                    "completion_claim": "agent_batch_nl_source_augmentation_regression_closed_and_matrix_scheduled_checker_requires_payload_evidence",
                },
                "matrix_runtime_preflight_and_project_readiness_extension": {
                    "batch": "89",
                    "proof_level": "nightly_runtime_preflight_project_readiness_and_scheduler_gap_preservation",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "project_inventory_contract": {
                        "api": "/api/v1/projects",
                        "new_fields": [
                            "archived",
                            "schema_ready",
                            "has_worker_fixture",
                            "nightly_matrix_eligible",
                        ],
                        "selection_semantics": (
                            "matrix runner excludes disabled/archived projects and records excluded API "
                            "projects when schema_ready, has_worker_fixture or nightly_matrix_eligible is false"
                        ),
                    },
                    "nightly_runtime_contract": {
                        "wrapper": "scripts/run_business_line_worker_readback_project_matrix_nightly.sh",
                        "automation_prompt": "Codex app automation now runs wrapper with --ensure-local-runtime",
                        "manifest_fields": [
                            "runtime_preflight",
                            "duration_seconds",
                            "matrix_started_at",
                            "matrix_finished_at",
                        ],
                        "fail_soft_preflight": (
                            "local-deploy start timeout is recorded as runtime_preflight blocked evidence "
                            "instead of crashing before manifest creation"
                        ),
                    },
                    "manual_blocked_evidence": {
                        "artifact_dir": "/tmp/mrw_business_line_worker_readback_project_matrix_batch89_blocked",
                        "manifest": "/tmp/mrw_business_line_worker_readback_project_matrix_batch89_blocked/nightly-manifest.json",
                        "status": "blocked_by_environment",
                        "matrix_exit_code": 1,
                        "runtime_preflight_status": "passed",
                        "runtime_start_exit_code": 124,
                        "matrix_report_loaded": True,
                    },
                    "scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch89_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_evidence_count": 0,
                    },
                    "verification": {
                        "project_contract": "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/core_business/test_projects_core_contract.py -q",
                        "matrix_checker_bundle": (
                            "/Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "tests/checkers/test_run_business_line_worker_readback_project_matrix_unittest.py "
                            "tests/checkers/test_run_business_line_worker_readback_project_matrix_nightly_unittest.py "
                            "tests/checkers/test_check_business_line_worker_readback_project_matrix_automation_spec_unittest.py -q"
                        ),
                        "automation_spec": (
                            "/Users/wangyiliang/.local/bin/python3.11 "
                            "scripts/check_business_line_worker_readback_project_matrix_automation_spec.py "
                            "development/latest-dev-docs/automation-runs/business-line-worker-readback-project-matrix/automation-spec.json "
                            "--run-date 2026-05-25 --execute-dry-run"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 89 improves scheduler readiness and blocked artifact evidence, but the repo still "
                        "has no real Codex scheduler-produced matrix artifact."
                    ),
                    "completion_claim": "matrix_nightly_runtime_preflight_and_project_readiness_contracts_added_without_claiming_scheduler_completion",
                },
                "matrix_scheduler_provenance_and_blocked_classification_extension": {
                    "batch": "90",
                    "proof_level": "scheduled_provenance_contract_and_blocked_artifact_classification",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "automation_provenance_contract": {
                        "spec": "development/latest-dev-docs/automation-runs/business-line-worker-readback-project-matrix/automation-spec.json",
                        "required_env": {"MRW_SCHEDULED_RUN_EVIDENCE": "true"},
                        "automation_prompt": (
                            "Codex app automation now invokes the wrapper with "
                            "MRW_SCHEDULED_RUN_EVIDENCE=true so scheduled artifacts carry explicit provenance"
                        ),
                        "manual_boundary": (
                            "manual wrapper invocations still do not set MRW_SCHEDULED_RUN_EVIDENCE and "
                            "therefore cannot claim scheduler evidence"
                        ),
                    },
                    "scheduled_checker_contract": {
                        "checker": "scripts/check_scheduled_automation_artifacts.py",
                        "new_classification": "scheduled_run_blocked",
                        "semantics": (
                            "matrix artifact with scheduler marker, non-dry-run payload, non-empty project "
                            "selection, and summary.total > 0 but non-passed status is classified as scheduled "
                            "but blocked; it does not increment scheduled_run_evidence_count"
                        ),
                    },
                    "simulated_scheduled_blocked_evidence": {
                        "root": "/tmp/mrw_batch90_scheduled_blocked_root",
                        "checker_artifact": "/tmp/mrw_batch90_scheduled_blocked_check.json",
                        "status": "blocked",
                        "matrix_lane_classification": "scheduled_run_blocked",
                        "scheduled_run_blocked_count": 1,
                        "scheduled_run_evidence_count": 0,
                    },
                    "repo_scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch90_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_blocked_count": 0,
                        "scheduled_run_evidence_count": 0,
                    },
                    "verification": {
                        "checker_and_spec_bundle": (
                            "/Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "tests/checkers/test_check_scheduled_automation_artifacts_unittest.py "
                            "tests/checkers/test_check_business_line_worker_readback_project_matrix_automation_spec_unittest.py "
                            "tests/checkers/test_run_business_line_worker_readback_project_matrix_nightly_unittest.py -q"
                        ),
                        "automation_spec": (
                            "/Users/wangyiliang/.local/bin/python3.11 "
                            "scripts/check_business_line_worker_readback_project_matrix_automation_spec.py "
                            "development/latest-dev-docs/automation-runs/business-line-worker-readback-project-matrix/automation-spec.json "
                            "--run-date 2026-05-25 --execute-dry-run"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 90 makes future Codex scheduler artifacts provable and classifiable, but no "
                        "real repo-local Codex scheduler artifact exists yet."
                    ),
                    "completion_claim": "scheduler_provenance_env_and_scheduled_run_blocked_classification_added_without_claiming_cron_completion",
                },
                "matrix_scheduled_checker_diagnostics_extension": {
                    "batch": "91",
                    "proof_level": "scheduled_artifact_diagnostics_contract",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "scheduled_checker_contract": {
                        "checker": "scripts/check_scheduled_automation_artifacts.py",
                        "diagnostics_fields": [
                            "matrix_status",
                            "matrix_report_status",
                            "matrix_exit_code",
                            "runtime_preflight_status",
                            "runtime_preflight_start_exit_code",
                            "project_keys",
                            "projects_api_url",
                            "summary_total",
                            "duration_seconds",
                        ],
                        "semantics": (
                            "matrix lane artifacts expose diagnostics at artifact-row level and promote the "
                            "selected artifact diagnostics to lane level without changing scheduled_run_evidence "
                            "or scheduled_run_blocked classification semantics"
                        ),
                    },
                    "automation_owner_docs": {
                        "readme": (
                            "development/latest-dev-docs/automation-runs/"
                            "business-line-worker-readback-project-matrix/README.md"
                        ),
                        "documented_boundaries": [
                            "MRW_SCHEDULED_RUN_EVIDENCE is scheduler-owned provenance",
                            "manual wrapper commands must not default to scheduler provenance",
                            "scheduled_run_blocked remains blocked evidence rather than completion evidence",
                        ],
                    },
                    "repo_scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch91_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_blocked_count": 0,
                        "scheduled_run_evidence_count": 0,
                    },
                    "verification": {
                        "checker_tests": (
                            "/Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "tests/checkers/test_check_scheduled_automation_artifacts_unittest.py -q"
                        ),
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 91 improves scheduled artifact observability for future scheduler outputs, but "
                        "does not claim that a real Codex scheduler-produced matrix artifact exists."
                    ),
                    "completion_claim": "matrix_scheduled_checker_diagnostics_added_without_claiming_cron_completion",
                },
                "matrix_manifest_blocked_project_diagnostics_extension": {
                    "batch": "92",
                    "proof_level": "manifest_level_blocked_project_diagnostics_contract",
                    "covered_line_keys": WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
                    "nightly_manifest_contract": {
                        "wrapper": "scripts/run_business_line_worker_readback_project_matrix_nightly.sh",
                        "new_field": "matrix_diagnostics",
                        "project_row_fields": [
                            "project_key",
                            "status",
                            "reason",
                            "stopped_at",
                            "exit_code",
                            "trigger_smoke_status",
                        ],
                        "summary_fields": [
                            "blocked_project_count",
                            "failed_project_count",
                            "blocked_projects",
                            "failed_projects",
                            "stopped_at_counts",
                            "reason_counts",
                            "first_blocked_reason",
                        ],
                    },
                    "scheduled_checker_contract": {
                        "checker": "scripts/check_scheduled_automation_artifacts.py",
                        "semantics": (
                            "checker diagnostics prefer manifest.matrix_diagnostics and preserve compact "
                            "blocked/failed project objects so scheduled_run_blocked can be triaged without "
                            "opening child reports"
                        ),
                    },
                    "automation_owner_docs": {
                        "readme": (
                            "development/latest-dev-docs/automation-runs/"
                            "business-line-worker-readback-project-matrix/README.md"
                        ),
                        "documented_field": "matrix_diagnostics",
                    },
                    "repo_scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch92_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_blocked_count": 0,
                        "scheduled_run_evidence_count": 0,
                    },
                    "verification": {
                        "wrapper_tests": (
                            "/Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "tests/checkers/test_run_business_line_worker_readback_project_matrix_nightly_unittest.py -q"
                        ),
                        "checker_tests": (
                            "/Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "tests/checkers/test_check_scheduled_automation_artifacts_unittest.py -q"
                        ),
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 92 makes blocked project reasons visible in future scheduler artifacts, but "
                        "does not claim that a real Codex scheduler-produced matrix artifact exists."
                    ),
                    "completion_claim": "matrix_manifest_blocked_project_diagnostics_added_without_claiming_cron_completion",
                },
                "ops_matrix_diagnostics_guidance_projection_extension": {
                    "batch": "93",
                    "proof_level": "ops_visible_matrix_diagnostics_guidance_contract",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "api_contract": {
                        "route": "/api/v1/business-lines/evidence-matrix",
                        "field": "matrix_diagnostics_guidance",
                        "required_fields": MATRIX_DIAGNOSTICS_REQUIRED_FIELDS,
                        "blocked_project_fields": MATRIX_DIAGNOSTICS_BLOCKED_PROJECT_FIELDS,
                        "classification_boundary": (
                            "scheduled_run_blocked is triage evidence, not completion proof; only "
                            "scheduled_run_evidence can close scheduled evidence"
                        ),
                    },
                    "frontend_contract": {
                        "surface": "main/frontend-modern/src/pages/OpsPage.tsx",
                        "test_id": "ops-business-line-matrix-diagnostics-guidance",
                        "compat_fields": ["matrix_diagnostics_guidance", "scheduled_matrix_diagnostics"],
                        "visible_fields": [
                            "source_artifact",
                            "recommended_display_order",
                            "required_fields",
                            "blocked_project_fields",
                            "classification_boundary",
                        ],
                    },
                    "repo_scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch93_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_blocked_count": 0,
                        "scheduled_run_evidence_count": 0,
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                        "frontend_business_line_e2e": (
                            "cd main/frontend-modern && npm run test:e2e -- "
                            "business-line-browser-actions.spec.ts --project=chromium"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 93 projects diagnostics guidance into the user-visible Ops surface, but does "
                        "not claim that a real Codex scheduler-produced matrix artifact exists."
                    ),
                    "completion_claim": "ops_visible_matrix_diagnostics_guidance_added_without_claiming_cron_completion",
                },
                "scheduled_matrix_artifact_summary_bridge_extension": {
                    "batch": "94",
                    "proof_level": "readonly_latest_scheduled_matrix_artifact_summary_bridge",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-matrix-artifact-summary",
                        "contract_version": SCHEDULED_MATRIX_ARTIFACT_SUMMARY_CONTRACT_VERSION,
                        "source_checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
                        "lane": SCHEDULED_MATRIX_LANE,
                        "user_path_params": False,
                        "query_params": False,
                        "fields": [
                            "contract_version",
                            "source_checker",
                            "lane",
                            "status",
                            "lane_classification",
                            "reason",
                            "artifact_path",
                            "diagnostics",
                            "summary",
                            "observed_at",
                            "recommended_command",
                            "completion_boundary",
                        ],
                    },
                    "frontend_contract": {
                        "surface": "main/frontend-modern/src/pages/OpsPage.tsx",
                        "test_id": "ops-business-line-scheduled-matrix-artifact-summary",
                        "visible_fields": [
                            "lane_classification",
                            "status",
                            "reason",
                            "artifact_path",
                            "runtime_preflight_status",
                            "matrix_exit_code",
                            "first_blocked_reason",
                            "completion_boundary",
                        ],
                    },
                    "repo_scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch94_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_blocked_count": 0,
                        "scheduled_run_evidence_count": 0,
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                        "frontend_business_line_e2e": (
                            "cd main/frontend-modern && npm run test:e2e -- "
                            "business-line-browser-actions.spec.ts --project=chromium"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 94 exposes the current checker-derived matrix artifact summary to the Ops UI, "
                        "but does not claim that a real Codex scheduler-produced matrix artifact exists."
                    ),
                    "completion_claim": "readonly_scheduled_matrix_artifact_summary_bridge_added_without_claiming_cron_completion",
                },
                "scheduled_artifact_summaries_bridge_extension": {
                    "batch": "95",
                    "proof_level": "readonly_all_scheduled_lanes_summary_bridge",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-summaries",
                        "contract_version": SCHEDULED_ARTIFACT_SUMMARIES_CONTRACT_VERSION,
                        "source_checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
                        "user_path_params": False,
                        "query_params": False,
                        "lane_source": "checker DEFAULT_LANES plus checker-discovered related lanes",
                        "fields": [
                            "contract_version",
                            "source_checker",
                            "status",
                            "summary",
                            "lanes",
                            "observed_at",
                            "recommended_command",
                            "whitelisted_lanes",
                            "completion_boundary",
                        ],
                        "lane_fields": [
                            "lane",
                            "status",
                            "lane_classification",
                            "reason",
                            "artifact_path",
                            "diagnostics",
                            "observed_at",
                            "recommended_command",
                        ],
                    },
                    "frontend_contract": {
                        "surface": "main/frontend-modern/src/pages/OpsPage.tsx",
                        "test_id": "ops-business-line-scheduled-artifact-summaries",
                        "visible_fields": [
                            "all_scheduled_lanes_status",
                            "summary",
                            "whitelisted_lanes",
                            "lane",
                            "lane_classification",
                            "reason",
                            "artifact_path",
                            "observed_at",
                            "completion_boundary",
                        ],
                        "classification_style_mapping": {
                            "scheduled_run_evidence": "ok",
                            "scheduled_run_blocked": "danger",
                            "manual_dry_run": "warn",
                            "missing": "warn",
                        },
                    },
                    "repo_scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch95_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_blocked_count": 0,
                        "scheduled_run_evidence_count": 0,
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                        "frontend_business_line_e2e": (
                            "cd main/frontend-modern && npm run test:e2e -- "
                            "business-line-browser-actions.spec.ts --project=chromium"
                        ),
                        "frontend_build": "cd main/frontend-modern && npm run build",
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 95 exposes checker-derived summaries for all scheduled lanes to the Ops UI, "
                        "but does not claim that a real Codex scheduler-produced matrix artifact exists."
                    ),
                    "completion_claim": "readonly_all_scheduled_lane_summary_bridge_added_without_claiming_cron_completion",
                },
                "scheduled_artifact_drilldown_extension": {
                    "batch": "96",
                    "proof_level": "readonly_sanitized_scheduled_artifact_drilldown",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "source_checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
                        "user_path_params": False,
                        "query_params": False,
                        "artifact_source": "checker build_report lanes[].artifacts",
                        "redacted_fields": ["absolute_path"],
                        "fields": [
                            "contract_version",
                            "source_checker",
                            "status",
                            "summary",
                            "lanes",
                            "observed_at",
                            "recommended_command",
                            "completion_boundary",
                        ],
                        "lane_fields": [
                            "lane",
                            "status",
                            "lane_classification",
                            "scheduled_completion_proof",
                            "reason",
                            "artifact_path",
                            "base_dir",
                            "artifact_count",
                            "artifacts",
                            "identity_warning_count",
                            "identity_warning_types",
                            "identity_status_counts",
                            "identity_warning_severity_counts",
                            "identity_warning_severity_order",
                            "identity_warning_highest_severity",
                            "identity_warning_highest_severity_rank",
                            "diagnostics",
                            "recommended_command",
                        ],
                        "artifact_fields": [
                            "artifact_path",
                            "classification",
                            "scheduled_completion_proof",
                            "reason",
                            "mtime",
                            "observed_at",
                        ],
                    },
                    "frontend_contract": {
                        "surface": "main/frontend-modern/src/pages/OpsPage.tsx",
                        "test_id": "ops-business-line-scheduled-artifact-drilldown",
                        "visible_fields": [
                            "lane",
                            "lane_classification",
                            "scheduled_completion_proof",
                            "base_dir",
                            "artifact_count",
                            "artifact_path",
                            "diagnostics",
                            "completion_boundary",
                        ],
                        "forbidden_visible_fields": ["absolute_path"],
                    },
                    "repo_scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch96_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_blocked_count": 0,
                        "scheduled_run_evidence_count": 0,
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                        "frontend_business_line_e2e": (
                            "cd main/frontend-modern && npm run test:e2e -- "
                            "business-line-browser-actions.spec.ts --project=chromium"
                        ),
                        "frontend_build": "cd main/frontend-modern && npm run build",
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 96 adds sanitized artifact-level drilldown for triage, but does not expose local "
                        "absolute paths and does not claim that manual_dry_run, missing, or scheduled_run_blocked "
                        "closes scheduled evidence."
                    ),
                    "completion_claim": "readonly_sanitized_scheduled_artifact_drilldown_added_without_claiming_cron_completion",
                },
                "scheduled_artifact_file_identity_extension": {
                    "batch": "97",
                    "proof_level": "readonly_sanitized_artifact_size_checksum_identity",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "source_checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
                        "user_path_params": False,
                        "query_params": False,
                        "artifact_metadata_source": (
                            "internal checker absolute_path is used only for stat/hash computation and is never "
                            "returned in the API response"
                        ),
                        "added_artifact_fields": ["size_bytes", "sha256"],
                        "redacted_fields": ["absolute_path"],
                        "completion_boundary": (
                            "size_bytes and sha256 are artifact identity/triage metadata only; completion proof "
                            "still requires scheduled_completion_proof=true from scheduled_run_evidence"
                        ),
                    },
                    "frontend_contract": {
                        "surface": "main/frontend-modern/src/pages/OpsPage.tsx",
                        "test_id": "ops-business-line-scheduled-artifact-drilldown",
                        "visible_fields": ["size_bytes", "sha256"],
                        "hash_display": "truncated_sha256_label",
                        "forbidden_visible_fields": ["absolute_path"],
                    },
                    "repo_scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch97_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_blocked_count": 0,
                        "scheduled_run_evidence_count": 0,
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                        "frontend_business_line_e2e": (
                            "cd main/frontend-modern && npm run test:e2e -- "
                            "business-line-browser-actions.spec.ts --project=chromium"
                        ),
                        "frontend_build": "cd main/frontend-modern && npm run build",
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 97 adds sanitized artifact size/hash identity for triage, but does not expose local "
                        "absolute paths and does not treat size/hash as scheduled evidence."
                    ),
                    "completion_claim": "readonly_sanitized_artifact_size_checksum_added_without_claiming_cron_completion",
                },
                "scheduled_checker_artifact_identity_provenance_extension": {
                    "batch": "98",
                    "proof_level": "checker_level_artifact_size_checksum_provenance",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "checker_contract": {
                        "checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
                        "artifact_fields": ["size_bytes", "sha256"],
                        "hash_algorithm": "sha256",
                        "artifact_identity_source": "checker artifact_row computes size/hash at collection time",
                        "absolute_path_boundary": (
                            "checker may keep absolute_path for local diagnostics, but business-lines API redacts "
                            "absolute_path and projects only artifact_path, size_bytes, and sha256"
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "projection_mode": "checker_identity_projection_without_api_file_reads",
                        "added_artifact_fields": ["size_bytes", "sha256"],
                        "redacted_fields": ["absolute_path"],
                    },
                    "repo_scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch98_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_blocked_count": 0,
                        "scheduled_run_evidence_count": 0,
                    },
                    "verification": {
                        "checker_tests": (
                            "/Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "tests/checkers/test_check_scheduled_automation_artifacts_unittest.py -q"
                        ),
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                        "frontend_business_line_e2e": (
                            "cd main/frontend-modern && npm run test:e2e -- "
                            "business-line-browser-actions.spec.ts --project=chromium"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 98 moves artifact size/hash provenance into the checker report itself, but size/hash "
                        "remain identity metadata and do not close scheduled evidence."
                    ),
                    "completion_claim": "checker_level_artifact_identity_provenance_added_without_claiming_cron_completion",
                },
                "scheduled_artifact_freshness_window_extension": {
                    "batch": "99",
                    "proof_level": "checker_level_artifact_freshness_identity_window",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "checker_contract": {
                        "checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
                        "window_scope": "per lane artifacts sorted by mtime descending",
                        "artifact_fields": [
                            "freshness_rank",
                            "freshness_window_size",
                            "is_latest_for_lane",
                            "identity_matches_latest",
                            "latest_artifact_path",
                        ],
                        "identity_basis": ["size_bytes", "sha256"],
                        "completion_boundary": (
                            "freshness indicates latest/stale identity comparison only; completion proof still "
                            "requires scheduled_run_evidence"
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "projection_mode": "checker_freshness_projection_without_user_path_params",
                        "added_artifact_fields": [
                            "freshness_rank",
                            "freshness_window_size",
                            "is_latest_for_lane",
                            "identity_matches_latest",
                            "latest_artifact_path",
                        ],
                        "redacted_fields": ["absolute_path"],
                    },
                    "frontend_contract": {
                        "surface": "main/frontend-modern/src/pages/OpsPage.tsx",
                        "test_id": "ops-business-line-scheduled-artifact-drilldown",
                        "visible_fields": [
                            "freshness_rank",
                            "freshness_window_size",
                            "is_latest_for_lane",
                            "identity_matches_latest",
                            "latest_artifact_path",
                        ],
                        "completion_boundary": "freshness is displayed separately from scheduled_completion_proof",
                    },
                    "repo_scheduled_evidence": {
                        "checker_artifact": "/tmp/mrw_batch99_scheduled_automation_artifacts.json",
                        "status": "blocked",
                        "matrix_lane_classification": "missing",
                        "scheduled_run_blocked_count": 0,
                        "scheduled_run_evidence_count": 0,
                    },
                    "verification": {
                        "checker_tests": (
                            "/Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "tests/checkers/test_check_scheduled_automation_artifacts_unittest.py -q"
                        ),
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                        "frontend_business_line_e2e": (
                            "cd main/frontend-modern && npm run test:e2e -- "
                            "business-line-browser-actions.spec.ts --project=chromium"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 99 adds checker-level freshness/rank comparison for artifact triage, but freshness "
                        "does not close scheduled evidence and does not replace scheduled_completion_proof."
                    ),
                    "completion_claim": "checker_level_artifact_freshness_window_added_without_claiming_cron_completion",
                },
                "scheduled_artifact_identity_drift_warning_extension": {
                    "batch": "100",
                    "proof_level": "scheduled_artifact_identity_drift_warning_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "checker_contract": {
                        "checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
                        "artifact_fields": [
                            "identity_status",
                            "identity_warning",
                            "identity_warning_message",
                        ],
                        "identity_drift_boundary": (
                            "identity drift warning fields are checker-derived triage metadata only; "
                            "scheduled_completion_proof remains derived only from scheduled_run_evidence"
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "projection_mode": "checker_identity_drift_warning_projection_without_api_file_reads",
                        "added_artifact_fields": [
                            "identity_status",
                            "identity_warning",
                            "identity_warning_message",
                        ],
                        "redacted_fields": ["absolute_path"],
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 100 exposes checker artifact identity drift warnings for drilldown triage, but "
                        "does not expose absolute_path and does not treat warning status as scheduled completion."
                    ),
                    "completion_claim": "identity_drift_warning_projection_added_without_claiming_cron_completion",
                },
                "scheduled_artifact_identity_warning_grouping_extension": {
                    "batch": "101",
                    "proof_level": "scheduled_artifact_identity_warning_grouping_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "checker_contract": {
                        "checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
                        "lane_fields": [
                            "identity_warning_count",
                            "identity_warning_types",
                            "identity_status_counts",
                        ],
                        "grouping_boundary": (
                            "lane-level identity warning grouping is checker-derived triage metadata only; "
                            "scheduled_completion_proof remains derived only from scheduled_run_evidence"
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "projection_mode": "checker_lane_identity_warning_grouping_projection",
                        "added_lane_fields": [
                            "identity_warning_count",
                            "identity_warning_types",
                            "identity_status_counts",
                        ],
                        "missing_lane_defaults": {
                            "identity_warning_count": 0,
                            "identity_warning_types": [],
                            "identity_status_counts": {},
                        },
                        "redacted_fields": ["absolute_path"],
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 101 exposes lane-level identity warning grouping for drilldown triage, but grouping "
                        "does not expose absolute_path and does not alter scheduled_completion_proof."
                    ),
                    "completion_claim": (
                        "identity_warning_grouping_projection_added_without_claiming_cron_completion"
                    ),
                },
                "scheduled_artifact_same_as_latest_projection_extension": {
                    "batch": "102",
                    "proof_level": "scheduled_artifact_same_as_latest_projection_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "checker_contract": {
                        "checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
                        "triage_status": "same_as_latest",
                        "warning_required": False,
                        "same_as_latest_boundary": (
                            "same_as_latest is a no-warning triage status for stale artifacts whose identity "
                            "matches the latest artifact; it is not scheduler proof and must not alter "
                            "scheduled_completion_proof."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "projection_mode": (
                            "same_as_latest_identity_status_projection_without_scheduler_proof"
                        ),
                        "artifact_identity_statuses": [
                            "latest",
                            "same_as_latest",
                        ],
                        "lane_identity_status_counts": [
                            "latest",
                            "same_as_latest",
                        ],
                        "redacted_fields": ["absolute_path"],
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 102 exposes same_as_latest as no-warning identity triage metadata, but "
                        "scheduled_completion_proof remains derived only from scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "same_as_latest_projection_added_without_claiming_cron_completion"
                    ),
                },
                "scheduled_artifact_identity_warning_severity_extension": {
                    "batch": "103",
                    "proof_level": "scheduled_artifact_identity_warning_severity_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "checker_contract": {
                        "checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
                        "artifact_fields": ["identity_warning_severity"],
                        "lane_fields": ["identity_warning_severity_counts"],
                        "severity_boundary": (
                            "identity warning severity is checker-derived triage priority metadata only; "
                            "scheduled_completion_proof remains derived only from scheduled_run_evidence"
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "projection_mode": "checker_identity_warning_severity_projection",
                        "added_artifact_fields": ["identity_warning_severity"],
                        "added_lane_fields": ["identity_warning_severity_counts"],
                        "missing_lane_defaults": {
                            "identity_warning_severity_counts": {},
                        },
                        "redacted_fields": ["absolute_path"],
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 103 exposes checker identity warning severity as triage priority metadata, but "
                        "scheduled_completion_proof remains derived only from scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "identity_warning_severity_projection_added_without_claiming_cron_completion"
                    ),
                },
                "scheduled_artifact_identity_warning_severity_order_extension": {
                    "batch": "104",
                    "proof_level": (
                        "scheduled_artifact_identity_warning_severity_order_extension"
                    ),
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "checker_contract": {
                        "checker": SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
                        "lane_fields": [
                            "identity_warning_severity_order",
                            "identity_warning_highest_severity",
                            "identity_warning_highest_severity_rank",
                        ],
                        "severity_order_boundary": (
                            "identity warning severity order and highest severity are checker-derived "
                            "triage ordering metadata only; scheduled_completion_proof remains derived "
                            "only from scheduled_run_evidence"
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "projection_mode": "checker_identity_warning_severity_order_projection",
                        "added_lane_fields": [
                            "identity_warning_severity_order",
                            "identity_warning_highest_severity",
                            "identity_warning_highest_severity_rank",
                        ],
                        "missing_lane_defaults": {
                            "identity_warning_severity_order": [],
                            "identity_warning_highest_severity": None,
                            "identity_warning_highest_severity_rank": None,
                        },
                        "redacted_fields": ["absolute_path"],
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 104 exposes checker identity warning severity ordering for triage, but "
                        "the ordering only changes triage priority display and does not change "
                        "scheduled_completion_proof."
                    ),
                    "completion_claim": (
                        "identity_warning_severity_order_projection_added_without_claiming_cron_completion"
                    ),
                },
                "scheduled_artifact_warning_filter_ui_extension": {
                    "batch": "105",
                    "proof_level": "scheduled_artifact_warning_filter_ui_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "ops_ui_contract": {
                        "filter_inputs": [
                            "identity_warning_count",
                            "identity_warning_highest_severity_rank",
                        ],
                        "filter_scope": (
                            "Ops warning-only filter is frontend display filtering only; "
                            "it changes which scheduled artifact rows are shown in Ops UI, "
                            "not the API scheduled evidence semantics."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "proof_addition": "none",
                        "scheduled_completion_proof_source": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "API scheduled_completion_proof and scheduled evidence semantics remain "
                            "unchanged; scheduled_completion_proof is controlled only by "
                            "scheduled_run_evidence."
                        ),
                        "redacted_fields": ["absolute_path"],
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 105 documents the Ops warning-only filter boundary: filter inputs are "
                        "identity_warning_count and identity_warning_highest_severity_rank, and the "
                        "filter only changes Ops UI display. The API adds no proof, and "
                        "scheduled_completion_proof remains derived only from scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "ops_warning_only_filter_ui_boundary_added_without_claiming_real_scheduler_run"
                    ),
                },
                "scheduled_artifact_warning_sort_ui_extension": {
                    "batch": "106",
                    "proof_level": "scheduled_artifact_warning_sort_ui_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "ops_ui_contract": {
                        "sort_inputs": [
                            "identity_warning_highest_severity_rank",
                            "identity_warning_count",
                            "artifact_count",
                        ],
                        "sort_modes": [
                            "source_order",
                            "warning_priority",
                            "warning_count",
                            "artifact_count",
                        ],
                        "sort_scope": (
                            "Ops lane sort is frontend display ordering only; it changes only the "
                            "scheduled artifact row order shown in Ops UI, not the API scheduled "
                            "evidence semantics or proof contract."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "proof_addition": "none",
                        "scheduled_completion_proof_source": "scheduled_run_evidence",
                        "scheduled_evidence_source": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "API scheduled_completion_proof and scheduled evidence semantics remain "
                            "unchanged; scheduled_completion_proof is still controlled only by "
                            "scheduled_run_evidence."
                        ),
                        "redacted_fields": ["absolute_path"],
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 106 documents the Ops lane sort boundary: sort inputs are "
                        "identity_warning_highest_severity_rank, identity_warning_count, and "
                        "artifact_count; sort modes are source_order, warning_priority, warning_count, "
                        "and artifact_count. Sorting changes only Ops UI display order. The API adds "
                        "no proof, scheduled_completion_proof remains derived only from "
                        "scheduled_run_evidence, and scheduled evidence is still controlled by "
                        "scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "ops_lane_sort_ui_boundary_added_without_closing_real_scheduler_run"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the metadata boundary; it does not close "
                        "or replace a real scheduler run."
                    ),
                },
                "scheduled_artifact_warning_sort_explanation_ui_extension": {
                    "batch": "107",
                    "proof_level": "scheduled_artifact_warning_sort_explanation_ui_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "ops_ui_contract": {
                        "explanation_modes": [
                            "source_order",
                            "warning_priority",
                            "warning_count",
                            "artifact_count",
                        ],
                        "explanations": {
                            "source_order": (
                                "Ops UI sort explanation only: preserves the source line order for "
                                "display and does not change scheduled_completion_proof or scheduled evidence."
                            ),
                            "warning_priority": (
                                "Ops UI sort explanation only: explains display ordering by highest "
                                "warning severity and does not change scheduled_completion_proof or "
                                "scheduled evidence."
                            ),
                            "warning_count": (
                                "Ops UI sort explanation only: explains display ordering by warning "
                                "count and does not change scheduled_completion_proof or scheduled evidence."
                            ),
                            "artifact_count": (
                                "Ops UI sort explanation only: explains display ordering by artifact "
                                "count and does not change scheduled_completion_proof or scheduled evidence."
                            ),
                        },
                        "explanation_scope": (
                            "Ops sort explanations describe only why the Ops UI presents scheduled "
                            "artifact rows in a chosen display order; they do not add API proof, do not "
                            "change API fields, and do not change scheduled evidence semantics."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "proof_addition": "none",
                        "api_fields_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_completion_proof_source": "scheduled_run_evidence",
                        "scheduled_evidence_source": "scheduled_run_evidence",
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "API scheduled_completion_proof and scheduled evidence semantics remain "
                            "unchanged; scheduled_completion_proof is still controlled only by "
                            "scheduled_run_evidence, and scheduled evidence is still controlled only by "
                            "scheduled_run_evidence."
                        ),
                        "redacted_fields": ["absolute_path"],
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 107 documents the Ops sort explanation boundary: explanation modes are "
                        "source_order, warning_priority, warning_count, and artifact_count. Each "
                        "explanation is only for Ops UI sort explanation and only explains UI display "
                        "order. The explanation adds no API proof, changes no API fields, does not change "
                        "scheduled_completion_proof, scheduled_completion_proof remains derived only from "
                        "scheduled_run_evidence, and scheduled evidence is still controlled only by "
                        "scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "ops_sort_explanation_ui_boundary_added_without_changing_scheduled_evidence"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the Ops UI sort explanation metadata boundary; "
                        "it does not close, replace, or alter a real scheduled_run_evidence proof."
                    ),
                },
                "scheduled_artifact_warning_empty_state_ui_extension": {
                    "batch": "108",
                    "proof_level": "scheduled_artifact_warning_empty_state_ui_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "ops_ui_contract": {
                        "empty_state_trigger": {
                            "filter": "warning_only filter",
                            "visible_lanes": 0,
                            "visible_lanes_condition": "visible_lanes == 0",
                            "total_lanes_condition": "total_lanes > 0",
                        },
                        "empty_state_message": (
                            "No lanes match the current warning-only view."
                        ),
                        "empty_state_scope": (
                            "Ops warning-only empty state only explains that the current warning-only "
                            "view has no matching lane; total_lanes > 0 means underlying scheduled "
                            "artifact lanes still exist. It does not mean scheduled evidence passed."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "proof_addition": "none",
                        "api_fields_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_completion_proof_source": "scheduled_run_evidence",
                        "scheduled_evidence_source": "scheduled_run_evidence",
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "The warning-only empty state is not scheduled evidence passed, adds no "
                            "API proof, changes no API fields, and does not change "
                            "scheduled_completion_proof; scheduled evidence remains controlled only by "
                            "scheduled_run_evidence."
                        ),
                        "redacted_fields": ["absolute_path"],
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 108 documents the Ops warning-only empty state boundary: the trigger is "
                        "warning_only filter plus visible_lanes == 0 plus total_lanes > 0. The empty "
                        "state message only explains that the current warning-only view has no matching "
                        "lane. The empty state is not equivalent to scheduled evidence passed, adds no "
                        "API proof, changes no API fields, does not change scheduled_completion_proof, "
                        "scheduled_completion_proof remains derived only from scheduled_run_evidence, "
                        "and scheduled evidence is still controlled only by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "ops_warning_only_empty_state_ui_boundary_added_without_changing_scheduled_evidence"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the Ops warning-only empty state metadata "
                        "boundary; it does not close, replace, or alter a real scheduled_run_evidence "
                        "proof."
                    ),
                },
                "scheduled_artifact_warning_empty_diagnostics_ui_extension": {
                    "batch": "109",
                    "proof_level": "scheduled_artifact_warning_empty_diagnostics_ui_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "ops_ui_contract": {
                        "diagnostics_fields": [
                            "filter",
                            "sort",
                            "total_lanes",
                            "visible_lanes",
                            "warning_lanes",
                        ],
                        "diagnostics_scope": (
                            "Ops warning-only empty diagnostics explain only the current warning-only "
                            "empty view parameters: filter, sort, total_lanes, visible_lanes, and "
                            "warning_lanes."
                        ),
                        "empty_diagnostics_boundary": (
                            "Diagnostics describe the current empty UI state parameters only; they do "
                            "not assert scheduled evidence passed and do not add any lane proof."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "proof_addition": "none",
                        "api_fields_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_completion_proof_source": "scheduled_run_evidence",
                        "scheduled_evidence_source": "scheduled_run_evidence",
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "Ops warning-only empty diagnostics add no API proof, change no API "
                            "fields, do not change scheduled_completion_proof, and scheduled "
                            "evidence is still controlled only by scheduled_run_evidence."
                        ),
                        "redacted_fields": ["absolute_path"],
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 109 documents the Ops warning-only empty diagnostics boundary: "
                        "diagnostics fields are filter, sort, total_lanes, visible_lanes, and "
                        "warning_lanes. Diagnostics only explain the current warning-only empty view "
                        "parameters, add no API proof, change no API fields, do not change "
                        "scheduled_completion_proof, scheduled_completion_proof remains derived only "
                        "from scheduled_run_evidence, and scheduled evidence is still controlled only "
                        "by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "ops_warning_only_empty_diagnostics_ui_boundary_added_without_changing_scheduled_evidence"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the Ops warning-only empty diagnostics "
                        "metadata boundary; it does not close, replace, or alter a real "
                        "scheduled_run_evidence proof."
                    ),
                },
                "scheduled_artifact_warning_empty_reset_ui_extension": {
                    "batch": "110",
                    "proof_level": "scheduled_artifact_warning_empty_reset_ui_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "ops_ui_contract": {
                        "reset_action_label": "reset empty warning view: show all lanes",
                        "filter_transition": {
                            "from": "warning_only",
                            "to": "all",
                        },
                        "sort_behavior": "sort remains unchanged",
                        "payload_behavior": "API payload unchanged",
                        "reset_scope": (
                            "Reset action label is reset empty warning view: show all lanes. "
                            "Reset changes only UI filter from warning_only to all; sort remains "
                            "unchanged and API payload unchanged."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/scheduled-artifact-drilldown",
                        "contract_version": SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "api_fields_changed": False,
                        "api_payload_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_completion_proof_source": "scheduled_run_evidence",
                        "scheduled_evidence_source": "scheduled_run_evidence",
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "Ops warning-only empty reset affordance adds no API proof, changes no "
                            "API fields, leaves API payload unchanged, does not change "
                            "scheduled_completion_proof, and scheduled evidence is still controlled "
                            "only by scheduled_run_evidence."
                        ),
                        "redacted_fields": ["absolute_path"],
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 110 documents the Ops warning-only empty reset affordance boundary: "
                        "reset action label is reset empty warning view: show all lanes; reset changes "
                        "only UI filter from warning_only to all; sort remains unchanged; API payload "
                        "unchanged. The reset affordance adds no API proof, changes no API fields, "
                        "does not change scheduled_completion_proof, scheduled_completion_proof remains "
                        "derived only from scheduled_run_evidence, and scheduled evidence is still "
                        "controlled only by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "ops_warning_only_empty_reset_ui_boundary_added_without_changing_scheduled_evidence"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the Ops warning-only empty reset affordance "
                        "metadata boundary; it does not close, replace, or alter a real "
                        "scheduled_run_evidence proof."
                    ),
                },
                "scheduled_artifact_warning_empty_reset_telemetry_ui_extension": {
                    "batch": "111",
                    "proof_level": "scheduled_artifact_warning_empty_reset_telemetry_ui_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "ui_event_contract": {
                        "event_name": "reset_empty_warning_view",
                        "event_scope": "ui_event_log_only",
                        "filter_transition": {
                            "from": "warning_only",
                            "to": "all",
                        },
                        "sort_behavior": "unchanged",
                        "api_payload_behavior": "unchanged",
                        "scheduled_evidence_write": "none",
                        "telemetry_scope": (
                            "Ops reset telemetry records only the UI event log for "
                            "reset_empty_warning_view. It tracks warning_only to all filter "
                            "transition, keeps sort unchanged, keeps API payload unchanged, and "
                            "writes no scheduled evidence."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/evidence-matrix",
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "api_fields_changed": False,
                        "api_payload_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "Ops reset telemetry is UI event log only. It adds no API proof, "
                            "changes no API fields, leaves API payload unchanged, does not change "
                            "scheduled_completion_proof, writes no scheduled evidence, and scheduled "
                            "evidence remains controlled only by scheduled_run_evidence."
                        ),
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 111 documents the Ops reset telemetry boundary: reset_empty_warning_view "
                        "is UI event log only, records warning_only to all filter transition, keeps "
                        "sort unchanged, keeps API payload unchanged, writes no scheduled evidence, "
                        "adds no API proof, changes no API fields, does not change "
                        "scheduled_completion_proof, and scheduled evidence remains controlled only "
                        "by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "ops_warning_only_empty_reset_telemetry_ui_boundary_added_without_changing_scheduled_evidence"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the Ops reset telemetry metadata boundary; "
                        "it does not close, replace, or alter a real scheduled_run_evidence proof."
                    ),
                },
                "dashboard_scheduled_artifact_reset_telemetry_reuse_extension": {
                    "batch": "112",
                    "proof_level": "dashboard_scheduled_artifact_reset_telemetry_reuse_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "dashboard_reuse_contract": {
                        "consumer_surface": "DashboardPage",
                        "source_metadata_key": (
                            "scheduled_artifact_warning_empty_reset_telemetry_ui_extension"
                        ),
                        "display_scope": "read_only_boundary_summary",
                        "event_name": "reset_empty_warning_view",
                        "event_scope": "ui_event_log_only",
                        "scheduled_evidence_write": "none",
                        "reuse_scope": (
                            "Dashboard/report detail reuse may display only a read-only boundary "
                            "summary derived from scheduled_artifact_warning_empty_reset_telemetry_ui_extension. "
                            "It keeps reset_empty_warning_view as ui_event_log_only telemetry and writes "
                            "no scheduled evidence."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/evidence-matrix",
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "api_fields_changed": False,
                        "api_payload_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "Dashboard/report detail reset telemetry reuse is read-only display. "
                            "It adds no API proof, changes no API fields, leaves API payload unchanged, "
                            "does not change scheduled_completion_proof, writes no scheduled evidence, "
                            "and scheduled evidence remains controlled only by scheduled_run_evidence."
                        ),
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 112 documents the Dashboard/report detail reuse boundary for reset "
                        "telemetry: DashboardPage consumes scheduled_artifact_warning_empty_reset_telemetry_ui_extension "
                        "only as a read_only_boundary_summary. The source event remains "
                        "reset_empty_warning_view, event scope remains ui_event_log_only, reuse writes "
                        "no scheduled evidence, adds no API proof, changes no API fields, leaves API "
                        "payload unchanged, does not change scheduled_completion_proof, and scheduled "
                        "evidence remains controlled only by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "dashboard_reset_telemetry_reuse_boundary_added_without_changing_scheduled_evidence"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the Dashboard/report detail read-only reuse "
                        "metadata boundary; it does not close, replace, or alter a real "
                        "scheduled_run_evidence proof."
                    ),
                },
                "dashboard_report_detail_reset_telemetry_reuse_extension": {
                    "batch": "113",
                    "proof_level": "dashboard_report_detail_reset_telemetry_reuse_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "report_detail_reuse_contract": {
                        "consumer_surface": "DashboardPage.report_detail",
                        "source_metadata_key": (
                            "scheduled_artifact_warning_empty_reset_telemetry_ui_extension"
                        ),
                        "display_scope": "report_detail_read_only_boundary_summary",
                        "event_name": "reset_empty_warning_view",
                        "event_scope": "ui_event_log_only",
                        "scheduled_evidence_write": "none",
                        "reuse_scope": (
                            "DashboardPage report detail may display only a read-only boundary "
                            "summary derived from scheduled_artifact_warning_empty_reset_telemetry_ui_extension. "
                            "It keeps reset_empty_warning_view as ui_event_log_only telemetry and writes "
                            "no scheduled evidence."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/evidence-matrix",
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "api_fields_changed": False,
                        "api_payload_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "DashboardPage report detail reset telemetry reuse is read-only display. "
                            "It adds no API proof, changes no API fields, leaves API payload unchanged, "
                            "does not change scheduled_completion_proof, writes no scheduled evidence, "
                            "and scheduled evidence remains controlled only by scheduled_run_evidence."
                        ),
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 113 documents the DashboardPage.report_detail reuse boundary for reset "
                        "telemetry: report detail consumes scheduled_artifact_warning_empty_reset_telemetry_ui_extension "
                        "only as a report_detail_read_only_boundary_summary. The source event remains "
                        "reset_empty_warning_view, event scope remains ui_event_log_only, reuse writes "
                        "no scheduled evidence, adds no API proof, changes no API fields, leaves API "
                        "payload unchanged, does not change scheduled_completion_proof, and scheduled "
                        "evidence remains controlled only by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "dashboard_report_detail_reset_telemetry_reuse_boundary_added_without_changing_scheduled_evidence"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the DashboardPage.report_detail read-only "
                        "reuse metadata boundary; it does not close, replace, or alter a real "
                        "scheduled_run_evidence proof."
                    ),
                },
                "dashboard_reset_telemetry_fallback_boundary_extension": {
                    "batch": "114",
                    "proof_level": "dashboard_reset_telemetry_fallback_boundary_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "fallback_contract": {
                        "consumer_surfaces": ["DashboardPage", "DashboardPage.report_detail"],
                        "fallback_trigger": "missing_or_invalid_reset_telemetry_metadata",
                        "fallback_message": "reset telemetry metadata unavailable",
                        "fallback_not_proof_label": (
                            "fallback boundary: not scheduled_run_evidence proof"
                        ),
                        "scheduled_evidence_write": "none",
                        "scheduled_completion_proof_behavior": "unchanged",
                        "contract_reuse_claim": "none_when_metadata_missing",
                        "fallback_scope": (
                            "Dashboard and DashboardPage.report_detail fallback may show only "
                            "reset telemetry metadata unavailable and the not-proof label when reset "
                            "telemetry metadata is missing or invalid. The fallback must not claim "
                            "contract reuse, must not write scheduled evidence, and must not change "
                            "scheduled_completion_proof."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/evidence-matrix",
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "api_fields_changed": False,
                        "api_payload_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "Dashboard reset telemetry fallback is a conservative unavailable/not-proof "
                            "message for missing or invalid reset telemetry metadata. It adds no API "
                            "proof, changes no API fields, leaves API payload unchanged, does not "
                            "change scheduled_completion_proof, writes no scheduled evidence, and "
                            "scheduled evidence remains controlled only by scheduled_run_evidence."
                        ),
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 114 documents the Dashboard reset telemetry fallback boundary: "
                        "DashboardPage and DashboardPage.report_detail may show reset telemetry "
                        "metadata unavailable only when reset telemetry metadata is missing or invalid. "
                        "The fallback label is fallback boundary: not scheduled_run_evidence proof; "
                        "contract reuse claim is none_when_metadata_missing; fallback writes no "
                        "scheduled evidence, adds no API proof, changes no API fields, leaves API "
                        "payload unchanged, does not change scheduled_completion_proof, and scheduled "
                        "evidence remains controlled only by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "dashboard_reset_telemetry_fallback_boundary_added_without_changing_scheduled_evidence"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the Dashboard reset telemetry fallback "
                        "metadata boundary; it does not close, replace, or alter a real "
                        "scheduled_run_evidence proof."
                    ),
                },
                "dashboard_report_export_reset_telemetry_context_extension": {
                    "batch": "115",
                    "proof_level": "dashboard_report_export_reset_telemetry_context_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "report_export_context_contract": {
                        "consumer_surfaces": [
                            "DashboardPage.report_from_filter_payload",
                            "DashboardPage.report_export_pdf",
                            "DashboardPage.report_export_docx",
                        ],
                        "context_scope": "ui_read_only_evidence_context",
                        "source_metadata_key": (
                            "scheduled_artifact_warning_empty_reset_telemetry_ui_extension"
                        ),
                        "not_report_proof": True,
                        "not_scheduled_run_evidence_proof": True,
                        "scheduled_evidence_write": "none",
                        "scheduled_completion_proof_behavior": "unchanged",
                        "context_semantics": (
                            "Dashboard report/export payload may include reset telemetry boundary "
                            "only as ui_read_only_evidence_context from "
                            "scheduled_artifact_warning_empty_reset_telemetry_ui_extension. The "
                            "context is not report proof, is not scheduled_run_evidence proof, writes "
                            "no scheduled evidence, and does not change scheduled_completion_proof."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/business-lines/evidence-matrix",
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "api_fields_changed": False,
                        "api_payload_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "Dashboard report/export reset telemetry context is UI/read-only evidence "
                            "context only. It adds no API proof, changes no API fields, leaves API "
                            "payload unchanged, does not change scheduled_completion_proof, writes no "
                            "scheduled evidence, and scheduled evidence remains controlled only by "
                            "scheduled_run_evidence."
                        ),
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 115 documents the Dashboard report/export reset telemetry context "
                        "boundary: DashboardPage.report_from_filter_payload, "
                        "DashboardPage.report_export_pdf, and DashboardPage.report_export_docx may "
                        "include reset telemetry boundary only as ui_read_only_evidence_context from "
                        "scheduled_artifact_warning_empty_reset_telemetry_ui_extension. The context "
                        "is not report proof, is not scheduled_run_evidence proof, writes no "
                        "scheduled evidence, adds no API proof, changes no API fields, leaves API "
                        "payload unchanged, does not change scheduled_completion_proof, and scheduled "
                        "evidence remains controlled only by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "dashboard_report_export_reset_telemetry_context_boundary_added_without_changing_scheduled_evidence"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the Dashboard report/export reset telemetry "
                        "context metadata boundary; it does not close, replace, or alter report proof "
                        "or real scheduled_run_evidence proof."
                    ),
                },
                "dashboard_report_export_renderer_reset_telemetry_note_extension": {
                    "batch": "116",
                    "proof_level": "dashboard_report_export_renderer_reset_telemetry_note_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "renderer_contract": {
                        "accepted_payload_field": "reset_telemetry_boundary_context",
                        "renderer_surfaces": [
                            "llm_report.export.pdf",
                            "llm_report.export.docx",
                        ],
                        "render_scope": "boundary_note",
                        "context_scope": "ui_read_only_evidence_context",
                        "not_report_proof": True,
                        "not_quality_gate_input": True,
                        "not_scheduled_run_evidence_proof": True,
                        "scheduled_evidence_write": "none",
                        "scheduled_completion_proof_behavior": "unchanged",
                        "audit_outcome_behavior": "unchanged",
                        "renderer_semantics": (
                            "PDF/DOCX export renderers may print reset telemetry boundary context only "
                            "as a boundary_note from reset_telemetry_boundary_context. The note is not "
                            "report proof, is not quality gate input, is not scheduled_run_evidence "
                            "proof, writes no scheduled evidence, does not change scheduled_completion_proof, "
                            "and does not change export audit outcome."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/llm-report/export/{pdf|docx}",
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "quality_gate_changed": False,
                        "audit_outcome_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "Dashboard reset telemetry export renderer notes are read-only boundary "
                            "notes. They add no API proof, do not participate in quality gate "
                            "decisions, do not alter export audit outcome, write no scheduled evidence, "
                            "and scheduled evidence remains controlled only by scheduled_run_evidence."
                        ),
                    },
                    "verification": {
                        "llm_report_export_renderer": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/unit/test_llm_report_export_service_unittest.py "
                            "main/backend/tests/integration/test_llm_report_api_unittest.py -q "
                            "-k 'reset_telemetry or export_pdf_endpoint_returns_download_response_when_gate_allows "
                            "or export_docx_endpoint_returns_download_response_when_gate_allows'"
                        ),
                        "dashboard_export_payload": (
                            "cd main/frontend-modern && npm run test:e2e -- "
                            "business-line-browser-actions.spec.ts --project=chromium"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 116 documents the Dashboard report/export renderer reset telemetry "
                        "boundary note: PDF/DOCX renderers may consume reset_telemetry_boundary_context "
                        "only as a boundary_note with ui_read_only_evidence_context semantics. The note "
                        "is not report proof, is not quality gate input, is not scheduled_run_evidence "
                        "proof, writes no scheduled evidence, does not change scheduled_completion_proof, "
                        "does not change export audit outcome, and scheduled evidence remains controlled "
                        "only by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "dashboard_report_export_renderer_reset_telemetry_note_added_without_changing_proof_or_audit_outcome"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the PDF/DOCX renderer boundary note for "
                        "Dashboard reset telemetry context; it does not close, replace, or alter report "
                        "proof, quality gate decisions, export audit outcome, or real scheduled_run_evidence proof."
                    ),
                },
                "dashboard_report_export_audit_reset_telemetry_trace_extension": {
                    "batch": "117",
                    "proof_level": "dashboard_report_export_audit_reset_telemetry_trace_extension",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "audit_trace_contract": {
                        "event_fields": [
                            "ui_read_only_context_included",
                            "ui_read_only_context_scope",
                            "ui_read_only_context_source",
                        ],
                        "source_payload_field": "reset_telemetry_boundary_context",
                        "context_scope": "ui_read_only_evidence_context",
                        "trace_scope": "export_audit_read_only_context_trace",
                        "not_report_proof": True,
                        "not_quality_gate_input": True,
                        "not_scheduled_run_evidence_proof": True,
                        "scheduled_evidence_write": "none",
                        "scheduled_completion_proof_behavior": "unchanged",
                        "audit_outcome_behavior": "unchanged",
                        "trace_semantics": (
                            "Export audit may record that PDF/DOCX output included reset telemetry "
                            "ui_read_only_evidence_context via ui_read_only_context_included. The trace "
                            "is not report proof, is not quality gate input, is not scheduled_run_evidence "
                            "proof, writes no scheduled evidence, does not change scheduled_completion_proof, "
                            "and does not change export audit outcome."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/llm-report/export/{pdf|docx}",
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "quality_gate_changed": False,
                        "audit_outcome_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "Dashboard reset telemetry export audit traces are read-only trace metadata. "
                            "They add no API proof, do not participate in quality gate decisions, do not "
                            "alter export audit outcome, write no scheduled evidence, and scheduled evidence "
                            "remains controlled only by scheduled_run_evidence."
                        ),
                    },
                    "verification": {
                        "llm_report_export_audit_trace": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/unit/test_llm_report_export_audit_service_unittest.py "
                            "main/backend/tests/integration/test_llm_report_api_unittest.py -q "
                            "-k 'ui_read_only_context or reset_telemetry or "
                            "export_pdf_endpoint_returns_download_response_when_gate_allows or "
                            "export_docx_endpoint_returns_download_response_when_gate_allows'"
                        ),
                        "dashboard_export_audit_trace": (
                            "cd main/frontend-modern && npm run test:e2e -- "
                            "business-line-browser-actions.spec.ts --project=chromium"
                        ),
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 117 documents the Dashboard report/export audit reset telemetry trace: "
                        "export audit records may include ui_read_only_context_included, "
                        "ui_read_only_context_scope, and ui_read_only_context_source only as read-only "
                        "trace metadata from reset_telemetry_boundary_context. The trace is not report "
                        "proof, is not quality gate input, is not scheduled_run_evidence proof, writes no "
                        "scheduled evidence, does not change scheduled_completion_proof, does not change "
                        "export audit outcome, and scheduled evidence remains controlled only by "
                        "scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "dashboard_report_export_audit_reset_telemetry_trace_added_without_changing_proof_gate_or_audit_outcome"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only export audit trace metadata for Dashboard "
                        "reset telemetry context; it does not close, replace, or alter report proof, "
                        "quality gate decisions, export audit outcome, or real scheduled_run_evidence proof."
                    ),
                },
                "dashboard_report_export_audit_summary_read_only_context_count_rollup": {
                    "batch": "118",
                    "proof_level": "dashboard_report_export_audit_summary_read_only_context_count_rollup",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "summary_rollup_contract": {
                        "summary_field": "ui_read_only_context_included_count",
                        "summary_scope": "export_audit_read_only_context_summary_rollup",
                        "source_event_field": "ui_read_only_context_included",
                        "source_scope_field": "ui_read_only_context_scope",
                        "not_report_proof": True,
                        "not_quality_gate_input": True,
                        "not_scheduled_run_evidence_proof": True,
                        "scheduled_evidence_write": "none",
                        "scheduled_completion_proof_behavior": "unchanged",
                        "audit_outcome_behavior": "unchanged",
                        "rollup_semantics": (
                            "Dashboard export audit summary may expose ui_read_only_context_included_count "
                            "only as an observability count of read-only context traces. The count is not "
                            "report proof, is not quality gate input, is not scheduled_run_evidence proof, "
                            "writes no scheduled evidence, does not change scheduled_completion_proof, and "
                            "does not change export audit outcome."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/dashboard/stats",
                        "summary_container": "llm_report_quality.summary.export_events",
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "quality_gate_changed": False,
                        "audit_outcome_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "ui_read_only_context_included_count is a summary rollup for Dashboard display "
                            "and audit observability only. It adds no API proof, does not participate in "
                            "quality gate decisions, does not alter export audit outcome, writes no scheduled "
                            "evidence, and scheduled evidence remains controlled only by scheduled_run_evidence."
                        ),
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        )
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 118 documents the Dashboard export audit summary rollup: "
                        "ui_read_only_context_included_count may count read-only context traces for display "
                        "and observability only. It is not report proof, is not quality gate input, is not "
                        "scheduled_run_evidence proof, writes no scheduled evidence, does not change "
                        "scheduled_completion_proof, does not change export audit outcome, and scheduled "
                        "evidence remains controlled only by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "dashboard_report_export_audit_summary_read_only_context_count_added_without_changing_proof_gate_or_audit_outcome"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only the summary rollup metadata for "
                        "ui_read_only_context_included_count; it does not close, replace, or alter report "
                        "proof, quality gate decisions, export audit outcome, or real scheduled_run_evidence proof."
                    ),
                },
                "llm_report_quality_trends_read_only_context_count_parity": {
                    "batch": "119",
                    "proof_level": "llm_report_quality_trends_read_only_context_count_parity",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "quality_trends_parity_contract": {
                        "summary_field": "ui_read_only_context_included_count",
                        "source_summary_container": "llm_report_quality.summary.export_events",
                        "parity_container": "quality_trends.export_events",
                        "not_report_proof": True,
                        "not_quality_gate_input": True,
                        "not_scheduled_run_evidence_proof": True,
                        "scheduled_evidence_write": "none",
                        "scheduled_completion_proof_behavior": "unchanged",
                        "audit_outcome_behavior": "unchanged",
                        "parity_semantics": (
                            "The /api/v1/llm-report/quality-trends parity may expose "
                            "ui_read_only_context_included_count only so the trends response matches the "
                            "Dashboard export audit summary observability field. The count is not report proof, "
                            "is not quality gate input, is not scheduled_run_evidence proof, writes no scheduled "
                            "evidence, does not change scheduled_completion_proof, and does not change export "
                            "audit outcome."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/llm-report/quality-trends",
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "quality_gate_changed": False,
                        "audit_outcome_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "quality-trends read-only context count parity is an observability parity field "
                            "only. It adds no API proof, does not participate in quality gate decisions, does "
                            "not alter export audit outcome, writes no scheduled evidence, and scheduled "
                            "evidence remains controlled only by scheduled_run_evidence."
                        ),
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        )
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 119 documents /api/v1/llm-report/quality-trends parity for "
                        "ui_read_only_context_included_count. The parity is only an observability count, is not "
                        "report proof, is not quality gate input, is not scheduled_run_evidence proof, writes no "
                        "scheduled evidence, does not change scheduled_completion_proof, does not change export "
                        "audit outcome, and scheduled evidence remains controlled only by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "llm_report_quality_trends_read_only_context_count_parity_added_without_changing_proof_gate_or_audit_outcome"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only quality-trends parity for "
                        "ui_read_only_context_included_count; it does not close, replace, or alter report proof, "
                        "quality gate decisions, export audit outcome, or real scheduled_run_evidence proof."
                    ),
                },
                "dashboard_report_export_audit_table_header_i18n_copy": {
                    "batch": "119",
                    "proof_level": "dashboard_report_export_audit_table_header_i18n_copy",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "audit_ui_copy_i18n_contract": {
                        "ui_surface": "Dashboard export audit table header",
                        "i18n_key": "dashboardPage.field.exportReadOnlyContextTrace",
                        "copy_scope": "export_audit_read_only_context_trace_header",
                        "not_report_proof": True,
                        "not_quality_gate_input": True,
                        "not_scheduled_run_evidence_proof": True,
                        "scheduled_evidence_write": "none",
                        "scheduled_completion_proof_behavior": "unchanged",
                        "audit_outcome_behavior": "unchanged",
                        "copy_semantics": (
                            "Dashboard export audit table header i18n copy labels the read-only context trace "
                            "column for users. The copy is not report proof, is not quality gate input, is not "
                            "scheduled_run_evidence proof, writes no scheduled evidence, does not change "
                            "scheduled_completion_proof, and does not change export audit outcome."
                        ),
                    },
                    "api_contract": {
                        "route": "Dashboard UI surface: /dashboard",
                        "ui_surface": "DashboardPage.exportAudit.table.header.readOnlyContextTrace",
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "quality_gate_changed": False,
                        "audit_outcome_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "Dashboard export audit table header i18n is UI copy only. It adds no API proof, "
                            "does not participate in quality gate decisions, does not alter export audit "
                            "outcome, writes no scheduled evidence, and scheduled evidence remains controlled "
                            "only by scheduled_run_evidence."
                        ),
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        )
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 119 documents Dashboard export audit table header i18n copy for the read-only "
                        "context trace column. The copy is UI labeling only, is not report proof, is not quality "
                        "gate input, is not scheduled_run_evidence proof, writes no scheduled evidence, does not "
                        "change scheduled_completion_proof, does not change export audit outcome, and scheduled "
                        "evidence remains controlled only by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "dashboard_report_export_audit_table_header_i18n_copy_added_without_changing_proof_gate_or_audit_outcome"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only Dashboard export audit table header i18n copy; it "
                        "does not close, replace, or alter report proof, quality gate decisions, export audit "
                        "outcome, or real scheduled_run_evidence proof."
                    ),
                },
                "dashboard_report_detail_export_read_only_context_summary": {
                    "batch": "119",
                    "proof_level": "dashboard_report_detail_export_read_only_context_summary",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "report_detail_summary_contract": {
                        "route": "/api/v1/dashboard/llm-report-detail",
                        "summary_container": "export_audit.summary",
                        "mirror_container": "export_events_summary",
                        "summary_field": "ui_read_only_context_included_count",
                        "source_event_field": "ui_read_only_context_included",
                        "not_report_proof": True,
                        "not_quality_gate_input": True,
                        "not_scheduled_run_evidence_proof": True,
                        "scheduled_evidence_write": "none",
                        "scheduled_completion_proof_behavior": "unchanged",
                        "audit_outcome_behavior": "unchanged",
                        "summary_semantics": (
                            "Dashboard report detail may aggregate export audit events into "
                            "ui_read_only_context_included_count for trace-level visibility only. The summary "
                            "is not report proof, is not quality gate input, is not scheduled_run_evidence proof, "
                            "writes no scheduled evidence, does not change scheduled_completion_proof, and does "
                            "not change export audit outcome."
                        ),
                    },
                    "api_contract": {
                        "route": "/api/v1/dashboard/llm-report-detail",
                        "proof_addition": "none",
                        "api_proof_added": False,
                        "quality_gate_changed": False,
                        "audit_outcome_changed": False,
                        "scheduled_completion_proof_changed": False,
                        "scheduled_evidence_controller": "scheduled_run_evidence",
                        "scheduled_evidence_semantics": (
                            "Report detail read-only context summary is trace-level observability only. It adds "
                            "no API proof, does not participate in quality gate decisions, does not alter export "
                            "audit outcome, writes no scheduled evidence, and scheduled evidence remains controlled "
                            "only by scheduled_run_evidence."
                        ),
                    },
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        )
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 119 documents Dashboard report detail export read-only context summary. "
                        "ui_read_only_context_included_count is trace-level observability only, is not report "
                        "proof, is not quality gate input, is not scheduled_run_evidence proof, writes no scheduled "
                        "evidence, does not change scheduled_completion_proof, does not change export audit outcome, "
                        "and scheduled evidence remains controlled only by scheduled_run_evidence."
                    ),
                    "completion_claim": (
                        "dashboard_report_detail_export_read_only_context_summary_added_without_changing_proof_gate_or_audit_outcome"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only Dashboard report detail export read-only context "
                        "summary; it does not close, replace, or alter report proof, quality gate decisions, "
                        "export audit outcome, or real scheduled_run_evidence proof."
                    ),
                },
                "read_only_context_proof_boundary_compression": {
                    "batch": "120",
                    "proof_level": "read_only_context_proof_boundary_compression",
                    "covered_line_keys": ["runtime_ops", *WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS],
                    "shared_boundary_contract": {
                        "shared_helper": "_read_only_context_proof_boundary",
                        "shared_constant": "READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS",
                        "boundary_fields": _read_only_context_proof_boundary(),
                        "boundary_semantics": (
                            "Batch 120 freezes reset telemetry and read-only context follow-ups unless they "
                            "directly block an active user flow. The shared boundary records only proof semantics; "
                            "it adds no export audit fields, Dashboard copy-only improvements, quality gate input, "
                            "scheduled_run_evidence, or scheduled completion proof."
                        ),
                    },
                    "frozen_scope": _read_only_context_proof_boundary(
                        reset_telemetry_followups="frozen_unless_user_flow_blocking",
                        read_only_context_followups="frozen_unless_user_flow_blocking",
                        remaining_polish="deferred_polish_unless_active_user_flow_blocking",
                        no_new_export_audit_fields=True,
                        no_new_dashboard_copy_only_improvements=True,
                    ),
                    "api_contract": _read_only_context_proof_boundary(
                        proof_addition="none",
                        api_proof_added=False,
                        quality_gate_changed=False,
                        audit_outcome_changed=False,
                        scheduled_completion_proof_changed=False,
                        scheduled_evidence_controller="scheduled_run_evidence",
                        scheduled_evidence_semantics=(
                            "Batch 120 compresses repeated proof-boundary wording only. It does not change "
                            "scheduled checker behavior, export audit outcome, quality gate decisions, report "
                            "proof, or any scheduled_run_evidence requirement."
                        ),
                    ),
                    "verification": {
                        "business_line_evidence_contract": (
                            "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest "
                            "main/backend/tests/core_business/test_business_line_evidence_contract.py -q"
                        )
                    },
                    "scheduled_evidence_boundary": (
                        "Batch 120 documents proof boundary compression only. reset telemetry and read-only "
                        "context follow-ups are frozen unless user-flow blocking; this batch writes no scheduled "
                        "evidence, does not add export audit fields, does not add Dashboard copy-only "
                        "improvements, does not change scheduled_completion_proof, and does not change export "
                        "audit outcome."
                    ),
                    "completion_claim": (
                        "read_only_context_proof_boundary_compression_added_without_behavior_or_proof_change"
                    ),
                    "completion_claim_boundary": (
                        "The completion_claim records only shared proof-boundary vocabulary and frozen scope; "
                        "it does not close, replace, or alter report proof, quality gate decisions, export audit "
                        "outcome, scheduled checker behavior, or real scheduled_run_evidence proof."
                    ),
                },
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
                entrypoints=["WritingWorkbenchPage", "GraphPage", "AgentChatPage", "LlmDesignerPage"],
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
