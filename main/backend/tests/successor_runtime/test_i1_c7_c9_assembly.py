"""Non-PostgreSQL structural assertions for the C7/C8/C9 family assemblies."""

from __future__ import annotations

import dataclasses

from app.successor_runtime.assembly.base import (
    KnowledgeAssemblyOptions,
    ProjectionAssemblyOptions,
    ProjectorSourceKey,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.material_ingest_assembly import (
    ASSEMBLY_CELL_IDS as MATERIAL_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.assembly.material_ingest_assembly import (
    MATERIAL_INGEST_FAMILY_ID,
    MATERIAL_INGEST_ROLLBACK_GAP_NOTE,
    build_material_ingest_assembly,
    build_deterministic_material_ingest_rollback_options,
    validate_material_ingest_assembly_native_definition,
)
from app.successor_runtime.assembly.knowledge_assembly import (
    ASSEMBLY_CELL_IDS as KNOWLEDGE_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.assembly.knowledge_assembly import (
    KNOWLEDGE_FAMILY_ID,
    build_knowledge_assembly,
    build_deterministic_knowledge_payloads,
)
from app.successor_runtime.assembly.projection_assembly import (
    PROJECTION_CLIENT_CONTRACT_KERNEL_ID,
    PROJECTION_CLIENT_CONTRACT_KERNEL_WIRING,
    PROJECTION_FAMILY_ID,
    build_projection_assembly,
    build_deterministic_facade_closure,
    validate_projection_assembly_native_definition,
)
from app.successor_runtime.capabilities.material_native_contribution import (
    DEFAULT_MATERIAL_NATIVE_SOURCE,
    MATERIAL_STAGE_CANDIDATE_CELL_ID,
    compile_material_native_contribution,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.runtime.projection_native_contribution import (
    ASSEMBLY_CELL_IDS as PROJECTION_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.runtime.projection_native_contribution import (
    DEFAULT_PROJECTION_NATIVE_SOURCE,
    PROJECTION_CLIENT_CONTRACT_CELL_ID,
    PROJECTION_COMMAND_QUERY_CELL_ID,
    PROJECTION_READ_MODEL_CELL_ID,
    compile_projection_native_contribution,
)
from functorial_kit.core.failure import Failure
from sqlalchemy import create_engine

(
    KNOWLEDGE_READ_CELL,
    KNOWLEDGE_WRITING_CELL,
    KNOWLEDGE_REPORT_CELL,
    KNOWLEDGE_GRAPH_PROJECTION_CELL,
) = KNOWLEDGE_ASSEMBLY_CELL_IDS


def _engine() -> object:
    return create_engine("sqlite:///:memory:")


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

    options = build_deterministic_material_ingest_rollback_options(local_assembly_scope_digest())
    installed = build_material_ingest_assembly(options=options, native_definition=native.definition)
    validate_material_ingest_assembly_native_definition(native.definition, installed)
    assert installed.cell(MATERIAL_STAGE_CANDIDATE_CELL_ID).status == "INSTALLED"
    assert installed.handlers[0].operation_contract_digest != ""
    assert expected_authority

    tampered_definition = dataclasses.replace(
        native.definition,
        source=dataclasses.replace(
            native.definition.source,
            canonical_write_authorized=True,
        ),
    )
    try:
        validate_material_ingest_assembly_native_definition(tampered_definition, installed)
    except ValueError as exc:
        assert "canonical write authority" in str(exc)
    else:
        raise AssertionError("tampered C7 native definition was accepted")


def test_c7_assembly_derives_c71_operation_from_native_catalog() -> None:
    native = compile_material_native_contribution(DEFAULT_MATERIAL_NATIVE_SOURCE)
    assert not isinstance(native, Failure)
    assembly = build_material_ingest_assembly(
        options=build_deterministic_material_ingest_rollback_options(local_assembly_scope_digest()),
        native_definition=native.definition,
    )
    contract = native.definition.catalog.lookup(DEFAULT_MATERIAL_NATIVE_SOURCE.operation_kind)
    assert contract is not None
    assert assembly.handlers[0].operation_contract_digest == contract.contract_digest


def test_c9_assembly_accepts_typed_native_definition_and_rejects_tamper() -> None:
    native = compile_projection_native_contribution(DEFAULT_PROJECTION_NATIVE_SOURCE)
    assert not isinstance(native, Failure)
    assembly = build_projection_assembly(native_definition=native.definition)
    validate_projection_assembly_native_definition(native.definition, assembly)
    wiring = assembly.projector_wiring[0]
    key = native.definition.projector_key
    assert (wiring.projector_id, wiring.projector_version, wiring.source_kind) == (
        key.projector_id,
        key.projector_version,
        key.source_kind,
    )

    tampered_definition = dataclasses.replace(
        native.definition,
        source=dataclasses.replace(
            native.definition.source,
            anchor=dataclasses.replace(
                native.definition.source.anchor,
                projector_id="tampered.projector.v1",
            ),
        ),
    )
    try:
        validate_projection_assembly_native_definition(tampered_definition, assembly)
    except ValueError as exc:
        assert "projector/offset key drift" in str(exc)
    else:
        raise AssertionError("tampered C9 native definition was accepted")


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


def test_c7_assembly_installs_pure_rollback_routes_with_closures() -> None:
    scope_digest = local_assembly_scope_digest()
    assembly = build_material_ingest_assembly(
        options=build_deterministic_material_ingest_rollback_options(scope_digest),
    )
    assert assembly.family_id == MATERIAL_INGEST_FAMILY_ID
    assert tuple(assembly.coverage()) == MATERIAL_ASSEMBLY_CELL_IDS
    assert set(assembly.coverage().values()) == {"INSTALLED"}
    assert len(assembly.handlers) == 4
    handler_digests = {handler.handler_binding_digest for handler in assembly.handlers}
    for cell_id in MATERIAL_ASSEMBLY_CELL_IDS:
        cell = assembly.cell(cell_id)
        assert cell.handler_binding_digest in handler_digests
    by_cell = {item.cell_id: item for item in assembly.rollback_bindings}
    for cell_id in MATERIAL_ASSEMBLY_CELL_IDS:
        assert by_cell[cell_id].status == "PRESENT"
        assert by_cell[cell_id].binding_refs
        assert "p4-fragments" not in " ".join(by_cell[cell_id].binding_refs)


def test_c8_assembly_without_options_installs_nothing() -> None:
    assembly = build_knowledge_assembly(
        engine=_engine(),  # type: ignore[arg-type]
        project_scope_digest=local_assembly_scope_digest(),
        options=None,
    )
    assert assembly.family_id == KNOWLEDGE_FAMILY_ID
    assert assembly.coverage() == {
        KNOWLEDGE_READ_CELL: "UNWIRED_DECLARED",
        KNOWLEDGE_WRITING_CELL: "UNWIRED_DECLARED",
        KNOWLEDGE_REPORT_CELL: "UNWIRED_DECLARED",
        KNOWLEDGE_GRAPH_PROJECTION_CELL: "PROJECTOR_WIRING_DECLARED",
    }
    assert assembly.handlers == ()
    assert assembly.recovery_handlers == ()
    for cell in assembly.cells:
        assert cell.family_id == KNOWLEDGE_FAMILY_ID
        assert cell.handler_binding_digest is None
    assert {item.cell_id for item in assembly.projector_wiring} == {KNOWLEDGE_GRAPH_PROJECTION_CELL}
    assert {item.cell_id for item in assembly.rollback_bindings} == set(KNOWLEDGE_ASSEMBLY_CELL_IDS)
    assert all(item.status == "PRESENT" and item.binding_refs for item in assembly.rollback_bindings)


def test_c8_assembly_installs_c81_c82_route_handlers_with_closures() -> None:
    scope_digest = local_assembly_scope_digest()
    assembly = build_knowledge_assembly(
        engine=_engine(),  # type: ignore[arg-type]
        project_scope_digest=scope_digest,
        options=KnowledgeAssemblyOptions(**build_deterministic_knowledge_payloads(scope_digest)),
    )
    assert assembly.coverage()[KNOWLEDGE_READ_CELL] == "INSTALLED"
    assert assembly.coverage()[KNOWLEDGE_WRITING_CELL] == "INSTALLED"
    assert assembly.coverage()[KNOWLEDGE_REPORT_CELL] == "UNWIRED_DECLARED"
    assert assembly.coverage()[KNOWLEDGE_GRAPH_PROJECTION_CELL] == ("PROJECTOR_WIRING_DECLARED")
    handler_digests = {handler.handler_binding_digest for handler in assembly.handlers}
    for cell_id in KNOWLEDGE_ASSEMBLY_CELL_IDS[:2]:
        assert assembly.cell(cell_id).handler_binding_digest in handler_digests
    assert "per-run source_ref" in assembly.cell(KNOWLEDGE_GRAPH_PROJECTION_CELL).note


def test_c8_assembly_registers_c84_projector_with_per_run_source_key() -> None:
    assembly = build_knowledge_assembly(
        engine=_engine(),  # type: ignore[arg-type]
        project_scope_digest=local_assembly_scope_digest(),
        projector_source_keys={
            KNOWLEDGE_GRAPH_PROJECTION_CELL: ProjectorSourceKey(
                source_ref=f"run:i1-local:{KNOWLEDGE_GRAPH_PROJECTION_CELL}:001",
                source_incarnation=(f"incarnation:i1-local:{KNOWLEDGE_GRAPH_PROJECTION_CELL}:001"),
            )
        },
    )
    cell = assembly.cell(KNOWLEDGE_GRAPH_PROJECTION_CELL)
    assert cell.status == "INSTALLED"
    assert cell.handler_binding_digest is not None
    assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 1
    wiring = assembly.projector_wiring[0]
    contract = assembly.projector_registry.projectors[0]
    assert cell.handler_binding_digest == wiring.registration_digest(contract)


def test_c9_assembly_statuses_and_digests() -> None:
    assembly = build_projection_assembly()
    assert assembly.family_id == PROJECTION_FAMILY_ID == DEFAULT_PROJECTION_NATIVE_SOURCE.family_id
    assert tuple(assembly.coverage()) == PROJECTION_ASSEMBLY_CELL_IDS
    assert set(assembly.coverage().values()) == {"INSTALLED"}
    assert len(assembly.handlers) == 1
    assert assembly.recovery_handlers == ()
    for cell in assembly.cells:
        assert cell.family_id == PROJECTION_FAMILY_ID
        assert cell.handler_binding_digest is not None
    kernel = {item.cell_id: item for item in assembly.kernel_wiring}
    assert set(kernel) == {PROJECTION_CLIENT_CONTRACT_CELL_ID}
    assert kernel[PROJECTION_CLIENT_CONTRACT_CELL_ID].kernel_id == PROJECTION_CLIENT_CONTRACT_KERNEL_ID
    assert (
        assembly.cell(PROJECTION_CLIENT_CONTRACT_CELL_ID).handler_binding_digest
        == kernel[PROJECTION_CLIENT_CONTRACT_CELL_ID].binding_digest
    )
    assert kernel[PROJECTION_CLIENT_CONTRACT_CELL_ID].binding_refs
    assert {item.cell_id for item in assembly.projector_wiring} == {PROJECTION_READ_MODEL_CELL_ID}
    assert {item.cell_id for item in assembly.rollback_bindings} == set(PROJECTION_ASSEMBLY_CELL_IDS)
    assert assembly.projector_registry is not None
    contract = assembly.projector_registry.projectors[0]
    anchor = DEFAULT_PROJECTION_NATIVE_SOURCE.anchor
    assert contract.projection_id == DEFAULT_PROJECTION_NATIVE_SOURCE.projection_contract
    assert contract.key.projector_id == anchor.projector_id
    assert contract.key.projector_version == anchor.projector_version
    assert contract.key.source_kind == anchor.source_kind
    assert contract.projection_schema_ref == anchor.projection_schema_ref
    assert all(item.status == "PRESENT" and item.binding_refs for item in assembly.rollback_bindings)


def test_c9_assembly_installs_facade_route_with_closure() -> None:
    assembly = build_projection_assembly(options=ProjectionAssemblyOptions(facade=build_deterministic_facade_closure()))
    assert assembly.family_id == PROJECTION_FAMILY_ID == DEFAULT_PROJECTION_NATIVE_SOURCE.family_id
    assert tuple(assembly.coverage()) == PROJECTION_ASSEMBLY_CELL_IDS
    assert set(assembly.coverage().values()) == {"INSTALLED"}
    assert len(assembly.handlers) == 1
    assert {item.cell_id for item in assembly.kernel_wiring} == {PROJECTION_CLIENT_CONTRACT_CELL_ID}
    assert PROJECTION_CLIENT_CONTRACT_KERNEL_WIRING.binding_digest == (
        assembly.cell(PROJECTION_CLIENT_CONTRACT_CELL_ID).handler_binding_digest
    )
    assert assembly.cell(PROJECTION_COMMAND_QUERY_CELL_ID).handler_binding_digest == (
        assembly.handlers[0].handler_binding_digest
    )
    assert "router" in assembly.cell(PROJECTION_COMMAND_QUERY_CELL_ID).note


def test_c9_assembly_registers_c93_projector_with_per_run_source_key() -> None:
    assembly = build_projection_assembly(
        projector_source_keys={
            PROJECTION_READ_MODEL_CELL_ID: ProjectorSourceKey(
                source_ref="projection:i1-local:source",
                source_incarnation="incarnation:i1-local:projection-read-model",
            )
        }
    )
    cell = assembly.cell(PROJECTION_READ_MODEL_CELL_ID)
    assert cell.status == "INSTALLED"
    assert cell.handler_binding_digest is not None
    assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 1
    wiring = assembly.projector_wiring[0]
    contract = assembly.projector_registry.projectors[0]
    assert cell.handler_binding_digest == wiring.registration_digest(contract)
