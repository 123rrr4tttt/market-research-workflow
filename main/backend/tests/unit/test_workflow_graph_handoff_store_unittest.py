from __future__ import annotations

import unittest

import pytest

from app.services.workflow_graph.handoff_store import WorkflowGraphHandoffStore
from app.services.workflow_graph.store import InMemoryRunStore

pytestmark = pytest.mark.unit


class WorkflowGraphHandoffStoreUnitTest(unittest.TestCase):
    def test_persist_list_and_replay(self):
        store = InMemoryRunStore()
        handoff_store = WorkflowGraphHandoffStore(store=store)
        payload = {
            "run_id": "run-h1",
            "contract_version": "graph_handoff.v1",
            "handoff_id": "h1",
            "handoff_mode": "pull_prepared_evidence",
            "producer": "workflow_graph.backend_bridge",
            "consumer": "llm_report.generate",
            "evidence_pack": {
                "contract_version": "graph_evidence_pack.v1",
                "pack_id": "p1",
                "provenance": {"project_key": "demo_proj"},
            },
        }

        persisted = handoff_store.persist(graph_id="g1", payload=payload)
        self.assertEqual(persisted["handoff_id"], "h1")
        self.assertEqual(persisted["audit_contract_version"], "workflow_graph.governance_audit.v1")
        persisted_event = store.get_events("run-h1")[0]
        self.assertEqual(persisted_event["payload"]["audit"]["action"], "handoff.persisted")
        self.assertEqual(persisted_event["payload"]["audit"]["object_scope"], "graph_handoff")
        self.assertEqual(persisted_event["payload"]["audit"]["project_key"], "demo_proj")
        self.assertEqual(
            persisted_event["payload"]["audit"]["context"]["evidence_pack_contract_version"],
            "graph_evidence_pack.v1",
        )

        listed = handoff_store.list_handoffs(run_id="run-h1")
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["handoff_id"], "h1")

        replayed = handoff_store.replay_handoff(run_id="run-h1", handoff_id="h1")
        self.assertEqual(replayed["handoff_id"], "h1")
        self.assertEqual(replayed["result"]["handoff_id"], "h1")
        self.assertTrue(any(evt.get("type") == "handoff.replayed" for evt in replayed["events"]))
        replay_event = [evt for evt in replayed["events"] if evt.get("type") == "handoff.replayed"][0]
        self.assertEqual(replay_event["payload"]["audit"]["action"], "handoff.replayed")
        self.assertEqual(replay_event["payload"]["audit"]["context"]["handoff_id"], "h1")

    def test_unknown_handoff_event_fail_closed(self):
        store = InMemoryRunStore()
        store.create_run(run_id="run-h2", topo_order=[])
        store.append_event("run-h2", event_type="handoff.unknown", payload={"handoff_id": "h2"})
        handoff_store = WorkflowGraphHandoffStore(store=store)
        with self.assertRaises(ValueError) as exc:
            handoff_store.list_handoffs(run_id="run-h2")
        self.assertIn("unknown handoff event type", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
