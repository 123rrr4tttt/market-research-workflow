"""Horizontal S1/S2c native catalog tests (inert, no runtime binding)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.successor_runtime.assembly.s1_horizontal_port_assembly import (
    build_s1_horizontal_port_registry,
)
from app.successor_runtime.assembly.s2c_ops_domain_surface_assembly import (
    build_s2c_ops_domain_surface_registry,
)
from mrw_functorial_kit.contributions.horizontal import (
    HORIZONTAL_RULE_ID,
    HorizontalNativeSource,
)
from mrw_functorial_kit.contributions.horizontal_catalog import (
    horizontal_native_catalog,
)

pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).parents[2]
KIT_ROOT = BACKEND_ROOT.parents[1] / "src" / "mrw_functorial_kit" / "contributions"


def test_horizontal_catalog_has_ordered_s1_then_s2c_native() -> None:
    assert len(horizontal_native_catalog) == 2
    s1, s2c = horizontal_native_catalog
    assert s1.definition.ports and not s1.definition.surfaces
    assert s2c.definition.surfaces and not s2c.definition.ports
    assert tuple(item.port_id for item in s1.definition.ports) == tuple(
        item.port_id for item in build_s1_horizontal_port_registry()
    )
    assert tuple(item.surface_id for item in s2c.definition.surfaces) == tuple(
        item.surface_id for item in build_s2c_ops_domain_surface_registry()
    )


def test_horizontal_projection_preserves_registry_identity_and_ceiling() -> None:
    s1, s2c = horizontal_native_catalog
    s1_ids = tuple(item.id for item in s1.projection.objects)
    s2c_ids = tuple(item.id for item in s2c.projection.objects)
    assert s1_ids == tuple(item.port_id for item in build_s1_horizontal_port_registry())
    assert s2c_ids == tuple(
        item.surface_id for item in build_s2c_ops_domain_surface_registry()
    )
    expected_ceiling = build_s1_horizontal_port_registry()[0].authority_ceiling
    assert s1.projection.ports[0]["authority_ceiling"] == dict(expected_ceiling)
    assert all(value is False for _, value in expected_ceiling)
    assert s1.projection.id == "mrw.horizontal.port-registry.v2"
    assert s2c.projection.id == "mrw.horizontal.domain-surface-registry.v2"
    assert s1.projection.owner == "runtime.horizontal-port-registry.v2"
    assert s2c.projection.owner == "runtime.horizontal-domain-surface-registry.v2"


def test_horizontal_projection_uses_business_owners_and_current_references() -> None:
    s1, s2c = horizontal_native_catalog
    contracts = (*s1.definition.ports, *s2c.definition.surfaces)
    objects = (*s1.projection.objects, *s2c.projection.objects)

    assert tuple(item.owner for item in objects) == tuple(
        contract.business_owner for contract in contracts
    )
    assert all(item.id.endswith(".v2") for item in objects)
    assert all(
        "ALL-" not in item.id and not item.id.startswith(("s1.", "s2c."))
        for item in objects
    )
    for contract, item in zip(contracts, objects, strict=True):
        assert contract.schema_ref in item.references
        assert set(item.references).isdisjoint(contract.historical_movement_ids)
        assert set(item.references).isdisjoint(contract.historical_gap_ids)


def test_horizontal_assembly_is_inert_read_only_binding() -> None:
    for native in horizontal_native_catalog:
        binding = native.assemble(None)
        assert not isinstance(binding, Exception)
        assert isinstance(binding.definition, HorizontalNativeSource)
        assert all(value is False for _, value in binding.authority_ceiling)


def test_horizontal_source_does_not_copy_rows_or_schema_strings() -> None:
    text = "\n".join(
        path.read_text()
        for path in (
            KIT_ROOT / "horizontal.py",
            KIT_ROOT / "horizontal_catalog.py",
        )
    )
    assert "ALL-SM-" not in text
    assert "all_lines.s1_horizontal_port_registry" not in text
    assert "all_lines.s2c_domain_surface_registry" not in text
    assert HORIZONTAL_RULE_ID == "mrw.horizontal.native-rule.v2"
