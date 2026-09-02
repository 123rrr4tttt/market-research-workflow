"""Non-PostgreSQL structural tests for the I1 C4/C5/C6 family assemblies."""

from __future__ import annotations

from collections.abc import Callable

from app.successor_runtime.assembly.base import (
    C4AssemblyOptions,
    C5AssemblyOptions,
    C6AssemblyOptions,
    ProjectorSourceKey,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.c4_assembly import (
    build_c4_assembly,
    build_deterministic_plan_payload,
    build_deterministic_retry_payload,
)
from app.successor_runtime.assembly.c5_assembly import (
    build_c5_assembly,
    build_deterministic_reconciliation_binding,
)
from app.successor_runtime.assembly.c6_assembly import (
    build_c6_assembly,
    build_deterministic_fixtures,
)
from app.successor_runtime.substrate.postgres.agent_batch_c4_3_handler import (
    C4_3SubmissionStoreRehydratedHandler,
)
from app.successor_runtime.substrate.postgres.agent_batch_c4_canary import (
    C4_1_BatchPlanRuntimeHandler,
    C4_2_RetryRuntimeHandler,
)

from .p3_c4_fixture import SCOPE_DIGEST, plan_payload, retry_payload


def _uow_factory() -> Callable[[], object]:
    def factory() -> object:
        raise AssertionError("assembly construction must not open a unit of work")

    return factory


def test_c4_assembly_default_is_fail_closed_for_canaries() -> None:
    assembly = build_c4_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=SCOPE_DIGEST,
        options=None,
    )

    assert assembly.family_id == "C4"
    assert assembly.coverage() == {
        "C4.1": "FIXTURE_CLOSURE_REQUIRED",
        "C4.2": "FIXTURE_CLOSURE_REQUIRED",
        "C4.3": "INSTALLED",
    }
    assert len(assembly.handlers) == 1
    assert isinstance(assembly.handlers[0], C4_3SubmissionStoreRehydratedHandler)
    installed = [cell for cell in assembly.cells if cell.status == "INSTALLED"]
    assert installed == [assembly.cell("C4.3")]
    assert installed[0].handler_binding_digest == (
        assembly.handlers[0].handler_binding_digest
    )
    assert all(
        cell.handler_binding_digest is None
        for cell in assembly.cells
        if cell.status != "INSTALLED"
    )
    assert all(rollback.status == "PRESENT" for rollback in assembly.rollback_bindings)


def test_c4_assembly_installs_canary_handlers_with_payloads() -> None:
    options = C4AssemblyOptions(
        plan_payload=plan_payload(),
        retry_payload=retry_payload(),
    )
    assembly = build_c4_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=SCOPE_DIGEST,
        options=options,
    )

    assert assembly.coverage() == {
        "C4.1": "INSTALLED",
        "C4.2": "INSTALLED",
        "C4.3": "INSTALLED",
    }
    assert len(assembly.handlers) == 3
    kinds = {type(handler) for handler in assembly.handlers}
    assert kinds == {
        C4_1_BatchPlanRuntimeHandler,
        C4_2_RetryRuntimeHandler,
        C4_3SubmissionStoreRehydratedHandler,
    }
    digests = [handler.handler_binding_digest for handler in assembly.handlers]
    assert len(set(digests)) == len(digests)
    installed_digests = {
        cell.handler_binding_digest
        for cell in assembly.cells
        if cell.status == "INSTALLED"
    }
    assert installed_digests == set(digests)


def test_c4_assembly_installs_with_production_fixture_builder() -> None:
    scope_digest = local_assembly_scope_digest()
    options = C4AssemblyOptions(
        plan_payload=build_deterministic_plan_payload(scope_digest),
        retry_payload=build_deterministic_retry_payload(scope_digest),
    )
    assembly = build_c4_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=scope_digest,
        options=options,
    )
    assert assembly.coverage() == {
        "C4.1": "INSTALLED",
        "C4.2": "INSTALLED",
        "C4.3": "INSTALLED",
    }
    assert len(assembly.handlers) == 3


def test_c4_assembly_rejects_payload_scope_drift() -> None:
    drifted_scope = "0" * 64
    options = C4AssemblyOptions(plan_payload=plan_payload())
    try:
        build_c4_assembly(
            uow_factory=_uow_factory(),
            project_scope_digest=drifted_scope,
            options=options,
        )
    except ValueError as exc:
        assert "scope digest" in str(exc)
    else:
        raise AssertionError("payload scope drift must fail closed")


def test_c5_assembly_declares_projector_wiring_and_c52_gap() -> None:
    assembly = build_c5_assembly()

    assert assembly.family_id == "C5"
    assert assembly.coverage() == {
        "C5.1": "PROJECTOR_WIRING_DECLARED",
        "C5.2": "FIXTURE_CLOSURE_REQUIRED",
        "C5.3": "PROJECTOR_WIRING_DECLARED",
        "C5.4": "PROJECTOR_WIRING_DECLARED",
    }
    assert len(assembly.projector_wiring) == 3
    assert {wiring.cell_id for wiring in assembly.projector_wiring} == {
        "C5.1",
        "C5.3",
        "C5.4",
    }
    assert all("source key" in wiring.note for wiring in assembly.projector_wiring)
    assert "REUSE_INFERRED" in assembly.cell("C5.2").note
    assert assembly.cell("C5.2").handler_binding_digest is None
    assert all(rollback.status == "PRESENT" for rollback in assembly.rollback_bindings)


