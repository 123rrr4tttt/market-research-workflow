from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .graph_projection_contract import GraphProjectionDryRunReport, GraphProjectionRolloutReadinessReport


CONTRACT_VERSION = "graph.node_live_db_rollout_gate.v1"

LIVE_DB_CLOSURE_EVIDENCE_FIELDS = (
    "live_db_validated",
    "alembic_current_or_upgrade_run",
    "backfill_graph_nodes_dry_run",
    "backend_data_graph_endpoint_smoke",
    "b_read_parity_checked",
)


@dataclass(frozen=True)
class GraphNodeLiveDbRolloutGateCheck:
    stage: str
    name: str
    passed: bool
    validated: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphNodeLiveDbRolloutGateReport:
    contract_version: str
    status: str
    closure_state: str
    closure_claim: bool
    dry_run_ready: bool
    read_mode_dry_run_safe: bool
    backfill_dry_run_ready: bool
    no_db_projection_validated: bool
    live_db_validated: bool
    live_db_closure_ready: bool
    database_configured: bool
    read_mode: str
    write_mode: str
    canary_projects: list[str]
    backfill_limit: int | None
    required_live_db_evidence: list[str]
    missing_live_db_evidence: list[str]
    checks: list[GraphNodeLiveDbRolloutGateCheck]
    remaining_live_db_gaps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _missing_live_db_evidence_fields(live_db_evidence: dict[str, Any] | None) -> list[str]:
    if not live_db_evidence:
        return list(LIVE_DB_CLOSURE_EVIDENCE_FIELDS)
    return [field for field in LIVE_DB_CLOSURE_EVIDENCE_FIELDS if not bool(live_db_evidence.get(field))]


def _no_db_projection_passed(no_db_report: GraphProjectionDryRunReport) -> bool:
    return (
        no_db_report.mode == "no_db_dry_run"
        and no_db_report.live_db_validated is False
        and no_db_report.unique_node_count > 0
        and no_db_report.writeable_edge_count > 0
    )


def _check_map(readiness_report: GraphProjectionRolloutReadinessReport) -> dict[str, bool]:
    return {check.name: bool(check.passed) for check in readiness_report.checks}


def _read_mode_dry_run_safe(readiness_report: GraphProjectionRolloutReadinessReport) -> bool:
    checks = _check_map(readiness_report)
    return bool(
        checks.get("read_mode_allowed")
        and checks.get("read_mode_pre_live_safe")
        and checks.get("b_canary_has_project_scope")
    )


def _backfill_dry_run_ready(readiness_report: GraphProjectionRolloutReadinessReport) -> bool:
    checks = _check_map(readiness_report)
    return bool(checks.get("backfill_dry_run_required") and checks.get("backfill_limit_bounded"))


def _closure_state(
    *,
    dry_run_ready: bool,
    live_db_validated: bool,
    live_db_evidence_present: bool,
) -> str:
    if live_db_validated:
        return "live_db_validated_ready_for_closure_review"
    if live_db_evidence_present:
        return "live_db_evidence_incomplete"
    if dry_run_ready:
        return "dry_run_ready_live_db_not_validated"
    return "dry_run_blocked_live_db_not_validated"


