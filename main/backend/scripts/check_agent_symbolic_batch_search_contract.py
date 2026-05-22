#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.agent_batch.agent_loop import run_agent_batch_nl_command_loop
from app.services.agent_batch.planner import build_agent_batch_task_manifest
from app.services.agent_batch.task_contract import (
    build_search_policy_contract,
    validate_retry_action_payload,
)

CONTRACT_VERSION = "agent-symbolic-batch-search.wave9.v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _submitter_factory() -> tuple[list[dict[str, Any]], Callable[[list[dict[str, Any]], str | None, str | None], dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def _submitter(tasks: list[dict[str, Any]], project_key: str | None, idempotency_key: str | None) -> dict[str, Any]:
        calls.append(
            {
                "tasks": [dict(task) for task in tasks],
                "project_key": project_key,
                "idempotency_key": idempotency_key,
            }
        )
        return {
            "job_id": f"abj-wave9-{len(calls)}",
            "accepted_count": len(tasks),
            "rejected_count": 0,
            "status": "ok",
        }

    return calls, _submitter


def _assert_required_keys(payload: dict[str, Any], keys: list[str], *, label: str) -> None:
    missing = [key for key in keys if key not in payload]
    _require(not missing, f"{label} missing required keys: {missing}")


def _check_agent_exposed_contract() -> dict[str, Any]:
    manifest = build_agent_batch_task_manifest()
    callable_tasks = {str(item.get("channel") or ""): item for item in list(manifest.get("callable_tasks") or [])}
    _require("search.market" in callable_tasks, "manifest does not expose search.market")
    _require("source_library" in callable_tasks, "manifest does not expose source_library")
    _require("query_terms" in list(callable_tasks["search.market"].get("required_keys") or []), "search.market lacks query_terms requirement")
    _require("item_key" in list(callable_tasks["source_library"].get("required_keys") or []), "source_library lacks item_key requirement")
    _require("source_mode" in list(callable_tasks["source_library"].get("optional_keys") or []), "source_library lacks source_mode optional field")

    policy = build_search_policy_contract()
    _assert_required_keys(policy, ["search_brief", "search_critic", "retry_action", "defaults", "event_names"], label="search policy")
    _require(policy["search_brief"]["artifact"] == "search_brief", "search brief schema is not exposed")
    _require(policy["search_critic"]["artifact"] == "search_critic", "search critic schema is not exposed")
    _require(policy["retry_action"]["fail_closed"] is True, "retry action schema must fail closed")
    _require(policy["defaults"]["retry_budget"] == 1, "retry budget must remain bounded to one retry")
    _require(policy["defaults"]["branching_default_enabled"] is False, "branching must remain default-off")
    for event_name in ("search_brief.created", "search_critic.scored", "search_retry.scheduled", "search_retry.skipped"):
        _require(event_name in list(policy.get("event_names") or []), f"missing event name {event_name}")

    normalized, reason_code, details = validate_retry_action_payload(
        {
            "action": "expand_query_terms",
            "reason": "need broader recall",
            "channel": "search.market",
            "rewrite": {"query_terms": ["ai terminal products"], "item_key": "ai_terminal.weekly"},
        }
    )
    _require(normalized is None, "search.market retry unexpectedly accepted item_key rewrite")
    _require(reason_code == "retry_action_rewrite_fields_unsupported", "unsupported rewrite did not fail closed")

    return {
        "manifest_version": manifest.get("manifest_version"),
        "callable_channels": sorted(callable_tasks),
        "policy_contract_version": policy.get("contract_version"),
        "retry_fail_closed_reason": reason_code,
        "retry_fail_closed_details": details,
    }


def _check_precision_retry_loop() -> dict[str, Any]:
    submit_calls, submitter = _submitter_factory()
    skill_text = (
        '{"intent":"market_news","strategy":"single_query","constraints":{"retrieval_mode":"web_only"},'
        '"tasks":[{"channel":"search.market",'
        '"query_terms":["chip pricing regulation"],"max_items":6,"provider":"auto","language":"en","days_back":120}]}'
    )
    with patch(
        "app.services.agent_batch.agent_loop.invoke_skill_safe",
        return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
    ):
        result = run_agent_batch_nl_command_loop(
            command="search chip pricing regulation web only last 120 days top 6",
            project_key="proj-wave9",
            idempotency_key="idem-wave9",
            dry_run=False,
            enable_bounded_retry=True,
            enable_limited_branching=False,
            parser_fallback=lambda _command: {},
            submitter=submitter,
            executor_snapshot=lambda: {"worker_online": True, "workers": ["celery@wave9"]},
        )

    plan = dict(result.get("plan") or {})
    brief = dict(plan.get("search_brief") or {})
    critic = dict(plan.get("search_critic") or {})
    retry = dict(plan.get("search_retry") or {})
    _assert_required_keys(brief, ["intent", "goal", "coverage_axes", "time_strategy", "search_strategies", "source_preferences", "stop_conditions"], label="search_brief")
    _assert_required_keys(critic, ["score", "coverage", "diagnosis", "next_action", "reason_codes"], label="search_critic")
    _require(bool(retry.get("scheduled")), "precision retry was not scheduled")
    _require(retry.get("used") == 1, "precision retry used count must be one")
    _require(retry.get("round") == 2, "precision retry must schedule round 2")
    _require(retry.get("action", {}).get("action") == "narrow_query_terms", "precision retry action mismatch")
    _require(len(submit_calls) == 2, "precision retry must call submitter exactly twice")
    _require(str(submit_calls[1]["idempotency_key"]).endswith(":retry:2"), "retry idempotency key is not round-scoped")
    first_query = list(submit_calls[0]["tasks"][0].get("query_terms") or [])
    retry_query = list(submit_calls[1]["tasks"][0].get("query_terms") or [])
    _require(first_query != retry_query, "precision retry did not rewrite query_terms")

    stage_names = [str(stage.get("name") or "") for stage in list(result.get("stages") or [])]
    for stage_name in ("search_brief", "search_critic", "search_retry"):
        _require(stage_name in stage_names, f"missing loop stage {stage_name}")

    return {
        "status": "passed",
        "brief_axes": brief.get("coverage_axes"),
        "critic_next_action": critic.get("next_action"),
        "critic_score": critic.get("score"),
        "retry_action": retry.get("action"),
        "submit_rounds": result.get("submit_rounds"),
        "first_query": first_query,
        "retry_query": retry_query,
    }


