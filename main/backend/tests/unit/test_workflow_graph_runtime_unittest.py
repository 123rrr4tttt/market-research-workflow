from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

import pytest

from app.services.agent_sessions import (
    reset_agent_session_service_for_tests,
    reset_agent_session_store_for_tests,
)
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services import workflow_graph as workflow_graph_module
from app.services.workflow_graph import WorkflowGraphRuntimeService
from app.services.workflow_graph.governance_contract import build_graph_rollback_contract
from app.services.workflow_graph.runtime import WorkflowGraphPlatformInterpreter
from app.services.workflow_graph.store import InMemoryCompiledGraphStore, InMemoryRunStore
from app.successor_runtime.capabilities.workflow_legacy_dsl import (
    parse_and_validate_workflow_dsl,
    workflow_program_metadata,
)


pytestmark = pytest.mark.unit


def _dsl() -> dict[str, Any]:
    return {
        "version": "1.0",
        "options": {},
        "nodes": [
            {"node_id": "n1", "node_type": "vector_search", "config": {"query": "ai", "top_k": 2}},
            {"node_id": "n2", "node_type": "llm_call", "config": {"prompt": "summarize"}},
            {"node_id": "n3", "node_type": "join", "config": {"field": "text"}},
        ],
        "edges": [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3"},
            {"from": "n1", "to": "n3"},
        ],
    }


def _bound() -> tuple[Any, Any, dict[str, Any]]:
    receipt = parse_and_validate_workflow_dsl(_dsl())
    assert receipt.ok and receipt.plan is not None
    metadata = workflow_program_metadata(receipt.program)
    nodes = {
        str(item["node_id"]): {
            "id": str(item["node_id"]),
            "node_type": item["node_type"],
            "params": dict(item["config"]),
        }
        for item in metadata["nodes"]
    }
    workflow = {
        "workflow_id": "wf-bound",
        "program_digest": receipt.program_digest,
        "plan_digest": receipt.plan_digest,
        "topo_order": list(metadata["topo_order"]),
        "nodes": nodes,
    }
    for node in nodes.values():
        incoming = [edge["from"] for edge in metadata["edges"] if edge["to"] == node["id"]]
        node["depends_on"] = incoming
    return receipt.program, receipt.plan, workflow


def _effect(node_type: str, payload: dict[str, Any]):
    from app.services.workflow_graph.executors.kernel import node_success

    def execute(context):
        assert context.node_type == node_type
        return node_success(context, payload)

    return execute


class WorkflowGraphPlatformInterpreterUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        store = InMemoryAgentSessionStore()
        reset_agent_session_store_for_tests(store)
        reset_agent_session_service_for_tests(
            AgentSessionService(store=store)
        )

    def test_plan_bound_interpreter_preserves_order_and_single_node_identity(self) -> None:
        program, plan, workflow = _bound()
        calls: list[str] = []

        def execute(context):
            calls.append(context.node_id)
            from app.services.workflow_graph.executors.kernel import node_success

            payload = {
                "vector_search": {"text": "ai"},
                "llm_call": {"text": "summary"},
                "join": {"values": ["ai", "summary"]},
            }[context.node_type]
            return node_success(context, payload)

        with patch(
            "app.services.workflow_graph.runtime.execute_node",
            side_effect=execute,
        ) as kernel:
            snapshot = WorkflowGraphPlatformInterpreter().run(
                plan=plan,
                program=program,
                workflow=workflow,
                inputs={"query": "ai"},
                run_id="run-order",
            )

        self.assertEqual(calls, ["n1", "n2", "n3"])
        self.assertEqual(kernel.call_count, 3)
        self.assertEqual(snapshot["run"]["status"], "succeeded")
        self.assertEqual(list(snapshot["results"]), ["n1", "n2", "n3"])
        self.assertEqual(snapshot["results"]["n3"]["values"], ["ai", "summary"])
        self.assertEqual(snapshot["run"]["metadata"]["program_digest"], workflow["program_digest"])
        self.assertEqual(snapshot["run"]["metadata"]["plan_digest"], workflow["plan_digest"])

    def test_kernel_failure_stops_unexecuted_downstream_nodes(self) -> None:
        program, plan, workflow = _bound()

        def execute(context):
            from app.services.workflow_graph.executors.kernel import node_failed

            if context.node_id == "n2":
                return node_failed(
                    context,
                    "required_input_missing",
                    "prompt_template_missing_inputs:topic",
                    owner="workflow_graph.kernel.llm_call",
                    details={"missing": ["topic"]},
                )
            from app.services.workflow_graph.executors.kernel import node_success

            return node_success(context, {"text": "ok"})

        with patch(
            "app.services.workflow_graph.runtime.execute_node",
            side_effect=execute,
        ) as kernel:
            snapshot = WorkflowGraphPlatformInterpreter().run(
                plan=plan,
                program=program,
                workflow=workflow,
                run_id="run-failure",
            )

        self.assertEqual(snapshot["run"]["status"], "failed")
        self.assertEqual(snapshot["run"]["node_statuses"], {
            "n1": "succeeded",
            "n2": "failed",
            "n3": "queued",
        })
        self.assertEqual(kernel.call_count, 2)
        failed = [event for event in snapshot["events"] if event["event_type"] == "node.failed"][0]
        self.assertEqual(failed["payload"]["failure_code"], "required_input_missing")
        self.assertEqual(
            failed["payload"]["failure_context"]["owner"],
            "workflow_graph.kernel.llm_call",
        )

    def test_expression_and_node_output_input_projection_is_preserved(self) -> None:
        payload = _dsl()
        payload["nodes"][0]["config"]["input_vars"] = [{
            "name": "query",
            "source": "expression",
            "expr": "={{$input.query}}",
            "required": True,
        }]
        payload["nodes"][1]["config"] = {
            "input_vars": [{
                "name": "prompt",
                "source": "node_output",
                "from_node": "n1",
                "from_key": "text",
                "required": True,
            }]
        }
        receipt = parse_and_validate_workflow_dsl(payload)
        assert receipt.ok and receipt.plan is not None
        metadata = workflow_program_metadata(receipt.program)
        nodes = {
            str(item["node_id"]): {
                "id": str(item["node_id"]),
                "node_type": item["node_type"],
                "params": dict(item["config"]),
            }
            for item in metadata["nodes"]
        }
        workflow = {
            "workflow_id": "wf-input",
            "program_digest": receipt.program_digest,
            "plan_digest": receipt.plan_digest,
            "topo_order": list(metadata["topo_order"]),
            "nodes": nodes,
        }
        captured: dict[str, Any] = {}

        def execute(context):
            from app.services.workflow_graph.executors.kernel import node_success

            captured[context.node_id] = context
            payload = {"n1": {"text": "hello"}, "n2": {"text": "hello"}, "n3": {}}
            return node_success(context, payload[context.node_id])

        with patch(
            "app.services.workflow_graph.runtime.execute_node",
            side_effect=execute,
        ):
            snapshot = WorkflowGraphPlatformInterpreter().run(
                plan=receipt.plan,
                program=receipt.program,
                workflow=workflow,
                inputs={"query": "hello"},
                run_id="run-input",
            )

        self.assertEqual(captured["n1"].inputs.get("query"), "hello")
        self.assertEqual(captured["n2"].inputs.get("prompt"), "hello")
        self.assertEqual(
            snapshot["results"]["n1"]["io_trace"]["query"]["source"],
            "expression",
        )

    def test_topo_drift_fails_without_executing_kernels(self) -> None:
        program, plan, workflow = _bound()
        workflow["topo_order"] = ["n2", "n1", "n3"]
        with patch(
            "app.services.workflow_graph.runtime.execute_node",
            side_effect=AssertionError("kernel must not run"),
        ):
            snapshot = WorkflowGraphPlatformInterpreter().run(
                plan=plan,
                program=program,
                workflow=workflow,
                run_id="run-drift",
            )

        self.assertEqual(snapshot["run"]["status"], "failed")
        failed = [event for event in snapshot["events"] if event["event_type"] == "run.failed"][0]
        self.assertEqual(failed["payload"]["reason_code"], "workflow_integrity_failed")


class WorkflowGraphServiceUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        store = InMemoryAgentSessionStore()
        reset_agent_session_store_for_tests(store)
        reset_agent_session_service_for_tests(
            AgentSessionService(store=store)
        )

    def test_service_uses_current_lowering_and_platform_interpreter(self) -> None:
        compiled_store = InMemoryCompiledGraphStore()
        compiler_service = workflow_graph_module.WorkflowGraphCompilerService(
            store=compiled_store,
        )
        response = compiler_service.compile({
            "graph_id": "wf-platform",
            "dsl": {
                "version": "1.0",
                "nodes": [
                    {"node_id": "n1", "node_type": "vector_search", "config": {"query": "ai"}},
                    {"node_id": "n2", "node_type": "join"},
                ],
                "edges": [{"from": "n1", "to": "n2"}],
            },
        })
        self.assertTrue(response["program_digest"])
        self.assertTrue(response["plan_digest"])
        reloaded_compiler = workflow_graph_module.WorkflowGraphCompilerService(
            store=compiled_store,
        )
        service = WorkflowGraphRuntimeService()
        service._engine = WorkflowGraphPlatformInterpreter(store=InMemoryRunStore())

        def execute(context):
            from app.services.workflow_graph.executors.kernel import node_success

            return node_success(context, {"text": "ai"} if context.node_id == "n1" else {"values": ["ai"]})

        with (
            patch.object(workflow_graph_module, "compiler", reloaded_compiler),
            patch(
                "app.services.workflow_graph.runtime.execute_node",
                side_effect=execute,
            ) as kernel,
        ):
            out = service.run({"graph_id": "wf-platform", "input": {"query": "ai"}})

        self.assertEqual(out["status"], "succeeded")
        self.assertEqual(out["compat_mode"], False)
        self.assertEqual(kernel.call_count, 2)
        detail = service.get_run(str(out["run_id"]))
        self.assertEqual(detail["status"], "succeeded")
        self.assertEqual(detail["metadata"]["program_digest"], response["program_digest"])
        self.assertEqual(detail["metadata"]["plan_digest"], response["plan_digest"])

    def test_service_rejects_stale_platform_binding(self) -> None:
        service = WorkflowGraphRuntimeService()
        compiled = {
            "dsl": _dsl(),
            "topo_order": ["n1"],
            "nodes": {},
            "platform": {
                "program_digest": "stale",
                "plan_digest": "stale",
                "catalog_digest": "stale",
            },
        }
        with patch.object(workflow_graph_module, "compiler") as compiler_patch:
            compiler_patch.get_compiled.return_value = compiled
            with self.assertRaisesRegex(ValueError, "platform binding is stale"):
                service.run({"graph_id": "stale", "input": {}})

    def test_replay_run_reports_explicit_consistency_mismatch(self) -> None:
        service = WorkflowGraphRuntimeService()
        service._engine = WorkflowGraphPlatformInterpreter(store=InMemoryRunStore())
        run_id = service._engine.store.create_run(
            run_id="run-replay-mismatch",
            topo_order=["n1"],
        )
        service._engine.store.set_run_status(run_id, "succeeded")
        service._engine.store.append_event(run_id, event_type="run.running")
        service._engine.store.append_event(run_id, event_type="node.running", node_id="n1")

        replay = service.replay_run(run_id, replay_mode="events_only")

        self.assertFalse(replay["replay_consistency"]["consistent"])
        codes = [item["code"] for item in replay["replay_consistency"]["issues"]]
        self.assertIn("run_status_mismatch", codes)
        self.assertIn("node_status_mismatch", codes)


class WorkflowGraphCompatibilityUnitTest(unittest.TestCase):
    def test_old_runtime_and_wrappers_are_retired(self) -> None:
        with self.assertRaises(ImportError):
            from app.services.workflow_graph.runtime import WorkflowGraphRuntime  # noqa: F401
        with self.assertRaises(ImportError):
            from app.services.workflow_graph.executors.base import (  # noqa: F401
                LegacyNodeExecutionContext,
            )
        with self.assertRaises(ImportError):
            from app.services.workflow_graph.executors.join import JoinExecutor  # noqa: F401
        with self.assertRaises(ImportError):
            from app.services.workflow_graph.executors.llm_call import LLMCallExecutor  # noqa: F401
        with self.assertRaises(ImportError):
            from app.services.workflow_graph.executors.vector_search import VectorSearchExecutor  # noqa: F401

    def test_graph_rollback_contract_is_preserved(self) -> None:
        contract = build_graph_rollback_contract(
            actor_id="ops-user",
            project_key="demo_proj",
            graph_id="cg-1",
            target_version_id="cver-1",
            current_revision=4,
            base_revision=4,
            reason="restore tested snapshot",
        )
        self.assertEqual(contract["contract_version"], "workflow_graph.rollback.v1")


if __name__ == "__main__":
    unittest.main()
