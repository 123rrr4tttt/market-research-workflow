"""I1 serial composition-root coverage and fail-closed smoke tests.

The assembly is local-only: this test never mounts a route, never starts a
node and never executes a work item.  It verifies that the 30-cell coverage
matrix is complete, installed handler digests are unique, unresolved cells
are explicitly declared and ``compose_node`` returns a real ``RuntimeNode``
with all installed handlers resolvable.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine

from app.successor_runtime.assembly import (
    build_local_offline_fixture_options,
    local_assembly_scope_digest,
    merge_family_assemblies,
)
from app.successor_runtime.assembly.c1_assembly import build_c1_assembly
from app.successor_runtime.assembly.c7_assembly import build_c7_assembly
from app.successor_runtime.assembly.c9_assembly import build_c9_assembly
from app.successor_runtime.assembly.successor_assembly import (
    ALL_I1_CELLS,
    SuccessorAssembly,
    assemble_successor_runtime,
)
from app.successor_runtime.runtime.assignments import AssignmentKind
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    NodeIdentity,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
)
from app.successor_runtime.substrate.postgres.composition_root import (
    ExactInstalledHandlerResolver,
)

pytestmark = pytest.mark.unit


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _engine():
    return create_engine("sqlite+pysqlite:///:memory:", future=True)


def _node_identity() -> NodeIdentity:
    return NodeIdentity(
        node_id="node:i1-composition-smoke",
        incarnation="node-inc:i1-composition-smoke",
        started_at=datetime(2026, 9, 2, 0, 0, tzinfo=UTC),
    )


def _node_args(assembly: SuccessorAssembly) -> dict[str, object]:
    profile_digests = frozenset(
        handler.interpreter_profile_digest
        for handler in assembly.handlers
        if handler.interpreter_profile_digest is not None
    )
    node_profile = _digest("i1-node-profile")
    deployment_catalog = _digest("i1-deployment-catalog")
    return {
        "identity": _node_identity(),
        "profile": RuntimeNodeProfile(
            profile_digest=node_profile,
            supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
            interpreter_profile_digests=profile_digests,
        ),
        "deployment": DeploymentBinding(
            catalog_digest=deployment_catalog,
            node_profile_digest=node_profile,
            runtime_protocol_version="1",
        ),
        "protocol": RuntimeNodeProtocol(version="1", claim_batch_size=1),
        "control_scope": ControlPlaneScope(
            system_actor_id="node:i1-composition-smoke",
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=1,
        ),
    }


def _default_assembly() -> SuccessorAssembly:
    return assemble_successor_runtime(engine=_engine())


def test_i1_composition_root_covers_exactly_thirty_cells() -> None:
    assembly = _default_assembly()
    assert {item.cell_id for item in assembly.cells} == ALL_I1_CELLS
    assert len(assembly.cells) == 30
    summary = assembly.coverage_summary()
    assert sum(summary.values()) == 30


def test_i1_default_coverage_matrix_is_fail_closed() -> None:
    assembly = _default_assembly()
    coverage = assembly.coverage()
    assert coverage["C1.1"] == "INSTALLED"
    assert coverage["C1.2"] == "INSTALLED"
    assert coverage["C1.3"] == "INSTALLED"
    assert coverage["C2.1"] == "INSTALLED"
    assert coverage["C2.2"] == "INSTALLED"
    assert coverage["C2.3"] == "INSTALLED"
    assert coverage["C4.3"] == "INSTALLED"
    assert coverage["C7.1"] == "UNWIRED_DECLARED"
    assert coverage["C7.2"] == "UNWIRED_DECLARED"
    assert coverage["C7.3"] == "UNWIRED_DECLARED"
    assert coverage["C7.4"] == "UNWIRED_DECLARED"
    assert coverage["C8.3"] == "UNWIRED_DECLARED"
    assert coverage["C9.2"] == "INSTALLED"
    for cell_id in ("C3.1", "C3.2", "C4.1", "C4.2", "C5.2", "C6.1", "C6.2", "C6.3"):
        assert coverage[cell_id] == "FIXTURE_CLOSURE_REQUIRED"
    for cell_id in ("C2.4", "C5.1", "C5.3", "C5.4", "C8.4", "C9.3"):
        assert coverage[cell_id] == "PROJECTOR_WIRING_DECLARED", cell_id
    assert assembly.projector_registry.projectors == ()


def test_i1_closed_coverage_matrix_installs_fixture_gated_cells() -> None:
    assembly = assemble_successor_runtime(
        engine=_engine(),
        options=build_local_offline_fixture_options(),
    )
    coverage = assembly.coverage()
    for cell_id in (
        "C1.1",
        "C1.2",
        "C1.3",
        "C2.1",
        "C2.2",
        "C2.3",
        "C3.1",
        "C3.2",
        "C4.1",
        "C4.2",
        "C4.3",
        "C5.2",
        "C6.1",
        "C6.2",
        "C6.3",
        "C7.1",
        "C7.2",
        "C7.3",
        "C7.4",
        "C8.1",
        "C8.2",
        "C8.3",
        "C8.4",
        "C9.1",
        "C9.2",
        "C9.3",
        "C2.4",
        "C5.1",
        "C5.3",
        "C5.4",
    ):
        assert coverage[cell_id] == "INSTALLED", cell_id
    installed = {item.cell_id for item in assembly.cells if item.status == "INSTALLED"}
    assert installed == set(ALL_I1_CELLS)
    assert len(installed) == 30
    for cell_id in ("C2.4", "C5.1", "C5.3", "C5.4", "C8.4", "C9.3"):
        cell = assembly.by_cell(cell_id)
        assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note
    assert assembly.projector_registry is not None
    assert len(assembly.projector_registry.projectors) == 6
    assert (
        len({projector.key for projector in assembly.projector_registry.projectors})
        == 6
    )


def test_i1_installed_handlers_have_unique_exact_digests() -> None:
    assembly = assemble_successor_runtime(
        engine=_engine(),
        options=build_local_offline_fixture_options(),
    )
    cells, handlers, recovery, kernel_wiring = merge_family_assemblies(
        assembly.families
    )
    assert cells == assembly.cells
    assert handlers == assembly.handlers
    assert recovery == assembly.recovery_handlers
    assert kernel_wiring == assembly.kernel_wiring
    handler_digests = {handler.handler_binding_digest for handler in handlers}
    assert len(handler_digests) == len(handlers)
    kernel_digests = {wiring.binding_digest for wiring in kernel_wiring}
    assert len(kernel_digests) == len(kernel_wiring)
    assert kernel_digests.isdisjoint(handler_digests)
    projector_digests = {
        cell.handler_binding_digest
        for cell in assembly.cells
        if cell.status == "INSTALLED"
        and cell.handler_binding_digest not in handler_digests
        and cell.handler_binding_digest not in kernel_digests
    }
    assert len(projector_digests) == 6
    assert handler_digests.isdisjoint(projector_digests)
    assert kernel_digests.isdisjoint(projector_digests)
    installed = [item for item in assembly.cells if item.status == "INSTALLED"]
    assert installed
    for cell in installed:
        assert cell.handler_binding_digest in (
            handler_digests | kernel_digests | projector_digests
        )
    for family in assembly.families:
        for wiring in family.projector_wiring:
            cell = family.cell(wiring.cell_id)
            if cell.status != "INSTALLED":
                continue
            assert family.projector_registry is not None
            contract = next(
                projector
                for projector in family.projector_registry.projectors
                if projector.key.projector_id == wiring.projector_id
                and projector.projection_id == wiring.projection_id
            )
            assert cell.handler_binding_digest == wiring.registration_digest(contract)


def test_i1_unresolved_cells_never_carry_a_binding_digest() -> None:
    assembly = _default_assembly()
    for cell in assembly.cells:
        if cell.status != "INSTALLED":
            assert cell.handler_binding_digest is None
            assert cell.note, cell.cell_id


def test_i1_c7_rollback_bindings_are_declared_gap_not_invented() -> None:
    c7 = build_c7_assembly()
    for cell_id in ("C7.1", "C7.2", "C7.3", "C7.4"):
        declaration = next(
            item for item in c7.rollback_bindings if item.cell_id == cell_id
        )
        assert declaration.status == "DECLARED_GAP"


def test_i1_c1_and_c9_builders_are_stable() -> None:
    c1 = build_c1_assembly()
    c9 = build_c9_assembly()
    assert c1.coverage()["C1.1"] == "INSTALLED"
    assert c1.coverage()["C1.2"] == "INSTALLED"
    assert c1.coverage()["C1.3"] == "INSTALLED"
    assert c9.coverage()["C9.2"] == "INSTALLED"
    assert c9.coverage()["C9.1"] == "UNWIRED_DECLARED"


def test_i1_compose_node_returns_runtime_node_without_starting_it() -> None:
    assembly = _default_assembly()
    assert assembly.project_scope_digest == local_assembly_scope_digest()
    node = assembly.compose_node(**_node_args(assembly))  # type: ignore[arg-type]
    assert isinstance(node, RuntimeNode)
    assert node.identity.node_id == "node:i1-composition-smoke"
    assert isinstance(node.interpreters, ExactInstalledHandlerResolver)
    handler_digests = {handler.handler_binding_digest for handler in assembly.handlers}
    kernel_digests = {wiring.binding_digest for wiring in assembly.kernel_wiring}
    installed = {
        item.handler_binding_digest
        for item in assembly.cells
        if item.status == "INSTALLED"
        and item.handler_binding_digest in handler_digests | kernel_digests
    }
    assert installed <= set(node.interpreters._by_digest) | kernel_digests
    assert handler_digests <= set(node.interpreters._by_digest)


def test_i1_projector_registry_registration_is_assembly_only() -> None:
    assembly = assemble_successor_runtime(
        engine=_engine(),
        options=build_local_offline_fixture_options(),
    )
    registry = assembly.projector_registry
    assert registry is not None
    assert registry.revision == 0
    assert len(registry.projectors) == 6
    expected_cells = {"C2.4", "C5.1", "C5.3", "C5.4", "C8.4", "C9.3"}
    assert {cell.cell_id for cell in assembly.cells if cell.status == "INSTALLED"} >= (
        expected_cells
    )
    for cell_id in expected_cells:
        cell = assembly.by_cell(cell_id)
        assert cell.handler_binding_digest is not None
        assert "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED" in cell.note


def test_i1_default_projector_keys_fail_closed_in_registry() -> None:
    assembly = _default_assembly()
    assert assembly.projector_registry.projectors == ()
    for cell_id in ("C2.4", "C5.1", "C5.3", "C5.4", "C8.4", "C9.3"):
        assert assembly.by_cell(cell_id).status == "PROJECTOR_WIRING_DECLARED"
        assert assembly.by_cell(cell_id).handler_binding_digest is None


def test_i1_composition_does_not_mount_router_or_run_once() -> None:
    assembly = _default_assembly()
    assert not hasattr(assembly, "router")
    node = assembly.compose_node(**_node_args(assembly))  # type: ignore[arg-type]
    assert not hasattr(node, "run")  # run_once is invoked explicitly only
    assert hasattr(node, "run_once")
