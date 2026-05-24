from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .gate_reason_codes import normalize_reason_code
from .metrics_payload import build_metrics_payload_for_result


CANARY_HANDOFF_CONTRACT_VERSION = "ingest.single_url_canary_handoff.v1"
CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION = "ingest.single_url_canary_metrics_snapshot.v1"
LIVE_CANARY_EVIDENCE_CONTRACT_VERSION = "ingest.single_url_canary_handoff.live_evidence.v1"

_LIVE_CANARY_EXECUTION_GAP = "demo_proj live canary execution has not been run against configured services"
_METRIC_24H_READBACK_GAP = "24h rejection-rate and inserted-valid ratios have not been inspected"
_PRODUCTION_STRICT_GATE_GAP = "production all-project strict-gate enablement remains operations-owned"

REMAINING_LIVE_RUN_GAPS: tuple[str, ...] = (
    _LIVE_CANARY_EXECUTION_GAP,
    _METRIC_24H_READBACK_GAP,
    _PRODUCTION_STRICT_GATE_GAP,
)

REMAINING_POST_LIVE_CANARY_GAPS: tuple[str, ...] = (
    _METRIC_24H_READBACK_GAP,
    _PRODUCTION_STRICT_GATE_GAP,
)


def build_single_url_canary_handoff(
    *,
    ingress_envelope: Mapping[str, Any] | None,
    postprocess_frontdoor: Mapping[str, Any] | None,
    writer_result: Mapping[str, Any] | None = None,
    metrics_payload: Mapping[str, Any] | None = None,
    fallback_adapter: str = "source_library_frontdoor",
    live_canary_validated: bool | None = None,
    closure_claim: bool | None = None,
    live_canary_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ingress = dict(ingress_envelope or {})
    postprocess = dict(postprocess_frontdoor or {})
    data = postprocess.get("data") if isinstance(postprocess.get("data"), dict) else {}
    meta = postprocess.get("meta") if isinstance(postprocess.get("meta"), dict) else {}
    source_ref = ingress.get("source_ref") if isinstance(ingress.get("source_ref"), dict) else {}
    quality_assessment = data.get("quality_assessment") if isinstance(data.get("quality_assessment"), dict) else {}
    quality_gates = data.get("quality_gates") if isinstance(data.get("quality_gates"), dict) else {}
    gate_plus = quality_gates.get("gate_plus") if isinstance(quality_gates.get("gate_plus"), dict) else {}
    gate_config = quality_gates.get("gate_config") if isinstance(quality_gates.get("gate_config"), dict) else {}
    rollout = _extract_guardrail_rollout(quality_assessment, gate_config)
    resolved_writer = _resolve_writer_result(data, writer_result)
    reason_code = normalize_reason_code(meta.get("reason_code") or data.get("admission") or "ok", default="ok")
    admission = str(data.get("admission") or "unknown").strip().lower() or "unknown"
    strict_enabled = bool(
        quality_assessment.get("strict_gate_enabled", gate_config.get("enable_strict_gate", rollout.get("enable_strict_gate")))
    )
    strict_source = str(
        quality_assessment.get("strict_gate_source")
        or gate_config.get("strict_gate_source")
        or rollout.get("strict_gate_source")
        or "disabled"
    )
    gate_state = _resolve_gate_state(
        strict_enabled=strict_enabled,
        admission=admission,
        gate_plus=gate_plus,
    )
    metrics = _build_metrics_snapshot(
        postprocess=postprocess,
        writer_result=resolved_writer,
        rollout=rollout,
        fallback_adapter=fallback_adapter,
        provided_metrics=metrics_payload,
    )
    evidence = _normalize_live_canary_evidence(live_canary_evidence)
    live_validated = bool(
        live_canary_validated
        if live_canary_validated is not None
        else _live_canary_evidence_validated(evidence)
        or rollout.get("live_canary_validated")
        or (metrics.get("guardrail_rollout") or {}).get("live_canary_validated")
    )
    closed = bool(
        closure_claim
        if closure_claim is not None
        else (evidence.get("closure_claim") if evidence else False)
        or rollout.get("closure_claim")
        or (metrics.get("guardrail_rollout") or {}).get("closure_claim")
    )
    if not live_validated:
        closed = False
    _apply_live_flags_to_metrics(metrics, live_canary_validated=live_validated, closure_claim=closed)

    return {
        "contract_version": CANARY_HANDOFF_CONTRACT_VERSION,
        "handoff_state": "closed" if closed else ("live_canary_validated" if live_validated else "partial_live_gap_open"),
        "frontdoor_run": {
            "ingress_contract_version": ingress.get("contract_version"),
            "ingress_type": ingress.get("ingress_type"),
            "entrypoint": ingress.get("entrypoint"),
            "source_mode": ingress.get("source_mode"),
            "project_key": ingress.get("project_key"),
            "source_url": source_ref.get("url") or source_ref.get("locator"),
            "trace_id": meta.get("trace_id") or ((ingress.get("meta") or {}).get("trace_id") if isinstance(ingress.get("meta"), dict) else None),
            "payload_hash": (ingress.get("meta") or {}).get("payload_hash") if isinstance(ingress.get("meta"), dict) else None,
            "route_hint": source_ref.get("frontdoor_route_hint"),
            "fetch_strategy": source_ref.get("fetch_strategy"),
            "router_state": source_ref.get("router_state"),
            "router_reason_code": source_ref.get("router_reason_code"),
        },
        "strict_gate_state": {
            "state": gate_state,
            "strict_gate_enabled": strict_enabled,
            "strict_gate_source": strict_source,
            "admission": admission,
            "reason_code": reason_code,
            "blocked": bool(gate_plus.get("blocked")),
            "blocked_stage": gate_plus.get("blocked_stage"),
            "blocked_reason": gate_plus.get("blocked_reason"),
            "quality_score": _coerce_float(quality_assessment.get("quality_score")),
            "meaningful": bool(quality_assessment.get("meaningful")),
            "provenance_ok": bool(quality_assessment.get("provenance_ok")),
            "content_ok": bool(quality_assessment.get("content_ok")),
        },
        "rollout": {
            "channel": _resolve_rollout_channel(rollout=rollout, strict_gate_source=strict_source),
            "rollout_mode": str(rollout.get("rollout_mode") or quality_assessment.get("guardrail_rollout_mode") or "unknown"),
            "project_key": rollout.get("project_key") or ingress.get("project_key"),
            "canary_projects": list(rollout.get("canary_projects") or []),
            "canary_matched": bool(rollout.get("canary_matched") or quality_assessment.get("guardrail_canary_matched")),
            "global_default_enabled": bool(rollout.get("global_default_enabled")),
            "decision_contract_version": rollout.get("contract_version"),
        },
        "metrics_snapshot": metrics,
        "live_canary_evidence": evidence or None,
        "live_canary_validated": live_validated,
        "closure_claim": closed,
        "remaining_live_run_gaps": _remaining_live_run_gaps(
            live_canary_validated=live_validated,
            closure_claim=closed,
        ),
    }


def _extract_guardrail_rollout(
    quality_assessment: Mapping[str, Any],
    gate_config: Mapping[str, Any],
) -> dict[str, Any]:
    rollout = gate_config.get("guardrail_rollout") if isinstance(gate_config.get("guardrail_rollout"), dict) else {}
    out = dict(rollout or {})
    out.setdefault("enable_strict_gate", bool(gate_config.get("enable_strict_gate")))
    out.setdefault("strict_gate_source", str(gate_config.get("strict_gate_source") or quality_assessment.get("strict_gate_source") or "disabled"))
    out.setdefault("rollout_mode", str(quality_assessment.get("guardrail_rollout_mode") or out.get("rollout_mode") or "unknown"))
    out.setdefault("canary_matched", bool(quality_assessment.get("guardrail_canary_matched")))
    out.setdefault("closure_claim", bool(quality_assessment.get("guardrail_closure_claim")))
    out.setdefault("live_canary_validated", False)
    return out


def _resolve_writer_result(
    data: Mapping[str, Any],
    writer_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(writer_result, Mapping):
        return dict(writer_result)
    embedded = data.get("writer_result") if isinstance(data.get("writer_result"), dict) else {}
    return dict(embedded or {})


def _build_metrics_snapshot(
    *,
    postprocess: Mapping[str, Any],
    writer_result: Mapping[str, Any],
    rollout: Mapping[str, Any],
    fallback_adapter: str,
    provided_metrics: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(provided_metrics, Mapping) and provided_metrics:
        payload = deepcopy(dict(provided_metrics))
    else:
        data = postprocess.get("data") if isinstance(postprocess.get("data"), dict) else {}
        meta = postprocess.get("meta") if isinstance(postprocess.get("meta"), dict) else {}
        admission = str(data.get("admission") or "").strip().lower()
        inserted_valid = _coerce_non_negative_int(writer_result.get("inserted"))
        rejected_count = 0 if admission in {"", "accept"} else 1
        payload = build_metrics_payload_for_result(
            {
                "inserted_valid": inserted_valid,
                "reason_code": normalize_reason_code(meta.get("reason_code") or data.get("admission") or "ok", default="ok"),
                "rejected_count": rejected_count,
                "guardrail_rollout": dict(rollout or {}),
                "single_write_workflow": fallback_adapter,
            },
            fallback_adapter=fallback_adapter,
        )
    guardrail = payload.get("guardrail_rollout") if isinstance(payload.get("guardrail_rollout"), dict) else {}
    return {
        "contract_version": CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION,
        "metrics_payload_schema_version": payload.get("schema_version"),
        "sample_size": _coerce_non_negative_int(payload.get("sample_size")),
        "url_only_document_rate": _coerce_float(payload.get("url_only_document_rate")),
        "empty_body_rate": _coerce_float(payload.get("empty_body_rate")),
        "reason_code_top_n": deepcopy(list(payload.get("reason_code_top_n") or [])),
        "adapter_hit_rate": deepcopy(list(payload.get("adapter_hit_rate") or [])),
        "guardrail_rollout": deepcopy(dict(guardrail or {})),
        "counters": deepcopy(dict(payload.get("counters") or {})),
    }


def _resolve_gate_state(
    *,
    strict_enabled: bool,
    admission: str,
    gate_plus: Mapping[str, Any],
) -> str:
    if not strict_enabled:
        return "strict_disabled"
    if admission == "accept" and not bool(gate_plus.get("blocked")):
        return "strict_passed"
    if admission in {"reject", "return_for_cleanup"} or bool(gate_plus.get("blocked")):
        return "strict_blocked"
    return "strict_pending"


def _resolve_rollout_channel(
    *,
    rollout: Mapping[str, Any],
    strict_gate_source: str,
) -> str:
    source = str(strict_gate_source or "").strip().lower()
    mode = str(rollout.get("rollout_mode") or "").strip().lower()
    if bool(rollout.get("canary_matched")) or source.endswith(":canary"):
        return "canary"
    if bool(rollout.get("global_default_enabled")) or mode == "on":
        return "global"
    if source == "settings.ingest_enable_strict_gate":
        return "settings_override"
    if source.startswith("terminal_context."):
        return "request_override"
    if mode == "passthrough":
        return "passthrough"
    if not bool(rollout.get("enable_strict_gate")) or source == "disabled":
        return "disabled"
    return "unknown"


def _coerce_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _normalize_live_canary_evidence(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {}
    evidence = deepcopy(dict(value))
    evidence.setdefault("contract_version", LIVE_CANARY_EVIDENCE_CONTRACT_VERSION)
    evidence["live_canary_validated"] = bool(
        evidence.get("live_canary_validated") or _live_canary_evidence_validated(evidence)
    )
    evidence["closure_claim"] = bool(evidence.get("closure_claim"))
    return evidence


def _live_canary_evidence_validated(evidence: Mapping[str, Any] | None) -> bool:
    if not isinstance(evidence, Mapping) or not evidence:
        return False
    if evidence.get("live_canary_validated") is True:
        return True
    checks = evidence.get("validation_checks")
    if not isinstance(checks, Mapping):
        return False
    required = {
        "api_runtime_validated",
        "db_readback_validated",
        "guardrail_pass_observed",
        "guardrail_block_observed",
        "handoff_readback_present",
    }
    return all(checks.get(name) is True for name in required)


def _apply_live_flags_to_metrics(
    metrics: dict[str, Any],
    *,
    live_canary_validated: bool,
    closure_claim: bool,
) -> None:
    guardrail = metrics.get("guardrail_rollout")
    if not isinstance(guardrail, dict):
        return
    guardrail["live_canary_validated"] = bool(live_canary_validated)
    guardrail["closure_claim"] = bool(closure_claim)


def _remaining_live_run_gaps(
    *,
    live_canary_validated: bool,
    closure_claim: bool,
) -> list[str]:
    if closure_claim:
        return []
    if live_canary_validated:
        return [_METRIC_24H_READBACK_GAP, _PRODUCTION_STRICT_GATE_GAP]
    return list(REMAINING_LIVE_RUN_GAPS)


__all__ = [
    "CANARY_HANDOFF_CONTRACT_VERSION",
    "CANARY_METRICS_SNAPSHOT_CONTRACT_VERSION",
    "LIVE_CANARY_EVIDENCE_CONTRACT_VERSION",
    "REMAINING_LIVE_RUN_GAPS",
    "REMAINING_POST_LIVE_CANARY_GAPS",
    "build_single_url_canary_handoff",
]
