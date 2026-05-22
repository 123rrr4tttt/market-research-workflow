from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .canary_handoff import CANARY_HANDOFF_CONTRACT_VERSION, CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION


CONTRACT_VERSION = "ingest.canary_metrics_readiness.v1"

LIVE_CANARY_EVIDENCE_FIELDS = (
    "demo_proj_live_canary_validated",
    "single_url_frontdoor_run_completed",
    "configured_services_used",
    "canary_handoff_readback_present",
)

METRIC_24H_EVIDENCE_FIELDS = (
    "metric_24h_readback_validated",
    "window_hours_at_least_24",
    "rejection_rate_reviewed",
    "inserted_valid_ratio_reviewed",
    "guardrail_rollout_counts_reviewed",
)

DETERMINISTIC_METRICS_FIELDS = (
    "contract_version",
    "metrics_snapshot.contract_version",
    "metrics_snapshot.sample_size",
    "metrics_snapshot.guardrail_rollout.sample_size",
    "metrics_snapshot.guardrail_rollout.strict_enabled_samples",
    "metrics_snapshot.guardrail_rollout.canary_matched_samples",
    "metrics_snapshot.guardrail_rollout.strict_gate_source_counts",
    "metrics_snapshot.guardrail_rollout.live_canary_validated",
    "metrics_snapshot.guardrail_rollout.closure_claim",
    "remaining_live_run_gaps",
)


