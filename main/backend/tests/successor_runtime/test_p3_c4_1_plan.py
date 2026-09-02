"""C4.1 ordered pure batch-plan contracts and source-mode boundary tests."""

from __future__ import annotations

import dataclasses

from app.successor_runtime.capabilities.agent_batch_c4 import (
    AgentBatchTask,
    build_batch_plan,
)

from .p3_c4_fixture import (
    PROJECT_KEY,
    SCOPE_DIGEST,
    c2_snapshot,
    plan_payload,
)


def _assert_no_source_mode(value: object) -> None:
    if dataclasses.is_dataclass(value):
        for field_def in dataclasses.fields(value):
            if field_def.name == "source_mode":
                raise AssertionError(f"{type(value).__name__} carries source_mode")
            _assert_no_source_mode(getattr(value, field_def.name))
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_source_mode(item)
    elif isinstance(value, dict):
        if "source_mode" in value:
            raise AssertionError("dict carries source_mode")
        for item in value.values():
            _assert_no_source_mode(item)


def test_plan_consumes_exact_c2_snapshot_without_source_mode_write() -> None:
    snapshot = c2_snapshot(item_keys=("handler.cluster.news", "market.default.tech"))
    payload = plan_payload(candidates=snapshot)
    assert payload.candidates.catalog.digest == snapshot.catalog.digest
    result = build_batch_plan(payload)

    assert snapshot.catalog.digest
    assert tuple(item.item_key for item in snapshot.source_items) == (
        "handler.cluster.news",
        "market.default.tech",
    )
    assert result.supplementation.enabled is True
    assert result.supplementation.item_keys == (
        "handler.cluster.news",
        "market.default.tech",
    )
    assert result.supplementation.selection_mode == "goal_relevance"
    assert len(result.tasks) == 3
    assert result.tasks[0].channel == "search.market"
    assert [task.channel for task in result.tasks[1:]] == [
        "source_library",
        "source_library",
    ]
    assert result.tasks[1].item_key == "handler.cluster.news"
    assert result.tasks[1].query_terms == payload.tasks[0].query_terms
    assert result.tasks[1].max_items == payload.tasks[0].max_items
    _assert_no_source_mode(result)


def test_supplementation_preserves_query_terms_and_target_max_items() -> None:
    base = AgentBatchTask(
        task_id="search_1",
        channel="search.market",
        query_terms=("生成式 AI 市场",),
        max_items=7,
        language="zh",
    )
    result = build_batch_plan(plan_payload(tasks=(base,)))

    appended = [task for task in result.tasks if task.channel == "source_library"]
    assert len(appended) == 2
    assert appended[0].query_terms == ("生成式 AI 市场",)
    assert appended[0].max_items == 7
    assert appended[1].query_terms == ("生成式 AI 市场",)
    assert appended[1].max_items == 7


def test_web_only_and_already_planned_modes_skip_supplementation() -> None:
    web_only = build_batch_plan(plan_payload(retrieval_mode="web_only"))
    assert web_only.supplementation.enabled is False
    assert web_only.supplementation.reason == "web_only_mode"
    assert len(web_only.tasks) == 1

    source_task = AgentBatchTask(
        task_id="source_1",
        channel="source_library",
        item_key="handler.cluster.news",
    )
    planned = build_batch_plan(
        plan_payload(
            tasks=(source_task,),
            retrieval_mode="hybrid",
            command="调研机器人",
        )
    )
    assert planned.supplementation.enabled is False
    assert planned.supplementation.reason == "source_library_already_planned"


def test_branching_is_broad_before_precision_and_default_off() -> None:
    disabled = build_batch_plan(plan_payload(limited_branching=False))
    assert disabled.branching.enabled is False
    assert disabled.branching.branch_count == 1

    enabled = build_batch_plan(
        plan_payload(
            command="调研机器人产品、公司和厂商",
            limited_branching=True,
            candidates=c2_snapshot(item_keys=()),
        )
    )
    assert enabled.branching.enabled is True
    assert enabled.branching.strategy_labels == ("broad", "precision")
    assert len(enabled.tasks) == 2
    assert enabled.tasks[0].task_id == "search_1"
    assert enabled.tasks[1].task_id == "search_1_branch_precision"
    assert enabled.tasks[1].query_terms
    assert enabled.tasks[1].query_terms != enabled.tasks[0].query_terms


def test_source_only_retrieval_never_branches_and_preserves_order() -> None:
    payload = plan_payload(
        tasks=(
            AgentBatchTask(
                task_id="source_keep",
                channel="source_library",
                item_key="market.default.tech",
            ),
        ),
        retrieval_mode="source_only",
        command="只用来源库调研机器人",
        limited_branching=True,
    )
    result = build_batch_plan(payload)
    assert result.branching.reason == "source_only_mode"
    keys = [task.item_key for task in result.tasks]
    assert keys[0] == "market.default.tech"
    assert keys[1:] == ["handler.cluster.news", "market.default.tech"]


def test_scope_digest_and_catalog_digest_are_exact_bound() -> None:
    payload = plan_payload()
    assert payload.scope_digest == SCOPE_DIGEST
    assert payload.project_key == PROJECT_KEY
    snapshot = payload.candidates
    assert snapshot.catalog.digest
    assert snapshot.catalog.revision == 9
    assert snapshot.catalog.incarnation == "channel-catalog-inc-c4"
    for item in snapshot.source_items:
        assert item.content_digest
        assert item.item_key


def test_empty_candidates_are_explicit_no_match_not_source_mode() -> None:
    snapshot = c2_snapshot(item_keys=())
    result = build_batch_plan(plan_payload(candidates=snapshot))
    assert result.supplementation.enabled is False
    assert result.supplementation.reason == "no_source_library_match"
    assert len(result.tasks) == 1
    _assert_no_source_mode(result)


def test_c4_batch_task_vocabulary_has_no_source_mode_field() -> None:
    assert "source_mode" not in {
        field_def.name for field_def in dataclasses.fields(AgentBatchTask)
    }
