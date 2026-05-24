from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .canary_handoff import LIVE_CANARY_EVIDENCE_CONTRACT_VERSION


CONTRACT_VERSION = "ingest.canary_strict_promotion_readiness.v1"
PRODUCTION_24H_METRICS_CONTRACT_VERSION = "ingest.production_24h_metrics_readback.v1"
OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION = "ingest.ops_strict_gate_promotion_evidence.v1"

PRODUCTION_24H_BLOCKERS = (
    "production_24h_rejection_rate_readback_not_available",
    "production_24h_inserted_valid_ratio_readback_not_available",
    "production_guardrail_rollout_counts_readback_not_available",
)
PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER = "production_24h_metrics_evidence_invalid"

OPS_PROMOTION_BLOCKERS = (
    "operations_strict_gate_promotion_decision_not_recorded",
    "operations_strict_gate_global_default_not_enabled",
)
OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER = "operations_strict_gate_promotion_evidence_invalid"


@dataclass(frozen=True)
class Boundary:
    name: str
    status: str
    passed: bool
    validated: bool
    detail: str
    blockers: list[str]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrictPromotionReadiness:
    contract_version: str
    status: str
    project_key: str
    closure_claim: bool
    repo_local_preflight_passed: bool
    repo_local_live_canary_validated: bool
    repo_local_metric_24h_shape_validated: bool
    production_24h_metrics_satisfied: bool
    strict_gate_promotion_satisfied: bool
    promotion_recommendation: str
    boundaries: list[Boundary]
    remaining_external_blockers: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_present(value: Any) -> bool:
    return bool(str(value or "").strip())


def _rate_matches(actual: Any, numerator: Any, denominator: Any) -> bool:
    actual_rate = _number(actual)
    try:
        num = int(numerator)
        den = int(denominator)
    except (TypeError, ValueError):
        return False
    if actual_rate is None or den <= 0:
        return False
    return round(num / den, 6) == round(actual_rate, 6)


def _live_canary_boundary(live_canary_evidence: Mapping[str, Any] | None) -> Boundary:
    evidence = _mapping(live_canary_evidence)
    validation_checks = _mapping(evidence.get("validation_checks"))
    required_checks = (
        "api_runtime_validated",
        "db_readback_validated",
        "guardrail_pass_observed",
        "guardrail_block_observed",
        "handoff_readback_present",
    )
    failed_checks = [name for name in required_checks if validation_checks.get(name) is not True]
    passed = (
        evidence.get("contract_version") == LIVE_CANARY_EVIDENCE_CONTRACT_VERSION
        and evidence.get("validation_scope") == "repo_local_api_db_runtime"
        and evidence.get("live_canary_validated") is True
        and evidence.get("closure_claim") is False
        and not failed_checks
    )
    blockers: list[str] = []
    if not evidence:
        blockers.append("repo_local_live_canary_evidence_missing")
    if failed_checks:
        blockers.append("repo_local_live_canary_validation_failed")
    return Boundary(
        name="repo_local_live_canary",
        status="validated" if passed else ("failed_evidence" if evidence else "missing_evidence"),
        passed=passed,
        validated=passed,
        detail=(
            "repo-local API/DB canary validated accepted and rejected strict-gate paths"
            if passed
            else "repo-local live canary evidence is missing or incomplete"
        ),
        blockers=blockers,
        evidence={
            "validation_scope": evidence.get("validation_scope"),
            "live_canary_validated": evidence.get("live_canary_validated"),
            "closure_claim": evidence.get("closure_claim"),
            "failed_validation_checks": failed_checks,
        },
    )


