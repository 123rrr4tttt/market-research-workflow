from __future__ import annotations

import unittest

from app.services.workflow_graph import WorkflowGraphCompilerService
from app.services.workflow_graph.compiler import compile_workflow_graph
from app.services.workflow_graph.contracts import WorkflowGraphCompileError
from app.services.workflow_graph.store import InMemoryCompiledGraphStore


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


if __name__ == "__main__":
    unittest.main()
