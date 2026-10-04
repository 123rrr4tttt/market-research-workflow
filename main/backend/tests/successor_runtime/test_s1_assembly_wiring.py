"""Current horizontal port assembly registration tests."""

from __future__ import annotations

import dataclasses
import json

import pytest
from sqlalchemy import create_engine

from app.successor_runtime.assembly.s1_horizontal_port_assembly import (
    S1_HORIZONTAL_PORT_REGISTRY_SCHEMA,
    S1_HORIZONTAL_PORT_STATUS,
    S1HorizontalPortContract,
    build_s1_horizontal_port_registry,
    s1_horizontal_port_registry_digest,
)
from app.successor_runtime.runtime.task_observation_native_contribution import (
    ASSEMBLY_CELL_IDS as TASK_CELL_IDS,
    DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
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


def _registry() -> tuple[S1HorizontalPortContract, ...]:
    contracts = build_s1_horizontal_port_registry()
    assert len(contracts) == 4
    return contracts


def test_registry_has_four_current_business_port_contracts() -> None:
    contracts = _registry()
    assert {item.port_id for item in contracts} == {
        "projection.request-identity.port.v2",
        "task.observation.line-event-readback.port.v2",
        "source.single-source-guard.port.v2",
        "batch.task.quality-promotion-readback.port.v2",
    }
    assert S1_HORIZONTAL_PORT_REGISTRY_SCHEMA == "mrw.horizontal.port-registry.v2"
    for item in contracts:
        assert item.status == S1_HORIZONTAL_PORT_STATUS
        assert item.module_ref.startswith(
            "main/backend/app/successor_runtime/capabilities/"
        )
        assert item.test_ref.startswith("main/backend/tests/successor_runtime/")
        assert item.schema_ref


def test_owner_cells_and_owners_come_from_family_authors() -> None:
    contracts = {item.port_id: item for item in _registry()}
    assert contracts["projection.request-identity.port.v2"].owner_cells == PROJECTION_CELL_IDS
    assert contracts["projection.request-identity.port.v2"].business_owner == (
        DEFAULT_PROJECTION_NATIVE_SOURCE.owner
    )
    assert contracts["task.observation.line-event-readback.port.v2"].owner_cells == TASK_CELL_IDS
    assert contracts["task.observation.line-event-readback.port.v2"].business_owner == (
        DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.owner
    )
    assert contracts["source.single-source-guard.port.v2"].owner_cells == SOURCE_CELL_IDS
    assert contracts["source.single-source-guard.port.v2"].business_owner == (
        DEFAULT_SOURCE_NATIVE_SOURCE.owner
    )
    assert contracts["batch.task.quality-promotion-readback.port.v2"].owner_cells == BATCH_CELL_IDS
    assert contracts["batch.task.quality-promotion-readback.port.v2"].business_owner == (
        DEFAULT_BATCH_TASK_NATIVE_SOURCE.owner
    )


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
    assert all(marker not in current_plain for marker in ("PKG-", "ALL-SM-", "GAP-"))

    changed_history = (
        dataclasses.replace(
            contracts[0],
            historical_package_id="historical-package-locator",
            historical_movement_ids=("historical-movement-locator",),
            historical_gap_ids=("historical-gap-locator",),
        ),
        *contracts[1:],
    )
    assert s1_horizontal_port_registry_digest(changed_history) == (
        s1_horizontal_port_registry_digest(contracts)
    )


def test_serial_assembly_carries_s1_ports_without_changing_cell_coverage() -> None:
    assembly = assemble_successor_runtime(
        engine=create_engine("sqlite+pysqlite:///:memory:", future=True)
    )
    assert len(assembly.horizontal_ports) == 4
    assert assembly.horizontal_ports == build_s1_horizontal_port_registry()
    assert len(assembly.cells) == 27
    assert len(assembly.coverage()) == 27
