"""I1 rollback rehearsal evidence: per-cell bindings and C7 pure routes.

This non-PostgreSQL harness records each cell's rollback binding status from
the frozen capability specs plus the closed local-only serial assembly.
C7.1-C7.4 are installed as pure rollback-route handlers when their route
closures are supplied; the same cells stay ``DECLARED_GAP`` in the default
fail-closed assembly.  Durable journal/authority epoch rehearsal remains a
PostgreSQL opt-in surface.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, TypeGuard

import pytest
from app.successor_runtime.assembly.material_ingest_assembly import (
    ASSEMBLY_CELL_IDS as MATERIAL_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.assembly.successor_assembly import (
    ALL_I1_CELLS,
    assemble_successor_runtime,
    build_local_offline_fixture_options,
)
from app.successor_runtime.specification import CapabilityCellSpec
from sqlalchemy import create_engine
from tests.successor_runtime.historical_fixture import historical_bytes
from tests.successor_runtime.i1_binding_candidate_support import (
    REPOSITORY_ROOT,
)

TOPIC = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
SPECS_DIR = REPOSITORY_ROOT / TOPIC / "evidence/capability-specs"
RETIRED_FROZEN_CELL_IDS = frozenset({"C6.1", "C6.2", "C6.3"})
RETIRED_CURRENT_CELL_IDS = frozenset(
    {
        "acquisition.batch.execute_element.v2",
        "acquisition.batch.fold_ordered_results.v2",
    }
)
CURRENT_I1_CELL_ORDER = (
    "workflow.definition.compile.v2",
    "workflow.runtime.observe.v2",
    "workflow.state.restore.v2",
    "source.resolve-execution-request.v2",
    "source.plan-source-mode.v2",
    "source.execute-provider-acquisition.v2",
    "source.project-terminal-result.v2",
    "batch.task.build_plan.v2",
    "batch.task.reduce_retry.v2",
    "batch.task.submit.v2",
    "task.session-observation.project.v1",
    "runtime.effect.reconcile.v1",
    "runtime.event.project.v1",
    "process.observation.project.v1",
    "material.ingest.stage-candidate.v2",
    "material.ingest.commit-readback.v2",
    "material.ingest.projection-diff.v2",
    "material.ingest.reconciliation.v2",
    "knowledge.read.v2",
    "knowledge.writing.v2",
    "knowledge.report.v2",
    "knowledge.graph-projection.v2",
    "projection.command-query.v2",
    "projection.client-contract.v2",
    "projection.read-model.v2",
)

pytestmark = pytest.mark.unit


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _load(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not _is_object_dict(value):
        raise TypeError(f"expected JSON object: {path}")  # noqa: TRY003
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"expected string JSON key: {path}")  # noqa: TRY003
        result[key] = item
    return result


def _verify_frozen_rollback_bindings() -> int:
    """Verify frozen capability records without treating them as live inventory."""

    paths = tuple(sorted(SPECS_DIR.glob("C*.v1.json")))
    specs = tuple(CapabilityCellSpec.from_dict(_load(path)) for path in paths)
    assert len(specs) == 30
    assert len({spec.cell_id for spec in specs}) == len(specs)
    assert RETIRED_FROZEN_CELL_IDS <= {spec.cell_id for spec in specs}
    for path, spec in zip(paths, specs, strict=True):
        assert path.name == f"{spec.cell_id}.v1.json"
        for binding in spec.rollback_bindings:
            frozen = historical_bytes(binding.path, binding.file_sha256)
            assert hashlib.sha256(frozen).hexdigest() == binding.file_sha256
    return len(specs)


def _require_current_binding_paths(binding_refs: tuple[str, ...]) -> None:
    for binding_ref in binding_refs:
        path = Path(binding_ref)
        if not path.is_absolute():
            path = REPOSITORY_ROOT / path
        assert path.is_file(), f"current rollback binding missing: {binding_ref}"


def _rollback_rows() -> list[dict[str, Any]]:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:"),
        options=build_local_offline_fixture_options(),
    )
    declarations = {item.cell_id: item for item in assembly.rollback_bindings}
    rows: list[dict[str, Any]] = []
    for cell in assembly.cells:
        declaration = declarations.get(cell.cell_id)
        if declaration is None:
            rows.append(
                {
                    "cell_id": cell.cell_id,
                    "rehearsal_status": "BLOCKED",
                    "declaration_status": "UNKNOWN_GAP",
                    "binding_refs": [],
                    "handler_binding_digest": cell.handler_binding_digest,
                    "operation_contract_refs": list(cell.operation_contract_refs),
                    "note": "current rollback declaration is absent",
                }
            )
            continue
        _require_current_binding_paths(declaration.binding_refs)
        row_base = {
            "cell_id": cell.cell_id,
            "binding_refs": list(declaration.binding_refs),
            "handler_binding_digest": cell.handler_binding_digest,
            "operation_contract_refs": list(cell.operation_contract_refs),
            "note": declaration.note,
        }
        if (
            cell.cell_id in MATERIAL_ASSEMBLY_CELL_IDS
            and declaration.status == "PRESENT"
        ):
            rows.append(
                {
                    **row_base,
                    "rehearsal_status": "ROUTE_ASSEMBLED",
                    "declaration_status": "PRESENT",
                }
            )
            continue
        if cell.cell_id in MATERIAL_ASSEMBLY_CELL_IDS:
            assert declaration.status == "DECLARED_GAP"
            rows.append(
                {
                    **row_base,
                    "rehearsal_status": "BLOCKED",
                    "declaration_status": "DECLARED_GAP",
                }
            )
            continue
        if declaration.status == "PRESENT":
            rows.append(
                {
                    **row_base,
                    "rehearsal_status": "STRUCTURAL_PASS",
                    "declaration_status": "PRESENT",
                }
            )
        elif declaration.status == "DECLARED_OPEN":
            rows.append(
                {
                    **row_base,
                    "rehearsal_status": "DECLARED_OPEN",
                    "declaration_status": "DECLARED_OPEN",
                    "note": declaration.note
                    or "no rollback implementation binding is installed",
                }
            )
        else:
            rows.append(
                {
                    **row_base,
                    "rehearsal_status": "BLOCKED",
                    "declaration_status": declaration.status,
                }
            )
    assert len(rows) == len(assembly.cells)
    assert {row["cell_id"] for row in rows} == ALL_I1_CELLS
    assert RETIRED_FROZEN_CELL_IDS.isdisjoint(
        row["cell_id"] for row in rows
    )
    assert tuple(row["cell_id"] for row in rows) == CURRENT_I1_CELL_ORDER
    assert len(set(CURRENT_I1_CELL_ORDER)) == len(CURRENT_I1_CELL_ORDER)
    assert RETIRED_CURRENT_CELL_IDS.isdisjoint(CURRENT_I1_CELL_ORDER)
    return rows


def test_i1_rollback_rehearsal_matrix_covers_current_twenty_five_cells() -> None:
    rows = _rollback_rows()
    assert len(rows) == 25
    assert tuple(row["cell_id"] for row in rows) == CURRENT_I1_CELL_ORDER
    assert RETIRED_CURRENT_CELL_IDS.isdisjoint(ALL_I1_CELLS)
    by_id = {row["cell_id"]: row for row in rows}
    assert set(by_id) == ALL_I1_CELLS
    assert len(by_id) == len(rows)
    for row in rows:
        assert row["operation_contract_refs"]
        assert row["handler_binding_digest"] is not None
        assert len(row["handler_binding_digest"]) == 64
        assert row["declaration_status"] != "UNKNOWN_GAP"
    for cell_id in MATERIAL_ASSEMBLY_CELL_IDS:
        assert by_id[cell_id]["rehearsal_status"] == "ROUTE_ASSEMBLED"
        assert by_id[cell_id]["declaration_status"] == "PRESENT"
        assert by_id[cell_id]["binding_refs"]


def test_i1_default_c7_rollback_gap_blocks_without_inventing_bindings() -> None:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:")
    )
    declarations = {
        item.cell_id: item
        for item in assembly.rollback_bindings
        if item.cell_id in MATERIAL_ASSEMBLY_CELL_IDS
    }
    assert set(declarations) == set(MATERIAL_ASSEMBLY_CELL_IDS)
    for cell_id in MATERIAL_ASSEMBLY_CELL_IDS:
        declaration = declarations[cell_id]
        assert declaration.status == "DECLARED_GAP"
        assert declaration.binding_refs == ()
        assert "rollback" in declaration.note.lower()


def test_i1_present_rollback_bindings_are_exact_on_disk() -> None:
    assert _verify_frozen_rollback_bindings() == 30
    rows = _rollback_rows()
    present = [row for row in rows if row["declaration_status"] == "PRESENT"]
    assert present
    for row in present:
        assert row["binding_refs"]


def test_i1_assembly_recovery_and_effect_digests_never_duplicate() -> None:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:")
    )
    effect_digests = {handler.handler_binding_digest for handler in assembly.handlers}
    recovery_digests = {
        handler.handler_binding_digest for handler in assembly.recovery_handlers
    }
    assert effect_digests.isdisjoint(recovery_digests)
