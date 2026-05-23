from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.check_graph_editing_audit_durability import (  # noqa: E402
    CONFLICT_READBACK_GRAPH_ID,
    CONFLICT_READBACK_PROJECT_KEY,
    TENANT_LIKE_GRAPH_ID,
    TENANT_LIKE_PROJECT_KEY,
    build_gate_snapshot,
    validate_gate_snapshot,
)


pytestmark = pytest.mark.unit


def _live_db_evidence() -> dict:
    return {
        "live_db_audit_durability_validated": True,
        "curated_submit_audit_readback_from_fresh_session": True,
        "curated_rollback_audit_readback_from_fresh_session": True,
        "handoff_persist_replay_readback_from_fresh_session": True,
        "tenant_project_scope_checked": True,
    }


def _graphpage_ui_evidence() -> dict:
    return {
        "graphpage_audit_readback_validated": True,
        "graphpage_rollback_control_validated": True,
        "graphpage_used_live_backend": True,
        "audit_records_visible_after_submit_rollback": True,
        "handoff_replay_visible_or_linked": True,
    }


class GraphEditingAuditDurabilityGateUnitTest(unittest.TestCase):
    def test_default_gate_validates_repo_local_readback_and_keeps_live_gaps_open(self) -> None:
        snapshot = build_gate_snapshot(database_url="postgresql://tenant/db")

        self.assertEqual(validate_gate_snapshot(snapshot), [])
        self.assertEqual(snapshot["status"], "passed")
        self.assertEqual(snapshot["readiness_state"], "repo_local_validated_live_gaps_open")
        self.assertFalse(snapshot["closure_claim"])
        self.assertTrue(snapshot["repo_local_audit_readback_validated"])
        self.assertTrue(snapshot["tenant_like_fixture_audit_trace_validated"])
        self.assertTrue(snapshot["conflict_rollback_readback_validated"])
        self.assertTrue(snapshot["live_tenant_db_audit_open"])
        self.assertTrue(snapshot["graphpage_audit_controls_validated"])
        self.assertFalse(snapshot["live_db_audit_durability_validated"])

        stages = {stage["name"]: stage for stage in snapshot["stages"]}
        self.assertEqual(stages["repo_local_audit_readback_contract"]["status"], "validated")
        self.assertEqual(stages["tenant_like_fixture_audit_trace"]["status"], "validated")
        self.assertEqual(stages["conflict_rollback_readback_fixture"]["status"], "validated")
        self.assertEqual(stages["live_db_audit_durability"]["status"], "configured_not_run")
        self.assertEqual(stages["graphpage_audit_rollback_readback_ui"]["status"], "validated")
        self.assertTrue(
            stages["graphpage_audit_rollback_readback_ui"]["metrics"]["static_checks"][
                "graphpage_e2e_covers_audit_rollback_and_handoff_replay"
            ]
        )
        self.assertIn("repo-local audit/readback contract", snapshot["boundary"])
        self.assertIn("tenant-like fixture audit trace", snapshot["boundary"])
        self.assertIn("conflict rollback readback fixture", snapshot["boundary"])
        self.assertIn("live_tenant_db_audit_open=true", snapshot["boundary"])
        self.assertIn("tenant DB", " ".join(snapshot["remaining_gaps"]))

    def test_tenant_like_fixture_proves_audit_readback_and_rollback_trace(self) -> None:
        snapshot = build_gate_snapshot()
        stages = {stage["name"]: stage for stage in snapshot["stages"]}
        fixture_stage = stages["tenant_like_fixture_audit_trace"]
        metrics = fixture_stage["metrics"]

        self.assertEqual(validate_gate_snapshot(snapshot), [])
        self.assertEqual(fixture_stage["status"], "validated")
        self.assertEqual(metrics["tenant_like_project_key"], TENANT_LIKE_PROJECT_KEY)
        self.assertEqual(metrics["tenant_like_graph_id"], TENANT_LIKE_GRAPH_ID)
        self.assertEqual(metrics["tenant_like_audit_count"], 3)
        self.assertEqual(metrics["tenant_like_raw_audit_actions"], ["submit", "submit", "rollback"])
        self.assertEqual(metrics["tenant_like_readback_audit_actions"], ["rollback", "submit", "submit"])
        self.assertEqual(metrics["tenant_like_rollback_revision"], 3)
        self.assertIn("node-wave18-baseline", metrics["tenant_like_restored_node_ids"])
        self.assertNotIn("node-wave18-experimental", metrics["tenant_like_restored_node_ids"])
        self.assertTrue(metrics["live_tenant_db_audit_open"])
        self.assertTrue(snapshot["live_tenant_db_audit_open"])

    def test_conflict_rollback_fixture_validates_marker_intent_and_readback(self) -> None:
        snapshot = build_gate_snapshot()
        stages = {stage["name"]: stage for stage in snapshot["stages"]}
        fixture_stage = stages["conflict_rollback_readback_fixture"]
        metrics = fixture_stage["metrics"]

        self.assertEqual(validate_gate_snapshot(snapshot), [])
        self.assertEqual(fixture_stage["status"], "validated")
        self.assertEqual(metrics["conflict_readback_project_key"], CONFLICT_READBACK_PROJECT_KEY)
        self.assertEqual(metrics["conflict_readback_graph_id"], CONFLICT_READBACK_GRAPH_ID)
        self.assertTrue(metrics["audit_event_validated"])
        self.assertTrue(metrics["conflict_did_not_append_audit_event"])
        self.assertEqual(
            metrics["conflict_marker"],
            {"category": "version_conflict", "expected_revision": 1, "actual_revision": 2},
        )
        self.assertEqual(metrics["raw_audit_actions"], ["submit", "submit", "rollback"])
        self.assertEqual(metrics["readback_audit_actions"], ["rollback", "submit", "submit"])
        self.assertEqual(metrics["rollback_intent"]["target_version_id"], "cver-wave20-baseline")
        self.assertEqual(metrics["rollback_intent"]["rollback_scope"], "snapshot_restore")
        self.assertTrue(metrics["rollback_intent"]["requires_base_revision_match"])
        self.assertEqual(metrics["readback_summary"]["graph_revision"], 3)
        self.assertIn("node-wave20-baseline", metrics["readback_summary"]["restored_node_ids"])
        self.assertNotIn("node-wave20-candidate", metrics["readback_summary"]["restored_node_ids"])
        self.assertTrue(snapshot["conflict_rollback_readback_validated"])
        self.assertTrue(snapshot["live_tenant_db_audit_open"])

    def test_incomplete_live_db_evidence_fails_closed(self) -> None:
        snapshot = build_gate_snapshot(
            live_db_audit_evidence={"live_db_audit_durability_validated": True}
        )

        self.assertEqual(snapshot["status"], "failed")
        stages = {stage["name"]: stage for stage in snapshot["stages"]}
        self.assertEqual(stages["live_db_audit_durability"]["status"], "failed_evidence")
        self.assertIn(
            "missing_true:curated_submit_audit_readback_from_fresh_session",
            stages["live_db_audit_durability"]["failures"],
        )
        self.assertIn("do not claim production audit durability", " ".join(snapshot["remaining_gaps"]))

    def test_live_db_evidence_can_be_recorded_without_topic_closure(self) -> None:
        snapshot = build_gate_snapshot(live_db_audit_evidence=_live_db_evidence())

        self.assertEqual(validate_gate_snapshot(snapshot), [])
        self.assertEqual(snapshot["status"], "passed")
        self.assertTrue(snapshot["repo_local_audit_readback_validated"])
        self.assertTrue(snapshot["tenant_like_fixture_audit_trace_validated"])
        self.assertTrue(snapshot["conflict_rollback_readback_validated"])
        self.assertTrue(snapshot["live_tenant_db_audit_open"])
        self.assertTrue(snapshot["live_db_audit_durability_validated"])
        self.assertTrue(snapshot["graphpage_audit_controls_validated"])
        self.assertFalse(snapshot["closure_claim"])
        self.assertEqual(snapshot["readiness_state"], "live_audit_evidence_recorded_non_closing")

    def test_complete_ui_evidence_can_be_recorded_without_live_db_closure(self) -> None:
        snapshot = build_gate_snapshot(graphpage_ui_evidence=_graphpage_ui_evidence())

        self.assertEqual(validate_gate_snapshot(snapshot), [])
        self.assertEqual(snapshot["status"], "passed")
        self.assertTrue(snapshot["repo_local_audit_readback_validated"])
        self.assertTrue(snapshot["graphpage_audit_controls_validated"])
        self.assertFalse(snapshot["live_db_audit_durability_validated"])
        self.assertFalse(snapshot["closure_claim"])
        self.assertEqual(snapshot["readiness_state"], "repo_local_validated_live_gaps_open")

    def test_incomplete_ui_evidence_fails_closed(self) -> None:
        evidence = _graphpage_ui_evidence()
        evidence.pop("handoff_replay_visible_or_linked")
        snapshot = build_gate_snapshot(graphpage_ui_evidence=evidence)

        self.assertEqual(snapshot["status"], "failed")
        stages = {stage["name"]: stage for stage in snapshot["stages"]}
        self.assertEqual(stages["graphpage_audit_rollback_readback_ui"]["status"], "failed_evidence")
        self.assertIn(
            "missing_true:handoff_replay_visible_or_linked",
            stages["graphpage_audit_rollback_readback_ui"]["failures"],
        )


if __name__ == "__main__":
    unittest.main()
