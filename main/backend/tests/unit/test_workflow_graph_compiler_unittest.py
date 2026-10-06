from __future__ import annotations

import inspect
import unittest
from typing import get_args
from unittest.mock import MagicMock

from functorial_kit import Failure

from app.services.workflow_graph import WorkflowGraphCompilerService
from app.services.workflow_graph.compiler import compile_workflow_graph
from app.services.workflow_graph.contracts import WorkflowGraphCompileError
from app.services.workflow_graph.store import InMemoryCompiledGraphStore
from app.successor_runtime.capabilities.workflow_legacy_dsl import (
    parse_and_validate_workflow_dsl,
)
from app.successor_runtime.capabilities.workflow_common import (
    normalize_workflow_json_object,
    normalize_workflow_json_value,
    try_normalize_workflow_json_value,
    WorkflowDefinitionFailureCode,
)


class WorkflowGraphCompilerUnitTestCase(unittest.TestCase):
    def _build_valid_payload(self) -> dict:
        return {
            "version": "1.0",
            "options": {"strict": True},
            "nodes": [
                {"node_id": "n1", "node_type": "vector_search"},
                {"node_id": "n2", "node_type": "llm_call"},
                {"node_id": "n3", "node_type": "join"},
            ],
            "edges": [
                {"from": "n1", "to": "n2"},
                {"from": "n2", "to": "n3"},
            ],
        }

    def test_compile_success_outputs_topology_edge_maps_and_checksum(self):
        payload = self._build_valid_payload()

        compiled = compile_workflow_graph(payload)

        self.assertEqual(compiled.version, "1.0")
        self.assertEqual(compiled.options, {"strict": True})
        self.assertEqual(compiled.topo_order, ("n1", "n2", "n3"))
        self.assertEqual(compiled.outgoing_edges, {"n1": ("n2",), "n2": ("n3",), "n3": ()})
        self.assertEqual(compiled.incoming_edges, {"n1": (), "n2": ("n1",), "n3": ("n2",)})
        self.assertEqual(len(compiled.checksum), 64)

        compiled_again = compile_workflow_graph(payload)
        self.assertEqual(compiled.checksum, compiled_again.checksum)

    def test_compile_accepts_curated_edge_endpoint_projection(self):
        payload = self._build_valid_payload()
        payload["edges"] = [
            {
                "from_node_id": "n1",
                "to_node_id": "n2",
                "from": {"id": "n1", "type": "vector_search"},
                "to": {"id": "n2", "type": "llm_call"},
            },
            {
                "from_node_id": "n2",
                "to_node_id": "n3",
                "from": {"id": "n2", "type": "llm_call"},
                "to": {"id": "n3", "type": "join"},
            },
        ]

        compiled = compile_workflow_graph(payload)

        self.assertEqual(compiled.topo_order, ("n1", "n2", "n3"))
        self.assertEqual(compiled.outgoing_edges, {"n1": ("n2",), "n2": ("n3",), "n3": ()})

    def test_compile_raises_on_duplicate_node_id(self):
        payload = self._build_valid_payload()
        payload["nodes"][1]["node_id"] = "n1"

        with self.assertRaisesRegex(WorkflowGraphCompileError, "duplicate node_id"):
            compile_workflow_graph(payload)

    def test_compile_raises_on_missing_node_reference(self):
        payload = self._build_valid_payload()
        payload["edges"].append({"from": "n3", "to": "missing"})

        with self.assertRaisesRegex(WorkflowGraphCompileError, "missing node"):
            compile_workflow_graph(payload)

    def test_compile_raises_on_invalid_node_type(self):
        payload = self._build_valid_payload()
        payload["nodes"][0]["node_type"] = "unknown"

        with self.assertRaisesRegex(WorkflowGraphCompileError, "invalid node_type"):
            compile_workflow_graph(payload)

    def test_compile_raises_on_cycle(self):
        payload = self._build_valid_payload()
        payload["edges"].append({"from": "n3", "to": "n1"})

        with self.assertRaisesRegex(WorkflowGraphCompileError, "contains a cycle"):
            compile_workflow_graph(payload)

    def test_compile_rejects_nested_non_json_values(self):
        payload = self._build_valid_payload()
        payload["nodes"][0]["config"] = {"threshold": float("nan")}

        with self.assertRaisesRegex(WorkflowGraphCompileError, "non-finite"):
            compile_workflow_graph(payload)

        payload = self._build_valid_payload()
        payload["nodes"][0]["config"] = {1: "not-a-json-key"}
        with self.assertRaisesRegex(WorkflowGraphCompileError, "keys must be strings"):
            compile_workflow_graph(payload)

    def test_successor_parser_rejects_nested_non_json_values(self):
        payload = self._build_valid_payload()
        payload["options"] = {"callback": object()}

        receipt = parse_and_validate_workflow_dsl(payload)

        self.assertFalse(receipt.ok)
        self.assertIsNotNone(receipt.failure)
        self.assertEqual(receipt.failure.code, "WORKFLOW_DSL_MALFORMED_PAYLOAD")
        self.assertIn("non-JSON value", receipt.failure.message)

    def test_workflow_json_normalizer_uses_typed_failure_lift_for_public_type_error(self):
        failure = try_normalize_workflow_json_value(
            {"nested": float("inf")},
            path="payload",
        )
        self.assertIsInstance(failure, Failure)
        assert isinstance(failure, Failure)
        self.assertEqual(failure.family, "workflow.definition.failure")
        self.assertEqual(failure.code, "WORKFLOW_DSL_MALFORMED_PAYLOAD")
        self.assertEqual(failure.context["public_exception"], "TypeError")
        self.assertEqual(failure.context["site"], "payload.nested")

        cases = (
            (
                normalize_workflow_json_value,
                {"nested": float("inf")},
                "payload.nested contains a non-finite JSON number",
            ),
            (
                normalize_workflow_json_value,
                {1: "bad-key"},
                "payload contains a non-string JSON object key",
            ),
            (
                normalize_workflow_json_value,
                object(),
                "payload contains a non-JSON value of type object",
            ),
            (
                normalize_workflow_json_object,
                ["not-an-object"],
                "payload must be a JSON object",
            ),
        )
        for normalize, value, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(TypeError, f"^{message}$"):
                    normalize(value, path="payload")

    def test_workflow_failure_family_contains_only_failure_taxonomy(self):
        self.assertEqual(
            set(get_args(WorkflowDefinitionFailureCode)),
            {
                "WORKFLOW_ACCEPTANCE_DIGEST_INVALID",
                "WORKFLOW_ACCEPTANCE_INPUT_INVALID",
                "WORKFLOW_CONTRACT_KIND_UNSUPPORTED",
                "WORKFLOW_DSL_COMPILE_FAILURE",
                "WORKFLOW_DSL_CYCLE",
                "WORKFLOW_DSL_DUPLICATE_NODE_ID",
                "WORKFLOW_DSL_MALFORMED_PAYLOAD",
                "WORKFLOW_DSL_MISSING_ENDPOINT",
                "WORKFLOW_DSL_UNSUPPORTED_NODE_TYPE",
                "WORKFLOW_OBSERVATION_SHAPE_INVALID",
                "WORKFLOW_PROGRAM_PLAN_BINDING_INVALID",
                "WORKFLOW_RECEIPT_CONTRACT_INVALID",
                "WORKFLOW_ROLLBACK_BINDING_INVALID",
                "WORKFLOW_SLICE_SHAPE_INVALID",
            },
        )

    def test_compiler_service_persists_and_reloads_compiled_graph(self):
        durable_store = InMemoryCompiledGraphStore()
        first_service = WorkflowGraphCompilerService(store=durable_store)

        response = first_service.compile({"dsl": self._build_valid_payload(), "graph_id": "graph-durable"})
        self.assertEqual(response["graph_id"], "graph-durable")

        reloaded_service = WorkflowGraphCompilerService(store=durable_store)
        compiled = reloaded_service.get_compiled("graph-durable")
        self.assertEqual(compiled["graph_id"], "graph-durable")
        self.assertEqual(compiled["topo_order"], ["n1", "n2", "n3"])
        self.assertEqual(compiled["checksum"], response["checksum"])

    def test_compiler_service_lowers_and_binds_exact_platform_plan(self):
        payload = self._build_valid_payload()
        receipt = parse_and_validate_workflow_dsl(payload)
        self.assertTrue(receipt.ok)

        service = WorkflowGraphCompilerService(store=InMemoryCompiledGraphStore())
        response = service.compile({"dsl": payload, "graph_id": "graph-platform"})
        compiled = service.get_compiled("graph-platform")

        self.assertEqual(response["program_digest"], receipt.program_digest)
        self.assertEqual(response["plan_digest"], receipt.plan_digest)
        self.assertEqual(response["catalog_digest"], receipt.catalog_digest)
        self.assertEqual(compiled["platform"], {
            "program_digest": receipt.program_digest,
            "plan_digest": receipt.plan_digest,
            "catalog_digest": receipt.catalog_digest,
        })
        self.assertEqual(list(receipt.topo_order), compiled["topo_order"])

    def test_save_failure_is_not_masked_by_service_memory(self):
        store = MagicMock(spec=InMemoryCompiledGraphStore)
        store.save_compiled.side_effect = RuntimeError("compiled store save failed")
        store.get_compiled.side_effect = KeyError("compiled graph not found")
        service = WorkflowGraphCompilerService(store=store)

        with self.assertRaisesRegex(RuntimeError, "compiled store save failed"):
            service.compile({"dsl": self._build_valid_payload(), "graph_id": "graph-save-failed"})

        store.save_compiled.assert_called_once()
        store.get_compiled.assert_not_called()
        with self.assertRaisesRegex(KeyError, "compiled graph not found"):
            service.get_compiled("graph-save-failed")
        store.get_compiled.assert_called_once_with("graph-save-failed")

    def test_get_failure_propagates_without_local_copy(self):
        store = MagicMock(spec=InMemoryCompiledGraphStore)
        store.get_compiled.side_effect = RuntimeError("compiled store read failed")
        service = WorkflowGraphCompilerService(store=store)

        with self.assertRaisesRegex(RuntimeError, "compiled store read failed"):
            service.get_compiled("graph-read-failed")

        store.get_compiled.assert_called_once_with("graph-read-failed")

    def test_list_failure_propagates_without_merged_values(self):
        store = MagicMock(spec=InMemoryCompiledGraphStore)
        store.list_compiled.side_effect = RuntimeError("compiled store list failed")
        service = WorkflowGraphCompilerService(store=store)

        with self.assertRaisesRegex(RuntimeError, "compiled store list failed"):
            service.list_compiled(limit=7)

        store.list_compiled.assert_called_once_with(limit=7)

    def test_compiler_service_has_no_private_facts_cache(self):
        source = inspect.getsource(WorkflowGraphCompilerService)

        self.assertNotIn("self._compiled", source)


if __name__ == "__main__":
    unittest.main()
