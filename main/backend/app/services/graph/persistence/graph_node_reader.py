from __future__ import annotations

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ....models.entities import GraphEdgeRecord, GraphNodeRecord
from ..mapping import normalize_graph_json_object
from ..models import Graph, GraphEdge, GraphNode


def _row_id(value: object) -> int:
    if isinstance(value, int):
        return value
    return int(str(value))


class GraphNodeReader:
    def __init__(self, session: Session):
        self.session = session

    def load_graph(self, *, limit: int = 5000) -> Graph:
        rows = self.session.execute(
            select(GraphNodeRecord).order_by(GraphNodeRecord.updated_at.desc()).limit(limit)
        ).scalars().all()
        graph = Graph(schema_version="v1")
        nodes_by_row_id: dict[int, GraphNode] = {}
        for row in rows:
            node_type = str(row.node_type)
            canonical_id = str(row.canonical_id)
            key = f"{node_type}:{canonical_id}"
            node = GraphNode(
                type=node_type,
                id=canonical_id,
                properties=normalize_graph_json_object(row.properties),
            )
            graph.nodes[key] = node
            nodes_by_row_id[_row_id(row.id)] = node

        if not nodes_by_row_id:
            return graph

        node_ids = list(nodes_by_row_id.keys())
        edge_rows = self.session.execute(
            select(GraphEdgeRecord).where(
                or_(GraphEdgeRecord.from_node_id.in_(node_ids), GraphEdgeRecord.to_node_id.in_(node_ids))
            )
        ).scalars().all()
        for edge_row in edge_rows:
            from_node = nodes_by_row_id.get(_row_id(edge_row.from_node_id))
            to_node = nodes_by_row_id.get(_row_id(edge_row.to_node_id))
            if from_node is None or to_node is None:
                continue
            graph.edges.append(
                GraphEdge(
                    type=str(edge_row.edge_type),
                    from_node=from_node,
                    to_node=to_node,
                    properties=normalize_graph_json_object(edge_row.properties),
                )
            )
        return graph
