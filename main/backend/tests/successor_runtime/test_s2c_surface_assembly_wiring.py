"""S2c horizontal/domain surface assembly wiring tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.successor_runtime.assembly.s2c_ops_domain_surface_assembly import (
    S2C_DOMAIN_SURFACE_STATUS,
    S2cOpsDomainSurfaceContract,
    build_s2c_ops_domain_surface_registry,
    s2c_ops_domain_surface_registry_digest,
)
from app.successor_runtime.assembly.successor_assembly import (
    assemble_successor_runtime,
)

pytestmark = pytest.mark.unit

REMAINING_MOVEMENT_IDS = {
    "ALL-SM-003",
    "ALL-SM-004",
    "ALL-SM-005",
    "ALL-SM-006",
    "ALL-SM-008",
    "ALL-SM-014",
    "ALL-SM-016",
    "ALL-SM-017",
    "ALL-SM-018",
    "ALL-GAP-001",
    "ALL-GAP-002",
}


def _registry() -> tuple[S2cOpsDomainSurfaceContract, ...]:
    contracts = build_s2c_ops_domain_surface_registry()
    assert len(contracts) == 11
    return contracts


def test_s2c_registry_covers_all_eleven_remaining_movements() -> None:
    contracts = _registry()
    assert {item.movement_ids[0] for item in contracts} == REMAINING_MOVEMENT_IDS
    assert {item.package_id for item in contracts} == {
        f"PKG-{movement}" for movement in REMAINING_MOVEMENT_IDS
    }
    for item in contracts:
        assert item.status == S2C_DOMAIN_SURFACE_STATUS
        assert item.owner_cells == ("C9.1",)
        assert item.line_disposition == "REIMPLEMENTED_AS"
        assert item.decision_owner
        assert item.schema_ref
        assert all(
            ref.startswith("main/backend/app/successor_runtime/")
            for ref in item.module_refs
        )
        assert all(
            ref.startswith("main/backend/tests/successor_runtime/")
            for ref in item.test_refs
        )


def test_s2c_registry_authority_is_all_false() -> None:
    expected = {
        "canonical_write": False,
        "live_provider": False,
        "external_delivery": False,
        "cutover": False,
        "authority_transfer": False,
        "scheduler": False,
        "executor": False,
        "credential_read": False,
    }
    for item in _registry():
        assert dict(item.authority_ceiling) == expected


def test_s2c_registry_digest_is_deterministic() -> None:
    contracts = _registry()
    assert len(s2c_ops_domain_surface_registry_digest(contracts)) == 64
    assert s2c_ops_domain_surface_registry_digest(contracts) == (
        s2c_ops_domain_surface_registry_digest(build_s2c_ops_domain_surface_registry())
    )


def test_serial_assembly_carries_s2c_surfaces_without_cell_change() -> None:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:", future=True)
    )
    assert len(assembly.cells) == 30
    assert len(assembly.coverage()) == 30
    assert len(assembly.domain_surfaces) == 11
    assert {item.movement_ids[0] for item in assembly.domain_surfaces} == (
        REMAINING_MOVEMENT_IDS
    )
    assert assembly.horizontal_ports
