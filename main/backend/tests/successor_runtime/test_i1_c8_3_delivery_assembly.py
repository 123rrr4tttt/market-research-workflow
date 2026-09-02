"""Focused C8.3 delivery-bridge installation evidence for the closed I1 assembly."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.successor_runtime.assembly.base import C8AssemblyOptions
from app.successor_runtime.assembly.c8_assembly import (
    C8_3_ROLLBACK_REF,
    C8_FAMILY_ID,
)
from app.successor_runtime.assembly.successor_assembly import (
    assemble_successor_runtime,
    build_local_offline_fixture_options,
)

pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]


def _engine():
    return create_engine("sqlite+pysqlite:///:memory:", future=True)


def _closed_assembly():
    options = build_local_offline_fixture_options()
    assembly = assemble_successor_runtime(engine=_engine(), options=options)
    return assembly, options


def _c8_family(assembly):
    matches = tuple(
        family for family in assembly.families if family.family_id == C8_FAMILY_ID
    )
    assert len(matches) == 1
    return matches[0]


def test_i1_c8_3_closed_assembly_installs_delivery_bridge() -> None:
    assembly, options = _closed_assembly()
    assert isinstance(options.c8, C8AssemblyOptions)
    assert options.c8.bundle is not None
    assert options.c8.activation_catalog is not None
    assert options.c8.delivery_interpreter is not None
    cell = assembly.by_cell("C8.3")
    assert cell.status == "INSTALLED"
    assert cell.handler_binding_digest is not None
    assert "reuses build_postgres_c8_delivery_assembly unchanged" in cell.note


def test_i1_c8_3_bridge_structure_and_digest_uniqueness() -> None:
    assembly, options = _closed_assembly()
    family = _c8_family(assembly)
    activation = options.c8.activation_catalog
    entry_digests = {entry.operation_contract_digest for entry in activation.entries}
    assert len(entry_digests) == 5
    bridge_handlers = tuple(
        handler
        for handler in family.handlers
        if handler.operation_contract_digest in entry_digests
    )
    assert len(bridge_handlers) == 5
    assert {handler.operation_contract_digest for handler in bridge_handlers} == (
        entry_digests
    )
    for handler in bridge_handlers:
        assert hasattr(handler, "effect")
        assert hasattr(handler, "verify_admit")
        assert handler.handler_binding_digest is not None
    all_digests = tuple(handler.handler_binding_digest for handler in family.handlers)
    assert len(set(all_digests)) == len(all_digests)
    c8_3_cell = assembly.by_cell("C8.3")
    assert (
        sum(digest == c8_3_cell.handler_binding_digest for digest in all_digests) == 1
    )
    recovery_digests = tuple(
        handler.handler_binding_digest for handler in family.recovery_handlers
    )
    assert len(family.recovery_handlers) == 5
    assert len(set(recovery_digests)) == len(recovery_digests)
    assert set(recovery_digests).isdisjoint(all_digests)


def test_i1_c8_3_rollback_binding_is_present() -> None:
    assembly, _ = _closed_assembly()
    declaration = next(
        item for item in assembly.rollback_bindings if item.cell_id == "C8.3"
    )
    assert declaration.status == "PRESENT"
    assert C8_3_ROLLBACK_REF in declaration.binding_refs
    rollback_path = REPOSITORY_ROOT / C8_3_ROLLBACK_REF
    assert rollback_path.is_file()


def test_i1_c8_3_closure_is_deterministic() -> None:
    first = build_local_offline_fixture_options()
    second = build_local_offline_fixture_options()
    first_entries = {
        entry.operation_contract_digest: entry.interpreter_binding.binding_digest
        for entry in first.c8.activation_catalog.entries
    }
    second_entries = {
        entry.operation_contract_digest: entry.interpreter_binding.binding_digest
        for entry in second.c8.activation_catalog.entries
    }
    assert first_entries == second_entries
    first_assembly = assemble_successor_runtime(engine=_engine(), options=first)
    second_assembly = assemble_successor_runtime(engine=_engine(), options=second)
    assert first_assembly.by_cell("C8.3").handler_binding_digest == (
        second_assembly.by_cell("C8.3").handler_binding_digest
    )


def test_i1_c8_3_default_options_remain_fail_closed() -> None:
    assembly = assemble_successor_runtime(engine=_engine())
    assert assembly.by_cell("C8.3").status == "UNWIRED_DECLARED"
    assert assembly.by_cell("C8.3").handler_binding_digest is None
    family = _c8_family(assembly)
    assert family.handlers == ()
    assert family.recovery_handlers == ()