def _metric_24h_shape_boundary(metrics_artifact: Mapping[str, Any] | None) -> Boundary:
    artifact = _mapping(metrics_artifact)
    metrics = _mapping(artifact.get("metrics_24h"))
    window = _mapping(artifact.get("window"))
    guardrail = _mapping(artifact.get("guardrail_rollout"))
    live_boundaries = _mapping(artifact.get("live_boundaries"))
    source_record = _mapping(artifact.get("source_record"))
    total_attempts = metrics.get("total_attempts")
    inserted_total = metrics.get("inserted_total_count")
    inserted_valid = metrics.get("inserted_valid_count")
    rejected = metrics.get("rejected_count")
    contract_version = artifact.get("contract_version")
    is_production_evidence = contract_version == PRODUCTION_24H_METRICS_CONTRACT_VERSION

    checks = {
        "contract_version": contract_version
        in {
            "ingest.canary_24h_metrics_artifact.v1",
            PRODUCTION_24H_METRICS_CONTRACT_VERSION,
        },
        "window_hours_at_least_24": int(window.get("window_hours") or 0) >= 24,
        "rejection_rate_reviewed": _rate_matches(metrics.get("rejection_rate"), rejected, total_attempts),
        "inserted_valid_ratio_reviewed": _rate_matches(
            metrics.get("inserted_valid_ratio"),
            inserted_valid,
            inserted_total,
        ),
        "guardrail_rollout_counts_reviewed": bool(
            guardrail.get("strict_enabled_samples")
            and guardrail.get("canary_matched_samples")
            and guardrail.get("guardrail_rollout_counts_review_present") is True
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    shape_passed = bool(artifact) and not failed
    production_checks = {
        "production_contract_version": is_production_evidence,
        "artifact_kind": artifact.get("artifact_kind") == "production_ingest_canary_24h_metrics_readback",
        "status_passed": artifact.get("status") == "passed",
        "deterministic_fixture_false": artifact.get("deterministic_fixture") is False,
        "evidence_scope_production": artifact.get("evidence_scope") == "production",
        "live_window_observed": window.get("live_window_observed") is True,
        "production_data_claim": live_boundaries.get("production_data_claim") is True,
        "metric_24h_live_readback_claim": live_boundaries.get("metric_24h_live_readback_claim") is True,
        "source_record_present": _string_present(source_record.get("record_id"))
        and _string_present(source_record.get("system"))
        and _string_present(source_record.get("generated_at")),
    }
    production_failed = [name for name, passed in production_checks.items() if not passed]
    production_satisfied = (
        shape_passed
        and is_production_evidence
        and not production_failed
    )
    blockers = [] if shape_passed else ["repo_local_24h_metric_shape_invalid"]
    if shape_passed and is_production_evidence and not production_satisfied:
        blockers.append(PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER)
    elif shape_passed and not production_satisfied:
        blockers.extend(PRODUCTION_24H_BLOCKERS)
    return Boundary(
        name="metric_24h_readback",
        status=(
            "production_validated"
            if production_satisfied
            else ("repo_local_shape_validated_production_open" if shape_passed else "failed_evidence")
        ),
        passed=shape_passed,
        validated=production_satisfied,
        detail=(
            "production 24h metric evidence is present but incomplete"
            if shape_passed and is_production_evidence and not production_satisfied
            else (
                "repo-local 24h metric shape is valid, but the artifact does not claim production data"
                if shape_passed and not production_satisfied
                else (
                    "production 24h metric evidence is validated"
                    if production_satisfied
                    else "24h metric evidence is missing or invalid"
                )
            )
        ),
        blockers=blockers,
        evidence={
            "checks": checks,
            "failed_checks": failed,
            "production_checks": production_checks if is_production_evidence else {},
            "production_failed_checks": production_failed if is_production_evidence else [],
            "deterministic_fixture": artifact.get("deterministic_fixture"),
            "contract_version": contract_version,
            "artifact_kind": artifact.get("artifact_kind"),
            "window_hours": window.get("window_hours"),
            "live_window_observed": window.get("live_window_observed"),
            "rejection_rate": metrics.get("rejection_rate"),
            "inserted_valid_ratio": metrics.get("inserted_valid_ratio"),
            "production_data_claim": live_boundaries.get("production_data_claim"),
            "metric_24h_live_readback_claim": live_boundaries.get("metric_24h_live_readback_claim"),
            "source_record_id": source_record.get("record_id"),
            "source_system": source_record.get("system"),
        },
    )


def _ops_promotion_boundary(ops_promotion_evidence: Mapping[str, Any] | None) -> Boundary:
    evidence = _mapping(ops_promotion_evidence)
    checks = {
        "contract_version": evidence.get("contract_version") == OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION,
        "evidence_scope_operations": evidence.get("evidence_scope") == "operations",
        "operations_approval_recorded": evidence.get("operations_approval_recorded") is True,
        "production_24h_metrics_reviewed": evidence.get("production_24h_metrics_reviewed") is True,
        "rollback_plan_recorded": evidence.get("rollback_plan_recorded") is True,
        "promotion_decision_is_promote": str(evidence.get("promotion_decision") or "").strip().lower() == "promote",
        "strict_gate_global_default_enabled": evidence.get("strict_gate_global_default_enabled") is True,
        "approved_by_present": _string_present(evidence.get("approved_by")),
        "approved_at_present": _string_present(evidence.get("approved_at")),
        "approval_ticket_present": _string_present(evidence.get("approval_ticket")),
        "rollback_plan_ref_present": _string_present(evidence.get("rollback_plan_ref")),
    }
    failed = [name for name, passed in checks.items() if not passed]
    passed = bool(evidence) and not failed
    blockers = [] if passed else ([OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER] if evidence else list(OPS_PROMOTION_BLOCKERS))
    return Boundary(
        name="ops_strict_gate_promotion",
        status="validated" if passed else ("failed_evidence" if evidence else "missing_evidence"),
        passed=passed,
        validated=passed,
        detail=(
            "operations promotion evidence records all-project strict-gate enablement"
            if passed
            else "all-project strict-gate promotion is operations-owned and not satisfied locally"
        ),
        blockers=blockers,
        evidence={
            "checks": checks,
            "failed_checks": failed,
            "contract_version": evidence.get("contract_version"),
            "evidence_scope": evidence.get("evidence_scope"),
            "promotion_decision": evidence.get("promotion_decision"),
            "strict_gate_global_default_enabled": evidence.get("strict_gate_global_default_enabled"),
            "approval_ticket": evidence.get("approval_ticket"),
        },
    )


def build_strict_promotion_readiness(
    *,
    project_key: str = "demo_proj",
    live_canary_evidence: Mapping[str, Any] | None,
    metrics_artifact: Mapping[str, Any] | None,
    ops_promotion_evidence: Mapping[str, Any] | None = None,
    closure_claim: bool = False,
) -> StrictPromotionReadiness:
    live_boundary = _live_canary_boundary(live_canary_evidence)
    metric_boundary = _metric_24h_shape_boundary(metrics_artifact)
    ops_boundary = _ops_promotion_boundary(ops_promotion_evidence)
    boundaries = [live_boundary, metric_boundary, ops_boundary]

    repo_local_preflight_passed = live_boundary.passed and metric_boundary.passed
    remaining_ids = []
    if not live_boundary.passed:
        remaining_ids.extend(live_boundary.blockers)
    if not metric_boundary.validated:
        remaining_ids.extend(metric_boundary.blockers)
    if not ops_boundary.validated:
        remaining_ids.extend(ops_boundary.blockers)

    deduped_remaining = list(dict.fromkeys(remaining_ids))
    production_24h_satisfied = metric_boundary.validated
    strict_gate_satisfied = ops_boundary.validated and production_24h_satisfied
    closed = bool(closure_claim and repo_local_preflight_passed and production_24h_satisfied and strict_gate_satisfied)
    if closed:
        status = "closed"
    elif repo_local_preflight_passed:
        status = "external_blocked"
    else:
        status = "repo_local_blocked"

    return StrictPromotionReadiness(
        contract_version=CONTRACT_VERSION,
        status=status,
        project_key=str(project_key or "demo_proj").strip() or "demo_proj",
        closure_claim=closed,
        repo_local_preflight_passed=repo_local_preflight_passed,
        repo_local_live_canary_validated=live_boundary.passed,
        repo_local_metric_24h_shape_validated=metric_boundary.passed,
        production_24h_metrics_satisfied=production_24h_satisfied,
        strict_gate_promotion_satisfied=strict_gate_satisfied,
        promotion_recommendation=(
            "do_not_promote_without_production_24h_metrics_and_operations_decision"
            if not strict_gate_satisfied
            else "promotion_evidence_satisfied"
        ),
        boundaries=boundaries,
        remaining_external_blockers=[
            {"id": blocker, "classification": "external_live_operational"} for blocker in deduped_remaining
        ],
    )


def validate_strict_promotion_readiness(report: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version mismatch")
    remaining = report.get("remaining_external_blockers")
    remaining_ids = {
        item.get("id")
        for item in remaining
        if isinstance(item, Mapping)
    } if isinstance(remaining, list) else set()
    status = report.get("status")
    if report.get("closure_claim") is not False and report.get("status") != "closed":
        errors.append("closure_claim can only be true when status is closed")
    if status == "closed":
        if report.get("closure_claim") is not True:
            errors.append("closed status requires closure_claim true")
        if report.get("repo_local_preflight_passed") is not True:
            errors.append("closed status requires repo_local_preflight_passed true")
        if report.get("production_24h_metrics_satisfied") is not True:
            errors.append("closed status requires production_24h_metrics_satisfied true")
        if report.get("strict_gate_promotion_satisfied") is not True:
            errors.append("closed status requires strict_gate_promotion_satisfied true")
        if remaining:
            errors.append("closed status must not include remaining_external_blockers")
    if status == "external_blocked" and not remaining:
        errors.append("external_blocked status requires remaining_external_blockers")
    if report.get("repo_local_preflight_passed") is True and report.get("status") not in {"external_blocked", "closed"}:
        errors.append("repo_local_preflight_passed requires external_blocked or closed status")
    if report.get("production_24h_metrics_satisfied") is False and not report.get("remaining_external_blockers"):
        errors.append("open production 24h metrics must have explicit external blockers")
    if report.get("strict_gate_promotion_satisfied") is False and not report.get("remaining_external_blockers"):
        errors.append("open strict-gate promotion must have explicit external blockers")
    if report.get("strict_gate_promotion_satisfied") is True and report.get("production_24h_metrics_satisfied") is not True:
        errors.append("strict_gate_promotion_satisfied requires production_24h_metrics_satisfied")
    production_blocker_ids = set(PRODUCTION_24H_BLOCKERS) | {PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER}
    if report.get("production_24h_metrics_satisfied") is True and production_blocker_ids.intersection(remaining_ids):
        errors.append("satisfied production 24h metrics must not keep production blockers")
    ops_blocker_ids = set(OPS_PROMOTION_BLOCKERS) | {OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER}
    if report.get("strict_gate_promotion_satisfied") is True and ops_blocker_ids.intersection(remaining_ids):
        errors.append("satisfied strict-gate promotion must not keep ops blockers")
    boundaries = report.get("boundaries")
    if not isinstance(boundaries, list) or len(boundaries) != 3:
        errors.append("report must include three boundaries")
    return errors


__all__ = [
    "CONTRACT_VERSION",
    "OPS_PROMOTION_BLOCKERS",
    "OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER",
    "OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION",
    "PRODUCTION_24H_BLOCKERS",
    "PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER",
    "PRODUCTION_24H_METRICS_CONTRACT_VERSION",
    "StrictPromotionReadiness",
    "build_strict_promotion_readiness",
    "validate_strict_promotion_readiness",
]
