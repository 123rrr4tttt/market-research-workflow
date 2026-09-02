"""Non-PostgreSQL structural assertions for the C7/C8/C9 family assemblies."""

from __future__ import annotations

from sqlalchemy import create_engine

from app.successor_runtime.assembly.base import (
    C8AssemblyOptions,
    C9AssemblyOptions,
    ProjectorSourceKey,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.c7_assembly import (
    C7_FAMILY_ID,
    C7_ROLLBACK_GAP_NOTE,
    build_c7_assembly,
    build_deterministic_c7_rollback_options,
)
from app.successor_runtime.assembly.c8_assembly import (
    C8_FAMILY_ID,
    build_c8_assembly,
    build_deterministic_c8_payloads,
)
from app.successor_runtime.assembly.c9_assembly import (
    C9_FAMILY_ID,
    C9_2_KERNEL_WIRING,
    build_c9_assembly,
    build_deterministic_facade_closure,
)


def _engine() -> object:
    return create_engine("sqlite:///:memory:")


def test_c7_assembly_covers_all_cells_unwired() -> None:
    assembly = build_c7_assembly()
    assert assembly.family_id == C7_FAMILY_ID
    assert assembly.coverage() == {
        "C7.1": "UNWIRED_DECLARED",
        "C7.2": "UNWIRED_DECLARED",
        "C7.3": "UNWIRED_DECLARED",
        "C7.4": "UNWIRED_DECLARED",
    }
    assert assembly.handlers == ()
    assert assembly.recovery_handlers == ()
    assert assembly.projector_wiring == ()
    for cell in assembly.cells:
        assert cell.family_id == C7_FAMILY_ID
        assert cell.handler_binding_digest is None
        assert cell.operation_contract_refs
        assert cell.required_wiring


def test_c7_rollback_declarations_are_declared_gap() -> None:
    assembly = build_c7_assembly()
    by_cell = {item.cell_id: item for item in assembly.rollback_bindings}
    assert set(by_cell) == {"C7.1", "C7.2", "C7.3", "C7.4"}
    for declaration in assembly.rollback_bindings:
        assert declaration.status == "DECLARED_GAP"
        assert declaration.binding_refs == ()
        assert C7_ROLLBACK_GAP_NOTE in declaration.note


def test_c7_assembly_installs_pure_rollback_routes_with_closures() -> None:
    scope_digest = local_assembly_scope_digest()
    assembly = build_c7_assembly(
        options=build_deterministic_c7_rollback_options(scope_digest),
    )
    assert assembly.family_id == C7_FAMILY_ID
    assert assembly.coverage() == {
        "C7.1": "INSTALLED",
        "C7.2": "INSTALLED",
        "C7.3": "INSTALLED",
        "C7.4": "INSTALLED",
    }
    assert len(assembly.handlers) == 4
    handler_digests = {handler.handler_binding_digest for handler in assembly.handlers}
    for cell_id in ("C7.1", "C7.2", "C7.3", "C7.4"):
        cell = assembly.cell(cell_id)
        assert cell.handler_binding_digest in handler_digests
    by_cell = {item.cell_id: item for item in assembly.rollback_bindings}
    for cell_id in ("C7.1", "C7.2", "C7.3", "C7.4"):
        assert by_cell[cell_id].status == "PRESENT"
        assert by_cell[cell_id].binding_refs
        assert "p4-fragments" not in " ".join(by_cell[cell_id].binding_refs)


def test_c8_assembly_without_options_installs_nothing() -> None:
    assembly = build_c8_assembly(
        engine=_engine(),  # type: ignore[arg-type]
        project_scope_digest=local_assembly_scope_digest(),
        options=None,
    )
    assert assembly.family_id == C8_FAMILY_ID
    assert assembly.coverage() == {
        "C8.1": "UNWIRED_DECLARED",
        "C8.2": "UNWIRED_DECLARED",
        "C8.3": "UNWIRED_DECLARED",
        "C8.4": "PROJECTOR_WIRING_DECLARED",
    }
    assert assembly.handlers == ()
    assert assembly.recovery_handlers == ()
    for cell in assembly.cells:
        assert cell.family_id == C8_FAMILY_ID
        assert cell.handler_binding_digest is None
    assert {item.cell_id for item in assembly.projector_wiring} == {"C8.4"}
    assert {item.cell_id for item in assembly.rollback_bindings} == {
        "C8.1",
        "C8.2",
        "C8.3",
        "C8.4",
    }
    assert all(
        item.status == "PRESENT" and item.binding_refs
        for item in assembly.rollback_bindings
    )


def test_c8_assembly_installs_c81_c82_route_handlers_with_closures() -> None:
    scope_digest = local_assembly_scope_digest()
    assembly = build_c8_assembly(
        engine=_engine(),  # type: ignore[arg-type]
        project_scope_digest=scope_digest,
        options=C8AssemblyOptions(**build_deterministic_c8_payloads(scope_digest)),
    )
    assert assembly.coverage()["C8.1"] == "INSTALLED"
    assert assembly.coverage()["C8.2"] == "INSTALLED"
    assert assembly.coverage()["C8.3"] == "UNWIRED_DECLARED"
    assert assembly.coverage()["C8.4"] == "PROJECTOR_WIRING_DECLARED"
    handler_digests = {handler.handler_binding_digest for handler in assembly.handlers}
    for cell_id in ("C8.1", "C8.2"):
        assert assembly.cell(cell_id).handler_binding_digest in handler_digests
    assert "per-run source_ref" in assembly.cell("C8.4").note


def test_c8_assembly_registers_c84_projector_with_per_run_source_key() -> None:
    assembly = build_c8_assembly(
        engine=_engine(),  # type: ignore[arg-type]
        project_scope_digest=local_assembly_scope_digest(),
        projector_source_keys={
            "C8.4": ProjectorSourceKey(
                source_ref="run:i1-local:C8.4:001",
                source_incarnation="incarnation:i1-local:C8.4:001",
            )
        },
    )
    cell = assembly.cell("C8.4")
    assert cell.status == "INSTALLED"
    assert cell.handler_binding_digest is not None
    assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 1
    wiring = assembly.projector_wiring[0]
    contract = assembly.projector_registry.projectors[0]
    assert cell.handler_binding_digest == wiring.registration_digest(contract)


def test_c9_assembly_statuses_and_digests() -> None:
    assembly = build_c9_assembly()
    assert assembly.family_id == C9_FAMILY_ID
    assert assembly.coverage() == {
        "C9.1": "UNWIRED_DECLARED",
        "C9.2": "INSTALLED",
        "C9.3": "PROJECTOR_WIRING_DECLARED",
    }
    assert assembly.handlers == ()
    assert assembly.recovery_handlers == ()
    for cell in assembly.cells:
        assert cell.family_id == C9_FAMILY_ID
        if cell.status != "INSTALLED":
            assert cell.handler_binding_digest is None
    kernel = {item.cell_id: item for item in assembly.kernel_wiring}
    assert set(kernel) == {"C9.2"}
    assert kernel["C9.2"].kernel_id == "mrw.successor.frontend.c9-2.typed-contract.v1"
    assert (
        assembly.cell("C9.2").handler_binding_digest == kernel["C9.2"].binding_digest
    )
    assert kernel["C9.2"].binding_refs
    assert {item.cell_id for item in assembly.projector_wiring} == {"C9.3"}
    assert {item.cell_id for item in assembly.rollback_bindings} == {
        "C9.1",
        "C9.2",
        "C9.3",
    }
    assert all(
        item.status == "PRESENT" and item.binding_refs
        for item in assembly.rollback_bindings
    )


def test_c9_assembly_installs_facade_route_with_closure() -> None:
    assembly = build_c9_assembly(
        options=C9AssemblyOptions(facade=build_deterministic_facade_closure())
    )
    assert assembly.family_id == C9_FAMILY_ID
    assert assembly.coverage() == {
        "C9.1": "INSTALLED",
        "C9.2": "INSTALLED",
        "C9.3": "PROJECTOR_WIRING_DECLARED",
    }
    assert len(assembly.handlers) == 1
    assert {item.cell_id for item in assembly.kernel_wiring} == {"C9.2"}
    assert C9_2_KERNEL_WIRING.binding_digest == (
        assembly.cell("C9.2").handler_binding_digest
    )
    assert assembly.cell("C9.1").handler_binding_digest == (
        assembly.handlers[0].handler_binding_digest
    )
    assert "router" in assembly.cell("C9.1").note


def test_c9_assembly_registers_c93_projector_with_per_run_source_key() -> None:
    assembly = build_c9_assembly(
        projector_source_keys={
            "C9.3": ProjectorSourceKey(
                source_ref="run:i1-local:C9.3:001",
                source_incarnation="incarnation:i1-local:C9.3:001",
            )
        }
    )
    cell = assembly.cell("C9.3")
    assert cell.status == "INSTALLED"
    assert cell.handler_binding_digest is not None
    assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 1
    wiring = assembly.projector_wiring[0]
    contract = assembly.projector_registry.projectors[0]
    assert cell.handler_binding_digest == wiring.registration_digest(contract)
