from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.graph.models import Graph, GraphEdge, GraphNode
from app.services.graph.mapping import normalize_canonical_node_id, normalize_node_id
from app.services.graph.persistence.graph_node_alias_resolver import GraphNodeAliasResolver
from app.services.graph.persistence.graph_node_writer import GraphNodeWriter
from app.services.graph.persistence.graph_projection_contract import (
    build_graph_projection_dry_run,
    build_graph_projection_rollout_readiness,
)


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

    def test_projection_writer_casefolds_storage_canonical_id_without_changing_interface_id(self):
        self.assertEqual(normalize_node_id(" ACME\u200b Corp "), "ACME Corp")
        self.assertEqual(normalize_canonical_node_id(" ACME\u200b Corp "), "acme corp")

        session = _FakeSession()
        writer = GraphNodeWriter(session, schema_version="v1")
        graph = Graph(
            nodes={
                "Entity:ACME": GraphNode(
                    type="Entity",
                    id=" ACME\u200b Corp ",
                    properties={"name": "ACME Corp"},
                )
            },
            edges=[],
            schema_version="v1",
        )
        captured_payloads: list[dict] = []

        def _capture_payload(payload: dict):
            captured_payloads.append(payload)
            return 42

        with patch.object(writer, "_upsert_node", side_effect=_capture_payload), patch.object(
            writer,
            "_upsert_aliases",
            return_value=0,
        ), patch.object(writer, "_upsert_edges", return_value=0):
            summary = writer.persist_graph_nodes(graph)

        self.assertEqual(summary.attempted, 1)
        self.assertEqual(summary.inserted_or_updated, 1)
        self.assertEqual(captured_payloads[0]["canonical_id"], "acme corp")
        self.assertEqual(captured_payloads[0]["id"], "acme corp")

    def test_projection_dry_run_resolves_canonical_edge_endpoints_without_db(self):
        post = GraphNode(type="Post", id=" 42 ", properties={"title": "Projection Fixture"})
        entity_upper = GraphNode(type="Entity", id=" ACME\u200b Corp ", properties={"name": "ACME Corp"})
        entity_lower = GraphNode(type="Entity", id="acme corp", properties={"name": "duplicate"})
        keyword = GraphNode(type="Keyword", id=" Lottery   AI ", properties={"label": "Lottery AI"})
        graph = Graph(
            nodes={
                "Post:raw-42": post,
                "Entity:upper": entity_upper,
                "Entity:lower": entity_lower,
                "Keyword:lottery-ai": keyword,
            },
            edges=[
                GraphEdge(
                    type="MENTIONS_ENTITY",
                    from_node=GraphNode(type="Post", id="42"),
                    to_node=entity_upper,
                    properties={},
                ),
                GraphEdge(
                    type="MENTIONS_KEYWORD",
                    from_node=post,
                    to_node=GraphNode(type="Keyword", id="Lottery AI"),
                    properties={},
                ),
            ],
            schema_version="v1",
        )

        report = build_graph_projection_dry_run(graph)

        self.assertFalse(report.live_db_validated)
        self.assertEqual(report.attempted_node_count, 4)
        self.assertEqual(report.unique_node_count, 3)
        self.assertEqual(report.duplicate_node_attempts, 1)
        self.assertEqual({node.key for node in report.nodes}, {"Post:42", "Entity:acme corp", "Keyword:lottery ai"})
        self.assertEqual(report.writeable_edge_count, 2)
        self.assertEqual(report.unresolved_edge_count, 0)
        self.assertEqual(
            {(edge.edge_type, edge.from_key, edge.to_key) for edge in report.edges},
            {
                ("MENTIONS_ENTITY", "Post:42", "Entity:acme corp"),
                ("MENTIONS_KEYWORD", "Post:42", "Keyword:lottery ai"),
            },
        )

    def test_projection_dry_run_marks_missing_edge_endpoint_as_rollout_signal(self):
        post = GraphNode(type="Post", id="1", properties={})
        missing = GraphNode(type="Entity", id="missing", properties={})
        graph = Graph(
            nodes={"Post:1": post},
            edges=[GraphEdge(type="MENTIONS_ENTITY", from_node=post, to_node=missing, properties={})],
            schema_version="v1",
        )

        report = build_graph_projection_dry_run(graph)

        self.assertEqual(report.writeable_edge_count, 0)
        self.assertEqual(report.unresolved_edge_count, 1)
        self.assertEqual(report.edges[0].skip_reason, "missing_to_endpoint")
        self.assertIn("b_primary read-mode parity", " ".join(report.live_db_gap))

    def test_projection_rollout_readiness_allows_bounded_pre_live_dry_run_only(self):
        report = build_graph_projection_rollout_readiness(
            read_mode="b_canary",
            write_mode="shadow",
            canary_projects=["demo_proj"],
            backfill_dry_run=True,
            backfill_limit=10,
            migration_checks={
                "graph_nodes_table": True,
                "graph_node_aliases_table": True,
                "graph_edges_table": True,
                "edge_depends_on_node_migration": True,
            },
            failure_isolation_checks={
                "admin_shadow_write_rollback_and_continue": True,
                "admin_b_read_fallback_to_a": True,
                "backfill_apply_rollback_on_failure": True,
            },
        )

        self.assertTrue(report.ready_for_live_db_dry_run)
        self.assertFalse(report.live_db_validated)
        self.assertFalse(report.closure_claim)
        self.assertIn("backfill_graph_nodes.py --dry-run", " ".join(report.live_db_gap))

    def test_projection_rollout_readiness_blocks_b_primary_apply_before_live_db(self):
        report = build_graph_projection_rollout_readiness(
            read_mode="b_primary",
            write_mode="on",
            canary_projects=[],
            backfill_dry_run=False,
            backfill_limit=None,
            migration_checks={
                "graph_nodes_table": True,
                "graph_node_aliases_table": True,
                "graph_edges_table": True,
                "edge_depends_on_node_migration": True,
            },
            failure_isolation_checks={
                "admin_shadow_write_rollback_and_continue": True,
                "admin_b_read_fallback_to_a": True,
                "backfill_apply_rollback_on_failure": True,
            },
        )

        self.assertFalse(report.ready_for_live_db_dry_run)
        failed = {check.name for check in report.checks if not check.passed}
        self.assertIn("read_mode_pre_live_safe", failed)
        self.assertIn("write_mode_pre_live_safe", failed)
        self.assertIn("backfill_dry_run_required", failed)
        self.assertIn("backfill_limit_bounded", failed)


if __name__ == "__main__":
    unittest.main()
