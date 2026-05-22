from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.check_graph_rollout_readback_gate import (  # noqa: E402
    STAGE_ORDER,
    build_gate_snapshot,
    validate_gate_snapshot,
)


pytestmark = pytest.mark.unit


def _passing_migration_checks() -> dict[str, bool]:
    return {
        "graph_nodes_table": True,
        "graph_node_aliases_table": True,
        "graph_edges_table": True,
        "edge_depends_on_node_migration": True,
    }


def _passing_failure_isolation_checks() -> dict[str, bool]:
    return {
        "admin_shadow_write_rollback_and_continue": True,
        "admin_b_read_fallback_to_a": True,
        "backfill_apply_rollback_on_failure": True,
    }


def _passing_force3d_rollback_checks() -> dict[str, bool]:
    return {
        "force3d_load_and_render_fallback_to_legacy": True,
        "force3d_manual_engine_switch_available": True,
        "force3d_switch_readback_covered_by_mocked_e2e": True,
        "runtime_pixel_gate_has_fallback_data_framing": True,
    }


class GraphRolloutReadbackGateUnitTest(unittest.TestCase):
    def test_default_gate_is_deterministic_pre_live_and_non_closing(self) -> None:
        first = build_gate_snapshot(
            migration_checks=_passing_migration_checks(),
            failure_isolation_checks=_passing_failure_isolation_checks(),
            force3d_rollback_checks=_passing_force3d_rollback_checks(),
            database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
        )
        second = build_gate_snapshot(
            migration_checks=_passing_migration_checks(),
            failure_isolation_checks=_passing_failure_isolation_checks(),
            force3d_rollback_checks=_passing_force3d_rollback_checks(),
            database_url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
        )

        self.assertEqual(validate_gate_snapshot(first), [])
        self.assertEqual(first["status"], "passed")
        self.assertEqual(first["readiness_state"], "pre_live_rollout_readback_ready")
        self.assertFalse(first["closure_claim"])
        self.assertFalse(first["live_tenant_db_validated"])
        self.assertFalse(first["webgl_live_visual_validated"])
        self.assertEqual([stage["name"] for stage in first["stages"]], STAGE_ORDER)
        self.assertEqual(first["manifest_digest"], second["manifest_digest"])
        self.assertEqual(first["projection_digest"], second["projection_digest"])
        self.assertEqual(first["rollback_trace_digest"], second["rollback_trace_digest"])
        self.assertEqual(len(first["rollback_trace"]["trace_digest"]), 64)
        self.assertIn("force3d_load_or_render_failure", [step["name"] for step in first["rollback_trace"]["steps"]])
        self.assertIn("live tenant DB", " ".join(first["remaining_live_gaps"]))
        self.assertIn("GraphPage", " ".join(first["remaining_live_gaps"]))

    def test_unsafe_projection_read_mode_blocks_readback_without_live_claims(self) -> None:
        snapshot = build_gate_snapshot(
            read_mode="b_primary",
            migration_checks=_passing_migration_checks(),
            failure_isolation_checks=_passing_failure_isolation_checks(),
            force3d_rollback_checks=_passing_force3d_rollback_checks(),
        )

        self.assertEqual(snapshot["status"], "failed")
        self.assertFalse(snapshot["closure_claim"])
        self.assertFalse(snapshot["live_tenant_db_validated"])
        stages = {stage["name"]: stage for stage in snapshot["stages"]}
        self.assertEqual(stages["manifest_shape_readback"]["status"], "failed")
        self.assertEqual(stages["projection_contract_readback"]["status"], "failed")
        self.assertIn(
            "readiness.read_mode_pre_live_safe",
            " ".join(stages["projection_contract_readback"]["failures"]),
        )

    def test_rollback_trace_failure_is_isolated_from_visual_live_closure(self) -> None:
        force3d_checks = _passing_force3d_rollback_checks()
        force3d_checks["force3d_load_and_render_fallback_to_legacy"] = False

        snapshot = build_gate_snapshot(
            migration_checks=_passing_migration_checks(),
            failure_isolation_checks=_passing_failure_isolation_checks(),
            force3d_rollback_checks=force3d_checks,
        )

        self.assertEqual(snapshot["status"], "failed")
        self.assertFalse(snapshot["webgl_live_visual_validated"])
        stages = {stage["name"]: stage for stage in snapshot["stages"]}
        self.assertEqual(stages["rollback_ready_trace"]["status"], "failed")
        self.assertIn("force3d_load_and_render_fallback_to_legacy", stages["rollback_ready_trace"]["failures"])
        self.assertEqual(stages["force3d_visual_boundary_readback"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
