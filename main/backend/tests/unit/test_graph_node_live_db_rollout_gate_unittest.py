from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.graph.models import Graph, GraphEdge, GraphNode
from app.services.graph.persistence.graph_node_live_db_rollout_gate import build_graph_node_live_db_rollout_gate
from app.services.graph.persistence.graph_projection_contract import (
    build_graph_projection_dry_run,
    build_graph_projection_rollout_readiness,
)


def _fixture_graph() -> Graph:
    post = GraphNode(type="Post", id="42", properties={"title": "Projection Fixture"})
    entity = GraphNode(type="Entity", id="ACME Corp", properties={"name": "ACME Corp"})
    return Graph(
        nodes={
            "Post:42": post,
            "Entity:acme": entity,
        },
        edges=[
            GraphEdge(
                type="MENTIONS_ENTITY",
                from_node=post,
                to_node=entity,
                properties={},
            )
        ],
        schema_version="v1",
    )


def _rollout(
    *,
    read_mode: str = "b_canary",
    write_mode: str = "shadow",
    canary_projects: list[str] | None = None,
    backfill_dry_run: bool = True,
    backfill_limit: int | None = 10,
):
    return build_graph_projection_rollout_readiness(
        read_mode=read_mode,
        write_mode=write_mode,
        canary_projects=canary_projects if canary_projects is not None else ["demo_proj"],
        backfill_dry_run=backfill_dry_run,
        backfill_limit=backfill_limit,
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


def _complete_live_db_evidence() -> dict[str, bool]:
    return {
        "live_db_validated": True,
        "alembic_current_or_upgrade_run": True,
        "backfill_graph_nodes_dry_run": True,
        "backend_data_graph_endpoint_smoke": True,
        "b_read_parity_checked": True,
    }


class GraphNodeLiveDbRolloutGateUnitTestCase(unittest.TestCase):
    def test_dry_run_ready_keeps_live_db_open_without_closure_claim(self):
        report = build_graph_node_live_db_rollout_gate(
            no_db_report=build_graph_projection_dry_run(_fixture_graph()),
            readiness_report=_rollout(),
            database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
        )

        self.assertEqual(report.status, "ok")
        self.assertEqual(report.closure_state, "dry_run_ready_live_db_not_validated")
        self.assertTrue(report.dry_run_ready)
        self.assertTrue(report.read_mode_dry_run_safe)
        self.assertTrue(report.backfill_dry_run_ready)
        self.assertFalse(report.live_db_validated)
        self.assertFalse(report.live_db_closure_ready)
        self.assertFalse(report.closure_claim)
        self.assertIn("scripts/backfill_graph_nodes.py --dry-run", " ".join(report.remaining_live_db_gaps))

    def test_b_primary_apply_is_blocked_without_live_db_evidence(self):
        report = build_graph_node_live_db_rollout_gate(
            no_db_report=build_graph_projection_dry_run(_fixture_graph()),
            readiness_report=_rollout(
                read_mode="b_primary",
                write_mode="on",
                canary_projects=[],
                backfill_dry_run=False,
                backfill_limit=None,
            ),
            database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
        )

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.closure_state, "dry_run_blocked_live_db_not_validated")
        self.assertFalse(report.dry_run_ready)
        self.assertFalse(report.read_mode_dry_run_safe)
        self.assertFalse(report.backfill_dry_run_ready)
        failed = {check.name for check in report.checks if not check.passed}
        self.assertIn("read_mode_pre_live_safe", failed)
        self.assertIn("write_mode_pre_live_safe", failed)
        self.assertIn("backfill_dry_run_required", failed)

    def test_incomplete_live_db_evidence_fails_instead_of_validating(self):
        report = build_graph_node_live_db_rollout_gate(
            no_db_report=build_graph_projection_dry_run(_fixture_graph()),
            readiness_report=_rollout(),
            database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
            live_db_evidence={"live_db_validated": True},
        )

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.closure_state, "live_db_evidence_incomplete")
        self.assertFalse(report.live_db_validated)
        self.assertIn("backfill_graph_nodes_dry_run", report.missing_live_db_evidence)
        failed = {check.name for check in report.checks if not check.passed}
        self.assertIn("live_db_closure_evidence", failed)

    def test_complete_live_db_evidence_validates_live_status_but_not_doc_closure_claim(self):
        report = build_graph_node_live_db_rollout_gate(
            no_db_report=build_graph_projection_dry_run(_fixture_graph()),
            readiness_report=_rollout(
                read_mode="b_primary",
                write_mode="on",
                canary_projects=[],
                backfill_dry_run=False,
                backfill_limit=None,
            ),
            database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
            live_db_evidence=_complete_live_db_evidence(),
        )

        self.assertEqual(report.status, "ok")
        self.assertEqual(report.closure_state, "live_db_validated_ready_for_closure_review")
        self.assertFalse(report.dry_run_ready)
        self.assertTrue(report.live_db_validated)
        self.assertTrue(report.live_db_closure_ready)
        self.assertFalse(report.closure_claim)
        self.assertEqual(report.remaining_live_db_gaps, [])


if __name__ == "__main__":
    unittest.main()