@dataclass(frozen=True)
class IngestCanaryMetricsStage:
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
class IngestCanaryMetricsReadinessReport:
    contract_version: str
    mode: str
    status: str
    project_key: str
    closure_claim: bool
    deterministic_metrics_ready: bool
    live_canary_validated: bool
    metric_24h_readback_validated: bool
    demo_proj_live_canary_open: bool
    metric_24h_readback_open: bool
    ready_for_live_canary: bool
    ready_for_24h_metric_readback: bool
    metrics_snapshot: dict[str, Any]
    stages: list[IngestCanaryMetricsStage]
    remaining_live_gaps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get_path(payload: Mapping[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for segment in dotted_path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(segment)
    return current


def _coerce_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _missing_evidence_fields(evidence: Mapping[str, Any] | None, fields: tuple[str, ...]) -> list[str]:
    if not evidence:
        return list(fields)
    return [field for field in fields if not bool(evidence.get(field))]


def _build_metrics_snapshot(handoff: Mapping[str, Any]) -> dict[str, Any]:
    metrics = handoff.get("metrics_snapshot") if isinstance(handoff.get("metrics_snapshot"), Mapping) else {}
    guardrail = metrics.get("guardrail_rollout") if isinstance(metrics.get("guardrail_rollout"), Mapping) else {}
    return {
        "sample_size": _coerce_non_negative_int(metrics.get("sample_size")),
        "metrics_contract_version": metrics.get("contract_version"),
        "guardrail_sample_size": _coerce_non_negative_int(guardrail.get("sample_size")),
        "strict_enabled_samples": _coerce_non_negative_int(guardrail.get("strict_enabled_samples")),
        "canary_matched_samples": _coerce_non_negative_int(guardrail.get("canary_matched_samples")),
        "strict_enabled_rate": float(guardrail.get("strict_enabled_rate") or 0.0),
        "canary_matched_rate": float(guardrail.get("canary_matched_rate") or 0.0),
        "live_canary_validated": bool(guardrail.get("live_canary_validated")),
        "closure_claim": bool(guardrail.get("closure_claim")),
    }


def _build_deterministic_stage(
    *,
    handoff: Mapping[str, Any],
    project_key: str,
) -> IngestCanaryMetricsStage:
    metrics = handoff.get("metrics_snapshot") if isinstance(handoff.get("metrics_snapshot"), Mapping) else {}
    guardrail = metrics.get("guardrail_rollout") if isinstance(metrics.get("guardrail_rollout"), Mapping) else {}
    frontdoor = handoff.get("frontdoor_run") if isinstance(handoff.get("frontdoor_run"), Mapping) else {}
    rollout = handoff.get("rollout") if isinstance(handoff.get("rollout"), Mapping) else {}
    strict_gate = handoff.get("strict_gate_state") if isinstance(handoff.get("strict_gate_state"), Mapping) else {}
    gaps = handoff.get("remaining_live_run_gaps") if isinstance(handoff.get("remaining_live_run_gaps"), list) else []

    checks = {
        "handoff_contract_version": handoff.get("contract_version") == CANARY_HANDOFF_CONTRACT_VERSION,
        "metrics_snapshot_contract_version": metrics.get("contract_version") == CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION,
        "demo_project_scope": frontdoor.get("project_key") == project_key,
        "single_url_source_mode": frontdoor.get("source_mode") == "url_execution",
        "strict_gate_visible": bool(strict_gate.get("strict_gate_enabled")),
        "rollout_channel_canary": rollout.get("channel") == "canary",
        "rollout_canary_matched": bool(rollout.get("canary_matched")),
        "metrics_sample_present": _coerce_non_negative_int(metrics.get("sample_size")) > 0,
        "guardrail_samples_present": _coerce_non_negative_int(guardrail.get("sample_size")) > 0,
        "strict_enabled_sample_present": _coerce_non_negative_int(guardrail.get("strict_enabled_samples")) > 0,
        "canary_matched_sample_present": _coerce_non_negative_int(guardrail.get("canary_matched_samples")) > 0,
        "strict_source_counts_visible": bool(guardrail.get("strict_gate_source_counts")),
        "handoff_keeps_live_gap_open": handoff.get("live_canary_validated") is False
        and handoff.get("closure_claim") is False
        and bool(gaps),
        "metrics_keep_closure_open": guardrail.get("live_canary_validated") is False
        and guardrail.get("closure_claim") is False,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    passed = not failed
    return IngestCanaryMetricsStage(
        name="deterministic_canary_metrics_snapshot",
        status="passed" if passed else "failed",
        passed=passed,
        validated=passed,
        detail=(
            f"project_key={frontdoor.get('project_key')!r} source_mode={frontdoor.get('source_mode')!r} "
            f"sample_size={metrics.get('sample_size')} strict_enabled_samples={guardrail.get('strict_enabled_samples')} "
            f"canary_matched_samples={guardrail.get('canary_matched_samples')}"
        ),
        gaps=[] if passed else [f"deterministic canary metrics checks failed: {', '.join(failed)}"],
        evidence_required=list(DETERMINISTIC_METRICS_FIELDS),
    )


def _build_live_canary_stage(
    *,
    deterministic_ready: bool,
    live_canary_evidence: Mapping[str, Any] | None,
    project_key: str,
) -> IngestCanaryMetricsStage:
    evidence_required = list(LIVE_CANARY_EVIDENCE_FIELDS)
    if not deterministic_ready:
        return IngestCanaryMetricsStage(
            name="demo_proj_live_canary",
            status="blocked",
            passed=False,
            validated=False,
            detail="deterministic canary metrics snapshot is not ready",
            gaps=[f"{project_key} live canary remains blocked until deterministic canary metrics are healthy"],
            evidence_required=evidence_required,
        )

    missing = _missing_evidence_fields(live_canary_evidence, LIVE_CANARY_EVIDENCE_FIELDS)
    if not missing:
        return IngestCanaryMetricsStage(
            name="demo_proj_live_canary",
            status="validated",
            passed=True,
            validated=True,
            detail=f"{project_key} live single URL canary evidence provided all required fields",
            gaps=[],
            evidence_required=evidence_required,
        )

    if live_canary_evidence:
        return IngestCanaryMetricsStage(
            name="demo_proj_live_canary",
            status="failed_evidence",
            passed=False,
            validated=False,
            detail=f"live canary evidence is present but missing required fields: {', '.join(missing)}",
            gaps=[
                f"{project_key} live canary evidence is incomplete",
                "do not promote this gate as live-canary validated",
            ],
            evidence_required=evidence_required,
        )

    return IngestCanaryMetricsStage(
        name="demo_proj_live_canary",
        status="ready_not_run",
        passed=True,
        validated=False,
        detail=f"deterministic canary metrics are ready, but {project_key} live canary was not run",
        gaps=[
            f"{project_key} live canary execution remains open against configured services",
            "single URL frontdoor result still needs a live canary handoff readback",
        ],
        evidence_required=evidence_required,
    )


def _build_metric_24h_stage(
    *,
    deterministic_ready: bool,
    live_canary_validated: bool,
    metric_readback_evidence: Mapping[str, Any] | None,
) -> IngestCanaryMetricsStage:
    evidence_required = list(METRIC_24H_EVIDENCE_FIELDS)
    if not deterministic_ready:
        return IngestCanaryMetricsStage(
            name="metric_24h_readback",
            status="blocked",
            passed=False,
            validated=False,
            detail="deterministic canary metrics snapshot is not ready",
            gaps=["24h metric readback remains blocked until deterministic canary metrics are healthy"],
            evidence_required=evidence_required,
        )

    missing = _missing_evidence_fields(metric_readback_evidence, METRIC_24H_EVIDENCE_FIELDS)
    if not missing:
        return IngestCanaryMetricsStage(
            name="metric_24h_readback",
            status="validated",
            passed=True,
            validated=True,
            detail="24h rejection-rate, inserted-valid ratio, and guardrail rollout metrics were read back",
            gaps=[],
            evidence_required=evidence_required,
        )

    if metric_readback_evidence:
        return IngestCanaryMetricsStage(
            name="metric_24h_readback",
            status="failed_evidence",
            passed=False,
            validated=False,
            detail=f"24h metric readback evidence is present but missing required fields: {', '.join(missing)}",
            gaps=[
                "24h metric readback evidence is incomplete",
                "do not claim 24h metric validation from this gate",
            ],
            evidence_required=evidence_required,
        )

    if not live_canary_validated:
        return IngestCanaryMetricsStage(
            name="metric_24h_readback",
            status="open_waiting_for_live_canary",
            passed=True,
            validated=False,
            detail="24h metric readback remains open because demo_proj live canary has not been validated",
            gaps=[
                "24h rejection-rate readback remains open until a live canary run exists",
                "24h inserted-valid ratio readback remains open until a live canary run exists",
            ],
            evidence_required=evidence_required,
        )

    return IngestCanaryMetricsStage(
        name="metric_24h_readback",
        status="ready_not_read",
        passed=True,
        validated=False,
        detail="live canary is validated, but 24h metric readback evidence was not provided",
        gaps=[
            "read back 24h rejection-rate before all-project strict-gate promotion",
            "read back 24h inserted-valid ratio before all-project strict-gate promotion",
            "read back 24h guardrail rollout counts before all-project strict-gate promotion",
        ],
        evidence_required=evidence_required,
    )


def build_ingest_canary_metrics_readiness(
    *,
    handoff: Mapping[str, Any],
    project_key: str = "demo_proj",
    live_canary_evidence: Mapping[str, Any] | None = None,
    metric_readback_evidence: Mapping[str, Any] | None = None,
) -> IngestCanaryMetricsReadinessReport:
    """Classify canary metrics readiness without pretending live closure."""
    normalized_project = str(project_key or "demo_proj").strip() or "demo_proj"
    deterministic_stage = _build_deterministic_stage(handoff=handoff, project_key=normalized_project)
    live_stage = _build_live_canary_stage(
        deterministic_ready=deterministic_stage.passed,
        live_canary_evidence=live_canary_evidence,
        project_key=normalized_project,
    )
    metric_stage = _build_metric_24h_stage(
        deterministic_ready=deterministic_stage.passed,
        live_canary_validated=live_stage.validated,
        metric_readback_evidence=metric_readback_evidence,
    )
    stages = [deterministic_stage, live_stage, metric_stage]
    required_passed = all(stage.passed for stage in stages)
    remaining_live_gaps = [gap for stage in stages if not stage.validated for gap in stage.gaps]
    return IngestCanaryMetricsReadinessReport(
        contract_version=CONTRACT_VERSION,
        mode="wave14_ingest_canary_metrics_readiness",
        status="ok" if required_passed else "failed",
        project_key=normalized_project,
        closure_claim=False,
        deterministic_metrics_ready=deterministic_stage.passed,
        live_canary_validated=live_stage.validated,
        metric_24h_readback_validated=metric_stage.validated,
        demo_proj_live_canary_open=not live_stage.validated,
        metric_24h_readback_open=not metric_stage.validated,
        ready_for_live_canary=deterministic_stage.passed,
        ready_for_24h_metric_readback=deterministic_stage.passed and live_stage.validated,
        metrics_snapshot=_build_metrics_snapshot(handoff),
        stages=stages,
        remaining_live_gaps=remaining_live_gaps,
    )


__all__ = [
    "CONTRACT_VERSION",
    "DETERMINISTIC_METRICS_FIELDS",
    "LIVE_CANARY_EVIDENCE_FIELDS",
    "METRIC_24H_EVIDENCE_FIELDS",
    "IngestCanaryMetricsReadinessReport",
    "IngestCanaryMetricsStage",
    "build_ingest_canary_metrics_readiness",
]
