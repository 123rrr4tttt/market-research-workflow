from __future__ import annotations

import json
import re
from typing import Any, Callable
from uuid import uuid4

from .planner import (
    AGENT_BATCH_PLANNER_CONTRACT_VERSION,
    AGENT_BATCH_PLANNER_PROMPT_ID,
    REASON_SKILL_PLAN_EMPTY_TASKS,
    REASON_SKILL_PLAN_INVALID_JSON,
    build_agent_batch_task_manifest,
    validate_skill_planner_contract,
)
from .task_contract import (
    get_search_policy_defaults,
    is_agent_batch_task_executable,
    normalize_agent_batch_task,
    validate_retry_action_payload,
)
from ..skill_runtime import invoke_skill_safe

REASON_SKILL_PLANNER_INVOKE_FAILED = "skill_planner_invoke_failed"
_AUTONOMOUS_SOURCE_MAX_TASKS = 2
_AUTONOMOUS_SOURCE_SCAN_LIMIT = 200
_RETRIEVAL_MODE_HYBRID = "hybrid"
_RETRIEVAL_MODE_SOURCE_ONLY = "source_only"
_RETRIEVAL_MODE_WEB_ONLY = "web_only"

StageRecord = dict[str, Any]


def run_agent_batch_nl_command_loop(
    *,
    command: str,
    project_key: str | None,
    idempotency_key: str | None,
    dry_run: bool,
    enable_bounded_retry: bool,
    enable_limited_branching: bool,
    parser_fallback: Callable[[str], dict[str, Any]],
    submitter: Callable[[list[dict[str, Any]], str | None, str | None], dict[str, Any]],
    executor_snapshot: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Run nl-command in loop-first flow: plan -> dispatch -> observe -> adjust -> report."""
    loop_id = f"abl-{uuid4().hex[:16]}"
    stages: list[StageRecord] = []
    degradation_flags: list[str] = []

    plan_payload, plan_meta = _plan_skill_first(command=command, parser_fallback=parser_fallback, loop_id=loop_id)
    stages.append(
        {
            "name": "plan",
            "status": "degraded" if plan_meta["fallback_used"] else "ok",
            "mode": "skill_first",
            "fallback_used": plan_meta["fallback_used"],
            "planner": plan_meta["planner"],
        }
    )
    if plan_meta["fallback_used"]:
        degradation_flags.append("plan.skill_first.degraded")
    if plan_meta.get("skill_error"):
        degradation_flags.append("plan.skill_error")
        degradation_flags.append("skill_planner_failed")

    tasks = _normalize_tasks(plan_payload.get("tasks") or [], command=command)
    retrieval_mode = _resolve_retrieval_mode(command=command, plan_payload=plan_payload)
    tasks, autonomy_meta = _augment_tasks_with_source_library(
        tasks=tasks,
        project_key=project_key,
        retrieval_mode=retrieval_mode,
    )
    pre_branch_search_brief = _build_search_brief(
        command=command,
        intent=str(plan_payload.get("intent") or ""),
        tasks=tasks,
        retrieval_mode=retrieval_mode,
        autonomy_meta=autonomy_meta,
    )
    tasks, branching = _expand_tasks_with_limited_branching(
        tasks=tasks,
        search_brief=pre_branch_search_brief,
        retrieval_mode=retrieval_mode,
        enable_limited_branching=enable_limited_branching,
        command=command,
    )
    plan_payload["tasks"] = list(tasks)
    plan_payload["branching"] = branching
    stages.append(
        {
            "name": "branching",
            "status": "ok" if bool(branching.get("enabled")) else "skipped",
            "enabled": bool(branching.get("enabled")),
            "branch_count": int(branching.get("branch_count") or 1),
            "reason": branching.get("reason"),
        }
    )
    search_brief = _build_search_brief(
        command=command,
        intent=str(plan_payload.get("intent") or ""),
        tasks=tasks,
        retrieval_mode=retrieval_mode,
        autonomy_meta=autonomy_meta,
    )
    plan_payload["search_brief"] = search_brief
    stages.append(
        {
            "name": "search_brief",
            "status": "ok",
            "strategy_count": len(list(search_brief.get("search_strategies") or [])),
            "attach_source_library": bool(((search_brief.get("source_preferences") or {}).get("attach_source_library"))),
        }
    )
    if autonomy_meta.get("enabled"):
        stages.append(
            {
                "name": "autonomous_mix",
                "status": "ok",
                "retrieval_mode": retrieval_mode,
                "source_library_item_keys": list(autonomy_meta.get("item_keys") or []),
            }
        )
    else:
        stages.append(
            {
                "name": "autonomous_mix",
                "status": "skipped",
                "retrieval_mode": retrieval_mode,
                "reason": str(autonomy_meta.get("reason") or "not_applicable"),
            }
        )
    if not tasks:
        raise ValueError("planner produced no executable tasks")

    submit_data: dict[str, Any] | None = None
    submit_rounds: list[dict[str, Any]] = []
    if dry_run:
        stages.append({"name": "dispatch", "status": "skipped", "reason": "dry_run"})
    else:
        submit_data = submitter(tasks, project_key, idempotency_key)
        accepted = int((submit_data or {}).get("accepted_count") or 0)
        rejected = int((submit_data or {}).get("rejected_count") or 0)
        dispatch_status = "ok" if accepted > 0 and rejected == 0 else "degraded"
        stages.append(
            {
                "name": "dispatch",
                "status": dispatch_status,
                "accepted_count": accepted,
                "rejected_count": rejected,
            }
        )
        if rejected > 0:
            degradation_flags.append("dispatch.partial_rejection")
        submit_rounds.append(_build_submit_round_record(round_index=1, submit_data=submit_data, task_count=len(tasks)))

    executor = executor_snapshot()
    observe_snapshot = {
        "executor": executor,
        "submit": {
            "job_id": (submit_data or {}).get("job_id"),
            "accepted_count": int((submit_data or {}).get("accepted_count") or 0),
            "rejected_count": int((submit_data or {}).get("rejected_count") or 0),
            "status": (submit_data or {}).get("status"),
        }
        if submit_data
        else None,
    }
    stages.append(
        {
            "name": "observe_snapshot",
            "status": "ok",
            "executor_healthy": _is_executor_healthy(executor),
        }
    )

    search_critic = _build_search_critic(
        search_brief=search_brief,
        tasks=tasks,
        dry_run=dry_run,
        submit_data=submit_data,
        executor=executor,
    )
    plan_payload["search_critic"] = search_critic
    stages.append(
        {
            "name": "search_critic",
            "status": "ok" if str(search_critic.get("next_action") or "") == "stop" else "degraded",
            "score": search_critic.get("score"),
            "next_action": search_critic.get("next_action"),
        }
    )
    search_retry, retry_submit_data, retried_tasks = _build_search_retry_state(
        command=command,
        tasks=tasks,
        search_brief=search_brief,
        search_critic=search_critic,
        dry_run=dry_run,
        enable_bounded_retry=enable_bounded_retry,
        submitter=submitter,
        project_key=project_key,
        idempotency_key=idempotency_key,
        loop_id=loop_id,
    )
    plan_payload["search_retry"] = search_retry
    stages.append(
        {
            "name": "search_retry",
            "status": "ok" if bool(search_retry.get("scheduled")) else "skipped",
            "scheduled": bool(search_retry.get("scheduled")),
            "reason": search_retry.get("reason"),
            "skip_reason": search_retry.get("skip_reason"),
        }
    )
    if retry_submit_data is not None:
        submit_rounds.append(_build_submit_round_record(round_index=2, submit_data=retry_submit_data, task_count=len(retried_tasks)))
        submit_data = retry_submit_data
        degradation_flags.append("search_retry.scheduled")

    adjustment = _build_strategy_adjustment(
        dry_run=dry_run,
        submit_data=submit_data,
        degradation_flags=degradation_flags,
        plan_meta=plan_meta,
    )
    stages.append(
        {
            "name": "strategy_adjustment",
            "status": "ok" if not adjustment.get("actions") else "degraded",
            "actions": list(adjustment.get("actions") or []),
        }
    )
    if adjustment.get("actions"):
        degradation_flags.append("strategy_adjustment.required")

    parsed = _build_backward_compatible_parsed(plan_payload=plan_payload, tasks=tasks, command=command)
    stages.append(
        {
            "name": "report",
            "status": "ok",
            "task_count": len(tasks),
            "degradation_count": len(degradation_flags),
        }
    )

    plan_payload["loop"] = {
        "iteration": 1,
        "planner": "rule" if plan_meta["fallback_used"] else "skill",
        "planner_path": "rule_planner_fallback" if plan_meta["fallback_used"] else "skill_planner",
        "fallback_used": bool(plan_meta["fallback_used"]),
        "degradation_flags": sorted(set(degradation_flags)),
        "fallback_reason_code": plan_meta.get("reason_code"),
        "fallback_reason": plan_meta.get("skill_error"),
    }
    plan_payload["strategy_adjustments"] = adjustment

    return {
        "command": command,
        "parsed": parsed,
        "plan": plan_payload,
        "submit": submit_data,
        "executor": executor,
        "dry_run": bool(dry_run),
        "loop_id": loop_id,
        "stages": stages,
        "degradation_flags": sorted(set(degradation_flags)),
        "observe_snapshot": observe_snapshot,
        "strategy_adjustment": adjustment,
        "submit_rounds": submit_rounds,
    }


def _augment_tasks_with_source_library(
    *,
    tasks: list[dict[str, Any]],
    project_key: str | None,
    retrieval_mode: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not tasks and retrieval_mode != _RETRIEVAL_MODE_SOURCE_ONLY:
        return tasks, {"enabled": False, "reason": "empty_tasks"}
    if retrieval_mode == _RETRIEVAL_MODE_WEB_ONLY:
        return tasks, {"enabled": False, "reason": "web_only_mode"}

    if any(str(task.get("channel") or "").strip().lower() == "source_library" for task in tasks) and retrieval_mode != _RETRIEVAL_MODE_SOURCE_ONLY:
        return tasks, {"enabled": False, "reason": "source_library_already_planned"}

    item_keys = _discover_source_library_item_keys(project_key=project_key, limit=_AUTONOMOUS_SOURCE_MAX_TASKS)
    if not item_keys:
        return tasks, {"enabled": False, "reason": "no_source_library_match"}

    appended: list[dict[str, Any]] = []
    for idx, item_key in enumerate(item_keys, start=1):
        appended.append(
            {
                "task_id": f"source_{idx}",
                "channel": "source_library",
                "query_terms": [],
                "max_items": 1,
                "provider": "auto",
                "language": "zh",
                "days_back": None,
                "item_key": item_key,
                "override_params": {
                    "autonomous_strategy": "mode_driven_source_library",
                    "autonomous_reason": "fixed_source_mode",
                },
            }
        )
    if retrieval_mode == _RETRIEVAL_MODE_SOURCE_ONLY:
        preserved = [task for task in tasks if str(task.get("channel") or "").strip().lower() == "source_library"]
        merged = preserved + appended
    else:
        merged = tasks + appended
    return merged, {"enabled": True, "item_keys": item_keys}


def _resolve_retrieval_mode(*, command: str, plan_payload: dict[str, Any]) -> str:
    constraints = dict(plan_payload.get("constraints") or {})
    forced = str(constraints.get("retrieval_mode") or "").strip().lower()
    if forced in {_RETRIEVAL_MODE_HYBRID, _RETRIEVAL_MODE_SOURCE_ONLY, _RETRIEVAL_MODE_WEB_ONLY}:
        return forced

    text = str(command or "").lower()
    if any(token in text for token in ("仅来源库", "只用来源库", "source only", "source_library_only", "fixed source only")):
        return _RETRIEVAL_MODE_SOURCE_ONLY
    if any(token in text for token in ("仅搜索", "只搜全网", "web only", "search only", "internet only")):
        return _RETRIEVAL_MODE_WEB_ONLY
    return _RETRIEVAL_MODE_HYBRID


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
    for index, task in enumerate(tasks, start=1):
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


def _build_search_critic(
    *,
    search_brief: dict[str, Any],
    tasks: list[dict[str, Any]],
    dry_run: bool,
    submit_data: dict[str, Any] | None,
    executor: dict[str, Any],
) -> dict[str, Any]:
    channels = {str(task.get("channel") or "").strip().lower() for task in tasks if str(task.get("channel") or "").strip()}
    search_strategies = list(search_brief.get("search_strategies") or [])
    coverage_axes = list(search_brief.get("coverage_axes") or [])
    source_preferences = dict(search_brief.get("source_preferences") or {})
    attach_source_library = bool(source_preferences.get("attach_source_library"))
    days_back = (dict(search_brief.get("time_strategy") or {})).get("days_back")
    strategy_count = len(search_strategies)
    rejected_count = int((submit_data or {}).get("rejected_count") or 0)

    entity_coverage = min(1.0, 0.35 + 0.12 * min(strategy_count, 2) + 0.18 * min(len(coverage_axes), 3))
    source_diversity = min(1.0, 0.2 + (0.35 if "search.market" in channels else 0.0) + (0.35 if "source_library" in channels else 0.0))
    freshness_fit = 0.8 if isinstance(days_back, int) and days_back <= 30 else 0.62 if isinstance(days_back, int) and days_back > 30 else 0.7
    goal_alignment = min(1.0, 0.45 + 0.12 * min(len(coverage_axes), 3) + (0.15 if tasks else 0.0))
    novelty_gain = min(1.0, 0.25 + (0.2 if strategy_count > 1 else 0.0) + (0.2 if attach_source_library else 0.0) + (0.1 if not dry_run else 0.0))

    coverage = {
        "entity_coverage": round(entity_coverage, 2),
        "source_diversity": round(source_diversity, 2),
        "freshness_fit": round(freshness_fit, 2),
        "goal_alignment": round(goal_alignment, 2),
        "novelty_gain": round(novelty_gain, 2),
    }
    score = round(sum(coverage.values()) / max(1, len(coverage)), 2)

    diagnosis: list[str] = []
    reason_codes: list[str] = []
    if rejected_count > 0:
        diagnosis.append("dispatch observed partial rejection and would benefit from a narrower retry payload")
        reason_codes.append("dispatch_partial_rejection")
    if not attach_source_library and any(axis in coverage_axes for axis in ("products", "companies", "recent_movement")):
        diagnosis.append("source-backed coverage is missing for this research brief")
        reason_codes.append("source_backing_missing")
    if strategy_count <= 1 and len(coverage_axes) > 1 and not attach_source_library:
        diagnosis.append("query strategy is still narrow and may benefit from a precision follow-up")
        reason_codes.append("precision_follow_up_recommended")
    if isinstance(days_back, int) and days_back > 60:
        diagnosis.append("time window may be too wide for a focused first-round scan")
        reason_codes.append("time_window_too_wide")
    if not _is_executor_healthy(executor):
        diagnosis.append("executor health snapshot is degraded; observations may be incomplete")
        reason_codes.append("executor_degraded")
    if not diagnosis:
        diagnosis.append("current search plan appears sufficiently aligned for an initial execution round")
        reason_codes.append("coverage_sufficient")

    if rejected_count > 0:
        next_action = "retry_with_precision_query"
    elif attach_source_library and strategy_count >= 1 and (not isinstance(days_back, int) or days_back <= 60):
        next_action = "stop"
    elif not attach_source_library and any(axis in coverage_axes for axis in ("products", "companies", "recent_movement")):
        next_action = "retry_with_source_library"
    elif strategy_count <= 1 and len(coverage_axes) > 1:
        next_action = "retry_with_precision_query"
    elif isinstance(days_back, int) and days_back > 60:
        next_action = "retry_with_time_shift"
    else:
        next_action = "stop"

    critic: dict[str, Any] = {
        "score": score,
        "coverage": coverage,
        "diagnosis": diagnosis,
        "next_action": next_action,
        "reason_codes": reason_codes,
    }
    candidate_items = list(source_preferences.get("candidate_items") or [])
    if next_action == "retry_with_source_library" and candidate_items:
        critic["rewrite"] = {"source_library": candidate_items}
    elif next_action == "retry_with_time_shift":
        critic["rewrite"] = {"days_back": 30}
    return critic


def _build_search_retry_state(
    *,
    command: str,
    tasks: list[dict[str, Any]],
    search_brief: dict[str, Any],
    search_critic: dict[str, Any],
    dry_run: bool,
    enable_bounded_retry: bool,
    submitter: Callable[[list[dict[str, Any]], str | None, str | None], dict[str, Any]],
    project_key: str | None,
    idempotency_key: str | None,
    loop_id: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    defaults = get_search_policy_defaults()
    retry_budget = max(0, int(defaults.get("retry_budget") or 0))
    max_retry_rounds = max(0, int(defaults.get("max_retry_rounds") or 0))
    retry_score_threshold = float(defaults.get("retry_score_threshold") or 0.72)
    score = float(search_critic.get("score") or 0.0)
    next_action = str(search_critic.get("next_action") or "stop").strip().lower()
    state: dict[str, Any] = {
        "enabled": bool(enable_bounded_retry),
        "scheduled": False,
        "budget": retry_budget,
        "used": 0,
        "max_retry_rounds": max_retry_rounds,
        "score_threshold": retry_score_threshold,
        "score": score,
        "reason_codes": list(search_critic.get("reason_codes") or []),
        "next_action": next_action,
    }
    if not enable_bounded_retry:
        state["skip_reason"] = "bounded_retry_disabled"
        return state, None, list(tasks)
    if dry_run:
        state["skip_reason"] = "dry_run"
        return state, None, list(tasks)
    if retry_budget <= 0 or max_retry_rounds <= 0:
        state["skip_reason"] = "retry_budget_exhausted"
        return state, None, list(tasks)
    if next_action == "stop":
        state["skip_reason"] = "critic_stop"
        return state, None, list(tasks)
    if score >= retry_score_threshold:
        state["skip_reason"] = "score_above_threshold"
        return state, None, list(tasks)

    retry_payload = _build_retry_action_from_critic(
        command=command,
        tasks=tasks,
        search_brief=search_brief,
        search_critic=search_critic,
        project_key=project_key,
    )
    if not retry_payload:
        state["skip_reason"] = "retry_action_unavailable"
        return state, None, list(tasks)

    normalized_retry, reason_code, details = validate_retry_action_payload(
        retry_payload,
        default_channel=str(retry_payload.get("channel") or ""),
    )
    if normalized_retry is None:
        state["skip_reason"] = reason_code or "retry_action_invalid"
        state["details"] = details
        return state, None, list(tasks)

    retried_tasks = _apply_retry_action(tasks=tasks, retry_action=normalized_retry, command=command)
    if retried_tasks == list(tasks):
        state["skip_reason"] = "retry_action_no_effect"
        state["action"] = normalized_retry
        return state, None, list(tasks)

    retry_submit = submitter(
        retried_tasks,
        project_key,
        _build_retry_idempotency_key(idempotency_key=idempotency_key, loop_id=loop_id, round_index=2),
    )
    state.update(
        {
            "scheduled": True,
            "used": 1,
            "round": 2,
            "reason": str(normalized_retry.get("reason") or ""),
            "action": normalized_retry,
            "submit": retry_submit,
            "task_count": len(retried_tasks),
        }
    )
    return state, retry_submit, retried_tasks


def _build_retry_action_from_critic(
    *,
    command: str,
    tasks: list[dict[str, Any]],
    search_brief: dict[str, Any],
    search_critic: dict[str, Any],
    project_key: str | None,
) -> dict[str, Any] | None:
    next_action = str(search_critic.get("next_action") or "").strip().lower()
    primary_search_task = next(
        (dict(task) for task in tasks if str(task.get("channel") or "").strip().lower() == "search.market"),
        dict(tasks[0]) if tasks else {},
    )
    primary_channel = str(primary_search_task.get("channel") or "search.market").strip().lower()
    reason_codes = list(search_critic.get("reason_codes") or [])
    reason = ", ".join(reason_codes) or "critic_requested_retry"
    rewrite = dict(search_critic.get("rewrite") or {})

    if next_action == "retry_with_precision_query":
        query_terms = list(rewrite.get("query_terms") or _build_precision_retry_query_terms(command=command, tasks=tasks, search_brief=search_brief))
        if not query_terms:
            return None
        return {
            "action": "narrow_query_terms",
            "reason": reason,
            "channel": primary_channel,
            "rewrite": {
                "query_terms": query_terms,
                "max_items": primary_search_task.get("max_items") or 20,
            },
        }
    if next_action == "retry_with_broader_query":
        query_terms = list(rewrite.get("query_terms") or _build_precision_retry_query_terms(command=command, tasks=tasks, search_brief=search_brief))
        if not query_terms:
            return None
        return {
            "action": "expand_query_terms",
            "reason": reason,
            "channel": primary_channel,
            "rewrite": {
                "query_terms": query_terms,
                "max_items": primary_search_task.get("max_items") or 20,
            },
        }
    if next_action == "retry_with_time_shift":
        days_back = rewrite.get("days_back") or 30
        return {
            "action": "shift_time_window",
            "reason": reason,
            "channel": primary_channel,
            "rewrite": {"days_back": days_back},
        }
    if next_action == "retry_with_source_library":
        candidate_items = list(rewrite.get("source_library") or ((search_brief.get("source_preferences") or {}).get("candidate_items") or []))
        if not candidate_items:
            candidate_items = _discover_source_library_item_keys(project_key=project_key, limit=1)
        if not candidate_items:
            return None
        source_query_terms = list(primary_search_task.get("query_terms") or [])
        return {
            "action": "attach_source_library",
            "reason": reason,
            "channel": "source_library",
            "rewrite": {
                "item_key": str(candidate_items[0]),
                "query_terms": source_query_terms,
                "provider": "auto",
                "max_items": 1,
                "source_mode": "protocol_search",
            },
            "target_items": candidate_items,
        }
    return {
        "action": "stop",
        "reason": reason,
    }


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
        normalized.append(
            normalize_agent_batch_task(
                {
                    "channel": "source_library",
                    "item_key": item_key,
                    "query_terms": list(rewrite.get("query_terms") or []),
                    "max_items": rewrite.get("max_items") or 1,
                    "provider": rewrite.get("provider") or "auto",
                    "language": rewrite.get("language"),
                    "scope": rewrite.get("scope"),
                    "platforms": list(rewrite.get("platforms") or []),
                    "source_mode": rewrite.get("source_mode") or "protocol_search",
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


def _build_retry_idempotency_key(*, idempotency_key: str | None, loop_id: str, round_index: int) -> str:
    base = str(idempotency_key or "").strip() or loop_id
    return f"{base}:retry:{round_index}"


def _build_submit_round_record(*, round_index: int, submit_data: dict[str, Any] | None, task_count: int) -> dict[str, Any]:
    payload = dict(submit_data or {})
    return {
        "round": round_index,
        "job_id": payload.get("job_id"),
        "accepted_count": int(payload.get("accepted_count") or 0),
        "rejected_count": int(payload.get("rejected_count") or 0),
        "task_count": task_count,
        "status": payload.get("status"),
    }


def _discover_source_library_item_keys(*, project_key: str | None, limit: int) -> list[str]:
    try:
        items = _list_effective_source_items(project_key=project_key)
    except Exception:
        return []
    if not items:
        return []

    channel_capability = _build_channel_capability_index(project_key=project_key)
    category_scored: dict[str, list[tuple[int, str]]] = {
        "fixed_channel_search": [],
        "fixed_source_site_search": [],
        "fixed_api_info": [],
        "other": [],
    }
    for row in items[:_AUTONOMOUS_SOURCE_SCAN_LIMIT]:
        if not bool(row.get("enabled", True)):
            continue
        item_key = str(row.get("item_key") or "").strip()
        if not item_key:
            continue
        category = _classify_source_library_item(row=row, channel_capability=channel_capability)
        # fixed_api_info tasks require credentials; skip missing-credential entries for autonomous selection.
        if category == "fixed_api_info" and not _is_item_credentials_ready(
            row=row,
            channel_capability=channel_capability,
            project_key=project_key,
        ):
            continue
        category_scored.setdefault(category, []).append((_source_item_priority(row), item_key))

    category_order = ["fixed_source_site_search", "fixed_channel_search", "fixed_api_info", "other"]
    out: list[str] = []
    per_category_cursor: dict[str, int] = {}
    sorted_buckets: dict[str, list[tuple[int, str]]] = {}
    for category in category_order:
        bucket = list(category_scored.get(category) or [])
        bucket.sort(key=lambda x: (-x[0], x[1]))
        sorted_buckets[category] = bucket
        per_category_cursor[category] = 0

    hard_limit = max(1, int(limit or _AUTONOMOUS_SOURCE_MAX_TASKS))
    # Round-robin across categories to keep "source_library = multi-capability set" semantics.
    while len(out) < hard_limit:
        progressed = False
        for category in category_order:
            bucket = sorted_buckets.get(category) or []
            cursor = int(per_category_cursor.get(category) or 0)
            while cursor < len(bucket):
                _, key = bucket[cursor]
                cursor += 1
                per_category_cursor[category] = cursor
                if key in out:
                    continue
                out.append(key)
                progressed = True
                break
            if len(out) >= hard_limit:
                break
        if not progressed:
            break
    return out


def _list_effective_source_items(*, project_key: str | None) -> list[dict[str, Any]]:
    from app.services.source_library.resolver import list_effective_items

    return list_effective_items(scope="effective", project_key=project_key)


def _source_item_priority(row: dict[str, Any]) -> int:
    key = str(row.get("item_key") or "").lower()
    name = str(row.get("name") or "").lower()
    channel_key = str(row.get("channel_key") or "").lower()
    params = dict(row.get("params") or {})
    text = f"{key} {name}"
    score = 1
    site_entries = params.get("site_entries") or params.get("site_entry_urls")
    has_site_entries = isinstance(site_entries, list) and any(str(x or "").strip() for x in site_entries)
    if has_site_entries:
        score += 8
    expected_entry_type = str(params.get("expected_entry_type") or "").strip().lower()
    if expected_entry_type in {"search_template", "rss", "sitemap", "domain_root"}:
        score += 4
    if channel_key == "handler.cluster":
        score += 6
    if channel_key.startswith("generic_web."):
        score += 3
    if "baseline" in text:
        score += 6
    if "default" in text:
        score += 5
    if "general" in text:
        score += 4
    if "high_value" in text or "root_site_search" in text:
        score += 3
    if key.startswith("handler.cluster"):
        score += 2
    if "crawler." in key:
        score -= 2
    return score


def _is_source_site_search_item(row: dict[str, Any]) -> bool:
    """Treat source-library item as source-constrained keyword search when it binds site entries."""
    params = dict(row.get("params") or {})
    site_entries = params.get("site_entries") or params.get("site_entry_urls")
    has_site_entries = isinstance(site_entries, list) and any(str(x or "").strip() for x in site_entries)
    if has_site_entries:
        return True

    channel_key = str(row.get("channel_key") or "").strip().lower()
    if channel_key in {"handler.cluster", "generic_web.rss", "generic_web.sitemap", "generic_web.search_template"}:
        return True
    return False


def _build_channel_capability_index(*, project_key: str | None) -> dict[str, dict[str, Any]]:
    try:
        from app.services.source_library.resolver import list_effective_channels

        rows = list_effective_channels(scope="effective", project_key=project_key)
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        channel_key = str((row or {}).get("channel_key") or "").strip()
        if channel_key:
            out[channel_key] = dict(row or {})
    return out


def _classify_source_library_item(*, row: dict[str, Any], channel_capability: dict[str, dict[str, Any]]) -> str:
    if _is_source_site_search_item(row):
        return "fixed_source_site_search"
    channel_key = str(row.get("channel_key") or "").strip()
    channel = dict(channel_capability.get(channel_key) or {})
    provider = str(channel.get("provider") or "").strip().lower()
    credential_refs = channel.get("credential_refs")
    if isinstance(credential_refs, list) and credential_refs:
        return "fixed_api_info"
    if provider in {"policy", "official_access", "api"}:
        return "fixed_api_info"
    if provider in {"market", "reddit", "google_news", "url_pool"}:
        return "fixed_channel_search"
    return "other"


def _is_item_credentials_ready(
    *,
    row: dict[str, Any],
    channel_capability: dict[str, dict[str, Any]],
    project_key: str | None,
) -> bool:
    channel_key = str(row.get("channel_key") or "").strip()
    channel = dict(channel_capability.get(channel_key) or {})
    refs = channel.get("credential_refs")
    if not isinstance(refs, list) or not refs:
        return True
    try:
        from app.services.source_library.runner import resolve_credential
    except Exception:
        return False
    for cred in refs:
        if not isinstance(cred, str) or not cred.strip():
            continue
        if resolve_credential(cred.strip(), project_key) is None:
            return False
    return True


def _plan_skill_first(*, command: str, parser_fallback: Callable[[str], dict[str, Any]], loop_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    fallback_plan = parser_fallback(command)

    prompt = _build_planner_prompt(command)
    invoked = invoke_skill_safe(
        skill_id="workflow.llm_call",
        payload={"prompt": prompt, "temperature": 0.0},
        context={
            "actor_role": "orchestration_runtime",
            "permissions": ["workflow.llm_call"],
            "trace_id": f"{loop_id}.plan.skill_first",
            "consumer": "agent_batch.nl_command.loop",
        },
    )
    if not invoked.get("ok"):
        return fallback_plan, {
            "planner": "rule",
            "fallback_used": True,
            "skill_error": invoked.get("error") or "skill_invoke_failed",
            "reason_code": REASON_SKILL_PLANNER_INVOKE_FAILED,
        }

    result = invoked.get("result")
    text = ""
    if isinstance(result, dict):
        raw = result.get("result")
        if isinstance(raw, dict):
            text = str(raw.get("text") or "")
        elif isinstance(raw, str):
            text = raw

    candidate = _extract_plan_from_llm_text(text)
    if candidate is None:
        return fallback_plan, {
            "planner": "rule",
            "fallback_used": True,
            "skill_error": REASON_SKILL_PLAN_INVALID_JSON,
            "reason_code": REASON_SKILL_PLAN_INVALID_JSON,
        }

    validated, reason_code = validate_skill_planner_contract(candidate)
    if validated is None:
        return fallback_plan, {
            "planner": "rule",
            "fallback_used": True,
            "skill_error": reason_code,
            "reason_code": reason_code,
        }

    normalized = _normalize_plan(validated, fallback=fallback_plan, command=command)
    if not normalized.get("tasks"):
        return fallback_plan, {
            "planner": "rule",
            "fallback_used": True,
            "skill_error": REASON_SKILL_PLAN_EMPTY_TASKS,
            "reason_code": REASON_SKILL_PLAN_EMPTY_TASKS,
        }
    normalized["contract_version"] = AGENT_BATCH_PLANNER_CONTRACT_VERSION
    normalized["prompt_id"] = AGENT_BATCH_PLANNER_PROMPT_ID

    return normalized, {
        "planner": "skill",
        "fallback_used": False,
        "skill_error": None,
        "reason_code": None,
    }


def _build_planner_prompt(command: str) -> str:
    manifest = json.dumps(build_agent_batch_task_manifest(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (
        "You are a deterministic planning assistant for agent-batch nl-command. "
        f"Use prompt_id={AGENT_BATCH_PLANNER_PROMPT_ID} and contract_version={AGENT_BATCH_PLANNER_CONTRACT_VERSION}. "
        "Given a natural-language command, output JSON only with keys: intent, strategy, constraints, tasks. "
        "Callable tasks are strictly defined by TASK_MANIFEST below; never invent channels or schema keys outside it. "
        "For each task, satisfy the required_keys declared in TASK_MANIFEST. "
        "Set constraints.retrieval_mode only from: hybrid/source_only/web_only when user intent is explicit. "
        "Use provider auto when uncertain. "
        "Do not include markdown fences. "
        f"\nTASK_MANIFEST: {manifest}"
        f"\ncommand: {command}"
    )


def _extract_plan_from_llm_text(text: str) -> dict[str, Any] | None:
    content = str(text or "").strip()
    if not content:
        return None

    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        content = fence.group(1).strip()

    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(content[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _normalize_plan(candidate: dict[str, Any], *, fallback: dict[str, Any], command: str) -> dict[str, Any]:
    intent = str(candidate.get("intent") or fallback.get("intent") or "market_research_general")
    strategy = str(candidate.get("strategy") or fallback.get("strategy") or "single_query")
    constraints = dict(fallback.get("constraints") or {})
    constraints.update(dict(candidate.get("constraints") or {}))

    tasks = _normalize_tasks(candidate.get("tasks") or [], command=command)
    if not tasks:
        tasks = _normalize_tasks(fallback.get("tasks") or [], command=command)

    return {
        "intent": intent,
        "strategy": strategy,
        "constraints": constraints,
        "tasks": tasks,
    }


def _normalize_tasks(raw_tasks: list[dict[str, Any]], *, command: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    language = _detect_language(command)

    for idx, task in enumerate(raw_tasks, start=1):
        if not isinstance(task, dict):
            continue
        normalized = normalize_agent_batch_task(task, idx=idx, default_language=language)
        if normalized:
            out.append(normalized)

    return [task for task in out if is_agent_batch_task_executable(task)]


def _detect_language(command: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", str(command or "")) else "en"


def _is_executor_healthy(executor: dict[str, Any]) -> bool:
    text = str(executor or "").lower()
    if not text:
        return False
    return "error" not in text and "fail" not in text and "down" not in text


def _build_strategy_adjustment(
    *,
    dry_run: bool,
    submit_data: dict[str, Any] | None,
    degradation_flags: list[str],
    plan_meta: dict[str, Any],
) -> dict[str, Any]:
    actions: list[str] = []
    if plan_meta.get("fallback_used"):
        actions.append("review_skill_planner_prompt_or_permission")
    if dry_run:
        actions.append("execute_without_dry_run")
    if submit_data is not None:
        accepted = int(submit_data.get("accepted_count") or 0)
        rejected = int(submit_data.get("rejected_count") or 0)
        if accepted == 0:
            actions.append("revise_plan_constraints_then_retry")
        elif rejected > 0:
            actions.append("retry_rejected_items_with_adjusted_params")
    if degradation_flags:
        actions.append("inspect_loop_degradation_flags")

    return {
        "actions": actions,
        "planner": plan_meta.get("planner"),
        "fallback_used": bool(plan_meta.get("fallback_used")),
        "parallelism": 1 if dry_run else 2,
        "provider_policy": "stable" if not plan_meta.get("fallback_used") else "conservative",
        "retry_backoff_seconds": 2 if not plan_meta.get("fallback_used") else 5,
    }


def _build_backward_compatible_parsed(
    *,
    plan_payload: dict[str, Any],
    tasks: list[dict[str, Any]],
    command: str,
) -> dict[str, Any]:
    first = tasks[0]
    return {
        "channel": str(first.get("channel") or "search.market"),
        "query_terms": list(first.get("query_terms") or []),
        "max_items": int(first.get("max_items") or 20),
        "provider": str(first.get("provider") or "auto"),
        "language": str(first.get("language") or _detect_language(command)),
        "days_back": first.get("days_back"),
        "intent": str(plan_payload.get("intent") or ""),
        "strategy": str(plan_payload.get("strategy") or ""),
        "task_count": len(tasks),
    }
