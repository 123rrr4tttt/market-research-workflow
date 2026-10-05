from __future__ import annotations

import inspect
import unittest
from unittest.mock import MagicMock

from app.services.workflow_graph import WorkflowGraphCompilerService
from app.services.workflow_graph.compiler import compile_workflow_graph
from app.services.workflow_graph.contracts import WorkflowGraphCompileError
from app.services.workflow_graph.store import InMemoryCompiledGraphStore
from app.successor_runtime.capabilities.workflow_legacy_dsl import (
    parse_and_validate_workflow_dsl,
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
