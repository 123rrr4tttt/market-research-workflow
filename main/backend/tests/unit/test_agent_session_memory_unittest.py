from __future__ import annotations

import unittest

import pytest

from app.services.agent_runtime.interactive_agent import InteractiveAgentRuntime
from app.services.agent_runtime.session_memory import (
    SessionContextBudget,
    SessionMemoryUpdateThresholds,
    build_memory_correction_marker,
    build_session_context_summary,
    should_update_memory,
)
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore

pytestmark = pytest.mark.unit


def _bundle() -> dict:
    return {
        "session": {
            "session_id": "as-test",
            "source": "user",
            "entrypoint_type": "interactive_agent",
            "project_key": "demo_proj",
            "goal": "Collect market context",
            "status": "blocked",
            "current_phase": "implementation",
            "compat_mode": False,
        },
        "tasks": [
            {
                "task_id": "task-plan",
                "subject": "Plan interactive capabilities",
                "task_type": "interactive_plan",
                "phase": "research",
                "status": "completed",
                "result_summary": "Selected read-only tools.",
                "tool_use_count": 1,
                "token_usage": 500,
            },
            {
                "task_id": "task-execute",
                "subject": "Execute selected project capability",
                "task_type": "capability_execution",
                "phase": "implementation",
                "status": "blocked",
                "last_activity": "waiting for high-risk capability approval",
                "tool_use_count": 2,
                "token_usage": 700,
            },
        ],
        "messages": [
            {"message_id": "m1", "role": "user", "actor": "user", "content": "请列出来源库并等待审批"},
            {"message_id": "m2", "role": "assistant", "actor": "interactive_agent", "content": "已读取来源库。"},
        ],
        "events": [
            {"seq": 1, "event_type": "memory.updated", "payload": {"reason": "forced_refresh"}},
            {
                "seq": 2,
                "event_type": "interactive_agent.tool_call_result",
                "task_id": "task-execute",
                "payload": {
                    "turn_id": "turn-1",
                    "call_id": "call-project",
                    "capability_id": "project.summary.read",
                    "tool_name": "project.summary.read",
                    "protocol": "read_only",
                    "status": "completed",
                    "summary": "read project summary",
                    "result": {
                        "project_key": "demo_proj",
                        "source_library": {
                            "total": 2,
                            "enabled": 1,
                            "channels": {"generic_web": 1, "policy_api": 1},
                            "sample": [{"item_key": "demo.news", "channel_key": "generic_web", "enabled": True}],
                        },
                    },
                },
            },
            {
                "seq": 3,
                "event_type": "interactive_agent.tool_call_result",
                "task_id": "task-execute",
                "payload": {
                    "turn_id": "turn-1",
                    "call_id": "call-source",
                    "capability_id": "source_library.item.list",
                    "tool_name": "source_library.item.list",
                    "protocol": "read_only",
                    "status": "completed",
                    "summary": "listed source-library items",
                    "result": {
                        "total": 2,
                        "items": [{"item_key": "demo.news", "name": "Demo News", "channel_key": "generic_web"}],
                    },
                },
            },
        ],
        "artifacts": [
            {
                "artifact_id": "artifact-1",
                "task_id": "task-execute",
                "artifact_type": "interactive_agent.capability_call",
                "name": "call.json",
                "mime_type": "application/json",
                "metadata": {"turn_id": "turn-1", "capability_id": "source_library.item.list", "status": "completed"},
            }
        ],
        "approvals": [
            {
                "approval_id": "approval-1",
                "status": "pending",
                "requester_task_id": "task-execute",
                "binding_payload": {"capability_id": "workflow_graph.run"},
            }
        ],
    }


