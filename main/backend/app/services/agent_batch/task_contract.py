from __future__ import annotations

from copy import deepcopy
import re
from typing import Annotated, Any, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.agent_service_semantics import agent_batch_failures

AGENT_BATCH_TASK_MANIFEST_VERSION = "agent_batch.task_manifest.v1"
AGENT_BATCH_SEARCH_POLICY_CONTRACT_VERSION = "agent_batch.search_policy.v1"
AGENT_BATCH_SEARCH_QUALITY_REPLAY_CONTRACT_VERSION = "agent_batch.search_quality_replay.v1"
AGENT_BATCH_PROVIDER_QUALITY_READINESS_CONTRACT_VERSION = "agent_batch.provider_quality_readiness.v1"
AGENT_BATCH_LIVE_QUALITY_THRESHOLD_CONTRACT_VERSION = "agent_batch.live_quality_threshold.v1"
AGENT_BATCH_QUALITY_PROMOTION_READBACK_CONTRACT_VERSION = (
    "agent_batch.quality_promotion_readback.v1"
)

_TASK_OPTIONAL_KEYS = [
    "task_id",
    "query_terms",
    "urls",
    "max_items",
    "provider",
    "language",
    "days_back",
    "item_key",
    "scope",
    "platforms",
    "source_mode",
    "override_params",
]

_RETRIEVAL_MODE_SOURCE_ONLY = "source_only"

_SEARCH_MARKET_OVERRIDE_ALLOWED_KEYS = [
    "enable_extraction",
    "start_offset",
    "require_approval",
    "approval_token",
]

_SOURCE_LIBRARY_OVERRIDE_ALLOWED_KEYS = [
    "query_terms",
    "keywords",
    "search_keywords",
    "base_keywords",
    "topic_keywords",
    "urls",
    "max_items",
    "limit",
    "provider",
    "language",
    "lang",
    "scope",
    "platforms",
    "source_mode",
    "pool_scope",
    "enable_extraction",
    "keyword_batch_size",
    "per_keyword_limit",
    "_allow_internal_generic_web",
    "_handler_key",
    "_handler_site_entry_count",
    "require_approval",
    "approval_token",
    "workflow_run_id",
    "trace_id",
]

_OVERRIDE_PROMOTION_FIELDS_BY_CHANNEL = {
    "source_library": [
        "query_terms",
        "urls",
        "max_items",
        "provider",
        "language",
        "scope",
        "platforms",
        "source_mode",
    ],
}

_RUNTIME_PARAM_ALIASES_BY_CHANNEL = {
    "source_library": {
        "query_terms": ["query_terms", "keywords", "search_keywords", "base_keywords", "topic_keywords"],
        "urls": ["urls"],
        "limit": ["limit", "max_items"],
        "provider": ["provider"],
        "language": ["language"],
        "scope": ["scope"],
        "platforms": ["platforms"],
        "source_mode": ["source_mode"],
    }
}


def _raise_legacy_agent_batch_failure(failure: Failure) -> NoReturn:
    """Lift one closed core failure into the legacy public exception ABI."""
    if not agent_batch_failures.matches(failure):
        # kit:boundary owner=agent_batch.public_abi class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w02_abi_lift_rejects_non_agent_batch_failure_as_programmer_defect
        raise TypeError("agent batch ABI lift requires an agent.batch.failure")

    message = failure.message
    if failure.code == "approval_not_found":
        # kit:boundary owner=agent_batch.public_abi class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=agent.batch.failure witness=test:test_w02_legacy_lift_preserves_public_exception_observation
        raise KeyError("approval_token_not_found")
    if failure.code == "approval_expired":
        # kit:boundary owner=agent_batch.public_abi class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=agent.batch.failure witness=test:test_w02_legacy_lift_preserves_public_exception_observation
        raise ValueError("approval_token_expired")
    if failure.code == "approval_token_required":
        # kit:boundary owner=agent_batch.public_abi class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=agent.batch.failure witness=test:test_w02_legacy_lift_preserves_public_exception_observation
        raise ValueError("approval_token is required")
    if failure.code in {"channel_unknown", "lane_invalid"}:
        # kit:boundary owner=agent_batch.public_abi class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=agent.batch.failure witness=test:test_w02_legacy_lift_preserves_public_exception_observation
        raise (KeyError(message) if failure.code == "channel_unknown" else ValueError(message))
    # kit:boundary owner=agent_batch.public_abi class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w02_abi_lift_rejects_non_agent_batch_failure_as_programmer_defect
    raise TypeError(f"unsupported agent batch failure code: {failure.code}")

_RETRY_ACTION_ALLOWED_VALUES = [
    "expand_query_terms",
    "narrow_query_terms",
    "shift_time_window",
    "change_provider",
    "attach_source_library",
    "replace_source_library",
    "stop",
]

_REWRITE_ELIGIBLE_FIELDS_BY_CHANNEL = {
    "search.market": [
        "query_terms",
        "max_items",
        "provider",
        "language",
        "days_back",
        "override_params",
    ],
    "source_library": [
        "item_key",
        "query_terms",
        "urls",
        "max_items",
        "provider",
        "language",
        "scope",
        "platforms",
        "source_mode",
        "override_params",
    ],
}

_SEARCH_BRIEF_SCHEMA = {
    "contract_version": AGENT_BATCH_SEARCH_POLICY_CONTRACT_VERSION,
    "artifact": "search_brief",
    "required_keys": [
        "intent",
        "goal",
        "coverage_axes",
        "time_strategy",
        "search_strategies",
        "source_preferences",
        "stop_conditions",
    ],
    "optional_keys": [
        "query_plan",
        "language",
        "notes",
    ],
    "time_strategy_required_keys": ["mode", "days_back"],
    "search_strategy_required_keys": ["label", "query_terms"],
    "source_preferences_required_keys": ["attach_source_library", "candidate_items"],
    "stop_conditions_required_keys": ["min_entity_count", "min_source_domains", "max_search_rounds"],
}

_SEARCH_CRITIC_SCHEMA = {
    "contract_version": AGENT_BATCH_SEARCH_POLICY_CONTRACT_VERSION,
    "artifact": "search_critic",
    "required_keys": [
        "score",
        "coverage",
        "diagnosis",
        "next_action",
    ],
    "optional_keys": [
        "rewrite",
        "reason_codes",
    ],
    "coverage_keys": [
        "entity_coverage",
        "source_diversity",
        "freshness_fit",
        "goal_alignment",
        "novelty_gain",
    ],
    "next_action_allowed_values": [
        "retry_with_precision_query",
        "retry_with_broader_query",
        "retry_with_source_library",
        "retry_with_time_shift",
        "stop",
    ],
}

