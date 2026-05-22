from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ...settings.config import settings


ROLLOUT_CONTRACT_VERSION = "ingest.guardrail_rollout.v1"
READINESS_CONTRACT_VERSION = "ingest.guardrail_rollout_readiness.v1"
ALLOWED_GUARDRAIL_ROLLOUT_MODES = {"off", "canary", "on", "passthrough"}
_DEFAULT_ROLLOUT_MODE = "canary"


@dataclass(frozen=True)
class IngestGuardrailRolloutDecision:
    contract_version: str
    enable_strict_gate: bool
    strict_gate_source: str
    rollout_mode: str
    project_key: str | None
    rollout_eligible: bool
    canary_projects: list[str]
    canary_matched: bool
    global_default_enabled: bool
    live_canary_validated: bool
    closure_claim: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IngestGuardrailRolloutCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class IngestGuardrailRolloutReadiness:
    contract_version: str
    mode: str
    rollout_mode: str
    canary_projects: list[str]
    ready_for_repo_rollout: bool
    response_visibility_fields: list[str]
    metrics_visibility_fields: list[str]
    live_canary_validated: bool
    closure_claim: bool
    checks: list[IngestGuardrailRolloutCheck]
    remaining_live_gap: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_rollout_mode(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"", "canary", "gray", "grey", "project_canary"}:
        return "canary"
    if raw in {"on", "all", "enabled", "full", "global"}:
        return "on"
    if raw in {"off", "disabled", "rollback"}:
        return "off"
    if raw in {"passthrough", "inherit", "legacy", "request_only"}:
        return "passthrough"
    return _DEFAULT_ROLLOUT_MODE


def _parse_project_allowlist(value: str | list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = str(value or "").split(",")
    return sorted({str(item).strip().lower() for item in raw_items if str(item or "").strip()})


def _rollout_check(name: str, passed: bool, detail: str) -> IngestGuardrailRolloutCheck:
    return IngestGuardrailRolloutCheck(name=name, passed=bool(passed), detail=detail)


def resolve_ingest_guardrail_rollout_decision(
    *,
    project_key: str | None,
    settings_enabled: bool | None = None,
    request_enabled: bool | None = None,
    strict_mode_enabled: bool | None = None,
    rollout_eligible: bool = True,
    rollout_mode: str | None = None,
    canary_projects: str | list[str] | tuple[str, ...] | set[str] | None = None,
) -> IngestGuardrailRolloutDecision:
    settings_gate_enabled = (
        bool(getattr(settings, "ingest_enable_strict_gate", False))
        if settings_enabled is None
        else bool(settings_enabled)
    )
    request_gate_enabled = bool(request_enabled)
    strict_mode_gate_enabled = bool(strict_mode_enabled)
    mode = _normalize_rollout_mode(
        rollout_mode if rollout_mode is not None else getattr(settings, "ingest_guardrail_rollout_mode", _DEFAULT_ROLLOUT_MODE)
    )
    projects = _parse_project_allowlist(
        canary_projects
        if canary_projects is not None
        else getattr(settings, "ingest_guardrail_canary_projects", "demo_proj")
    )
    normalized_project = str(project_key or "").strip().lower() or None
    canary_matched = bool(normalized_project and normalized_project in set(projects))

    eligible = bool(rollout_eligible)

    if settings_gate_enabled:
        enabled = True
        source = "settings.ingest_enable_strict_gate"
    elif request_gate_enabled:
        enabled = True
        source = "terminal_context.meaningful_gate_config"
    elif strict_mode_gate_enabled:
        enabled = True
        source = "terminal_context.strict_mode"
    elif eligible and mode == "on":
        enabled = True
        source = "settings.ingest_guardrail_rollout_mode"
    elif eligible and mode == "canary" and canary_matched:
        enabled = True
        source = "settings.ingest_guardrail_rollout_mode:canary"
    else:
        enabled = False
        source = "disabled"

    return IngestGuardrailRolloutDecision(
        contract_version=ROLLOUT_CONTRACT_VERSION,
        enable_strict_gate=enabled,
        strict_gate_source=source,
        rollout_mode=mode,
        project_key=normalized_project,
        rollout_eligible=eligible,
        canary_projects=projects,
        canary_matched=canary_matched,
        global_default_enabled=bool(mode == "on"),
        live_canary_validated=False,
        closure_claim=False,
    )


def build_ingest_guardrail_rollout_readiness(
    *,
    rollout_mode: str,
    canary_projects: list[str] | tuple[str, ...] | set[str] | None,
    response_visibility_fields: list[str] | tuple[str, ...] | set[str],
    metrics_visibility_fields: list[str] | tuple[str, ...] | set[str],
) -> IngestGuardrailRolloutReadiness:
    mode = _normalize_rollout_mode(rollout_mode)
    projects = _parse_project_allowlist(canary_projects)
    response_fields = sorted({str(field).strip() for field in response_visibility_fields if str(field or "").strip()})
    metrics_fields = sorted({str(field).strip() for field in metrics_visibility_fields if str(field or "").strip()})
    required_response_fields = {
        "quality_assessment.strict_gate_enabled",
        "quality_assessment.strict_gate_source",
        "quality_gates.gate_config.guardrail_rollout",
    }
    required_metrics_fields = {
        "metrics_payload.guardrail_rollout.strict_enabled_samples",
        "metrics_payload.guardrail_rollout.canary_matched_samples",
        "metrics_payload.guardrail_rollout.strict_gate_source_counts",
    }
    response_field_set = set(response_fields)
    metrics_field_set = set(metrics_fields)
    checks = [
        _rollout_check(
            "rollout_mode_allowed",
            mode in ALLOWED_GUARDRAIL_ROLLOUT_MODES,
            f"rollout_mode={mode!r} allowed={sorted(ALLOWED_GUARDRAIL_ROLLOUT_MODES)}",
        ),
        _rollout_check(
            "canary_has_project_scope",
            mode != "canary" or bool(projects),
            "canary rollout requires at least one explicit project",
        ),
        _rollout_check(
            "response_visibility_fields_present",
            required_response_fields.issubset(response_field_set),
            f"required={sorted(required_response_fields)} actual={response_fields}",
        ),
        _rollout_check(
            "metrics_visibility_fields_present",
            required_metrics_fields.issubset(metrics_field_set),
            f"required={sorted(required_metrics_fields)} actual={metrics_fields}",
        ),
    ]
    ready = all(check.passed for check in checks)
    return IngestGuardrailRolloutReadiness(
        contract_version=READINESS_CONTRACT_VERSION,
        mode="repo_deterministic_guardrail_rollout_readiness",
        rollout_mode=mode,
        canary_projects=projects,
        ready_for_repo_rollout=ready,
        response_visibility_fields=response_fields,
        metrics_visibility_fields=metrics_fields,
        live_canary_validated=False,
        closure_claim=False,
        checks=checks,
        remaining_live_gap=[
            "demo_proj live canary execution still must be run against configured services",
            "24h rejection and inserted_valid ratios still must be inspected before all-project rollout",
            "production default strict gate enablement remains an operations decision",
        ],
    )


__all__ = [
    "ALLOWED_GUARDRAIL_ROLLOUT_MODES",
    "READINESS_CONTRACT_VERSION",
    "ROLLOUT_CONTRACT_VERSION",
    "IngestGuardrailRolloutDecision",
    "IngestGuardrailRolloutReadiness",
    "build_ingest_guardrail_rollout_readiness",
    "resolve_ingest_guardrail_rollout_decision",
]
