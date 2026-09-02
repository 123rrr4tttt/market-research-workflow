"""S1 horizontal port registration for the all-lines successor plan.

The four S1 ports are cross-family typed contracts rather than
``RuntimeHandler`` cells.  This module records the exact successor module,
schema reference, movement/package binding, target cells and fail-closed
authority ceiling for ALL-SM-010 through ALL-SM-013.  Registration is
assembly-level bookkeeping: no live provider is started, no canonical write
is performed, no runtime effect is interpreted and no authority is granted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, TypeAlias

from app.successor_runtime.capabilities import (
    line_event_readback_port,
    quality_promotion_port,
    request_identity_port,
    single_source_guard_port,
)

S1_HORIZONTAL_PORT_REGISTRY_SCHEMA = (
    "mrw.functorial_successor.all_lines.s1_horizontal_port_registry.v1"
)
S1_HORIZONTAL_PORT_STATUS: Literal["DECLARED_PURE_PORT_NO_RUNTIME_BINDING"] = (
    "DECLARED_PURE_PORT_NO_RUNTIME_BINDING"
)
S1HorizontalPortStatus: TypeAlias = Literal["DECLARED_PURE_PORT_NO_RUNTIME_BINDING"]

_NO_AUTHORITY: tuple[tuple[str, bool], ...] = (
    ("canonical_write", False),
    ("live_provider", False),
    ("external_delivery", False),
    ("cutover", False),
    ("authority_transfer", False),
    ("scheduler", False),
    ("executor", False),
)


@dataclass(frozen=True, slots=True)
class S1HorizontalPortContract:
    """One inspectable S1 horizontal port binding in the successor assembly."""

    port_id: str
    package_id: str
    movement_ids: tuple[str, ...]
    business_line_id: str
    gap_ids: tuple[str, ...]
    owner_cells: tuple[str, ...]
    module_ref: str
    schema_ref: str
    test_ref: str
    status: S1HorizontalPortStatus = S1_HORIZONTAL_PORT_STATUS
    authority_ceiling: tuple[tuple[str, bool], ...] = _NO_AUTHORITY

    def __post_init__(self) -> None:
        for name in (
            "port_id",
            "package_id",
            "business_line_id",
            "module_ref",
            "schema_ref",
            "test_ref",
        ):
            if (
                not isinstance(getattr(self, name), str)
                or not getattr(self, name).strip()
            ):
                raise ValueError(f"S1HorizontalPortContract.{name} is required")
        if self.status != S1_HORIZONTAL_PORT_STATUS:
            raise ValueError("S1 horizontal port status is not the declared value")
        if not self.movement_ids or not self.owner_cells or not self.gap_ids:
            raise ValueError("S1 horizontal port requires movement/gap/cell bindings")
        if self.authority_ceiling != _NO_AUTHORITY:
            raise ValueError("S1 horizontal port cannot grant runtime authority")

    def to_plain(self) -> dict[str, object]:
        return {
            "port_id": self.port_id,
            "package_id": self.package_id,
            "movement_ids": list(self.movement_ids),
            "business_line_id": self.business_line_id,
            "gap_ids": list(self.gap_ids),
            "owner_cells": list(self.owner_cells),
            "module_ref": self.module_ref,
            "schema_ref": self.schema_ref,
            "test_ref": self.test_ref,
            "status": self.status,
            "authority_ceiling": {
                name: value for name, value in self.authority_ceiling
            },
        }


def build_s1_horizontal_port_registry() -> tuple[S1HorizontalPortContract, ...]:
    """Return the four S1 horizontal port contracts in package order."""

    return (
        S1HorizontalPortContract(
            port_id="s1.ALL-SM-010.request_identity.v1",
            package_id="PKG-ALL-SM-010",
            movement_ids=("ALL-SM-010",),
            business_line_id="BL-request-identity",
            gap_ids=("GAP-request-identity",),
            owner_cells=("C9.1",),
            module_ref=(
                "main/backend/app/successor_runtime/capabilities/"
                "request_identity_port.py"
            ),
            schema_ref=request_identity_port.REQUEST_IDENTITY_PORT_REF,
            test_ref=(
                "main/backend/tests/successor_runtime/test_s1_request_identity.py"
            ),
        ),
        S1HorizontalPortContract(
            port_id="s1.ALL-SM-011.line_event_readback.v1",
            package_id="PKG-ALL-SM-011",
            movement_ids=("ALL-SM-011",),
            business_line_id="BL-task-readback-metadata",
            gap_ids=("GAP-task-readback-metadata-line-events",),
            owner_cells=("C5.4",),
            module_ref=(
                "main/backend/app/successor_runtime/capabilities/"
                "line_event_readback_port.py"
            ),
            schema_ref=line_event_readback_port.SCHEMA_REF,
            test_ref=(
                "main/backend/tests/successor_runtime/test_s1_line_event_readback.py"
            ),
        ),
        S1HorizontalPortContract(
            port_id="s1.ALL-SM-012.single_source_guard.v1",
            package_id="PKG-ALL-SM-012",
            movement_ids=("ALL-SM-012",),
            business_line_id="BL-single-source-guard",
            gap_ids=("GAP-single-source-guard",),
            owner_cells=("C2.3",),
            module_ref=(
                "main/backend/app/successor_runtime/capabilities/"
                "single_source_guard_port.py"
            ),
            schema_ref=single_source_guard_port.SINGLE_SOURCE_GUARD_DECISION_SCHEMA,
            test_ref=(
                "main/backend/tests/successor_runtime/test_s1_single_source_guard.py"
            ),
        ),
        S1HorizontalPortContract(
            port_id="s1.ALL-SM-013.quality_promotion.v1",
            package_id="PKG-ALL-SM-013",
            movement_ids=("ALL-SM-013",),
            business_line_id="BL-agent-batch-quality-promotion-readback",
            gap_ids=("GAP-agent-batch-quality-promotion-readback-evidence-omission",),
            owner_cells=("C4.1", "C4.2", "C4.3"),
            module_ref=(
                "main/backend/app/successor_runtime/capabilities/"
                "quality_promotion_port.py"
            ),
            schema_ref=quality_promotion_port.QUALITY_PROMOTION_PORT_SCHEMA,
            test_ref=(
                "main/backend/tests/successor_runtime/test_s1_quality_promotion.py"
            ),
        ),
    )


def s1_horizontal_port_registry_digest(
    contracts: tuple[S1HorizontalPortContract, ...],
) -> str:
    """Deterministic registry digest over port_id, schema_ref and bindings."""

    rows = tuple(
        {
            "port_id": item.port_id,
            "package_id": item.package_id,
            "movement_ids": list(item.movement_ids),
            "schema_ref": item.schema_ref,
            "owner_cells": list(item.owner_cells),
        }
        for item in contracts
    )
    payload = {
        "schema": S1_HORIZONTAL_PORT_REGISTRY_SCHEMA,
        "rows": rows,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "S1_HORIZONTAL_PORT_REGISTRY_SCHEMA",
    "S1_HORIZONTAL_PORT_STATUS",
    "S1HorizontalPortContract",
    "S1HorizontalPortStatus",
    "build_s1_horizontal_port_registry",
    "s1_horizontal_port_registry_digest",
]