class AgentSessionMemoryUnitTest(unittest.TestCase):
    def test_build_session_context_summary_compresses_bundle_sections(self):
        summary = build_session_context_summary(_bundle(), latest_user_instruction="最新指令：只读摘要，不执行")

        self.assertEqual(summary["contract_version"], "agent_runtime.session_context_summary.v1")
        self.assertEqual(summary["stable_summary"]["counts"]["pending_approvals"], 1)
        self.assertEqual(summary["stable_summary"]["latest_user_instruction"], "最新指令：只读摘要，不执行")
        self.assertEqual(summary["project_context"]["source_library"]["total"], 2)
        self.assertEqual(summary["tool_use_summary"]["total_calls"], 2)
        self.assertEqual(summary["tool_use_summary"]["status_counts"]["completed"], 2)
        self.assertEqual(summary["budgeted_context"]["priority_order"][0], "latest_user_instruction")
        text = summary["budgeted_context"]["text"]
        self.assertLess(text.index("[latest_user_instruction]"), text.index("[approval_state]"))
        self.assertLess(text.index("[approval_state]"), text.index("[current_task]"))

    def test_budgeted_context_keeps_high_priority_sections_first(self):
        bundle = _bundle()
        bundle["messages"].extend(
            {"message_id": f"old-{index}", "role": "assistant", "actor": "agent", "content": "history " * 80}
            for index in range(20)
        )
        summary = build_session_context_summary(
            bundle,
            latest_user_instruction="Keep this instruction visible",
            budget=SessionContextBudget(
                max_chars=520,
                min_section_chars=80,
                per_section_max_chars={
                    "latest_user_instruction": 120,
                    "approval_state": 120,
                    "current_task": 120,
                    "tool_result_summary": 160,
                    "project_summary": 160,
                    "history_summary": 160,
                },
            ),
        )

        section_keys = [item["key"] for item in summary["budgeted_context"]["sections"]]
        self.assertEqual(section_keys[:3], ["latest_user_instruction", "approval_state", "current_task"])
        self.assertIn("history_summary", summary["budgeted_context"]["omitted_sections"])
        self.assertLessEqual(summary["budgeted_context"]["used_chars"], 520 + 10)

    def test_should_update_memory_reports_threshold_reasons(self):
        result = should_update_memory(
            _bundle(),
            thresholds=SessionMemoryUpdateThresholds(token_threshold=1000, event_threshold=2, tool_threshold=2),
        )

        self.assertTrue(result["should_update"])
        self.assertIn("token_threshold", result["reasons"])
        self.assertIn("event_threshold", result["reasons"])
        self.assertIn("tool_threshold", result["reasons"])
        self.assertEqual(result["metrics"]["event_count_since_memory_update"], 2)
        self.assertEqual(result["metrics"]["tool_result_count_since_memory_update"], 2)

    def test_should_update_memory_supports_explicit_summary_request(self):
        bundle = _bundle()
        bundle["events"] = [
            {"seq": 1, "event_type": "memory.updated", "payload": {}},
            {"seq": 2, "event_type": "interactive_agent.model_delta", "payload": {"summary": "idle"}},
        ]
        bundle["tasks"] = []
        bundle["messages"].append({"message_id": "m3", "role": "user", "actor": "user", "content": "请总结一下当前会话记忆"})

        result = should_update_memory(
            bundle,
            thresholds=SessionMemoryUpdateThresholds(token_threshold=99999, event_threshold=99, tool_threshold=99),
        )

        self.assertTrue(result["should_update"])
        self.assertEqual(result["reasons"], ["user_requested_summary"])
        self.assertEqual(result["metrics"]["event_count_since_memory_update"], 1)

    def test_memory_correction_marks_previous_summary_stale(self):
        bundle = _bundle()
        bundle["messages"].append(
            {
                "message_id": "m-correct",
                "role": "user",
                "actor": "user",
                "content": "之前你记忆里的来源库数量错了，请修正。",
            }
        )

        marker = build_memory_correction_marker(bundle["messages"])
        result = should_update_memory(
            bundle,
            thresholds=SessionMemoryUpdateThresholds(token_threshold=99999, event_threshold=99, tool_threshold=99),
        )
        summary = build_session_context_summary(bundle)

        self.assertTrue(marker["invalidates_previous_summary"])
        self.assertIn("user_corrected_memory", result["reasons"])
        self.assertTrue(result["correction"]["invalidates_previous_summary"])
        self.assertEqual(
            summary["stable_summary"]["memory_correction"]["handling"],
            "mark_previous_summary_stale_and_rebuild",
        )

    def test_interactive_agent_attaches_context_summary_to_final_metadata(self):
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        runtime = InteractiveAgentRuntime(service=service)

        def should_not_run(**kwargs):
            raise AssertionError("agent_batch should not run for capability questions")

        out = runtime.run_turn(
            message="你能做什么工具？",
            project_key="demo_proj",
            batch_loop_runner=should_not_run,
            parser_fallback=lambda command: {"command": command},
            submitter=lambda tasks, project_key, idem: {"job_id": "unused"},
            executor_snapshot=lambda: {"status": "ok"},
        )

        self.assertIn("context_summary", out)
        self.assertEqual(out["context_summary"]["stable_summary"]["session"]["session_id"], out["session"]["session_id"])
        assistant_messages = [item for item in out["messages"] if item.get("role") == "assistant"]
        self.assertTrue(assistant_messages)
        self.assertIn("context_summary", assistant_messages[-1]["metadata"])


if __name__ == "__main__":
    unittest.main()