_SEARCH_QUALITY_REPLAY_SCHEMA = {
    "contract_version": AGENT_BATCH_SEARCH_QUALITY_REPLAY_CONTRACT_VERSION,
    "artifact": "search_quality_replay",
    "scope": "deterministic_no_network_symbolic_search_quality_replay",
    "required_keys": [
        "scope",
        "score",
        "coverage",
        "source_quality_signals",
        "live_provider_gap_state",
    ],
    "source_quality_signal_required_keys": [
        "record_id",
        "domain",
        "channel",
        "provider",
        "provider_trace_state",
        "provider_live_verified",
        "axis_hits",
        "freshness_fit",
        "domain_relevance",
        "source_quality_score",
    ],
    "coverage_keys": [
        "entity_coverage",
        "source_diversity",
        "freshness_fit",
        "goal_alignment",
        "novelty_gain",
        "source_quality",
    ],
    "live_provider_gap_required_keys": [
        "status",
        "live_provider_probe_performed",
        "providers_not_started",
        "quality_claim_allowed",
        "reason",
    ],
    "benchmark_uplift_required_keys": [
        "average_baseline_score",
        "average_retry_score",
        "average_uplift",
        "false_positive_retry_rate",
    ],
}

_PROVIDER_QUALITY_READINESS_SCHEMA = {
    "contract_version": AGENT_BATCH_PROVIDER_QUALITY_READINESS_CONTRACT_VERSION,
    "artifact": "provider_quality_readiness",
    "scope": "symbolic_search_provider_quality_readiness_fixture_quality_and_live_gap_boundary",
    "required_keys": [
        "scope",
        "readiness_state",
        "fixture_quality",
        "provider_readiness",
        "unsupported_live_provider_claims",
        "remaining_live_gaps",
        "gate_semantics",
    ],
    "fixture_quality_required_keys": [
        "status",
        "case_count",
        "average_uplift",
        "false_positive_retry_rate",
        "quality_claim_allowed",
        "live_provider_gap_state",
    ],
    "provider_readiness_required_keys": [
        "probe_type",
        "providers",
        "quality_claim_allowed",
        "auto_promotion_allowed",
    ],
    "provider_row_required_keys": [
        "provider",
        "live_probe_status",
        "availability_state",
        "result_quality_verified",
        "quality_claim_allowed",
        "fallback_reason",
        "remaining_gap",
    ],
    "unsupported_claim_required_keys": [
        "code",
        "claim",
        "reason",
        "required_next_evidence",
    ],
    "remaining_live_gap_required_keys": [
        "code",
        "status",
        "reason",
        "required_next_evidence",
    ],
}

_LIVE_QUALITY_THRESHOLD_SCHEMA = {
    "contract_version": AGENT_BATCH_LIVE_QUALITY_THRESHOLD_CONTRACT_VERSION,
    "artifact": "live_quality_threshold",
    "scope": "symbolic_search_live_provider_quality_threshold_contract",
    "required_keys": [
        "scope",
        "threshold_version",
        "quality_thresholds",
        "fixture_quality_boundary",
        "replay_evaluation",
        "threshold_status",
        "live_provider_replay_closed",
        "quality_claim_allowed",
        "unsupported_live_provider_claims",
        "remaining_live_gaps",
    ],
    "quality_threshold_required_keys": [
        "required_providers",
        "min_case_count",
        "min_results_per_provider",
        "min_source_domains",
        "min_relevance_score",
        "min_freshness_score",
        "max_duplicate_rate",
        "max_timeout_rate",
        "max_p95_latency_ms",
        "min_review_sample_count",
        "require_trace_success",
    ],
    "provider_evaluation_required_keys": [
        "provider",
        "replay_status",
        "case_count",
        "result_count",
        "source_domain_count",
        "relevance_score",
        "freshness_score",
        "duplicate_rate",
        "timeout_rate",
        "p95_latency_ms",
        "review_sample_count",
        "trace_success",
        "thresholds_met",
        "quality_claim_allowed",
        "remaining_gap",
    ],
    "unsupported_claim_required_keys": [
        "code",
        "claim",
        "reason",
        "required_next_evidence",
    ],
    "remaining_live_gap_required_keys": [
        "code",
        "status",
        "reason",
        "required_next_evidence",
    ],
}

_QUALITY_PROMOTION_READBACK_SCHEMA = {
    "contract_version": AGENT_BATCH_QUALITY_PROMOTION_READBACK_CONTRACT_VERSION,
    "artifact": "quality_promotion_readback",
    "scope": "provider_independent_symbolic_quality_promotion_readback",
    "required_keys": [
        "scope",
        "fixture_search_brief",
        "critic_score_readback",
        "bounded_retry_readback",
        "quality_threshold_readback",
        "promotion_decision",
        "promotion_decision_readback",
        "provider_independent_boundary",
        "unsupported_promotion_claims",
        "remaining_live_gaps",
    ],
    "fixture_search_brief_required_keys": [
        "case_id",
        "intent",
        "goal",
        "coverage_axes",
        "time_strategy",
        "search_strategy_count",
        "candidate_items",
    ],
    "critic_score_required_keys": [
        "case_id",
        "score",
        "score_threshold",
        "next_action",
        "reason_codes",
        "retry_score_source",
    ],
    "bounded_retry_required_keys": [
        "enabled",
        "retry_budget",
        "max_retry_rounds",
        "retry_allowed_count",
        "retry_blocked_count",
        "replay_score_is_observational",
    ],
    "quality_threshold_required_keys": [
        "threshold_status",
        "fixture_threshold_status",
        "live_provider_replay_closed",
        "quality_claim_allowed",
    ],
    "promotion_decision_required_keys": [
        "decision_id",
        "decision",
        "promotion_allowed",
        "provider_auto_promotion_allowed",
        "reason_codes",
        "required_next_evidence",
    ],
    "promotion_decision_readback_required_keys": [
        "readback_performed",
        "readback_matches_decision",
        "promotion_allowed",
        "provider_auto_promotion_allowed",
        "decision_digest",
    ],
}

_RETRY_ACTION_REQUIRED_REWRITE_FIELDS = {
    "expand_query_terms": ["query_terms"],
    "narrow_query_terms": ["query_terms"],
    "shift_time_window": ["days_back"],
    "change_provider": ["provider"],
    "attach_source_library": ["item_key"],
    "replace_source_library": ["item_key"],
    "stop": [],
}

