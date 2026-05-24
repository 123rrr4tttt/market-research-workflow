from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping

from .canary_handoff import LIVE_CANARY_EVIDENCE_CONTRACT_VERSION


CONTRACT_VERSION = "ingest.canary_strict_promotion_readiness.v1"
PRODUCTION_24H_METRICS_CONTRACT_VERSION = "ingest.production_24h_metrics_readback.v1"
PRODUCTION_24H_METRICS_ARTIFACT_KIND = "production_ingest_canary_24h_metrics_readback"
OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION = "ingest.ops_strict_gate_promotion_evidence.v1"
OPS_STRICT_GATE_PROMOTION_ARTIFACT_KIND = "ops_strict_gate_promotion_evidence"

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
    closure_requested: bool
    closure_claim: bool
    closure_request_status: str
    repo_local_readiness_status: str
    production_24h_metrics_artifact_status: str
    ops_promotion_artifact_status: str
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


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _string_present(value: Any) -> bool:
    return bool(str(value or "").strip())


def _timestamp_present(value: Any) -> bool:
    text = str(value or "").strip()
    if "T" not in text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


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


def _metric_count_checks(metrics: Mapping[str, Any], guardrail: Mapping[str, Any]) -> dict[str, bool]:
    total_attempts = _integer(metrics.get("total_attempts"))
    rejected = _integer(metrics.get("rejected_count"))
    inserted_total = _integer(metrics.get("inserted_total_count"))
    inserted_valid = _integer(metrics.get("inserted_valid_count"))
    inserted_invalid = _integer(metrics.get("inserted_invalid_count"))
    counts = (total_attempts, rejected, inserted_total, inserted_valid, inserted_invalid)
    counts_present = all(value is not None for value in counts)
    counts_non_negative = counts_present and all(value >= 0 for value in counts if value is not None)
    return {
        "metric_counts_present": counts_present,
        "metric_counts_non_negative": counts_non_negative,
        "metric_total_attempts_positive": total_attempts is not None and total_attempts > 0,
        "metric_rejected_inserted_total_consistent": counts_present
        and rejected + inserted_total == total_attempts,
        "metric_inserted_valid_invalid_consistent": counts_present
        and inserted_valid + inserted_invalid == inserted_total,
        "guardrail_rollout_counts_match_total_attempts": total_attempts is not None
        and _integer(guardrail.get("strict_enabled_samples")) == total_attempts
        and _integer(guardrail.get("canary_matched_samples")) == total_attempts,
    }


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


