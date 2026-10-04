"""Current business registry for horizontal read-only/control surfaces.

The surfaces are declarations carried by the default runtime assembly.  Their
current identity, owner, and owner cells come from the business families that
author those cells.  Former package, movement, and gap labels remain only as
explicit historical provenance and do not participate in the current
projection or digest.  Registration mounts no route, interprets no effect,
and grants no runtime authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Literal, TypeAlias

from app.successor_runtime.capabilities.batch_task_native_contribution import (
    ASSEMBLY_CELL_IDS as BATCH_CELL_IDS,
)
from app.successor_runtime.capabilities.batch_task_native_contribution import (
    DEFAULT_BATCH_TASK_NATIVE_SOURCE,
)
from app.successor_runtime.capabilities.knowledge_report_export_audit_evidence_surface import (
    SURFACE_SCHEMA as REPORT_EXPORT_AUDIT_SURFACE_SCHEMA,
)
from app.successor_runtime.capabilities.knowledge_report_quality_trend_evidence_surface import (
    SURFACE_SCHEMA as REPORT_QUALITY_TREND_SURFACE_SCHEMA,
)
from app.successor_runtime.capabilities.search_retrieval_panel import (
    SURFACE_SCHEMA as SEARCH_RETRIEVAL_PANEL_SURFACE_SCHEMA,
)
from app.successor_runtime.capabilities.quality_promotion_port import (
    QUALITY_PROMOTION_PORT_SCHEMA,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    ASSEMBLY_CELL_IDS as SOURCE_CELL_IDS,
)
from app.successor_runtime.capabilities.source_native_contribution import (
    DEFAULT_SOURCE_NATIVE_SOURCE,
)
from app.successor_runtime.capabilities.source_library_worker_readback import (
    SURFACE_SCHEMA as SOURCE_LIBRARY_WORKER_SURFACE_SCHEMA,
)
from app.successor_runtime.ops_domain.base import AUTHORITY_KEYS
from app.successor_runtime.ops_domain.dashboard_admin_surface import (
    SURFACE_SCHEMA as DASHBOARD_ADMIN_SURFACE_SCHEMA,
)
from app.successor_runtime.ops_domain.health_matrix_surface import (
    SURFACE_SCHEMA as HEALTH_MATRIX_SURFACE_SCHEMA,
)
from app.successor_runtime.ops_domain.ops_misc_surface import (
    SURFACE_SCHEMA as OPS_MISC_SURFACE_SCHEMA,
)
from app.successor_runtime.ops_domain.projects_config_surface import (
    SURFACE_SCHEMA as PROJECTS_CONFIG_SURFACE_SCHEMA,
)
from app.successor_runtime.ops_domain.runtime_ops_surface import (
    SURFACE_SCHEMA as RUNTIME_OPS_SURFACE_SCHEMA,
)
from app.successor_runtime.runtime.projection_native_contribution import (
    ASSEMBLY_CELL_IDS as PROJECTION_CELL_IDS,
)
from app.successor_runtime.runtime.projection_native_contribution import (
    DEFAULT_PROJECTION_NATIVE_SOURCE,
)

S2C_DOMAIN_SURFACE_REGISTRY_SCHEMA = (
    "mrw.horizontal.domain-surface-registry.v2"
)
S2C_DOMAIN_SURFACE_STATUS: Literal[
    "DECLARED_TYPED_READONLY_CONTROL_SURFACE_NO_RUNTIME_BINDING"
] = "DECLARED_TYPED_READONLY_CONTROL_SURFACE_NO_RUNTIME_BINDING"
S2cDomainSurfaceStatus: TypeAlias = Literal[
    "DECLARED_TYPED_READONLY_CONTROL_SURFACE_NO_RUNTIME_BINDING"
]

_NO_AUTHORITY: tuple[tuple[str, bool], ...] = tuple(
    (name, False) for name in AUTHORITY_KEYS
)

@dataclass(frozen=True, slots=True)
class S2cOpsDomainSurfaceContract:
    """One inspectable current horizontal/domain surface declaration."""

    surface_id: str
    business_owner: str
    business_line_ids: tuple[str, ...]
    owner_cells: tuple[str, ...]
    module_refs: tuple[str, ...]
    test_refs: tuple[str, ...]
    schema_ref: str
    historical_package_id: str
    historical_movement_ids: tuple[str, ...]
    historical_gap_ids: tuple[str, ...]
    status: S2cDomainSurfaceStatus = S2C_DOMAIN_SURFACE_STATUS
    authority_ceiling: tuple[tuple[str, bool], ...] = _NO_AUTHORITY
    decision_owner: str = ""
    line_disposition: Literal[
        "REIMPLEMENTED_AS",
        "EXPLICITLY_REJECTED",
        "DECLARED_LOSS",
    ] = "REIMPLEMENTED_AS"
    component_decisions: tuple[tuple[str, str], ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        for name in (
            "surface_id",
            "business_owner",
            "schema_ref",
            "historical_package_id",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"S2cOpsDomainSurfaceContract.{name} is required")
        if self.status != S2C_DOMAIN_SURFACE_STATUS:
            raise ValueError("S2c surface status is not the declared value")
        if (
            not self.historical_movement_ids
            or not self.module_refs
            or not self.test_refs
        ):
            raise ValueError("surface requires historical provenance and module/test locators")
        if self.line_disposition not in (
            "REIMPLEMENTED_AS",
            "EXPLICITLY_REJECTED",
            "DECLARED_LOSS",
        ):
            raise ValueError(f"unknown line disposition: {self.line_disposition}")
        if self.authority_ceiling != _NO_AUTHORITY:
            raise ValueError("S2c surface cannot grant runtime authority")
        if not isinstance(self.decision_owner, str) or not self.decision_owner.strip():
            raise ValueError("S2c surface requires an explicit decision_owner")
        if self.decision_owner != self.business_owner:
            raise ValueError("surface decision owner must be its business owner")
        expected_cells = {
            DEFAULT_PROJECTION_NATIVE_SOURCE.owner: PROJECTION_CELL_IDS,
            DEFAULT_SOURCE_NATIVE_SOURCE.owner: SOURCE_CELL_IDS,
            DEFAULT_BATCH_TASK_NATIVE_SOURCE.owner: BATCH_CELL_IDS,
        }.get(self.business_owner)
        if expected_cells is None or self.owner_cells != expected_cells:
            raise ValueError("surface owner cells must come from its family author")

    def to_plain(self) -> dict[str, object]:
        return {
            "surface_id": self.surface_id,
            "business_owner": self.business_owner,
            "business_line_ids": list(self.business_line_ids),
            "owner_cells": list(self.owner_cells),
            "module_refs": list(self.module_refs),
            "test_refs": list(self.test_refs),
            "schema_ref": self.schema_ref,
            "status": self.status,
            "authority_ceiling": {
                name: value for name, value in self.authority_ceiling
            },
            "decision_owner": self.decision_owner,
            "line_disposition": self.line_disposition,
            "component_decisions": [
                {"kind": kind, "decision": decision}
                for kind, decision in self.component_decisions
            ],
            "note": self.note,
        }


def _module_ref(path: str) -> str:
    return "main/backend/app/successor_runtime/" + path


def _test_ref(path: str) -> str:
    return "main/backend/tests/successor_runtime/" + path


def build_s2c_ops_domain_surface_registry() -> Annotated[
    tuple[S2cOpsDomainSurfaceContract, ...],
    "kit:prepared-command effect_boundary=successor_runtime.s2c_ops_domain_surface_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Return the eleven current surface contracts in stable historical order."""

    return (
        S2cOpsDomainSurfaceContract(
            surface_id="projection.projects-config.surface.v2",
            business_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            business_line_ids=("BL-projects-config-workflow",),
            owner_cells=PROJECTION_CELL_IDS,
            module_refs=(_module_ref("ops_domain/projects_config_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=PROJECTS_CONFIG_SURFACE_SCHEMA,
            historical_package_id="PKG-ALL-SM-005",
            historical_movement_ids=("ALL-SM-005",),
            historical_gap_ids=(),
            decision_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            component_decisions=(
                ("project_readback", "REIMPLEMENTED_AS"),
                ("mutation_workflow_execution", "EXPLICITLY_REJECTED"),
            ),
            note="typed read-only/control surface; write execution is no-call",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="projection.dashboard-admin-governance.surface.v2",
            business_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            business_line_ids=("BL-dashboard-admin-governance",),
            owner_cells=PROJECTION_CELL_IDS,
            module_refs=(_module_ref("ops_domain/dashboard_admin_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=DASHBOARD_ADMIN_SURFACE_SCHEMA,
            historical_package_id="PKG-ALL-SM-006",
            historical_movement_ids=("ALL-SM-006",),
            historical_gap_ids=(),
            decision_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            component_decisions=(
                ("dashboard_readback", "REIMPLEMENTED_AS"),
                ("report_from_filter_synthesis", "EXPLICITLY_REJECTED"),
                ("admin_governance_mutation", "EXPLICITLY_REJECTED"),
            ),
            note="report closure and admin/governance mutations carry explicit owners",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="projection.runtime-ops.surface.v2",
            business_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            business_line_ids=("BL-runtime-ops",),
            owner_cells=PROJECTION_CELL_IDS,
            module_refs=(_module_ref("ops_domain/runtime_ops_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=RUNTIME_OPS_SURFACE_SCHEMA,
            historical_package_id="PKG-ALL-SM-008",
            historical_movement_ids=("ALL-SM-008",),
            historical_gap_ids=(),
            decision_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            component_decisions=(
                ("runtime_readback", "REIMPLEMENTED_AS"),
                ("retry_cancel_service_probe_execution", "EXPLICITLY_REJECTED"),
            ),
            note="runtime diagnostics are read/control surfaces only",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="projection.runtime-health-matrix.surface.v2",
            business_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            business_line_ids=("BL-runtime-health-matrix",),
            owner_cells=PROJECTION_CELL_IDS,
            module_refs=(_module_ref("ops_domain/health_matrix_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=HEALTH_MATRIX_SURFACE_SCHEMA,
            historical_package_id="PKG-ALL-SM-017",
            historical_movement_ids=("ALL-SM-017",),
            historical_gap_ids=(),
            decision_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            component_decisions=(
                ("health_matrix_classification", "REIMPLEMENTED_AS"),
                ("probe_execution", "EXPLICITLY_REJECTED"),
            ),
            note="passive matrix classification; no probe is started",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="projection.runtime-health-matrix-closure.surface.v2",
            business_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            business_line_ids=("BL-runtime-health-matrix",),
            owner_cells=PROJECTION_CELL_IDS,
            module_refs=(_module_ref("ops_domain/health_matrix_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=HEALTH_MATRIX_SURFACE_SCHEMA,
            historical_package_id="PKG-ALL-GAP-002",
            historical_movement_ids=("ALL-GAP-002",),
            historical_gap_ids=("GAP-runtime-health-matrix",),
            decision_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            component_decisions=(
                ("separate_surface", "EXPLICITLY_REJECTED"),
                ("integrated_runtime_health_matrix", "REIMPLEMENTED_AS"),
            ),
            note="supplementary health-matrix evidence uses the shared runtime lane",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="projection.operations-readback.surface.v2",
            business_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            business_line_ids=("BL-admin-crawler-cluechain-codexauth-keyword-stats",),
            owner_cells=PROJECTION_CELL_IDS,
            module_refs=(_module_ref("ops_domain/ops_misc_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=OPS_MISC_SURFACE_SCHEMA,
            historical_package_id="PKG-ALL-SM-018",
            historical_movement_ids=("ALL-SM-018",),
            historical_gap_ids=(),
            decision_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            component_decisions=(
                ("admin_raw_data", "REIMPLEMENTED_AS"),
                ("admin_graphs", "REIMPLEMENTED_AS"),
                ("crawler_readback", "REIMPLEMENTED_AS"),
                ("clue_chains_readback", "REIMPLEMENTED_AS"),
                ("codex_auth_structural_status", "REIMPLEMENTED_AS"),
                ("keywords", "REIMPLEMENTED_AS"),
                ("stats", "REIMPLEMENTED_AS"),
                ("skills_invocation", "EXPLICITLY_REJECTED"),
                ("project_customization_execution", "DECLARED_LOSS"),
            ),
            note="per-group typed read-only/rejected/loss record; no silent no-call",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="projection.report-export-audit-evidence.surface.v2",
            business_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            business_line_ids=("BL-dashboard-llm-report-detail-export-audit",),
            owner_cells=PROJECTION_CELL_IDS,
            module_refs=(
                _module_ref("capabilities/knowledge_report_export_audit_evidence_surface.py"),
            ),
            test_refs=(
                _test_ref("test_s2c_evidence_consumption.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=REPORT_EXPORT_AUDIT_SURFACE_SCHEMA,
            historical_package_id="PKG-ALL-SM-014",
            historical_movement_ids=("ALL-SM-014",),
            historical_gap_ids=(),
            decision_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            component_decisions=(
                ("audit_evidence_consumption", "REIMPLEMENTED_AS"),
                ("durable_audit_write", "EXPLICITLY_REJECTED"),
            ),
            note="evidence consumption/no-call decision; never a durable writer",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="projection.report-quality-trend-evidence.surface.v2",
            business_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            business_line_ids=("BL-llm-report-trend-quality-records",),
            owner_cells=PROJECTION_CELL_IDS,
            module_refs=(
                _module_ref("capabilities/knowledge_report_quality_trend_evidence_surface.py"),
            ),
            test_refs=(
                _test_ref("test_s2c_evidence_consumption.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=REPORT_QUALITY_TREND_SURFACE_SCHEMA,
            historical_package_id="PKG-ALL-SM-016",
            historical_movement_ids=("ALL-SM-016",),
            historical_gap_ids=(),
            decision_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            component_decisions=(
                ("trend_evidence_consumption", "REIMPLEMENTED_AS"),
                ("durable_trend_aggregation", "EXPLICITLY_REJECTED"),
            ),
            note="degraded/local readback is never durable report proof",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="projection.search-retrieval-readback.surface.v2",
            business_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            business_line_ids=("BL-search-discovery-index-worker-readback",),
            owner_cells=PROJECTION_CELL_IDS,
            module_refs=(_module_ref("capabilities/search_retrieval_panel.py"),),
            test_refs=(
                _test_ref("test_s2c_worker_and_retrieval_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=SEARCH_RETRIEVAL_PANEL_SURFACE_SCHEMA,
            historical_package_id="PKG-ALL-SM-003",
            historical_movement_ids=("ALL-SM-003",),
            historical_gap_ids=(),
            decision_owner=DEFAULT_PROJECTION_NATIVE_SOURCE.owner,
            component_decisions=(
                ("retrieval_panel_contract", "REIMPLEMENTED_AS"),
                ("untracked_panel_ui", "DECLARED_LOSS"),
                ("search_index_write", "EXPLICITLY_REJECTED"),
            ),
            note="backend-typed panel contract; donor UI bytes are not adopted",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="source.worker-readback.surface.v2",
            business_owner=DEFAULT_SOURCE_NATIVE_SOURCE.owner,
            business_line_ids=("BL-source-library-resource-worker-readback",),
            owner_cells=SOURCE_CELL_IDS,
            module_refs=(
                _module_ref("capabilities/source_library_worker_readback.py"),
            ),
            test_refs=(
                _test_ref("test_s2c_worker_and_retrieval_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=SOURCE_LIBRARY_WORKER_SURFACE_SCHEMA,
            historical_package_id="PKG-ALL-SM-004",
            historical_movement_ids=("ALL-SM-004",),
            historical_gap_ids=(),
            decision_owner=DEFAULT_SOURCE_NATIVE_SOURCE.owner,
            component_decisions=(
                ("worker_readback", "REIMPLEMENTED_AS"),
                ("provider_dispatch", "EXPLICITLY_REJECTED"),
            ),
            note="admitted guard boundary is readback only; dispatch count stays 0",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="batch.task.quality-promotion-readback.surface.v2",
            business_owner=DEFAULT_BATCH_TASK_NATIVE_SOURCE.owner,
            business_line_ids=("BL-agent-batch-quality-promotion-readback",),
            owner_cells=BATCH_CELL_IDS,
            module_refs=(_module_ref("capabilities/quality_promotion_port.py"),),
            test_refs=(
                _test_ref("test_s1_quality_promotion.py"),
                _test_ref("test_s2_quality_promotion.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=QUALITY_PROMOTION_PORT_SCHEMA,
            historical_package_id="PKG-ALL-GAP-001",
            historical_movement_ids=("ALL-GAP-001",),
            historical_gap_ids=(
                "GAP-agent-batch-quality-promotion-readback-evidence-omission",
            ),
            decision_owner=DEFAULT_BATCH_TASK_NATIVE_SOURCE.owner,
            component_decisions=(
                ("separate_surface", "EXPLICITLY_REJECTED"),
                ("integrated_quality_promotion_port", "REIMPLEMENTED_AS"),
            ),
            note="evidence-omission readback uses the shared quality-promotion port",
        ),
    )


def s2c_ops_domain_surface_registry_digest(
    contracts: tuple[S2cOpsDomainSurfaceContract, ...],
) -> str:
    """Digest only current business identity, locators, and authority declaration."""

    rows = tuple(item.to_plain() for item in contracts)
    payload = {
        "schema": S2C_DOMAIN_SURFACE_REGISTRY_SCHEMA,
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
    "S2C_DOMAIN_SURFACE_REGISTRY_SCHEMA",
    "S2C_DOMAIN_SURFACE_STATUS",
    "S2cDomainSurfaceStatus",
    "S2cOpsDomainSurfaceContract",
    "build_s2c_ops_domain_surface_registry",
    "s2c_ops_domain_surface_registry_digest",
]
