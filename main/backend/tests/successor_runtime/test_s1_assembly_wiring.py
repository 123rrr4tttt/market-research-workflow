"""S1 horizontal port assembly registration tests (ALL-SM-010..013)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.successor_runtime.assembly.s1_horizontal_port_assembly import (
    S1_HORIZONTAL_PORT_STATUS,
    S1HorizontalPortContract,
    build_s1_horizontal_port_registry,
    s1_horizontal_port_registry_digest,
)
from app.successor_runtime.assembly.successor_assembly import (
    assemble_successor_runtime,
)

pytestmark = pytest.mark.unit


def _registry() -> tuple[S1HorizontalPortContract, ...]:
    contracts = build_s1_horizontal_port_registry()
    assert len(contracts) == 4
    return contracts


def test_s1_registry_has_four_exact_horizontal_port_contracts() -> None:
    contracts = _registry()
    assert {item.port_id for item in contracts} == {
        "s1.ALL-SM-010.request_identity.v1",
        "s1.ALL-SM-011.line_event_readback.v1",
        "s1.ALL-SM-012.single_source_guard.v1",
        "s1.ALL-SM-013.quality_promotion.v1",
    }
    assert {item.package_id for item in contracts} == {
        "PKG-ALL-SM-010",
        "PKG-ALL-SM-011",
        "PKG-ALL-SM-012",
        "PKG-ALL-SM-013",
    }
    assert {item.movement_ids[0] for item in contracts} == {
        "ALL-SM-010",
        "ALL-SM-011",
        "ALL-SM-012",
        "ALL-SM-013",
    }
    for item in contracts:
        assert item.status == S1_HORIZONTAL_PORT_STATUS
        assert item.module_ref.startswith(
            "main/backend/app/successor_runtime/capabilities/"
        )
        assert item.test_ref.startswith("main/backend/tests/successor_runtime/")
        assert item.schema_ref


def test_s1_owner_cells_match_closure_plan_placement() -> None:
    contracts = {item.movement_ids[0]: item for item in _registry()}
    assert contracts["ALL-SM-010"].owner_cells == ("C9.1",)
    assert contracts["ALL-SM-011"].owner_cells == ("C5.4",)
    assert contracts["ALL-SM-012"].owner_cells == ("C2.3",)
    assert contracts["ALL-SM-013"].owner_cells == ("C4.1", "C4.2", "C4.3")


def test_s1_registry_authority_ceiling_is_all_false() -> None:
    for item in _registry():
        authority = dict(item.authority_ceiling)
        assert authority == {
            "canonical_write": False,
            "live_provider": False,
            "external_delivery": False,
            "cutover": False,
            "authority_transfer": False,
            "scheduler": False,
            "executor": False,
        }
        assert all(value is False for value in authority.values())


def test_s1_registry_digest_is_deterministic_and_unique() -> None:
    contracts = _registry()
    assert len(s1_horizontal_port_registry_digest(contracts)) == 64
    assert s1_horizontal_port_registry_digest(contracts) == (
        s1_horizontal_port_registry_digest(build_s1_horizontal_port_registry())
    )


def test_serial_assembly_carries_s1_ports_without_changing_cell_coverage() -> None:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:", future=True)
    )
    assert len(assembly.horizontal_ports) == 4
    assert assembly.horizontal_ports == build_s1_horizontal_port_registry()
    assert len(assembly.cells) == 30
    assert len(assembly.coverage()) == 30
