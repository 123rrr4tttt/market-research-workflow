"""S2c horizontal/domain surface registry for the all-lines successor plan.

The S2c package lands the remaining all-lines blockers as typed read-only or
control-plane surfaces inside ``successor_runtime``.  This module records the
exact successor module, schema reference, movement/package binding, target
cell and fail-closed authority ceiling for every S2c closure.  Registration
is assembly-level bookkeeping: no route is mounted, no runtime effect is
interpreted and no authority is granted.  It does not alter ``ALL_I1_CELLS``
or the 30-cell coverage topology; the surfaces are carried as horizontal
domain records of the serial successor assembly under the C9.1 namespace.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, TypeAlias

from app.successor_runtime.capabilities.c8_report_export_audit_evidence_surface import (
    SURFACE_SCHEMA as C8_EXPORT_AUDIT_SURFACE_SCHEMA,
)
from app.successor_runtime.capabilities.c8_report_quality_trend_evidence_surface import (
    SURFACE_SCHEMA as C8_TREND_SURFACE_SCHEMA,
)
from app.successor_runtime.capabilities.c9_2_search_retrieval_panel import (
    SURFACE_SCHEMA as C9_2_SEARCH_RETRIEVAL_SURFACE_SCHEMA,
)
from app.successor_runtime.capabilities.quality_promotion_port import (
    QUALITY_PROMOTION_PORT_SCHEMA,
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

S2C_DOMAIN_SURFACE_REGISTRY_SCHEMA = (
    "mrw.functorial_successor.all_lines.s2c_ops_domain_surface_registry.v1"
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

_DECISION_OWNER_OWNERS: dict[str, str] = {
    "ALL-SM-003": "MRW search/discovery worker lane owner (B-recheck); S2c decision owner",
    "ALL-SM-004": "MRW source-library/resource lane owner (B-recheck); S2c decision owner",
    "ALL-SM-005": "MRW project/config workflow owner (B-recheck); S2c decision owner",
    "ALL-SM-006": "MRW dashboard/admin/governance owner (B-recheck); S2c decision owner",
    "ALL-SM-008": "MRW runtime ops owner (B-recheck); S2c decision owner",
    "ALL-SM-014": "MRW dashboard/report owner (B-recheck); S2c decision owner",
    "ALL-SM-016": "MRW report trend owner (B-recheck); S2c decision owner",
    "ALL-SM-017": "MRW runtime ops owner (B-recheck); S2c decision owner",
    "ALL-SM-018": "MRW admin/ops owner (B-recheck); S2c decision owner",
    "ALL-GAP-001": "MRW agent-batch owner (B-recheck); S2c decision owner",
    "ALL-GAP-002": "MRW runtime ops owner (B-recheck); S2c decision owner",
}


@dataclass(frozen=True, slots=True)
class S2cOpsDomainSurfaceContract:
    """One inspectable S2c horizontal/domain surface binding."""

    surface_id: str
    package_id: str
    movement_ids: tuple[str, ...]
    business_line_ids: tuple[str, ...]
    gap_ids: tuple[str, ...]
    owner_cells: tuple[str, ...]
    module_refs: tuple[str, ...]
    test_refs: tuple[str, ...]
    schema_ref: str
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
        for name in ("surface_id", "package_id", "schema_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"S2cOpsDomainSurfaceContract.{name} is required")
        if self.status != S2C_DOMAIN_SURFACE_STATUS:
            raise ValueError("S2c surface status is not the declared value")
        if not self.movement_ids or not self.module_refs or not self.test_refs:
            raise ValueError("S2c surface requires movement/module/test bindings")
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
        if self.owner_cells != ("C9.1",):
            raise ValueError("S2c surfaces are carried under the C9.1 namespace")

    def to_plain(self) -> dict[str, object]:
        return {
            "surface_id": self.surface_id,
            "package_id": self.package_id,
            "movement_ids": list(self.movement_ids),
            "business_line_ids": list(self.business_line_ids),
            "gap_ids": list(self.gap_ids),
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


def build_s2c_ops_domain_surface_registry() -> tuple[S2cOpsDomainSurfaceContract, ...]:
    """Return the eleven S2c surface contracts in movement order."""

    return (
        S2cOpsDomainSurfaceContract(
            surface_id="s2c.ALL-SM-005.projects_config_surface.v1",
            package_id="PKG-ALL-SM-005",
            movement_ids=("ALL-SM-005",),
            business_line_ids=("BL-projects-config-workflow",),
            gap_ids=(),
            owner_cells=("C9.1",),
            module_refs=(_module_ref("ops_domain/projects_config_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=PROJECTS_CONFIG_SURFACE_SCHEMA,
            decision_owner=_DECISION_OWNER_OWNERS["ALL-SM-005"],
            component_decisions=(
                ("project_readback", "REIMPLEMENTED_AS"),
                ("mutation_workflow_execution", "EXPLICITLY_REJECTED"),
            ),
            note="typed read-only/control surface; write execution is no-call",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="s2c.ALL-SM-006.dashboard_admin_surface.v1",
            package_id="PKG-ALL-SM-006",
            movement_ids=("ALL-SM-006",),
            business_line_ids=("BL-dashboard-admin-governance",),
            gap_ids=(),
            owner_cells=("C9.1",),
            module_refs=(_module_ref("ops_domain/dashboard_admin_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=DASHBOARD_ADMIN_SURFACE_SCHEMA,
            decision_owner=_DECISION_OWNER_OWNERS["ALL-SM-006"],
            component_decisions=(
                ("dashboard_readback", "REIMPLEMENTED_AS"),
                ("report_from_filter_synthesis", "EXPLICITLY_REJECTED"),
                ("admin_governance_mutation", "EXPLICITLY_REJECTED"),
            ),
            note="report closure and admin/governance mutations carry explicit owners",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="s2c.ALL-SM-008.runtime_ops_surface.v1",
            package_id="PKG-ALL-SM-008",
            movement_ids=("ALL-SM-008",),
            business_line_ids=("BL-runtime-ops",),
            gap_ids=(),
            owner_cells=("C9.1",),
            module_refs=(_module_ref("ops_domain/runtime_ops_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=RUNTIME_OPS_SURFACE_SCHEMA,
            decision_owner=_DECISION_OWNER_OWNERS["ALL-SM-008"],
            component_decisions=(
                ("runtime_readback", "REIMPLEMENTED_AS"),
                ("retry_cancel_service_probe_execution", "EXPLICITLY_REJECTED"),
            ),
            note="runtime diagnostics are read/control surfaces only",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="s2c.ALL-SM-017.health_matrix_surface.v1",
            package_id="PKG-ALL-SM-017",
            movement_ids=("ALL-SM-017",),
            business_line_ids=("BL-runtime-health-matrix",),
            gap_ids=(),
            owner_cells=("C9.1",),
            module_refs=(_module_ref("ops_domain/health_matrix_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=HEALTH_MATRIX_SURFACE_SCHEMA,
            decision_owner=_DECISION_OWNER_OWNERS["ALL-SM-017"],
            component_decisions=(
                ("health_matrix_classification", "REIMPLEMENTED_AS"),
                ("probe_execution", "EXPLICITLY_REJECTED"),
            ),
            note="passive matrix classification; no probe is started",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="s2c.ALL-GAP-002.health_matrix_fold.v1",
            package_id="PKG-ALL-GAP-002",
            movement_ids=("ALL-GAP-002",),
            business_line_ids=("BL-runtime-health-matrix",),
            gap_ids=("GAP-runtime-health-matrix",),
            owner_cells=("C9.1",),
            module_refs=(_module_ref("ops_domain/health_matrix_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=HEALTH_MATRIX_SURFACE_SCHEMA,
            decision_owner=_DECISION_OWNER_OWNERS["ALL-GAP-002"],
            component_decisions=(
                ("separate_surface", "EXPLICITLY_REJECTED"),
                ("folded_into_all_sm_008_017", "REIMPLEMENTED_AS"),
            ),
            note="supplementary health-matrix gap folds into the shared lane",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="s2c.ALL-SM-018.ops_misc_surface.v1",
            package_id="PKG-ALL-SM-018",
            movement_ids=("ALL-SM-018",),
            business_line_ids=("BL-admin-crawler-cluechain-codexauth-keyword-stats",),
            gap_ids=(),
            owner_cells=("C9.1",),
            module_refs=(_module_ref("ops_domain/ops_misc_surface.py"),),
            test_refs=(
                _test_ref("test_s2c_ops_domain_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=OPS_MISC_SURFACE_SCHEMA,
            decision_owner=_DECISION_OWNER_OWNERS["ALL-SM-018"],
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
            surface_id="s2c.ALL-SM-014.c8_export_audit_evidence_surface.v1",
            package_id="PKG-ALL-SM-014",
            movement_ids=("ALL-SM-014",),
            business_line_ids=("BL-dashboard-llm-report-detail-export-audit",),
            gap_ids=(),
            owner_cells=("C9.1",),
            module_refs=(
                _module_ref("capabilities/c8_report_export_audit_evidence_surface.py"),
            ),
            test_refs=(
                _test_ref("test_s2c_evidence_consumption.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=C8_EXPORT_AUDIT_SURFACE_SCHEMA,
            decision_owner=_DECISION_OWNER_OWNERS["ALL-SM-014"],
            component_decisions=(
                ("audit_evidence_consumption", "REIMPLEMENTED_AS"),
                ("durable_audit_write", "EXPLICITLY_REJECTED"),
            ),
            note="evidence consumption/no-call decision; never a durable writer",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="s2c.ALL-SM-016.c8_quality_trend_evidence_surface.v1",
            package_id="PKG-ALL-SM-016",
            movement_ids=("ALL-SM-016",),
            business_line_ids=("BL-llm-report-trend-quality-records",),
            gap_ids=(),
            owner_cells=("C9.1",),
            module_refs=(
                _module_ref("capabilities/c8_report_quality_trend_evidence_surface.py"),
            ),
            test_refs=(
                _test_ref("test_s2c_evidence_consumption.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=C8_TREND_SURFACE_SCHEMA,
            decision_owner=_DECISION_OWNER_OWNERS["ALL-SM-016"],
            component_decisions=(
                ("trend_evidence_consumption", "REIMPLEMENTED_AS"),
                ("durable_trend_aggregation", "EXPLICITLY_REJECTED"),
            ),
            note="degraded/local readback is never durable report proof",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="s2c.ALL-SM-003.c9_2_search_retrieval_panel.v1",
            package_id="PKG-ALL-SM-003",
            movement_ids=("ALL-SM-003",),
            business_line_ids=("BL-search-discovery-index-worker-readback",),
            gap_ids=(),
            owner_cells=("C9.1",),
            module_refs=(_module_ref("capabilities/c9_2_search_retrieval_panel.py"),),
            test_refs=(
                _test_ref("test_s2c_worker_and_retrieval_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=C9_2_SEARCH_RETRIEVAL_SURFACE_SCHEMA,
            decision_owner=_DECISION_OWNER_OWNERS["ALL-SM-003"],
            component_decisions=(
                ("retrieval_panel_contract", "REIMPLEMENTED_AS"),
                ("untracked_panel_ui", "DECLARED_LOSS"),
                ("search_index_write", "EXPLICITLY_REJECTED"),
            ),
            note="C9.2 panel contract is backend-typed; donor UI bytes are not adopted",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="s2c.ALL-SM-004.source_library_worker_readback.v1",
            package_id="PKG-ALL-SM-004",
            movement_ids=("ALL-SM-004",),
            business_line_ids=("BL-source-library-resource-worker-readback",),
            gap_ids=(),
            owner_cells=("C9.1",),
            module_refs=(
                _module_ref("capabilities/source_library_worker_readback.py"),
            ),
            test_refs=(
                _test_ref("test_s2c_worker_and_retrieval_surfaces.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=SOURCE_LIBRARY_WORKER_SURFACE_SCHEMA,
            decision_owner=_DECISION_OWNER_OWNERS["ALL-SM-004"],
            component_decisions=(
                ("worker_readback", "REIMPLEMENTED_AS"),
                ("provider_dispatch", "EXPLICITLY_REJECTED"),
            ),
            note="admitted guard boundary is readback only; dispatch count stays 0",
        ),
        S2cOpsDomainSurfaceContract(
            surface_id="s2c.ALL-GAP-001.quality_promotion_gap_fold.v1",
            package_id="PKG-ALL-GAP-001",
            movement_ids=("ALL-GAP-001",),
            business_line_ids=("BL-agent-batch-quality-promotion-readback",),
            gap_ids=("GAP-agent-batch-quality-promotion-readback-evidence-omission",),
            owner_cells=("C9.1",),
            module_refs=(_module_ref("capabilities/quality_promotion_port.py"),),
            test_refs=(
                _test_ref("test_s1_quality_promotion.py"),
                _test_ref("test_s2_quality_promotion.py"),
                _test_ref("test_s2c_surface_assembly_wiring.py"),
            ),
            schema_ref=QUALITY_PROMOTION_PORT_SCHEMA,
            decision_owner=_DECISION_OWNER_OWNERS["ALL-GAP-001"],
            component_decisions=(
                ("separate_surface", "EXPLICITLY_REJECTED"),
                ("folded_into_all_sm_013", "REIMPLEMENTED_AS"),
            ),
            note="evidence-omission gap folds into the ALL-SM-013 shared port",
        ),
    )


def s2c_ops_domain_surface_registry_digest(
    contracts: tuple[S2cOpsDomainSurfaceContract, ...],
) -> str:
    """Deterministic registry digest over surface bindings."""

    rows = tuple(
        {
            "surface_id": item.surface_id,
            "package_id": item.package_id,
            "movement_ids": list(item.movement_ids),
            "schema_ref": item.schema_ref,
            "owner_cells": list(item.owner_cells),
            "line_disposition": item.line_disposition,
        }
        for item in contracts
    )
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
