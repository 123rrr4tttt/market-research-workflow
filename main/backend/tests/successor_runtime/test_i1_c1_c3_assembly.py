"""Non-PostgreSQL structural assertions for the retained source assembly."""

from __future__ import annotations

from app.successor_runtime.assembly.base import (
    ProjectorSourceKey,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.source_assembly import build_source_assembly
from app.successor_runtime.capabilities import source_resolution as c21
from app.successor_runtime.capabilities import source_planning as c22
from app.successor_runtime.capabilities import source_provider_acquisition as c23
from app.successor_runtime.capabilities.source_resolution_interpreters import (
    authority_requirement_digest as c21_authority_requirement_digest,
    successor_interpreter_profile_digest,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    ASSEMBLY_CELL_IDS as SOURCE_ASSEMBLY_CELL_IDS,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    SOURCE_FAMILY_ID,
)
from app.successor_runtime.runtime.assignments import InterpreterBinding
from app.successor_runtime.substrate.postgres.source_library_c2_23_canary import (
    build_successor_c2_2_binding,
    build_successor_c2_3_binding,
)

(
    SOURCE_RESOLVE_CELL,
    SOURCE_PLAN_CELL,
    SOURCE_PROVIDER_EFFECT_CELL,
    SOURCE_TERMINAL_PROJECTION_CELL,
) = SOURCE_ASSEMBLY_CELL_IDS


def _uow_factory() -> object:
    return None


def _scope_digest() -> str:
    return local_assembly_scope_digest()


def test_c2_assembly_installs_one_exact_handler_per_installed_cell() -> None:
    assembly = build_source_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=_scope_digest(),
    )

    assert assembly.family_id == SOURCE_FAMILY_ID
    assert assembly.coverage() == {
        SOURCE_RESOLVE_CELL: "INSTALLED",
        SOURCE_PLAN_CELL: "INSTALLED",
        SOURCE_PROVIDER_EFFECT_CELL: "INSTALLED",
        SOURCE_TERMINAL_PROJECTION_CELL: "PROJECTOR_WIRING_DECLARED",
    }
    assert len(assembly.handlers) == 6
    assert len({handler.handler_binding_digest for handler in assembly.handlers}) == 6
    handler_digests = {handler.handler_binding_digest for handler in assembly.handlers}
    for cell_id in SOURCE_ASSEMBLY_CELL_IDS[:3]:
        cell = assembly.cell(cell_id)
        assert cell.status == "INSTALLED"
        assert cell.handler_binding_digest in handler_digests
    assert len(assembly.projector_wiring) == 1
    assert assembly.projector_wiring[0].cell_id == SOURCE_TERMINAL_PROJECTION_CELL
    assert assembly.projector_wiring[0].source_kind == "RUNTIME_JOURNAL"
    assert "LIVE_PROVIDER_DIMENSION_UNRESOLVED" in assembly.cell(SOURCE_PROVIDER_EFFECT_CELL).note


def test_c2_assembly_registers_projector_with_per_run_source_key() -> None:
    assembly = build_source_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=_scope_digest(),
        projector_source_keys={
            SOURCE_TERMINAL_PROJECTION_CELL: ProjectorSourceKey(
                source_ref=f"run:i1-local:{SOURCE_TERMINAL_PROJECTION_CELL}:001",
                source_incarnation=(f"incarnation:i1-local:{SOURCE_TERMINAL_PROJECTION_CELL}:001"),
            )
        },
    )
    cell = assembly.cell(SOURCE_TERMINAL_PROJECTION_CELL)
    assert cell.status == "INSTALLED"
    assert cell.handler_binding_digest is not None
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 1
    wiring = assembly.projector_wiring[0]
    contract = assembly.projector_registry.projectors[0]
    assert cell.handler_binding_digest == wiring.registration_digest(contract)
    assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note


def test_c2_installed_digests_match_existing_binding_builders() -> None:
    project_scope_digest = _scope_digest()
    deployment_catalog_digest = c21.deployment_catalog_digest()
    assembly = build_source_assembly(
        uow_factory=_uow_factory,
        project_scope_digest=project_scope_digest,
    )
    by_cell = {handler.handler_binding_digest: handler for handler in assembly.handlers}

    c2_1_ref = c21.build_source_resolution_catalog(c21.build_source_resolution_bundle()).lookup(
        c21.SOURCE_RESOLUTION_KIND
    )
    assert c2_1_ref is not None
    c2_1_binding = InterpreterBinding.from_content(
        operation_contract_digest=c2_1_ref.contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
        runtime_protocol_version="1",
        resource_policy_epoch=1,
        authority_requirement_digest=c21_authority_requirement_digest(),
    )
    assert c2_1_binding.binding_digest in by_cell

    c2_2_catalog = c22.build_source_planning_catalog(
        c22.build_source_planning_bundle()
    )
    for kind in c22.SOURCE_PLANNING_KINDS:
        c2_2_ref = c2_2_catalog.lookup(kind)
        assert c2_2_ref is not None
        c2_2_binding = build_successor_c2_2_binding(
            contract_digest=c2_2_ref.contract_digest,
            deployment_catalog_digest=deployment_catalog_digest,
            project_scope_digest=project_scope_digest,
            runtime_protocol_version="1",
        )
        assert c2_2_binding.binding_digest in by_cell

    c2_3_ref = c23.build_source_provider_acquisition_catalog(c23.build_source_provider_acquisition_bundle()).lookup(
        c23.SOURCE_PROVIDER_ACQUISITION_KIND
    )
    assert c2_3_ref is not None
    c2_3_binding = build_successor_c2_3_binding(
        contract_digest=c2_3_ref.contract_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
        runtime_protocol_version="1",
    )
    assert c2_3_binding.binding_digest in by_cell
