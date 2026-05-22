from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from .graph_node_live_db_rollout_gate import GraphNodeLiveDbRolloutGateReport
from .graph_projection_contract import GraphProjectionDryRunReport, GraphProjectionRolloutReadinessReport


CONTRACT_VERSION = "graph.node_rollout_manifest_readback.v1"
DEFAULT_SOURCE_DOCS = (
    "CURRENT_DEV/2026-03-02-graph-node-standardization-a-then-b-plan",
    "Wave7 canonical id evidence",
    "Wave10 DB rollout readiness",
    "Wave14 live DB rollout gate",
)


@dataclass(frozen=True)
class GraphNodeRolloutManifestStage:
    name: str
    status: str
    deterministic: bool
    live_db_validated: bool
    closure_claim: bool
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphNodeRolloutManifestReport:
    contract_version: str
    status: str
    manifest_id: str
    manifest_digest: str
    deterministic_readback: bool
    closure_claim: bool
    live_db_validated: bool
    live_db_closure_ready: bool
    source_docs: list[str]
    stages: list[GraphNodeRolloutManifestStage]
    readback_failures: list[str]
    remaining_live_db_gaps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_payload(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(data: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_payload(data).encode("utf-8")).hexdigest()


def _manifest_body(
    *,
    no_db_report: GraphProjectionDryRunReport,
    readiness_report: GraphProjectionRolloutReadinessReport,
    gate_report: GraphNodeLiveDbRolloutGateReport,
    source_docs: list[str],
) -> dict[str, Any]:
    stages = [
        GraphNodeRolloutManifestStage(
            name="wave7_canonical_id_fixture",
            status="passed" if gate_report.no_db_projection_validated else "failed",
            deterministic=True,
            live_db_validated=False,
            closure_claim=False,
            evidence={
                "mode": no_db_report.mode,
                "schema_version": no_db_report.schema_version,
                "unique_node_count": no_db_report.unique_node_count,
                "duplicate_node_attempts": no_db_report.duplicate_node_attempts,
                "writeable_edge_count": no_db_report.writeable_edge_count,
                "unresolved_edge_count": no_db_report.unresolved_edge_count,
                "live_db_validated": no_db_report.live_db_validated,
            },
        ),
        GraphNodeRolloutManifestStage(
            name="wave10_pre_live_db_dry_run_readiness",
            status="passed" if readiness_report.ready_for_live_db_dry_run else "failed",
            deterministic=True,
            live_db_validated=False,
            closure_claim=False,
            evidence={
                "mode": readiness_report.mode,
                "read_mode": readiness_report.read_mode,
                "write_mode": readiness_report.write_mode,
                "canary_projects": readiness_report.canary_projects,
                "backfill_dry_run": readiness_report.backfill_dry_run,
                "backfill_limit": readiness_report.backfill_limit,
                "ready_for_live_db_dry_run": readiness_report.ready_for_live_db_dry_run,
                "failed_checks": [check.name for check in readiness_report.checks if not check.passed],
            },
        ),
        GraphNodeRolloutManifestStage(
            name="wave14_live_db_rollout_gate",
            status=gate_report.status,
            deterministic=True,
            live_db_validated=gate_report.live_db_validated,
            closure_claim=gate_report.closure_claim,
            evidence={
                "contract_version": gate_report.contract_version,
                "closure_state": gate_report.closure_state,
                "dry_run_ready": gate_report.dry_run_ready,
                "read_mode_dry_run_safe": gate_report.read_mode_dry_run_safe,
                "backfill_dry_run_ready": gate_report.backfill_dry_run_ready,
                "live_db_closure_ready": gate_report.live_db_closure_ready,
                "missing_live_db_evidence": gate_report.missing_live_db_evidence,
            },
        ),
    ]

    return {
        "contract_version": CONTRACT_VERSION,
        "manifest_id": (
            "graph-node-standardization:"
            f"{readiness_report.read_mode}:"
            f"{readiness_report.write_mode}:"
            f"limit-{readiness_report.backfill_limit}:"
            f"{gate_report.closure_state}"
        ),
        "closure_claim": False,
        "live_db_validated": gate_report.live_db_validated,
        "live_db_closure_ready": gate_report.live_db_closure_ready,
        "source_docs": source_docs,
        "stages": [stage.to_dict() for stage in stages],
        "remaining_live_db_gaps": gate_report.remaining_live_db_gaps,
    }


def _readback_failures(body: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if body.get("closure_claim") is not False:
        failures.append("manifest closure_claim must remain false")
    stages = body.get("stages")
    if not isinstance(stages, list) or len(stages) != 3:
        failures.append("manifest must contain exactly three rollout stages")
        stages = []
    stage_names = [stage.get("name") for stage in stages if isinstance(stage, dict)]
    expected_stage_names = [
        "wave7_canonical_id_fixture",
        "wave10_pre_live_db_dry_run_readiness",
        "wave14_live_db_rollout_gate",
    ]
    if stage_names != expected_stage_names:
        failures.append(f"manifest stages are not in canonical order: {stage_names}")
    for stage in stages:
        if not isinstance(stage, dict):
            failures.append("manifest stage must be an object")
            continue
        if stage.get("deterministic") is not True:
            failures.append(f"{stage.get('name')}: deterministic must be true")
        if stage.get("closure_claim") is not False:
            failures.append(f"{stage.get('name')}: closure_claim must remain false")
    if body.get("live_db_closure_ready") and body.get("live_db_validated") is not True:
        failures.append("live_db_closure_ready requires live_db_validated=true")
    if body.get("live_db_validated") is not True and not body.get("remaining_live_db_gaps"):
        failures.append("non-live manifest must retain remaining live DB gaps")
    return failures


def build_graph_node_rollout_manifest(
    *,
    no_db_report: GraphProjectionDryRunReport,
    readiness_report: GraphProjectionRolloutReadinessReport,
    gate_report: GraphNodeLiveDbRolloutGateReport,
    source_docs: list[str] | tuple[str, ...] | None = None,
) -> GraphNodeRolloutManifestReport:
    """Build and read back the deterministic Graph Node rollout manifest.

    The manifest is intentionally a pure report over the dry-run/readiness/gate
    outputs. It does not open a tenant DB and must not convert dry-run evidence
    into a closure claim.
    """
    docs = sorted({str(doc).strip() for doc in (source_docs or DEFAULT_SOURCE_DOCS) if str(doc).strip()})
    first_body = _manifest_body(
        no_db_report=no_db_report,
        readiness_report=readiness_report,
        gate_report=gate_report,
        source_docs=docs,
    )
    second_body = _manifest_body(
        no_db_report=no_db_report,
        readiness_report=readiness_report,
        gate_report=gate_report,
        source_docs=docs,
    )
    first_digest = _digest(first_body)
    second_digest = _digest(second_body)
    readback_failures = _readback_failures(first_body)
    if first_digest != second_digest:
        readback_failures.append("manifest digest changed across repeated readback")
    for index, body in enumerate((first_body, second_body), start=1):
        if _canonical_payload(json.loads(_canonical_payload(body))) != _canonical_payload(body):
            readback_failures.append(f"manifest readback {index} is not canonical JSON stable")

    deterministic_readback = not readback_failures
    stage_objects = [
        GraphNodeRolloutManifestStage(
            name=stage["name"],
            status=stage["status"],
            deterministic=stage["deterministic"],
            live_db_validated=stage["live_db_validated"],
            closure_claim=stage["closure_claim"],
            evidence=dict(stage["evidence"]),
        )
        for stage in first_body["stages"]
    ]
    status = "ok" if deterministic_readback and gate_report.status == "ok" else "failed"

    return GraphNodeRolloutManifestReport(
        contract_version=CONTRACT_VERSION,
        status=status,
        manifest_id=str(first_body["manifest_id"]),
        manifest_digest=first_digest,
        deterministic_readback=deterministic_readback,
        closure_claim=False,
        live_db_validated=bool(first_body["live_db_validated"]),
        live_db_closure_ready=bool(first_body["live_db_closure_ready"]),
        source_docs=list(first_body["source_docs"]),
        stages=stage_objects,
        readback_failures=readback_failures,
        remaining_live_db_gaps=list(first_body["remaining_live_db_gaps"]),
    )


__all__ = [
    "CONTRACT_VERSION",
    "DEFAULT_SOURCE_DOCS",
    "GraphNodeRolloutManifestReport",
    "GraphNodeRolloutManifestStage",
    "build_graph_node_rollout_manifest",
]
