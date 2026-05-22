from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.check_graph_editing_audit_durability import (  # noqa: E402
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
        self.assertFalse(snapshot["graphpage_audit_controls_validated"])
        self.assertFalse(snapshot["live_db_audit_durability_validated"])

        stages = {stage["name"]: stage for stage in snapshot["stages"]}
        self.assertEqual(stages["repo_local_audit_readback_contract"]["status"], "validated")
        self.assertEqual(stages["live_db_audit_durability"]["status"], "configured_not_run")
        self.assertIn(
            stages["graphpage_audit_rollback_readback_ui"]["status"],
            {"not_exposed", "ready_not_run"},
        )
        self.assertIn("repo-local audit/readback contract", snapshot["boundary"])
        self.assertIn("live backend", " ".join(snapshot["remaining_gaps"]))
        self.assertIn("tenant DB", " ".join(snapshot["remaining_gaps"]))

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
        self.assertTrue(snapshot["live_db_audit_durability_validated"])
        self.assertFalse(snapshot["graphpage_audit_controls_validated"])
        self.assertFalse(snapshot["closure_claim"])
        self.assertEqual(snapshot["readiness_state"], "repo_local_validated_live_gaps_open")

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
