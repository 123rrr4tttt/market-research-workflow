"""Current business registration for four cross-family horizontal ports.

The contracts are declarations carried by the default runtime assembly, not
``RuntimeHandler`` cells.  Their current identity and owners come from the
business families that author the referenced cells.  Former package,
movement, and gap labels remain only as explicit historical provenance and do
not participate in the current projection or digest.  Registration starts no
provider, performs no write, interprets no effect, and grants no authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Literal, TypeAlias

from app.successor_runtime.capabilities import (
    line_event_readback_port,
    quality_promotion_port,
    request_identity_port,
    single_source_guard_port,
)
from app.successor_runtime.capabilities.batch_task_native_contribution import (
    ASSEMBLY_CELL_IDS as BATCH_CELL_IDS,
)
from app.successor_runtime.capabilities.batch_task_native_contribution import (
    DEFAULT_BATCH_TASK_NATIVE_SOURCE,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    ASSEMBLY_CELL_IDS as SOURCE_CELL_IDS,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    DEFAULT_SOURCE_NATIVE_SOURCE,
)
from app.successor_runtime.runtime.task_observation_native_contribution import (
    ASSEMBLY_CELL_IDS as TASK_CELL_IDS,
)
from app.successor_runtime.runtime.task_observation_native_contribution import (
    DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE,
)
from app.successor_runtime.runtime.projection_native_contribution import (
    ASSEMBLY_CELL_IDS as PROJECTION_CELL_IDS,
)
from app.successor_runtime.runtime.projection_native_contribution import (
    DEFAULT_PROJECTION_NATIVE_SOURCE,
)

S1_HORIZONTAL_PORT_REGISTRY_SCHEMA = (
    "mrw.horizontal.port-registry.v2"
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
    """One inspectable current horizontal port declaration.

    ``historical_*`` fields locate the former closure-plan record.  They are
    deliberately excluded from :meth:`to_plain`, the registry digest, and the
    contribution projection.
    """

    port_id: str
    business_owner: str
    business_line_id: str
    owner_cells: tuple[str, ...]
    module_ref: str
    schema_ref: str
    test_ref: str
    historical_package_id: str
    historical_movement_ids: tuple[str, ...]
    historical_gap_ids: tuple[str, ...]
    status: S1HorizontalPortStatus = S1_HORIZONTAL_PORT_STATUS
    authority_ceiling: tuple[tuple[str, bool], ...] = _NO_AUTHORITY

    def __post_init__(self) -> None:
        for name in (
            "port_id",
            "business_owner",
            "business_line_id",
            "module_ref",
            "schema_ref",
            "test_ref",
            "historical_package_id",
        ):
            if (
                not isinstance(getattr(self, name), str)
                or not getattr(self, name).strip()
            ):
                raise ValueError(f"S1HorizontalPortContract.{name} is required")
        if self.status != S1_HORIZONTAL_PORT_STATUS:
            raise ValueError("S1 horizontal port status is not the declared value")
        if (
            not self.owner_cells
            or not self.historical_movement_ids
            or not self.historical_gap_ids
        ):
            raise ValueError("horizontal port requires current cells and historical provenance")
        expected_cells = {
            DEFAULT_PROJECTION_NATIVE_SOURCE.owner: PROJECTION_CELL_IDS,
            DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.owner: TASK_CELL_IDS,
            DEFAULT_SOURCE_NATIVE_SOURCE.owner: SOURCE_CELL_IDS,
            DEFAULT_BATCH_TASK_NATIVE_SOURCE.owner: BATCH_CELL_IDS,
        }.get(self.business_owner)
        if expected_cells is None or self.owner_cells != expected_cells:
            raise ValueError("horizontal port owner cells must come from its family author")
        if self.authority_ceiling != _NO_AUTHORITY:
            raise ValueError("S1 horizontal port cannot grant runtime authority")

    def to_plain(self) -> dict[str, object]:
        return {
            "port_id": self.port_id,
            "business_owner": self.business_owner,
            "business_line_id": self.business_line_id,
            "owner_cells": list(self.owner_cells),
            "module_ref": self.module_ref,
            "schema_ref": self.schema_ref,
            "test_ref": self.test_ref,
            "status": self.status,
            "authority_ceiling": {
                name: value for name, value in self.authority_ceiling
            },
        }


def build_s1_horizontal_port_registry() -> Annotated[
    tuple[S1HorizontalPortContract, ...],
    "kit:prepared-command effect_boundary=successor_runtime.s1_horizontal_port_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Return the four current horizontal port contracts in stable order."""

    return (
        S1HorizontalPortContract(
            port_id="projection.request-identity.port.v2",
            business_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            business_line_id="BL-request-identity",
            owner_cells=PROJECTION_CELL_IDS,
            module_ref=(
                "main/backend/app/successor_runtime/capabilities/"
                "request_identity_port.py"
            ),
            schema_ref=request_identity_port.REQUEST_IDENTITY_PORT_REF,
            test_ref=(
                "main/backend/tests/successor_runtime/test_s1_request_identity.py"
            ),
            historical_package_id="PKG-ALL-SM-010",
            historical_movement_ids=("ALL-SM-010",),
            historical_gap_ids=("GAP-request-identity",),
        ),
        S1HorizontalPortContract(
            port_id="task.observation.line-event-readback.port.v2",
            business_owner=DEFAULT_TASK_OBSERVATION_NATIVE_SOURCE.owner,
            business_line_id="BL-task-readback-metadata",
            owner_cells=TASK_CELL_IDS,
            module_ref=(
                "main/backend/app/successor_runtime/capabilities/"
                "line_event_readback_port.py"
            ),
            schema_ref=line_event_readback_port.SCHEMA_REF,
            test_ref=(
                "main/backend/tests/successor_runtime/test_s1_line_event_readback.py"
            ),
            historical_package_id="PKG-ALL-SM-011",
            historical_movement_ids=("ALL-SM-011",),
            historical_gap_ids=("GAP-task-readback-metadata-line-events",),
        ),
        S1HorizontalPortContract(
            port_id="source.single-source-guard.port.v2",
            business_owner=DEFAULT_SOURCE_NATIVE_SOURCE.owner,
            business_line_id="BL-single-source-guard",
            owner_cells=SOURCE_CELL_IDS,
            module_ref=(
                "main/backend/app/successor_runtime/capabilities/"
                "single_source_guard_port.py"
            ),
            schema_ref=single_source_guard_port.SINGLE_SOURCE_GUARD_DECISION_SCHEMA,
            test_ref=(
                "main/backend/tests/successor_runtime/test_s1_single_source_guard.py"
            ),
            historical_package_id="PKG-ALL-SM-012",
            historical_movement_ids=("ALL-SM-012",),
            historical_gap_ids=("GAP-single-source-guard",),
        ),
        S1HorizontalPortContract(
            port_id="batch.task.quality-promotion-readback.port.v2",
            business_owner=DEFAULT_BATCH_TASK_NATIVE_SOURCE.owner,
            business_line_id="BL-agent-batch-quality-promotion-readback",
            owner_cells=BATCH_CELL_IDS,
            module_ref=(
                "main/backend/app/successor_runtime/capabilities/"
                "quality_promotion_port.py"
            ),
            schema_ref=quality_promotion_port.QUALITY_PROMOTION_PORT_SCHEMA,
            test_ref=(
                "main/backend/tests/successor_runtime/test_s1_quality_promotion.py"
            ),
            historical_package_id="PKG-ALL-SM-013",
            historical_movement_ids=("ALL-SM-013",),
            historical_gap_ids=(
                "GAP-agent-batch-quality-promotion-readback-evidence-omission",
            ),
        ),
    )


def s1_horizontal_port_registry_digest(
    contracts: tuple[S1HorizontalPortContract, ...],
) -> str:
    """Digest only current business identity, locators, and authority declaration."""

    rows = tuple(item.to_plain() for item in contracts)
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
