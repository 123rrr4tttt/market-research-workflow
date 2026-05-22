from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .graph_projection_contract import GraphProjectionDryRunReport, GraphProjectionRolloutReadinessReport


CONTRACT_VERSION = "graph.live_smoke_readiness.v1"

LIVE_DB_EVIDENCE_FIELDS = (
    "live_db_validated",
    "alembic_current_or_upgrade_run",
    "backfill_graph_nodes_dry_run",
    "backend_data_graph_endpoint_smoke",
    "b_read_parity_checked",
)

FRONTEND_BACKEND_EVIDENCE_FIELDS = (
    "frontend_backend_data_smoke_validated",
    "backend_data_source_live",
    "force3d_canvas_nonblank",
    "force3d_scene_nodes_match_data",
)


@dataclass(frozen=True)
class GraphLiveSmokeStage:
    name: str
    status: str
    passed: bool
    validated: bool
    detail: str
    gaps: list[str]
    evidence_required: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphLiveSmokeReadinessReport:
    contract_version: str
    mode: str
    status: str
    closure_claim: bool
    live_db_validated: bool
    frontend_backend_data_smoke_validated: bool
    database_configured: bool
    ready_for_live_db_dry_run: bool
    no_db_fixture_smoke_passed: bool
    stages: list[GraphLiveSmokeStage]
    remaining_live_gaps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _failed_check_names(checks: dict[str, bool]) -> list[str]:
    return sorted(name for name, passed in checks.items() if not passed)


def _missing_evidence_fields(evidence: dict[str, Any] | None, fields: tuple[str, ...]) -> list[str]:
    if not evidence:
        return list(fields)
    return [field for field in fields if not bool(evidence.get(field))]


def _build_no_db_stage(no_db_report: GraphProjectionDryRunReport) -> GraphLiveSmokeStage:
    passed = (
        no_db_report.mode == "no_db_dry_run"
        and no_db_report.live_db_validated is False
        and no_db_report.unique_node_count > 0
        and no_db_report.writeable_edge_count > 0
    )
    gaps = list(no_db_report.live_db_gap)
    if not passed:
        gaps.insert(0, "no-DB projection fixture smoke did not satisfy canonical node/edge minimums")
    return GraphLiveSmokeStage(
        name="no_db_fixture_smoke",
        status="passed" if passed else "failed",
        passed=passed,
        validated=passed,
        detail=(
            f"mode={no_db_report.mode} unique_nodes={no_db_report.unique_node_count} "
            f"writeable_edges={no_db_report.writeable_edge_count} unresolved_edges={no_db_report.unresolved_edge_count}"
        ),
        gaps=gaps,
        evidence_required=[],
    )


def _build_rollout_stage(readiness_report: GraphProjectionRolloutReadinessReport) -> GraphLiveSmokeStage:
    failed = [check.name for check in readiness_report.checks if not check.passed]
    passed = bool(readiness_report.ready_for_live_db_dry_run and not failed)
    gaps = list(readiness_report.live_db_gap)
    if failed:
        gaps.insert(0, f"pre-live readiness checks failed: {', '.join(sorted(failed))}")
    return GraphLiveSmokeStage(
        name="pre_live_db_dry_run_readiness",
        status="ready" if passed else "blocked",
        passed=passed,
        validated=passed,
        detail=(
            f"read_mode={readiness_report.read_mode} write_mode={readiness_report.write_mode} "
            f"canary_projects={','.join(readiness_report.canary_projects) or '-'}"
        ),
        gaps=gaps,
        evidence_required=[],
    )


def _build_live_db_stage(
    *,
    database_configured: bool,
    live_db_evidence: dict[str, Any] | None,
) -> GraphLiveSmokeStage:
    missing = _missing_evidence_fields(live_db_evidence, LIVE_DB_EVIDENCE_FIELDS)
    evidence_required = list(LIVE_DB_EVIDENCE_FIELDS)
    if not missing:
        return GraphLiveSmokeStage(
            name="live_db_backend_data_smoke",
            status="validated",
            passed=True,
            validated=True,
            detail="live tenant migration, backfill dry-run, backend data graph endpoint, and B-read parity evidence were provided",
            gaps=[],
            evidence_required=evidence_required,
        )
    if live_db_evidence:
        return GraphLiveSmokeStage(
            name="live_db_backend_data_smoke",
            status="failed_evidence",
            passed=False,
            validated=False,
            detail=f"live DB evidence file is present but missing required fields: {', '.join(missing)}",
            gaps=[
                "live tenant DB smoke evidence is incomplete",
                "do not promote graph_node_projection_read_mode=b_primary from this gate",
            ],
            evidence_required=evidence_required,
        )
    if database_configured:
        return GraphLiveSmokeStage(
            name="live_db_backend_data_smoke",
            status="configured_not_run",
            passed=True,
            validated=False,
            detail="database URL is configured, but this bounded gate did not open a tenant DB session",
            gaps=[
                "alembic current/upgrade still must be run against the configured tenant schema",
                "backfill_graph_nodes.py --dry-run still must be run against live tenant data",
                "admin graph backend-data endpoints still need a live nonempty smoke",
                "b_canary or b_primary parity still must be compared against seeded projection data",
            ],
            evidence_required=evidence_required,
        )
    return GraphLiveSmokeStage(
        name="live_db_backend_data_smoke",
        status="not_configured",
        passed=False,
        validated=False,
        detail="database URL is missing, so live DB smoke cannot be scheduled from this environment",
        gaps=["configure DATABASE_URL before running the live graph backend-data smoke"],
        evidence_required=evidence_required,
    )


