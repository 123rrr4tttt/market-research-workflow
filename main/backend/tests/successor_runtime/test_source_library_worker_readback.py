"""Focused tests for source-library worker readback."""

from __future__ import annotations

import pytest
from app.successor_runtime.capabilities.source_library_worker_readback import (
    SourceLibraryWorkerObservation,
    project_source_library_matrix_row,
    project_source_library_worker_readback,
)
from app.successor_runtime.capabilities.source_library_worker_readback import (
    authority_ceiling as worker_authority_ceiling,
)

pytestmark = pytest.mark.unit


def _worker_row(
    item_key: str = "item:001",
    guard: str = "admitted",
    phase: str = "provider_dispatch_boundary",
) -> SourceLibraryWorkerObservation:
    return SourceLibraryWorkerObservation(
        item_key=item_key,
        plan_mode="runner",
        phase=phase,
        guard_decision=guard,
        observed_at="2026-09-02T18:00:00+00:00",
    )


def test_source_library_admitted_boundary_consumes_fact_but_never_dispatches() -> None:
    readback = project_source_library_worker_readback((_worker_row(),))
    assert readback.admitted_count == 1
    assert readback.execution_fact_consumed is True
    assert readback.provider_dispatch_count == 0
    assert readback.authority == worker_authority_ceiling()
    row = project_source_library_matrix_row(readback)
    assert row["line_key"] == "resource_source_library"
    assert row["status"] == "passed"


def test_source_library_rejected_or_missing_fails_closed() -> None:
    rejected = project_source_library_worker_readback(
        (_worker_row(guard="rejected", item_key="item:002"),)
    )
    assert rejected.rejected_or_missing_count == 1
    assert rejected.line_guard_fail_closed is True
    assert rejected.execution_fact_consumed is False
    assert rejected.provider_dispatch_count == 0
    assert project_source_library_matrix_row(rejected)["status"] == "blocked"

    missing = project_source_library_worker_readback(
        (_worker_row(guard="missing", item_key="item:003"),)
    )
    assert missing.rejected_or_missing_count == 1
    assert project_source_library_matrix_row(missing)["status"] == "blocked"
