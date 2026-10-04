"""S2c horizontal/domain surface assembly wiring tests."""

from __future__ import annotations

import dataclasses
import json

import pytest
from sqlalchemy import create_engine

from app.successor_runtime.assembly.s2c_ops_domain_surface_assembly import (
    S2C_DOMAIN_SURFACE_REGISTRY_SCHEMA,
    S2C_DOMAIN_SURFACE_STATUS,
    S2cOpsDomainSurfaceContract,
    build_s2c_ops_domain_surface_registry,
    s2c_ops_domain_surface_registry_digest,
)
from app.successor_runtime.runtime.projection_native_contribution import (
    ASSEMBLY_CELL_IDS as PROJECTION_CELL_IDS,
    DEFAULT_PROJECTION_NATIVE_SOURCE,
)
from app.successor_runtime.assembly.successor_assembly import (
    assemble_successor_runtime,
)
from app.successor_runtime.capabilities.batch_task_native_contribution import (
    ASSEMBLY_CELL_IDS as BATCH_CELL_IDS,
    DEFAULT_BATCH_TASK_NATIVE_SOURCE,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    ASSEMBLY_CELL_IDS as SOURCE_CELL_IDS,
    DEFAULT_SOURCE_NATIVE_SOURCE,
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


def test_registry_covers_eleven_current_business_surfaces() -> None:
    contracts = _registry()
    assert {item.surface_id for item in contracts} == {
        "projection.projects-config.surface.v2",
        "projection.dashboard-admin-governance.surface.v2",
        "projection.runtime-ops.surface.v2",
        "projection.runtime-health-matrix.surface.v2",
        "projection.runtime-health-matrix-closure.surface.v2",
        "projection.operations-readback.surface.v2",
        "projection.report-export-audit-evidence.surface.v2",
        "projection.report-quality-trend-evidence.surface.v2",
        "projection.search-retrieval-readback.surface.v2",
        "source.worker-readback.surface.v2",
        "batch.task.quality-promotion-readback.surface.v2",
    }
    assert S2C_DOMAIN_SURFACE_REGISTRY_SCHEMA == (
        "mrw.horizontal.domain-surface-registry.v2"
    )
    assert {
        item.historical_movement_ids[0] for item in contracts
    } == REMAINING_MOVEMENT_IDS
    for item in contracts:
        assert item.status == S2C_DOMAIN_SURFACE_STATUS
        assert item.line_disposition == "REIMPLEMENTED_AS"
        assert item.decision_owner == item.business_owner
        assert item.schema_ref
        assert all(
            ref.startswith("main/backend/app/successor_runtime/")
            for ref in item.module_refs
        )
        assert all(
            ref.startswith("main/backend/tests/successor_runtime/")
            for ref in item.test_refs
        )


def test_surface_owners_and_cells_come_from_family_authors() -> None:
    contracts = {item.surface_id: item for item in _registry()}
    source = contracts["source.worker-readback.surface.v2"]
    batch = contracts["batch.task.quality-promotion-readback.surface.v2"]
    projection = tuple(
        item
        for item in contracts.values()
        if item not in (source, batch)
    )

    assert source.business_owner == DEFAULT_SOURCE_NATIVE_SOURCE.owner
    assert source.owner_cells == SOURCE_CELL_IDS
    assert batch.business_owner == DEFAULT_BATCH_TASK_NATIVE_SOURCE.owner
    assert batch.owner_cells == BATCH_CELL_IDS
    assert all(
        item.business_owner == DEFAULT_PROJECTION_NATIVE_SOURCE.owner for item in projection
    )
    assert all(item.owner_cells == PROJECTION_CELL_IDS for item in projection)


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


def test_historical_provenance_is_excluded_from_current_plain_and_digest() -> None:
    contracts = _registry()
    current_plain = json.dumps(
        [item.to_plain() for item in contracts],
        sort_keys=True,
    )
    assert all(
        key not in contracts[0].to_plain()
        for key in ("package_id", "movement_ids", "gap_ids", "historical_package_id")
    )
    assert all(marker not in current_plain for marker in ("PKG-", "ALL-SM-", "ALL-GAP-"))
    assert "B-recheck" not in current_plain
    assert "S2c decision owner" not in current_plain
    assert "folded_into_all_sm" not in current_plain

    changed_history = (
        dataclasses.replace(
            contracts[0],
            historical_package_id="historical-package-locator",
            historical_movement_ids=("historical-movement-locator",),
            historical_gap_ids=("historical-gap-locator",),
        ),
        *contracts[1:],
    )
    assert s2c_ops_domain_surface_registry_digest(changed_history) == (
        s2c_ops_domain_surface_registry_digest(contracts)
    )


def test_serial_assembly_carries_s2c_surfaces_without_cell_change() -> None:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:", future=True)
    )
    assert len(assembly.cells) == 27
    assert len(assembly.coverage()) == 27
    assert len(assembly.domain_surfaces) == 11
    assert {item.surface_id for item in assembly.domain_surfaces} == {
        item.surface_id for item in build_s2c_ops_domain_surface_registry()
    }
    assert assembly.horizontal_ports