def test_c5_assembly_installs_reconciliation_route_with_binding() -> None:
    scope_digest = local_assembly_scope_digest()
    assembly = build_c5_assembly(
        options=C5AssemblyOptions(
            reconciliation_binding=build_deterministic_reconciliation_binding(
                scope_digest
            )
        )
    )
    cell = assembly.cell("C5.2")
    assert cell.status == "INSTALLED"
    assert cell.handler_binding_digest == assembly.handlers[0].handler_binding_digest
    assert "C5_2_DURABLE_ATTEMPT_NODE_NOT_PROVEN" in cell.note
    assert {wiring.cell_id for wiring in assembly.projector_wiring} == {
        "C5.1",
        "C5.3",
        "C5.4",
    }


def test_c5_assembly_registers_projectors_with_per_run_source_keys() -> None:
    assembly = build_c5_assembly(
        projector_source_keys={
            "C5.1": ProjectorSourceKey(
                source_ref="run:i1-local:C5.1:001",
                source_incarnation="incarnation:i1-local:C5.1:001",
            ),
            "C5.3": ProjectorSourceKey(
                source_ref="run:i1-local:C5.3:001",
                source_incarnation="incarnation:i1-local:C5.3:001",
            ),
            "C5.4": ProjectorSourceKey(
                source_ref="run:i1-local:C5.4:001",
                source_incarnation="incarnation:i1-local:C5.4:001",
            ),
        }
    )
    for cell_id in ("C5.1", "C5.3", "C5.4"):
        cell = assembly.cell(cell_id)
        assert cell.status == "INSTALLED", cell_id
        assert cell.handler_binding_digest is not None
        assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 3
    by_cell = {wiring.cell_id: wiring for wiring in assembly.projector_wiring}
    registered = {
        wiring.cell_id: wiring.registration_digest(contract)
        for wiring in assembly.projector_wiring
        for contract in assembly.projector_registry.projectors
        if contract.projection_id == wiring.projection_id
    }
    for cell_id in ("C5.1", "C5.3", "C5.4"):
        assert assembly.cell(cell_id).handler_binding_digest == registered[cell_id]
    assert by_cell["C5.1"].projector_id == (
        "successor.agent_session.journal_projection.v1"
    )


def test_c5_assembly_supports_partial_projector_registration() -> None:
    assembly = build_c5_assembly(
        projector_source_keys={
            "C5.1": ProjectorSourceKey(
                source_ref="run:i1-local:C5.1:001",
                source_incarnation="incarnation:i1-local:C5.1:001",
            )
        }
    )
    assert assembly.cell("C5.1").status == "INSTALLED"
    assert assembly.cell("C5.3").status == "PROJECTOR_WIRING_DECLARED"
    assert assembly.cell("C5.4").status == "PROJECTOR_WIRING_DECLARED"
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 1


def test_c6_assembly_never_installs_without_run_fixtures() -> None:
    scope_digest = local_assembly_scope_digest()
    default_assembly = build_c6_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=scope_digest,
        options=None,
    )
    assert default_assembly.coverage() == {
        "C6.1": "FIXTURE_CLOSURE_REQUIRED",
        "C6.2": "FIXTURE_CLOSURE_REQUIRED",
        "C6.3": "FIXTURE_CLOSURE_REQUIRED",
    }
    assert default_assembly.handlers == ()

    partial_options = C6AssemblyOptions(
        model_step_source=object(),
        provider_port=object(),
        raw_observation={"fixture": True},
    )
    partial_assembly = build_c6_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=scope_digest,
        options=partial_options,
    )
    assert partial_assembly.coverage() == {
        "C6.1": "FIXTURE_CLOSURE_REQUIRED",
        "C6.2": "INSTALLED",
        "C6.3": "INSTALLED",
    }
    assert len(partial_assembly.handlers) == 2
    assert "missing" in partial_assembly.cell("C6.1").note
    assert "LIVE_PROVIDER_DIMENSION_UNRESOLVED" in (partial_assembly.cell("C6.2").note)
    assert all(
        rollback.status == "PRESENT" for rollback in default_assembly.rollback_bindings
    )


def test_c6_assembly_installs_all_cells_with_production_fixtures() -> None:
    scope_digest = local_assembly_scope_digest()
    assembly = build_c6_assembly(
        uow_factory=_uow_factory(),
        project_scope_digest=scope_digest,
        options=C6AssemblyOptions(**build_deterministic_fixtures()),
    )
    assert assembly.coverage() == {
        "C6.1": "INSTALLED",
        "C6.2": "INSTALLED",
        "C6.3": "INSTALLED",
    }
    assert len(assembly.handlers) == 3
    assert "LIVE_PROVIDER_DIMENSION_UNRESOLVED" in assembly.cell("C6.2").note
    assert all(rollback.status == "PRESENT" for rollback in assembly.rollback_bindings)


def test_c4_c5_c6_combined_coverage_and_family_discipline() -> None:
    assemblies = (
        build_c4_assembly(
            uow_factory=_uow_factory(),
            project_scope_digest=SCOPE_DIGEST,
        ),
        build_c5_assembly(),
        build_c6_assembly(
            uow_factory=_uow_factory(),
            project_scope_digest=SCOPE_DIGEST,
        ),
    )
    cells = tuple(cell for assembly in assemblies for cell in assembly.cells)

    assert len(cells) == 10
    assert {cell.cell_id for cell in cells} == {
        "C4.1",
        "C4.2",
        "C4.3",
        "C5.1",
        "C5.2",
        "C5.3",
        "C5.4",
        "C6.1",
        "C6.2",
        "C6.3",
    }
    assert all(cell.family_id in {"C4", "C5", "C6"} for cell in cells)
    assert all(cell.family_id == cell.cell_id.split(".")[0] for cell in cells)
