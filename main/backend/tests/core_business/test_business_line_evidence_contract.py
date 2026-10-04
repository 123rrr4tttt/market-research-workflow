from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from fastapi.routing import APIRoute

    from app.api import router as api_router
    from app.api.business_lines import (
        ASYNC_TASK_READBACK_ARTIFACT_CHECKER_SCRIPT,
        ASYNC_TASK_READBACK_LIVE_SAMPLE_RUNNER_SCRIPT,
        ASYNC_TASK_READBACK_WORKER_MANIFEST_CLI,
        ASYNC_TASK_READBACK_WORKER_MANIFEST_CANDIDATE_BUILDER_SCRIPT,
        ASYNC_TASK_READBACK_WORKER_MANIFEST_CHECKER_SCRIPT,
        ASYNC_TASK_READBACK_WORKER_EVIDENCE_CHAIN_SCRIPT,
        CONTRACT_VERSION,
        LINE_KEYS,
        MATRIX_DIAGNOSTICS_BLOCKED_PROJECT_FIELDS,
        MATRIX_DIAGNOSTICS_RECOMMENDED_DISPLAY_ORDER,
        MATRIX_DIAGNOSTICS_REQUIRED_FIELDS,
        PROCESS_STATS_PROBE_PATH,
        READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS,
        REAL_BACKEND_BROWSER_SMOKE_TEST_FILE,
        SCHEDULED_ARTIFACT_CHECKER_SCRIPT,
        SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION,
        SCHEDULED_ARTIFACT_SUMMARIES_CONTRACT_VERSION,
        SCHEDULED_MATRIX_ARTIFACT_SUMMARY_CONTRACT_VERSION,
        SCHEDULED_MATRIX_LANE,
        TRACE_BASELINE_BODY_TRACE_EXEMPT_PROBE_PATHS,
        TRACE_BASELINE_CONTRACT_VERSION,
        TRACE_BASELINE_DEFAULT_SLOW_THRESHOLD_MS,
        TRACE_BASELINE_RECOMMENDED_COMMAND,
        TRACE_BASELINE_RUNNER_SCRIPT,
        WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS,
        _drilldown_scheduled_lane,
        _read_only_context_proof_boundary,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


pytestmark = [pytest.mark.contract, pytest.mark.mocked]

REQUIRED_LINE_FIELDS = {
    "line_key",
    "user_task",
    "entrypoints",
    "api_groups",
    "evidence_contracts",
    "current_gaps",
    "next_remediation",
    "robustness_controls",
    "verification_commands",
    "live_smoke",
    "trace_baseline",
    "real_backend_browser_smoke",
    "async_execution_readiness",
    "async_task_readback",
}

REQUIRED_LIVE_SMOKE_FIELDS = {
    "probe_path",
    "expected_statuses",
    "proof_level",
    "blocked_semantics",
    "recommended_command",
    "response_assertions",
}

REQUIRED_RESPONSE_ASSERTION_FIELDS = {
    "envelope_required",
    "required_data_paths",
    "semantic_fields",
    "failure_classification",
}

REQUIRED_TRACE_BASELINE_FIELDS = {
    "contract_version",
    "proof_level",
    "runner_script",
    "recommended_command",
    "probe_path",
    "request_headers",
    "response_headers",
    "body_meta_trace",
    "duration_evidence",
    "failure_classification",
    "completion_claim",
}

REQUIRED_REAL_BACKEND_BROWSER_SMOKE_FIELDS = {
    "proof_level",
    "test_file",
    "route_path",
    "readiness_gate",
    "blocked_semantics",
    "browser_assertions",
}

REQUIRED_ASYNC_EXECUTION_READINESS_FIELDS = {
    "proof_level",
    "process_stats_probe",
    "requires_worker",
    "async_surfaces",
    "blocked_semantics",
    "verification_artifact",
}

REQUIRED_ASYNC_TASK_READBACK_FIELDS = {
    "proof_level",
    "requires_worker_readback",
    "readback_artifact",
    "readback_paths",
    "required_events",
    "terminal_states",
    "blocked_semantics",
}

REQUIRED_MATRIX_DIAGNOSTICS_GUIDANCE_FIELDS = {
    "source_lane",
    "source_artifact",
    "consumer_surface",
    "recommended_display_order",
    "required_fields",
    "blocked_project_fields",
    "classification_boundary",
}

REQUIRED_SCHEDULED_MATRIX_ARTIFACT_SUMMARY_FIELDS = {
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
}

REQUIRED_SCHEDULED_ARTIFACT_SUMMARIES_FIELDS = {
    "contract_version",
    "source_checker",
    "status",
    "summary",
    "lanes",
    "observed_at",
    "recommended_command",
    "whitelisted_lanes",
    "completion_boundary",
}

REQUIRED_SCHEDULED_ARTIFACT_SUMMARY_LANE_FIELDS = {
    "lane",
    "status",
    "lane_classification",
    "reason",
    "artifact_path",
    "diagnostics",
    "observed_at",
    "recommended_command",
}

REQUIRED_SCHEDULED_ARTIFACT_DRILLDOWN_FIELDS = {
    "contract_version",
    "source_checker",
    "status",
    "summary",
    "lanes",
    "observed_at",
    "recommended_command",
    "completion_boundary",
}

REQUIRED_SCHEDULED_ARTIFACT_DRILLDOWN_LANE_FIELDS = {
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
}

REQUIRED_SCHEDULED_ARTIFACT_DRILLDOWN_ARTIFACT_FIELDS = {
    "artifact_path",
    "classification",
    "scheduled_completion_proof",
    "reason",
    "mtime",
    "observed_at",
    "size_bytes",
    "sha256",
    "freshness_rank",
    "freshness_window_size",
    "is_latest_for_lane",
    "identity_matches_latest",
    "latest_artifact_path",
    "identity_status",
    "identity_warning",
    "identity_warning_message",
    "identity_warning_severity",
}

DEFAULT_SCHEDULED_ARTIFACT_DRILLDOWN_LANES = {
    "performance_capacity_baseline_nightly",
    "llm_report_token_state_retention_nightly",
    "business_line_worker_readback_project_matrix_nightly",
}

ASYNC_TASK_READBACK_REQUIRES_WORKER = {
    "ingest": True,
    "search_discovery_index": True,
    "resource_source_library": True,
    "projects_config_workflow": False,
    "dashboard_admin_governance": False,
    "writing_knowledge_graph_agent": True,
    "runtime_ops": False,
}


@pytest.fixture
def client() -> TestClient:
    if _IMPORT_ERROR is not None:
        pytest.skip(f"business line evidence contract tests require backend dependencies: {_IMPORT_ERROR}")

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    return TestClient(app)


def test_business_line_evidence_matrix_route_is_registered() -> None:
    if _IMPORT_ERROR is not None:
        pytest.skip(f"business line evidence contract tests require backend dependencies: {_IMPORT_ERROR}")

    paths = {route.path for route in api_router.routes if isinstance(route, APIRoute)}

    assert "/business-lines/evidence-matrix" in paths


def test_scheduled_matrix_artifact_summary_route_is_registered_without_user_path() -> None:
    if _IMPORT_ERROR is not None:
        pytest.skip(f"business line evidence contract tests require backend dependencies: {_IMPORT_ERROR}")

    route = next(
        (
            route
            for route in api_router.routes
            if isinstance(route, APIRoute)
            and route.path == "/business-lines/scheduled-matrix-artifact-summary"
        ),
        None,
    )

    assert route is not None
    assert not route.dependant.path_params
    assert not route.dependant.query_params


def test_scheduled_artifact_summaries_route_is_registered_without_user_path() -> None:
    if _IMPORT_ERROR is not None:
        pytest.skip(f"business line evidence contract tests require backend dependencies: {_IMPORT_ERROR}")

    route = next(
        (
            route
            for route in api_router.routes
            if isinstance(route, APIRoute)
            and route.path == "/business-lines/scheduled-artifact-summaries"
        ),
        None,
    )

    assert route is not None
    assert not route.dependant.path_params
    assert not route.dependant.query_params


def test_scheduled_artifact_drilldown_route_is_registered_without_user_path() -> None:
    if _IMPORT_ERROR is not None:
        pytest.skip(f"business line evidence contract tests require backend dependencies: {_IMPORT_ERROR}")

    route = next(
        (
            route
            for route in api_router.routes
            if isinstance(route, APIRoute)
            and route.path == "/business-lines/scheduled-artifact-drilldown"
        ),
        None,
    )

    assert route is not None
    assert not route.dependant.path_params
    assert not route.dependant.query_params


def test_scheduled_matrix_artifact_summary_contract(client: TestClient) -> None:
    response = client.get("/api/v1/business-lines/scheduled-matrix-artifact-summary")

    assert response.status_code == 200
    body = response.json()
    assert {"status", "data", "error", "meta"}.issubset(body.keys())
    assert body["status"] == "ok"
    assert body["error"] is None

    data = body["data"]
    assert REQUIRED_SCHEDULED_MATRIX_ARTIFACT_SUMMARY_FIELDS.issubset(data.keys())
    assert data["contract_version"] == SCHEDULED_MATRIX_ARTIFACT_SUMMARY_CONTRACT_VERSION
    assert data["source_checker"] == SCHEDULED_ARTIFACT_CHECKER_SCRIPT
    assert data["lane"] == SCHEDULED_MATRIX_LANE
    assert data["status"] in {"passed", "blocked", "checker_unavailable"}
    assert data["lane_classification"] in {
        "scheduled_run_evidence",
        "scheduled_run_blocked",
        "manual_dry_run",
        "missing",
        "checker_unavailable",
    }
    assert isinstance(data["reason"], str)
    assert data["reason"]
    assert data["artifact_path"] is None or isinstance(data["artifact_path"], str)
    assert isinstance(data["diagnostics"], dict)
    assert isinstance(data["summary"], dict)
    assert isinstance(data["observed_at"], str)
    assert data["observed_at"]
    assert data["recommended_command"]
    assert "check_scheduled_automation_artifacts.py" in data["recommended_command"]

    completion_boundary = data["completion_boundary"]
    assert "scheduled_run_blocked" in completion_boundary
    assert "scheduled_run_evidence" in completion_boundary
    assert "not completion proof" in completion_boundary["scheduled_run_blocked"]
    assert "Only scheduled_run_evidence can close scheduled evidence" in (
        completion_boundary["scheduled_run_evidence"]
    )
    assert completion_boundary["completion_claim"] == "does_not_claim_real_scheduler_run"
    if data["lane_classification"] != "scheduled_run_evidence":
        assert data["status"] != "passed"


def test_scheduled_artifact_summaries_contract(client: TestClient) -> None:
    response = client.get("/api/v1/business-lines/scheduled-artifact-summaries")

    assert response.status_code == 200
    body = response.json()
    assert {"status", "data", "error", "meta"}.issubset(body.keys())
    assert body["status"] == "ok"
    assert body["error"] is None

    data = body["data"]
    assert REQUIRED_SCHEDULED_ARTIFACT_SUMMARIES_FIELDS.issubset(data.keys())
    assert data["contract_version"] == SCHEDULED_ARTIFACT_SUMMARIES_CONTRACT_VERSION
    assert data["source_checker"] == SCHEDULED_ARTIFACT_CHECKER_SCRIPT
    assert data["status"] in {"passed", "blocked", "checker_unavailable"}
    assert isinstance(data["summary"], dict)
    assert isinstance(data["lanes"], list)
    assert isinstance(data["observed_at"], str)
    assert data["observed_at"]
    assert "check_scheduled_automation_artifacts.py" in data["recommended_command"]
    assert isinstance(data["whitelisted_lanes"], list)
    assert SCHEDULED_MATRIX_LANE in data["whitelisted_lanes"]

    completion_boundary = data["completion_boundary"]
    assert "scheduled_run_blocked" in completion_boundary
    assert "manual_dry_run" in completion_boundary
    assert "missing" in completion_boundary
    assert "scheduled_run_evidence" in completion_boundary
    assert "not completion proof" in completion_boundary["scheduled_run_blocked"]
    assert "not completion proof" in completion_boundary["manual_dry_run"]
    assert "not completion proof" in completion_boundary["missing"]
    assert "Only scheduled_run_evidence can close scheduled evidence" in (
        completion_boundary["scheduled_run_evidence"]
    )
    assert completion_boundary["completion_claim"] == "does_not_claim_real_scheduler_run"

    if data["status"] == "checker_unavailable":
        assert data["lanes"] == []
        return

    assert data["lanes"]
    lane_names = {lane["lane"] for lane in data["lanes"] if isinstance(lane, dict)}
    assert SCHEDULED_MATRIX_LANE in lane_names
    for lane in data["lanes"]:
        assert REQUIRED_SCHEDULED_ARTIFACT_SUMMARY_LANE_FIELDS.issubset(lane.keys())
        assert isinstance(lane["lane"], str)
        assert lane["lane"]
        assert lane["status"] in {"passed", "blocked"}
        assert lane["lane_classification"] in {
            "scheduled_run_evidence",
            "scheduled_run_blocked",
            "manual_dry_run",
            "missing",
        }
        assert isinstance(lane["reason"], str)
        assert lane["reason"]
        assert lane["artifact_path"] is None or isinstance(lane["artifact_path"], str)
        assert isinstance(lane["diagnostics"], dict)
        assert isinstance(lane["observed_at"], str)
        assert lane["observed_at"]
        assert "check_scheduled_automation_artifacts.py" in lane["recommended_command"]
        if lane["lane_classification"] != "scheduled_run_evidence":
            assert lane["status"] != "passed"


def test_scheduled_artifact_drilldown_contract(client: TestClient) -> None:
    response = client.get("/api/v1/business-lines/scheduled-artifact-drilldown")

    assert response.status_code == 200
    body = response.json()
    assert {"status", "data", "error", "meta"}.issubset(body.keys())
    assert body["status"] == "ok"
    assert body["error"] is None
    assert "absolute_path" not in response.text

    data = body["data"]
    assert REQUIRED_SCHEDULED_ARTIFACT_DRILLDOWN_FIELDS.issubset(data.keys())
    assert data["contract_version"] == SCHEDULED_ARTIFACT_DRILLDOWN_CONTRACT_VERSION
    assert data["source_checker"] == SCHEDULED_ARTIFACT_CHECKER_SCRIPT
    assert data["status"] in {"passed", "blocked", "checker_unavailable"}
    assert isinstance(data["summary"], dict)
    assert isinstance(data["lanes"], list)
    assert isinstance(data["observed_at"], str)
    assert data["observed_at"]
    assert "check_scheduled_automation_artifacts.py" in data["recommended_command"]

    completion_boundary = data["completion_boundary"]
    assert "scheduled_run_blocked" in completion_boundary
    assert "manual_dry_run" in completion_boundary
    assert "missing" in completion_boundary
    assert "scheduled_run_evidence" in completion_boundary
    assert "not completion proof" in completion_boundary["scheduled_run_blocked"]
    assert "not completion proof" in completion_boundary["manual_dry_run"]
    assert "not completion proof" in completion_boundary["missing"]
    assert "Only scheduled_run_evidence can close scheduled evidence" in (
        completion_boundary["scheduled_run_evidence"]
    )
    assert completion_boundary["completion_claim"] == "does_not_claim_real_scheduler_run"

    if data["status"] == "checker_unavailable":
        assert data["lanes"] == []
        return

    assert data["lanes"]
    lane_names = {lane["lane"] for lane in data["lanes"] if isinstance(lane, dict)}
    assert DEFAULT_SCHEDULED_ARTIFACT_DRILLDOWN_LANES.issubset(lane_names)

    for lane in data["lanes"]:
        assert REQUIRED_SCHEDULED_ARTIFACT_DRILLDOWN_LANE_FIELDS.issubset(lane.keys())
        assert isinstance(lane["lane"], str)
        assert lane["lane"]
        assert lane["status"] in {"passed", "blocked"}
        assert lane["lane_classification"] in {
            "scheduled_run_evidence",
            "scheduled_run_blocked",
            "manual_dry_run",
            "missing",
        }
        assert isinstance(lane["scheduled_completion_proof"], bool)
        assert lane["scheduled_completion_proof"] == (
            lane["lane_classification"] == "scheduled_run_evidence"
        )
        assert isinstance(lane["reason"], str)
        assert lane["reason"]
        assert lane["artifact_path"] is None or isinstance(lane["artifact_path"], str)
        assert isinstance(lane["base_dir"], str)
        assert lane["base_dir"]
        assert isinstance(lane["artifact_count"], int)
        assert isinstance(lane["artifacts"], list)
        assert lane["artifact_count"] == len(lane["artifacts"])
        assert isinstance(lane["identity_warning_count"], int)
        assert not isinstance(lane["identity_warning_count"], bool)
        assert lane["identity_warning_count"] >= 0
        assert isinstance(lane["identity_warning_types"], list)
        assert all(
            isinstance(identity_warning_type, str) and identity_warning_type
            for identity_warning_type in lane["identity_warning_types"]
        )
        assert isinstance(lane["identity_status_counts"], dict)
        assert all(
            isinstance(identity_status, str)
            and identity_status
            and isinstance(identity_status_count, int)
            and not isinstance(identity_status_count, bool)
            and identity_status_count >= 0
            for identity_status, identity_status_count in lane["identity_status_counts"].items()
        )
        assert isinstance(lane["identity_warning_severity_counts"], dict)
        assert all(
            isinstance(identity_warning_severity, str)
            and identity_warning_severity
            and isinstance(identity_warning_severity_count, int)
            and not isinstance(identity_warning_severity_count, bool)
            and identity_warning_severity_count >= 0
            for (
                identity_warning_severity,
                identity_warning_severity_count,
            ) in lane["identity_warning_severity_counts"].items()
        )
        assert isinstance(lane["identity_warning_severity_order"], list)
        assert all(
            isinstance(identity_warning_severity, str)
            and identity_warning_severity
            for identity_warning_severity in lane["identity_warning_severity_order"]
        )
        assert lane["identity_warning_highest_severity"] is None or isinstance(
            lane["identity_warning_highest_severity"], str
        )
        assert lane["identity_warning_highest_severity_rank"] is None or (
            isinstance(lane["identity_warning_highest_severity_rank"], int)
            and not isinstance(lane["identity_warning_highest_severity_rank"], bool)
            and lane["identity_warning_highest_severity_rank"] > 0
        )
        assert isinstance(lane["diagnostics"], dict)
        assert "check_scheduled_automation_artifacts.py" in lane["recommended_command"]
        if lane["lane_classification"] != "scheduled_run_evidence":
            assert lane["status"] != "passed"
        if lane["lane_classification"] == "missing":
            assert lane["artifacts"] == []
            assert lane["artifact_count"] == 0

        for artifact in lane["artifacts"]:
            assert REQUIRED_SCHEDULED_ARTIFACT_DRILLDOWN_ARTIFACT_FIELDS.issubset(
                artifact.keys()
            )
            assert "absolute_path" not in artifact
            assert isinstance(artifact["artifact_path"], str)
            assert artifact["artifact_path"]
            assert artifact["classification"] in {
                "scheduled_run_evidence",
                "scheduled_run_blocked",
                "manual_dry_run",
                "missing",
            }
            assert isinstance(artifact["scheduled_completion_proof"], bool)
            assert artifact["scheduled_completion_proof"] == (
                artifact["classification"] == "scheduled_run_evidence"
            )
            assert isinstance(artifact["reason"], str)
            assert artifact["reason"]
            assert artifact["mtime"] is None or isinstance(artifact["mtime"], str)
            assert artifact["observed_at"] is None or isinstance(artifact["observed_at"], str)
            assert artifact["size_bytes"] is None or isinstance(artifact["size_bytes"], int)
            if isinstance(artifact["size_bytes"], int):
                assert artifact["size_bytes"] >= 0
            assert artifact["sha256"] is None or isinstance(artifact["sha256"], str)
            if isinstance(artifact["sha256"], str):
                assert len(artifact["sha256"]) == 64
            assert artifact["freshness_rank"] is None or isinstance(artifact["freshness_rank"], int)
            if isinstance(artifact["freshness_rank"], int):
                assert artifact["freshness_rank"] >= 1
            assert artifact["freshness_window_size"] is None or isinstance(
                artifact["freshness_window_size"], int
            )
            if isinstance(artifact["freshness_window_size"], int):
                assert artifact["freshness_window_size"] >= 1
            assert artifact["is_latest_for_lane"] is None or isinstance(
                artifact["is_latest_for_lane"], bool
            )
            assert artifact["identity_matches_latest"] is None or isinstance(
                artifact["identity_matches_latest"], bool
            )
            assert artifact["latest_artifact_path"] is None or isinstance(
                artifact["latest_artifact_path"], str
            )
            assert artifact["identity_status"] is None or isinstance(
                artifact["identity_status"], str
            )
            assert artifact["identity_warning"] is None or isinstance(
                artifact["identity_warning"], str
            )
            assert artifact["identity_warning_message"] is None or isinstance(
                artifact["identity_warning_message"], str
            )
            assert artifact["identity_warning_severity"] is None or isinstance(
                artifact["identity_warning_severity"], str
            )


def test_scheduled_artifact_drilldown_lane_identity_warning_grouping_normalization() -> None:
    if _IMPORT_ERROR is not None:
        pytest.skip(f"business line evidence contract tests require backend dependencies: {_IMPORT_ERROR}")

    missing_lane = _drilldown_scheduled_lane(
        {"lane": "missing_lane", "classification": "missing"},
        fallback_observed_at="2026-05-25T00:00:00Z",
        fallback_recommended_command="python3 scripts/check_scheduled_automation_artifacts.py --json",
    )
    assert missing_lane["scheduled_completion_proof"] is False
    assert missing_lane["identity_warning_count"] == 0
    assert missing_lane["identity_warning_types"] == []
    assert missing_lane["identity_status_counts"] == {}
    assert missing_lane["identity_warning_severity_counts"] == {}
    assert missing_lane["identity_warning_severity_order"] == []
    assert missing_lane["identity_warning_highest_severity"] is None
    assert missing_lane["identity_warning_highest_severity_rank"] is None

    malformed_grouping_lane = _drilldown_scheduled_lane(
        {
            "lane": "malformed_grouping_lane",
            "classification": "scheduled_run_blocked",
            "identity_warning_count": -1,
            "identity_warning_types": ["stale_identity", None, ""],
            "identity_status_counts": {
                "latest": 1,
                "stale": -1,
                "": 3,
                "boolean_count": True,
            },
            "identity_warning_severity_counts": {
                "critical": 2,
                "low": -1,
                "": 3,
                "boolean_count": True,
            },
            "identity_warning_severity_order": ["critical", None, "", "warning"],
            "identity_warning_highest_severity": "",
            "identity_warning_highest_severity_rank": True,
        },
        fallback_observed_at="2026-05-25T00:00:00Z",
        fallback_recommended_command="python3 scripts/check_scheduled_automation_artifacts.py --json",
    )
    assert malformed_grouping_lane["scheduled_completion_proof"] is False
    assert malformed_grouping_lane["identity_warning_count"] == 0
    assert malformed_grouping_lane["identity_warning_types"] == ["stale_identity"]
    assert malformed_grouping_lane["identity_status_counts"] == {"latest": 1}
    assert malformed_grouping_lane["identity_warning_severity_counts"] == {"critical": 2}
    assert malformed_grouping_lane["identity_warning_severity_order"] == [
        "critical",
        "warning",
    ]
    assert malformed_grouping_lane["identity_warning_highest_severity"] is None
    assert malformed_grouping_lane["identity_warning_highest_severity_rank"] is None

    malformed_rank_lane = _drilldown_scheduled_lane(
        {
            "lane": "malformed_rank_lane",
            "classification": "scheduled_run_blocked",
            "identity_warning_severity_order": "critical",
            "identity_warning_highest_severity": ["critical"],
            "identity_warning_highest_severity_rank": -1,
        },
        fallback_observed_at="2026-05-25T00:00:00Z",
        fallback_recommended_command="python3 scripts/check_scheduled_automation_artifacts.py --json",
    )
    assert malformed_rank_lane["identity_warning_severity_order"] == []
    assert malformed_rank_lane["identity_warning_highest_severity"] is None
    assert malformed_rank_lane["identity_warning_highest_severity_rank"] is None

    valid_rank_lane = _drilldown_scheduled_lane(
        {
            "lane": "valid_rank_lane",
            "classification": "scheduled_run_blocked",
            "identity_warning_highest_severity": "critical",
            "identity_warning_highest_severity_rank": 0,
        },
        fallback_observed_at="2026-05-25T00:00:00Z",
        fallback_recommended_command="python3 scripts/check_scheduled_automation_artifacts.py --json",
    )
    assert valid_rank_lane["identity_warning_highest_severity"] == "critical"
    assert valid_rank_lane["identity_warning_highest_severity_rank"] is None

    positive_rank_lane = _drilldown_scheduled_lane(
        {
            "lane": "positive_rank_lane",
            "classification": "scheduled_run_blocked",
            "identity_warning_highest_severity": "warning",
            "identity_warning_highest_severity_rank": 1,
        },
        fallback_observed_at="2026-05-25T00:00:00Z",
        fallback_recommended_command="python3 scripts/check_scheduled_automation_artifacts.py --json",
    )
    assert positive_rank_lane["identity_warning_highest_severity"] == "warning"
    assert positive_rank_lane["identity_warning_highest_severity_rank"] == 1


def test_scheduled_artifact_drilldown_same_as_latest_projection_is_no_warning() -> None:
    if _IMPORT_ERROR is not None:
        pytest.skip(f"business line evidence contract tests require backend dependencies: {_IMPORT_ERROR}")

    lane = _drilldown_scheduled_lane(
        {
            "lane": "same_as_latest_lane",
            "classification": "scheduled_run_blocked",
            "reason": "latest scheduler proof is not present for this lane",
            "artifact_path": "artifacts/scheduled/latest.json",
            "base_dir": "artifacts/scheduled",
            "identity_warning_count": 0,
            "identity_warning_types": [],
            "identity_status_counts": {
                "latest": 1,
                "same_as_latest": 1,
            },
            "identity_warning_severity_counts": {},
            "artifacts": [
                {
                    "artifact_path": "artifacts/scheduled/latest.json",
                    "absolute_path": "/tmp/must-not-leak/latest.json",
                    "classification": "manual_dry_run",
                    "reason": "latest manual artifact is not scheduler proof",
                    "mtime": "2026-05-25T00:00:00Z",
                    "observed_at": "2026-05-25T00:00:01Z",
                    "size_bytes": 128,
                    "sha256": "a" * 64,
                    "freshness_rank": 1,
                    "freshness_window_size": 2,
                    "is_latest_for_lane": True,
                    "identity_matches_latest": True,
                    "latest_artifact_path": "artifacts/scheduled/latest.json",
                    "identity_status": "latest",
                    "identity_warning": None,
                    "identity_warning_message": None,
                    "identity_warning_severity": None,
                },
                {
                    "artifact_path": "artifacts/scheduled/stale-same-as-latest.json",
                    "absolute_path": "/tmp/must-not-leak/stale-same-as-latest.json",
                    "classification": "scheduled_run_blocked",
                    "reason": "stale artifact matches latest identity but is not scheduler proof",
                    "mtime": "2026-05-24T00:00:00Z",
                    "observed_at": "2026-05-25T00:00:01Z",
                    "size_bytes": 128,
                    "sha256": "a" * 64,
                    "freshness_rank": 2,
                    "freshness_window_size": 2,
                    "is_latest_for_lane": False,
                    "identity_matches_latest": True,
                    "latest_artifact_path": "artifacts/scheduled/latest.json",
                    "identity_status": "same_as_latest",
                    "identity_warning": None,
                    "identity_warning_message": None,
                    "identity_warning_severity": None,
                },
            ],
        },
        fallback_observed_at="2026-05-25T00:00:00Z",
        fallback_recommended_command="python3 scripts/check_scheduled_automation_artifacts.py --json",
    )

    assert lane["scheduled_completion_proof"] is False
    assert lane["identity_warning_count"] == 0
    assert lane["identity_warning_types"] == []
    assert lane["identity_status_counts"] == {
        "latest": 1,
        "same_as_latest": 1,
    }
    assert lane["identity_warning_severity_counts"] == {}
    assert lane["identity_warning_severity_order"] == []
    assert lane["identity_warning_highest_severity"] is None
    assert lane["identity_warning_highest_severity_rank"] is None
    assert "absolute_path" not in lane

    latest_artifact, same_as_latest_artifact = lane["artifacts"]
    assert latest_artifact["identity_status"] == "latest"
    assert latest_artifact["identity_warning_severity"] is None
    assert latest_artifact["scheduled_completion_proof"] is False
    assert "absolute_path" not in latest_artifact

    assert same_as_latest_artifact["identity_status"] == "same_as_latest"
    assert same_as_latest_artifact["identity_warning"] is None
    assert same_as_latest_artifact["identity_warning_message"] is None
    assert same_as_latest_artifact["identity_warning_severity"] is None
    assert same_as_latest_artifact["scheduled_completion_proof"] is False
    assert "absolute_path" not in same_as_latest_artifact


def test_business_line_evidence_matrix_contract(client: TestClient) -> None:
    response = client.get("/api/v1/business-lines/evidence-matrix")
    assert response.status_code == 200
    body = response.json()
    assert {"status", "data", "error", "meta"}.issubset(body.keys())
    assert body["status"] == "ok"
    assert body["error"] is None

    data = body["data"]
    assert data["contract_version"] == "business_line.evidence_matrix.v2"
    assert data["vocabulary_version"] == "business_line.vocabulary.current.v1"
    assert "batch_orchestration" not in data
    assert "source_report" not in data
    assert "installed_codex_app" not in response.text
    assert '"status": "passed"' not in response.text

    guidance = data["matrix_diagnostics_guidance"]
    assert REQUIRED_MATRIX_DIAGNOSTICS_GUIDANCE_FIELDS.issubset(guidance.keys())
    assert guidance["source_lane"] == "business_line_worker_readback_project_matrix_nightly"
    assert guidance["source_artifact"] == "nightly-manifest.json:matrix_diagnostics"
    assert guidance["consumer_surface"] == "OpsPage:/api/v1/business-lines/evidence-matrix"
    assert guidance["recommended_display_order"] == MATRIX_DIAGNOSTICS_RECOMMENDED_DISPLAY_ORDER
    assert guidance["required_fields"] == MATRIX_DIAGNOSTICS_REQUIRED_FIELDS
    assert guidance["blocked_project_fields"] == MATRIX_DIAGNOSTICS_BLOCKED_PROJECT_FIELDS
    assert {
        "runtime_preflight_status",
        "matrix_exit_code",
        "project_keys",
        "summary_total",
        "first_blocked_reason",
        "reason_counts",
    }.issubset(guidance["required_fields"])
    assert {
        "project_key",
        "status",
        "reason",
        "stopped_at",
        "exit_code",
        "trigger_smoke_status",
    }.issubset(guidance["blocked_project_fields"])
    assert "not completion proof" in guidance["classification_boundary"]["scheduled_run_blocked"]
    assert "Only scheduled_run_evidence can close scheduled evidence" in (
        guidance["classification_boundary"]["scheduled_run_evidence"]
    )
    assert guidance["classification_boundary"]["completion_claim"] == "does_not_claim_real_scheduler_run"

    coverage = data["coverage"]
    assert coverage["covered_line_count"] == 7
    assert coverage["covered_line_keys"] == LINE_KEYS
    assert coverage["not_admin_only"] is True

    worker = data["worker_readback"]
    assert worker["contract_version"] == "business_line.worker_readback_contract.v2"
    assert worker["covered_line_keys"] == WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS
    assert worker["runner_script"] == ASYNC_TASK_READBACK_LIVE_SAMPLE_RUNNER_SCRIPT
    assert worker["manifest_cli"] == ASYNC_TASK_READBACK_WORKER_MANIFEST_CLI
    assert worker["manifest_checker_script"] == ASYNC_TASK_READBACK_WORKER_MANIFEST_CHECKER_SCRIPT
    assert worker["candidate_builder_script"] == (
        ASYNC_TASK_READBACK_WORKER_MANIFEST_CANDIDATE_BUILDER_SCRIPT
    )
    assert worker["evidence_chain_script"] == ASYNC_TASK_READBACK_WORKER_EVIDENCE_CHAIN_SCRIPT
    assert worker["artifact_checker_script"] == ASYNC_TASK_READBACK_ARTIFACT_CHECKER_SCRIPT
    assert set(worker["required_manifest_fields"]) == {
        "line_key",
        "task_id_or_run_id",
        "worker_name",
        "queue",
        "trace_id",
        "readback_endpoint_or_path",
        "terminal_events",
    }
    assert set(worker["required_live_readback_fields"]) == {
        "matching_task_id_or_run_id",
        "worker_name",
        "queue",
        "trace_id",
        "success_status",
        "terminal_event",
        "required_events",
    }
    assert worker["process_runtime_endpoints"] == [
        "/api/v1/process/tasks?line_key={line_key}&limit=...",
        "/api/v1/process/logs?line_key={line_key}&limit=...",
    ]
    assert "every selected project_key and every worker-required line" in worker["aggregation_contract"]
    assert "async_task_readback_missing" in worker["blocked_semantics"]
    assert "manifest_qualification_failed" in worker["blocked_semantics"]
    assert "blocked_by_environment" in worker["blocked_semantics"]
    assert "not passed" in worker["blocked_semantics"]
    assert worker["completion_claim"] == "not_observed_without_live_worker_readback"

    scheduled = data["scheduled_observation"]
    assert scheduled["observation_status"] == "not_observed"
    assert scheduled["scheduled_run_evidence"] == "not_observed"
    assert scheduled["install_status"] == "unknown"
    assert scheduled["evidence_endpoint"] == "/api/v1/business-lines/scheduled-matrix-artifact-summary"
    assert scheduled["summary_contract_version"] == SCHEDULED_MATRIX_ARTIFACT_SUMMARY_CONTRACT_VERSION
    assert "does not observe a scheduler run" in scheduled["reason"]
    assert scheduled["completion_claim"] == "not_observed"

    ui = data["ui_boundary"]["reset_telemetry"]
    assert ui["event_name"] == "reset_empty_warning_view"
    assert ui["event_scope"] == "ui_event_log_only"
    assert ui["filter_transition"] == {"from": "warning_only", "to": "all"}
    assert ui["sort_behavior"] == "unchanged"
    assert ui["api_payload_behavior"] == "unchanged"
    assert ui["scheduled_evidence_write"] == "none"
    assert ui["scheduled_completion_proof"] is False
    assert ui["scheduled_evidence_controller"] == "scheduled_run_evidence"
    assert "writes no scheduled evidence" in ui["telemetry_scope"]

    read_only_context = data["ui_boundary"]["read_only_context"]
    for key, value in READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS.items():
        assert read_only_context[key] == value
    assert read_only_context["scheduled_evidence_controller"] == "scheduled_run_evidence"
    assert read_only_context["observation_status"] == "not_applicable_ui_boundary"
    assert "not report proof" in read_only_context["boundary"]
    assert "not quality gate input" in read_only_context["boundary"]
    assert "scheduled_run_evidence proof" in read_only_context["boundary"]

    assert READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS == {
        "not_report_proof": True,
        "not_quality_gate_input": True,
        "not_scheduled_run_evidence_proof": True,
        "scheduled_evidence_write": "none",
        "scheduled_completion_proof_behavior": "unchanged",
        "audit_outcome_behavior": "unchanged",
    }
    assert _read_only_context_proof_boundary(extra_flag=True) == {
        **READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS,
        "extra_flag": True,
    }

    lines = data["lines"]
    assert len(lines) == 7
    assert {line["line_key"] for line in lines} == set(LINE_KEYS)
    assert [line["line_key"] for line in lines] == LINE_KEYS

    for line in lines:
        assert REQUIRED_LINE_FIELDS.issubset(line.keys())
        for field in REQUIRED_LINE_FIELDS - {"line_key", "user_task"}:
            assert line[field], f"{line['line_key']} missing non-empty {field}"

        live_smoke = line["live_smoke"]
        assert REQUIRED_LIVE_SMOKE_FIELDS.issubset(live_smoke.keys())
        for field in REQUIRED_LIVE_SMOKE_FIELDS:
            assert live_smoke[field], f"{line['line_key']} missing non-empty live_smoke.{field}"
        assert live_smoke["probe_path"].startswith("/api/v1/")
        assert all(isinstance(status, int) for status in live_smoke["expected_statuses"])
        assert live_smoke["proof_level"] == "live_backend_smoke_plan"
        assert "blocked_by_environment" in live_smoke["blocked_semantics"]
        assert "not passed" in live_smoke["blocked_semantics"]
        assert "curl" in live_smoke["recommended_command"]

        response_assertions = live_smoke["response_assertions"]
        assert REQUIRED_RESPONSE_ASSERTION_FIELDS.issubset(response_assertions.keys())
        expected_envelope_required = line["line_key"] != "runtime_ops"
        assert response_assertions["envelope_required"] is expected_envelope_required
        assert response_assertions["required_data_paths"]
        assert response_assertions["semantic_fields"]
        assert response_assertions["failure_classification"]
        assert all(isinstance(path, str) and path for path in response_assertions["required_data_paths"])
        assert all(isinstance(field, str) and field for field in response_assertions["semantic_fields"])

        trace_baseline = line["trace_baseline"]
        assert REQUIRED_TRACE_BASELINE_FIELDS.issubset(trace_baseline.keys())
        assert trace_baseline["contract_version"] == TRACE_BASELINE_CONTRACT_VERSION
        assert trace_baseline["proof_level"] == "live_backend_trace_baseline_contract"
        assert trace_baseline["runner_script"] == TRACE_BASELINE_RUNNER_SCRIPT
        assert trace_baseline["recommended_command"] == TRACE_BASELINE_RECOMMENDED_COMMAND
        assert trace_baseline["probe_path"] == live_smoke["probe_path"]
        assert trace_baseline["request_headers"]["x_trace_id"] == "required"
        assert trace_baseline["request_headers"]["x_request_id"] == "required"
        assert trace_baseline["response_headers"]["required"] == ["x-trace-id", "x-request-id"]
        assert trace_baseline["body_meta_trace"]["required"] is expected_envelope_required
        if expected_envelope_required:
            assert trace_baseline["body_meta_trace"]["exempt_probe_paths"] == []
        else:
            assert line["line_key"] == "runtime_ops"
            assert trace_baseline["body_meta_trace"]["exempt_probe_paths"] == (
                TRACE_BASELINE_BODY_TRACE_EXEMPT_PROBE_PATHS
            )
        assert trace_baseline["duration_evidence"]["required"] is True
        assert trace_baseline["duration_evidence"]["default_slow_threshold_ms"] == (
            TRACE_BASELINE_DEFAULT_SLOW_THRESHOLD_MS
        )
        assert trace_baseline["failure_classification"]["endpoint_unreachable"] == "blocked_by_environment"
        assert trace_baseline["failure_classification"]["slow_request"] == "trace_latency_observation"
        assert trace_baseline["completion_claim"] == "does_not_claim_production_or_scheduler_completion"

        browser = line["real_backend_browser_smoke"]
        assert REQUIRED_REAL_BACKEND_BROWSER_SMOKE_FIELDS.issubset(browser.keys())
        assert browser["proof_level"] == "real_backend_browser_smoke_plan"
        assert browser["test_file"] == REAL_BACKEND_BROWSER_SMOKE_TEST_FILE
        assert browser["route_path"].startswith("/#/")
        assert "requireRealBackendReadiness" in browser["readiness_gate"]
        assert "blocked_by_environment" in browser["blocked_semantics"]
        assert "Mocked rails are not real proof" in browser["blocked_semantics"]
        assert "does not claim production, Docker, Celery, or scheduler completion" in browser["blocked_semantics"]

        readiness = line["async_execution_readiness"]
        assert REQUIRED_ASYNC_EXECUTION_READINESS_FIELDS.issubset(readiness.keys())
        assert readiness["proof_level"] == "async_worker_readiness_plan"
        assert readiness["process_stats_probe"] == PROCESS_STATS_PROBE_PATH
        assert isinstance(readiness["requires_worker"], bool)
        assert readiness["requires_worker"] is ASYNC_TASK_READBACK_REQUIRES_WORKER[line["line_key"]]
        assert "celery_worker_unavailable" in readiness["blocked_semantics"]
        assert "does not prove worker/async passed" in readiness["blocked_semantics"]
        assert readiness["verification_artifact"].startswith("business_line_async_worker_readiness.")

        readback = line["async_task_readback"]
        assert REQUIRED_ASYNC_TASK_READBACK_FIELDS.issubset(readback.keys())
        assert readback["proof_level"] == "async_task_readback_contract"
        assert readback["requires_worker_readback"] is ASYNC_TASK_READBACK_REQUIRES_WORKER[line["line_key"]]
        assert readback["readback_artifact"].startswith("business_line_async_task_readback.")
        assert all(isinstance(path, str) and path for path in readback["readback_paths"])
        assert all(isinstance(event, str) and event for event in readback["required_events"])
        assert all(isinstance(state, str) and state for state in readback["terminal_states"])
        assert "blocked_by_environment" in readback["blocked_semantics"]
        assert "not passed" in readback["blocked_semantics"]
        if readback["requires_worker_readback"]:
            assert "worker" in readback["blocked_semantics"].lower()
            assert "async_task_readback_missing" in readback["blocked_semantics"]
            assert "worker_started" in readback["required_events"]
        else:
            assert "process_config_audit_readback_missing" in readback["blocked_semantics"]
            assert any(keyword in " ".join(readback["readback_paths"]) for keyword in ["process", "config", "audit"])
