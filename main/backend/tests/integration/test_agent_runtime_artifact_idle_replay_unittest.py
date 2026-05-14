from __future__ import annotations

import time
import unittest
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.agent_runtime.interactive_agent import InteractiveAgentRuntime
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore

pytestmark = pytest.mark.integration


def _never_run_agent_batch(**kwargs):
    raise AssertionError("agent_batch should not run for read-only replay scenarios")


def _parser_fallback(command: str) -> dict[str, str]:
    return {"command": command}


def _submitter(tasks, project_key, idempotency_key):
    return {"job_id": "unused"}


def _executor_snapshot() -> dict[str, str]:
    return {"status": "ok"}


class _ArtifactReplayPlanner:
    def __init__(self, *, query: str, artifact_ref: str) -> None:
        self.query = query
        self.artifact_ref = artifact_ref
        self.calls = 0

    def plan_next(self, *, context, available_tools, transcript, remaining_budget):
        self.calls += 1
        if transcript:
            return {"model_path": "fixed-s09-replay", "tool_calls": [], "final_answer": "artifact ready", "stop": True}
        return {
            "model_path": "fixed-s09-replay",
            "tool_calls": [
                {
                    "tool_name": "agent_artifact.search",
                    "input": {"query": self.query, "limit": 5},
                    "reason": "S-09 artifact lookup replay",
                },
                {
                    "tool_name": "agent_artifact.read",
                    "input": {"artifact_ref": self.artifact_ref},
                    "reason": "S-09 artifact read replay",
                },
            ],
            "final_answer": None,
            "stop": True,
        }


class AgentRuntimeArtifactIdleReplayTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgentSessionService(store=InMemoryAgentSessionStore())
        self.runtime = InteractiveAgentRuntime(service=self.service)

    def _run_turn(self, **overrides):
        return self.runtime.run_turn(
            message=overrides.pop("message"),
            project_key=overrides.pop("project_key", "demo_proj"),
            batch_loop_runner=overrides.pop("batch_loop_runner", _never_run_agent_batch),
            parser_fallback=_parser_fallback,
            submitter=_submitter,
            executor_snapshot=_executor_snapshot,
            **overrides,
        )

    def test_s09_artifact_search_and_read_replay_summarizes_existing_artifact(self):
        bundle = self.service.create_session(
            source="integration-test",
            entrypoint_type="interactive_agent",
            goal="S-09 seeded artifact session",
            project_key="demo_proj",
        )
        session_id = bundle["session"]["session_id"]
        seeded = self.service.store.upsert_artifact(
            {
                "session_id": session_id,
                "artifact_type": "research_summary_json",
                "name": "s09-market-brief.json",
                "mime_type": "application/json",
                "content_json": {
                    "title": "S-09 market brief",
                    "summary": "Existing artifact summary for S-09 replay.",
                    "findings": ["artifact.search/read can reuse session evidence"],
                },
                "metadata": {"scenario": "S-09", "summary": "Existing artifact summary for S-09 replay."},
            }
        )
        planner = _ArtifactReplayPlanner(query="s09-market-brief", artifact_ref=seeded["artifact_id"])

        out = self._run_turn(
            session_id=session_id,
            message="查看已有产物 artifact read s09-market-brief",
            run_loop_planner=planner,
        )

        self.assertEqual(out["agent_mode"], "read_only")
        self.assertEqual(out["loop_result"], {})
        self.assertEqual(out["plan"]["strategy"], "read-only-fast-path")
        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("agent_artifact.search", capability_ids)
        self.assertIn("agent_artifact.read", capability_ids)
        self.assertNotIn("agent_batch.nl_command.submit", capability_ids)

        search_call = next(item for item in out["capability_calls"] if item["capability_id"] == "agent_artifact.search")
        read_call = next(item for item in out["capability_calls"] if item["capability_id"] == "agent_artifact.read")
        self.assertEqual(search_call["status"], "completed")
        self.assertEqual(read_call["status"], "completed")
        self.assertEqual(search_call["result"]["total"], 1)
        self.assertEqual(search_call["result"]["items"][0]["name"], "s09-market-brief.json")
        self.assertEqual(read_call["result"]["artifact"]["artifact_id"], seeded["artifact_id"])
        self.assertIn("读取产物: s09-market-brief.json", out["final_answer"])
        self.assertGreaterEqual(planner.calls, 1)

    def test_s10_idle_status_chat_returns_fast_without_agent_batch(self):
        start = time.perf_counter()
        out = self._run_turn(message="当前状态怎么样？")
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 1.0)
        self.assertEqual(out["agent_mode"], "conversation")
        self.assertEqual(out["loop_result"], {})
        self.assertEqual(out["plan"]["strategy"], "read-only-fast-path")
        capability_ids = [item["capability_id"] for item in out["capability_calls"]]
        self.assertIn("agent_session.context.read", capability_ids)
        self.assertNotIn("agent_batch.nl_command.submit", capability_ids)
        self.assertTrue(all(item.get("protocol") == "read_only" for item in out["capability_calls"]))
        self.assertEqual(out["run_loop"]["tool_call_count"], len(out["capability_calls"]))


if __name__ == "__main__":
    unittest.main()
