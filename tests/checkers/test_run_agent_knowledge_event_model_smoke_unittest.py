#!/usr/bin/env python3
"""Focused tests for Agent/knowledge event-model smoke artifact behavior."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_agent_knowledge_event_model_smoke.py"
SPEC = importlib.util.spec_from_file_location("run_agent_knowledge_event_model_smoke", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


class AgentKnowledgeEventModelSmokeTestCase(unittest.TestCase):
    def make_output_path(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name) / "artifact.json"

    def response(self, data: dict[str, object], status_code: int = 200) -> object:
        return smoke.HttpResult(
            status_code=status_code,
            body=json.dumps({"status": "ok", "data": data, "error": None, "meta": {}}),
        )

    def run_main(self, argv: list[str]) -> tuple[int, dict[str, object]]:
        output = Path(argv[argv.index("--output") + 1])
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = smoke.main(argv)
        return exit_code, json.loads(output.read_text(encoding="utf-8"))

    def test_passed_flow_writes_agent_knowledge_event_evidence(self) -> None:
        output = self.make_output_path()

        def fake_post(url: str, payload: dict[str, object] | None = None, *, timeout: float) -> object:
            if url.endswith("/typed-knowledge/live-sample?project_key=demo_proj"):
                return self.response(
                    {
                        "contract_version": "typed_knowledge.persistence_api_boundary.v1",
                        "repository": {
                            "live_db_write": True,
                            "repository_ref": "sqlalchemy://typed-knowledge/live-db",
                        },
                        "records": [
                            {"object_type": "knowledge_item", "object_key": "ki:robotics-policy"},
                            {"object_type": "topic_cluster", "object_key": "topic:robotics"},
                        ],
                        "writes": [],
                    }
                )
            if url.endswith("/typed-knowledge/governance/review-state"):
                return self.response(
                    {
                        "contract_version": "typed_knowledge.governance_review_state_mutation.v1",
                        "identity_ref": "demo_proj:knowledge_item:ki:robotics-policy",
                        "live_db_write": True,
                        "current": {"review_state": "human_confirmed"},
                    }
                )
            if url.endswith("/writing/keyword-cards"):
                return self.response(
                    {
                        "cards": [
                            {"card_id": "card-typed", "publisher": "typed_knowledge"},
                            {"card_id": "card-search", "publisher": "serper"},
                        ],
                        "source_count": {"resource": 2, "document": 0, "graph": 0},
                    }
                )
            if "/workflow-graph/curated/" in url and url.endswith("/draft"):
                return self.response({"sync_status": "draft_saved", "revision": 1, "graph_id": "graph"})
            if "/workflow-graph/curated/" in url and url.endswith("/submit"):
                return self.response({"submit_status": "submitted", "revision": 2, "graph_id": "graph"})
            if "/workflow-graph/curated/" in url and url.endswith("/evidence-pack"):
                return self.response(
                    {
                        "contract_version": "workflow_graph.evidence_pack.v1",
                        "selected_nodes": [{"node_id": "company-acme"}, {"node_id": "market-robotics"}],
                        "relations": [{"from": "company-acme", "to": "market-robotics"}],
                    }
                )
            if "/workflow-graph/curated/" in url and url.endswith("/handoff/writing"):
                return self.response(
                    {
                        "contract_version": "workflow_graph.writing_handoff.v1",
                        "handoff_id": "handoff-1",
                        "consumer": "writing",
                        "persistence": {
                            "backend_marker": "workflow_graph.run_store",
                            "event_type": "handoff.persisted",
                            "run_id": "run-1",
                            "handoff_id": "handoff-1",
                        },
                    }
                )
            if url.endswith("/agent-sessions"):
                return self.response({"session_id": "as-test"})
            if url.endswith("/agent-sessions/as-test/messages"):
                return self.response({"message": {"message_id": "msg-test"}})
            raise AssertionError(f"unexpected POST {url}")

        def fake_get(url: str, *, timeout: float) -> object:
            if url.endswith("/typed-knowledge/writing-context?project_key=demo_proj"):
                return self.response(
                    {
                        "live_db_backed": True,
                        "typed_knowledge_context": {
                            "contract_version": "writing.typed_knowledge_context.v1",
                            "source": "typed_knowledge",
                            "consumer": "writing.keyword_card",
                            "handoffs": [{"knowledge_item_key": "ki:robotics-policy"}],
                        },
                    }
                )
            if "/workflow-graph/curated/" in url and url.endswith("/audit?limit=50"):
                return self.response({"items": [{"event_type": "draft_saved"}]})
            if url.endswith("/workflow-graph/runs/run-1/handoff/handoff-1/replay"):
                return self.response(
                    {
                        "run_id": "run-1",
                        "handoff_id": "handoff-1",
                        "backend_marker": "workflow_graph.run_store",
                        "events": [
                            {"event_type": "handoff.persisted"},
                            {"event_type": "handoff.replayed"},
                        ],
                    }
                )
            if url.endswith("/agent-sessions/as-test/events"):
                return self.response(
                    {
                        "items": [
                            {"event_type": "session.created"},
                            {"event_type": "message.created"},
                        ]
                    }
                )
            raise AssertionError(f"unexpected GET {url}")

        with (
            patch.object(smoke, "_http_post_json", side_effect=fake_post),
            patch.object(smoke, "_http_get", side_effect=fake_get),
        ):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    "demo_proj",
                    "--output",
                    str(output),
                    "--json",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(smoke.SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual(smoke.STATUS_PASSED, payload["status"])
        self.assertEqual([], payload["failures"])
        self.assertEqual(13, payload["summary"]["passed_step_count"])
        self.assertTrue(payload["evidence"]["typed_knowledge_live_db_write"])
        self.assertEqual("typed_knowledge", payload["evidence"]["keyword_card_publisher"])
        self.assertEqual("workflow_graph.run_store", payload["evidence"]["handoff_backend_marker"])
        self.assertEqual(["handoff.persisted", "handoff.replayed"], payload["evidence"]["handoff_replay_event_types"])
        self.assertEqual("as-test", payload["evidence"]["agent_session_id"])
        self.assertEqual(2, payload["evidence"]["agent_event_count"])

    def test_backend_unreachable_is_blocked_and_requires_allow_blocked(self) -> None:
        output = self.make_output_path()
        with patch.object(
            smoke,
            "_http_post_json",
            return_value=smoke.HttpResult(status_code=None, body="", error="connection refused"),
        ):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    "demo_proj",
                    "--output",
                    str(output),
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual(smoke.STATUS_BLOCKED, payload["status"])
        self.assertIn("typed_knowledge_live_sample:backend_unreachable", payload["failures"])

        with patch.object(
            smoke,
            "_http_post_json",
            return_value=smoke.HttpResult(status_code=None, body="", error="connection refused"),
        ):
            exit_code, payload = self.run_main(
                [
                    "--api-base",
                    "http://127.0.0.1:8000",
                    "--project-key",
                    "demo_proj",
                    "--output",
                    str(output),
                    "--allow-blocked",
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertEqual(smoke.STATUS_BLOCKED, payload["status"])


if __name__ == "__main__":
    unittest.main()
