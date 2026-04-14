from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.graph.models import Graph, GraphNode
from app.services.graph.persistence.graph_node_alias_resolver import GraphNodeAliasResolver
from app.services.graph.persistence.graph_node_writer import GraphNodeWriter


class _FakeExecResult:
    def __init__(self, row=(1,)):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeSession:
    def __init__(self):
        self.calls = 0

    def execute(self, _stmt):  # noqa: ANN001
        self.calls += 1
        return _FakeExecResult((1,))


class GraphPersistenceWriterUnitTestCase(unittest.TestCase):
    def test_alias_resolver_extracts_display_and_id_aliases(self):
        resolver = GraphNodeAliasResolver()
        aliases = resolver.resolve({"name": " ACME Corp ", "id": "kb:123"})
        norms = {(a.alias_norm, a.alias_type) for a in aliases}
        self.assertIn(("acme corp", "display"), norms)
        self.assertIn(("kb:123", "id"), norms)

    def test_writer_persists_nodes_and_aliases(self):
        session = _FakeSession()
        writer = GraphNodeWriter(session, schema_version="v1")
        graph = Graph(
            nodes={
                "Post:1": GraphNode(type="Post", id="1", properties={"title": "Hello"}),
                "Entity:e1": GraphNode(type="Entity", id="e1", properties={"name": "Acme"}),
            },
            edges=[],
            schema_version="v1",
        )

        summary = writer.persist_graph_nodes(graph)
        self.assertEqual(summary.attempted, 2)
        self.assertEqual(summary.inserted_or_updated, 2)
        self.assertGreaterEqual(summary.aliases_written, 2)
        self.assertEqual(summary.edges_written, 0)
        self.assertEqual(summary.skipped, 0)
        self.assertGreaterEqual(session.calls, 4)


if __name__ == "__main__":
    unittest.main()
