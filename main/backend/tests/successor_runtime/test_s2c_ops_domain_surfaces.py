"""Focused tests for the S2c ops-domain typed surfaces."""

from __future__ import annotations

import pytest

from app.successor_runtime.ops_domain.base import authority_ceiling
from app.successor_runtime.ops_domain.dashboard_admin_surface import (
    DashboardAdminReadbackRow,
    project_dashboard_admin_surface,
)
from app.successor_runtime.ops_domain.health_matrix_surface import (
    ProbeObservation,
    project_runtime_health_matrix,
)
from app.successor_runtime.ops_domain.ops_misc_surface import (
    GROUP_COVERAGE,
    OpsMiscGroupDecision,
    project_ops_misc_surface,
)
from app.successor_runtime.ops_domain.projects_config_surface import (
    DEFAULT_NO_CALL_DECISIONS,
    ProjectConfigReadbackRow,
    project_projects_config_surface,
)
from app.successor_runtime.ops_domain.runtime_ops_surface import (
    RuntimeOpsReadbackRow,
    project_runtime_ops_surface,
)

pytestmark = pytest.mark.unit


def test_ops_domain_authority_ceiling_is_all_false() -> None:
    plain = authority_ceiling()
    assert set(plain) == {
        "canonical_write",
        "live_provider",
        "external_delivery",
        "cutover",
        "authority_transfer",
        "scheduler",
        "executor",
        "credential_read",
    }
    assert all(value is False for value in plain.values())


def test_projects_config_surface_records_readback_and_explicit_no_call() -> None:
    manifest = project_projects_config_surface(
        readback_rows=(
            ProjectConfigReadbackRow(
                row_id="pc:001",
                project_key="demo",
                read_kind="project_readback",
                source_refs=("main/backend/app/api/projects.py",),
            ),
        ),
        no_call_decisions=DEFAULT_NO_CALL_DECISIONS,
    )
    assert manifest.schema.startswith("mrw.successor.ops-domain.")
    assert manifest.movement_ids == ("ALL-SM-005",)
    assert manifest.authority == authority_ceiling()
    assert len(manifest.readback_rows) == 1
    assert manifest.no_call_decisions
    assert all(
        decision.decision_owner
        and decision.disposition
        in (
            "EXPLICITLY_REJECTED",
            "DECLARED_LOSS",
        )
        for decision in manifest.no_call_decisions
    )


def test_dashboard_surface_always_carries_report_closure_decision() -> None:
    manifest = project_dashboard_admin_surface(
        readback_rows=(
            DashboardAdminReadbackRow(
                row_id="dash:001",
                read_kind="dashboard_read_projection",
                surface_key="business_lines",
            ),
        )
    )
    ids = {decision.decision_id for decision in manifest.no_call_decisions}
    assert "ALL-SM-006.report-from-filter-synthesis.explicitly-rejected.v1" in ids
    report = next(
        decision
        for decision in manifest.no_call_decisions
        if decision.decision_id.endswith(
            "report-from-filter-synthesis.explicitly-rejected.v1"
        )
    )
    assert report.disposition == "EXPLICITLY_REJECTED"
    assert report.decision_owner
    assert manifest.authority == authority_ceiling()


def test_runtime_ops_surface_defaults_never_execute_control_actions() -> None:
    manifest = project_runtime_ops_surface(
        readback_rows=(
            RuntimeOpsReadbackRow(
                row_id="ops:001",
                read_kind="app_health",
                probe_name="health",
                status="passed",
            ),
        )
    )
    action_kinds = {decision.action_kind for decision in manifest.no_call_decisions}
    assert {
        "process_retry",
        "process_cancel",
        "real_health_probe_execution",
        "service_start_stop",
    } <= action_kinds
    assert all(
        decision.disposition == "EXPLICITLY_REJECTED"
        for decision in manifest.no_call_decisions
    )
    assert manifest.authority == authority_ceiling()


def test_health_matrix_classification_is_passive_and_status_taxonomy() -> None:
    passed = project_runtime_health_matrix(
        "docker",
        (ProbeObservation(check_id="api", probe_kind="endpoint", status="passed"),),
    )
    assert passed.overall_status == "passed"
    assert passed.nominal_exit_code == 0
    assert passed.no_probe_execution is True

    degraded = project_runtime_health_matrix(
        "local",
        (
            ProbeObservation(check_id="api", probe_kind="endpoint", status="passed"),
            ProbeObservation(check_id="pg", probe_kind="dependency", status="degraded"),
        ),
    )
    assert degraded.overall_status == "degraded"
    assert degraded.nominal_exit_code == 1

    blocked = project_runtime_health_matrix(
        "mixed",
        (ProbeObservation(check_id="pg", probe_kind="dependency", status="blocked"),),
    )
    assert blocked.overall_status == "blocked"
    assert blocked.nominal_exit_code == 3

    unknown = project_runtime_health_matrix("not_run", ())
    assert unknown.overall_status == "unknown"
    assert unknown.nominal_exit_code == 3
    assert unknown.no_probe_execution is True


def test_ops_misc_surface_covers_all_nine_groups_and_accepts_override() -> None:
    complete = project_ops_misc_surface()
    assert {decision.group for decision in complete.group_decisions} == set(
        GROUP_COVERAGE
    )
    assert len(complete.group_decisions) == 9
    assert all(decision.decision_owner for decision in complete.group_decisions)

    custom = OpsMiscGroupDecision(
        group="stats",
        disposition="EXPLICITLY_REJECTED",
        decision_owner="test owner",
        reason_code="TEST_NO_CALL",
        surface_id="ops-misc.stats.explicitly-rejected.v1",
    )
    overridden = project_ops_misc_surface((custom,))
    stats = next(
        decision for decision in overridden.group_decisions if decision.group == "stats"
    )
    assert stats.disposition == "EXPLICITLY_REJECTED"


def test_surface_manifests_are_deterministic_json_readbacks() -> None:
    first = project_ops_misc_surface()
    second = project_ops_misc_surface()
    assert first.to_plain() == second.to_plain()
    assert first.digest() == second.digest()
