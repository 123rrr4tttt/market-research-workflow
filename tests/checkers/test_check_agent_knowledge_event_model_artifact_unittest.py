#!/usr/bin/env python3
"""Focused tests for Agent/knowledge event-model smoke artifact checks."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_agent_knowledge_event_model_artifact.py"
SPEC = importlib.util.spec_from_file_location("check_agent_knowledge_event_model_artifact", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class AgentKnowledgeEventModelArtifactTestCase(unittest.TestCase):
    def make_repo(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)

    def write_json(self, root: Path, rel_path: str, payload: object) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def step(self, name: str, evidence: dict[str, object]) -> dict[str, object]:
        return {
            "name": name,
            "path": f"/api/v1/{name}",
            "http_status": 200,
            "status": checker.STATUS_PASSED,
            "evidence": evidence,
        }

    def payload(self, status: str = checker.STATUS_PASSED) -> dict[str, object]:
        return {
            "schema_version": checker.ARTIFACT_SCHEMA_VERSION,
            "status": status,
            "generated_at": "2026-05-25T00:00:00Z",
            "api_base": "http://127.0.0.1:8000",
            "project_key": "demo_proj",
            "smoke_id": "agent-knowledge-event-test",
            "steps": [
                self.step("typed_knowledge_live_sample", {"live_db_write": True, "record_count": 4}),
                self.step("governance_review_mutation", {"live_db_write": True, "current_review_state": "human_confirmed"}),
                self.step("writing_context", {"handoff_count": 1, "live_db_backed": True}),
                self.step(
                    "writing_keyword_cards",
                    {"publisher": "typed_knowledge", "publishers": ["typed_knowledge"], "typed_knowledge_card_count": 1},
                ),
                self.step("workflow_graph_draft", {"sync_status": "draft_saved"}),
                self.step("workflow_graph_submit", {"submit_status": "submitted"}),
                self.step("workflow_graph_audit", {"audit_count": 1}),
                self.step("workflow_graph_evidence_pack", {"selected_node_count": 2}),
                self.step(
                    "graph_writing_handoff_persist",
                    {"backend_marker": "workflow_graph.run_store", "run_id": "run-1", "handoff_id": "handoff-1"},
                ),
                self.step(
                    "handoff_replay",
                    {"event_count": 2, "event_types": ["handoff.persisted", "handoff.replayed"]},
                ),
                self.step("agent_session_create", {"session_id": "as-test"}),
                self.step("agent_session_message", {"message_id": "msg-test", "session_id": "as-test"}),
                self.step(
                    "agent_session_events_readback",
                    {"event_count": 2, "event_types": ["session.created", "message.created"]},
                ),
            ],
            "failures": [],
            "summary": {"passed_step_count": 13, "failed_step_count": 0, "blocked_step_count": 0},
            "evidence": {
                "typed_knowledge_live_db_write": True,
                "writing_context_handoff_count": 1,
                "keyword_card_publisher": "typed_knowledge",
                "graph_audit_count": 1,
                "evidence_pack_selected_node_count": 2,
                "handoff_backend_marker": "workflow_graph.run_store",
                "handoff_replay_event_count": 2,
                "handoff_replay_event_types": ["handoff.persisted", "handoff.replayed"],
                "agent_session_id": "as-test",
                "agent_event_count": 2,
            },
        }

    def test_passed_artifact_with_required_evidence_passes(self) -> None:
        root = self.make_repo()
        artifact = self.write_json(root, "agent-knowledge-event-model.json", self.payload())

        report = checker.build_check(artifact)

        self.assertEqual(checker.CHECK_SCHEMA_VERSION, report["schema_version"])
        self.assertEqual(checker.STATUS_PASSED, report["status"])
        self.assertEqual([], report["failures"])
        self.assertEqual(24, report["summary"]["check_count"])
        self.assertEqual(0, checker.main([str(artifact)]))

    def test_missing_typed_knowledge_publisher_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["steps"][3]["evidence"] = {"publisher": "serper", "publishers": ["serper"], "typed_knowledge_card_count": 0}  # type: ignore[index]
        payload["evidence"]["keyword_card_publisher"] = "serper"  # type: ignore[index]
        payload["evidence"]["keyword_card_typed_knowledge_count"] = 0  # type: ignore[index]
        artifact = self.write_json(root, "agent-knowledge-event-model.json", payload)

        report = checker.build_check(artifact)

        self.assertEqual(checker.STATUS_FAILED, report["status"])
        self.assertIn("keyword_card.publisher", report["failures"])

    def test_handoff_replay_without_replayed_event_fails(self) -> None:
        root = self.make_repo()
        payload = self.payload()
        payload["steps"][9]["evidence"] = {"event_count": 1, "event_types": ["handoff.persisted"]}  # type: ignore[index]
        payload["evidence"]["handoff_replay_event_types"] = ["handoff.persisted"]  # type: ignore[index]
        artifact = self.write_json(root, "agent-knowledge-event-model.json", payload)

        report = checker.build_check(artifact)

        self.assertEqual(checker.STATUS_FAILED, report["status"])
        self.assertIn("handoff.replay_persisted_and_replayed", report["failures"])

    def test_blocked_artifact_exits_zero_only_when_allowed(self) -> None:
        root = self.make_repo()
        payload = self.payload(status=checker.STATUS_BLOCKED)
        payload["steps"] = [
            {
                "name": "typed_knowledge_live_sample",
                "status": checker.STATUS_BLOCKED,
                "http_status": None,
                "reason": "backend_unreachable",
                "evidence": {},
            }
        ]
        payload["failures"] = ["typed_knowledge_live_sample:backend_unreachable"]
        artifact = self.write_json(root, "agent-knowledge-event-model.json", payload)

        self.assertEqual(checker.STATUS_BLOCKED, checker.build_check(artifact, allow_blocked=True)["status"])
        self.assertEqual(1, checker.main([str(artifact)]))
        self.assertEqual(0, checker.main([str(artifact), "--allow-blocked"]))


if __name__ == "__main__":
    unittest.main()
