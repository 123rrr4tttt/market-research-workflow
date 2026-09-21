"""W07 ops-surface failure-family and narrow boundary witnesses."""

from __future__ import annotations

from pathlib import Path

import pytest
from functorial_kit import Failure
from functorial_kit.arch.gates import scan_project

from app.successor_runtime.ops_domain.base import ops_surface_failure, normalized_text
from app.successor_runtime.ops_domain.dashboard_admin_surface import (
    DashboardAdminReadbackRow,
)
from app.successor_runtime.ops_domain.health_matrix_surface import ProbeObservation
from app.successor_runtime.ops_domain.ops_misc_surface import OpsMiscGroupDecision
from app.successor_runtime.ops_domain.projects_config_surface import (
    ProjectConfigReadbackRow,
)
from app.successor_runtime.ops_domain.runtime_ops_surface import RuntimeOpsReadbackRow


REPO_ROOT = Path(__file__).resolve().parents[4]


def test_INVARIANT__ops_surface_failure_factory_is_closed() -> None:
    failure = ops_surface_failure(
        "NORMALIZED_TEXT_INVALID",
        "row_id must be a string",
        site="test_w07_ops_surface",
        field="row_id",
    )
    assert isinstance(failure, Failure)
    assert failure.family == "successor.ops_surface.failure"
    assert failure.code == "NORMALIZED_TEXT_INVALID"
    assert failure.context == {
        "owner": "successor_runtime.ops_domain",
        "site": "test_w07_ops_surface",
        "failure_family": "successor.ops_surface.failure",
        "witness": "test:test_w07_ops_surface_failure_family",
        "field": "row_id",
    }


def test_INVARIANT__ops_surface_programmer_defect_boundaries_preserve_abi() -> None:
    with pytest.raises(TypeError, match="row_id must be a string"):
        normalized_text(1, "row_id")
    with pytest.raises(ValueError, match="unknown read_kind"):
        DashboardAdminReadbackRow(row_id="x", read_kind="invalid", surface_key="s")
    with pytest.raises(ValueError, match="unknown probe_kind"):
        ProbeObservation(check_id="x", probe_kind="invalid")
    with pytest.raises(ValueError, match="unknown group"):
        OpsMiscGroupDecision(
            group="invalid",
            disposition="EXPLICITLY_REJECTED",
            decision_owner="owner",
            reason_code="reason",
            surface_id="surface",
        )
    with pytest.raises(ValueError, match="unknown read_kind"):
        ProjectConfigReadbackRow(
            row_id="x",
            project_key="p",
            read_kind="invalid",
        )
    with pytest.raises(ValueError, match="unknown read_kind"):
        RuntimeOpsReadbackRow(row_id="x", read_kind="invalid", probe_name="probe")


def test_w07_ops_surface_programmer_defect_boundaries() -> None:
    """Boundary metadata witness for the retained ops-surface defect ABI."""

    test_INVARIANT__ops_surface_programmer_defect_boundaries_preserve_abi()


def test_INVARIANT__ops_surface_scan_has_no_unclassified_throws() -> None:
    scan = scan_project(REPO_ROOT)
    violations = [
        violation
        for violation in scan.violations
        if violation.gate == "no-throw-in-core"
        and violation.file.startswith("main/backend/app/successor_runtime/ops_domain/")
    ]
    assert violations == []
