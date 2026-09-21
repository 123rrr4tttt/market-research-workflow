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
    assert data["contract_version"] == CONTRACT_VERSION
    matrix_diagnostics_guidance = data["matrix_diagnostics_guidance"]
    assert REQUIRED_MATRIX_DIAGNOSTICS_GUIDANCE_FIELDS.issubset(matrix_diagnostics_guidance.keys())
    assert matrix_diagnostics_guidance["source_lane"] == (
        "business_line_worker_readback_project_matrix_nightly"
    )
    assert matrix_diagnostics_guidance["source_artifact"] == "nightly-manifest.json:matrix_diagnostics"
    assert matrix_diagnostics_guidance["consumer_surface"] == (
        "OpsPage:/api/v1/business-lines/evidence-matrix"
    )
    assert matrix_diagnostics_guidance["recommended_display_order"] == (
        MATRIX_DIAGNOSTICS_RECOMMENDED_DISPLAY_ORDER
    )
    assert matrix_diagnostics_guidance["required_fields"] == MATRIX_DIAGNOSTICS_REQUIRED_FIELDS
    assert matrix_diagnostics_guidance["blocked_project_fields"] == (
        MATRIX_DIAGNOSTICS_BLOCKED_PROJECT_FIELDS
    )
    assert {
        "runtime_preflight_status",
        "matrix_exit_code",
        "project_keys",
        "summary_total",
        "first_blocked_reason",
        "reason_counts",
    }.issubset(matrix_diagnostics_guidance["required_fields"])
    assert {
        "project_key",
        "status",
        "reason",
        "stopped_at",
        "exit_code",
        "trigger_smoke_status",
    }.issubset(matrix_diagnostics_guidance["blocked_project_fields"])
    classification_boundary = matrix_diagnostics_guidance["classification_boundary"]
    assert "not completion proof" in classification_boundary["scheduled_run_blocked"]
    assert "Only scheduled_run_evidence can close scheduled evidence" in (
        classification_boundary["scheduled_run_evidence"]
    )
    assert classification_boundary["completion_claim"] == "does_not_claim_real_scheduler_run"

    batch_orchestration = data["batch_orchestration"]
    assert batch_orchestration["covered_line_count"] == 7
    assert batch_orchestration["covered_line_keys"] == LINE_KEYS
    assert batch_orchestration["not_admin_only"] is True
    assert "覆盖所有条线" in batch_orchestration["statement"]
    assert "不把下一批作为本批漏项修补" in batch_orchestration["statement"]
    same_batch_live_smoke = batch_orchestration["same_batch_live_smoke"]
    assert same_batch_live_smoke["batch"] == "67"
    assert same_batch_live_smoke["proof_level"] == "live_backend_smoke_plan"
    assert "live user-flow smoke" in same_batch_live_smoke["statement"]
    assert "不宣称生产证明" in same_batch_live_smoke["statement"]
    assert "第68批" in same_batch_live_smoke["statement"]
    assert "响应语义可校验" in same_batch_live_smoke["statement"]
    assert "blocked_by_environment" in same_batch_live_smoke["blocked_semantics"]
    response_assertion_extension = same_batch_live_smoke["response_assertion_extension"]
    assert response_assertion_extension["batch"] == "68"
    assert response_assertion_extension["proof_level"] == "live_backend_response_semantics_plan"
    real_backend_extension = same_batch_live_smoke["real_backend_browser_smoke_extension"]
    assert real_backend_extension["batch"] == "69"
    assert real_backend_extension["proof_level"] == "real_backend_browser_smoke_plan"
    assert real_backend_extension["test_file"] == REAL_BACKEND_BROWSER_SMOKE_TEST_FILE
    assert "7条 canonical line_key" in real_backend_extension["statement"]
    assert "不替代第66-68批字段" in real_backend_extension["statement"]
    assert "不把 mocked rail 当 real proof" in real_backend_extension["statement"]
    assert "不宣称生产、Docker、Celery 或 scheduler 完成" in real_backend_extension["statement"]
    async_readiness_extension = batch_orchestration["async_execution_readiness_extension"]
    assert async_readiness_extension["batch"] == "70"
    assert async_readiness_extension["proof_level"] == "async_worker_readiness_plan"
    assert async_readiness_extension["process_stats_probe"] == PROCESS_STATS_PROBE_PATH
    assert "7条 canonical line_key" in async_readiness_extension["statement"]
    assert "后端 live smoke 或真实后端浏览器 passed 不等于" in async_readiness_extension["statement"]
    assert "Celery worker" in async_readiness_extension["statement"]
    assert "scheduler" in async_readiness_extension["statement"]
    assert "Docker" in async_readiness_extension["statement"]
    assert "production" in async_readiness_extension["statement"]
    assert "celery_worker_unavailable" in async_readiness_extension["blocked_semantics"]
    async_task_readback_extension = batch_orchestration["async_task_readback_extension"]
    assert async_task_readback_extension["batch"] == "71"
    assert async_task_readback_extension["proof_level"] == "async_task_readback_contract"
    assert "7条 canonical line_key" in async_task_readback_extension["statement"]
    assert "gate/contract" in async_task_readback_extension["statement"]
    assert "不宣称真实任务消费" in async_task_readback_extension["statement"]
    assert "worker 执行" in async_task_readback_extension["statement"]
    assert "worker visibility alone is not proof" in async_task_readback_extension["blocked_semantics"]
    assert "async_task_readback_missing" in async_task_readback_extension["blocked_semantics"]
    assert "not passed" in async_task_readback_extension["blocked_semantics"]
    live_sample_runner_extension = async_task_readback_extension["live_sample_runner_extension"]
    assert live_sample_runner_extension["batch"] == "72"
    assert live_sample_runner_extension["proof_level"] == "async_task_readback_live_sample_runner_metadata"
    assert live_sample_runner_extension["script"] == ASYNC_TASK_READBACK_LIVE_SAMPLE_RUNNER_SCRIPT
    assert live_sample_runner_extension["live_backend_only"] is True
    assert "live backend" in live_sample_runner_extension["statement"]
    assert "process/config/audit/diagnostic readback samples" in live_sample_runner_extension["statement"]
    assert "缺少真实 task/run id 时必须保持 blocked" in live_sample_runner_extension["statement"]
    assert "不能伪造真实 task 消费" in live_sample_runner_extension["statement"]
    assert "不能关闭 live evidence" in live_sample_runner_extension["statement"]
    assert "不能伪造真实 task 消费或宣称真实 task completion" in live_sample_runner_extension["statement"]
    assert live_sample_runner_extension["non_worker_sample_scope"] == [
        "process readback",
        "config readback",
        "audit readback",
        "diagnostic readback",
    ]
    assert "must remain blocked" in live_sample_runner_extension["worker_required_blocked_semantics"]
    assert "real task/run id" in live_sample_runner_extension["worker_required_blocked_semantics"]
    assert "synthetic samples cannot close live evidence" in live_sample_runner_extension[
        "worker_required_blocked_semantics"
    ]
    assert "prove real task consumption" in live_sample_runner_extension["worker_required_blocked_semantics"]
    assert live_sample_runner_extension["completion_claim"] == "does_not_claim_real_task_completion"
    worker_manifest_extension = async_task_readback_extension["worker_task_readback_manifest_extension"]
    assert worker_manifest_extension["batch"] == "73"
    assert worker_manifest_extension["proof_level"] == "worker_required_task_readback_manifest_metadata"
    assert worker_manifest_extension["script"] == ASYNC_TASK_READBACK_LIVE_SAMPLE_RUNNER_SCRIPT
    assert worker_manifest_extension["manifest_cli"] == ASYNC_TASK_READBACK_WORKER_MANIFEST_CLI
    assert worker_manifest_extension["covered_line_keys"] == WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS
    assert set(worker_manifest_extension["covered_line_keys"]) == {
        "ingest",
        "search_discovery_index",
        "resource_source_library",
        "writing_knowledge_graph_agent",
    }
    assert len(worker_manifest_extension["covered_line_keys"]) == 4
    assert "四条 worker-required line" in worker_manifest_extension["statement"]
    assert "manifest/probe CLI 对齐" in worker_manifest_extension["statement"]
    assert "只允许接收真实 worker manifest" in worker_manifest_extension["statement"]
    assert "不宣称真实 task completion" in worker_manifest_extension["statement"]
    assert "不宣称真实 task completion 或 worker 闭环已经完成" in worker_manifest_extension["statement"]
    assert worker_manifest_extension["requires_real_task_identifiers"] == ["task_id_or_run_id"]
    assert worker_manifest_extension["requires_worker_probe_fields"] == ["worker_name", "queue"]
    assert worker_manifest_extension["requires_trace_readback_fields"] == ["trace_id", "readback_endpoint"]
    assert set(worker_manifest_extension["required_manifest_fields"]) == {
        "line_key",
        "task_id",
        "run_id",
        "worker_name",
        "queue",
        "trace_id",
        "readback_endpoint",
    }
    assert "synthetic samples" in worker_manifest_extension["synthetic_samples_semantics"]
    assert "cannot close worker-required async task readback evidence" in worker_manifest_extension[
        "synthetic_samples_semantics"
    ]
    assert "process visibility alone cannot close" in worker_manifest_extension["synthetic_samples_semantics"]
    assert "Missing real task_id/run_id" in worker_manifest_extension["blocked_semantics"]
    assert "worker_name" in worker_manifest_extension["blocked_semantics"]
    assert "queue" in worker_manifest_extension["blocked_semantics"]
    assert "trace_id" in worker_manifest_extension["blocked_semantics"]
    assert "readback endpoint" in worker_manifest_extension["blocked_semantics"]
    assert "async_task_readback_missing" in worker_manifest_extension["blocked_semantics"]
    assert "blocked_by_environment" in worker_manifest_extension["blocked_semantics"]
    assert "not passed" in worker_manifest_extension["blocked_semantics"]
    assert worker_manifest_extension["completion_claim"] == "does_not_close_real_task_completion"
    worker_manifest_qualification_extension = async_task_readback_extension[
        "worker_task_readback_manifest_qualification_extension"
    ]
    assert worker_manifest_qualification_extension["batch"] == "74"
    assert (
        worker_manifest_qualification_extension["proof_level"]
        == "worker_required_task_readback_manifest_qualification_metadata"
    )
    assert worker_manifest_qualification_extension["checker"] == (
        ASYNC_TASK_READBACK_WORKER_MANIFEST_CHECKER_SCRIPT
    )
    assert worker_manifest_qualification_extension["checker"] == (
        "scripts/check_business_line_task_readback_manifest.py"
    )
    assert worker_manifest_qualification_extension["covered_line_keys"] == (
        WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS
    )
    assert set(worker_manifest_qualification_extension["covered_line_keys"]) == {
        "ingest",
        "search_discovery_index",
        "resource_source_library",
        "writing_knowledge_graph_agent",
    }
    assert worker_manifest_qualification_extension["worker_required_line_count"] == 4
    assert len(worker_manifest_qualification_extension["covered_line_keys"]) == 4
    assert "四条 worker-required line" in worker_manifest_qualification_extension["statement"]
    assert "qualification/checker gate" in worker_manifest_qualification_extension["statement"]
    assert "checker 已作为独立脚本落地" in worker_manifest_qualification_extension["statement"]
    assert "拒绝非真实 manifest" in worker_manifest_qualification_extension["statement"]
    assert "synthetic/fixture/generated/mock ids 必须判定为 failed" in (
        worker_manifest_qualification_extension["statement"]
    )
    assert "避免合成 manifest fixture 被误认为真实任务闭环" in (
        worker_manifest_qualification_extension["statement"]
    )
    assert worker_manifest_qualification_extension["must_fail_identifier_qualifiers"] == [
        "synthetic",
        "fixture",
        "generated",
        "mock",
    ]
    assert worker_manifest_qualification_extension["requires_real_task_identifiers"] == [
        "task_id_or_run_id"
    ]
    assert worker_manifest_qualification_extension["requires_worker_probe_fields"] == [
        "worker_name",
        "queue",
    ]
    assert worker_manifest_qualification_extension["requires_trace_readback_fields"] == [
        "trace_id",
        "readback_endpoint_or_path",
    ]
    assert worker_manifest_qualification_extension["requires_terminal_events"] is True
    assert set(worker_manifest_qualification_extension["required_manifest_fields"]) == {
        "line_key",
        "task_id_or_run_id",
        "worker_name",
        "queue",
        "trace_id",
        "readback_endpoint_or_path",
        "terminal_events",
    }
    qualification_semantics = worker_manifest_qualification_extension["qualification_semantics"]
    assert "real task_id_or_run_id" in qualification_semantics
    assert "worker_name" in qualification_semantics
    assert "queue" in qualification_semantics
    assert "trace_id" in qualification_semantics
    assert "readback endpoint/path" in qualification_semantics
    assert "terminal events" in qualification_semantics
    failure_semantics = worker_manifest_qualification_extension["failure_semantics"]
    assert "synthetic" in failure_semantics
    assert "fixture" in failure_semantics
    assert "generated" in failure_semantics
    assert "mock" in failure_semantics
    assert "must fail the checker" in failure_semantics
    assert "real task_id_or_run_id" in failure_semantics
    assert "worker_name" in failure_semantics
    assert "queue" in failure_semantics
    assert "trace_id" in failure_semantics
    assert "readback endpoint/path" in failure_semantics
    assert "terminal events" in failure_semantics
    assert "async_task_readback_missing" in failure_semantics
    assert "manifest_qualification_failed" in failure_semantics
    assert "not passed" in failure_semantics
    assert worker_manifest_qualification_extension["completion_claim"] == "does_not_close_real_task_completion"
    worker_manifest_candidate_builder_extension = async_task_readback_extension[
        "worker_task_readback_manifest_candidate_builder_extension"
    ]
    assert worker_manifest_candidate_builder_extension["batch"] == "75"
    assert (
        worker_manifest_candidate_builder_extension["proof_level"]
        == "worker_required_task_readback_manifest_candidate_builder_metadata"
    )
    assert (
        worker_manifest_candidate_builder_extension["script"]
        == ASYNC_TASK_READBACK_WORKER_MANIFEST_CANDIDATE_BUILDER_SCRIPT
    )
    assert worker_manifest_candidate_builder_extension["script"] == (
        "scripts/build_business_line_task_readback_manifest_from_runtime.py"
    )
    assert worker_manifest_candidate_builder_extension["covered_line_keys"] == (
        WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS
    )
    assert set(worker_manifest_candidate_builder_extension["covered_line_keys"]) == {
        "ingest",
        "search_discovery_index",
        "resource_source_library",
        "writing_knowledge_graph_agent",
    }
    assert worker_manifest_candidate_builder_extension["worker_required_line_count"] == 4
    assert len(worker_manifest_candidate_builder_extension["covered_line_keys"]) == 4
    assert (
        worker_manifest_candidate_builder_extension["candidate_schema_name"]
        == "business_line_task_readback_manifest_candidate.v1"
    )
    assert worker_manifest_candidate_builder_extension["candidate_discovery_sources"] == [
        "live_runtime_state",
        "evidence_matrix",
        "async_task_readback_paths",
    ]
    assert "四条 worker-required line" in worker_manifest_candidate_builder_extension["statement"]
    assert "candidate builder 只能从 live runtime" in worker_manifest_candidate_builder_extension[
        "statement"
    ]
    assert "evidence matrix" in worker_manifest_candidate_builder_extension["statement"]
    assert "readback paths" in worker_manifest_candidate_builder_extension["statement"]
    assert "不能伪造 task/run id" in worker_manifest_candidate_builder_extension["statement"]
    assert "不能把 blocked 缺口计为 passed" in worker_manifest_candidate_builder_extension[
        "statement"
    ]
    assert "先经第74批 checker qualification" in worker_manifest_candidate_builder_extension[
        "statement"
    ]
    assert "第73批 runner/manifest probe" in worker_manifest_candidate_builder_extension[
        "statement"
    ]
    assert "第71批 async_task_readback builder/checker" in worker_manifest_candidate_builder_extension[
        "statement"
    ]
    assert "不宣称真实 task completion" in worker_manifest_candidate_builder_extension["statement"]
    assert set(worker_manifest_candidate_builder_extension["required_candidate_fields"]) == {
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
    }
    candidate_source_semantics = worker_manifest_candidate_builder_extension[
        "candidate_source_semantics"
    ]
    assert "live runtime state" in candidate_source_semantics
    assert "evidence matrix metadata" in candidate_source_semantics
    assert "async_task_readback readback paths" in candidate_source_semantics
    assert "must not synthesize" in candidate_source_semantics
    assert "invent task_id/run_id values" in candidate_source_semantics
    candidate_builder_blocked_semantics = worker_manifest_candidate_builder_extension[
        "blocked_semantics"
    ]
    assert "Missing live runtime evidence" in candidate_builder_blocked_semantics
    assert "real task_id_or_run_id" in candidate_builder_blocked_semantics
    assert "worker/readback fields" in candidate_builder_blocked_semantics
    assert "qualification failure" in candidate_builder_blocked_semantics
    assert "blocked readback gaps" in candidate_builder_blocked_semantics
    assert "async_task_readback_missing" in candidate_builder_blocked_semantics
    assert "manifest_candidate_builder_blocked" in candidate_builder_blocked_semantics
    assert "manifest_qualification_failed" in candidate_builder_blocked_semantics
    assert "not passed" in candidate_builder_blocked_semantics
    assert worker_manifest_candidate_builder_extension["recommended_chain"] == [
        "batch_75_build_candidates_from_live_runtime_evidence_matrix_and_readback_paths",
        "batch_74_check_business_line_task_readback_manifest_qualification",
        "batch_73_run_business_line_async_task_readback_live_samples_with_manifest_probe",
        "batch_71_async_task_readback_builder_checker_contract",
    ]
    assert (
        worker_manifest_candidate_builder_extension["completion_claim"]
        == "does_not_claim_real_task_completion"
    )
    worker_evidence_chain_extension = async_task_readback_extension[
        "worker_task_readback_evidence_chain_extension"
    ]
    assert worker_evidence_chain_extension["batch"] == "76"
    assert (
        worker_evidence_chain_extension["proof_level"]
        == "worker_required_task_readback_evidence_chain_metadata"
    )
    assert (
        worker_evidence_chain_extension["script"]
        == ASYNC_TASK_READBACK_WORKER_EVIDENCE_CHAIN_SCRIPT
    )
    assert worker_evidence_chain_extension["script"] == (
        "scripts/run_business_line_worker_readback_evidence_chain.py"
    )
    assert worker_evidence_chain_extension["covered_line_keys"] == (
        WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS
    )
    assert set(worker_evidence_chain_extension["covered_line_keys"]) == {
        "ingest",
        "search_discovery_index",
        "resource_source_library",
        "writing_knowledge_graph_agent",
    }
    assert worker_evidence_chain_extension["worker_required_line_count"] == 4
    assert len(worker_evidence_chain_extension["covered_line_keys"]) == 4
    assert worker_evidence_chain_extension["chain_order"] == [
        "batch75_candidate_builder",
        "batch74_manifest_checker",
        "batch73_live_sample_runner",
        "batch71_async_task_readback_builder",
        "batch71_async_task_readback_checker",
    ]
    assert "chain enforces batch75->74->73->71 order" in worker_evidence_chain_extension[
        "statement"
    ]
    assert "四条 worker-required line" in worker_evidence_chain_extension["statement"]
    assert "不启动服务" in worker_evidence_chain_extension["statement"]
    assert "不伪造 task/run id" in worker_evidence_chain_extension["statement"]
    assert "blocked chain 当 completion" in worker_evidence_chain_extension["statement"]
    stop_semantics = worker_evidence_chain_extension["stop_semantics"]
    assert "batch74_manifest_checker" in stop_semantics
    assert "not passed" in stop_semantics
    assert "must be stopped" in stop_semantics
    assert "must not run batch73" in stop_semantics
    assert "batch71 builder/checker" in stop_semantics
    allow_blocked_semantics = worker_evidence_chain_extension["allow_blocked_semantics"]
    assert "Blocked chain output is allowed" in allow_blocked_semantics
    assert "blocked_by_environment" in allow_blocked_semantics
    assert "async_task_readback_missing" in allow_blocked_semantics
    assert "manifest_candidate_builder_blocked" in allow_blocked_semantics
    assert "manifest_qualification_failed" in allow_blocked_semantics
    assert "is not completion" in allow_blocked_semantics
    assert "must not be counted as passed" in allow_blocked_semantics
    runtime_semantics = worker_evidence_chain_extension["runtime_semantics"]
    assert "must not start backend" in runtime_semantics
    assert "Celery" in runtime_semantics
    assert "scheduler" in runtime_semantics
    assert "Docker" in runtime_semantics
    assert "must not forge task_id/run_id values" in runtime_semantics
    assert (
        worker_evidence_chain_extension["completion_claim"]
        == "does_not_claim_worker_readback_completion"
    )
    worker_strict_semantics_extension = async_task_readback_extension[
        "worker_task_readback_strict_semantics_extension"
    ]
    assert worker_strict_semantics_extension["batch"] == "77"
    assert (
        worker_strict_semantics_extension["proof_level"]
        == "worker_required_task_readback_strict_semantics_metadata"
    )
    assert worker_strict_semantics_extension["covered_line_keys"] == (
        WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS
    )
    assert set(worker_strict_semantics_extension["covered_line_keys"]) == {
        "ingest",
        "search_discovery_index",
        "resource_source_library",
        "writing_knowledge_graph_agent",
    }
    assert worker_strict_semantics_extension["worker_required_line_count"] == 4
    assert len(worker_strict_semantics_extension["covered_line_keys"]) == 4
    assert "strict worker readback semantics" in worker_strict_semantics_extension["statement"]
    assert "readback 2xx alone is not proof" in worker_strict_semantics_extension["statement"]
    assert "readback response itself" in worker_strict_semantics_extension["statement"]
    assert "第73 runner 不能从 manifest 或 contract 默认补 status/events/trace" in (
        worker_strict_semantics_extension["statement"]
    )
    assert worker_strict_semantics_extension["required_live_readback_fields"] == [
        "matching_task_id_or_run_id",
        "worker_name",
        "queue",
        "trace_id",
        "success_status",
        "terminal_event",
        "required_events",
    ]
    assert worker_strict_semantics_extension["disallowed_fallbacks"] == [
        "readback_2xx_only",
        "request_id_as_trace_id",
        "correlation_id_as_trace_id",
        "manifest_default_status",
        "manifest_default_events",
        "manifest_default_trace",
        "contract_default_status",
        "contract_default_events",
        "contract_default_trace",
    ]
    strict_failure_semantics = worker_strict_semantics_extension["failure_semantics"]
    assert "Missing or mismatched task_id_or_run_id" in strict_failure_semantics
    assert "worker_name" in strict_failure_semantics
    assert "queue" in strict_failure_semantics
    assert "trace_id" in strict_failure_semantics
    assert "success status" in strict_failure_semantics
    assert "terminal event" in strict_failure_semantics
    assert "required_events" in strict_failure_semantics
    assert "readback response itself" in strict_failure_semantics
    assert "must be failed, not passed" in strict_failure_semantics
    assert "request_id/correlation_id aliases" in strict_failure_semantics
    assert "manifest or contract defaults" in strict_failure_semantics
    assert "cannot close worker-required proof" in strict_failure_semantics
    assert (
        worker_strict_semantics_extension["completion_claim"]
        == "requires_strict_worker_readback_response_match"
    )
    worker_artifact_checker_strict_extension = async_task_readback_extension[
        "worker_task_readback_artifact_checker_strict_extension"
    ]
    assert worker_artifact_checker_strict_extension["batch"] == "78"
    assert (
        worker_artifact_checker_strict_extension["proof_level"]
        == "worker_required_task_readback_artifact_checker_strict_contract_metadata"
    )
    assert worker_artifact_checker_strict_extension["checker"] == (
        ASYNC_TASK_READBACK_ARTIFACT_CHECKER_SCRIPT
    )
    assert worker_artifact_checker_strict_extension["checker"] == (
        "scripts/check_business_line_async_task_readback_artifact.py"
    )
    assert worker_artifact_checker_strict_extension["covered_line_keys"] == (
        WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS
    )
    assert set(worker_artifact_checker_strict_extension["covered_line_keys"]) == {
        "ingest",
        "search_discovery_index",
        "resource_source_library",
        "writing_knowledge_graph_agent",
    }
    assert worker_artifact_checker_strict_extension["worker_required_line_count"] == 4
    assert len(worker_artifact_checker_strict_extension["covered_line_keys"]) == 4
    artifact_checker_statement = worker_artifact_checker_strict_extension["statement"]
    assert "downstream artifact checker strict contract" in artifact_checker_statement
    assert "scripts/check_business_line_async_task_readback_artifact.py" in artifact_checker_statement
    assert "worker-required artifact" in artifact_checker_statement
    assert "identity" in artifact_checker_statement
    assert "worker" in artifact_checker_statement
    assert "queue" in artifact_checker_statement
    assert "trace" in artifact_checker_statement
    assert "readback_location" in artifact_checker_statement
    assert "required_events" in artifact_checker_statement
    assert "canonical worker-required line set" in artifact_checker_statement
    assert "requires_worker_readback=false" in artifact_checker_statement
    assert "空 required_events" in artifact_checker_statement
    assert "只声明 checker gate" in artifact_checker_statement
    assert "防止替换 artifact 或绕过 runner" in artifact_checker_statement
    assert "不宣称真实 worker completion" in artifact_checker_statement
    assert worker_artifact_checker_strict_extension["required_checker_fields"] == [
        "canonical_worker_required_line_key",
        "matching_task_id_or_run_id",
        "worker_name",
        "queue",
        "trace_id",
        "readback_location",
        "non_empty_required_events",
        "canonical_worker_success_terminal_status",
    ]
    assert worker_artifact_checker_strict_extension["bypass_protection"] == [
        "replaced_artifact",
        "runner_bypass",
        "requires_worker_readback_false_artifact",
        "empty_required_events_artifact",
        "weakened_success_terminal_states_artifact",
        "manifest_only_artifact",
        "contract_default_artifact",
    ]
    artifact_checker_failure_semantics = worker_artifact_checker_strict_extension[
        "failure_semantics"
    ]
    assert "Missing or mismatched canonical worker-required line" in artifact_checker_failure_semantics
    assert "identity" in artifact_checker_failure_semantics
    assert "worker_name" in artifact_checker_failure_semantics
    assert "queue" in artifact_checker_failure_semantics
    assert "trace_id" in artifact_checker_failure_semantics
    assert "readback_location" in artifact_checker_failure_semantics
    assert "non-empty required_events" in artifact_checker_failure_semantics
    assert "canonical worker success terminal status" in artifact_checker_failure_semantics
    assert "must fail the checker, not passed" in artifact_checker_failure_semantics
    assert "replaced artifacts" in artifact_checker_failure_semantics
    assert "runner bypass" in artifact_checker_failure_semantics
    assert "requires_worker_readback=false artifacts" in artifact_checker_failure_semantics
    assert "empty required_events artifacts" in artifact_checker_failure_semantics
    assert "weakened success terminal states" in artifact_checker_failure_semantics
    assert "manifest-only artifacts" in artifact_checker_failure_semantics
    assert "contract-default artifacts" in artifact_checker_failure_semantics
    assert "cannot close worker-required proof" in artifact_checker_failure_semantics
    assert (
        worker_artifact_checker_strict_extension["completion_claim"]
        == "checker_gate_only_does_not_claim_real_worker_completion"
    )
    worker_manifest_linked_artifact_checker_extension = async_task_readback_extension[
        "worker_task_readback_manifest_linked_artifact_checker_extension"
    ]
    assert worker_manifest_linked_artifact_checker_extension["batch"] == "79"
    assert (
        worker_manifest_linked_artifact_checker_extension["proof_level"]
        == "worker_required_manifest_linked_artifact_checker_contract_metadata"
    )
    assert worker_manifest_linked_artifact_checker_extension["checker"] == (
        ASYNC_TASK_READBACK_ARTIFACT_CHECKER_SCRIPT
    )
    assert worker_manifest_linked_artifact_checker_extension["checker"] == (
        "scripts/check_business_line_async_task_readback_artifact.py"
    )
    assert worker_manifest_linked_artifact_checker_extension["checker_cli"] == (
        ASYNC_TASK_READBACK_WORKER_MANIFEST_CLI
    )
    assert worker_manifest_linked_artifact_checker_extension["checker_cli"] == (
        "--task-readback-manifest"
    )
    assert worker_manifest_linked_artifact_checker_extension["chain"] == (
        ASYNC_TASK_READBACK_WORKER_EVIDENCE_CHAIN_SCRIPT
    )
    assert worker_manifest_linked_artifact_checker_extension["chain"] == (
        "scripts/run_business_line_worker_readback_evidence_chain.py"
    )
    assert (
        worker_manifest_linked_artifact_checker_extension["manifest_source_step"]
        == "batch75_candidate_builder"
    )
    assert (
        worker_manifest_linked_artifact_checker_extension["checker_step"]
        == "batch71_async_task_readback_checker"
    )
    assert worker_manifest_linked_artifact_checker_extension["covered_line_keys"] == (
        WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS
    )
    assert set(worker_manifest_linked_artifact_checker_extension["covered_line_keys"]) == {
        "ingest",
        "search_discovery_index",
        "resource_source_library",
        "writing_knowledge_graph_agent",
    }
    assert worker_manifest_linked_artifact_checker_extension["worker_required_line_count"] == 4
    manifest_linked_statement = worker_manifest_linked_artifact_checker_extension["statement"]
    assert "manifest-linked artifact consistency gate" in manifest_linked_statement
    assert "scripts/check_business_line_async_task_readback_artifact.py" in manifest_linked_statement
    assert "--task-readback-manifest" in manifest_linked_statement
    assert "第75批 candidate manifest" in manifest_linked_statement
    assert "第71批 async_task_readback artifact" in manifest_linked_statement
    assert "scripts/run_business_line_worker_readback_evidence_chain.py" in manifest_linked_statement
    assert "batch75_candidate_builder" in manifest_linked_statement
    assert "batch71_async_task_readback_checker" in manifest_linked_statement
    assert "candidate manifest 传给" in manifest_linked_statement
    assert "artifact 与 manifest 脱钩" in manifest_linked_statement
    assert worker_manifest_linked_artifact_checker_extension["required_consistency_fields"] == [
        "line_key",
        "task_id_or_run_id",
        "worker_name",
        "queue",
        "trace_id",
        "readback_location",
        "status",
        "events",
    ]
    assert worker_manifest_linked_artifact_checker_extension["manifest_link_contract"] == {
        "source": "batch75_candidate_manifest",
        "consumer": "batch71_async_task_readback_checker",
        "cli": ASYNC_TASK_READBACK_WORKER_MANIFEST_CLI,
    }
    manifest_linked_failure_semantics = worker_manifest_linked_artifact_checker_extension[
        "failure_semantics"
    ]
    assert "Artifact/manifest mismatch" in manifest_linked_failure_semantics
    assert "line_key" in manifest_linked_failure_semantics
    assert "task_id_or_run_id" in manifest_linked_failure_semantics
    assert "worker_name" in manifest_linked_failure_semantics
    assert "queue" in manifest_linked_failure_semantics
    assert "trace_id" in manifest_linked_failure_semantics
    assert "readback_location" in manifest_linked_failure_semantics
    assert "status" in manifest_linked_failure_semantics
    assert "events" in manifest_linked_failure_semantics
    assert "must fail the checker, not passed" in manifest_linked_failure_semantics
    assert "--task-readback-manifest" in manifest_linked_failure_semantics
    assert "batch75 candidate manifest into the batch71 checker" in manifest_linked_failure_semantics
    assert "cannot close worker-required proof" in manifest_linked_failure_semantics
    assert (
        worker_manifest_linked_artifact_checker_extension["completion_claim"]
        == "manifest_linked_checker_gate_only_does_not_claim_real_worker_completion"
    )
    worker_process_runtime_projection_extension = async_task_readback_extension[
        "worker_task_readback_process_runtime_projection_extension"
    ]
    assert worker_process_runtime_projection_extension["batch"] == "80"
    assert (
        worker_process_runtime_projection_extension["proof_level"]
        == "worker_required_process_runtime_readback_projection_contract_metadata"
    )
    assert worker_process_runtime_projection_extension["covered_line_keys"] == (
        WORKER_REQUIRED_ASYNC_TASK_READBACK_LINE_KEYS
    )
    assert set(worker_process_runtime_projection_extension["covered_line_keys"]) == {
        "ingest",
        "search_discovery_index",
        "resource_source_library",
        "writing_knowledge_graph_agent",
    }
    assert worker_process_runtime_projection_extension["worker_required_line_count"] == 4
    assert worker_process_runtime_projection_extension["process_runtime_endpoints"] == [
        "/api/v1/process/tasks?line_key={line_key}&limit=...",
        "/api/v1/process/logs?line_key={line_key}&limit=...",
    ]
    assert worker_process_runtime_projection_extension["required_projection_fields"] == [
        "line_key",
        "task_id_or_run_id",
        "worker_name",
        "queue",
        "trace_id",
        "readback_location",
        "status",
        "events",
    ]
    process_projection_statement = worker_process_runtime_projection_extension["statement"]
    assert "process runtime readback projection contract" in process_projection_statement
    assert "/api/v1/process/tasks?line_key={line_key}&limit=..." in process_projection_statement
    assert "/api/v1/process/logs?line_key={line_key}&limit=..." in process_projection_statement
    assert "line_key 级 runtime readback projection" in process_projection_statement
    assert "四条 worker-required line" in process_projection_statement
    assert "/{task_id} 动态路由吞掉" in process_projection_statement
    assert "不能硬编码 completion" in process_projection_statement
    assert "不宣称真实 worker completion" in process_projection_statement
    process_projection_route_contract = worker_process_runtime_projection_extension["route_contract"]
    assert "line_key query projection endpoints" in process_projection_route_contract
    assert "collection routes" in process_projection_route_contract
    assert "must not be swallowed" in process_projection_route_contract
    assert "/api/v1/process/tasks/{task_id}" in process_projection_route_contract
    process_projection_blocked_semantics = worker_process_runtime_projection_extension[
        "blocked_semantics"
    ]
    assert "Empty projection" in process_projection_blocked_semantics
    assert "line_key" in process_projection_blocked_semantics
    assert "task_id_or_run_id" in process_projection_blocked_semantics
    assert "worker_name" in process_projection_blocked_semantics
    assert "queue" in process_projection_blocked_semantics
    assert "trace_id" in process_projection_blocked_semantics
    assert "readback_location" in process_projection_blocked_semantics
    assert "status" in process_projection_blocked_semantics
    assert "events" in process_projection_blocked_semantics
    assert "route collision" in process_projection_blocked_semantics
    assert "async_task_readback_missing" in process_projection_blocked_semantics
    assert "blocked_by_environment" in process_projection_blocked_semantics
    assert "not passed" in process_projection_blocked_semantics
    process_projection_failure_semantics = worker_process_runtime_projection_extension[
        "failure_semantics"
    ]
    assert "must not synthesize or hardcode completion" in process_projection_failure_semantics
    assert "Missing or empty projection rows" in process_projection_failure_semantics
    assert "missing required projection fields" in process_projection_failure_semantics
    assert "dynamic-route capture" in process_projection_failure_semantics
    assert "non-runtime defaults" in process_projection_failure_semantics
    assert "cannot close worker-required proof" in process_projection_failure_semantics
    assert "async_task_readback_missing" in process_projection_failure_semantics
    assert "blocked_by_environment" in process_projection_failure_semantics
    assert (
        worker_process_runtime_projection_extension["completion_claim"]
        == "process_runtime_projection_only_does_not_claim_real_worker_completion"
    )
    identity_drift_warning_extension = async_task_readback_extension[
        "scheduled_artifact_identity_drift_warning_extension"
    ]
    assert identity_drift_warning_extension["batch"] == "100"
    assert (
        identity_drift_warning_extension["proof_level"]
        == "scheduled_artifact_identity_drift_warning_extension"
    )
    assert identity_drift_warning_extension["api_contract"]["added_artifact_fields"] == [
        "identity_status",
        "identity_warning",
        "identity_warning_message",
    ]
    assert identity_drift_warning_extension["api_contract"]["redacted_fields"] == [
        "absolute_path"
    ]
    assert "scheduled_completion_proof remains derived only from scheduled_run_evidence" in (
        identity_drift_warning_extension["checker_contract"]["identity_drift_boundary"]
    )
    identity_warning_grouping_extension = async_task_readback_extension[
        "scheduled_artifact_identity_warning_grouping_extension"
    ]
    assert identity_warning_grouping_extension["batch"] == "101"
    assert (
        identity_warning_grouping_extension["proof_level"]
        == "scheduled_artifact_identity_warning_grouping_extension"
    )
    assert identity_warning_grouping_extension["api_contract"]["added_lane_fields"] == [
        "identity_warning_count",
        "identity_warning_types",
        "identity_status_counts",
    ]
    assert identity_warning_grouping_extension["api_contract"]["missing_lane_defaults"] == {
        "identity_warning_count": 0,
        "identity_warning_types": [],
        "identity_status_counts": {},
    }
    assert identity_warning_grouping_extension["api_contract"]["redacted_fields"] == [
        "absolute_path"
    ]
    assert "triage metadata only" in (
        identity_warning_grouping_extension["checker_contract"]["grouping_boundary"]
    )
    assert "scheduled_completion_proof remains derived only from scheduled_run_evidence" in (
        identity_warning_grouping_extension["checker_contract"]["grouping_boundary"]
    )
    same_as_latest_projection_extension = async_task_readback_extension[
        "scheduled_artifact_same_as_latest_projection_extension"
    ]
    assert same_as_latest_projection_extension["batch"] == "102"
    assert (
        same_as_latest_projection_extension["proof_level"]
        == "scheduled_artifact_same_as_latest_projection_extension"
    )
    assert same_as_latest_projection_extension["checker_contract"]["triage_status"] == (
        "same_as_latest"
    )
    assert same_as_latest_projection_extension["checker_contract"]["warning_required"] is False
    assert (
        same_as_latest_projection_extension["api_contract"]["projection_mode"]
        == "same_as_latest_identity_status_projection_without_scheduler_proof"
    )
    assert same_as_latest_projection_extension["api_contract"]["redacted_fields"] == [
        "absolute_path"
    ]
    assert "no-warning triage status" in (
        same_as_latest_projection_extension["checker_contract"]["same_as_latest_boundary"]
    )
    assert "not scheduler proof" in (
        same_as_latest_projection_extension["checker_contract"]["same_as_latest_boundary"]
    )
    assert "scheduled_run_evidence" in (
        same_as_latest_projection_extension["scheduled_evidence_boundary"]
    )
    assert (
        same_as_latest_projection_extension["completion_claim"]
        == "same_as_latest_projection_added_without_claiming_cron_completion"
    )
    identity_warning_severity_extension = async_task_readback_extension[
        "scheduled_artifact_identity_warning_severity_extension"
    ]
    assert identity_warning_severity_extension["batch"] == "103"
    assert (
        identity_warning_severity_extension["proof_level"]
        == "scheduled_artifact_identity_warning_severity_extension"
    )
    assert identity_warning_severity_extension["checker_contract"]["artifact_fields"] == [
        "identity_warning_severity"
    ]
    assert identity_warning_severity_extension["checker_contract"]["lane_fields"] == [
        "identity_warning_severity_counts"
    ]
    assert identity_warning_severity_extension["api_contract"]["added_artifact_fields"] == [
        "identity_warning_severity"
    ]
    assert identity_warning_severity_extension["api_contract"]["added_lane_fields"] == [
        "identity_warning_severity_counts"
    ]
    assert identity_warning_severity_extension["api_contract"]["missing_lane_defaults"] == {
        "identity_warning_severity_counts": {},
    }
    assert identity_warning_severity_extension["api_contract"]["redacted_fields"] == [
        "absolute_path"
    ]
    assert "triage priority metadata" in (
        identity_warning_severity_extension["checker_contract"]["severity_boundary"]
    )
    assert "scheduled_completion_proof remains derived only from scheduled_run_evidence" in (
        identity_warning_severity_extension["checker_contract"]["severity_boundary"]
    )
    assert "scheduled_run_evidence" in (
        identity_warning_severity_extension["scheduled_evidence_boundary"]
    )
    assert (
        identity_warning_severity_extension["completion_claim"]
        == "identity_warning_severity_projection_added_without_claiming_cron_completion"
    )
    identity_warning_severity_order_extension = async_task_readback_extension[
        "scheduled_artifact_identity_warning_severity_order_extension"
    ]
    assert identity_warning_severity_order_extension["batch"] == "104"
    assert (
        identity_warning_severity_order_extension["proof_level"]
        == "scheduled_artifact_identity_warning_severity_order_extension"
    )
    assert identity_warning_severity_order_extension["checker_contract"]["lane_fields"] == [
        "identity_warning_severity_order",
        "identity_warning_highest_severity",
        "identity_warning_highest_severity_rank",
    ]
    assert identity_warning_severity_order_extension["api_contract"][
        "added_lane_fields"
    ] == [
        "identity_warning_severity_order",
        "identity_warning_highest_severity",
        "identity_warning_highest_severity_rank",
    ]
    assert identity_warning_severity_order_extension["api_contract"][
        "missing_lane_defaults"
    ] == {
        "identity_warning_severity_order": [],
        "identity_warning_highest_severity": None,
        "identity_warning_highest_severity_rank": None,
    }
    assert identity_warning_severity_order_extension["api_contract"][
        "redacted_fields"
    ] == ["absolute_path"]
    assert "triage ordering metadata only" in (
        identity_warning_severity_order_extension["checker_contract"][
            "severity_order_boundary"
        ]
    )
    assert "scheduled_completion_proof remains derived only from scheduled_run_evidence" in (
        identity_warning_severity_order_extension["checker_contract"][
            "severity_order_boundary"
        ]
    )
    assert "does not change scheduled_completion_proof" in (
        identity_warning_severity_order_extension["scheduled_evidence_boundary"]
    )
    assert (
        identity_warning_severity_order_extension["completion_claim"]
        == "identity_warning_severity_order_projection_added_without_claiming_cron_completion"
    )
    warning_filter_ui_extension = async_task_readback_extension[
        "scheduled_artifact_warning_filter_ui_extension"
    ]
    assert warning_filter_ui_extension["batch"] == "105"
    assert (
        warning_filter_ui_extension["proof_level"]
        == "scheduled_artifact_warning_filter_ui_extension"
    )
    assert warning_filter_ui_extension["ops_ui_contract"]["filter_inputs"] == [
        "identity_warning_count",
        "identity_warning_highest_severity_rank",
    ]
    assert "frontend display filtering only" in (
        warning_filter_ui_extension["ops_ui_contract"]["filter_scope"]
    )
    assert "not the API scheduled evidence semantics" in (
        warning_filter_ui_extension["ops_ui_contract"]["filter_scope"]
    )
    assert warning_filter_ui_extension["api_contract"]["proof_addition"] == "none"
    assert (
        warning_filter_ui_extension["api_contract"]["scheduled_completion_proof_source"]
        == "scheduled_run_evidence"
    )
    assert "scheduled_completion_proof is controlled only by scheduled_run_evidence" in (
        warning_filter_ui_extension["api_contract"]["scheduled_evidence_semantics"]
    )
    assert warning_filter_ui_extension["api_contract"]["redacted_fields"] == [
        "absolute_path"
    ]
    assert "identity_warning_count" in (
        warning_filter_ui_extension["scheduled_evidence_boundary"]
    )
    assert "identity_warning_highest_severity_rank" in (
        warning_filter_ui_extension["scheduled_evidence_boundary"]
    )
    assert "only changes Ops UI display" in (
        warning_filter_ui_extension["scheduled_evidence_boundary"]
    )
    assert "API adds no proof" in (
        warning_filter_ui_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled_completion_proof remains derived only from scheduled_run_evidence" in (
        warning_filter_ui_extension["scheduled_evidence_boundary"]
    )
    assert (
        warning_filter_ui_extension["completion_claim"]
        == "ops_warning_only_filter_ui_boundary_added_without_claiming_real_scheduler_run"
    )
    warning_sort_ui_extension = async_task_readback_extension[
        "scheduled_artifact_warning_sort_ui_extension"
    ]
    assert warning_sort_ui_extension["batch"] == "106"
    assert (
        warning_sort_ui_extension["proof_level"]
        == "scheduled_artifact_warning_sort_ui_extension"
    )
    assert warning_sort_ui_extension["ops_ui_contract"]["sort_inputs"] == [
        "identity_warning_highest_severity_rank",
        "identity_warning_count",
        "artifact_count",
    ]
    assert warning_sort_ui_extension["ops_ui_contract"]["sort_modes"] == [
        "source_order",
        "warning_priority",
        "warning_count",
        "artifact_count",
    ]
    assert "frontend display ordering only" in (
        warning_sort_ui_extension["ops_ui_contract"]["sort_scope"]
    )
    assert "not the API scheduled evidence semantics" in (
        warning_sort_ui_extension["ops_ui_contract"]["sort_scope"]
    )
    assert warning_sort_ui_extension["api_contract"]["proof_addition"] == "none"
    assert (
        warning_sort_ui_extension["api_contract"]["scheduled_completion_proof_source"]
        == "scheduled_run_evidence"
    )
    assert (
        warning_sort_ui_extension["api_contract"]["scheduled_evidence_source"]
        == "scheduled_run_evidence"
    )
    assert "scheduled_completion_proof is still controlled only by scheduled_run_evidence" in (
        warning_sort_ui_extension["api_contract"]["scheduled_evidence_semantics"]
    )
    assert warning_sort_ui_extension["api_contract"]["redacted_fields"] == [
        "absolute_path"
    ]
    assert "identity_warning_highest_severity_rank" in (
        warning_sort_ui_extension["scheduled_evidence_boundary"]
    )
    assert "identity_warning_count" in (
        warning_sort_ui_extension["scheduled_evidence_boundary"]
    )
    assert "artifact_count" in warning_sort_ui_extension["scheduled_evidence_boundary"]
    assert "source_order" in warning_sort_ui_extension["scheduled_evidence_boundary"]
    assert "warning_priority" in warning_sort_ui_extension["scheduled_evidence_boundary"]
    assert "warning_count" in warning_sort_ui_extension["scheduled_evidence_boundary"]
    assert "Sorting changes only Ops UI display order" in (
        warning_sort_ui_extension["scheduled_evidence_boundary"]
    )
    assert "API adds no proof" in warning_sort_ui_extension["scheduled_evidence_boundary"]
    assert "scheduled_completion_proof remains derived only from scheduled_run_evidence" in (
        warning_sort_ui_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled evidence is still controlled by scheduled_run_evidence" in (
        warning_sort_ui_extension["scheduled_evidence_boundary"]
    )
    assert (
        warning_sort_ui_extension["completion_claim"]
        == "ops_lane_sort_ui_boundary_added_without_closing_real_scheduler_run"
    )
    assert "does not close" in warning_sort_ui_extension["completion_claim_boundary"]
    assert "real scheduler run" in warning_sort_ui_extension["completion_claim_boundary"]
    warning_sort_explanation_ui_extension = async_task_readback_extension[
        "scheduled_artifact_warning_sort_explanation_ui_extension"
    ]
    assert warning_sort_explanation_ui_extension["batch"] == "107"
    assert (
        warning_sort_explanation_ui_extension["proof_level"]
        == "scheduled_artifact_warning_sort_explanation_ui_extension"
    )
    assert warning_sort_explanation_ui_extension["ops_ui_contract"][
        "explanation_modes"
    ] == [
        "source_order",
        "warning_priority",
        "warning_count",
        "artifact_count",
    ]
    explanations = warning_sort_explanation_ui_extension["ops_ui_contract"][
        "explanations"
    ]
    assert set(explanations) == {
        "source_order",
        "warning_priority",
        "warning_count",
        "artifact_count",
    }
    for explanation in explanations.values():
        assert "Ops UI sort explanation only" in explanation
        assert "scheduled_completion_proof" in explanation
        assert "scheduled evidence" in explanation
    assert "Ops sort explanations describe only" in (
        warning_sort_explanation_ui_extension["ops_ui_contract"]["explanation_scope"]
    )
    assert "do not add API proof" in (
        warning_sort_explanation_ui_extension["ops_ui_contract"]["explanation_scope"]
    )
    assert "do not change API fields" in (
        warning_sort_explanation_ui_extension["ops_ui_contract"]["explanation_scope"]
    )
    assert (
        warning_sort_explanation_ui_extension["api_contract"]["proof_addition"]
        == "none"
    )
    assert (
        warning_sort_explanation_ui_extension["api_contract"]["api_fields_changed"]
        is False
    )
    assert (
        warning_sort_explanation_ui_extension["api_contract"][
            "scheduled_completion_proof_changed"
        ]
        is False
    )
    assert (
        warning_sort_explanation_ui_extension["api_contract"][
            "scheduled_completion_proof_source"
        ]
        == "scheduled_run_evidence"
    )
    assert (
        warning_sort_explanation_ui_extension["api_contract"][
            "scheduled_evidence_source"
        ]
        == "scheduled_run_evidence"
    )
    assert (
        warning_sort_explanation_ui_extension["api_contract"][
            "scheduled_evidence_controller"
        ]
        == "scheduled_run_evidence"
    )
    assert "scheduled_completion_proof is still controlled only by scheduled_run_evidence" in (
        warning_sort_explanation_ui_extension["api_contract"]["scheduled_evidence_semantics"]
    )
    assert "scheduled evidence is still controlled only by scheduled_run_evidence" in (
        warning_sort_explanation_ui_extension["api_contract"]["scheduled_evidence_semantics"]
    )
    assert warning_sort_explanation_ui_extension["api_contract"]["redacted_fields"] == [
        "absolute_path"
    ]
    assert "source_order" in warning_sort_explanation_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "warning_priority" in warning_sort_explanation_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "warning_count" in warning_sort_explanation_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "artifact_count" in warning_sort_explanation_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "only for Ops UI sort explanation" in warning_sort_explanation_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "adds no API proof" in warning_sort_explanation_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "changes no API fields" in warning_sort_explanation_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "does not change scheduled_completion_proof" in (
        warning_sort_explanation_ui_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled_completion_proof remains derived only from scheduled_run_evidence" in (
        warning_sort_explanation_ui_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled evidence is still controlled only by scheduled_run_evidence" in (
        warning_sort_explanation_ui_extension["scheduled_evidence_boundary"]
    )
    assert (
        warning_sort_explanation_ui_extension["completion_claim"]
        == "ops_sort_explanation_ui_boundary_added_without_changing_scheduled_evidence"
    )
    assert "Ops UI sort explanation metadata boundary" in (
        warning_sort_explanation_ui_extension["completion_claim_boundary"]
    )
    assert "scheduled_run_evidence proof" in (
        warning_sort_explanation_ui_extension["completion_claim_boundary"]
    )
    warning_empty_state_ui_extension = async_task_readback_extension[
        "scheduled_artifact_warning_empty_state_ui_extension"
    ]
    assert warning_empty_state_ui_extension["batch"] == "108"
    assert (
        warning_empty_state_ui_extension["proof_level"]
        == "scheduled_artifact_warning_empty_state_ui_extension"
    )
    empty_state_trigger = warning_empty_state_ui_extension["ops_ui_contract"][
        "empty_state_trigger"
    ]
    assert empty_state_trigger["filter"] == "warning_only filter"
    assert empty_state_trigger["visible_lanes"] == 0
    assert empty_state_trigger["visible_lanes_condition"] == "visible_lanes == 0"
    assert empty_state_trigger["total_lanes_condition"] == "total_lanes > 0"
    assert (
        warning_empty_state_ui_extension["ops_ui_contract"]["empty_state_message"]
        == "No lanes match the current warning-only view."
    )
    assert "only explains that the current warning-only view has no matching lane" in (
        warning_empty_state_ui_extension["ops_ui_contract"]["empty_state_scope"]
    )
    assert "does not mean scheduled evidence passed" in (
        warning_empty_state_ui_extension["ops_ui_contract"]["empty_state_scope"]
    )
    assert warning_empty_state_ui_extension["api_contract"]["proof_addition"] == "none"
    assert (
        warning_empty_state_ui_extension["api_contract"]["api_fields_changed"] is False
    )
    assert (
        warning_empty_state_ui_extension["api_contract"][
            "scheduled_completion_proof_changed"
        ]
        is False
    )
    assert (
        warning_empty_state_ui_extension["api_contract"][
            "scheduled_completion_proof_source"
        ]
        == "scheduled_run_evidence"
    )
    assert (
        warning_empty_state_ui_extension["api_contract"]["scheduled_evidence_source"]
        == "scheduled_run_evidence"
    )
    assert (
        warning_empty_state_ui_extension["api_contract"][
            "scheduled_evidence_controller"
        ]
        == "scheduled_run_evidence"
    )
    assert "not scheduled evidence passed" in (
        warning_empty_state_ui_extension["api_contract"]["scheduled_evidence_semantics"]
    )
    assert "adds no API proof" in (
        warning_empty_state_ui_extension["api_contract"]["scheduled_evidence_semantics"]
    )
    assert "changes no API fields" in (
        warning_empty_state_ui_extension["api_contract"]["scheduled_evidence_semantics"]
    )
    assert "does not change scheduled_completion_proof" in (
        warning_empty_state_ui_extension["api_contract"]["scheduled_evidence_semantics"]
    )
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        warning_empty_state_ui_extension["api_contract"]["scheduled_evidence_semantics"]
    )
    assert warning_empty_state_ui_extension["api_contract"]["redacted_fields"] == [
        "absolute_path"
    ]
    assert "warning_only filter" in warning_empty_state_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "visible_lanes == 0" in warning_empty_state_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "total_lanes > 0" in warning_empty_state_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "current warning-only view has no matching lane" in (
        warning_empty_state_ui_extension["scheduled_evidence_boundary"]
    )
    assert "not equivalent to scheduled evidence passed" in (
        warning_empty_state_ui_extension["scheduled_evidence_boundary"]
    )
    assert "adds no API proof" in warning_empty_state_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "changes no API fields" in warning_empty_state_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "does not change scheduled_completion_proof" in (
        warning_empty_state_ui_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled_completion_proof remains derived only from scheduled_run_evidence" in (
        warning_empty_state_ui_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled evidence is still controlled only by scheduled_run_evidence" in (
        warning_empty_state_ui_extension["scheduled_evidence_boundary"]
    )
    assert (
        warning_empty_state_ui_extension["completion_claim"]
        == "ops_warning_only_empty_state_ui_boundary_added_without_changing_scheduled_evidence"
    )
    assert "Ops warning-only empty state metadata boundary" in (
        warning_empty_state_ui_extension["completion_claim_boundary"]
    )
    assert "scheduled_run_evidence proof" in (
        warning_empty_state_ui_extension["completion_claim_boundary"]
    )
    warning_empty_diagnostics_ui_extension = async_task_readback_extension[
        "scheduled_artifact_warning_empty_diagnostics_ui_extension"
    ]
    assert warning_empty_diagnostics_ui_extension["batch"] == "109"
    assert (
        warning_empty_diagnostics_ui_extension["proof_level"]
        == "scheduled_artifact_warning_empty_diagnostics_ui_extension"
    )
    empty_diagnostics_contract = warning_empty_diagnostics_ui_extension[
        "ops_ui_contract"
    ]
    assert empty_diagnostics_contract["diagnostics_fields"] == [
        "filter",
        "sort",
        "total_lanes",
        "visible_lanes",
        "warning_lanes",
    ]
    assert "current warning-only empty view parameters" in (
        empty_diagnostics_contract["diagnostics_scope"]
    )
    for diagnostics_field in [
        "filter",
        "sort",
        "total_lanes",
        "visible_lanes",
        "warning_lanes",
    ]:
        assert diagnostics_field in empty_diagnostics_contract["diagnostics_scope"]
        assert diagnostics_field in warning_empty_diagnostics_ui_extension[
            "scheduled_evidence_boundary"
        ]
    assert "current empty UI state parameters only" in (
        empty_diagnostics_contract["empty_diagnostics_boundary"]
    )
    assert "do not assert scheduled evidence passed" in (
        empty_diagnostics_contract["empty_diagnostics_boundary"]
    )
    assert "do not add any lane proof" in (
        empty_diagnostics_contract["empty_diagnostics_boundary"]
    )
    assert (
        warning_empty_diagnostics_ui_extension["api_contract"]["proof_addition"]
        == "none"
    )
    assert (
        warning_empty_diagnostics_ui_extension["api_contract"]["api_fields_changed"]
        is False
    )
    assert (
        warning_empty_diagnostics_ui_extension["api_contract"][
            "scheduled_completion_proof_changed"
        ]
        is False
    )
    assert (
        warning_empty_diagnostics_ui_extension["api_contract"][
            "scheduled_completion_proof_source"
        ]
        == "scheduled_run_evidence"
    )
    assert (
        warning_empty_diagnostics_ui_extension["api_contract"][
            "scheduled_evidence_source"
        ]
        == "scheduled_run_evidence"
    )
    assert (
        warning_empty_diagnostics_ui_extension["api_contract"][
            "scheduled_evidence_controller"
        ]
        == "scheduled_run_evidence"
    )
    assert "add no API proof" in (
        warning_empty_diagnostics_ui_extension["api_contract"][
            "scheduled_evidence_semantics"
        ]
    )
    assert "change no API fields" in (
        warning_empty_diagnostics_ui_extension["api_contract"][
            "scheduled_evidence_semantics"
        ]
    )
    assert "do not change scheduled_completion_proof" in (
        warning_empty_diagnostics_ui_extension["api_contract"][
            "scheduled_evidence_semantics"
        ]
    )
    assert "scheduled evidence is still controlled only by scheduled_run_evidence" in (
        warning_empty_diagnostics_ui_extension["api_contract"][
            "scheduled_evidence_semantics"
        ]
    )
    assert warning_empty_diagnostics_ui_extension["api_contract"]["redacted_fields"] == [
        "absolute_path"
    ]
    assert "Batch 109" in warning_empty_diagnostics_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "current warning-only empty view parameters" in (
        warning_empty_diagnostics_ui_extension["scheduled_evidence_boundary"]
    )
    assert "add no API proof" in warning_empty_diagnostics_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "change no API fields" in warning_empty_diagnostics_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "do not change scheduled_completion_proof" in (
        warning_empty_diagnostics_ui_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled_completion_proof remains derived only from scheduled_run_evidence" in (
        warning_empty_diagnostics_ui_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled evidence is still controlled only by scheduled_run_evidence" in (
        warning_empty_diagnostics_ui_extension["scheduled_evidence_boundary"]
    )
    assert (
        warning_empty_diagnostics_ui_extension["completion_claim"]
        == "ops_warning_only_empty_diagnostics_ui_boundary_added_without_changing_scheduled_evidence"
    )
    assert "Ops warning-only empty diagnostics metadata boundary" in (
        warning_empty_diagnostics_ui_extension["completion_claim_boundary"]
    )
    assert "scheduled_run_evidence proof" in (
        warning_empty_diagnostics_ui_extension["completion_claim_boundary"]
    )
    warning_empty_reset_ui_extension = async_task_readback_extension[
        "scheduled_artifact_warning_empty_reset_ui_extension"
    ]
    assert warning_empty_reset_ui_extension["batch"] == "110"
    assert (
        warning_empty_reset_ui_extension["proof_level"]
        == "scheduled_artifact_warning_empty_reset_ui_extension"
    )
    empty_reset_contract = warning_empty_reset_ui_extension["ops_ui_contract"]
    assert (
        empty_reset_contract["reset_action_label"]
        == "reset empty warning view: show all lanes"
    )
    assert empty_reset_contract["filter_transition"] == {
        "from": "warning_only",
        "to": "all",
    }
    assert empty_reset_contract["sort_behavior"] == "sort remains unchanged"
    assert empty_reset_contract["payload_behavior"] == "API payload unchanged"
    assert "reset empty warning view: show all lanes" in (
        empty_reset_contract["reset_scope"]
    )
    assert "Reset changes only UI filter from warning_only to all" in (
        empty_reset_contract["reset_scope"]
    )
    assert "sort remains unchanged" in empty_reset_contract["reset_scope"]
    assert "API payload unchanged" in empty_reset_contract["reset_scope"]
    assert (
        warning_empty_reset_ui_extension["api_contract"]["proof_addition"]
        == "none"
    )
    assert (
        warning_empty_reset_ui_extension["api_contract"]["api_proof_added"]
        is False
    )
    assert (
        warning_empty_reset_ui_extension["api_contract"]["api_fields_changed"]
        is False
    )
    assert (
        warning_empty_reset_ui_extension["api_contract"]["api_payload_changed"]
        is False
    )
    assert (
        warning_empty_reset_ui_extension["api_contract"][
            "scheduled_completion_proof_changed"
        ]
        is False
    )
    assert (
        warning_empty_reset_ui_extension["api_contract"][
            "scheduled_completion_proof_source"
        ]
        == "scheduled_run_evidence"
    )
    assert (
        warning_empty_reset_ui_extension["api_contract"][
            "scheduled_evidence_source"
        ]
        == "scheduled_run_evidence"
    )
    assert (
        warning_empty_reset_ui_extension["api_contract"][
            "scheduled_evidence_controller"
        ]
        == "scheduled_run_evidence"
    )
    assert "adds no API proof" in (
        warning_empty_reset_ui_extension["api_contract"][
            "scheduled_evidence_semantics"
        ]
    )
    assert "changes no API fields" in (
        warning_empty_reset_ui_extension["api_contract"][
            "scheduled_evidence_semantics"
        ]
    )
    assert "leaves API payload unchanged" in (
        warning_empty_reset_ui_extension["api_contract"][
            "scheduled_evidence_semantics"
        ]
    )
    assert "does not change scheduled_completion_proof" in (
        warning_empty_reset_ui_extension["api_contract"][
            "scheduled_evidence_semantics"
        ]
    )
    assert "scheduled evidence is still controlled only by scheduled_run_evidence" in (
        warning_empty_reset_ui_extension["api_contract"][
            "scheduled_evidence_semantics"
        ]
    )
    assert warning_empty_reset_ui_extension["api_contract"]["redacted_fields"] == [
        "absolute_path"
    ]
    assert "Batch 110" in warning_empty_reset_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "reset empty warning view: show all lanes" in (
        warning_empty_reset_ui_extension["scheduled_evidence_boundary"]
    )
    assert "only UI filter from warning_only to all" in (
        warning_empty_reset_ui_extension["scheduled_evidence_boundary"]
    )
    assert "sort remains unchanged" in warning_empty_reset_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "API payload unchanged" in warning_empty_reset_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "adds no API proof" in warning_empty_reset_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "changes no API fields" in warning_empty_reset_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "does not change scheduled_completion_proof" in (
        warning_empty_reset_ui_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled_completion_proof remains derived only from scheduled_run_evidence" in (
        warning_empty_reset_ui_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled evidence is still controlled only by scheduled_run_evidence" in (
        warning_empty_reset_ui_extension["scheduled_evidence_boundary"]
    )
    assert (
        warning_empty_reset_ui_extension["completion_claim"]
        == "ops_warning_only_empty_reset_ui_boundary_added_without_changing_scheduled_evidence"
    )
    assert "Ops warning-only empty reset affordance metadata boundary" in (
        warning_empty_reset_ui_extension["completion_claim_boundary"]
    )
    assert "scheduled_run_evidence proof" in (
        warning_empty_reset_ui_extension["completion_claim_boundary"]
    )
    warning_empty_reset_telemetry_ui_extension = async_task_readback_extension[
        "scheduled_artifact_warning_empty_reset_telemetry_ui_extension"
    ]
    assert warning_empty_reset_telemetry_ui_extension["batch"] == "111"
    assert (
        warning_empty_reset_telemetry_ui_extension["proof_level"]
        == "scheduled_artifact_warning_empty_reset_telemetry_ui_extension"
    )
    reset_telemetry_contract = warning_empty_reset_telemetry_ui_extension[
        "ui_event_contract"
    ]
    assert reset_telemetry_contract["event_name"] == "reset_empty_warning_view"
    assert reset_telemetry_contract["event_scope"] == "ui_event_log_only"
    assert reset_telemetry_contract["filter_transition"] == {
        "from": "warning_only",
        "to": "all",
    }
    assert reset_telemetry_contract["sort_behavior"] == "unchanged"
    assert reset_telemetry_contract["api_payload_behavior"] == "unchanged"
    assert reset_telemetry_contract["scheduled_evidence_write"] == "none"
    assert "UI event log" in reset_telemetry_contract["telemetry_scope"]
    assert "reset_empty_warning_view" in reset_telemetry_contract["telemetry_scope"]
    assert "warning_only to all filter transition" in (
        reset_telemetry_contract["telemetry_scope"]
    )
    assert "keeps sort unchanged" in reset_telemetry_contract["telemetry_scope"]
    assert "keeps API payload unchanged" in (
        reset_telemetry_contract["telemetry_scope"]
    )
    assert "writes no scheduled evidence" in (
        reset_telemetry_contract["telemetry_scope"]
    )
    reset_telemetry_api_contract = warning_empty_reset_telemetry_ui_extension[
        "api_contract"
    ]
    assert (
        reset_telemetry_api_contract["route"]
        == "/api/v1/business-lines/evidence-matrix"
    )
    assert reset_telemetry_api_contract["proof_addition"] == "none"
    assert reset_telemetry_api_contract["api_proof_added"] is False
    assert reset_telemetry_api_contract["api_fields_changed"] is False
    assert reset_telemetry_api_contract["api_payload_changed"] is False
    assert (
        reset_telemetry_api_contract["scheduled_completion_proof_changed"]
        is False
    )
    assert (
        reset_telemetry_api_contract["scheduled_evidence_controller"]
        == "scheduled_run_evidence"
    )
    assert "UI event log only" in reset_telemetry_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "adds no API proof" in reset_telemetry_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "changes no API fields" in reset_telemetry_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "leaves API payload unchanged" in reset_telemetry_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "does not change scheduled_completion_proof" in (
        reset_telemetry_api_contract["scheduled_evidence_semantics"]
    )
    assert "writes no scheduled evidence" in reset_telemetry_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        reset_telemetry_api_contract["scheduled_evidence_semantics"]
    )
    assert "Batch 111" in warning_empty_reset_telemetry_ui_extension[
        "scheduled_evidence_boundary"
    ]
    assert "reset_empty_warning_view is UI event log only" in (
        warning_empty_reset_telemetry_ui_extension["scheduled_evidence_boundary"]
    )
    assert "warning_only to all filter transition" in (
        warning_empty_reset_telemetry_ui_extension["scheduled_evidence_boundary"]
    )
    assert "keeps sort unchanged" in (
        warning_empty_reset_telemetry_ui_extension["scheduled_evidence_boundary"]
    )
    assert "keeps API payload unchanged" in (
        warning_empty_reset_telemetry_ui_extension["scheduled_evidence_boundary"]
    )
    assert "writes no scheduled evidence" in (
        warning_empty_reset_telemetry_ui_extension["scheduled_evidence_boundary"]
    )
    assert "adds no API proof" in (
        warning_empty_reset_telemetry_ui_extension["scheduled_evidence_boundary"]
    )
    assert "changes no API fields" in (
        warning_empty_reset_telemetry_ui_extension["scheduled_evidence_boundary"]
    )
    assert "does not change scheduled_completion_proof" in (
        warning_empty_reset_telemetry_ui_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        warning_empty_reset_telemetry_ui_extension["scheduled_evidence_boundary"]
    )
    assert (
        warning_empty_reset_telemetry_ui_extension["completion_claim"]
        == "ops_warning_only_empty_reset_telemetry_ui_boundary_added_without_changing_scheduled_evidence"
    )
    assert "Ops reset telemetry metadata boundary" in (
        warning_empty_reset_telemetry_ui_extension["completion_claim_boundary"]
    )
    assert "scheduled_run_evidence proof" in (
        warning_empty_reset_telemetry_ui_extension["completion_claim_boundary"]
    )
    dashboard_reset_telemetry_reuse_extension = async_task_readback_extension[
        "dashboard_scheduled_artifact_reset_telemetry_reuse_extension"
    ]
    assert dashboard_reset_telemetry_reuse_extension["batch"] == "112"
    assert (
        dashboard_reset_telemetry_reuse_extension["proof_level"]
        == "dashboard_scheduled_artifact_reset_telemetry_reuse_extension"
    )
    dashboard_reuse_contract = dashboard_reset_telemetry_reuse_extension[
        "dashboard_reuse_contract"
    ]
    assert dashboard_reuse_contract["consumer_surface"] == "DashboardPage"
    assert (
        dashboard_reuse_contract["source_metadata_key"]
        == "scheduled_artifact_warning_empty_reset_telemetry_ui_extension"
    )
    assert dashboard_reuse_contract["display_scope"] == "read_only_boundary_summary"
    assert dashboard_reuse_contract["event_name"] == "reset_empty_warning_view"
    assert dashboard_reuse_contract["event_scope"] == "ui_event_log_only"
    assert dashboard_reuse_contract["scheduled_evidence_write"] == "none"
    assert "Dashboard/report detail reuse" in dashboard_reuse_contract["reuse_scope"]
    assert "read-only boundary summary" in dashboard_reuse_contract["reuse_scope"]
    assert "scheduled_artifact_warning_empty_reset_telemetry_ui_extension" in (
        dashboard_reuse_contract["reuse_scope"]
    )
    assert "reset_empty_warning_view as ui_event_log_only telemetry" in (
        dashboard_reuse_contract["reuse_scope"]
    )
    assert "writes no scheduled evidence" in dashboard_reuse_contract["reuse_scope"]
    dashboard_reuse_api_contract = dashboard_reset_telemetry_reuse_extension[
        "api_contract"
    ]
    assert (
        dashboard_reuse_api_contract["route"]
        == "/api/v1/business-lines/evidence-matrix"
    )
    assert dashboard_reuse_api_contract["proof_addition"] == "none"
    assert dashboard_reuse_api_contract["api_proof_added"] is False
    assert dashboard_reuse_api_contract["api_fields_changed"] is False
    assert dashboard_reuse_api_contract["api_payload_changed"] is False
    assert (
        dashboard_reuse_api_contract["scheduled_completion_proof_changed"]
        is False
    )
    assert (
        dashboard_reuse_api_contract["scheduled_evidence_controller"]
        == "scheduled_run_evidence"
    )
    assert "read-only display" in dashboard_reuse_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "adds no API proof" in dashboard_reuse_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "changes no API fields" in dashboard_reuse_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "leaves API payload unchanged" in dashboard_reuse_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "does not change scheduled_completion_proof" in (
        dashboard_reuse_api_contract["scheduled_evidence_semantics"]
    )
    assert "writes no scheduled evidence" in dashboard_reuse_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        dashboard_reuse_api_contract["scheduled_evidence_semantics"]
    )
    assert "Batch 112" in dashboard_reset_telemetry_reuse_extension[
        "scheduled_evidence_boundary"
    ]
    assert "DashboardPage consumes" in (
        dashboard_reset_telemetry_reuse_extension["scheduled_evidence_boundary"]
    )
    assert "read_only_boundary_summary" in (
        dashboard_reset_telemetry_reuse_extension["scheduled_evidence_boundary"]
    )
    assert "reset_empty_warning_view" in (
        dashboard_reset_telemetry_reuse_extension["scheduled_evidence_boundary"]
    )
    assert "ui_event_log_only" in (
        dashboard_reset_telemetry_reuse_extension["scheduled_evidence_boundary"]
    )
    assert "writes no scheduled evidence" in (
        dashboard_reset_telemetry_reuse_extension["scheduled_evidence_boundary"]
    )
    assert "adds no API proof" in (
        dashboard_reset_telemetry_reuse_extension["scheduled_evidence_boundary"]
    )
    assert "changes no API fields" in (
        dashboard_reset_telemetry_reuse_extension["scheduled_evidence_boundary"]
    )
    assert "leaves API payload unchanged" in (
        dashboard_reset_telemetry_reuse_extension["scheduled_evidence_boundary"]
    )
    assert "does not change scheduled_completion_proof" in (
        dashboard_reset_telemetry_reuse_extension["scheduled_evidence_boundary"]
    )
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        dashboard_reset_telemetry_reuse_extension["scheduled_evidence_boundary"]
    )
    assert (
        dashboard_reset_telemetry_reuse_extension["completion_claim"]
        == "dashboard_reset_telemetry_reuse_boundary_added_without_changing_scheduled_evidence"
    )
    assert "Dashboard/report detail read-only reuse metadata boundary" in (
        dashboard_reset_telemetry_reuse_extension["completion_claim_boundary"]
    )
    assert "scheduled_run_evidence proof" in (
        dashboard_reset_telemetry_reuse_extension["completion_claim_boundary"]
    )
    dashboard_report_detail_reset_telemetry_reuse_extension = async_task_readback_extension[
        "dashboard_report_detail_reset_telemetry_reuse_extension"
    ]
    assert dashboard_report_detail_reset_telemetry_reuse_extension["batch"] == "113"
    assert (
        dashboard_report_detail_reset_telemetry_reuse_extension["proof_level"]
        == "dashboard_report_detail_reset_telemetry_reuse_extension"
    )
    report_detail_reuse_contract = (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "report_detail_reuse_contract"
        ]
    )
    assert (
        report_detail_reuse_contract["consumer_surface"]
        == "DashboardPage.report_detail"
    )
    assert (
        report_detail_reuse_contract["source_metadata_key"]
        == "scheduled_artifact_warning_empty_reset_telemetry_ui_extension"
    )
    assert (
        report_detail_reuse_contract["display_scope"]
        == "report_detail_read_only_boundary_summary"
    )
    assert report_detail_reuse_contract["event_name"] == "reset_empty_warning_view"
    assert report_detail_reuse_contract["event_scope"] == "ui_event_log_only"
    assert report_detail_reuse_contract["scheduled_evidence_write"] == "none"
    assert "DashboardPage report detail" in report_detail_reuse_contract[
        "reuse_scope"
    ]
    assert "read-only boundary summary" in report_detail_reuse_contract[
        "reuse_scope"
    ]
    assert "scheduled_artifact_warning_empty_reset_telemetry_ui_extension" in (
        report_detail_reuse_contract["reuse_scope"]
    )
    assert "reset_empty_warning_view as ui_event_log_only telemetry" in (
        report_detail_reuse_contract["reuse_scope"]
    )
    assert "writes no scheduled evidence" in report_detail_reuse_contract[
        "reuse_scope"
    ]
    report_detail_reuse_api_contract = (
        dashboard_report_detail_reset_telemetry_reuse_extension["api_contract"]
    )
    assert (
        report_detail_reuse_api_contract["route"]
        == "/api/v1/business-lines/evidence-matrix"
    )
    assert report_detail_reuse_api_contract["proof_addition"] == "none"
    assert report_detail_reuse_api_contract["api_proof_added"] is False
    assert report_detail_reuse_api_contract["api_fields_changed"] is False
    assert report_detail_reuse_api_contract["api_payload_changed"] is False
    assert (
        report_detail_reuse_api_contract["scheduled_completion_proof_changed"]
        is False
    )
    assert (
        report_detail_reuse_api_contract["scheduled_evidence_controller"]
        == "scheduled_run_evidence"
    )
    assert "read-only display" in report_detail_reuse_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "adds no API proof" in report_detail_reuse_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "changes no API fields" in report_detail_reuse_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "leaves API payload unchanged" in report_detail_reuse_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "does not change scheduled_completion_proof" in (
        report_detail_reuse_api_contract["scheduled_evidence_semantics"]
    )
    assert "writes no scheduled evidence" in report_detail_reuse_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        report_detail_reuse_api_contract["scheduled_evidence_semantics"]
    )
    assert "Batch 113" in dashboard_report_detail_reset_telemetry_reuse_extension[
        "scheduled_evidence_boundary"
    ]
    assert "DashboardPage.report_detail" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "report_detail_read_only_boundary_summary" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "reset_empty_warning_view" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "ui_event_log_only" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "writes no scheduled evidence" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "adds no API proof" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "changes no API fields" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "leaves API payload unchanged" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "does not change scheduled_completion_proof" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert (
        dashboard_report_detail_reset_telemetry_reuse_extension["completion_claim"]
        == "dashboard_report_detail_reset_telemetry_reuse_boundary_added_without_changing_scheduled_evidence"
    )
    assert "DashboardPage.report_detail read-only reuse metadata boundary" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "completion_claim_boundary"
        ]
    )
    assert "scheduled_run_evidence proof" in (
        dashboard_report_detail_reset_telemetry_reuse_extension[
            "completion_claim_boundary"
        ]
    )
    dashboard_reset_telemetry_fallback_boundary_extension = async_task_readback_extension[
        "dashboard_reset_telemetry_fallback_boundary_extension"
    ]
    assert dashboard_reset_telemetry_fallback_boundary_extension["batch"] == "114"
    assert (
        dashboard_reset_telemetry_fallback_boundary_extension["proof_level"]
        == "dashboard_reset_telemetry_fallback_boundary_extension"
    )
    fallback_contract = dashboard_reset_telemetry_fallback_boundary_extension[
        "fallback_contract"
    ]
    assert fallback_contract["consumer_surfaces"] == [
        "DashboardPage",
        "DashboardPage.report_detail",
    ]
    assert (
        fallback_contract["fallback_trigger"]
        == "missing_or_invalid_reset_telemetry_metadata"
    )
    assert fallback_contract["fallback_message"] == "reset telemetry metadata unavailable"
    assert (
        fallback_contract["fallback_not_proof_label"]
        == "fallback boundary: not scheduled_run_evidence proof"
    )
    assert fallback_contract["scheduled_evidence_write"] == "none"
    assert (
        fallback_contract["scheduled_completion_proof_behavior"]
        == "unchanged"
    )
    assert (
        fallback_contract["contract_reuse_claim"]
        == "none_when_metadata_missing"
    )
    assert "Dashboard and DashboardPage.report_detail fallback" in (
        fallback_contract["fallback_scope"]
    )
    assert "reset telemetry metadata unavailable" in fallback_contract[
        "fallback_scope"
    ]
    assert "not-proof label" in fallback_contract["fallback_scope"]
    assert "missing or invalid" in fallback_contract["fallback_scope"]
    assert "must not claim contract reuse" in fallback_contract["fallback_scope"]
    assert "must not write scheduled evidence" in fallback_contract[
        "fallback_scope"
    ]
    assert "must not change scheduled_completion_proof" in fallback_contract[
        "fallback_scope"
    ]
    fallback_api_contract = dashboard_reset_telemetry_fallback_boundary_extension[
        "api_contract"
    ]
    assert fallback_api_contract["route"] == "/api/v1/business-lines/evidence-matrix"
    assert fallback_api_contract["proof_addition"] == "none"
    assert fallback_api_contract["api_proof_added"] is False
    assert fallback_api_contract["api_fields_changed"] is False
    assert fallback_api_contract["api_payload_changed"] is False
    assert fallback_api_contract["scheduled_completion_proof_changed"] is False
    assert (
        fallback_api_contract["scheduled_evidence_controller"]
        == "scheduled_run_evidence"
    )
    assert "conservative unavailable/not-proof message" in fallback_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "missing or invalid reset telemetry metadata" in fallback_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "adds no API proof" in fallback_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "changes no API fields" in fallback_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "leaves API payload unchanged" in fallback_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "does not change scheduled_completion_proof" in (
        fallback_api_contract["scheduled_evidence_semantics"]
    )
    assert "writes no scheduled evidence" in fallback_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        fallback_api_contract["scheduled_evidence_semantics"]
    )
    assert "Batch 114" in dashboard_reset_telemetry_fallback_boundary_extension[
        "scheduled_evidence_boundary"
    ]
    assert "DashboardPage and DashboardPage.report_detail" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "reset telemetry metadata unavailable" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "fallback boundary: not scheduled_run_evidence proof" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "contract reuse claim is none_when_metadata_missing" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "writes no scheduled evidence" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "adds no API proof" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "changes no API fields" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "leaves API payload unchanged" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "does not change scheduled_completion_proof" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert (
        dashboard_reset_telemetry_fallback_boundary_extension["completion_claim"]
        == "dashboard_reset_telemetry_fallback_boundary_added_without_changing_scheduled_evidence"
    )
    assert "Dashboard reset telemetry fallback metadata boundary" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "completion_claim_boundary"
        ]
    )
    assert "scheduled_run_evidence proof" in (
        dashboard_reset_telemetry_fallback_boundary_extension[
            "completion_claim_boundary"
        ]
    )
    dashboard_report_export_reset_telemetry_context_extension = async_task_readback_extension[
        "dashboard_report_export_reset_telemetry_context_extension"
    ]
    assert dashboard_report_export_reset_telemetry_context_extension["batch"] == "115"
    assert (
        dashboard_report_export_reset_telemetry_context_extension["proof_level"]
        == "dashboard_report_export_reset_telemetry_context_extension"
    )
    report_export_context_contract = (
        dashboard_report_export_reset_telemetry_context_extension[
            "report_export_context_contract"
        ]
    )
    assert report_export_context_contract["consumer_surfaces"] == [
        "DashboardPage.report_from_filter_payload",
        "DashboardPage.report_export_pdf",
        "DashboardPage.report_export_docx",
    ]
    assert (
        report_export_context_contract["context_scope"]
        == "ui_read_only_evidence_context"
    )
    assert (
        report_export_context_contract["source_metadata_key"]
        == "scheduled_artifact_warning_empty_reset_telemetry_ui_extension"
    )
    assert report_export_context_contract["not_report_proof"] is True
    assert (
        report_export_context_contract["not_scheduled_run_evidence_proof"]
        is True
    )
    assert report_export_context_contract["scheduled_evidence_write"] == "none"
    assert (
        report_export_context_contract[
            "scheduled_completion_proof_behavior"
        ]
        == "unchanged"
    )
    assert "Dashboard report/export payload" in report_export_context_contract[
        "context_semantics"
    ]
    assert "ui_read_only_evidence_context" in report_export_context_contract[
        "context_semantics"
    ]
    assert "scheduled_artifact_warning_empty_reset_telemetry_ui_extension" in (
        report_export_context_contract["context_semantics"]
    )
    assert "not report proof" in report_export_context_contract[
        "context_semantics"
    ]
    assert "not scheduled_run_evidence proof" in report_export_context_contract[
        "context_semantics"
    ]
    assert "writes no scheduled evidence" in report_export_context_contract[
        "context_semantics"
    ]
    assert "does not change scheduled_completion_proof" in (
        report_export_context_contract["context_semantics"]
    )
    report_export_api_contract = dashboard_report_export_reset_telemetry_context_extension[
        "api_contract"
    ]
    assert (
        report_export_api_contract["route"]
        == "/api/v1/business-lines/evidence-matrix"
    )
    assert report_export_api_contract["proof_addition"] == "none"
    assert report_export_api_contract["api_proof_added"] is False
    assert report_export_api_contract["api_fields_changed"] is False
    assert report_export_api_contract["api_payload_changed"] is False
    assert (
        report_export_api_contract["scheduled_completion_proof_changed"]
        is False
    )
    assert (
        report_export_api_contract["scheduled_evidence_controller"]
        == "scheduled_run_evidence"
    )
    assert "UI/read-only evidence context only" in report_export_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "adds no API proof" in report_export_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "changes no API fields" in report_export_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "leaves API payload unchanged" in report_export_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "does not change scheduled_completion_proof" in (
        report_export_api_contract["scheduled_evidence_semantics"]
    )
    assert "writes no scheduled evidence" in report_export_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        report_export_api_contract["scheduled_evidence_semantics"]
    )
    assert "Batch 115" in dashboard_report_export_reset_telemetry_context_extension[
        "scheduled_evidence_boundary"
    ]
    assert "DashboardPage.report_from_filter_payload" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "DashboardPage.report_export_pdf" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "DashboardPage.report_export_docx" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "ui_read_only_evidence_context" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "scheduled_artifact_warning_empty_reset_telemetry_ui_extension" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "not report proof" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "not scheduled_run_evidence proof" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "writes no scheduled evidence" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "adds no API proof" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "changes no API fields" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "leaves API payload unchanged" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "does not change scheduled_completion_proof" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert (
        dashboard_report_export_reset_telemetry_context_extension["completion_claim"]
        == "dashboard_report_export_reset_telemetry_context_boundary_added_without_changing_scheduled_evidence"
    )
    assert "Dashboard report/export reset telemetry context metadata boundary" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "completion_claim_boundary"
        ]
    )
    assert "report proof" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "completion_claim_boundary"
        ]
    )
    assert "scheduled_run_evidence proof" in (
        dashboard_report_export_reset_telemetry_context_extension[
            "completion_claim_boundary"
        ]
    )
    dashboard_report_export_renderer_reset_telemetry_note_extension = async_task_readback_extension[
        "dashboard_report_export_renderer_reset_telemetry_note_extension"
    ]
    assert dashboard_report_export_renderer_reset_telemetry_note_extension["batch"] == "116"
    assert (
        dashboard_report_export_renderer_reset_telemetry_note_extension["proof_level"]
        == "dashboard_report_export_renderer_reset_telemetry_note_extension"
    )
    renderer_contract = dashboard_report_export_renderer_reset_telemetry_note_extension[
        "renderer_contract"
    ]
    assert renderer_contract["accepted_payload_field"] == "reset_telemetry_boundary_context"
    assert renderer_contract["renderer_surfaces"] == [
        "llm_report.export.pdf",
        "llm_report.export.docx",
    ]
    assert renderer_contract["render_scope"] == "boundary_note"
    assert renderer_contract["context_scope"] == "ui_read_only_evidence_context"
    assert renderer_contract["not_report_proof"] is True
    assert renderer_contract["not_quality_gate_input"] is True
    assert renderer_contract["not_scheduled_run_evidence_proof"] is True
    assert renderer_contract["scheduled_evidence_write"] == "none"
    assert (
        renderer_contract["scheduled_completion_proof_behavior"]
        == "unchanged"
    )
    assert renderer_contract["audit_outcome_behavior"] == "unchanged"
    assert "PDF/DOCX export renderers" in renderer_contract["renderer_semantics"]
    assert "reset_telemetry_boundary_context" in renderer_contract["renderer_semantics"]
    assert "boundary_note" in renderer_contract["renderer_semantics"]
    assert "not report proof" in renderer_contract["renderer_semantics"]
    assert "not quality gate input" in renderer_contract["renderer_semantics"]
    assert "not scheduled_run_evidence proof" in renderer_contract["renderer_semantics"]
    assert "writes no scheduled evidence" in renderer_contract["renderer_semantics"]
    assert "does not change scheduled_completion_proof" in renderer_contract[
        "renderer_semantics"
    ]
    assert "does not change export audit outcome" in renderer_contract[
        "renderer_semantics"
    ]
    renderer_api_contract = dashboard_report_export_renderer_reset_telemetry_note_extension[
        "api_contract"
    ]
    assert renderer_api_contract["route"] == "/api/v1/llm-report/export/{pdf|docx}"
    assert renderer_api_contract["proof_addition"] == "none"
    assert renderer_api_contract["api_proof_added"] is False
    assert renderer_api_contract["quality_gate_changed"] is False
    assert renderer_api_contract["audit_outcome_changed"] is False
    assert renderer_api_contract["scheduled_completion_proof_changed"] is False
    assert renderer_api_contract["scheduled_evidence_controller"] == "scheduled_run_evidence"
    assert "read-only boundary notes" in renderer_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "do not participate in quality gate decisions" in renderer_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "do not alter export audit outcome" in renderer_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "write no scheduled evidence" in renderer_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        renderer_api_contract["scheduled_evidence_semantics"]
    )
    assert "Batch 116" in dashboard_report_export_renderer_reset_telemetry_note_extension[
        "scheduled_evidence_boundary"
    ]
    assert "reset_telemetry_boundary_context" in (
        dashboard_report_export_renderer_reset_telemetry_note_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "boundary_note" in (
        dashboard_report_export_renderer_reset_telemetry_note_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "not quality gate input" in (
        dashboard_report_export_renderer_reset_telemetry_note_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "does not change export audit outcome" in (
        dashboard_report_export_renderer_reset_telemetry_note_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert (
        dashboard_report_export_renderer_reset_telemetry_note_extension["completion_claim"]
        == "dashboard_report_export_renderer_reset_telemetry_note_added_without_changing_proof_or_audit_outcome"
    )
    assert "PDF/DOCX renderer boundary note" in (
        dashboard_report_export_renderer_reset_telemetry_note_extension[
            "completion_claim_boundary"
        ]
    )
    assert "quality gate decisions" in (
        dashboard_report_export_renderer_reset_telemetry_note_extension[
            "completion_claim_boundary"
        ]
    )
    assert "export audit outcome" in (
        dashboard_report_export_renderer_reset_telemetry_note_extension[
            "completion_claim_boundary"
        ]
    )
    assert "scheduled_run_evidence proof" in (
        dashboard_report_export_renderer_reset_telemetry_note_extension[
            "completion_claim_boundary"
        ]
    )
    dashboard_report_export_audit_reset_telemetry_trace_extension = async_task_readback_extension[
        "dashboard_report_export_audit_reset_telemetry_trace_extension"
    ]
    assert dashboard_report_export_audit_reset_telemetry_trace_extension["batch"] == "117"
    assert (
        dashboard_report_export_audit_reset_telemetry_trace_extension["proof_level"]
        == "dashboard_report_export_audit_reset_telemetry_trace_extension"
    )
    audit_trace_contract = dashboard_report_export_audit_reset_telemetry_trace_extension[
        "audit_trace_contract"
    ]
    assert audit_trace_contract["event_fields"] == [
        "ui_read_only_context_included",
        "ui_read_only_context_scope",
        "ui_read_only_context_source",
    ]
    assert audit_trace_contract["source_payload_field"] == "reset_telemetry_boundary_context"
    assert audit_trace_contract["context_scope"] == "ui_read_only_evidence_context"
    assert (
        audit_trace_contract["trace_scope"]
        == "export_audit_read_only_context_trace"
    )
    assert audit_trace_contract["not_report_proof"] is True
    assert audit_trace_contract["not_quality_gate_input"] is True
    assert audit_trace_contract["not_scheduled_run_evidence_proof"] is True
    assert audit_trace_contract["scheduled_evidence_write"] == "none"
    assert (
        audit_trace_contract["scheduled_completion_proof_behavior"]
        == "unchanged"
    )
    assert audit_trace_contract["audit_outcome_behavior"] == "unchanged"
    assert "Export audit may record" in audit_trace_contract["trace_semantics"]
    assert "ui_read_only_context_included" in audit_trace_contract["trace_semantics"]
    assert "not report proof" in audit_trace_contract["trace_semantics"]
    assert "not quality gate input" in audit_trace_contract["trace_semantics"]
    assert "not scheduled_run_evidence proof" in audit_trace_contract[
        "trace_semantics"
    ]
    assert "writes no scheduled evidence" in audit_trace_contract["trace_semantics"]
    assert "does not change scheduled_completion_proof" in audit_trace_contract[
        "trace_semantics"
    ]
    assert "does not change export audit outcome" in audit_trace_contract[
        "trace_semantics"
    ]
    audit_trace_api_contract = dashboard_report_export_audit_reset_telemetry_trace_extension[
        "api_contract"
    ]
    assert audit_trace_api_contract["route"] == "/api/v1/llm-report/export/{pdf|docx}"
    assert audit_trace_api_contract["proof_addition"] == "none"
    assert audit_trace_api_contract["api_proof_added"] is False
    assert audit_trace_api_contract["quality_gate_changed"] is False
    assert audit_trace_api_contract["audit_outcome_changed"] is False
    assert audit_trace_api_contract["scheduled_completion_proof_changed"] is False
    assert audit_trace_api_contract["scheduled_evidence_controller"] == "scheduled_run_evidence"
    assert "read-only trace metadata" in audit_trace_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "do not participate in quality gate decisions" in audit_trace_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "do not alter export audit outcome" in audit_trace_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "write no scheduled evidence" in audit_trace_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "scheduled evidence remains controlled only by scheduled_run_evidence" in (
        audit_trace_api_contract["scheduled_evidence_semantics"]
    )
    assert "Batch 117" in dashboard_report_export_audit_reset_telemetry_trace_extension[
        "scheduled_evidence_boundary"
    ]
    assert "ui_read_only_context_included" in (
        dashboard_report_export_audit_reset_telemetry_trace_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "read-only trace metadata" in (
        dashboard_report_export_audit_reset_telemetry_trace_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "not quality gate input" in (
        dashboard_report_export_audit_reset_telemetry_trace_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert "does not change export audit outcome" in (
        dashboard_report_export_audit_reset_telemetry_trace_extension[
            "scheduled_evidence_boundary"
        ]
    )
    assert (
        dashboard_report_export_audit_reset_telemetry_trace_extension["completion_claim"]
        == "dashboard_report_export_audit_reset_telemetry_trace_added_without_changing_proof_gate_or_audit_outcome"
    )
    assert "export audit trace metadata" in (
        dashboard_report_export_audit_reset_telemetry_trace_extension[
            "completion_claim_boundary"
        ]
    )
    assert "quality gate decisions" in (
        dashboard_report_export_audit_reset_telemetry_trace_extension[
            "completion_claim_boundary"
        ]
    )
    assert "export audit outcome" in (
        dashboard_report_export_audit_reset_telemetry_trace_extension[
            "completion_claim_boundary"
        ]
    )
    assert "scheduled_run_evidence proof" in (
        dashboard_report_export_audit_reset_telemetry_trace_extension[
            "completion_claim_boundary"
        ]
    )
    dashboard_report_export_audit_summary_read_only_context_count_rollup = (
        async_task_readback_extension[
            "dashboard_report_export_audit_summary_read_only_context_count_rollup"
        ]
    )
    assert (
        dashboard_report_export_audit_summary_read_only_context_count_rollup["batch"]
        == "118"
    )
    assert (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "proof_level"
        ]
        == "dashboard_report_export_audit_summary_read_only_context_count_rollup"
    )
    summary_rollup_contract = (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "summary_rollup_contract"
        ]
    )
    assert (
        summary_rollup_contract["summary_field"]
        == "ui_read_only_context_included_count"
    )
    assert (
        summary_rollup_contract["summary_scope"]
        == "export_audit_read_only_context_summary_rollup"
    )
    assert (
        summary_rollup_contract["source_event_field"]
        == "ui_read_only_context_included"
    )
    assert summary_rollup_contract["source_scope_field"] == "ui_read_only_context_scope"
    assert summary_rollup_contract["not_report_proof"] is True
    assert summary_rollup_contract["not_quality_gate_input"] is True
    assert summary_rollup_contract["not_scheduled_run_evidence_proof"] is True
    assert summary_rollup_contract["scheduled_evidence_write"] == "none"
    assert (
        summary_rollup_contract["scheduled_completion_proof_behavior"]
        == "unchanged"
    )
    assert summary_rollup_contract["audit_outcome_behavior"] == "unchanged"
    assert "summary may expose ui_read_only_context_included_count" in (
        summary_rollup_contract["rollup_semantics"]
    )
    assert "not report proof" in summary_rollup_contract["rollup_semantics"]
    assert "not quality gate input" in summary_rollup_contract["rollup_semantics"]
    assert "not scheduled_run_evidence proof" in summary_rollup_contract[
        "rollup_semantics"
    ]
    assert "writes no scheduled evidence" in summary_rollup_contract[
        "rollup_semantics"
    ]
    assert "does not change export audit outcome" in summary_rollup_contract[
        "rollup_semantics"
    ]
    summary_rollup_api_contract = (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "api_contract"
        ]
    )
    assert summary_rollup_api_contract["route"] == "/api/v1/dashboard/stats"
    assert (
        summary_rollup_api_contract["summary_container"]
        == "llm_report_quality.summary.export_events"
    )
    assert summary_rollup_api_contract["proof_addition"] == "none"
    assert summary_rollup_api_contract["api_proof_added"] is False
    assert summary_rollup_api_contract["quality_gate_changed"] is False
    assert summary_rollup_api_contract["audit_outcome_changed"] is False
    assert summary_rollup_api_contract["scheduled_completion_proof_changed"] is False
    assert (
        summary_rollup_api_contract["scheduled_evidence_controller"]
        == "scheduled_run_evidence"
    )
    assert "summary rollup" in summary_rollup_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "does not participate in quality gate decisions" in (
        summary_rollup_api_contract["scheduled_evidence_semantics"]
    )
    assert "does not alter export audit outcome" in summary_rollup_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "writes no scheduled evidence" in summary_rollup_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "Batch 118" in (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "scheduled_evidence_boundary"
        ]
    )
    assert "ui_read_only_context_included_count" in (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "scheduled_evidence_boundary"
        ]
    )
    assert "not quality gate input" in (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "scheduled_evidence_boundary"
        ]
    )
    assert "does not change export audit outcome" in (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "scheduled_evidence_boundary"
        ]
    )
    assert (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "completion_claim"
        ]
        == "dashboard_report_export_audit_summary_read_only_context_count_added_without_changing_proof_gate_or_audit_outcome"
    )
    assert "summary rollup metadata" in (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "completion_claim_boundary"
        ]
    )
    assert "quality gate decisions" in (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "completion_claim_boundary"
        ]
    )
    assert "export audit outcome" in (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "completion_claim_boundary"
        ]
    )
    assert "scheduled_run_evidence proof" in (
        dashboard_report_export_audit_summary_read_only_context_count_rollup[
            "completion_claim_boundary"
        ]
    )
    llm_report_quality_trends_read_only_context_count_parity = (
        async_task_readback_extension[
            "llm_report_quality_trends_read_only_context_count_parity"
        ]
    )
    assert llm_report_quality_trends_read_only_context_count_parity["batch"] == "119"
    assert (
        llm_report_quality_trends_read_only_context_count_parity["proof_level"]
        == "llm_report_quality_trends_read_only_context_count_parity"
    )
    quality_trends_parity_contract = (
        llm_report_quality_trends_read_only_context_count_parity[
            "quality_trends_parity_contract"
        ]
    )
    assert (
        quality_trends_parity_contract["summary_field"]
        == "ui_read_only_context_included_count"
    )
    assert (
        quality_trends_parity_contract["source_summary_container"]
        == "llm_report_quality.summary.export_events"
    )
    assert (
        quality_trends_parity_contract["parity_container"]
        == "quality_trends.export_events"
    )
    assert quality_trends_parity_contract["not_report_proof"] is True
    assert quality_trends_parity_contract["not_quality_gate_input"] is True
    assert (
        quality_trends_parity_contract["not_scheduled_run_evidence_proof"]
        is True
    )
    assert quality_trends_parity_contract["scheduled_evidence_write"] == "none"
    assert (
        quality_trends_parity_contract["scheduled_completion_proof_behavior"]
        == "unchanged"
    )
    assert quality_trends_parity_contract["audit_outcome_behavior"] == "unchanged"
    assert "/api/v1/llm-report/quality-trends parity" in (
        quality_trends_parity_contract["parity_semantics"]
    )
    assert "not quality gate input" in (
        quality_trends_parity_contract["parity_semantics"]
    )
    assert "not scheduled_run_evidence proof" in (
        quality_trends_parity_contract["parity_semantics"]
    )
    assert "writes no scheduled evidence" in (
        quality_trends_parity_contract["parity_semantics"]
    )
    assert "does not change export audit outcome" in (
        quality_trends_parity_contract["parity_semantics"]
    )
    quality_trends_api_contract = (
        llm_report_quality_trends_read_only_context_count_parity["api_contract"]
    )
    assert (
        quality_trends_api_contract["route"]
        == "/api/v1/llm-report/quality-trends"
    )
    assert quality_trends_api_contract["proof_addition"] == "none"
    assert quality_trends_api_contract["api_proof_added"] is False
    assert quality_trends_api_contract["quality_gate_changed"] is False
    assert quality_trends_api_contract["audit_outcome_changed"] is False
    assert (
        quality_trends_api_contract["scheduled_completion_proof_changed"]
        is False
    )
    assert (
        quality_trends_api_contract["scheduled_evidence_controller"]
        == "scheduled_run_evidence"
    )
    assert "observability parity field" in (
        quality_trends_api_contract["scheduled_evidence_semantics"]
    )
    assert "does not participate in quality gate decisions" in (
        quality_trends_api_contract["scheduled_evidence_semantics"]
    )
    assert "does not alter export audit outcome" in (
        quality_trends_api_contract["scheduled_evidence_semantics"]
    )
    assert "writes no scheduled evidence" in (
        quality_trends_api_contract["scheduled_evidence_semantics"]
    )
    assert "Batch 119" in (
        llm_report_quality_trends_read_only_context_count_parity[
            "scheduled_evidence_boundary"
        ]
    )
    assert "/api/v1/llm-report/quality-trends parity" in (
        llm_report_quality_trends_read_only_context_count_parity[
            "scheduled_evidence_boundary"
        ]
    )
    assert "not quality gate input" in (
        llm_report_quality_trends_read_only_context_count_parity[
            "scheduled_evidence_boundary"
        ]
    )
    assert "does not change export audit outcome" in (
        llm_report_quality_trends_read_only_context_count_parity[
            "scheduled_evidence_boundary"
        ]
    )
    assert (
        llm_report_quality_trends_read_only_context_count_parity[
            "completion_claim"
        ]
        == "llm_report_quality_trends_read_only_context_count_parity_added_without_changing_proof_gate_or_audit_outcome"
    )
    assert "quality-trends parity" in (
        llm_report_quality_trends_read_only_context_count_parity[
            "completion_claim_boundary"
        ]
    )
    assert "quality gate decisions" in (
        llm_report_quality_trends_read_only_context_count_parity[
            "completion_claim_boundary"
        ]
    )
    assert "export audit outcome" in (
        llm_report_quality_trends_read_only_context_count_parity[
            "completion_claim_boundary"
        ]
    )
    assert "scheduled_run_evidence proof" in (
        llm_report_quality_trends_read_only_context_count_parity[
            "completion_claim_boundary"
        ]
    )
    dashboard_report_export_audit_table_header_i18n_copy = (
        async_task_readback_extension[
            "dashboard_report_export_audit_table_header_i18n_copy"
        ]
    )
    assert dashboard_report_export_audit_table_header_i18n_copy["batch"] == "119"
    assert (
        dashboard_report_export_audit_table_header_i18n_copy["proof_level"]
        == "dashboard_report_export_audit_table_header_i18n_copy"
    )
    audit_ui_copy_i18n_contract = (
        dashboard_report_export_audit_table_header_i18n_copy[
            "audit_ui_copy_i18n_contract"
        ]
    )
    assert (
        audit_ui_copy_i18n_contract["ui_surface"]
        == "Dashboard export audit table header"
    )
    assert (
        audit_ui_copy_i18n_contract["i18n_key"]
        == "dashboardPage.field.exportReadOnlyContextTrace"
    )
    assert (
        audit_ui_copy_i18n_contract["copy_scope"]
        == "export_audit_read_only_context_trace_header"
    )
    assert audit_ui_copy_i18n_contract["not_report_proof"] is True
    assert audit_ui_copy_i18n_contract["not_quality_gate_input"] is True
    assert audit_ui_copy_i18n_contract["not_scheduled_run_evidence_proof"] is True
    assert audit_ui_copy_i18n_contract["scheduled_evidence_write"] == "none"
    assert (
        audit_ui_copy_i18n_contract["scheduled_completion_proof_behavior"]
        == "unchanged"
    )
    assert audit_ui_copy_i18n_contract["audit_outcome_behavior"] == "unchanged"
    assert "table header i18n copy" in audit_ui_copy_i18n_contract[
        "copy_semantics"
    ]
    assert "not quality gate input" in audit_ui_copy_i18n_contract[
        "copy_semantics"
    ]
    assert "not scheduled_run_evidence proof" in audit_ui_copy_i18n_contract[
        "copy_semantics"
    ]
    assert "writes no scheduled evidence" in audit_ui_copy_i18n_contract[
        "copy_semantics"
    ]
    assert "does not change export audit outcome" in audit_ui_copy_i18n_contract[
        "copy_semantics"
    ]
    audit_ui_copy_api_contract = (
        dashboard_report_export_audit_table_header_i18n_copy["api_contract"]
    )
    assert audit_ui_copy_api_contract["route"] == "Dashboard UI surface: /dashboard"
    assert (
        audit_ui_copy_api_contract["ui_surface"]
        == "DashboardPage.exportAudit.table.header.readOnlyContextTrace"
    )
    assert audit_ui_copy_api_contract["proof_addition"] == "none"
    assert audit_ui_copy_api_contract["api_proof_added"] is False
    assert audit_ui_copy_api_contract["quality_gate_changed"] is False
    assert audit_ui_copy_api_contract["audit_outcome_changed"] is False
    assert (
        audit_ui_copy_api_contract["scheduled_completion_proof_changed"]
        is False
    )
    assert (
        audit_ui_copy_api_contract["scheduled_evidence_controller"]
        == "scheduled_run_evidence"
    )
    assert "UI copy only" in audit_ui_copy_api_contract[
        "scheduled_evidence_semantics"
    ]
    assert "does not participate in quality gate decisions" in (
        audit_ui_copy_api_contract["scheduled_evidence_semantics"]
    )
    assert "does not alter export audit outcome" in (
        audit_ui_copy_api_contract["scheduled_evidence_semantics"]
    )
    assert "writes no scheduled evidence" in (
        audit_ui_copy_api_contract["scheduled_evidence_semantics"]
    )
    assert "Batch 119" in (
        dashboard_report_export_audit_table_header_i18n_copy[
            "scheduled_evidence_boundary"
        ]
    )
    assert "Dashboard export audit table header i18n copy" in (
        dashboard_report_export_audit_table_header_i18n_copy[
            "scheduled_evidence_boundary"
        ]
    )
    assert "not quality gate input" in (
        dashboard_report_export_audit_table_header_i18n_copy[
            "scheduled_evidence_boundary"
        ]
    )
    assert "does not change export audit outcome" in (
        dashboard_report_export_audit_table_header_i18n_copy[
            "scheduled_evidence_boundary"
        ]
    )
    assert (
        dashboard_report_export_audit_table_header_i18n_copy["completion_claim"]
        == "dashboard_report_export_audit_table_header_i18n_copy_added_without_changing_proof_gate_or_audit_outcome"
    )
    assert "table header i18n copy" in (
        dashboard_report_export_audit_table_header_i18n_copy[
            "completion_claim_boundary"
        ]
    )
    assert "quality gate decisions" in (
        dashboard_report_export_audit_table_header_i18n_copy[
            "completion_claim_boundary"
        ]
    )
    assert "export audit outcome" in (
        dashboard_report_export_audit_table_header_i18n_copy[
            "completion_claim_boundary"
        ]
    )
    assert "scheduled_run_evidence proof" in (
        dashboard_report_export_audit_table_header_i18n_copy[
            "completion_claim_boundary"
        ]
    )
    dashboard_report_detail_export_read_only_context_summary = (
        async_task_readback_extension[
            "dashboard_report_detail_export_read_only_context_summary"
        ]
    )
    assert dashboard_report_detail_export_read_only_context_summary["batch"] == "119"
    assert (
        dashboard_report_detail_export_read_only_context_summary["proof_level"]
        == "dashboard_report_detail_export_read_only_context_summary"
    )
    report_detail_summary_contract = (
        dashboard_report_detail_export_read_only_context_summary[
            "report_detail_summary_contract"
        ]
    )
    assert report_detail_summary_contract["route"] == "/api/v1/dashboard/llm-report-detail"
    assert report_detail_summary_contract["summary_container"] == "export_audit.summary"
    assert report_detail_summary_contract["mirror_container"] == "export_events_summary"
    assert (
        report_detail_summary_contract["summary_field"]
        == "ui_read_only_context_included_count"
    )
    assert report_detail_summary_contract["source_event_field"] == "ui_read_only_context_included"
    assert report_detail_summary_contract["not_report_proof"] is True
    assert report_detail_summary_contract["not_quality_gate_input"] is True
    assert report_detail_summary_contract["not_scheduled_run_evidence_proof"] is True
    assert report_detail_summary_contract["scheduled_evidence_write"] == "none"
    assert (
        report_detail_summary_contract["scheduled_completion_proof_behavior"]
        == "unchanged"
    )
    assert report_detail_summary_contract["audit_outcome_behavior"] == "unchanged"
    assert "trace-level visibility only" in report_detail_summary_contract["summary_semantics"]
    assert "not quality gate input" in report_detail_summary_contract["summary_semantics"]
    assert "not scheduled_run_evidence proof" in report_detail_summary_contract["summary_semantics"]
    report_detail_api_contract = (
        dashboard_report_detail_export_read_only_context_summary["api_contract"]
    )
    assert report_detail_api_contract["route"] == "/api/v1/dashboard/llm-report-detail"
    assert report_detail_api_contract["proof_addition"] == "none"
    assert report_detail_api_contract["api_proof_added"] is False
    assert report_detail_api_contract["quality_gate_changed"] is False
    assert report_detail_api_contract["audit_outcome_changed"] is False
    assert report_detail_api_contract["scheduled_completion_proof_changed"] is False
    assert (
        report_detail_api_contract["scheduled_evidence_controller"]
        == "scheduled_run_evidence"
    )
    assert "trace-level observability only" in (
        report_detail_api_contract["scheduled_evidence_semantics"]
    )
    assert "writes no scheduled evidence" in (
        report_detail_api_contract["scheduled_evidence_semantics"]
    )
    assert "Batch 119" in (
        dashboard_report_detail_export_read_only_context_summary[
            "scheduled_evidence_boundary"
        ]
    )
    assert "ui_read_only_context_included_count" in (
        dashboard_report_detail_export_read_only_context_summary[
            "scheduled_evidence_boundary"
        ]
    )
    assert "report detail export read-only context summary" in (
        dashboard_report_detail_export_read_only_context_summary[
            "completion_claim_boundary"
        ]
    )
    assert "scheduled_run_evidence proof" in (
        dashboard_report_detail_export_read_only_context_summary[
            "completion_claim_boundary"
        ]
    )
    read_only_context_proof_boundary_compression = async_task_readback_extension[
        "read_only_context_proof_boundary_compression"
    ]
    assert read_only_context_proof_boundary_compression["batch"] == "120"
    assert (
        read_only_context_proof_boundary_compression["proof_level"]
        == "read_only_context_proof_boundary_compression"
    )
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
    shared_boundary_contract = read_only_context_proof_boundary_compression[
        "shared_boundary_contract"
    ]
    assert shared_boundary_contract["shared_helper"] == "_read_only_context_proof_boundary"
    assert shared_boundary_contract["shared_constant"] == "READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS"
    assert shared_boundary_contract["boundary_fields"] == READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS
    assert "freezes reset telemetry and read-only context follow-ups" in (
        shared_boundary_contract["boundary_semantics"]
    )
    assert "adds no export audit fields" in shared_boundary_contract["boundary_semantics"]
    assert "quality gate input" in shared_boundary_contract["boundary_semantics"]
    assert "scheduled_run_evidence" in shared_boundary_contract["boundary_semantics"]

    frozen_scope = read_only_context_proof_boundary_compression["frozen_scope"]
    for key, value in READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS.items():
        assert frozen_scope[key] == value
    assert (
        frozen_scope["reset_telemetry_followups"]
        == "frozen_unless_user_flow_blocking"
    )
    assert (
        frozen_scope["read_only_context_followups"]
        == "frozen_unless_user_flow_blocking"
    )
    assert (
        frozen_scope["remaining_polish"]
        == "deferred_polish_unless_active_user_flow_blocking"
    )
    assert frozen_scope["no_new_export_audit_fields"] is True
    assert frozen_scope["no_new_dashboard_copy_only_improvements"] is True

    compressed_api_contract = read_only_context_proof_boundary_compression[
        "api_contract"
    ]
    for key, value in READ_ONLY_CONTEXT_PROOF_BOUNDARY_FIELDS.items():
        assert compressed_api_contract[key] == value
    assert compressed_api_contract["proof_addition"] == "none"
    assert compressed_api_contract["api_proof_added"] is False
    assert compressed_api_contract["quality_gate_changed"] is False
    assert compressed_api_contract["audit_outcome_changed"] is False
    assert compressed_api_contract["scheduled_completion_proof_changed"] is False
    assert compressed_api_contract["scheduled_evidence_controller"] == "scheduled_run_evidence"
    assert "does not change scheduled checker behavior" in (
        compressed_api_contract["scheduled_evidence_semantics"]
    )
    assert "quality gate decisions" in compressed_api_contract["scheduled_evidence_semantics"]
    assert "scheduled_run_evidence requirement" in (
        compressed_api_contract["scheduled_evidence_semantics"]
    )
    assert "Batch 120" in read_only_context_proof_boundary_compression[
        "scheduled_evidence_boundary"
    ]
    assert "frozen unless user-flow blocking" in read_only_context_proof_boundary_compression[
        "scheduled_evidence_boundary"
    ]
    assert "does not add export audit fields" in (
        read_only_context_proof_boundary_compression["scheduled_evidence_boundary"]
    )
    assert "does not add Dashboard copy-only improvements" in (
        read_only_context_proof_boundary_compression["scheduled_evidence_boundary"]
    )
    assert "does not change export audit outcome" in (
        read_only_context_proof_boundary_compression["scheduled_evidence_boundary"]
    )
    assert (
        read_only_context_proof_boundary_compression["completion_claim"]
        == "read_only_context_proof_boundary_compression_added_without_behavior_or_proof_change"
    )
    assert "shared proof-boundary vocabulary" in (
        read_only_context_proof_boundary_compression["completion_claim_boundary"]
    )
    assert "quality gate decisions" in (
        read_only_context_proof_boundary_compression["completion_claim_boundary"]
    )
    assert "scheduled checker behavior" in (
        read_only_context_proof_boundary_compression["completion_claim_boundary"]
    )
    assert "scheduled_run_evidence proof" in (
        read_only_context_proof_boundary_compression["completion_claim_boundary"]
    )

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
        assert response_assertions["required_data_paths"], (
            f"{line['line_key']} missing non-empty live_smoke.response_assertions.required_data_paths"
        )
        assert response_assertions["semantic_fields"], (
            f"{line['line_key']} missing non-empty live_smoke.response_assertions.semantic_fields"
        )
        assert response_assertions["failure_classification"], (
            f"{line['line_key']} missing non-empty live_smoke.response_assertions.failure_classification"
        )
        assert all(isinstance(path, str) and path for path in response_assertions["required_data_paths"])
        assert all(isinstance(field, str) and field for field in response_assertions["semantic_fields"])

        trace_baseline = line["trace_baseline"]
        assert REQUIRED_TRACE_BASELINE_FIELDS.issubset(trace_baseline.keys())
        for field in REQUIRED_TRACE_BASELINE_FIELDS - {"body_meta_trace"}:
            assert trace_baseline[field], (
                f"{line['line_key']} missing non-empty trace_baseline.{field}"
            )
        assert trace_baseline["contract_version"] == TRACE_BASELINE_CONTRACT_VERSION
        assert trace_baseline["proof_level"] == "live_backend_trace_baseline_contract"
        assert trace_baseline["runner_script"] == TRACE_BASELINE_RUNNER_SCRIPT
        assert trace_baseline["recommended_command"] == TRACE_BASELINE_RECOMMENDED_COMMAND
        assert TRACE_BASELINE_RUNNER_SCRIPT in trace_baseline["recommended_command"]
        assert "--base-url http://127.0.0.1:8000" in trace_baseline["recommended_command"]
        assert "--trace-prefix business-line-trace" in trace_baseline["recommended_command"]
        assert (
            f"--slow-threshold-ms {TRACE_BASELINE_DEFAULT_SLOW_THRESHOLD_MS}"
            in trace_baseline["recommended_command"]
        )
        assert trace_baseline["probe_path"] == live_smoke["probe_path"]

        request_headers = trace_baseline["request_headers"]
        assert request_headers["x_trace_id"] == "required"
        assert request_headers["x_request_id"] == "required"
        assert "runner generated per line trace id" in request_headers["value_source"]

        response_headers = trace_baseline["response_headers"]
        assert response_headers["required"] == ["x-trace-id", "x-request-id"]
        assert "must equal the request trace id" in response_headers["propagation_rule"]

        body_meta_trace = trace_baseline["body_meta_trace"]
        assert body_meta_trace["field"] == "meta.trace_id"
        assert body_meta_trace["required"] is expected_envelope_required
        if expected_envelope_required:
            assert body_meta_trace["exempt_probe_paths"] == []
            assert body_meta_trace["exemption_reason"] is None
        else:
            assert line["line_key"] == "runtime_ops"
            assert live_smoke["probe_path"] in TRACE_BASELINE_BODY_TRACE_EXEMPT_PROBE_PATHS
            assert body_meta_trace["exempt_probe_paths"] == TRACE_BASELINE_BODY_TRACE_EXEMPT_PROBE_PATHS
            assert "health/deep returns a non-envelope runtime payload" in body_meta_trace[
                "exemption_reason"
            ]

        duration_evidence = trace_baseline["duration_evidence"]
        assert duration_evidence["required"] is True
        assert duration_evidence["default_slow_threshold_ms"] == (
            TRACE_BASELINE_DEFAULT_SLOW_THRESHOLD_MS
        )
        assert {
            "matrix.duration_ms",
            "lines[].duration_ms",
            "lines[].slow_request",
            "lines[].slow_threshold_ms",
            "summary.slow_request_count",
        }.issubset(duration_evidence["required_artifact_fields"])

        trace_failure_classification = trace_baseline["failure_classification"]
        assert trace_failure_classification["endpoint_unreachable"] == "blocked_by_environment"
        assert trace_failure_classification["header_trace_id"] == "trace_propagation_failed"
        assert trace_failure_classification["header_request_id"] == "trace_propagation_failed"
        assert trace_failure_classification["body_meta_trace_id"] == "trace_envelope_meta_failed"
        assert trace_failure_classification["slow_request"] == "trace_latency_observation"
        assert trace_baseline["completion_claim"] == (
            "does_not_claim_production_or_scheduler_completion"
        )

        real_backend_browser_smoke = line["real_backend_browser_smoke"]
        assert REQUIRED_REAL_BACKEND_BROWSER_SMOKE_FIELDS.issubset(real_backend_browser_smoke.keys())
        for field in REQUIRED_REAL_BACKEND_BROWSER_SMOKE_FIELDS:
            assert real_backend_browser_smoke[field], (
                f"{line['line_key']} missing non-empty real_backend_browser_smoke.{field}"
            )
        assert real_backend_browser_smoke["proof_level"] == "real_backend_browser_smoke_plan"
        assert real_backend_browser_smoke["test_file"] == REAL_BACKEND_BROWSER_SMOKE_TEST_FILE
        assert real_backend_browser_smoke["route_path"].startswith("/#/")
        assert "requireRealBackendReadiness" in real_backend_browser_smoke["readiness_gate"]
        assert "blocked_by_environment" in real_backend_browser_smoke["blocked_semantics"]
        assert "Mocked rails are not real proof" in real_backend_browser_smoke["blocked_semantics"]
        assert "does not claim production, Docker, Celery, or scheduler completion" in real_backend_browser_smoke[
            "blocked_semantics"
        ]
        assert all(
            isinstance(assertion, str) and assertion
            for assertion in real_backend_browser_smoke["browser_assertions"]
        )

        if line["line_key"] == "writing_knowledge_graph_agent":
            combined = " ".join(
                [
                    real_backend_browser_smoke["route_path"],
                    real_backend_browser_smoke["readiness_gate"],
                    *real_backend_browser_smoke["browser_assertions"],
                ]
            )
            assert any(keyword in combined for keyword in ["writing", "graph", "agent"])

        async_execution_readiness = line["async_execution_readiness"]
        assert REQUIRED_ASYNC_EXECUTION_READINESS_FIELDS.issubset(async_execution_readiness.keys())
        for field in REQUIRED_ASYNC_EXECUTION_READINESS_FIELDS - {"requires_worker"}:
            assert async_execution_readiness[field], (
                f"{line['line_key']} missing non-empty async_execution_readiness.{field}"
            )
        assert isinstance(async_execution_readiness["requires_worker"], bool)
        assert async_execution_readiness["proof_level"] == "async_worker_readiness_plan"
        assert async_execution_readiness["process_stats_probe"] == PROCESS_STATS_PROBE_PATH
        assert "celery_worker_unavailable" in async_execution_readiness["blocked_semantics"]
        assert "does not prove worker/async passed" in async_execution_readiness["blocked_semantics"]
        assert "does not claim Celery worker" in async_execution_readiness["blocked_semantics"]
        assert all(
            isinstance(surface, str) and surface for surface in async_execution_readiness["async_surfaces"]
        )
        assert async_execution_readiness["verification_artifact"].startswith(
            "business_line_async_worker_readiness."
        )

        assert (
            async_execution_readiness["requires_worker"]
            is ASYNC_TASK_READBACK_REQUIRES_WORKER[line["line_key"]]
        )

        if line["line_key"] == "runtime_ops":
            runtime_semantics = " ".join(
                [
                    *async_execution_readiness["async_surfaces"],
                    async_execution_readiness["blocked_semantics"],
                    async_execution_readiness["process_stats_probe"],
                ]
            )
            assert "process stats" in runtime_semantics
            assert "worker readiness" in runtime_semantics

        async_task_readback = line["async_task_readback"]
        assert REQUIRED_ASYNC_TASK_READBACK_FIELDS.issubset(async_task_readback.keys())
        for field in REQUIRED_ASYNC_TASK_READBACK_FIELDS - {"requires_worker_readback"}:
            assert async_task_readback[field], (
                f"{line['line_key']} missing non-empty async_task_readback.{field}"
            )
        assert isinstance(async_task_readback["requires_worker_readback"], bool)
        assert async_task_readback["proof_level"] == "async_task_readback_contract"
        assert (
            async_task_readback["requires_worker_readback"]
            is ASYNC_TASK_READBACK_REQUIRES_WORKER[line["line_key"]]
        )
        assert async_task_readback["readback_artifact"].startswith("business_line_async_task_readback.")
        assert all(isinstance(path, str) and path for path in async_task_readback["readback_paths"])
        assert all(isinstance(event, str) and event for event in async_task_readback["required_events"])
        assert all(isinstance(state, str) and state for state in async_task_readback["terminal_states"])
        assert "blocked_by_environment" in async_task_readback["blocked_semantics"]
        assert "not passed" in async_task_readback["blocked_semantics"]
        assert any(
            state in async_task_readback["terminal_states"]
            for state in ["completed", "applied", "available", "healthy"]
        )

        if async_task_readback["requires_worker_readback"]:
            blocked_semantics = async_task_readback["blocked_semantics"].lower()
            assert "worker" in blocked_semantics
            assert "task" in blocked_semantics
            assert "async_task_readback_missing" in async_task_readback["blocked_semantics"]
            assert "worker_started" in async_task_readback["required_events"]
        else:
            assert "does not require" in async_task_readback["blocked_semantics"]
            assert "process_config_audit_readback_missing" in async_task_readback["blocked_semantics"]
            non_worker_semantics = " ".join(
                [
                    *async_task_readback["readback_paths"],
                    *async_task_readback["required_events"],
                    async_task_readback["blocked_semantics"],
                ]
            )
            assert any(keyword in non_worker_semantics for keyword in ["process", "config", "audit", "diagnostic"])