_RETRY_ACTION_ALLOWED_REWRITE_FIELDS_BY_ACTION = {
    "expand_query_terms": ["query_terms", "max_items", "override_params"],
    "narrow_query_terms": ["query_terms", "max_items", "override_params"],
    "shift_time_window": ["days_back"],
    "change_provider": ["provider", "language", "override_params"],
    "attach_source_library": ["item_key", "query_terms", "urls", "max_items", "provider", "language", "scope", "platforms", "source_mode", "override_params"],
    "replace_source_library": ["item_key", "query_terms", "urls", "max_items", "provider", "language", "scope", "platforms", "source_mode", "override_params"],
    "stop": [],
}

_RETRY_ACTION_SCHEMA = {
    "contract_version": AGENT_BATCH_SEARCH_POLICY_CONTRACT_VERSION,
    "artifact": "retry_action",
    "required_keys": [
        "action",
        "reason",
    ],
    "optional_keys": [
        "channel",
        "rewrite",
        "target_items",
    ],
    "allowed_actions": list(_RETRY_ACTION_ALLOWED_VALUES),
    "required_rewrite_fields_by_action": deepcopy(_RETRY_ACTION_REQUIRED_REWRITE_FIELDS),
    "allowed_rewrite_fields_by_action": deepcopy(_RETRY_ACTION_ALLOWED_REWRITE_FIELDS_BY_ACTION),
    "fail_closed": True,
}

_SEARCH_POLICY_DEFAULTS = {
    "retry_budget": 1,
    "max_retry_rounds": 1,
    "retry_score_threshold": 0.72,
    "max_branch_count": 3,
    "branching_default_enabled": False,
    "critic_mode": "observe_only",
}

_SEARCH_POLICY_EVENT_NAMES = [
    "search_brief.created",
    "search_round.completed",
    "search_critic.scored",
    "search_retry.scheduled",
    "search_retry.skipped",
    "search_stop.completed",
]

_AGENT_BATCH_CHANNEL_SPECS: dict[str, dict[str, Any]] = {
    "search.market": {
        "channel": "search.market",
        "description": "General web/provider market search task.",
        "required_keys": ["channel", "query_terms"],
        "optional_keys": ["max_items", "provider", "language", "days_back", "task_id", "override_params"],
        "query_terms_rule": "non-empty string array",
        "override_params_schema": {
            "allowed_keys": list(_SEARCH_MARKET_OVERRIDE_ALLOWED_KEYS),
            "note": "Only these advanced controls are guaranteed to affect execution.",
        },
        "defaults": {"max_items": 20, "provider": "auto"},
        "execution": {
            "required_non_empty_keys": ["query_terms"],
            "default_lane": "main",
            "submitter_export": "_submit_search_market_job",
            "rule_guard_export": "_enforce_search_market_rule_set",
            "submit_item_fields": ["query_terms", "max_items", "provider", "language", "days_back", "override_params"],
            "dispatch": {
                "skill_id": "agent_batch.dispatch.market_collect",
                "required_permission": "agent_batch.dispatch.market_collect",
                "consumer": "agent_batch.dispatch.market_collect",
                "handler_export": "_skill_dispatch_market_collect",
                "trace_prefix": "dispatch-market",
                "payload_fields": [
                    "query_terms",
                    "max_items",
                    "project_key",
                    "provider",
                    "language",
                    "days_back",
                    "override_params",
                    "trace_id",
                    "lane",
                    "workflow_run_id",
                ],
            },
            "approval_binding": {
                "argv_prefix": ["task_ingest_market"],
                "value_field": "query_terms",
                "value_mode": "extend",
            },
        },
    },
    "source_library": {
        "channel": "source_library",
        "description": "Keyword search constrained to configured source sites (resolved by source library item_key).",
        "required_keys": ["channel", "item_key"],
        "optional_keys": [
            "task_id",
            "query_terms",
            "urls",
            "language",
            "max_items",
            "provider",
            "scope",
            "platforms",
            "source_mode",
            "override_params",
        ],
        "item_key_rule": "non-empty string",
        "override_params_schema": {
            "allowed_keys": [
                "keywords",
                "search_keywords",
                "base_keywords",
                "topic_keywords",
                "pool_scope",
                "enable_extraction",
                "keyword_batch_size",
                "per_keyword_limit",
                "_allow_internal_generic_web",
            ],
            "note": "Use top-level fields first; keep override_params for secondary item-specific tuning.",
        },
        "defaults": {"max_items": 20, "provider": "auto"},
        "execution": {
            "required_non_empty_keys": ["item_key"],
            "default_lane": "subagent",
            "submitter_export": "_submit_source_library_job",
            "submit_item_fields": [
                "item_key",
                "query_terms",
                "urls",
                "max_items",
                "provider",
                "language",
                "scope",
                "platforms",
                "source_mode",
                "override_params",
            ],
            "dispatch": {
                "skill_id": "agent_batch.dispatch.source_library_item",
                "required_permission": "agent_batch.dispatch.source_library_item",
                "consumer": "agent_batch.dispatch.source_library_item",
                "handler_export": "_skill_dispatch_source_library_item",
                "trace_prefix": "dispatch-source",
                "trace_hint_field": "item_key",
                "payload_fields": [
                    "item_key",
                    "project_key",
                    "override_params",
                    "trace_id",
                    "lane",
                    "workflow_run_id",
                ],
            },
            "approval_binding": {
                "argv_prefix": ["task_run_source_library_item"],
                "value_field": "item_key",
                "value_mode": "append",
            },
        },
    },
}


def _clone_channel_spec(spec: dict[str, Any], *, include_internal: bool) -> dict[str, Any]:
    cloned = deepcopy(spec)
    if not include_internal:
        cloned.pop("execution", None)
    return cloned


def build_search_brief_schema() -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task_contract_constants "
    "witness=test:test_w02_agent_authority_metadata"
]:
    return deepcopy(_SEARCH_BRIEF_SCHEMA)


def build_search_critic_schema() -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task_contract_constants "
    "witness=test:test_w02_agent_authority_metadata"
]:
    return deepcopy(_SEARCH_CRITIC_SCHEMA)


def build_search_quality_replay_schema() -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task_contract_constants "
    "witness=test:test_w02_agent_authority_metadata"
]:
    return deepcopy(_SEARCH_QUALITY_REPLAY_SCHEMA)


def build_provider_quality_readiness_schema() -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task_contract_constants "
    "witness=test:test_w02_agent_authority_metadata"
]:
    return deepcopy(_PROVIDER_QUALITY_READINESS_SCHEMA)


