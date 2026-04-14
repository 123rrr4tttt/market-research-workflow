from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.graph.exporter import export_to_json
from app.services.graph.models import Graph, GraphEdge, GraphNode


class GraphExporterInterfaceUnitTestCase(unittest.TestCase):
    def test_export_to_json_keeps_interface_shape(self):
        post = GraphNode(type=" Post ", id=" p-1 ", properties={"title": "hello", "type": "reserved"})
        keyword = GraphNode(type="Keyword", id="k-1", properties={"text": "lottery"})
        graph = Graph(
            nodes={
                "Post:p-1": post,
                "Keyword:k-1": keyword,
            },
            edges=[
                GraphEdge(
                    type="MENTIONS_KEYWORD",
                    from_node=post,
                    to_node=keyword,
                    properties={"weight": 1.0},
                )
            ],
            schema_version="v1",
        )

        payload = export_to_json(graph)

        self.assertEqual(set(payload.keys()), {"graph_schema_version", "nodes", "edges"})
        self.assertEqual(payload["graph_schema_version"], "v1")
        self.assertEqual(len(payload["nodes"]), 2)
        self.assertEqual(len(payload["edges"]), 1)

        post_node = payload["nodes"][0]
        self.assertEqual(post_node["type"], "Post")
        self.assertEqual(post_node["id"], "p-1")
        self.assertEqual(post_node["title"], "hello")
        self.assertNotIn("type ", post_node)

        edge = payload["edges"][0]
        self.assertEqual(edge["type"], "MENTIONS_KEYWORD")
        self.assertEqual(edge["from"], {"type": "Post", "id": "p-1"})
        self.assertEqual(edge["to"], {"type": "Keyword", "id": "k-1"})
        self.assertEqual(edge["weight"], 1.0)

    def test_export_to_json_uses_default_schema_version_when_empty(self):
        node = GraphNode(type="Entity", id="e-1", properties={})
        graph = Graph(nodes={"Entity:e-1": node}, edges=[], schema_version="")

        payload = export_to_json(graph)

        self.assertEqual(payload["graph_schema_version"], "v1")

