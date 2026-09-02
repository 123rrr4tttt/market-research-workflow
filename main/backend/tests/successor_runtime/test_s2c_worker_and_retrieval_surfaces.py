"""Focused tests for search panel and source-library worker readback."""

from __future__ import annotations

import pytest

from app.successor_runtime.capabilities.c9_2_search_retrieval_panel import (
    DECLARED_LOSS,
    SearchRetrievalRunObservation,
    project_search_retrieval_panel,
)
from app.successor_runtime.capabilities.c9_2_search_retrieval_panel import (
    authority_ceiling as panel_authority_ceiling,
)
from app.successor_runtime.capabilities.source_library_worker_readback import (
    SourceLibraryWorkerObservation,
    project_source_library_matrix_row,
    project_source_library_worker_readback,
)
from app.successor_runtime.capabilities.source_library_worker_readback import (
    authority_ceiling as worker_authority_ceiling,
)

pytestmark = pytest.mark.unit


def _search_row(
    run_id: str = "run:001",
    state: str = "terminal",
    freshness: str = "fresh",
) -> SearchRetrievalRunObservation:
    return SearchRetrievalRunObservation(
        retrieval_run_id=run_id,
        search_kind="discovery",
        run_state=state,
        index_freshness=freshness,
        observed_at="2026-09-02T18:00:00+00:00",
    )


def test_search_panel_empty_is_no_panel_and_readiness_is_not_faked() -> None:
    payload = project_search_retrieval_panel(())
    assert payload.panel_status == "NO_PANEL"
    assert payload.no_fake_panel_success is True
    assert payload.authority == panel_authority_ceiling()
    assert "dashboard-search-retrieval-run-panel-ui-byte-loss" in DECLARED_LOSS


def test_search_panel_undecidable_blocks_ready_status() -> None:
    payload = project_search_retrieval_panel(
        (
            _search_row(state="terminal"),
            _search_row(run_id="run:002", state="undecidable"),
        )
    )
    assert payload.panel_status == "BLOCKED"


def test_search_panel_terminal_fresh_is_ready() -> None:
    payload = project_search_retrieval_panel(
        (
            _search_row(run_id="run:001"),
            _search_row(run_id="run:002"),
        )
    )
    assert payload.panel_status == "READY"
    assert "search-index-write-no-call" in payload.declared_loss


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