def build_live_quality_threshold_schema() -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task_contract_constants "
    "witness=test:test_w02_agent_authority_metadata"
]:
    return deepcopy(_LIVE_QUALITY_THRESHOLD_SCHEMA)


def build_quality_promotion_readback_schema() -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task_contract_constants "
    "witness=test:test_w02_agent_authority_metadata"
]:
    return deepcopy(_QUALITY_PROMOTION_READBACK_SCHEMA)


def build_retry_action_schema() -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task_contract_constants "
    "witness=test:test_w02_agent_authority_metadata"
]:
    return deepcopy(_RETRY_ACTION_SCHEMA)


def get_rewrite_eligible_fields_by_channel() -> dict[str, list[str]]:
    return {channel: list(fields) for channel, fields in _REWRITE_ELIGIBLE_FIELDS_BY_CHANNEL.items()}


def get_retry_action_allowed_fields(action: str, channel: str) -> list[str]:
    normalized_action = str(action or "").strip().lower()
    normalized_channel = str(channel or "").strip().lower()
    base_fields = list(_RETRY_ACTION_ALLOWED_REWRITE_FIELDS_BY_ACTION.get(normalized_action) or [])
    eligible_fields = set(_REWRITE_ELIGIBLE_FIELDS_BY_CHANNEL.get(normalized_channel) or [])
    return [field for field in base_fields if field in eligible_fields]


def get_retry_action_required_fields(action: str, channel: str) -> list[str]:
    normalized_action = str(action or "").strip().lower()
    normalized_channel = str(channel or "").strip().lower()
    base_fields = list(_RETRY_ACTION_REQUIRED_REWRITE_FIELDS.get(normalized_action) or [])
    eligible_fields = set(_REWRITE_ELIGIBLE_FIELDS_BY_CHANNEL.get(normalized_channel) or [])
    return [field for field in base_fields if field in eligible_fields]


def _normalize_retry_rewrite_value(field: str, value: Any) -> Any:
    if field == "query_terms":
        return normalize_query_terms(value)
    if field in {"urls", "platforms"}:
        return normalize_string_list(value)
    if field == "max_items":
        try:
            return max(1, min(100, int(value)))
        except Exception:
            return None
    if field == "days_back":
        return normalize_days_back(value)
    if field == "override_params":
        return dict(value or {}) if isinstance(value, dict) else None
    text = str(value or "").strip()
    return text or None


def validate_retry_action_payload(
    payload: dict[str, Any] | None,
    *,
    default_channel: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any]]:
    raw = dict(payload or {})
    action = str(raw.get("action") or "").strip().lower()
    if action not in _RETRY_ACTION_ALLOWED_VALUES:
        return None, "retry_action_invalid", {"action": action}

    reason = str(raw.get("reason") or "").strip()
    if not reason:
        return None, "retry_action_reason_missing", {"action": action}

    channel = str(raw.get("channel") or default_channel or "").strip().lower()
    if action != "stop" and channel not in _REWRITE_ELIGIBLE_FIELDS_BY_CHANNEL:
        return None, "retry_action_channel_invalid", {"channel": channel}

    raw_rewrite = raw.get("rewrite") or {}
    if not isinstance(raw_rewrite, dict):
        return None, "retry_action_rewrite_invalid", {"action": action}

    allowed_fields = set(get_retry_action_allowed_fields(action, channel))
    required_fields = set(get_retry_action_required_fields(action, channel))
    unsupported_fields = sorted(key for key in raw_rewrite.keys() if key not in allowed_fields)
    if unsupported_fields:
        return (
            None,
            "retry_action_rewrite_fields_unsupported",
            {
                "action": action,
                "channel": channel,
                "unsupported_fields": unsupported_fields,
                "allowed_fields": sorted(allowed_fields),
            },
        )

    normalized_rewrite: dict[str, Any] = {}
    for field in sorted(allowed_fields):
        if field not in raw_rewrite:
            continue
        normalized_value = _normalize_retry_rewrite_value(field, raw_rewrite.get(field))
        if normalized_value in (None, [], {}):
            continue
        normalized_rewrite[field] = normalized_value

    missing_required_fields = sorted(field for field in required_fields if field not in normalized_rewrite)
    if missing_required_fields:
        return (
            None,
            "retry_action_rewrite_fields_missing",
            {
                "action": action,
                "channel": channel,
                "missing_required_fields": missing_required_fields,
            },
        )

    return (
        {
            "action": action,
            "reason": reason,
            "channel": channel or None,
            "rewrite": normalized_rewrite,
            "target_items": normalize_string_list(raw.get("target_items")),
        },
        None,
        {},
    )


def get_search_policy_defaults() -> dict[str, Any]:
    return deepcopy(_SEARCH_POLICY_DEFAULTS)


def list_search_policy_event_names() -> list[str]:
    return list(_SEARCH_POLICY_EVENT_NAMES)


def build_search_policy_contract() -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task_contract_policy_sources "
    "witness=test:test_w02_agent_authority_metadata"
]:
    return {
        "contract_version": AGENT_BATCH_SEARCH_POLICY_CONTRACT_VERSION,
        "search_brief": build_search_brief_schema(),
        "search_critic": build_search_critic_schema(),
        "quality_replay": build_search_quality_replay_schema(),
        "provider_quality_readiness": build_provider_quality_readiness_schema(),
        "live_quality_threshold": build_live_quality_threshold_schema(),
        "quality_promotion_readback": build_quality_promotion_readback_schema(),
        "retry_action": build_retry_action_schema(),
        "rewrite_eligible_fields_by_channel": get_rewrite_eligible_fields_by_channel(),
        "defaults": get_search_policy_defaults(),
        "event_names": list_search_policy_event_names(),
    }


def get_agent_batch_task_contract_specs() -> dict[str, dict[str, Any]]:
    return {channel: _clone_channel_spec(spec, include_internal=False) for channel, spec in _AGENT_BATCH_CHANNEL_SPECS.items()}


def get_agent_batch_task_contract_spec(channel: str, *, include_internal: bool = False) -> dict[str, Any] | None:
    normalized_channel = str(channel or "").strip().lower()
    spec = _AGENT_BATCH_CHANNEL_SPECS.get(normalized_channel)
    if spec is None:
        return None
    return _clone_channel_spec(spec, include_internal=include_internal)


def get_agent_batch_known_channels() -> set[str]:
    return set(_AGENT_BATCH_CHANNEL_SPECS.keys())


def build_agent_batch_tasks_schema() -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task_contract_constants "
    "witness=test:test_w02_agent_authority_metadata"
]:
    return {
        "required_keys": ["channel"],
        "optional_keys": list(_TASK_OPTIONAL_KEYS),
    }


