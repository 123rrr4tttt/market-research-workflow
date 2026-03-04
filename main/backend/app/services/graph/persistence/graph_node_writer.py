from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ....models.entities import GraphEdgeRecord, GraphNodeAliasRecord, GraphNodeRecord
from ....services.projects import current_project_key
from ..mapping import normalize_node_id, normalize_node_properties, normalize_node_type
from ..models import Graph
from .graph_node_alias_resolver import GraphNodeAliasResolver


@dataclass
class GraphWriteSummary:
    attempted: int = 0
    inserted_or_updated: int = 0
    aliases_written: int = 0
    edges_written: int = 0
    skipped: int = 0


class GraphNodeWriter:
    def __init__(self, session: Session, *, schema_version: str = "v1", project_key: str | None = None):
        self.session = session
        self.schema_version = schema_version or "v1"
        self.project_key = str(project_key or current_project_key() or "default").strip() or "default"
        self.alias_resolver = GraphNodeAliasResolver()

    @staticmethod
    def _display_name(properties: dict[str, Any]) -> str | None:
        for key in ("label", "name", "text", "canonical_name", "title"):
            value = str(properties.get(key) or "").strip()
            if value:
                return value
        return None

    @staticmethod
    def _source_doc_id(node_type: str, node_id: str) -> int | None:
        if node_type not in {"Post", "MarketData", "Policy"}:
            return None
        if not node_id.isdigit():
            return None
        return int(node_id)

    def _upsert_node(self, payload: dict[str, Any]) -> int | None:
        stmt = pg_insert(GraphNodeRecord.__table__).values(
            project_key=self.project_key,
            node_type=payload["node_type"],
            canonical_id=payload["canonical_id"],
            display_name=payload.get("display_name"),
            properties=payload.get("properties") or {},
            source_doc_id=payload.get("source_doc_id"),
            node_schema_version=payload.get("node_schema_version") or self.schema_version,
            quality_flags=payload.get("quality_flags"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["project_key", "node_type", "canonical_id"],
            set_={
                "display_name": stmt.excluded.display_name,
                "properties": stmt.excluded.properties,
                "source_doc_id": stmt.excluded.source_doc_id,
                "node_schema_version": stmt.excluded.node_schema_version,
                "quality_flags": stmt.excluded.quality_flags,
                "updated_at": func.now(),
            },
        ).returning(GraphNodeRecord.__table__.c.id)

        row = self.session.execute(stmt).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def _upsert_aliases(self, node_id: int, node_payload: dict[str, Any]) -> int:
        count = 0
        aliases = sorted(
            self.alias_resolver.resolve(node_payload),
            key=lambda item: (item.alias_type, item.alias_norm),
        )
        for alias in aliases:
            stmt = pg_insert(GraphNodeAliasRecord.__table__).values(
                project_key=self.project_key,
                node_id=node_id,
                alias_text=alias.alias_text,
                alias_norm=alias.alias_norm,
                alias_type=alias.alias_type,
            )
            # Keep alias mapping first-wins in shadow mode to avoid concurrent UPDATE deadlocks.
            stmt = stmt.on_conflict_do_nothing(index_elements=["project_key", "alias_norm", "alias_type"])
            self.session.execute(stmt)
            count += 1
        return count

    @staticmethod
    def _normalize_edge_type(edge_type: Any) -> str:
        text = str(edge_type or "").strip()
        return text or "RELATED_TO"

    def _resolve_node_record_id(self, node_type: str, canonical_id: str) -> int | None:
        row = self.session.execute(
            select(GraphNodeRecord.id).where(
                GraphNodeRecord.project_key == self.project_key,
                GraphNodeRecord.node_type == node_type,
                GraphNodeRecord.canonical_id == canonical_id,
            )
        ).fetchone()
        if not row:
            return None
        return int(row[0]) if row[0] is not None else None

    def _upsert_edges(self, graph: Graph, node_id_map: dict[str, int]) -> int:
        count = 0
        edge_rows: list[tuple[str, int, int, dict[str, Any]]] = []
        for edge in graph.edges:
            from_type = normalize_node_type(edge.from_node.type)
            from_id = normalize_node_id(edge.from_node.id)
            to_type = normalize_node_type(edge.to_node.type)
            to_id = normalize_node_id(edge.to_node.id)
            if not from_type or not from_id or not to_type or not to_id:
                continue
            from_key = f"{from_type}:{from_id}"
            to_key = f"{to_type}:{to_id}"
            from_node_id = node_id_map.get(from_key) or self._resolve_node_record_id(from_type, from_id)
            to_node_id = node_id_map.get(to_key) or self._resolve_node_record_id(to_type, to_id)
            if not from_node_id or not to_node_id:
                continue
            edge_rows.append(
                (
                    self._normalize_edge_type(edge.type),
                    int(from_node_id),
                    int(to_node_id),
                    normalize_node_properties(edge.properties if isinstance(edge.properties, dict) else {}),
                )
            )

        edge_rows = sorted(edge_rows, key=lambda item: (item[0], item[1], item[2]))
        for edge_type, from_node_id, to_node_id, properties in edge_rows:
            stmt = pg_insert(GraphEdgeRecord.__table__).values(
                project_key=self.project_key,
                edge_type=edge_type,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                properties=properties,
                edge_schema_version=self.schema_version,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["project_key", "edge_type", "from_node_id", "to_node_id"],
                set_={
                    "properties": stmt.excluded.properties,
                    "edge_schema_version": stmt.excluded.edge_schema_version,
                    "updated_at": func.now(),
                },
            )
            self.session.execute(stmt)
            count += 1
        return count

    def persist_graph_nodes(self, graph: Graph) -> GraphWriteSummary:
        summary = GraphWriteSummary()
        node_id_map: dict[str, int] = {}
        for node in graph.nodes.values():
            summary.attempted += 1
            node_type = normalize_node_type(node.type)
            canonical_id = normalize_node_id(node.id)
            if not node_type or not canonical_id:
                summary.skipped += 1
                continue
            props = normalize_node_properties(node.properties)
            payload = {
                "node_type": node_type,
                "canonical_id": canonical_id,
                "display_name": self._display_name(props),
                "properties": props,
                "source_doc_id": self._source_doc_id(node_type, canonical_id),
                "node_schema_version": self.schema_version,
                "quality_flags": {},
                "id": canonical_id,
            }
            record_id = self._upsert_node(payload)
            if record_id is None:
                summary.skipped += 1
                continue
            node_id_map[f"{node_type}:{canonical_id}"] = int(record_id)
            summary.inserted_or_updated += 1
            summary.aliases_written += self._upsert_aliases(record_id, payload | props)
        summary.edges_written = self._upsert_edges(graph, node_id_map)

        return summary