def build_graph_node_live_db_rollout_gate(
    *,
    no_db_report: GraphProjectionDryRunReport,
    readiness_report: GraphProjectionRolloutReadinessReport,
    database_url: str | None,
    live_db_evidence: dict[str, Any] | None = None,
) -> GraphNodeLiveDbRolloutGateReport:
    """Classify Graph Node live DB rollout state without overclaiming closure.

    Dry-run readiness means the no-DB projection fixture and pre-live read/write
    guards are healthy. Live DB validation only becomes true when explicit
    evidence proves migration/current, live dry-run backfill, backend graph
    endpoint smoke, and B-read parity.
    """
    no_db_projection_validated = _no_db_projection_passed(no_db_report)
    dry_run_readiness_checks_passed = all(check.passed for check in readiness_report.checks)
    dry_run_ready = bool(no_db_projection_validated and readiness_report.ready_for_live_db_dry_run)
    read_mode_safe = _read_mode_dry_run_safe(readiness_report)
    backfill_ready = _backfill_dry_run_ready(readiness_report)

    live_db_evidence_present = live_db_evidence is not None
    missing_live_db_evidence = _missing_live_db_evidence_fields(live_db_evidence)
    live_db_validated = live_db_evidence_present and not missing_live_db_evidence
    database_configured = bool(str(database_url or "").strip())

    checks: list[GraphNodeLiveDbRolloutGateCheck] = [
        GraphNodeLiveDbRolloutGateCheck(
            stage="dry_run",
            name="no_db_projection_fixture",
            passed=no_db_projection_validated,
            validated=no_db_projection_validated,
            detail=(
                f"mode={no_db_report.mode} unique_nodes={no_db_report.unique_node_count} "
                f"writeable_edges={no_db_report.writeable_edge_count} live_db_validated={no_db_report.live_db_validated}"
            ),
        ),
        GraphNodeLiveDbRolloutGateCheck(
            stage="dry_run",
            name="pre_live_rollout_readiness",
            passed=dry_run_readiness_checks_passed,
            validated=dry_run_readiness_checks_passed,
            detail=(
                f"ready_for_live_db_dry_run={readiness_report.ready_for_live_db_dry_run} "
                f"read_mode={readiness_report.read_mode} write_mode={readiness_report.write_mode} "
                f"backfill_dry_run={readiness_report.backfill_dry_run}"
            ),
        ),
    ]
    checks.extend(
        GraphNodeLiveDbRolloutGateCheck(
            stage="dry_run",
            name=check.name,
            passed=check.passed,
            validated=check.passed,
            detail=check.detail,
        )
        for check in readiness_report.checks
    )

    if live_db_validated:
        checks.append(
            GraphNodeLiveDbRolloutGateCheck(
                stage="live_db",
                name="live_db_closure_evidence",
                passed=True,
                validated=True,
                detail="complete live DB closure evidence was supplied",
            )
        )
    elif live_db_evidence_present:
        checks.append(
            GraphNodeLiveDbRolloutGateCheck(
                stage="live_db",
                name="live_db_closure_evidence",
                passed=False,
                validated=False,
                detail=f"live DB evidence is incomplete: missing {', '.join(missing_live_db_evidence)}",
            )
        )
    else:
        checks.append(
            GraphNodeLiveDbRolloutGateCheck(
                stage="live_db",
                name="live_db_closure_evidence",
                passed=True,
                validated=False,
                detail="no live DB evidence supplied; dry-run/read-mode/backfill readiness is not closure",
            )
        )

    if live_db_validated:
        remaining_live_db_gaps: list[str] = []
    else:
        remaining_live_db_gaps = [
            *no_db_report.live_db_gap,
            *readiness_report.live_db_gap,
        ]
        if not database_configured:
            remaining_live_db_gaps.append("configure DATABASE_URL before claiming tenant live DB closure")
        if live_db_evidence_present:
            remaining_live_db_gaps.append(
                "complete live DB evidence fields before setting live_db_validated=true: "
                + ", ".join(missing_live_db_evidence)
            )
        else:
            remaining_live_db_gaps.append(
                "provide live DB evidence before moving this topic from dry-run readiness to closure review"
            )
        remaining_live_db_gaps = _unique_ordered(remaining_live_db_gaps)

    if live_db_validated:
        status = "ok" if no_db_projection_validated else "failed"
    elif live_db_evidence_present:
        status = "failed"
    else:
        status = "ok" if dry_run_ready else "failed"

    return GraphNodeLiveDbRolloutGateReport(
        contract_version=CONTRACT_VERSION,
        status=status,
        closure_state=_closure_state(
            dry_run_ready=dry_run_ready,
            live_db_validated=bool(live_db_validated),
            live_db_evidence_present=live_db_evidence_present,
        ),
        closure_claim=False,
        dry_run_ready=dry_run_ready,
        read_mode_dry_run_safe=read_mode_safe,
        backfill_dry_run_ready=backfill_ready,
        no_db_projection_validated=no_db_projection_validated,
        live_db_validated=bool(live_db_validated),
        live_db_closure_ready=bool(live_db_validated),
        database_configured=database_configured,
        read_mode=readiness_report.read_mode,
        write_mode=readiness_report.write_mode,
        canary_projects=readiness_report.canary_projects,
        backfill_limit=readiness_report.backfill_limit,
        required_live_db_evidence=list(LIVE_DB_CLOSURE_EVIDENCE_FIELDS),
        missing_live_db_evidence=[] if live_db_validated else missing_live_db_evidence,
        checks=checks,
        remaining_live_db_gaps=remaining_live_db_gaps,
    )


__all__ = [
    "CONTRACT_VERSION",
    "LIVE_DB_CLOSURE_EVIDENCE_FIELDS",
    "GraphNodeLiveDbRolloutGateCheck",
    "GraphNodeLiveDbRolloutGateReport",
    "build_graph_node_live_db_rollout_gate",
]
