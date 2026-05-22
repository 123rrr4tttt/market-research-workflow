from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.graph.models import Graph, GraphEdge, GraphNode
from app.services.graph.persistence.graph_live_smoke_readiness import build_graph_live_smoke_readiness
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


def _ready_rollout():
    return build_graph_projection_rollout_readiness(
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


def _frontend_checks() -> dict[str, bool]:
    return {
        "force3d_contract_script_registered": True,
        "force3d_contract_checker_exists": True,
        "graphpage_backend_data_query_uses_api_wrappers": True,
        "graphpage_force3d_debug_stats_exposed": True,
        "mocked_force3d_e2e_exists": True,
    }


def _backend_checks() -> dict[str, bool]:
    return {
        "admin_backend_data_graph_routes_exist": True,
        "admin_graph_routes_use_failure_isolation_tail": True,
        "frontend_backend_data_endpoints_exist": True,
        "frontend_backend_data_wrappers_exist": True,
    }


class GraphLiveSmokeReadinessUnitTestCase(unittest.TestCase):
    def test_live_db_configured_not_run_keeps_closure_open_and_records_gaps(self):
        report = build_graph_live_smoke_readiness(
            no_db_report=build_graph_projection_dry_run(_fixture_graph()),
            readiness_report=_ready_rollout(),
            database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
            frontend_contract_checks=_frontend_checks(),
            backend_data_contract_checks=_backend_checks(),
        )

        self.assertEqual(report.status, "ok")
        self.assertFalse(report.closure_claim)
        self.assertFalse(report.live_db_validated)
        self.assertFalse(report.frontend_backend_data_smoke_validated)
        stages = {stage.name: stage for stage in report.stages}
        self.assertEqual(stages["no_db_fixture_smoke"].status, "passed")
        self.assertEqual(stages["live_db_backend_data_smoke"].status, "configured_not_run")
        self.assertEqual(stages["frontend_backend_data_visual_smoke"].status, "ready_not_run")
        self.assertIn("live tenant data", " ".join(report.remaining_live_gaps))
        self.assertIn("nonempty data", " ".join(report.remaining_live_gaps))

    def test_frontend_static_failure_isolated_from_no_db_and_live_db_classification(self):
        frontend_checks = _frontend_checks()
        frontend_checks["graphpage_force3d_debug_stats_exposed"] = False

        report = build_graph_live_smoke_readiness(
            no_db_report=build_graph_projection_dry_run(_fixture_graph()),
            readiness_report=_ready_rollout(),
            database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
            frontend_contract_checks=frontend_checks,
            backend_data_contract_checks=_backend_checks(),
        )

        self.assertEqual(report.status, "failed")
        stages = {stage.name: stage for stage in report.stages}
        self.assertEqual(stages["no_db_fixture_smoke"].status, "passed")
        self.assertEqual(stages["live_db_backend_data_smoke"].status, "configured_not_run")
        self.assertEqual(stages["frontend_backend_data_visual_smoke"].status, "blocked")
        self.assertIn("frontend:graphpage_force3d_debug_stats_exposed", stages["frontend_backend_data_visual_smoke"].detail)

    def test_incomplete_live_evidence_does_not_mark_live_db_validated(self):
        report = build_graph_live_smoke_readiness(
            no_db_report=build_graph_projection_dry_run(_fixture_graph()),
            readiness_report=_ready_rollout(),
            database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
            frontend_contract_checks=_frontend_checks(),
            backend_data_contract_checks=_backend_checks(),
            live_db_evidence={"live_db_validated": True},
        )

        self.assertEqual(report.status, "failed")
        self.assertFalse(report.live_db_validated)
        stages = {stage.name: stage for stage in report.stages}
        self.assertEqual(stages["live_db_backend_data_smoke"].status, "failed_evidence")
        self.assertIn("backfill_graph_nodes_dry_run", stages["live_db_backend_data_smoke"].detail)
        self.assertIn("do not promote graph_node_projection_read_mode=b_primary", " ".join(report.remaining_live_gaps))

    def test_complete_live_evidence_validates_smokes_but_still_does_not_claim_closure(self):
        report = build_graph_live_smoke_readiness(
            no_db_report=build_graph_projection_dry_run(_fixture_graph()),
            readiness_report=_ready_rollout(),
            database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
            frontend_contract_checks=_frontend_checks(),
            backend_data_contract_checks=_backend_checks(),
            live_db_evidence={
                "live_db_validated": True,
                "alembic_current_or_upgrade_run": True,
                "backfill_graph_nodes_dry_run": True,
                "backend_data_graph_endpoint_smoke": True,
                "b_read_parity_checked": True,
            },
            frontend_backend_evidence={
                "frontend_backend_data_smoke_validated": True,
                "backend_data_source_live": True,
                "force3d_canvas_nonblank": True,
                "force3d_scene_nodes_match_data": True,
            },
        )

        self.assertEqual(report.status, "ok")
        self.assertTrue(report.live_db_validated)
        self.assertTrue(report.frontend_backend_data_smoke_validated)
        self.assertFalse(report.closure_claim)
        self.assertEqual(report.remaining_live_gaps, [])


if __name__ == "__main__":
    unittest.main()
