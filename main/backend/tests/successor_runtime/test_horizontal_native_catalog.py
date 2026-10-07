"""The native family catalog is the assembly's authoritative source."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect

from app.successor_runtime.assembly.successor_assembly import (
    ALL_I1_CELLS,
    assemble_successor_runtime,
)
from app.successor_runtime.assembly.knowledge_assembly import (
    ASSEMBLY_CELL_IDS as KNOWLEDGE_CELL_IDS,
)
from app.successor_runtime.assembly.material_ingest_assembly import (
    ASSEMBLY_CELL_IDS as MATERIAL_CELL_IDS,
)
from app.successor_runtime.capabilities.batch_task_native_contribution import (
    ASSEMBLY_CELL_IDS as BATCH_CELL_IDS,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    ASSEMBLY_CELL_IDS as SOURCE_CELL_IDS,
)
from app.successor_runtime.capabilities.workflow_native_contribution import (
    ASSEMBLY_CELL_IDS as WORKFLOW_CELL_IDS,
)
from app.successor_runtime.runtime.projection_native_contribution import (
    ASSEMBLY_CELL_IDS as PROJECTION_CELL_IDS,
)
from app.successor_runtime.runtime.task_observation_native_contribution import (
    ASSEMBLY_CELL_IDS as TASK_CELL_IDS,
)

pytestmark = pytest.mark.unit


def test_authoritative_native_families_define_exact_assembly_coverage() -> None:
    declared = frozenset(
        (
            *WORKFLOW_CELL_IDS,
            *SOURCE_CELL_IDS,
            *BATCH_CELL_IDS,
            *TASK_CELL_IDS,
            *MATERIAL_CELL_IDS,
            *KNOWLEDGE_CELL_IDS,
            *PROJECTION_CELL_IDS,
        )
    )
    assert declared == ALL_I1_CELLS


def test_assembly_construction_is_inert_until_explicit_runtime_execution() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    assembly = assemble_successor_runtime(engine=engine)

    assert assembly.cells
    assert inspect(engine).get_table_names() == []
