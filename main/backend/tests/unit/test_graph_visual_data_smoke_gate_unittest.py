from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.check_graph_visual_data_smoke_gate import (  # noqa: E402
    build_gate_snapshot,
    validate_gate_snapshot,
)


pytestmark = pytest.mark.unit


def _backend_data_evidence() -> dict:
    return {
        "backend_data_visual_smoke_validated": True,
        "backend_data_source_live": True,
        "response_envelope_success": True,
        "nodes_nonempty": True,
        "edges_nonempty": True,
        "graph_schema_version_present": True,
        "graph_payload": {
            "graph_schema_version": "v1",
            "nodes": [
                {"type": "Post", "id": "42", "properties": {"title": "Live Data"}},
                {"type": "Entity", "id": "ACME Corp", "properties": {"name": "ACME Corp"}},
            ],
            "edges": [
                {
                    "type": "MENTIONS_ENTITY",
                    "from": {"type": "Post", "id": "42"},
                    "to": {"type": "Entity", "id": "ACME Corp"},
                    "properties": {},
                }
            ],
        },
    }


def _live_ui_evidence() -> dict:
    return {
        "live_ui_smoke_validated": True,
        "backend_data_source_live": True,
        "graphpage_loaded_from_backend_endpoint": True,
        "force3d_canvas_nonblank": True,
        "force3d_scene_nodes_match_data": True,
        "graph3d_debug_stats_captured": True,
        "debug_stats": {
            "dataNodes": 2,
            "sceneNodeObjects": 2,
            "emptyDataNodes": 0,
            "emptySceneNodeObjects": 0,
        },
    }


class GraphVisualDataSmokeGateUnitTest(unittest.TestCase):
    def test_default_gate_is_partial_and_does_not_close_live_ui(self) -> None:
        snapshot = build_gate_snapshot()

        self.assertEqual(validate_gate_snapshot(snapshot), [])
        self.assertEqual(snapshot["status"], "passed")
        self.assertEqual(snapshot["readiness_state"], "partial")
        self.assertFalse(snapshot["closure_claim"])
        self.assertTrue(snapshot["fixture_smoke_validated"])
        self.assertFalse(snapshot["backend_data_visual_smoke_validated"])
        self.assertFalse(snapshot["live_ui_smoke_validated"])
        self.assertIn("partial/live-smoke boundary", snapshot["boundary"])

        stages = {stage["name"]: stage for stage in snapshot["stages"]}
        self.assertEqual(stages["fixture_visual_data_smoke"]["status"], "validated")
        self.assertEqual(stages["backend_data_visual_smoke"]["status"], "ready_not_run")
        self.assertEqual(stages["live_ui_force3d_smoke"]["status"], "not_run")
        self.assertIn("unrun live UI smoke keeps this gate partial", " ".join(snapshot["remaining_gaps"]))

    def test_backend_data_visual_smoke_does_not_stand_in_for_live_ui(self) -> None:
        snapshot = build_gate_snapshot(backend_data_evidence=_backend_data_evidence())

        self.assertEqual(validate_gate_snapshot(snapshot), [])
        self.assertEqual(snapshot["status"], "passed")
        self.assertEqual(snapshot["readiness_state"], "partial")
        self.assertTrue(snapshot["backend_data_visual_smoke_validated"])
        self.assertFalse(snapshot["live_ui_smoke_validated"])
        self.assertFalse(snapshot["closure_claim"])

        stages = {stage["name"]: stage for stage in snapshot["stages"]}
        self.assertEqual(stages["backend_data_visual_smoke"]["status"], "validated")
        self.assertEqual(stages["live_ui_force3d_smoke"]["status"], "ready_not_run")

    def test_live_ui_evidence_can_be_recorded_without_claiming_topic_closure(self) -> None:
        snapshot = build_gate_snapshot(
            backend_data_evidence=_backend_data_evidence(),
            live_ui_evidence=_live_ui_evidence(),
        )

        self.assertEqual(validate_gate_snapshot(snapshot), [])
        self.assertEqual(snapshot["status"], "passed")
        self.assertEqual(snapshot["readiness_state"], "live_ui_validated_non_closing")
        self.assertTrue(snapshot["backend_data_visual_smoke_validated"])
        self.assertTrue(snapshot["live_ui_smoke_validated"])
        self.assertFalse(snapshot["closure_claim"])
        self.assertEqual(snapshot["remaining_gaps"], [])

    def test_incomplete_backend_data_evidence_fails_instead_of_claiming_partial_success(self) -> None:
        snapshot = build_gate_snapshot(
            backend_data_evidence={
                "backend_data_visual_smoke_validated": True,
                "graph_payload": _backend_data_evidence()["graph_payload"],
            }
        )

        self.assertEqual(snapshot["status"], "failed")
        stages = {stage["name"]: stage for stage in snapshot["stages"]}
        self.assertEqual(stages["backend_data_visual_smoke"]["status"], "failed_evidence")
        self.assertIn("missing_true:backend_data_source_live", stages["backend_data_visual_smoke"]["failures"])


if __name__ == "__main__":
    unittest.main()