def build_agent_batch_manifest_entry(channel: str) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task_contract_policy_sources "
    "witness=test:test_w02_agent_authority_metadata"
]:
    spec = get_agent_batch_task_contract_spec(channel, include_internal=False)
    if spec is None:
        _raise_legacy_agent_batch_failure(
            agent_batch_failures.fail(
                "channel_unknown",
                f"unknown agent batch channel: {channel}",
                {"channel": str(channel or "")},
            )
        )
    spec["channel"] = str(channel or "").strip().lower()
    return spec


def get_allowed_override_params_by_channel() -> dict[str, set[str]]:
    return {
        "search.market": set(_SEARCH_MARKET_OVERRIDE_ALLOWED_KEYS),
        "source_library": set(_SOURCE_LIBRARY_OVERRIDE_ALLOWED_KEYS),
    }


def list_agent_batch_dispatch_skill_bindings() -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []
    for channel, spec in _AGENT_BATCH_CHANNEL_SPECS.items():
        execution = dict(spec.get("execution") or {})
        dispatch = dict(execution.get("dispatch") or {})
        skill_id = str(dispatch.get("skill_id") or "").strip()
        required_permission = str(dispatch.get("required_permission") or "").strip()
        handler_export = str(dispatch.get("handler_export") or "").strip()
        if not skill_id or not required_permission or not handler_export:
            continue
        bindings.append(
            {
                "channel": channel,
                "skill_id": skill_id,
                "required_permission": required_permission,
                "handler_export": handler_export,
            }
        )
    return bindings


def list_agent_batch_execution_bindings() -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []
    for channel, spec in _AGENT_BATCH_CHANNEL_SPECS.items():
        execution = dict(spec.get("execution") or {})
        submitter_export = str(execution.get("submitter_export") or "").strip()
        rule_guard_export = str(execution.get("rule_guard_export") or "").strip()
        binding = {
            "channel": channel,
            "submitter_export": submitter_export,
        }
        if rule_guard_export:
            binding["rule_guard_export"] = rule_guard_export
        if submitter_export:
            bindings.append(binding)
    return bindings


def build_agent_batch_execution_registry(
    *,
    execution_bindings: list[dict[str, str]] | None = None,
    globals_map: dict[str, Any] | None = None,
) -> Annotated[
    dict[str, dict[str, Any]],
    "kit:non-authoritative derived_as=view fact_source=task_contract_policy_sources "
    "witness=test:test_w02_agent_authority_metadata"
]:
    bindings = list(execution_bindings or list_agent_batch_execution_bindings())
    exported = dict(globals_map or {})
    registry: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        channel = str(binding.get("channel") or "").strip().lower()
        submitter_export = str(binding.get("submitter_export") or "").strip()
        rule_guard_export = str(binding.get("rule_guard_export") or "").strip()
        if not channel or not submitter_export:
            continue
        submitter = exported.get(submitter_export)
        if not callable(submitter):
            # kit:boundary owner=agent_batch.execution_registry class=PROGRAMMER_DEFECT failure_family=none witness=test:test_build_agent_batch_execution_registry_resolves_exports_and_fails_fast
            raise RuntimeError(f"channel submitter export not found: {submitter_export}")
        entry: dict[str, Any] = {"submitter": submitter}
        if rule_guard_export:
            rule_guard = exported.get(rule_guard_export)
            if not callable(rule_guard):
                # kit:boundary owner=agent_batch.execution_registry class=PROGRAMMER_DEFECT failure_family=none witness=test:test_build_agent_batch_execution_registry_resolves_exports_and_fails_fast
                raise RuntimeError(f"channel rule_guard export not found: {rule_guard_export}")
            entry["rule_guard"] = rule_guard
        registry[channel] = entry
    return registry


