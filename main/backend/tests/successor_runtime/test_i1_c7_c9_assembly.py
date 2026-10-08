"""Non-PostgreSQL structural assertions for the C7 material-ingest assembly."""

from __future__ import annotations

import dataclasses

from app.successor_runtime.assembly.material_ingest_assembly import (
    ASSEMBLY_CELL_IDS as MATERIAL_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.assembly.material_ingest_assembly import (
    MATERIAL_INGEST_FAMILY_ID,
    MATERIAL_INGEST_ROLLBACK_GAP_NOTE,
    build_material_ingest_assembly,
    validate_material_ingest_assembly_native_definition,
)
from app.successor_runtime.capabilities.material_native_contribution import (
    DEFAULT_MATERIAL_NATIVE_SOURCE,
    MATERIAL_STAGE_CANDIDATE_CELL_ID,
    compile_material_native_contribution,
)
from app.successor_runtime.capabilities.checksum import content_digest
from functorial_kit.core.failure import Failure


def test_c7_assembly_accepts_typed_native_definition_and_rejects_tamper() -> None:
    native = compile_material_native_contribution(DEFAULT_MATERIAL_NATIVE_SOURCE)
    assert not isinstance(native, Failure)
    assembly = build_material_ingest_assembly(native_definition=native.definition)
    validate_material_ingest_assembly_native_definition(native.definition, assembly)
    expected_authority = content_digest(
        (
            DEFAULT_MATERIAL_NATIVE_SOURCE.canonical_writer_ref,
            DEFAULT_MATERIAL_NATIVE_SOURCE.production_admission_ref,
            DEFAULT_MATERIAL_NATIVE_SOURCE.projector_driver_ref,
        )
    )
    cell = assembly.cell(MATERIAL_STAGE_CANDIDATE_CELL_ID)
    assert cell.status == "UNWIRED_DECLARED"

    tampered_definition = dataclasses.replace(
        native.definition,
        source=dataclasses.replace(
            native.definition.source,
            canonical_write_authorized=True,
        ),
    )
    try:
        validate_material_ingest_assembly_native_definition(tampered_definition, assembly)
    except ValueError as exc:
        assert "canonical write authority" in str(exc)
    else:
        raise AssertionError("tampered C7 native definition was accepted")


def test_c7_assembly_covers_all_cells_unwired() -> None:
    assembly = build_material_ingest_assembly()
    assert assembly.family_id == MATERIAL_INGEST_FAMILY_ID
    assert tuple(assembly.coverage()) == MATERIAL_ASSEMBLY_CELL_IDS
    assert set(assembly.coverage().values()) == {"UNWIRED_DECLARED"}
    assert assembly.handlers == ()
    assert assembly.recovery_handlers == ()
    assert assembly.projector_wiring == ()
    for cell in assembly.cells:
        assert cell.family_id == MATERIAL_INGEST_FAMILY_ID
        assert cell.handler_binding_digest is None
        assert cell.operation_contract_refs
        assert cell.required_wiring


def test_c7_rollback_declarations_are_declared_gap() -> None:
    assembly = build_material_ingest_assembly()
    by_cell = {item.cell_id: item for item in assembly.rollback_bindings}
    assert set(by_cell) == set(MATERIAL_ASSEMBLY_CELL_IDS)
    for declaration in assembly.rollback_bindings:
        assert declaration.status == "DECLARED_GAP"
        assert declaration.binding_refs == ()
        assert MATERIAL_INGEST_ROLLBACK_GAP_NOTE in declaration.note
