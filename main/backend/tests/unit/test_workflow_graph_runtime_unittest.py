from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from app.services.agent_sessions import reset_agent_session_service_for_tests, reset_agent_session_store_for_tests
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services import workflow_graph as workflow_graph_module
from app.services.workflow_graph.executors.base import BaseNodeExecutor
from app.services.workflow_graph.executors.llm_call import LLMCallExecutor
from app.services.workflow_graph.executors.vector_search import VectorSearchExecutor
from app.services.workflow_graph.runtime import WorkflowGraphRuntime
from app.services.workflow_graph import WorkflowGraphRuntimeService
from app.services.workflow_graph.store import InMemoryRunStore

pytestmark = pytest.mark.unit


class _FailExecutor(BaseNodeExecutor):
    node_type = "llm_call"

    def execute(self, node, context):  # type: ignore[override]
        raise RuntimeError("boom")


class _EchoVectorExecutor(BaseNodeExecutor):
    node_type = "vector_search"

    def execute(self, node, context):  # type: ignore[override]
        return {"query": context.inputs.get("query"), "text": context.inputs.get("query")}


class _EchoLlmExecutor(BaseNodeExecutor):
    node_type = "llm_call"

    def execute(self, node, context):  # type: ignore[override]
        return {"text": context.inputs.get("prompt")}


class WorkflowGraphRuntimeUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        store = InMemoryAgentSessionStore()
        reset_agent_session_store_for_tests(store)
        reset_agent_session_service_for_tests(AgentSessionService(store=store))

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
        fake_context = type(
            "_Ctx",
            (),
            {"inputs": {"request_id": "req-1"}, "upstream_results": {"n1": {"v": 1}}, "run_id": "run-1", "node_id": "n2"},
        )()
        node = {"id": "n2", "node_type": "llm_call", "params": {"prompt": "hello"}}

        with patch("app.services.workflow_graph.executors.llm_call._invoke_llm", side_effect=RuntimeError("llm down")):
            result = executor.execute(node, fake_context)  # type: ignore[arg-type]

        self.assertTrue(result["degraded"])
        self.assertIn("[fallback-llm]", result["text"])
        self.assertEqual(result["trace_id"], "req-1")
        self.assertIn("llm", result["meta"])
        self.assertEqual(result["meta"]["llm"]["audit"]["status"], "degraded")

    def test_llm_call_executor_uses_service_config_as_route_baseline(self):
        executor = LLMCallExecutor()
        fake_context = type(
            "_Ctx",
            (),
            {"inputs": {"project_key": "demo_proj"}, "upstream_results": {}, "run_id": "run-2", "node_id": "n9"},
        )()
        node = {
            "id": "n9",
            "node_type": "llm_call",
            "params": {"prompt": "hello", "service_name": "policy_summary"},
        }

        with (
            patch(
                "app.services.workflow_graph.executors.llm_call.get_llm_config",
                return_value={"model": "cfg-model", "temperature": 0.3},
            ),
            patch("app.services.workflow_graph.executors.llm_call._invoke_llm", return_value="ok"),
        ):
            result = executor.execute(node, fake_context)  # type: ignore[arg-type]

        self.assertFalse(result["degraded"])
        self.assertEqual(result["model"], "cfg-model")
        self.assertEqual(result["temperature"], 0.3)
        self.assertEqual(result["route_kind"], "service_config")
        self.assertEqual(result["meta"]["llm"]["routing"]["field_sources"]["model"], "config")
        self.assertEqual(result["meta"]["llm"]["audit"]["status"], "succeeded")

    def test_llm_call_executor_blocks_denied_agent_permission_scope(self):
        executor = LLMCallExecutor()
        fake_context = type(
            "_Ctx",
            (),
            {"inputs": {"project_key": "demo_proj"}, "upstream_results": {}, "run_id": "run-3", "node_id": "n10"},
        )()
        node = {
            "id": "n10",
            "node_type": "llm_call",
            "params": {"prompt": "hello", "permission_scope": ["cross_consumer.invoke"]},
        }
        with patch("app.services.workflow_graph.executors.llm_call._invoke_llm") as mocked_invoke:
            result = executor.execute(node, fake_context)  # type: ignore[arg-type]
        self.assertTrue(result["degraded"])
        self.assertIn("agent_permission_denied", str(result["degraded_reason"]))
        self.assertEqual(result["meta"]["llm"]["audit"]["status"], "blocked")
        self.assertFalse(result["meta"]["agent_boundary"]["allowed"])
        mocked_invoke.assert_not_called()

    def test_runtime_resolves_expression_and_node_output_with_io_trace(self):
        runtime = WorkflowGraphRuntime(executors=[_EchoVectorExecutor(), _EchoLlmExecutor()])
        workflow = {
            "workflow_id": "wf-expr",
            "topo_order": ["n1", "n2"],
            "nodes": {
                "n1": {
                    "id": "n1",
                    "node_type": "vector_search",
                    "params": {
                        "input_vars": [
                            {"name": "query", "source": "expression", "expr": "={{$input.query}}", "required": True},
                        ],
                    },
                },
                "n2": {
                    "id": "n2",
                    "node_type": "llm_call",
                    "depends_on": ["n1"],
                    "params": {
                        "input_vars": [
                            {
                                "name": "prompt",
                                "source": "node_output",
                                "from_node": "n1",
                                "from_key": "text",
                                "required": True,
                            }
                        ],
                    },
                },
            },
        }

        out = runtime.run(workflow, inputs={"query": "hello io"}, run_id="run-expr")

        self.assertEqual(out["run"]["status"], "succeeded")
        self.assertEqual(out["results"]["n1"]["query"], "hello io")
        self.assertEqual(out["results"]["n2"]["text"], "hello io")
        self.assertIn("io_trace", out["results"]["n1"])
        self.assertIn("query", out["results"]["n1"]["io_trace"])
        self.assertEqual(out["results"]["n1"]["io_trace"]["query"]["source"], "expression")
        self.assertIn("data", out["results"]["n2"])
        self.assertIn("meta", out["results"]["n2"])
        self.assertIsNone(out["results"]["n2"]["error"])

    def test_runtime_fails_when_prompt_template_missing_required_inputs(self):
        runtime = WorkflowGraphRuntime()
        workflow = {
            "workflow_id": "wf-missing-prompt-var",
            "topo_order": ["n1"],
            "nodes": {
                "n1": {
                    "id": "n1",
                    "node_type": "llm_call",
                    "params": {
                        "prompt_template": "Answer: {query} / {context}",
                        "input_vars": [{"name": "query", "source": "input", "required": True}],
                    },
                },
            },
        }
        out = runtime.run(workflow, inputs={"query": "x"}, run_id="run-missing-prompt-var")
        self.assertEqual(out["run"]["status"], "failed")
        fail_events = [item for item in out.get("events", []) if item.get("type") == "node.failed"]
        self.assertTrue(fail_events)
        self.assertIn("prompt_template_missing_inputs:context", str(fail_events[-1].get("payload", {}).get("error", "")))

    def test_runtime_service_projects_run_into_agent_session(self):
        service = WorkflowGraphRuntimeService()
        service._engine = WorkflowGraphRuntime(store=InMemoryRunStore())
        compiled = {
            "topo_order": ["n1", "n2"],
            "nodes": {
                "n1": {"id": "n1", "node_type": "vector_search", "params": {"query": "ai"}},
                "n2": {"id": "n2", "node_type": "join", "depends_on": ["n1"]},
            },
        }

        with patch.object(workflow_graph_module.compiler, "get_compiled", return_value=compiled):
            out = service.run({"graph_id": "wf-1", "input": {"query": "ai"}})

        self.assertTrue(str(out["session_id"]))
        self.assertEqual(out["status"], "succeeded")
        run_detail = service.get_run(str(out["run_id"]))
        self.assertEqual(run_detail["session_id"], out["session_id"])
        session_bundle = service.get_run_agent_session(str(out["run_id"]))
        self.assertEqual(session_bundle["session"]["session_id"], out["session_id"])
        task_subjects = [item["subject"] for item in session_bundle["tasks"]]
        self.assertIn("Node n1", task_subjects)
        self.assertIn("Verification", task_subjects)


if __name__ == "__main__":
    unittest.main()
