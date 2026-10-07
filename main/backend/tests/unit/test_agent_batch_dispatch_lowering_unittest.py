"""Pure typed body -> single-dispatch payload lowering witness."""

from __future__ import annotations

import pytest

from app.api.agent_batch import (
    AgentBatchItemSubmit,
    build_dispatch_single_payload_from_item,
)
from app.successor_runtime.capabilities import batch_task

pytestmark = pytest.mark.unit


def _lower(
    *,
    item: AgentBatchItemSubmit | None = None,
    dispatch_id: str = "dispatch:batch-task:001",
) -> batch_task.BatchTaskSingleDispatchPayload:
    return build_dispatch_single_payload_from_item(
        item=item
        or AgentBatchItemSubmit(
            item_id="item-1",
            channel="search.market",
            query_terms=["robot"],
        ),
        dispatch_id=dispatch_id,
        project_key="demo",
        resolved_schema="mrw_demo",
        registry_revision=1,
        scope_incarnation="inc-demo",
        scope_digest="0" * 64,
        capability_id=batch_task.BATCH_TASK_OWNER,
        lane="main",
        queue="celery",
        trace_id=None,
        workflow_run_id=None,
    )


def test_body_lowering_preserves_channel_scope_and_routing() -> None:
    payload = _lower()
    assert payload.dispatch_id == "dispatch:batch-task:001"
    assert payload.item.channel == "search.market"
    assert payload.item.job_id == "item-1"
    assert payload.item.query_terms == ("robot",)
    assert payload.lane == "main"
    assert payload.queue == "celery"
    assert payload.capability_id == batch_task.BATCH_TASK_OWNER
    assert payload.payload_digest


def test_body_lowering_rejects_unsupported_channel() -> None:
    with pytest.raises(ValueError, match="unsupported dispatch item channel"):
        _lower(
            item=AgentBatchItemSubmit(item_id="item-1", channel="unknown"),
        )
