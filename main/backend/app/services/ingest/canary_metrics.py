from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .canary_handoff import CANARY_HANDOFF_CONTRACT_VERSION, CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION


CONTRACT_VERSION = "ingest.canary_metrics_readiness.v1"
CONFIGURED_PROVIDER_CANARY_CONTRACT_VERSION = "ingest.configured_provider_canary_boundary.v1"

LIVE_CANARY_EVIDENCE_FIELDS = (
    "demo_proj_live_canary_validated",
    "single_url_frontdoor_run_completed",
    "configured_services_used",
    "canary_handoff_readback_present",
)

CONFIGURED_PROVIDER_CANARY_EVIDENCE_FIELDS = (
    "demo_proj_live_canary_validated",
    "single_url_frontdoor_run_completed",
    "configured_services_used",
    "canary_handoff_readback_present",
    "configured_provider.provider_key",
    "configured_provider.config_state",
    "configured_provider.runtime",
    "configured_provider.live_probe_status",
    "frontdoor_run.entrypoint",
    "frontdoor_run.source_mode",
    "frontdoor_run.source_url",
    "handoff_readback.contract_version",
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
    configured_provider_canary_boundary: dict[str, Any]
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


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _missing_evidence_fields(evidence: Mapping[str, Any] | None, fields: tuple[str, ...]) -> list[str]:
    if not evidence:
        return list(fields)
    return [field for field in fields if not bool(evidence.get(field))]


def build_configured_provider_canary_boundary(
    *,
    live_canary_evidence: Mapping[str, Any] | None,
    project_key: str = "demo_proj",
) -> dict[str, Any]:
    """Validate live canary evidence without starting external services."""
    evidence = live_canary_evidence if isinstance(live_canary_evidence, Mapping) else {}
    provider = evidence.get("configured_provider") if isinstance(evidence.get("configured_provider"), Mapping) else {}
    readback = evidence.get("handoff_readback") if isinstance(evidence.get("handoff_readback"), Mapping) else {}
    if not readback and isinstance(evidence.get("canary_handoff"), Mapping):
        readback = evidence.get("canary_handoff")  # type: ignore[assignment]
    frontdoor = evidence.get("frontdoor_run") if isinstance(evidence.get("frontdoor_run"), Mapping) else {}
    if not frontdoor and isinstance(readback.get("frontdoor_run"), Mapping):
        frontdoor = readback.get("frontdoor_run")  # type: ignore[assignment]

    normalized_project = _clean_text(project_key) or "demo_proj"
    provider_key = _clean_text(provider.get("provider_key") or provider.get("provider") or provider.get("name"))
    config_state = _clean_text(provider.get("config_state")).lower()
    runtime = _clean_text(provider.get("runtime") or provider.get("runtime_provider"))
    live_probe_status = _clean_text(provider.get("live_probe_status") or provider.get("runtime_status")).lower()
    frontdoor_project = _clean_text(frontdoor.get("project_key") or readback.get("project_key"))
    frontdoor_entrypoint = _clean_text(frontdoor.get("entrypoint"))
    frontdoor_source_mode = _clean_text(frontdoor.get("source_mode"))
    source_url = _clean_text(frontdoor.get("source_url") or frontdoor.get("url"))
    handoff_contract = _clean_text(readback.get("contract_version"))

    required_flags = {
        "demo_proj_live_canary_validated": evidence.get("demo_proj_live_canary_validated") is True,
        "single_url_frontdoor_run_completed": evidence.get("single_url_frontdoor_run_completed") is True,
        "configured_services_used": evidence.get("configured_services_used") is True,
        "canary_handoff_readback_present": evidence.get("canary_handoff_readback_present") is True,
    }
    missing_fields = [field for field, passed in required_flags.items() if not passed]
    if not provider_key:
        missing_fields.append("configured_provider.provider_key")
    if not config_state:
        missing_fields.append("configured_provider.config_state")
    if not runtime:
        missing_fields.append("configured_provider.runtime")
    if not live_probe_status:
        missing_fields.append("configured_provider.live_probe_status")
    if not frontdoor_entrypoint:
        missing_fields.append("frontdoor_run.entrypoint")
    if not frontdoor_source_mode:
        missing_fields.append("frontdoor_run.source_mode")
    if not source_url:
        missing_fields.append("frontdoor_run.source_url")
    if not handoff_contract:
        missing_fields.append("handoff_readback.contract_version")

    checks = {
        "configured_provider_selected": bool(provider_key),
        "configured_provider_configured": bool(
            config_state in {"configured", "configured_service", "configured_via_codex_cli_fallback"}
            or provider.get("configured") is True
        ),
        "configured_provider_live_runtime_validated": bool(
            live_probe_status in {"passed", "validated", "ok"}
            or provider.get("runtime_validated") is True
            or evidence.get("provider_live_runtime_validated") is True
        ),
        "frontdoor_entrypoint_is_url_pool": frontdoor_entrypoint == "ingest.url_pool",
        "frontdoor_source_mode_is_url_execution": frontdoor_source_mode == "url_execution",
        "frontdoor_project_matches": not frontdoor_project or frontdoor_project == normalized_project,
        "frontdoor_source_url_is_public_url": source_url.startswith(("http://", "https://")),
        "handoff_contract_read_back": handoff_contract == CANARY_HANDOFF_CONTRACT_VERSION,
        "closure_not_claimed_by_boundary": evidence.get("closure_claim") is not True,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    passed = bool(evidence) and not missing_fields and not failed_checks
    return {
        "contract_version": CONFIGURED_PROVIDER_CANARY_CONTRACT_VERSION,
        "status": "validated" if passed else ("failed_evidence" if evidence else "missing_evidence"),
        "project_key": normalized_project,
        "evidence_present": bool(evidence),
        "configured_provider": {
            "provider_key": provider_key or None,
            "config_state": config_state or None,
            "runtime": runtime or None,
            "live_probe_status": live_probe_status or None,
        },
        "frontdoor_run": {
            "project_key": frontdoor_project or None,
            "entrypoint": frontdoor_entrypoint or None,
            "source_mode": frontdoor_source_mode or None,
            "source_url": source_url or None,
        },
        "handoff_readback": {
            "contract_version": handoff_contract or None,
            "handoff_state": readback.get("handoff_state"),
            "closure_claim": readback.get("closure_claim"),
        },
        "validation": {
            "passed": passed,
            "missing_fields": missing_fields,
            "failed_checks": failed_checks,
            "checks": checks,
        },
        "live_canary_validated": passed,
        "closure_claim": False,
    }


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
    configured_provider_boundary: Mapping[str, Any],
    project_key: str,
) -> IngestCanaryMetricsStage:
    evidence_required = list(CONFIGURED_PROVIDER_CANARY_EVIDENCE_FIELDS)
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

    validation = (
        configured_provider_boundary.get("validation")
        if isinstance(configured_provider_boundary.get("validation"), Mapping)
        else {}
    )
    missing = list(validation.get("missing_fields") or [])
    failed_checks = list(validation.get("failed_checks") or [])
    evidence_present = configured_provider_boundary.get("evidence_present") is True
    if validation.get("passed") is True:
        return IngestCanaryMetricsStage(
            name="demo_proj_live_canary",
            status="validated",
            passed=True,
            validated=True,
            detail=f"{project_key} live single URL canary evidence passed configured-provider boundary",
            gaps=[],
            evidence_required=evidence_required,
        )

    if evidence_present:
        return IngestCanaryMetricsStage(
            name="demo_proj_live_canary",
            status="failed_evidence",
            passed=False,
            validated=False,
            detail=(
                "live canary evidence failed configured-provider boundary: "
                f"missing={', '.join(missing) or 'none'} failed={', '.join(failed_checks) or 'none'}"
            ),
            gaps=[
                f"{project_key} configured-provider live canary evidence is incomplete",
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
    configured_provider_boundary = build_configured_provider_canary_boundary(
        live_canary_evidence=live_canary_evidence,
        project_key=normalized_project,
    )
    live_stage = _build_live_canary_stage(
        deterministic_ready=deterministic_stage.passed,
        configured_provider_boundary=configured_provider_boundary,
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
        configured_provider_canary_boundary=configured_provider_boundary,
        stages=stages,
        remaining_live_gaps=remaining_live_gaps,
    )


__all__ = [
    "CONFIGURED_PROVIDER_CANARY_CONTRACT_VERSION",
    "CONFIGURED_PROVIDER_CANARY_EVIDENCE_FIELDS",
    "CONTRACT_VERSION",
    "DETERMINISTIC_METRICS_FIELDS",
    "LIVE_CANARY_EVIDENCE_FIELDS",
    "METRIC_24H_EVIDENCE_FIELDS",
    "IngestCanaryMetricsReadinessReport",
    "IngestCanaryMetricsStage",
    "build_configured_provider_canary_boundary",
    "build_ingest_canary_metrics_readiness",
]
