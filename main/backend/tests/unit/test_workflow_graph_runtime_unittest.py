from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from app.services.workflow_graph.executors.base import BaseNodeExecutor
from app.services.workflow_graph.executors.llm_call import LLMCallExecutor
from app.services.workflow_graph.executors.vector_search import VectorSearchExecutor
from app.services.workflow_graph.runtime import WorkflowGraphRuntime
from app.services.workflow_graph.store import InMemoryRunStore

pytestmark = pytest.mark.unit


class _FailExecutor(BaseNodeExecutor):
    node_type = "llm_call"

    def execute(self, node, context):  # type: ignore[override]
        raise RuntimeError("boom")


class WorkflowGraphRuntimeUnitTest(unittest.TestCase):
    def test_store_keeps_runs_events_results(self):
        store = InMemoryRunStore()
        run_id = store.create_run(run_id="run-1", topo_order=["a", "b"])

        store.set_run_status(run_id, "running")
        store.set_node_status(run_id, "a", "running")
        store.set_node_result(run_id, "a", {"ok": True})
        store.set_node_status(run_id, "a", "succeeded")
        store.append_event(run_id, event_type="node.succeeded", node_id="a")

        snap = store.snapshot(run_id)
        self.assertEqual(snap["run"]["status"], "running")
        self.assertEqual(snap["run"]["node_statuses"]["a"], "succeeded")
        self.assertEqual(snap["results"]["a"], {"ok": True})
        self.assertEqual(snap["events"][0]["type"], "node.succeeded")

    def test_runtime_runs_nodes_by_topo_order_and_marks_succeeded(self):
        runtime = WorkflowGraphRuntime()
        workflow = {
            "workflow_id": "wf-1",
            "topo_order": ["n1", "n2", "n3"],
            "nodes": {
                "n1": {"id": "n1", "node_type": "vector_search", "params": {"query": "ai market", "top_k": 2}},
                "n2": {"id": "n2", "node_type": "llm_call", "depends_on": ["n1"], "params": {"prompt": "summarize"}},
                "n3": {"id": "n3", "node_type": "join", "depends_on": ["n1", "n2"]},
            },
        }

        out = runtime.run(workflow, inputs={"state": "CA"}, run_id="run-topo")

        self.assertEqual(out["run"]["status"], "succeeded")
        self.assertEqual(out["run"]["node_statuses"]["n1"], "succeeded")
        self.assertEqual(out["run"]["node_statuses"]["n2"], "succeeded")
        self.assertEqual(out["run"]["node_statuses"]["n3"], "succeeded")
        self.assertEqual(list(out["results"].keys()), ["n1", "n2", "n3"])

    def test_runtime_marks_failed_when_node_executor_errors(self):
        runtime = WorkflowGraphRuntime(executors=[VectorSearchExecutor(), _FailExecutor()])
        workflow = {
            "workflow_id": "wf-2",
            "topo_order": ["n1", "n2", "n3"],
            "nodes": {
                "n1": {"id": "n1", "node_type": "vector_search", "params": {"query": "test"}},
                "n2": {"id": "n2", "node_type": "llm_call", "depends_on": ["n1"]},
                "n3": {"id": "n3", "node_type": "join", "depends_on": ["n1", "n2"]},
            },
        }

        out = runtime.run(workflow, run_id="run-fail")

        self.assertEqual(out["run"]["status"], "failed")
        self.assertEqual(out["run"]["node_statuses"]["n1"], "succeeded")
        self.assertEqual(out["run"]["node_statuses"]["n2"], "failed")
        self.assertEqual(out["run"]["node_statuses"]["n3"], "queued")
        self.assertNotIn("n3", out["results"])

    def test_vector_search_executor_graceful_fallback(self):
        executor = VectorSearchExecutor()
        fake_context = type("_Ctx", (), {"inputs": {}, "upstream_results": {}})()
        node = {"id": "n1", "node_type": "vector_search", "params": {"query": "fallback test"}}

        with patch("app.services.workflow_graph.executors.vector_search._vector_search_service", side_effect=RuntimeError("x")):
            result = executor.execute(node, fake_context)  # type: ignore[arg-type]

        self.assertTrue(result["degraded"])
        self.assertEqual(len(result["hits"]), 1)
        self.assertEqual(result["hits"][0]["backend"], "mock")

    def test_llm_call_executor_graceful_fallback(self):
        executor = LLMCallExecutor()
        fake_context = type("_Ctx", (), {"inputs": {}, "upstream_results": {"n1": {"v": 1}}})()
        node = {"id": "n2", "node_type": "llm_call", "params": {"prompt": "hello"}}

        with patch("app.services.workflow_graph.executors.llm_call._invoke_llm", side_effect=RuntimeError("llm down")):
            result = executor.execute(node, fake_context)  # type: ignore[arg-type]

        self.assertTrue(result["degraded"])
        self.assertIn("[fallback-llm]", result["text"])


if __name__ == "__main__":
    unittest.main()
