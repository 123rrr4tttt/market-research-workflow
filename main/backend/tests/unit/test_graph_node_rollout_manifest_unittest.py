from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.graph.models import Graph, GraphEdge, GraphNode
from app.services.graph.persistence.graph_node_live_db_rollout_gate import build_graph_node_live_db_rollout_gate
from app.services.graph.persistence.graph_node_rollout_manifest import build_graph_node_rollout_manifest
from app.services.graph.persistence.graph_projection_contract import (
    build_graph_projection_dry_run,
    build_graph_projection_rollout_readiness,
)


def _fixture_graph() -> Graph:
    post = GraphNode(type="Post", id=" 42 ", properties={"title": "Projection Fixture"})
    entity_upper = GraphNode(type="Entity", id=" ACME\u200b Corp ", properties={"name": "ACME Corp"})
    entity_lower = GraphNode(type="Entity", id="acme corp", properties={"name": "acme corp duplicate"})
    return Graph(
        nodes={
            "Post:raw-42": post,
            "Entity:upper": entity_upper,
            "Entity:lower": entity_lower,
        },
        edges=[
            GraphEdge(
                type="MENTIONS_ENTITY",
                from_node=GraphNode(type="Post", id="42"),
                to_node=entity_upper,
                properties={},
            )
        ],
        schema_version="v1",
    )


def _readiness(*, read_mode: str = "b_canary", backfill_dry_run: bool = True):
    return build_graph_projection_rollout_readiness(
        read_mode=read_mode,
        write_mode="shadow",
        canary_projects=["demo_proj"],
        backfill_dry_run=backfill_dry_run,
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


def _manifest(*, readiness=None, live_db_evidence=None):
    no_db_report = build_graph_projection_dry_run(_fixture_graph())
    readiness_report = readiness or _readiness()
    gate_report = build_graph_node_live_db_rollout_gate(
        no_db_report=no_db_report,
        readiness_report=readiness_report,
        database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
        live_db_evidence=live_db_evidence,
    )
    return build_graph_node_rollout_manifest(
        no_db_report=no_db_report,
        readiness_report=readiness_report,
        gate_report=gate_report,
        source_docs=[
            "wave7",
            "wave10",
            "wave14",
        ],
    )


class GraphNodeRolloutManifestUnitTestCase(unittest.TestCase):
    def test_manifest_readback_is_deterministic_without_live_db_closure_claim(self):
        first = _manifest()
        second = _manifest()

        self.assertEqual(first.status, "ok")
        self.assertEqual(first.manifest_digest, second.manifest_digest)
        self.assertTrue(first.deterministic_readback)
        self.assertFalse(first.live_db_validated)
        self.assertFalse(first.live_db_closure_ready)
        self.assertFalse(first.closure_claim)
        self.assertEqual(
            [stage.name for stage in first.stages],
            [
                "wave7_canonical_id_fixture",
                "wave10_pre_live_db_dry_run_readiness",
                "wave14_live_db_rollout_gate",
            ],
        )
        self.assertEqual([stage.closure_claim for stage in first.stages], [False, False, False])
        self.assertIn("provide live DB evidence", " ".join(first.remaining_live_db_gaps))

    def test_manifest_fails_when_pre_live_readiness_is_blocked(self):
        report = _manifest(readiness=_readiness(read_mode="b_primary", backfill_dry_run=False))

        self.assertEqual(report.status, "failed")
        self.assertTrue(report.deterministic_readback)
        stages = {stage.name: stage for stage in report.stages}
        self.assertEqual(stages["wave10_pre_live_db_dry_run_readiness"].status, "failed")
        self.assertIn(
            "read_mode_pre_live_safe",
            stages["wave10_pre_live_db_dry_run_readiness"].evidence["failed_checks"],
        )

    def test_manifest_accepts_complete_live_evidence_but_still_leaves_doc_closure_false(self):
        report = _manifest(
            live_db_evidence={
                "live_db_validated": True,
                "alembic_current_or_upgrade_run": True,
                "backfill_graph_nodes_dry_run": True,
                "backend_data_graph_endpoint_smoke": True,
                "b_read_parity_checked": True,
            }
        )

        self.assertEqual(report.status, "ok")
        self.assertTrue(report.live_db_validated)
        self.assertTrue(report.live_db_closure_ready)
        self.assertFalse(report.closure_claim)
        self.assertEqual(report.remaining_live_db_gaps, [])


if __name__ == "__main__":
    unittest.main()