def _check_source_library_retry_loop() -> dict[str, Any]:
    submit_calls, submitter = _submitter_factory()
    skill_text = (
        '{"intent":"market_research_general","strategy":"single_query","constraints":{"retrieval_mode":"web_only"},'
        '"tasks":[{"channel":"search.market",'
        '"query_terms":["embodied ai robotics commercialization companies product latest news"],'
        '"max_items":3,"provider":"auto","language":"en","days_back":7}]}'
    )
    with patch(
        "app.services.agent_batch.agent_loop.invoke_skill_safe",
        return_value={"ok": True, "result": {"result": {"text": skill_text}}, "error": None},
    ), patch(
        "app.services.agent_batch.agent_loop._list_effective_source_items",
        return_value=[
            {
                "item_key": "robotics.market_watch",
                "name": "Robotics Market Watch",
                "description": "Commercial robotics products, companies, launches, and funding",
                "channel_key": "handler.cluster",
                "enabled": True,
                "tags": ["robotics", "commercialization", "product", "company"],
                "params": {
                    "site_entries": ["https://example.com/search?q={{q}}"],
                    "expected_entry_type": "search_template",
                },
            }
        ],
    ), patch(
        "app.services.agent_batch.agent_loop._build_channel_capability_index",
        return_value={
            "handler.cluster": {
                "channel_key": "handler.cluster",
                "provider": "handler",
                "credential_refs": [],
            }
        },
    ), patch(
        "app.services.agent_batch.agent_loop._is_item_credentials_ready",
        return_value=True,
    ):
        result = run_agent_batch_nl_command_loop(
            command="search embodied ai robotics commercialization companies product latest news last 7 days top 3",
            project_key="proj-wave9",
            idempotency_key="idem-wave9-source",
            dry_run=False,
            enable_bounded_retry=True,
            enable_limited_branching=False,
            parser_fallback=lambda _command: {},
            submitter=submitter,
            executor_snapshot=lambda: {"worker_online": True, "workers": ["celery@wave9"]},
        )

    retry = dict((result.get("plan") or {}).get("search_retry") or {})
    _require(bool(retry.get("scheduled")), "source-library retry was not scheduled")
    _require(retry.get("threshold_bypassed") is True, "source-gap retry must record threshold bypass")
    _require(retry.get("action", {}).get("action") == "attach_source_library", "source retry action mismatch")
    _require(len(submit_calls) == 2, "source retry must call submitter exactly twice")
    retried_tasks = list(submit_calls[1].get("tasks") or [])
    source_tasks = [task for task in retried_tasks if str(task.get("channel") or "") == "source_library"]
    _require(len(source_tasks) == 1, "source retry must append one source_library task")
    _require(source_tasks[0].get("item_key") == "robotics.market_watch", "source retry item_key mismatch")
    _require(source_tasks[0].get("max_items") == 3, "source retry must preserve max_items")

    return {
        "status": "passed",
        "critic_next_action": (result.get("plan") or {}).get("search_critic", {}).get("next_action"),
        "retry_action": retry.get("action"),
        "threshold_bypassed": retry.get("threshold_bypassed"),
        "retried_source_task": source_tasks[0],
    }


def build_contract() -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    evidence: dict[str, Any] = {}
    checks = [
        ("agent_exposed_task_contract", _check_agent_exposed_contract),
        ("precision_retry_loop", _check_precision_retry_loop),
        ("source_library_retry_loop", _check_source_library_retry_loop),
    ]
    for name, check in checks:
        try:
            evidence[name] = check()
        except Exception as exc:  # noqa: BLE001
            failures.append({"check": name, "error": str(exc)})

    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "deterministic_no_network_agent_batch_search_brief_critic_retry",
        "status": "passed" if not failures else "failed",
        "closure_claim": "minimal_runtime_loop_closed_not_global_topic",
        "evidence": evidence,
        "failures": failures,
        "remaining_blockers": [
            {
                "code": "live_provider_and_source_quality_not_replayed",
                "reason": "checker intentionally does not start external search providers or source-library network probes",
            },
            {
                "code": "benchmark_uplift_not_proven",
                "reason": "AT-SB-08 benchmark/go-no-go rubric is not replayed here",
            },
            {
                "code": "global_topic_closure_requires_index_audit",
                "reason": "worker evidence is topic-local only and does not edit shared CURRENT_DEV indexes",
            },
        ],
    }


def main() -> int:
    contract = build_contract()
    print(json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