def _build_frontend_backend_stage(
    *,
    frontend_contract_checks: dict[str, bool],
    backend_data_contract_checks: dict[str, bool],
    frontend_backend_evidence: dict[str, Any] | None,
) -> GraphLiveSmokeStage:
    missing_static = [
        *(f"frontend:{name}" for name in _failed_check_names(frontend_contract_checks)),
        *(f"backend_data:{name}" for name in _failed_check_names(backend_data_contract_checks)),
    ]
    evidence_required = list(FRONTEND_BACKEND_EVIDENCE_FIELDS)
    if missing_static:
        return GraphLiveSmokeStage(
            name="frontend_backend_data_visual_smoke",
            status="blocked",
            passed=False,
            validated=False,
            detail=f"static frontend/backend-data prerequisites failed: {', '.join(missing_static)}",
            gaps=[
                "frontend/backend-data visual smoke is not ready to run",
                "fix static graph route, API, or force3d checker prerequisites first",
            ],
            evidence_required=evidence_required,
        )

    missing_evidence = _missing_evidence_fields(frontend_backend_evidence, FRONTEND_BACKEND_EVIDENCE_FIELDS)
    if not missing_evidence:
        return GraphLiveSmokeStage(
            name="frontend_backend_data_visual_smoke",
            status="validated",
            passed=True,
            validated=True,
            detail="frontend force3d smoke evidence used live backend graph data and nonblank canvas scene checks",
            gaps=[],
            evidence_required=evidence_required,
        )
    if frontend_backend_evidence:
        return GraphLiveSmokeStage(
            name="frontend_backend_data_visual_smoke",
            status="failed_evidence",
            passed=False,
            validated=False,
            detail=f"frontend/backend-data evidence file is present but missing required fields: {', '.join(missing_evidence)}",
            gaps=[
                "frontend/backend-data visual smoke evidence is incomplete",
                "mocked GraphPage e2e remains useful but is not live backend-data proof",
            ],
            evidence_required=evidence_required,
        )

    return GraphLiveSmokeStage(
        name="frontend_backend_data_visual_smoke",
        status="ready_not_run",
        passed=True,
        validated=False,
        detail="force3d frontend contract and backend data graph routes are present; live backend-data browser smoke was not run",
        gaps=[
            "run GraphPage against a live backend graph endpoint with nonempty data",
            "capture window.__graph3dDebug scene stats and nonblank canvas evidence from backend data",
            "mocked GraphPage force3d e2e does not close the live visual gap",
        ],
        evidence_required=evidence_required,
    )


def build_graph_live_smoke_readiness(
    *,
    no_db_report: GraphProjectionDryRunReport,
    readiness_report: GraphProjectionRolloutReadinessReport,
    database_url: str | None,
    frontend_contract_checks: dict[str, bool],
    backend_data_contract_checks: dict[str, bool],
    live_db_evidence: dict[str, Any] | None = None,
    frontend_backend_evidence: dict[str, Any] | None = None,
) -> GraphLiveSmokeReadinessReport:
    """Classify Wave12 graph smoke readiness without pretending live closure.

    The gate succeeds when deterministic no-DB checks and static run
    prerequisites are healthy. Live DB and backend-data browser smokes are only
    marked validated when explicit evidence is supplied.
    """
    database_configured = bool(str(database_url or "").strip())
    stages = [
        _build_no_db_stage(no_db_report),
        _build_rollout_stage(readiness_report),
        _build_live_db_stage(
            database_configured=database_configured,
            live_db_evidence=live_db_evidence,
        ),
        _build_frontend_backend_stage(
            frontend_contract_checks=frontend_contract_checks,
            backend_data_contract_checks=backend_data_contract_checks,
            frontend_backend_evidence=frontend_backend_evidence,
        ),
    ]
    stage_by_name = {stage.name: stage for stage in stages}
    live_db_validated = stage_by_name["live_db_backend_data_smoke"].validated
    frontend_backend_validated = stage_by_name["frontend_backend_data_visual_smoke"].validated
    required_passed = all(stage.passed for stage in stages)
    remaining_live_gaps = [
        gap
        for stage in stages
        if not stage.validated
        for gap in stage.gaps
    ]
    return GraphLiveSmokeReadinessReport(
        contract_version=CONTRACT_VERSION,
        mode="wave12_graph_live_smoke_readiness",
        status="ok" if required_passed else "failed",
        closure_claim=False,
        live_db_validated=live_db_validated,
        frontend_backend_data_smoke_validated=frontend_backend_validated,
        database_configured=database_configured,
        ready_for_live_db_dry_run=stage_by_name["pre_live_db_dry_run_readiness"].passed,
        no_db_fixture_smoke_passed=stage_by_name["no_db_fixture_smoke"].passed,
        stages=stages,
        remaining_live_gaps=remaining_live_gaps,
    )


__all__ = [
    "CONTRACT_VERSION",
    "FRONTEND_BACKEND_EVIDENCE_FIELDS",
    "LIVE_DB_EVIDENCE_FIELDS",
    "GraphLiveSmokeReadinessReport",
    "GraphLiveSmokeStage",
    "build_graph_live_smoke_readiness",
]
