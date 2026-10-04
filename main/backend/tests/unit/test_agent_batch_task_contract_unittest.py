from __future__ import annotations

import pytest

from app.services.agent_batch.task_contract import (
    _apply_retry_action,
    _build_search_brief,
    _expand_tasks_with_limited_branching,
    build_agent_batch_execution_registry,
    normalize_agent_batch_task,
)


pytestmark = pytest.mark.unit


def test_normalize_task_uses_shared_source_library_defaults() -> None:
    task = normalize_agent_batch_task(
        {"channel": "source_library", "item_key": "ai_terminal.weekly"},
        idx=1,
        default_language="zh",
    )

    assert task["max_items"] == 20
    assert task["provider"] == "auto"
    assert task["source_mode"] is None


def test_search_brief_preserves_strategy_time_and_source_preferences() -> None:
    task = normalize_agent_batch_task(
        {
            "channel": "search.market",
            "query_terms": ["ai terminal market signals"],
            "max_items": 20,
            "language": "en",
            "days_back": 14,
        },
        idx=1,
        default_language="en",
    )

    brief = _build_search_brief(
        command="search ai terminal market signals last 14 days top 20",
        intent="market_news",
        tasks=[task],
        retrieval_mode="web_only",
        autonomy_meta={"enabled": False, "item_keys": []},
    )

    assert brief["intent"] == "market_news"
    assert brief["time_strategy"] == {"mode": "recent", "days_back": 14}
    assert brief["search_strategies"] == [
        {"label": "broad", "query_terms": ["ai terminal market signals"]}
    ]
    assert brief["source_preferences"]["attach_source_library"] is False
    assert brief["stop_conditions"]["max_search_rounds"] == 2


def test_limited_branching_expands_high_ambiguity_search_task() -> None:
    command = "search ai terminal products companies web only last 30 days top 10"
    task = normalize_agent_batch_task(
        {
            "channel": "search.market",
            "query_terms": ["ai terminal products companies"],
            "max_items": 10,
            "language": "en",
            "days_back": 30,
        },
        idx=1,
        default_language="en",
    )
    brief = _build_search_brief(
        command=command,
        intent="market_research_general",
        tasks=[task],
        retrieval_mode="web_only",
        autonomy_meta={"enabled": False, "item_keys": []},
    )

    expanded, branching = _expand_tasks_with_limited_branching(
        tasks=[task],
        search_brief=brief,
        retrieval_mode="web_only",
        enable_limited_branching=True,
        command=command,
    )

    assert branching == {
        "default_enabled": False,
        "enabled": True,
        "branch_count": 2,
        "reason": "high_ambiguity_prompt",
        "strategy_labels": ["broad", "precision"],
    }
    assert len(expanded) == 2
    assert expanded[0]["query_terms"] != expanded[1]["query_terms"]


def test_retry_attach_source_library_inherits_query_terms_and_target_count() -> None:
    retried = _apply_retry_action(
        tasks=[
            {
                "channel": "search.market",
                "query_terms": ["ai terminal products companies"],
                "max_items": 8,
                "provider": "auto",
                "language": "en",
            }
        ],
        retry_action={
            "action": "attach_source_library",
            "channel": "source_library",
            "rewrite": {"item_key": "ai_terminal.weekly"},
        },
        command="search ai terminal products companies top 8",
    )

    assert len(retried) == 2
    source_task = retried[1]
    assert source_task["channel"] == "source_library"
    assert source_task["item_key"] == "ai_terminal.weekly"
    assert source_task["query_terms"] == ["ai terminal products companies"]
    assert source_task["max_items"] == 8
    assert source_task["source_mode"] is None


def test_build_agent_batch_execution_registry_resolves_exports_and_fails_fast() -> None:
    registry = build_agent_batch_execution_registry(
        execution_bindings=[
            {
                "channel": "search.market",
                "submitter_export": "submit_search",
                "rule_guard_export": "guard_search",
            }
        ],
        globals_map={
            "submit_search": lambda *_args, **_kwargs: None,
            "guard_search": lambda *_args, **_kwargs: None,
        },
    )
    assert callable(registry["search.market"]["submitter"])
    assert callable(registry["search.market"]["rule_guard"])

    try:
        build_agent_batch_execution_registry(
            execution_bindings=[
                {
                    "channel": "search.market",
                    "submitter_export": "missing_submit",
                }
            ],
            globals_map={},
        )
    except RuntimeError as error:
        assert str(error) == "channel submitter export not found: missing_submit"
    else:
        raise AssertionError("missing submitter export must fail fast")
