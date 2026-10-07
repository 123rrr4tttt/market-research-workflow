"""Single-item dispatch kernel: deterministic task_id and queue consistency."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.agent_batch.routing import resolve_queue_for_lane

pytestmark = pytest.mark.unit

try:
    from app.api import agent_batch as agent_batch_api
except Exception as exc:  # pragma: no cover - import guard
    agent_batch_api = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


@pytest.mark.skipif(agent_batch_api is None, reason="agent_batch_api import failed")
def test_market_dispatch_passes_server_task_id_and_lane_queue() -> None:
    recorded: dict[str, object] = {}

    class _ApplyAsyncStub:
        def apply_async(self, **kwargs: object) -> object:
            recorded.update(kwargs)
            return SimpleNamespace(id=str(kwargs.get("task_id") or "random-task"))

    with patch.object(
        agent_batch_api.tasks_module, "task_ingest_market", _ApplyAsyncStub()
    ):
        result = agent_batch_api._skill_dispatch_market_collect(
            {
                "query_terms": ["robot"],
                "project_key": "demo",
                "lane": "main",
                "queue": "user-forged-queue",
                "task_id": "server-derived-task-id",
            }
        )
    assert result["task_id"] == "server-derived-task-id"
    assert recorded["task_id"] == "server-derived-task-id"
    # The actual effect queue must come from lane, not the user-supplied queue.
    assert recorded["queue"] == resolve_queue_for_lane("main")
    assert recorded["queue"] != "user-forged-queue"


@pytest.mark.skipif(agent_batch_api is None, reason="agent_batch_api import failed")
def test_source_dispatch_passes_server_task_id() -> None:
    recorded: dict[str, object] = {}

    class _ApplyAsyncStub:
        def apply_async(self, **kwargs: object) -> object:
            recorded.update(kwargs)
            return SimpleNamespace(id=str(kwargs.get("task_id") or "random-task"))

    with patch.object(
        agent_batch_api.tasks_module, "task_run_source_library_item", _ApplyAsyncStub()
    ):
        result = agent_batch_api._skill_dispatch_source_library_item(
            {
                "item_key": "source:1",
                "project_key": "demo",
                "lane": "subagent",
                "task_id": "server-derived-source-task",
            }
        )
    assert result["task_id"] == "server-derived-source-task"
    assert recorded["task_id"] == "server-derived-source-task"
    assert recorded["queue"] == resolve_queue_for_lane("subagent")


def test_installed_dispatch_uses_declared_skill_and_native_kernel() -> None:
    from app.composition.production import dispatch_batch_item
    from app.successor_runtime.capabilities import batch_task as c4
    from celery import Celery

    broker = Celery("controlled-native-dispatch", broker="memory://", backend="cache+memory://")
    queue = resolve_queue_for_lane("main")
    payload = c4.BatchTaskSingleDispatchPayload(
        schema_version=c4.DISPATCH_SINGLE_PAYLOAD_SCHEMA, operation_kind=c4.DISPATCH_SINGLE_KIND,
        dispatch_id="dispatch:native", project_key="controlled", resolved_schema="project_controlled",
        registry_revision=1, scope_incarnation="scope:controlled", scope_digest="a" * 64,
        capability_id=c4.BATCH_TASK_OWNER,
        item=c4.AgentBatchSubmissionItem(job_id="source:1", channel="source_library", item_key="source:1"),
        lane="main", queue=queue,
    )
    sent: list[dict[str, object]] = []

    class Transport:
        def apply_async(self, **kwargs: object) -> object:
            sent.append(kwargs)
            return broker.send_task("controlled.source", args=kwargs["args"], kwargs=kwargs["kwargs"],
                                    queue=kwargs["queue"], task_id=kwargs["task_id"])

    with patch.object(agent_batch_api.tasks_module, "task_run_source_library_item", Transport()):
        ack = dispatch_batch_item(payload)
    assert len(sent) == 1
    assert ack.celery_task_id == c4.derive_dispatch_task_id(
        project_scope_digest=payload.scope_digest, capability_id=payload.capability_id, dispatch_id=payload.dispatch_id)
    assert ack.queue == sent[0]["queue"] == queue
    with broker.connection() as connection:
        transport_queue = connection.SimpleQueue(queue)
        message = transport_queue.get(block=False)
        assert message.headers["id"] == ack.celery_task_id
        message.ack()
        transport_queue.close()