def _metric_24h_shape_boundary(
    metrics_artifact: Mapping[str, Any] | None,
    *,
    production_metrics_artifact: Mapping[str, Any] | None = None,
    production_metrics_artifact_attached: bool = False,
) -> Boundary:
    artifact = _mapping(metrics_artifact)
    metrics = _mapping(artifact.get("metrics_24h"))
    window = _mapping(artifact.get("window"))
    guardrail = _mapping(artifact.get("guardrail_rollout"))
    total_attempts = metrics.get("total_attempts")
    inserted_total = metrics.get("inserted_total_count")
    inserted_valid = metrics.get("inserted_valid_count")
    rejected = metrics.get("rejected_count")
    contract_version = artifact.get("contract_version")

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
    checks.update(_metric_count_checks(metrics, guardrail))
    failed = [name for name, passed in checks.items() if not passed]
    shape_passed = bool(artifact) and not failed

    production_artifact = _mapping(production_metrics_artifact) if production_metrics_artifact is not None else artifact
    production_attached = (
        production_metrics_artifact_attached
        or production_metrics_artifact is not None
        or production_artifact.get("contract_version") == PRODUCTION_24H_METRICS_CONTRACT_VERSION
    )
    production_metrics = _mapping(production_artifact.get("metrics_24h"))
    production_window = _mapping(production_artifact.get("window"))
    production_guardrail = _mapping(production_artifact.get("guardrail_rollout"))
    production_live_boundaries = _mapping(production_artifact.get("live_boundaries"))
    production_source_record = _mapping(production_artifact.get("source_record"))
    production_total_attempts = production_metrics.get("total_attempts")
    production_inserted_total = production_metrics.get("inserted_total_count")
    production_inserted_valid = production_metrics.get("inserted_valid_count")
    production_rejected = production_metrics.get("rejected_count")
    production_contract_version = production_artifact.get("contract_version")
    is_production_evidence = production_contract_version == PRODUCTION_24H_METRICS_CONTRACT_VERSION
    production_shape_checks = {
        "contract_version": production_contract_version
        in {
            "ingest.canary_24h_metrics_artifact.v1",
            PRODUCTION_24H_METRICS_CONTRACT_VERSION,
        },
        "window_hours_at_least_24": int(production_window.get("window_hours") or 0) >= 24,
        "rejection_rate_reviewed": _rate_matches(
            production_metrics.get("rejection_rate"),
            production_rejected,
            production_total_attempts,
        ),
        "inserted_valid_ratio_reviewed": _rate_matches(
            production_metrics.get("inserted_valid_ratio"),
            production_inserted_valid,
            production_inserted_total,
        ),
        "guardrail_rollout_counts_reviewed": bool(
            production_guardrail.get("strict_enabled_samples")
            and production_guardrail.get("canary_matched_samples")
            and production_guardrail.get("guardrail_rollout_counts_review_present") is True
        ),
    }
    production_shape_checks.update(_metric_count_checks(production_metrics, production_guardrail))
    production_shape_failed = [name for name, passed in production_shape_checks.items() if not passed]
    production_shape_passed = bool(production_artifact) and not production_shape_failed
    production_checks = {
        "production_contract_version": is_production_evidence,
        "artifact_kind": production_artifact.get("artifact_kind") == PRODUCTION_24H_METRICS_ARTIFACT_KIND,
        "status_passed": production_artifact.get("status") == "passed",
        "deterministic_fixture_false": production_artifact.get("deterministic_fixture") is False,
        "evidence_scope_production": production_artifact.get("evidence_scope") == "production",
        "live_window_observed": production_window.get("live_window_observed") is True,
        "production_data_claim": production_live_boundaries.get("production_data_claim") is True,
        "metric_24h_live_readback_claim": production_live_boundaries.get("metric_24h_live_readback_claim") is True,
        "live_boundaries_closure_claim_false": production_live_boundaries.get("closure_claim") is False,
        "source_record_present": _string_present(production_source_record.get("record_id"))
        and _string_present(production_source_record.get("system"))
        and _string_present(production_source_record.get("generated_at")),
        "source_record_generated_at_timestamp": _timestamp_present(production_source_record.get("generated_at")),
    }
    production_failed = [name for name, passed in production_checks.items() if not passed]
    production_satisfied = (
        production_shape_passed
        and is_production_evidence
        and not production_failed
    )
    blockers = [] if shape_passed else ["repo_local_24h_metric_shape_invalid"]
    if shape_passed and production_attached and not production_satisfied:
        blockers.append(PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER)
    elif shape_passed and not production_satisfied:
        blockers.extend(PRODUCTION_24H_BLOCKERS)
    return Boundary(
        name="metric_24h_readback",
        status=(
            "production_validated"
            if production_satisfied
            else (
                "production_artifact_invalid"
                if shape_passed and production_attached
                else ("repo_local_shape_validated_production_open" if shape_passed else "failed_evidence")
            )
        ),
        passed=shape_passed,
        validated=production_satisfied,
        detail=(
            "production 24h metric evidence is present but incomplete"
            if shape_passed and production_attached and not production_satisfied
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
            "production_artifact_attached": production_attached,
            "production_checks": production_checks if is_production_evidence else {},
            "production_shape_checks": production_shape_checks if production_attached else {},
            "production_shape_failed_checks": production_shape_failed if production_attached else [],
            "production_failed_checks": production_failed if is_production_evidence else [],
            "deterministic_fixture": artifact.get("deterministic_fixture"),
            "contract_version": contract_version,
            "artifact_kind": artifact.get("artifact_kind"),
            "window_hours": window.get("window_hours"),
            "live_window_observed": window.get("live_window_observed"),
            "rejection_rate": metrics.get("rejection_rate"),
            "inserted_valid_ratio": metrics.get("inserted_valid_ratio"),
            "production_contract_version": production_contract_version,
            "production_artifact_kind": production_artifact.get("artifact_kind"),
            "production_deterministic_fixture": production_artifact.get("deterministic_fixture"),
            "production_live_window_observed": production_window.get("live_window_observed"),
            "production_data_claim": production_live_boundaries.get("production_data_claim"),
            "metric_24h_live_readback_claim": production_live_boundaries.get("metric_24h_live_readback_claim"),
            "source_record_id": production_source_record.get("record_id"),
            "source_system": production_source_record.get("system"),
        },
    )