def normalize_days_back(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return max(1, min(365, parsed))


def normalize_query_terms(value: Any) -> list[str]:
    raw = value
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def normalize_agent_batch_task(task: dict[str, Any], *, idx: int, default_language: str) -> dict[str, Any]:
    raw_channel = str(task.get("channel") or "search.market").strip().lower() or "search.market"
    spec = get_agent_batch_task_contract_spec(raw_channel, include_internal=True)
    if spec is None:
        return {}

    defaults = dict(spec.get("defaults") or {})
    max_items_default = int(defaults.get("max_items") or 20)
    provider_default = str(defaults.get("provider") or "auto").strip() or "auto"
    source_mode_default = str(defaults.get("source_mode") or "").strip() or None

    try:
        max_items = int(task.get("max_items") if task.get("max_items") is not None else max_items_default)
    except Exception:
        max_items = max_items_default
    max_items = max(1, min(100, max_items))

    return {
        "task_id": str(task.get("task_id") or f"search_{idx}"),
        "channel": raw_channel,
        "query_terms": normalize_query_terms(task.get("query_terms")),
        "urls": normalize_string_list(task.get("urls")),
        "max_items": max_items,
        "provider": str(task.get("provider") or provider_default).strip() or provider_default,
        "language": str(task.get("language") or default_language).strip() or default_language,
        "days_back": normalize_days_back(task.get("days_back")),
        "item_key": str(task.get("item_key") or "").strip() or None,
        "scope": str(task.get("scope") or "").strip() or None,
        "platforms": normalize_string_list(task.get("platforms")) or None,
        "source_mode": str(task.get("source_mode") or source_mode_default or "").strip() or None,
        "override_params": dict(task.get("override_params") or {}),
    }


def _detect_language(command: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", str(command or "")) else "en"


def _resolve_source_collect_limit(*, tasks: list[dict[str, Any]], default: int = 20) -> int:
    limits: list[int] = []
    for task in tasks:
        channel = str(task.get("channel") or "").strip().lower()
        if channel not in {"search.market", "source_library"}:
            continue
        try:
            value = int(task.get("max_items") or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            limits.append(value)
    if not limits:
        return max(1, min(100, int(default or 20)))
    return max(1, min(100, max(limits)))


def _resolve_source_query_terms(*, tasks: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for task in tasks:
        channel = str(task.get("channel") or "").strip().lower()
        if channel != "search.market":
            continue
        for term in list(task.get("query_terms") or []):
            text = str(term or "").strip()
            if text and text not in out:
                out.append(text)
    return out


def _build_search_brief(
    *,
    command: str,
    intent: str,
    tasks: list[dict[str, Any]],
    retrieval_mode: str,
    autonomy_meta: dict[str, Any],
) -> dict[str, Any]:
    source_item_keys = [str(task.get("item_key") or "").strip() for task in tasks if str(task.get("channel") or "").strip().lower() == "source_library"]
    source_item_keys = [item_key for item_key in source_item_keys if item_key]
    search_strategies = _build_search_strategy_entries(tasks=tasks)
    return {
        "intent": str(intent or "market_research_general").strip() or "market_research_general",
        "goal": str(command or "").strip(),
        "coverage_axes": _infer_coverage_axes(command=command, tasks=tasks),
        "time_strategy": {
            "mode": _resolve_time_strategy_mode(tasks=tasks, retrieval_mode=retrieval_mode),
            "days_back": _resolve_search_brief_days_back(tasks=tasks),
        },
        "search_strategies": search_strategies,
        "source_preferences": {
            "attach_source_library": bool(autonomy_meta.get("enabled")) or bool(source_item_keys),
            "candidate_items": source_item_keys or list(autonomy_meta.get("item_keys") or []),
        },
        "stop_conditions": {
            "min_entity_count": 8,
            "min_source_domains": 4,
            "max_search_rounds": 2,
        },
    }


def _build_search_strategy_entries(*, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for _index, task in enumerate(tasks, start=1):
        channel = str(task.get("channel") or "").strip().lower()
        query_terms = list(task.get("query_terms") or [])
        if channel == "search.market" and query_terms:
            label = "broad" if len(entries) == 0 else "precision" if len(entries) == 1 else f"query_{len(entries) + 1}"
            entries.append({"label": label, "query_terms": query_terms})
    if entries:
        return entries

    source_item_keys = [str(task.get("item_key") or "").strip() for task in tasks if str(task.get("channel") or "").strip().lower() == "source_library"]
    source_item_keys = [item_key for item_key in source_item_keys if item_key]
    if source_item_keys:
        return [{"label": "source_library_only", "query_terms": source_item_keys}]
    return [{"label": "broad", "query_terms": ["市场研究"]}]


def _infer_coverage_axes(*, command: str, tasks: list[dict[str, Any]]) -> list[str]:
    text = f"{command} {' '.join(' '.join(list(task.get('query_terms') or [])) for task in tasks)}".lower()
    axes: list[str] = []

    axis_hints = [
        ("products", ("产品", "product", "sku", "device", "terminal")),
        ("companies", ("公司", "company", "companies", "vendor", "vendors", "厂商", "enterprise")),
        ("recent_movement", ("最近", "latest", "news", "动态", "发布", "融资", "trend")),
        ("policy", ("监管", "政策", "regulation", "policy", "standard")),
        ("pricing", ("价格", "pricing", "price", "报价")),
    ]
    for label, hints in axis_hints:
        if any(hint in text for hint in hints):
            axes.append(label)

    if not axes:
        axes.append("market_overview")
    return axes


def _resolve_search_brief_days_back(*, tasks: list[dict[str, Any]]) -> int | None:
    for task in tasks:
        days_back = task.get("days_back")
        if isinstance(days_back, int) and days_back > 0:
            return days_back
    return 30


def _resolve_time_strategy_mode(*, tasks: list[dict[str, Any]], retrieval_mode: str) -> str:
    if retrieval_mode == _RETRIEVAL_MODE_SOURCE_ONLY:
        return "source_only"
    if any(isinstance(task.get("days_back"), int) and int(task.get("days_back")) <= 30 for task in tasks):
        return "recent"
    if any(isinstance(task.get("days_back"), int) and int(task.get("days_back")) > 30 for task in tasks):
        return "historical_window"
    return "recent"


def _expand_tasks_with_limited_branching(
    *,
    tasks: list[dict[str, Any]],
    search_brief: dict[str, Any],
    retrieval_mode: str,
    enable_limited_branching: bool,
    command: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    branching = {
        "default_enabled": False,
        "enabled": False,
        "branch_count": 1,
        "reason": "disabled",
        "strategy_labels": [],
    }
    if not enable_limited_branching:
        return tasks, branching
    if retrieval_mode == _RETRIEVAL_MODE_SOURCE_ONLY:
        branching["reason"] = "source_only_mode"
        return tasks, branching
    if len(tasks) != 1:
        branching["reason"] = "multi_task_plan"
        return tasks, branching

    primary_task = dict(tasks[0])
    if str(primary_task.get("channel") or "").strip().lower() != "search.market":
        branching["reason"] = "non_search_market_task"
        return tasks, branching

    coverage_axes = list(search_brief.get("coverage_axes") or [])
    if len(coverage_axes) < 2:
        branching["reason"] = "low_ambiguity_prompt"
        return tasks, branching

    precision_terms = _build_precision_retry_query_terms(command=command, tasks=tasks, search_brief=search_brief)
    if not precision_terms:
        branching["reason"] = "precision_variant_unavailable"
        return tasks, branching
    if precision_terms == list(primary_task.get("query_terms") or []):
        branching["reason"] = "no_distinct_precision_variant"
        return tasks, branching

    default_language = str(primary_task.get("language") or _detect_language(command)).strip().lower() or _detect_language(command)
    broad_task = normalize_agent_batch_task(
        {
            **primary_task,
            "task_id": str(primary_task.get("task_id") or "search_1"),
        },
        idx=1,
        default_language=default_language,
    )
    precision_task = normalize_agent_batch_task(
        {
            **primary_task,
            "task_id": f"{str(primary_task.get('task_id') or 'search_1')}_branch_precision",
            "query_terms": precision_terms,
            "max_items": max(1, int(primary_task.get("max_items") or 20)),
        },
        idx=2,
        default_language=default_language,
    )
    if broad_task.get("query_terms") == precision_task.get("query_terms"):
        branching["reason"] = "precision_variant_collapsed"
        return tasks, branching

    branching.update(
        {
            "enabled": True,
            "branch_count": 2,
            "reason": "high_ambiguity_prompt",
            "strategy_labels": ["broad", "precision"],
        }
    )
    return [broad_task, precision_task], branching


def _build_precision_retry_query_terms(*, command: str, tasks: list[dict[str, Any]], search_brief: dict[str, Any]) -> list[str]:
    primary_task = next(
        (dict(task) for task in tasks if str(task.get("channel") or "").strip().lower() == "search.market"),
        dict(tasks[0]) if tasks else {},
    )
    base_query = " ".join(list(primary_task.get("query_terms") or [])).strip() or str(command or "").strip()
    if not base_query:
        return []

    language = str(primary_task.get("language") or _detect_language(command)).strip().lower()
    coverage_axes = list(search_brief.get("coverage_axes") or [])
    if language.startswith("zh"):
        axis_suffix = {
            "products": "产品",
            "companies": "公司 厂商",
            "recent_movement": "发布 融资 动态",
            "policy": "政策 监管",
            "pricing": "价格 报价",
        }
    else:
        axis_suffix = {
            "products": "products devices",
            "companies": "companies vendors",
            "recent_movement": "launches funding news",
            "policy": "policy regulation",
            "pricing": "pricing price",
        }

    suffix_tokens: list[str] = []
    for axis in coverage_axes:
        suffix = str(axis_suffix.get(str(axis)) or "").strip()
        if suffix:
            suffix_tokens.append(suffix)
    merged_query = " ".join([base_query] + suffix_tokens).strip()
    return [re.sub(r"\s+", " ", merged_query).strip()]


def _apply_retry_action(
    *,
    tasks: list[dict[str, Any]],
    retry_action: dict[str, Any],
    command: str,
) -> list[dict[str, Any]]:
    action = str(retry_action.get("action") or "").strip().lower()
    rewrite = dict(retry_action.get("rewrite") or {})
    channel = str(retry_action.get("channel") or "").strip().lower()
    default_language = _detect_language(command)
    if action == "stop":
        return list(tasks)

    normalized: list[dict[str, Any]] = []
    if action == "attach_source_library":
        item_key = str(rewrite.get("item_key") or "").strip()
        if not item_key:
            return list(tasks)
        existing_keys = {str(task.get("item_key") or "").strip() for task in tasks}
        if item_key in existing_keys:
            return list(tasks)
        normalized.extend(
            [
                normalize_agent_batch_task(task, idx=idx, default_language=default_language)
                for idx, task in enumerate(tasks, start=1)
            ]
        )
        requested_max_items = rewrite.get("max_items")
        if requested_max_items is None:
            requested_max_items = _resolve_source_collect_limit(tasks=normalized, default=20)
        requested_query_terms = list(rewrite.get("query_terms") or [])
        if not requested_query_terms:
            requested_query_terms = _resolve_source_query_terms(tasks=normalized)
        normalized.append(
            normalize_agent_batch_task(
                {
                    "channel": "source_library",
                    "item_key": item_key,
                    "query_terms": requested_query_terms,
                    "max_items": requested_max_items,
                    "provider": rewrite.get("provider") or "auto",
                    "language": rewrite.get("language"),
                    "scope": rewrite.get("scope"),
                    "platforms": list(rewrite.get("platforms") or []),
                    "source_mode": rewrite.get("source_mode"),
                    "urls": list(rewrite.get("urls") or []),
                    "override_params": dict(rewrite.get("override_params") or {}),
                },
                idx=len(tasks) + 1,
                default_language=default_language,
            )
        )
        return normalized

    for idx, task in enumerate(tasks, start=1):
        normalized_task = normalize_agent_batch_task(task, idx=idx, default_language=default_language)
        if str(normalized_task.get("channel") or "").strip().lower() != channel:
            normalized.append(normalized_task)
            continue
        updated_task = dict(normalized_task)
        for field, value in rewrite.items():
            updated_task[field] = value
        normalized.append(normalize_agent_batch_task(updated_task, idx=idx, default_language=default_language))
    return normalized


def build_agent_batch_submit_item_data(task: dict[str, Any], *, idx: int, default_language: str) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=normalized_task_input "
    "witness=test:test_w02_agent_authority_metadata"
]:
    normalized = normalize_agent_batch_task(task, idx=idx, default_language=default_language)
    if not normalized:
        return {}
    return {
        "channel": normalized.get("channel"),
        "item_key": normalized.get("item_key"),
        "query_terms": list(normalized.get("query_terms") or []),
        "urls": list(normalized.get("urls") or []),
        "max_items": normalized.get("max_items"),
        "provider": normalized.get("provider"),
        "language": normalized.get("language") or None,
        "days_back": normalized.get("days_back"),
        "scope": normalized.get("scope"),
        "platforms": list(normalized.get("platforms") or []),
        "source_mode": normalized.get("source_mode"),
        "override_params": dict(normalized.get("override_params") or {}),
    }


def infer_agent_batch_channel(task: dict[str, Any] | None) -> str | None:
    raw = dict(task or {})
    channel = str(raw.get("channel") or "").strip().lower()
    if channel:
        return channel

    item_key = str(raw.get("item_key") or raw.get("source_id") or "").strip()
    if item_key:
        return "source_library"

    nested = raw.get("input")
    if isinstance(nested, dict):
        nested_item_key = str(nested.get("item_key") or nested.get("source_id") or "").strip()
        if nested_item_key:
            return "source_library"

    if normalize_query_terms(raw.get("query_terms")):
        return "search.market"
    if isinstance(nested, dict) and normalize_query_terms(nested.get("query_terms")):
        return "search.market"
    return None


def _has_required_value(task: dict[str, Any], key: str) -> bool:
    if key in {"query_terms"}:
        return bool(normalize_query_terms(task.get(key)))
    if key in {"urls", "platforms"}:
        return bool(normalize_string_list(task.get(key)))
    return bool(str(task.get(key) or "").strip())


def is_agent_batch_task_executable(task: dict[str, Any]) -> bool:
    channel = str(task.get("channel") or "search.market").strip().lower() or "search.market"
    spec = get_agent_batch_task_contract_spec(channel, include_internal=True)
    if spec is None:
        return False
    execution = dict(spec.get("execution") or {})
    required_non_empty_keys = list(execution.get("required_non_empty_keys") or [])
    return all(_has_required_value(task, key) for key in required_non_empty_keys)


def resolve_agent_batch_lane(channel: str, priority: int | None) -> str:
    spec = get_agent_batch_task_contract_spec(channel, include_internal=True)
    default_lane = str(((spec or {}).get("execution") or {}).get("default_lane") or "main").strip() or "main"
    if default_lane != "main":
        return default_lane
    if isinstance(priority, int) and priority >= 8:
        return "system"
    return default_lane


def build_agent_batch_dispatch_payload(channel: str, payload: dict[str, Any]) -> Annotated[
    dict[str, Any],
    "kit:prepared-command effect_boundary=task_contract "
    "witness=test:test_w02_agent_authority_metadata"
]:
    spec = get_agent_batch_task_contract_spec(channel, include_internal=True)
    if spec is None:
        _raise_legacy_agent_batch_failure(
            agent_batch_failures.fail("channel_unknown", f"unknown agent batch channel: {channel}", {"channel": str(channel or "")})
        )
    dispatch = dict(((spec.get("execution") or {}).get("dispatch") or {}))
    fields = list(dispatch.get("payload_fields") or [])
    out = {"channel": str(channel or "").strip().lower()}
    for field in fields:
        if field == "channel":
            continue
        if field in payload:
            out[field] = payload.get(field)
    return out


def build_agent_batch_dispatch_invocation(channel: str, payload: dict[str, Any], *, trace_id: str | None) -> Annotated[
    dict[str, Any],
    "kit:prepared-command effect_boundary=task_contract "
    "witness=test:test_w02_agent_authority_metadata"
]:
    spec = get_agent_batch_task_contract_spec(channel, include_internal=True)
    if spec is None:
        _raise_legacy_agent_batch_failure(
            agent_batch_failures.fail("channel_unknown", f"unknown agent batch channel: {channel}", {"channel": str(channel or "")})
        )
    dispatch = dict(((spec.get("execution") or {}).get("dispatch") or {}))
    skill_id = str(dispatch.get("skill_id") or "").strip()
    required_permission = str(dispatch.get("required_permission") or "").strip()
    consumer = str(dispatch.get("consumer") or skill_id).strip() or skill_id
    fallback_trace = str(dispatch.get("trace_prefix") or skill_id).strip() or skill_id
    trace_hint_field = str(dispatch.get("trace_hint_field") or "").strip()
    if trace_hint_field:
        trace_hint = str((payload or {}).get(trace_hint_field) or "").strip()
        if trace_hint:
            fallback_trace = f"{fallback_trace}-{trace_hint}"
    resolved_trace = str(trace_id or "").strip() or fallback_trace
    return {
        "skill_id": skill_id,
        "payload": build_agent_batch_dispatch_payload(channel, payload),
        "context": {
            "actor_role": "orchestration_runtime",
            "permissions": [required_permission],
            "trace_id": resolved_trace,
            "consumer": consumer,
        },
    }


def build_agent_batch_approval_argv(channel: str, payload: dict[str, Any]) -> Annotated[
    list[str],
    "kit:prepared-command effect_boundary=task_contract "
    "witness=test:test_w02_agent_authority_metadata"
]:
    spec = get_agent_batch_task_contract_spec(channel, include_internal=True)
    if spec is None:
        _raise_legacy_agent_batch_failure(
            agent_batch_failures.fail("channel_unknown", f"unknown agent batch channel: {channel}", {"channel": str(channel or "")})
        )
    approval_binding = dict(((spec.get("execution") or {}).get("approval_binding") or {}))
    argv = [str(item) for item in list(approval_binding.get("argv_prefix") or []) if str(item or "").strip()]
    value_field = str(approval_binding.get("value_field") or "").strip()
    value_mode = str(approval_binding.get("value_mode") or "append").strip().lower() or "append"
    value = (payload or {}).get(value_field)
    if value_mode == "extend":
        argv.extend(normalize_query_terms(value))
    else:
        candidate = str(value or "").strip()
        if candidate:
            argv.append(candidate)
    return argv


def build_business_override_params(channel: str, task: dict[str, Any], *, workflow_run_id: str | None) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task+workflow_run_id "
    "witness=test:test_w02_agent_authority_metadata"
]:
    normalized_channel = str(channel or "").strip().lower()
    override_params = dict(task.get("override_params") or {})
    if normalized_channel not in _OVERRIDE_PROMOTION_FIELDS_BY_CHANNEL:
        if str(workflow_run_id or "").strip():
            override_params.setdefault("workflow_run_id", str(workflow_run_id).strip())
        return override_params
    if normalized_channel == "source_library":
        override_params.pop("source_mode", None)

    query_terms = normalize_query_terms(task.get("query_terms"))
    urls = normalize_string_list(task.get("urls"))
    platforms = normalize_string_list(task.get("platforms"))

    if query_terms:
        override_params["query_terms"] = query_terms
    if urls:
        override_params["urls"] = urls

    max_items = task.get("max_items")
    if max_items is not None:
        try:
            max_items_int = int(max_items)
        except Exception:
            max_items_int = None
        if max_items_int is not None:
            override_params["max_items"] = max_items_int
            override_params["limit"] = max_items_int

    if str(task.get("provider") or "").strip():
        override_params["provider"] = str(task.get("provider")).strip()
    if str(task.get("language") or "").strip():
        override_params["language"] = str(task.get("language")).strip()
    if str(task.get("scope") or "").strip():
        override_params["scope"] = str(task.get("scope")).strip()
    if platforms:
        override_params["platforms"] = platforms
    if str(workflow_run_id or "").strip():
        override_params["workflow_run_id"] = str(workflow_run_id).strip()
    return override_params


def build_source_library_override_params(task: dict[str, Any], *, workflow_run_id: str | None) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=business_override+workflow_run_id "
    "witness=test:test_w02_agent_authority_metadata"
]:
    return build_business_override_params("source_library", task, workflow_run_id=workflow_run_id)


def parse_business_runtime_params(channel: str, override_params: dict[str, Any] | None) -> dict[str, Any]:
    normalized_channel = str(channel or "").strip().lower()
    ov = dict(override_params or {})
    aliases = dict(_RUNTIME_PARAM_ALIASES_BY_CHANNEL.get(normalized_channel) or {})

    def _pick_first(name: str) -> Any:
        for key in aliases.get(name, [name]):
            if ov.get(key) is not None:
                return ov.get(key)
        return None

    urls = [url for url in normalize_string_list(_pick_first("urls")) if url.startswith(("http://", "https://"))]
    limit = None
    raw_limit = _pick_first("limit")
    if raw_limit is not None:
        try:
            limit = max(1, int(raw_limit))
        except Exception:
            limit = None
    provider = str(_pick_first("provider") or "").strip().lower() or None
    language = str(_pick_first("language") or "").strip().lower() or None
    scope = str(_pick_first("scope") or "").strip() or None
    platforms = normalize_string_list(_pick_first("platforms")) or None
    source_mode = str(_pick_first("source_mode") or "").strip().lower() or None
    query_terms = []
    for key in aliases.get("query_terms", ["query_terms"]):
        query_terms = normalize_query_terms(ov.get(key))
        if query_terms:
            break
    return {
        "query_terms": query_terms,
        "urls": urls,
        "limit": limit,
        "provider": provider,
        "language": language,
        "scope": scope,
        "platforms": platforms,
        "source_mode": source_mode,
        "override_params": ov,
    }


def parse_source_library_runtime_params(override_params: dict[str, Any] | None) -> dict[str, Any]:
    return parse_business_runtime_params("source_library", override_params)
