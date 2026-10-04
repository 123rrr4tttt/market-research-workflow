"""C4.2 typed retry reducer: budget, order, attempt intent, source-mode gate."""

from __future__ import annotations

import dataclasses

import pytest

from app.successor_runtime.capabilities.agent_batch_c4 import (
    AgentBatchTask,
    RetryAction,
    RetryBudget,
    reduce_retry_action,
    validate_retry_action,
)

from .p3_c4_fixture import retry_payload


def _narrow_payload(score: float = 0.5):
    return retry_payload(
        action=RetryAction(
            action="narrow_query_terms",
            reason="critic_requested_retry",
            channel="search.market",
            rewrite={"query_terms": ("机器人 产品",)},
        ),
        next_action="retry_with_precision_query",
        reason_codes=("precision_needed",),
        score=score,
    )


def test_scheduled_retry_preserves_order_and_emits_fresh_attempt_intent() -> None:
    transition = reduce_retry_action(retry_payload())
    assert transition.kind == "RETRY_SCHEDULED"
    assert transition.attempt_intent is not None
    intent = transition.attempt_intent
    assert intent.prior_attempt_ref == "attempt:round-1"
    assert intent.round_index == 1
    assert intent.attempt_id == "attempt:p3-c4-demo:attempt:round-1:retry:1"
    assert intent.idempotency_key == "attempt:round-1:retry:1"
    assert intent.attempt_intent_digest
    assert transition.tasks[-1].channel == "source_library"
    assert transition.tasks[-1].item_key == "handler.cluster.news"
    assert transition.tasks[:-1] == transition.tasks[:-1]
    assert len(transition.tasks) == 2
    assert transition.observations["budget_remaining"] == 0
    assert transition.observations["used"] == 1
    assert transition.transition_digest


def test_budget_is_monotone_non_increasing_and_at_most_one_retry() -> None:
    payload = retry_payload(budget=RetryBudget(remaining=1, used=0, max_rounds=1))
    first = reduce_retry_action(payload)
    assert first.observations["budget_remaining"] == 0
    assert first.observations["used"] == 1

    exhausted = reduce_retry_action(
        retry_payload(
            budget=RetryBudget(remaining=0, used=1, max_rounds=1),
        )
    )
    assert exhausted.kind == "RETRY_SKIPPED"
    assert exhausted.observations["skip_reason"] == "retry_budget_exhausted"
    assert exhausted.observations["budget_remaining"] == 0


def test_disabled_dry_run_critic_stop_and_score_guards_skip() -> None:
    disabled = reduce_retry_action(retry_payload(retry_enabled=False))
    assert disabled.kind == "RETRY_SKIPPED"
    assert disabled.observations["skip_reason"] == "bounded_retry_disabled"

    dry = reduce_retry_action(retry_payload(dry_run=True))
    assert dry.observations["skip_reason"] == "dry_run"

    stop = reduce_retry_action(retry_payload(next_action="stop", reason_codes=()))
    assert stop.observations["skip_reason"] == "critic_stop"

    above = reduce_retry_action(
        retry_payload(
            score=0.8,
            next_action="retry_with_precision_query",
            reason_codes=("precision_needed",),
        )
    )
    assert above.observations["skip_reason"] == "score_above_threshold"


def test_ordered_rewrite_applies_in_current_task_order() -> None:
    base = AgentBatchTask(
        task_id="search_1",
        channel="search.market",
        query_terms=("机器人",),
        max_items=20,
    )
    payload = retry_payload(
        tasks=(base,),
        action=RetryAction(
            action="narrow_query_terms",
            reason="precision",
            channel="search.market",
            rewrite={"query_terms": ("机器人 公司 厂商",)},
        ),
        next_action="retry_with_precision_query",
        reason_codes=("precision_needed",),
        score=0.5,
    )
    transition = reduce_retry_action(payload)
    assert transition.kind == "RETRY_SCHEDULED"
    assert transition.tasks[0].task_id == "search_1"
    assert transition.tasks[0].query_terms == ("机器人 公司 厂商",)
    assert transition.tasks[0].max_items == 20


def test_no_effect_rewrite_skips_without_new_attempt() -> None:
    payload = retry_payload(
        action=RetryAction(
            action="attach_source_library",
            reason="source_backing_missing",
            channel="source_library",
            rewrite={
                "item_key": "handler.cluster.news",
                "query_terms": ("机器人",),
            },
        )
    )
    transition = reduce_retry_action(payload)
    assert transition.kind == "RETRY_SCHEDULED"
    assert transition.attempt_intent is not None
    assert len(transition.tasks) == 2

    duplicate = retry_payload(
        tasks=(
            AgentBatchTask(
                task_id="source_1",
                channel="source_library",
                item_key="handler.cluster.news",
            ),
        ),
        action=RetryAction(
            action="attach_source_library",
            reason="source_backing_missing",
            channel="source_library",
            rewrite={"item_key": "handler.cluster.news"},
        ),
        next_action="retry_with_source_library",
        reason_codes=("source_backing_missing",),
        score=0.5,
    )
    no_effect = reduce_retry_action(duplicate)
    assert no_effect.kind == "RETRY_SKIPPED"
    assert no_effect.observations["skip_reason"] == "retry_action_no_effect"
    assert no_effect.attempt_intent is None


def test_source_mode_rewrite_is_rejected_by_c4_successor_surface() -> None:
    action = RetryAction(
        action="attach_source_library",
        reason="source_backing_missing",
        channel="source_library",
        rewrite={
            "item_key": "handler.cluster.news",
            "source_mode": "site_search",
        },
    )
    normalized, reason_code, details = validate_retry_action(action)
    assert normalized is not None
    assert reason_code == "retry_action_rewrite_fields_unsupported"
    assert "source_mode" in details["unsupported_fields"]

    with pytest.raises(ValueError, match="source_mode"):
        reduce_retry_action(
            retry_payload(
                action=RetryAction(
                    action="attach_source_library",
                    reason="source_backing_missing",
                    channel="source_library",
                    rewrite={
                        "item_key": "handler.cluster.news",
                        "source_mode": "site_search",
                    },
                )
            )
        )


def test_reducer_output_has_no_source_mode_anywhere() -> None:
    transition = reduce_retry_action(retry_payload())

    def walk(value: object) -> None:
        if dataclasses.is_dataclass(value):
            for field_def in dataclasses.fields(value):
                assert field_def.name != "source_mode"
                walk(getattr(value, field_def.name))
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            assert "source_mode" not in value
            for item in value.values():
                walk(item)

    walk(transition)