def _ops_promotion_boundary(ops_promotion_evidence: Mapping[str, Any] | None) -> Boundary:
    evidence = _mapping(ops_promotion_evidence)
    checks = {
        "contract_version": evidence.get("contract_version") == OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION,
        "artifact_kind": evidence.get("artifact_kind") == OPS_STRICT_GATE_PROMOTION_ARTIFACT_KIND,
        "evidence_scope_operations": evidence.get("evidence_scope") == "operations",
        "operations_approval_recorded": evidence.get("operations_approval_recorded") is True,
        "production_24h_metrics_reviewed": evidence.get("production_24h_metrics_reviewed") is True,
        "rollback_plan_recorded": evidence.get("rollback_plan_recorded") is True,
        "promotion_decision_is_promote": str(evidence.get("promotion_decision") or "").strip().lower() == "promote",
        "strict_gate_global_default_enabled": evidence.get("strict_gate_global_default_enabled") is True,
        "approved_by_present": _string_present(evidence.get("approved_by")),
        "approved_at_present": _string_present(evidence.get("approved_at")),
        "approved_at_timestamp": _timestamp_present(evidence.get("approved_at")),
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
    production_metrics_artifact: Mapping[str, Any] | None = None,
    production_metrics_artifact_attached: bool = False,
    ops_promotion_evidence: Mapping[str, Any] | None = None,
    ops_promotion_artifact_attached: bool = False,
    closure_claim: bool = False,
) -> StrictPromotionReadiness:
    live_boundary = _live_canary_boundary(live_canary_evidence)
    metric_boundary = _metric_24h_shape_boundary(
        metrics_artifact,
        production_metrics_artifact=production_metrics_artifact,
        production_metrics_artifact_attached=production_metrics_artifact_attached,
    )
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
    closure_request_status = (
        "claimed_closed"
        if closed
        else ("requested_but_blocked" if closure_claim else "not_requested")
    )
    production_artifact_attached = bool(metric_boundary.evidence.get("production_artifact_attached"))
    production_artifact_status = (
        "attached_validated"
        if production_24h_satisfied
        else ("attached_invalid" if production_artifact_attached else "not_attached")
    )
    ops_artifact_attached = ops_promotion_artifact_attached or ops_promotion_evidence is not None
    ops_artifact_status = (
        "attached_validated"
        if ops_boundary.validated
        else ("attached_invalid" if ops_artifact_attached else "not_attached")
    )
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
        closure_requested=bool(closure_claim),
        closure_claim=closed,
        closure_request_status=closure_request_status,
        repo_local_readiness_status="validated" if repo_local_preflight_passed else "blocked",
        production_24h_metrics_artifact_status=production_artifact_status,
        ops_promotion_artifact_status=ops_artifact_status,
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
    if not isinstance(report.get("closure_requested"), bool):
        errors.append("closure_requested must be boolean")
    remaining = report.get("remaining_external_blockers")
    remaining_ids = {
        item.get("id")
        for item in remaining
        if isinstance(item, Mapping)
    } if isinstance(remaining, list) else set()
    status = report.get("status")
    if report.get("closure_claim") is not False and report.get("status") != "closed":
        errors.append("closure_claim can only be true when status is closed")
    if report.get("closure_claim") is True and report.get("closure_requested") is not True:
        errors.append("closure_claim requires closure_requested true")
    closure_request_status = report.get("closure_request_status")
    if closure_request_status not in {"not_requested", "requested_but_blocked", "claimed_closed"}:
        errors.append("closure_request_status invalid")
    if report.get("closure_requested") is False and closure_request_status != "not_requested":
        errors.append("unrequested closure must use closure_request_status not_requested")
    if report.get("closure_requested") is True and report.get("closure_claim") is False and closure_request_status != "requested_but_blocked":
        errors.append("blocked closure request must use closure_request_status requested_but_blocked")
    if report.get("closure_claim") is True and closure_request_status != "claimed_closed":
        errors.append("claimed closure must use closure_request_status claimed_closed")
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
    repo_local_status = report.get("repo_local_readiness_status")
    if repo_local_status not in {"validated", "blocked"}:
        errors.append("repo_local_readiness_status invalid")
    if report.get("repo_local_preflight_passed") is True and repo_local_status != "validated":
        errors.append("repo_local_preflight_passed requires repo_local_readiness_status validated")
    if report.get("repo_local_preflight_passed") is False and repo_local_status != "blocked":
        errors.append("repo_local_preflight_passed false requires repo_local_readiness_status blocked")
    if report.get("production_24h_metrics_satisfied") is False and not report.get("remaining_external_blockers"):
        errors.append("open production 24h metrics must have explicit external blockers")
    if report.get("strict_gate_promotion_satisfied") is False and not report.get("remaining_external_blockers"):
        errors.append("open strict-gate promotion must have explicit external blockers")
    production_artifact_status = report.get("production_24h_metrics_artifact_status")
    if production_artifact_status not in {"not_attached", "attached_invalid", "attached_validated"}:
        errors.append("production_24h_metrics_artifact_status invalid")
    if report.get("production_24h_metrics_satisfied") is True and production_artifact_status != "attached_validated":
        errors.append("satisfied production 24h metrics require attached_validated artifact status")
    ops_artifact_status = report.get("ops_promotion_artifact_status")
    if ops_artifact_status not in {"not_attached", "attached_invalid", "attached_validated"}:
        errors.append("ops_promotion_artifact_status invalid")
    if ops_artifact_status == "attached_validated" and not any(
        isinstance(boundary, Mapping)
        and boundary.get("name") == "ops_strict_gate_promotion"
        and boundary.get("validated") is True
        for boundary in report.get("boundaries", []) or []
    ):
        errors.append("attached_validated ops artifact status requires validated ops boundary")
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
    "OPS_STRICT_GATE_PROMOTION_ARTIFACT_KIND",
    "OPS_PROMOTION_BLOCKERS",
    "OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER",
    "OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION",
    "PRODUCTION_24H_METRICS_ARTIFACT_KIND",
    "PRODUCTION_24H_BLOCKERS",
    "PRODUCTION_24H_EVIDENCE_INVALID_BLOCKER",
    "PRODUCTION_24H_METRICS_CONTRACT_VERSION",
    "StrictPromotionReadiness",
    "build_strict_promotion_readiness",
    "validate_strict_promotion_readiness",
]
