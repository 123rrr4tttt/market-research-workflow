"""Typed family ownership witnesses for the current successor assembly."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.successor_runtime.assembly.successor_assembly import (
    assemble_successor_runtime,
)
from app.successor_runtime.capabilities.batch_task_native_contribution import (
    ASSEMBLY_CELL_IDS as BATCH_CELL_IDS,
    DEFAULT_BATCH_TASK_NATIVE_SOURCE,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    ASSEMBLY_CELL_IDS as SOURCE_CELL_IDS,
    DEFAULT_SOURCE_NATIVE_SOURCE,
)
from app.successor_runtime.runtime.projection_native_contribution import (
    ASSEMBLY_CELL_IDS as PROJECTION_CELL_IDS,
    DEFAULT_PROJECTION_NATIVE_SOURCE,
)
from app.successor_runtime.runtime.task_observation_native_contribution import (
    ASSEMBLY_CELL_IDS as TASK_CELL_IDS,
    DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
)

pytestmark = pytest.mark.unit


def test_family_assembly_uses_authoritative_native_cell_declarations() -> None:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:", future=True)
    )
    cells_by_family = {
        family.family_id: tuple(cell.cell_id for cell in family.cells)
        for family in assembly.families
    }

    assert cells_by_family["mrw.source"] == SOURCE_CELL_IDS
    assert cells_by_family["batch.task"] == BATCH_CELL_IDS
    assert cells_by_family["task.observation.v1"] == TASK_CELL_IDS
    assert cells_by_family["mrw.projection"] == PROJECTION_CELL_IDS


def test_native_family_owners_remain_domain_owned() -> None:
    assert DEFAULT_SOURCE_NATIVE_SOURCE.owner == "source.acquire.v2"
    assert DEFAULT_BATCH_TASK_NATIVE_SOURCE.owner == "batch.task.v2"
    assert DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.owner == "task.observation.v2"
    assert DEFAULT_PROJECTION_NATIVE_SOURCE.owner == "projection.material-closure.v2"
