from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import pytest

from app.services.workflow_graph.handoff_store import WorkflowGraphHandoffStore
from app.services.workflow_graph.store import InMemoryHistoricalWorkflowRunReader

pytestmark = pytest.mark.unit


def _payload() -> dict[str, object]:
    return {
        "run_id": "run-h1",
        "handoff_id": "h1",
        "contract_version": "graph_handoff.v1",
        "handoff_mode": "pull_prepared_evidence",
        "producer": "workflow_graph.backend_bridge",
        "consumer": "llm_report.generate",
        "evidence_pack": {"contract_version": "graph_evidence_pack.v1"},
    }


def _event(seq: int, event_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "event_id": f"run-h1:{seq}",
        "event_type": event_type,
        "project_key": None,
        "session_id": None,
        "run_id": "run-h1",
        "trace_id": "workflow_graph.run-h1",
        "created_at": "2026-10-07T00:00:00+00:00",
        "seq": seq,
        "ts": "2026-10-07T00:00:00+00:00",
        "type": event_type,
        "node_id": None,
        "payload": payload,
    }


def _reader(*events: dict[str, object]) -> InMemoryHistoricalWorkflowRunReader:
    return InMemoryHistoricalWorkflowRunReader(
        {
            "run-h1": {
                "run": {
                    "run_id": "run-h1",
                    "status": "succeeded",
                    "created_at": "2026-10-07T00:00:00+00:00",
                    "updated_at": "2026-10-07T00:00:00+00:00",
                    "node_statuses": {},
                    "metadata": {"workflow_id": "g1", "project_key": "demo_proj"},
                },
                "events": list(events),
                "results": {},
            }
        }
    )


class WorkflowGraphHandoffStoreUnitTest(unittest.TestCase):
    def test_build_returns_typed_request_local_carrier_without_reader_write(self) -> None:
        reader = MagicMock()
        store = WorkflowGraphHandoffStore(reader=reader)

        built = store.build(graph_id="g1", payload=_payload())

        self.assertEqual(built["run_id"], "run-h1")
        self.assertEqual(built["handoff_id"], "h1")
        self.assertEqual(built["payload"]["evidence_pack"]["contract_version"], "graph_evidence_pack.v1")
        self.assertFalse(built["durable"])
        self.assertEqual(built["backend_marker"], "workflow_graph.request_local_handoff")
        reader.get_events.assert_not_called()

    def test_historical_list_and_replay_are_read_only(self) -> None:
        persisted = _event(1, "handoff.persisted", _payload())
        replayed = _event(
            2,
            "handoff.replayed",
            {
                "run_id": "run-h1",
                "handoff_id": "h1",
                "contract_version": "workflow_graph.handoff.v1",
            },
        )
        store = WorkflowGraphHandoffStore(reader=_reader(persisted, replayed))

        listed = store.list_handoffs(run_id="run-h1", project_key="demo_proj")
        replay = store.replay_handoff(
            run_id="run-h1",
            handoff_id="h1",
            project_key="demo_proj",
        )

        self.assertEqual(listed["total"], 1)
        self.assertTrue(listed["read_only"])
        self.assertEqual(replay["result"]["handoff_id"], "h1")
        self.assertEqual([event["type"] for event in replay["events"]], ["handoff.persisted", "handoff.replayed"])
        self.assertTrue(replay["read_only"])

        with self.assertRaisesRegex(KeyError, "not available in this project"):
            store.replay_handoff(
                run_id="run-h1",
                handoff_id="h1",
                project_key="other_proj",
            )

    def test_unknown_handoff_event_type_fails_closed(self) -> None:
        store = WorkflowGraphHandoffStore(
            reader=_reader(_event(1, "handoff.unknown", {"handoff_id": "h1"}))
        )
        with self.assertRaisesRegex(ValueError, "unknown handoff event type"):
            store.list_handoffs(run_id="run-h1", project_key="demo_proj")


if __name__ == "__main__":
    unittest.main()
