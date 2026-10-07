"""Closed offline assembly witness over the actual typed family builders."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.successor_runtime.assembly.successor_assembly import (
    ALL_I1_CELLS,
    assemble_successor_runtime,
    build_local_offline_fixture_options,
)

pytestmark = pytest.mark.unit


def test_offline_assembly_closes_actual_cells_without_executing_handlers() -> None:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:", future=True),
        options=build_local_offline_fixture_options(),
    )

    assert {cell.cell_id for cell in assembly.cells} == ALL_I1_CELLS
    assert all(cell.status == "INSTALLED" for cell in assembly.cells)
    assert all(
        getattr(handler, "execute_calls", 0) == 0
        for handler in (*assembly.handlers, *assembly.recovery_handlers)
    )


def test_offline_projector_registry_uses_run_bound_source_identities() -> None:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:", future=True),
        options=build_local_offline_fixture_options(),
    )

    assert assembly.projector_registry.projectors
    assert all(
        projector.key.source_ref.startswith("run:local-assembly:")
        and projector.key.source_incarnation.startswith(
            "incarnation:local-assembly:"
        )
        for projector in assembly.projector_registry.projectors
    )
