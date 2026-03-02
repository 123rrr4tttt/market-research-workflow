from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.graph.doc_types import resolve_graph_node_combo, resolve_graph_node_ensemble
from app.services.graph.models import Graph, GraphEdge, GraphNode
from app.services.graph.projection import project_graph_by_node_types


class GraphProjectionUnitTestCase(unittest.TestCase):
    def test_project_graph_by_node_types_filters_nodes_and_edges(self):
        post = GraphNode(type="Post", id="1", properties={})
        keyword = GraphNode(type="Keyword", id="k1", properties={})
        entity = GraphNode(type="Entity", id="e1", properties={})
        graph = Graph(
            nodes={
                "Post:1": post,
                "Keyword:k1": keyword,
                "Entity:e1": entity,
            },
            edges=[
                GraphEdge(type="MENTIONS_KEYWORD", from_node=post, to_node=keyword, properties={}),
                GraphEdge(type="MENTIONS_ENTITY", from_node=post, to_node=entity, properties={}),
            ],
            schema_version="v1",
        )

        projected = project_graph_by_node_types(graph, ["Post", "Keyword"])

        self.assertEqual(set(projected.nodes.keys()), {"Post:1", "Keyword:k1"})
        self.assertEqual(len(projected.edges), 1)
        self.assertEqual(projected.edges[0].type, "MENTIONS_KEYWORD")

    def test_project_graph_by_node_types_empty_combo_keeps_original(self):
        node = GraphNode(type="Post", id="1", properties={})
        graph = Graph(nodes={"Post:1": node}, edges=[], schema_version="v1")

        projected = project_graph_by_node_types(graph, [])
        self.assertIs(projected, graph)

    def test_resolve_node_combo_is_subset_of_ensemble(self):
        ensemble = set(resolve_graph_node_ensemble(None))
        social_combo = resolve_graph_node_combo("social", None)
        market_combo = resolve_graph_node_combo("market", None)
        policy_combo = resolve_graph_node_combo("policy", None)

        self.assertTrue(set(social_combo).issubset(ensemble))
        self.assertTrue(set(market_combo).issubset(ensemble))
        self.assertTrue(set(policy_combo).issubset(ensemble))

